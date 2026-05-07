"""Paso 4: Verificacion de compresion de ATR a lo largo de un patron VCP candidato.

============================================================================
DESCRIPCION DEL PASO
============================================================================
Evalua si la volatilidad intradia (medida por ATR) se comprime durante la
formacion de una secuencia de contracciones decrecientes. Este es un filtro
complementario al Paso 3: no solo las contracciones de precio deben ser
menores, sino que la volatilidad medida por ATR tambien debe disminuir.

============================================================================
METODOS IMPLEMENTADOS
============================================================================
1. "ratio" (recomendado):
   - Compara ATR al inicio vs al final: ATR_end / ATR_start <= threshold.
   - Simple y directo. Con threshold=0.85, exige al menos 15% de compresion.

2. "trend":
   - Ajusta regresion lineal (OLS) sobre la serie de ATR en el rango del patron.
   - Exige pendiente negativa con R^2 >= min_r_squared.
   - Usa scipy.stats.linregress.

3. "ratio_normalized":
   - Normaliza ATR por precio antes de comparar: (ATR_end/P_end) / (ATR_start/P_start).
   - Corrige por cambios de nivel de precio durante el patron.

============================================================================
CALCULO DEL ATR (Wilder's Smoothing / RMA)
============================================================================
Esta version usa Wilder's Smoothing (Recursive Moving Average), que es el
estandar de la industria para ATR (a diferencia de la SMA usada en el Paso 1):

1. True Range: TR_t = max(H_t - L_t, |H_t - C_{t-1}|, |L_t - C_{t-1}|)
2. Primer ATR = SMA de los primeros ``period`` TRs.
3. ATR_t = ATR_{t-1} * (1 - 1/period) + TR_t * (1/period)

El RMA es mas suave que la SMA y reacciona mas lentamente a cambios bruscos,
lo cual es deseable para medir compresion de volatilidad a mediano plazo.

============================================================================
LIBRERIAS UTILIZADAS
============================================================================
- numpy: Arrays para calculo iterativo del ATR con Wilder's smoothing.
- pandas: Series temporales, concat para True Range, slicing por fechas.
- scipy.stats.linregress: Regresion lineal para metodo "trend".
"""

from __future__ import annotations

import logging
from typing import Literal

import numpy as np
import pandas as pd
from scipy.stats import linregress

from models.types import ATRCompressionResult, DecreasingSequence

logger = logging.getLogger(__name__)

_VALID_METHODS = {"ratio", "trend", "ratio_normalized"}


def compute_atr(ohlc: pd.DataFrame, period: int = 14) -> pd.Series:
    """Calcula el ATR usando Wilder's smoothing (RMA) sobre la serie OHLC completa.

    True Range = max(high - low, |high - prev_close|, |low - prev_close|).
    ATR = RMA del TR: primer valor = SMA de los primeros ``period`` TRs validos,
    luego formula recursiva con alpha = 1/period.

    Args:
        ohlc: DataFrame con columnas ['high', 'low', 'close'] e indice
            DatetimeIndex.
        period: Periodo del ATR. Default 14.

    Returns:
        pd.Series indexada igual que ohlc, con NaN en los primeros ``period``
        valores hasta que el ATR se estabiliza.
    """
    high = ohlc["high"]
    low = ohlc["low"]
    close = ohlc["close"]
    prev_close = close.shift(1)

    tr = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)

    atr_values = np.full(len(tr), np.nan)
    if len(tr) <= period:
        return pd.Series(atr_values, index=ohlc.index, name="atr")

    atr_values[period] = tr.iloc[1 : period + 1].mean()
    alpha = 1.0 / period
    for i in range(period + 1, len(tr)):
        atr_values[i] = atr_values[i - 1] * (1 - alpha) + tr.iloc[i] * alpha

    return pd.Series(atr_values, index=ohlc.index, name="atr")


def _check_compression_ratio(
    atr_start: float, atr_end: float, threshold: float
) -> tuple[bool, dict]:
    """Verifica que atr_end / atr_start <= threshold.

    Args:
        atr_start: ATR al inicio del patron.
        atr_end: ATR al final del patron.
        threshold: Ratio maximo permitido.

    Returns:
        Tupla (passes, method_metrics).
    """
    ratio = atr_end / atr_start if atr_start > 0 else float("inf")
    return ratio <= threshold, {"ratio_observed": ratio, "threshold": threshold}


def _check_compression_trend(
    atr_series: pd.Series, min_r_squared: float
) -> tuple[bool, dict]:
    """Ajusta regresion lineal sobre atr_series y exige pendiente negativa con R2 minimo.

    Args:
        atr_series: Serie de ATR sobre el rango del patron.
        min_r_squared: R2 minimo requerido.

    Returns:
        Tupla (passes, method_metrics).
    """
    clean = atr_series.dropna()
    if len(clean) < 3:
        return False, {"error": "insufficient_points"}

    x = np.arange(len(clean), dtype=np.float64)
    y = clean.to_numpy(dtype=np.float64)
    result = linregress(x, y)

    slope = float(result.slope)
    r_squared = float(result.rvalue**2)

    metrics = {
        "slope": slope,
        "r_squared": r_squared,
        "min_r_squared_required": min_r_squared,
    }
    return slope < 0 and r_squared >= min_r_squared, metrics


def _check_compression_ratio_normalized(
    atr_start: float,
    atr_end: float,
    price_start: float,
    price_end: float,
    threshold: float,
) -> tuple[bool, dict]:
    """Verifica que (atr_end/price_end) / (atr_start/price_start) <= threshold.

    Args:
        atr_start: ATR al inicio del patron.
        atr_end: ATR al final del patron.
        price_start: Precio close al inicio del patron.
        price_end: Precio close al final del patron.
        threshold: Ratio normalizado maximo permitido.

    Returns:
        Tupla (passes, method_metrics).
    """
    metrics_base = {
        "threshold": threshold,
        "price_start": price_start,
        "price_end": price_end,
    }
    if atr_start <= 0 or price_start <= 0 or price_end <= 0:
        return False, {"normalized_ratio_observed": float("inf"), **metrics_base}

    norm_start = atr_start / price_start
    norm_end = atr_end / price_end
    ratio = norm_end / norm_start

    return ratio <= threshold, {"normalized_ratio_observed": ratio, **metrics_base}


def verify_atr_compression(
    sequence: DecreasingSequence,
    ohlc: pd.DataFrame,
    method: Literal["ratio", "trend", "ratio_normalized"] = "ratio",
    atr_period: int = 14,
    ratio_threshold: float = 0.7,
    min_r_squared: float = 0.5,
) -> ATRCompressionResult:
    """Verifica si el ATR se comprime a lo largo de una secuencia VCP candidata.

    El patron se define temporalmente entre el primer high de la secuencia
    y el ultimo low.

    Args:
        sequence: DecreasingSequence devuelta por detect_decreasing_sequence.
        ohlc: DataFrame OHLC del mismo activo, debe contener las fechas del
            patron mas al menos ``atr_period`` bars previos.
        method: "ratio", "trend" o "ratio_normalized".
        atr_period: Periodo del ATR. Default 14.
        ratio_threshold: Umbral para methods "ratio" y "ratio_normalized".
        min_r_squared: R2 minimo para method="trend".

    Returns:
        ATRCompressionResult con passes, metricas y datos del calculo.

    Raises:
        ValueError: Si method es invalido, si las fechas no estan en el ohlc,
            o si no hay suficientes bars previos para ATR estabilizado.
    """
    if method not in _VALID_METHODS:
        raise ValueError(
            f"Invalid method '{method}'. Must be one of {sorted(_VALID_METHODS)}"
        )

    start_date = sequence.contractions[0].high_swing.date
    end_date = sequence.contractions[-1].low_swing.date

    if start_date not in ohlc.index:
        raise ValueError(f"start_date {start_date.date()} not found in ohlc.index")
    if end_date not in ohlc.index:
        raise ValueError(f"end_date {end_date.date()} not found in ohlc.index")

    start_loc = ohlc.index.get_loc(start_date)
    if start_loc < atr_period:
        raise ValueError(
            f"Need at least {atr_period} bars before start_date "
            f"{start_date.date()}, but only {start_loc} available"
        )

    atr_series = compute_atr(ohlc, atr_period)
    atr_start = float(atr_series.loc[start_date])
    atr_end = float(atr_series.loc[end_date])

    if method == "ratio":
        passes, metrics = _check_compression_ratio(atr_start, atr_end, ratio_threshold)
    elif method == "trend":
        passes, metrics = _check_compression_trend(
            atr_series.loc[start_date:end_date], min_r_squared
        )
    else:
        price_start = float(ohlc.loc[start_date, "close"])
        price_end = float(ohlc.loc[end_date, "close"])
        passes, metrics = _check_compression_ratio_normalized(
            atr_start, atr_end, price_start, price_end, ratio_threshold
        )

    logger.debug(
        "ATR compression check (%s): passes=%s, atr_start=%.4f, atr_end=%.4f",
        method,
        passes,
        atr_start,
        atr_end,
    )
    return ATRCompressionResult(
        passes=passes,
        method=method,
        atr_start=atr_start,
        atr_end=atr_end,
        start_date=start_date,
        end_date=end_date,
        atr_period=atr_period,
        method_metrics=metrics,
    )


def verify_atr_compression_batch(
    sequences: dict[pd.Timestamp, DecreasingSequence | None],
    ohlc: pd.DataFrame,
    method: Literal["ratio", "trend", "ratio_normalized"] = "ratio",
    atr_period: int = 14,
    ratio_threshold: float = 0.7,
    min_r_squared: float = 0.5,
) -> dict[pd.Timestamp, ATRCompressionResult | None]:
    """Aplica verify_atr_compression a un batch de secuencias.

    Args:
        sequences: Dict {evaluation_date: DecreasingSequence | None}.
        ohlc: DataFrame OHLC.
        method: Metodo de compresion.
        atr_period: Periodo del ATR.
        ratio_threshold: Umbral para ratio/ratio_normalized.
        min_r_squared: R2 minimo para trend.

    Returns:
        Dict ordenado {evaluation_date: ATRCompressionResult | None}.
    """
    results: dict[pd.Timestamp, ATRCompressionResult | None] = {}
    for dt, seq in sequences.items():
        if seq is None:
            results[dt] = None
            continue
        try:
            results[dt] = verify_atr_compression(
                sequence=seq,
                ohlc=ohlc,
                method=method,
                atr_period=atr_period,
                ratio_threshold=ratio_threshold,
                min_r_squared=min_r_squared,
            )
        except ValueError:
            logger.warning(
                "Skipping ATR compression for %s: insufficient data", dt.date()
            )
            results[dt] = None

    n_evaluated = sum(1 for v in results.values() if v is not None)
    n_passed = sum(1 for v in results.values() if v is not None and v.passes)
    logger.debug(
        "ATR compression batch: %d evaluated, %d passed (%.1f%%)",
        n_evaluated,
        n_passed,
        100 * n_passed / max(n_evaluated, 1),
    )
    return results
