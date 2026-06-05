"""Paso 6: Deteccion de pivote y trigger de breakout para el patron VCP.

============================================================================
DESCRIPCION DEL PASO
============================================================================
Ultima pieza del detector heuristico: dado un VCP candidato confirmado
(secuencia decreciente + compresion de ATR + contraccion de volumen),
identifica el punto de pivote y genera una senal de compra cuando el precio
supera el pivote con confirmacion de volumen.

============================================================================
IDENTIFICACION DEL PIVOTE
============================================================================
El pivote se define como el high_swing.price de la **ultima** contraccion
de la secuencia. Este es el nivel de resistencia que el precio debe superar
para confirmar el breakout.

El stop-loss natural es el low_swing.price de esa misma contraccion —
si el precio cae debajo de ese nivel, el patron fallo.

============================================================================
TRIGGER DE BREAKOUT
============================================================================
Para que se genere una senal de compra en una fecha dada:
1. El close del dia debe ser > pivot_price (precio supero la resistencia).
2. Confirmacion de volumen (opcional pero recomendada):
   - "ratio": volumen del dia >= ratio_threshold * media de volumen de los
     ultimos N dias (default: 1.5x media de 50 dias, clasico de Minervini).
   - "percentile": volumen del dia >= percentil P de los ultimos N dias.

============================================================================
PIPELINE COMPLETO (run_full_vcp_pipeline)
============================================================================
Orquesta los 6 pasos en secuencia para cada fecha de evaluacion:
  Paso 1: Detectar swings (una sola vez sobre toda la serie).
  Paso 2: Calcular contracciones (una sola vez sobre todos los swings).
  Paso 3: Para cada fecha, buscar secuencia decreciente.
  Paso 4: Verificar compresion de ATR.
  Paso 5: Verificar contraccion de volumen (opcional).
  Paso 6: Evaluar trigger de breakout (precio > pivot + volumen).

============================================================================
LIBRERIAS UTILIZADAS
============================================================================
- numpy: Calculo de percentiles para metodo "percentile" de volumen.
- pandas: Slicing temporal, acceso a precios y volumenes por fecha.
- Importa funciones de los pasos 1-5 para el pipeline completo.
"""

from __future__ import annotations

import logging
from typing import Literal

import numpy as np
import pandas as pd

from models.types import (
    ATRCompressionResult,
    DecreasingSequence,
    PivotInfo,
    VCPSignal,
    VolumeContractionResult,
)
from vcp_detection.heuristic.atr_compression import compute_atr, verify_atr_compression
from vcp_detection.heuristic.contractions import compute_contractions
from vcp_detection.heuristic.decreasing_sequence import detect_decreasing_sequence
from vcp_detection.heuristic.swing_detector import SwingDetector
from vcp_detection.heuristic.volume_contraction import verify_volume_contraction

logger = logging.getLogger(__name__)

_VALID_VOLUME_METHODS = {"ratio", "percentile"}


def identify_pivot(sequence: DecreasingSequence) -> PivotInfo:
    """Identifica el pivote a partir de una DecreasingSequence.

    El pivote se define como el high_swing.price del ultimo par HIGH->LOW
    (es decir, la ultima Contraction de la secuencia).

    Args:
        sequence: DecreasingSequence ya validada por detect_decreasing_sequence.

    Returns:
        PivotInfo con price, date, last_low_price, last_low_date y referencia
        a la secuencia.

    Raises:
        ValueError: Si sequence.contractions esta vacia.
    """
    if not sequence.contractions:
        raise ValueError("Cannot identify pivot from empty contractions list")

    last_contraction = sequence.contractions[-1]
    return PivotInfo(
        price=last_contraction.high_swing.price,
        date=last_contraction.high_swing.date,
        last_low_price=last_contraction.low_swing.price,
        last_low_date=last_contraction.low_swing.date,
        sequence=sequence,
    )


def _check_volume_ratio(
    volume_today: float, volume_recent: pd.Series, ratio_threshold: float
) -> tuple[bool, dict]:
    """Verifica que volume_today >= ratio_threshold * mean(volume_recent).

    Args:
        volume_today: Volumen del dia de breakout.
        volume_recent: Serie con los volumenes de los M dias previos.
        ratio_threshold: Default 1.5.

    Returns:
        Tupla (passes, method_metrics).
    """
    volume_avg = float(volume_recent.mean()) if len(volume_recent) > 0 else 0.0
    ratio = volume_today / volume_avg if volume_avg > 0 else float("inf")
    passes = ratio >= ratio_threshold

    return passes, {
        "applied": True,
        "method": "ratio",
        "value_observed": ratio,
        "threshold_value": ratio_threshold,
        "passed": passes,
        "lookback_days": len(volume_recent),
        "volume_today": volume_today,
        "volume_avg": volume_avg,
    }


def _check_volume_percentile(
    volume_today: float, volume_recent: pd.Series, percentile: int
) -> tuple[bool, dict]:
    """Verifica que volume_today >= percentile_P(volume_recent).

    Args:
        volume_today: Volumen del dia de breakout.
        volume_recent: Serie con los volumenes de los M dias previos.
        percentile: 0-100. Default 80.

    Returns:
        Tupla (passes, method_metrics).
    """
    if len(volume_recent) == 0:
        return False, {
            "applied": True,
            "method": "percentile",
            "value_observed": volume_today,
            "threshold_value": 0.0,
            "percentile": percentile,
            "passed": False,
            "lookback_days": 0,
        }

    threshold_value = float(np.percentile(volume_recent.dropna().to_numpy(), percentile))
    passes = volume_today >= threshold_value

    return passes, {
        "applied": True,
        "method": "percentile",
        "value_observed": volume_today,
        "threshold_value": threshold_value,
        "percentile": percentile,
        "passed": passes,
        "lookback_days": len(volume_recent),
    }


def detect_breakout_signal(
    sequence: DecreasingSequence,
    atr_compression_result: ATRCompressionResult,
    ohlc: pd.DataFrame,
    evaluation_date: pd.Timestamp,
    volume_method: Literal["ratio", "percentile"] = "ratio",
    volume_ratio_threshold: float = 1.5,
    volume_percentile: int = 80,
    volume_lookback_days: int = 50,
    require_volume_confirmation: bool = True,
    volume_contraction_result: VolumeContractionResult | None = None,
    volume_confirmation_window: int = 1,
    volume_lookback_from_pattern: bool = False,
    volume_confirmation_forward: int = 0,
) -> VCPSignal | None:
    """Detecta si hay senal de compra VCP en evaluation_date.

    Args:
        sequence: DecreasingSequence ya validada.
        atr_compression_result: ATRCompressionResult con passes=True.
        ohlc: DataFrame OHLC. Columna "volume" opcional.
        evaluation_date: Fecha en la cual evaluar la senal.
        volume_method: "ratio" o "percentile".
        volume_ratio_threshold: Default 1.5 (Minervini clasico).
        volume_percentile: Default 80.
        volume_lookback_days: Dias previos para baseline de volumen.
            Se ignora si volume_lookback_from_pattern=True.
        require_volume_confirmation: Si False, bypasea el filtro de volumen.
        volume_contraction_result: Resultado de verify_volume_contraction si
            se evaluo previamente.
        volume_confirmation_window: Dias (incluyendo hoy) donde buscar al
            menos un dia con volumen alto tras el cruce del pivot. Con 1
            (default) exige volumen alto el mismo dia del breakout. Con 3,
            acepta si hubo volumen alto en los ultimos 3 dias.
        volume_lookback_from_pattern: Si True, usa la duracion del patron
            VCP (primer high a ultimo low) como periodo de lookback para
            calcular el volumen promedio de referencia, en vez del fijo
            volume_lookback_days.
        volume_confirmation_forward: Dias hacia adelante (despues del
            breakout de precio) donde buscar confirmacion de volumen.
            Con 0 (default) solo busca hacia atras (comportamiento original).
            Con N > 0, si el volumen no se confirma en la ventana backward,
            busca en los N dias siguientes verificando que el precio siga
            por encima del pivot. Si en algun dia forward el close cae
            <= pivot, se cancela la busqueda. La senal se emite en el dia
            donde se confirma el volumen (no en el dia del breakout de precio).

    Returns:
        VCPSignal si el trigger de precio (y opcionalmente de volumen) se cumple,
        None en caso contrario.

    Raises:
        ValueError: Si volume_method no es valido o evaluation_date no esta en ohlc.
    """
    if volume_method not in _VALID_VOLUME_METHODS:
        raise ValueError(
            f"Invalid volume_method '{volume_method}'. "
            f"Must be one of {sorted(_VALID_VOLUME_METHODS)}"
        )

    if evaluation_date not in ohlc.index:
        raise ValueError(f"evaluation_date {evaluation_date} not found in ohlc.index")

    if not atr_compression_result.passes:
        logger.warning(
            "ATR compression did not pass for evaluation_date %s, returning None",
            evaluation_date,
        )
        return None

    pivot_info = identify_pivot(sequence)

    if evaluation_date < pivot_info.last_low_date:
        raise ValueError(
            f"evaluation_date {evaluation_date.date()} is before last_low_date "
            f"{pivot_info.last_low_date.date()} of the sequence"
        )

    close_today = float(ohlc.loc[evaluation_date, "close"])
    if close_today <= pivot_info.price:
        return None

    effective_lookback = volume_lookback_days
    if volume_lookback_from_pattern:
        pattern_start = sequence.contractions[0].high_swing.date
        pattern_end = sequence.contractions[-1].low_swing.date
        if pattern_start in ohlc.index and pattern_end in ohlc.index:
            start_loc = ohlc.index.get_loc(pattern_start)
            end_loc = ohlc.index.get_loc(pattern_end)
            effective_lookback = max(end_loc - start_loc, 10)

    volume_confirmation = _evaluate_volume(
        ohlc=ohlc,
        evaluation_date=evaluation_date,
        volume_method=volume_method,
        volume_ratio_threshold=volume_ratio_threshold,
        volume_percentile=volume_percentile,
        volume_lookback_days=effective_lookback,
        require_volume_confirmation=require_volume_confirmation,
        volume_confirmation_window=volume_confirmation_window,
    )

    backward_passed = not volume_confirmation["applied"] or volume_confirmation["passed"]

    if not backward_passed and volume_confirmation_forward > 0:
        eval_loc = ohlc.index.get_loc(evaluation_date)
        max_forward_loc = min(eval_loc + volume_confirmation_forward, len(ohlc) - 1)

        for fwd_loc in range(eval_loc + 1, max_forward_loc + 1):
            fwd_date = ohlc.index[fwd_loc]
            fwd_close = float(ohlc.iloc[fwd_loc]["close"])

            if fwd_close <= pivot_info.price:
                break

            fwd_vol_confirmation = _evaluate_volume(
                ohlc=ohlc,
                evaluation_date=fwd_date,
                volume_method=volume_method,
                volume_ratio_threshold=volume_ratio_threshold,
                volume_percentile=volume_percentile,
                volume_lookback_days=effective_lookback,
                require_volume_confirmation=require_volume_confirmation,
                volume_confirmation_window=1,
            )

            if fwd_vol_confirmation.get("passed", False):
                fwd_vol_confirmation["forward_confirmed"] = True
                fwd_vol_confirmation["breakout_date"] = evaluation_date
                fwd_vol_confirmation["confirmation_delay_days"] = fwd_loc - eval_loc
                volume_confirmation = fwd_vol_confirmation
                evaluation_date = fwd_date
                close_today = fwd_close
                backward_passed = True
                break

    if not backward_passed:
        return None

    suggested_stop = pivot_info.last_low_price
    stop_distance_pct = (close_today - suggested_stop) / close_today

    logger.debug(
        "VCP breakout signal at %s: entry=%.4f, pivot=%.4f, stop=%.4f (%.1f%%)",
        evaluation_date.date(),
        close_today,
        pivot_info.price,
        suggested_stop,
        stop_distance_pct * 100,
    )
    return VCPSignal(
        signal_date=evaluation_date,
        entry_price=close_today,
        pivot_price=pivot_info.price,
        suggested_stop=suggested_stop,
        suggested_stop_distance_pct=stop_distance_pct,
        pivot_info=pivot_info,
        atr_compression=atr_compression_result,
        volume_confirmation=volume_confirmation,
        volume_contraction=volume_contraction_result,
        metadata={
            "n_contractions": sequence.n_contractions,
            "depths_pct": sequence.depths_pct,
            "atr_method": atr_compression_result.method,
            "entry_distance_pct": (close_today - pivot_info.price) / pivot_info.price,
        },
    )


def _evaluate_volume(
    ohlc: pd.DataFrame,
    evaluation_date: pd.Timestamp,
    volume_method: str,
    volume_ratio_threshold: float,
    volume_percentile: int,
    volume_lookback_days: int,
    require_volume_confirmation: bool,
    volume_confirmation_window: int = 1,
) -> dict:
    """Evalua la confirmacion de volumen para un breakout.

    Soporta una ventana de confirmacion: en vez de exigir volumen alto
    solo en el dia exacto del breakout, busca si hubo volumen alto en
    alguno de los ultimos ``volume_confirmation_window`` dias (incluyendo
    hoy). Con window=1 (default) se comporta igual que antes.

    Args:
        ohlc: DataFrame OHLC.
        evaluation_date: Fecha del breakout candidato.
        volume_method: "ratio" o "percentile".
        volume_ratio_threshold: Umbral para method="ratio".
        volume_percentile: Percentil para method="percentile".
        volume_lookback_days: Dias de lookback para calcular baseline.
        require_volume_confirmation: Si False, bypasea completamente.
        volume_confirmation_window: Dias hacia atras (incluyendo hoy)
            donde buscar al menos un dia con volumen alto. Default 1.

    Returns:
        Dict con info del filtro de volumen aplicado.
    """
    if not require_volume_confirmation:
        return {"applied": False, "reason": "config_bypass"}

    has_volume = "volume" in ohlc.columns and ohlc["volume"].notna().any()
    if not has_volume:
        return {"applied": False, "reason": "no_volume_column"}

    eval_loc = ohlc.index.get_loc(evaluation_date)
    lookback_start = max(0, eval_loc - volume_lookback_days)
    volume_recent = ohlc["volume"].iloc[lookback_start:eval_loc]

    window = max(1, volume_confirmation_window)
    window_start = max(0, eval_loc - window + 1)
    window_vols = ohlc["volume"].iloc[window_start:eval_loc + 1]

    best_metrics = None
    for vol_date, vol_value in window_vols.items():
        vol_value = float(vol_value)
        if volume_method == "ratio":
            _, metrics = _check_volume_ratio(vol_value, volume_recent, volume_ratio_threshold)
        else:
            _, metrics = _check_volume_percentile(vol_value, volume_recent, volume_percentile)

        metrics["confirmation_window"] = window
        metrics["confirmed_on"] = vol_date

        if metrics["passed"]:
            return metrics
        if best_metrics is None or vol_value > best_metrics.get("volume_today", 0):
            best_metrics = metrics

    return best_metrics


def detect_breakout_signals_batch(
    sequences_with_compression: dict[
        pd.Timestamp,
        tuple[DecreasingSequence, ATRCompressionResult] | None,
    ],
    ohlc: pd.DataFrame,
    volume_method: Literal["ratio", "percentile"] = "ratio",
    volume_ratio_threshold: float = 1.5,
    volume_percentile: int = 80,
    volume_lookback_days: int = 50,
    require_volume_confirmation: bool = True,
) -> dict[pd.Timestamp, VCPSignal | None]:
    """Aplica detect_breakout_signal a un batch de candidatos.

    Args:
        sequences_with_compression: Dict {evaluation_date: (seq, atr_result) | None}.
        ohlc: DataFrame OHLC.
        volume_method: Metodo de confirmacion de volumen.
        volume_ratio_threshold: Umbral para ratio.
        volume_percentile: Percentil para percentile.
        volume_lookback_days: Dias de lookback.
        require_volume_confirmation: Si False, bypasea volumen.

    Returns:
        Dict ordenado {evaluation_date: VCPSignal | None}.
    """
    results: dict[pd.Timestamp, VCPSignal | None] = {}
    for dt, entry in sequences_with_compression.items():
        if entry is None:
            results[dt] = None
            continue
        seq, atr_result = entry
        try:
            results[dt] = detect_breakout_signal(
                sequence=seq,
                atr_compression_result=atr_result,
                ohlc=ohlc,
                evaluation_date=dt,
                volume_method=volume_method,
                volume_ratio_threshold=volume_ratio_threshold,
                volume_percentile=volume_percentile,
                volume_lookback_days=volume_lookback_days,
                require_volume_confirmation=require_volume_confirmation,
            )
        except ValueError:
            logger.warning("Skipping breakout detection for %s: invalid data", dt.date())
            results[dt] = None

    n_signals = sum(1 for v in results.values() if v is not None)
    logger.debug(
        "Breakout batch: %d evaluated, %d signals generated",
        len(results),
        n_signals,
    )
    return results


def run_full_vcp_pipeline(
    ohlc: pd.DataFrame,
    swing_detector: SwingDetector,
    sequence_params: dict,
    compression_params: dict,
    breakout_params: dict,
    evaluation_dates: pd.DatetimeIndex | None = None,
    volume_contraction_params: dict | None = None,
    deduplicate: bool = False,
    dedup_cooldown_bars: int = 1,
    precomputed_swings=None,
    precomputed_contractions=None,
    precomputed_atr: pd.Series | None = None,
) -> dict[pd.Timestamp, VCPSignal | None]:
    """Ejecuta el pipeline completo: swings -> contracciones -> secuencias
    decrecientes -> compresion ATR -> (volume contraction) -> senal de breakout.

    Args:
        ohlc: DataFrame OHLC con DatetimeIndex.
        swing_detector: Instancia de SwingDetector ya configurada.
        sequence_params: Kwargs para detect_decreasing_sequence.
        compression_params: Kwargs para verify_atr_compression.
        breakout_params: Kwargs para detect_breakout_signal.
        evaluation_dates: Fechas a evaluar. Si None, usa todo ohlc.index.
        volume_contraction_params: Si no es None, kwargs para
            verify_volume_contraction.
        deduplicate: Si True, emite solo la primera senal por patron.
        dedup_cooldown_bars: Barras minimas despues de invalidacion.
        precomputed_swings: Swings precalculados. Si None, se calculan.
        precomputed_contractions: Contracciones precalculadas. Si None, se calculan.
        precomputed_atr: Serie ATR precalculada. Si None, se calcula.

    Returns:
        Dict ordenado {evaluation_date: VCPSignal | None}.
    """
    if evaluation_dates is None:
        evaluation_dates = ohlc.index

    swings = precomputed_swings if precomputed_swings is not None else swing_detector.detect(ohlc)
    all_contractions = precomputed_contractions if precomputed_contractions is not None else compute_contractions(swings, ohlc)

    atr_period = compression_params.get("atr_period", 14)
    if precomputed_atr is None:
        precomputed_atr = compute_atr(ohlc, atr_period)

    active_pivot: float | None = None
    active_stop: float | None = None
    invalidated_at: int | None = None

    results: dict[pd.Timestamp, VCPSignal | None] = {}
    for dt in evaluation_dates:
        dt_loc = ohlc.index.get_loc(dt)

        if deduplicate and active_pivot is not None and active_stop is not None:
            close_today = float(ohlc.loc[dt, "close"])
            if close_today < active_stop:
                invalidated_at = dt_loc
                active_pivot = None
                active_stop = None

        seq = detect_decreasing_sequence(
            all_contractions,
            evaluation_date=dt,
            ohlc_index=ohlc.index,
            **sequence_params,
        )
        if seq is None:
            results[dt] = None
            continue

        try:
            atr_result = verify_atr_compression(seq, ohlc, **compression_params, precomputed_atr=precomputed_atr)
        except ValueError:
            results[dt] = None
            continue

        if not atr_result.passes:
            results[dt] = None
            continue

        vol_contraction_result: VolumeContractionResult | None = None
        if volume_contraction_params is not None:
            try:
                vol_contraction_result = verify_volume_contraction(
                    sequence=seq, ohlc=ohlc, **volume_contraction_params,
                )
            except ValueError:
                results[dt] = None
                continue
            if not vol_contraction_result.passes:
                results[dt] = None
                continue

        try:
            signal = detect_breakout_signal(
                sequence=seq,
                atr_compression_result=atr_result,
                ohlc=ohlc,
                evaluation_date=dt,
                volume_contraction_result=vol_contraction_result,
                **breakout_params,
            )
        except ValueError:
            results[dt] = None
            continue

        if signal is None:
            results[dt] = None
            continue

        if deduplicate:
            pivot_price = signal.pivot_price
            is_same_pattern = (
                active_pivot is not None
                and abs(pivot_price - active_pivot) < 1e-10
            )
            in_cooldown = (
                invalidated_at is not None
                and (dt_loc - invalidated_at) < dedup_cooldown_bars
            )

            if is_same_pattern or in_cooldown:
                results[dt] = None
                continue

            active_pivot = pivot_price
            active_stop = signal.suggested_stop
            invalidated_at = None

        results[dt] = signal

    n_signals = sum(1 for v in results.values() if v is not None)
    logger.debug(
        "Full VCP pipeline: %d dates evaluated, %d signals generated (%.1f%%)",
        len(evaluation_dates),
        n_signals,
        100 * n_signals / max(len(evaluation_dates), 1),
    )
    return results
