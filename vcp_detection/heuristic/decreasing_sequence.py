"""Paso 3: Detector de secuencias decrecientes de contracciones (regla central del VCP).

============================================================================
DESCRIPCION DEL PASO
============================================================================
Evalua si las ultimas N contracciones dentro de una ventana temporal forman
una secuencia monotonicamente decreciente. Esta es la regla central del patron
VCP de Minervini: las contracciones deben ser cada vez menores, indicando que
la volatilidad se comprime y la oferta se seca.

Ademas de la monotonia, se aplican **filtros de calidad**:
- max_depth_pct: rechaza secuencias con contracciones individuales muy profundas
  (indicarían una caida de Stage 4, no una base saludable).
- min_total_reduction: exige que la ultima contraccion sea significativamente
  menor que la primera (rechaza secuencias "tecnicamente decrecientes" pero
  sin compresion real).

============================================================================
METODOS DE MONOTONIA
============================================================================
1. "strict": Cada depth[i+1] < depth[i] estrictamente.
   - Muy restrictivo con datos reales (el ruido de mercado causa falsos negativos).

2. "tolerance" (recomendado): Permite depth[i+1] <= depth[i] * (1 + tolerance).
   - Con tolerance=0.10, si la contraccion anterior fue 8.0% se acepta hasta 8.8%.
   - Balance entre sensibilidad y robustez al ruido.

3. "robust_trend": Ajusta regresion lineal sobre las profundidades y exige
   pendiente negativa con R^2 >= min_r_squared.
   - Requiere minimo 3 contracciones.
   - Usa scipy.stats.linregress.

============================================================================
FILTROS DE CALIDAD (post-monotonia)
============================================================================
- max_depth_pct: Si alguna contraccion individual supera este umbral (ej: 25%),
  la secuencia se rechaza.
- min_total_reduction: depths[-1] / depths[0] <= threshold (ej: 0.70 significa
  que la ultima contraccion debe ser <= 70% de la primera).

============================================================================
ALGORITMO
============================================================================
1. Filtrar contracciones por confirmed_at <= evaluation_date (anti look-ahead).
2. Filtrar por ventana temporal (lookback_bars desde evaluation_date).
3. Probar las ultimas k contracciones para k desde max_contractions hasta
   min_contractions. Devuelve la primera (mas larga) que pase.
4. Aplicar filtros de calidad opcionales.

============================================================================
LIBRERIAS UTILIZADAS
============================================================================
- numpy: Generacion de arrays para regresion lineal.
- pandas: Manejo de timestamps y DatetimeIndex para ventana temporal.
- scipy.stats.linregress: Regresion lineal para metodo "robust_trend".
"""

from __future__ import annotations

import logging
from typing import Literal

import numpy as np
import pandas as pd
from scipy.stats import linregress

from models.types import Contraction, DecreasingSequence

logger = logging.getLogger(__name__)

_VALID_METHODS = {"strict", "tolerance", "robust_trend"}


def detect_decreasing_sequence(
    contractions: list[Contraction],
    evaluation_date: pd.Timestamp,
    method: Literal["strict", "tolerance", "robust_trend"] = "tolerance",
    min_contractions: int = 2,
    max_contractions: int = 6,
    lookback_bars: int = 80,
    tolerance: float = 0.1,
    min_r_squared: float = 0.5,
    ohlc_index: pd.DatetimeIndex | None = None,
    max_depth_pct: float | None = None,
    min_total_reduction: float | None = None,
) -> DecreasingSequence | None:
    """Evalua si existe una secuencia decreciente de contracciones terminando
    en o antes de evaluation_date.

    Args:
        contractions: Lista de Contraction (output de compute_contractions).
        evaluation_date: Fecha en la cual se evalua la presencia del patron.
        method: "strict", "tolerance" o "robust_trend".
        min_contractions: Minimo de contracciones para secuencia valida.
        max_contractions: Maximo a considerar.
        lookback_bars: Ventana temporal hacia atras desde evaluation_date.
        tolerance: Solo para method="tolerance". Default 0.1 (10%).
        min_r_squared: Solo para method="robust_trend". Default 0.5.
        ohlc_index: DatetimeIndex opcional para contar bars de trading.
        max_depth_pct: Profundidad maxima permitida por contraccion individual.
        min_total_reduction: Ratio maximo depths[-1]/depths[0].

    Returns:
        DecreasingSequence si encontro secuencia valida, None en caso contrario.

    Raises:
        ValueError: Si method es invalido, min_contractions < 2, o
            max_contractions < min_contractions.
    """
    _validate_params(method, min_contractions, max_contractions)

    eligible = _filter_contractions(contractions, evaluation_date, lookback_bars, ohlc_index)

    if len(eligible) < min_contractions:
        return None

    checker = _get_monotonicity_checker(method)

    upper = min(max_contractions, len(eligible))
    for k in range(upper, min_contractions - 1, -1):
        tail = eligible[-k:]
        depths = [c.depth_pct for c in tail]

        if method == "strict":
            passes, metrics = checker(depths)
        elif method == "tolerance":
            passes, metrics = checker(depths, tolerance)
        else:
            passes, metrics = checker(depths, min_r_squared)

        if not passes:
            continue

        if not _passes_quality_filters(depths, max_depth_pct, min_total_reduction, metrics):
            continue

        return DecreasingSequence(
            contractions=tail,
            evaluation_date=evaluation_date,
            method=method,
            method_metrics=metrics,
            n_contractions=k,
            depths_pct=depths,
        )

    return None


def scan_for_sequences(
    contractions: list[Contraction],
    evaluation_dates: pd.DatetimeIndex,
    method: Literal["strict", "tolerance", "robust_trend"] = "tolerance",
    min_contractions: int = 2,
    max_contractions: int = 6,
    lookback_bars: int = 80,
    tolerance: float = 0.1,
    min_r_squared: float = 0.5,
    ohlc_index: pd.DatetimeIndex | None = None,
    max_depth_pct: float | None = None,
    min_total_reduction: float | None = None,
) -> dict[pd.Timestamp, DecreasingSequence | None]:
    """Aplica detect_decreasing_sequence sobre multiples fechas de evaluacion.

    Args:
        contractions: Lista de Contraction.
        evaluation_dates: Fechas sobre las cuales evaluar.
        method: Metodo de monotonia.
        min_contractions: Minimo de contracciones.
        max_contractions: Maximo de contracciones.
        lookback_bars: Ventana temporal.
        tolerance: Tolerancia para method="tolerance".
        min_r_squared: R^2 minimo para method="robust_trend".
        ohlc_index: DatetimeIndex opcional.
        max_depth_pct: Profundidad maxima permitida por contraccion individual.
        min_total_reduction: Ratio maximo depths[-1]/depths[0].

    Returns:
        Dict ordenado {evaluation_date: DecreasingSequence | None}.
    """
    results: dict[pd.Timestamp, DecreasingSequence | None] = {}
    for dt in evaluation_dates:
        results[dt] = detect_decreasing_sequence(
            contractions=contractions,
            evaluation_date=dt,
            method=method,
            min_contractions=min_contractions,
            max_contractions=max_contractions,
            lookback_bars=lookback_bars,
            tolerance=tolerance,
            min_r_squared=min_r_squared,
            ohlc_index=ohlc_index,
            max_depth_pct=max_depth_pct,
            min_total_reduction=min_total_reduction,
        )
    n_detected = sum(1 for v in results.values() if v is not None)
    logger.debug(
        "Scanned %d dates: %d detections (%.1f%%)",
        len(evaluation_dates),
        n_detected,
        100 * n_detected / max(len(evaluation_dates), 1),
    )
    return results


# ---------------------------------------------------------------------------
# Quality filters
# ---------------------------------------------------------------------------


def _passes_quality_filters(
    depths: list[float],
    max_depth_pct: float | None,
    min_total_reduction: float | None,
    metrics: dict,
) -> bool:
    """Aplica filtros de calidad opcionales sobre una secuencia candidata.

    Args:
        depths: Lista de profundidades en orden cronologico.
        max_depth_pct: Profundidad maxima por contraccion individual.
        min_total_reduction: Ratio maximo depths[-1]/depths[0].
        metrics: Dict de metricas del checker, se enriquece in-place.

    Returns:
        True si pasa todos los filtros activos.
    """
    if max_depth_pct is not None:
        worst = max(depths)
        metrics["max_depth_observed"] = worst
        metrics["max_depth_threshold"] = max_depth_pct
        if worst > max_depth_pct:
            return False

    if min_total_reduction is not None and len(depths) >= 2 and depths[0] > 0:
        total_reduction = depths[-1] / depths[0]
        metrics["total_reduction_observed"] = total_reduction
        metrics["total_reduction_threshold"] = min_total_reduction
        if total_reduction > min_total_reduction:
            return False

    return True


# ---------------------------------------------------------------------------
# Monotonicity checkers
# ---------------------------------------------------------------------------


def _is_strictly_decreasing(depths: list[float]) -> tuple[bool, dict]:
    """Verifica si cada depth es estrictamente menor que el anterior.

    Args:
        depths: Lista de profundidades en orden cronologico.

    Returns:
        Tupla (passes, metrics).
    """
    for i in range(1, len(depths)):
        if depths[i] >= depths[i - 1]:
            return False, {"all_strict_decreasing": False}
    return True, {"all_strict_decreasing": True}


def _is_decreasing_with_tolerance(
    depths: list[float], tolerance: float
) -> tuple[bool, dict]:
    """Verifica monotonia decreciente con margen de tolerancia.

    Exige depths[i+1] <= depths[i] * (1 + tolerance) para cada par consecutivo.

    Args:
        depths: Lista de profundidades en orden cronologico.
        tolerance: Margen permitido (ej: 0.1 = 10%).

    Returns:
        Tupla (passes, metrics).
    """
    max_ratio = 0.0
    for i in range(1, len(depths)):
        if depths[i - 1] > 0:
            ratio = depths[i] / depths[i - 1]
            max_ratio = max(max_ratio, ratio)
            if depths[i] > depths[i - 1] * (1 + tolerance):
                return False, {
                    "max_ratio_observed": max_ratio,
                    "tolerance_used": tolerance,
                }
    return True, {"max_ratio_observed": max_ratio, "tolerance_used": tolerance}


def _is_robust_decreasing_trend(
    depths: list[float], min_r_squared: float
) -> tuple[bool, dict]:
    """Ajusta regresion lineal y exige pendiente negativa con R^2 minimo.

    Args:
        depths: Lista de profundidades en orden cronologico.
        min_r_squared: R^2 minimo requerido.

    Returns:
        Tupla (passes, metrics).
    """
    if len(depths) < 3:
        return False, {"error": "insufficient_points"}

    x = np.arange(len(depths), dtype=np.float64)
    y = np.array(depths, dtype=np.float64)
    result = linregress(x, y)

    slope = float(result.slope)
    r_squared = float(result.rvalue ** 2)

    metrics = {
        "slope": slope,
        "r_squared": r_squared,
        "min_r_squared_required": min_r_squared,
    }
    passes = slope < 0 and r_squared >= min_r_squared
    return passes, metrics


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _validate_params(method: str, min_contractions: int, max_contractions: int) -> None:
    """Valida parametros de entrada.

    Raises:
        ValueError: Si los parametros son invalidos.
    """
    if method not in _VALID_METHODS:
        raise ValueError(
            f"Invalid method '{method}'. Must be one of {sorted(_VALID_METHODS)}"
        )
    if min_contractions < 2:
        raise ValueError(
            f"min_contractions must be >= 2, got {min_contractions}"
        )
    if max_contractions < min_contractions:
        raise ValueError(
            f"max_contractions ({max_contractions}) must be >= "
            f"min_contractions ({min_contractions})"
        )


def _filter_contractions(
    contractions: list[Contraction],
    evaluation_date: pd.Timestamp,
    lookback_bars: int,
    ohlc_index: pd.DatetimeIndex | None,
) -> list[Contraction]:
    """Filtra contracciones por confirmed_at y ventana temporal.

    Args:
        contractions: Lista completa de contracciones.
        evaluation_date: Fecha de evaluacion.
        lookback_bars: Ventana hacia atras.
        ohlc_index: Indice de trading days opcional.

    Returns:
        Lista filtrada y ordenada cronologicamente.
    """
    confirmed = [c for c in contractions if c.confirmed_at <= evaluation_date]

    if ohlc_index is not None:
        valid_dates = ohlc_index[ohlc_index <= evaluation_date]
        if len(valid_dates) > lookback_bars:
            cutoff = valid_dates[-lookback_bars]
        elif len(valid_dates) > 0:
            cutoff = valid_dates[0]
        else:
            return []
    else:
        cutoff = evaluation_date - pd.Timedelta(days=lookback_bars)

    eligible = [c for c in confirmed if c.low_swing.date >= cutoff]
    eligible.sort(key=lambda c: c.low_swing.date)
    return eligible


def _get_monotonicity_checker(method: str):
    """Devuelve la funcion de chequeo de monotonia correspondiente al metodo."""
    return {
        "strict": _is_strictly_decreasing,
        "tolerance": _is_decreasing_with_tolerance,
        "robust_trend": _is_robust_decreasing_trend,
    }[method]
