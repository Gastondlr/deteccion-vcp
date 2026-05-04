"""Paso 5: Verificacion de contraccion de volumen durante la formacion del patron VCP.

============================================================================
DESCRIPCION DEL PASO
============================================================================
Evalua si el volumen (o un proxy como transactions) decrece durante la
formacion de la secuencia de contracciones. Segun Minervini, la oferta debe
"secarse" durante la formacion de la base — el volumen decreciente confirma
que los vendedores se agotan y la presion de venta disminuye.

Para cada contraccion de la secuencia, se calcula el volumen promedio en el
rango [high_date, low_date], y luego se evalua si la serie de volumenes
promedio es decreciente.

============================================================================
METODOS IMPLEMENTADOS
============================================================================
1. "ratio" (recomendado):
   - Compara volumen promedio de la primera contraccion vs la ultima:
     vol_last / vol_first <= threshold.
   - Con threshold=0.85, exige que el volumen de la ultima contraccion sea
     como maximo 85% del de la primera.

2. "per_contraction":
   - Verifica que cada contraccion tenga menor volumen promedio que la anterior.
   - Permite tolerancia: vol[i+1] <= vol[i] * (1 + tolerance).

3. "trend":
   - Ajusta regresion lineal (OLS) sobre los volumenes promedio por contraccion.
   - Exige pendiente negativa con R^2 >= min_r_squared.
   - Requiere minimo 3 contracciones.

============================================================================
LIBRERIAS UTILIZADAS
============================================================================
- numpy: Arrays para regresion lineal.
- pandas: Slicing temporal del volumen por rango de fechas, calculo de media.
- scipy.stats.linregress: Regresion lineal para metodo "trend".
"""

from __future__ import annotations

import logging
from typing import Literal

import numpy as np
import pandas as pd
from scipy.stats import linregress

from models.types import DecreasingSequence, VolumeContractionResult

logger = logging.getLogger(__name__)

_VALID_METHODS = {"per_contraction", "trend", "ratio"}


def _avg_volume_per_contraction(
    sequence: DecreasingSequence,
    ohlc: pd.DataFrame,
    volume_column: str,
) -> list[float]:
    """Calcula el volumen promedio durante cada contraccion de la secuencia.

    Para cada contraccion (high_date -> low_date), calcula la media del volumen
    en ese rango de fechas.

    Args:
        sequence: DecreasingSequence con las contracciones.
        ohlc: DataFrame con la columna de volumen y DatetimeIndex.
        volume_column: Nombre de la columna a usar.

    Returns:
        Lista de volumenes promedio, uno por contraccion, en orden cronologico.
    """
    avg_volumes = []
    for c in sequence.contractions:
        mask = (ohlc.index >= c.high_swing.date) & (ohlc.index <= c.low_swing.date)
        vol_slice = ohlc.loc[mask, volume_column]
        avg_volumes.append(float(vol_slice.mean()) if len(vol_slice) > 0 else 0.0)
    return avg_volumes


def _check_per_contraction(
    avg_volumes: list[float], tolerance: float
) -> tuple[bool, dict]:
    """Verifica que cada contraccion tenga menor volumen promedio que la anterior.

    Permite tolerancia: vol[i+1] <= vol[i] * (1 + tolerance).

    Args:
        avg_volumes: Volumen promedio por contraccion en orden cronologico.
        tolerance: Margen permitido (ej: 0.1 = 10%).

    Returns:
        Tupla (passes, method_metrics).
    """
    if len(avg_volumes) < 2:
        return False, {"error": "insufficient_contractions"}

    max_ratio = 0.0
    for i in range(1, len(avg_volumes)):
        if avg_volumes[i - 1] > 0:
            ratio = avg_volumes[i] / avg_volumes[i - 1]
            max_ratio = max(max_ratio, ratio)
            if avg_volumes[i] > avg_volumes[i - 1] * (1 + tolerance):
                return False, {
                    "max_ratio_observed": max_ratio,
                    "tolerance_used": tolerance,
                    "failed_at_contraction": i,
                }

    return True, {"max_ratio_observed": max_ratio, "tolerance_used": tolerance}


def _check_volume_trend(
    avg_volumes: list[float], min_r_squared: float
) -> tuple[bool, dict]:
    """Ajusta regresion lineal sobre volumenes promedio y exige pendiente negativa.

    Args:
        avg_volumes: Volumen promedio por contraccion en orden cronologico.
        min_r_squared: R2 minimo requerido.

    Returns:
        Tupla (passes, method_metrics).
    """
    if len(avg_volumes) < 3:
        return False, {"error": "insufficient_points"}

    x = np.arange(len(avg_volumes), dtype=np.float64)
    y = np.array(avg_volumes, dtype=np.float64)
    result = linregress(x, y)

    slope = float(result.slope)
    r_squared = float(result.rvalue**2)

    metrics = {
        "slope": slope,
        "r_squared": r_squared,
        "min_r_squared_required": min_r_squared,
    }
    return slope < 0 and r_squared >= min_r_squared, metrics


def _check_volume_ratio(
    avg_volumes: list[float], threshold: float
) -> tuple[bool, dict]:
    """Verifica que vol_last / vol_first <= threshold.

    Args:
        avg_volumes: Volumen promedio por contraccion en orden cronologico.
        threshold: Ratio maximo permitido.

    Returns:
        Tupla (passes, method_metrics).
    """
    if len(avg_volumes) < 2:
        return False, {"error": "insufficient_contractions"}

    vol_first = avg_volumes[0]
    vol_last = avg_volumes[-1]
    ratio = vol_last / vol_first if vol_first > 0 else float("inf")

    return ratio <= threshold, {"ratio_observed": ratio, "threshold": threshold}


def verify_volume_contraction(
    sequence: DecreasingSequence,
    ohlc: pd.DataFrame,
    method: Literal["per_contraction", "trend", "ratio"] = "per_contraction",
    volume_column: str = "volume",
    tolerance: float = 0.1,
    ratio_threshold: float = 0.8,
    min_r_squared: float = 0.5,
) -> VolumeContractionResult:
    """Verifica si el volumen se contrae a lo largo de una secuencia VCP candidata.

    Para cada contraccion de la secuencia, calcula el volumen promedio en el
    rango [high_date, low_date], y luego evalua si la serie de volumenes
    promedio es decreciente segun el metodo configurado.

    Args:
        sequence: DecreasingSequence devuelta por detect_decreasing_sequence.
        ohlc: DataFrame con la columna de volumen y DatetimeIndex.
        method: "per_contraction", "trend" o "ratio".
        volume_column: Columna a usar como volumen ("volume", "transactions", etc.).
        tolerance: Margen para method="per_contraction".
        ratio_threshold: Umbral para method="ratio".
        min_r_squared: R2 minimo para method="trend".

    Returns:
        VolumeContractionResult con passes, metricas y datos del calculo.

    Raises:
        ValueError: Si method es invalido o la columna no existe.
    """
    if method not in _VALID_METHODS:
        raise ValueError(
            f"Invalid method '{method}'. Must be one of {sorted(_VALID_METHODS)}"
        )

    if volume_column not in ohlc.columns:
        raise ValueError(
            f"Column '{volume_column}' not found in ohlc. "
            f"Available: {sorted(ohlc.columns.tolist())}"
        )

    start_date = sequence.contractions[0].high_swing.date
    end_date = sequence.contractions[-1].low_swing.date

    if start_date not in ohlc.index:
        raise ValueError(f"start_date {start_date.date()} not found in ohlc.index")
    if end_date not in ohlc.index:
        raise ValueError(f"end_date {end_date.date()} not found in ohlc.index")

    avg_volumes = _avg_volume_per_contraction(sequence, ohlc, volume_column)

    if method == "per_contraction":
        passes, metrics = _check_per_contraction(avg_volumes, tolerance)
    elif method == "trend":
        passes, metrics = _check_volume_trend(avg_volumes, min_r_squared)
    else:
        passes, metrics = _check_volume_ratio(avg_volumes, ratio_threshold)

    logger.debug(
        "Volume contraction check (%s, col=%s): passes=%s, avg_vols=%s",
        method,
        volume_column,
        passes,
        [f"{v:.0f}" for v in avg_volumes],
    )
    return VolumeContractionResult(
        passes=passes,
        method=method,
        volume_column=volume_column,
        avg_volumes=avg_volumes,
        start_date=start_date,
        end_date=end_date,
        method_metrics=metrics,
    )


def verify_volume_contraction_batch(
    sequences: dict[pd.Timestamp, DecreasingSequence | None],
    ohlc: pd.DataFrame,
    method: Literal["per_contraction", "trend", "ratio"] = "per_contraction",
    volume_column: str = "volume",
    tolerance: float = 0.1,
    ratio_threshold: float = 0.8,
    min_r_squared: float = 0.5,
) -> dict[pd.Timestamp, VolumeContractionResult | None]:
    """Aplica verify_volume_contraction a un batch de secuencias.

    Args:
        sequences: Dict {evaluation_date: DecreasingSequence | None}.
        ohlc: DataFrame con la columna de volumen.
        method: Metodo de evaluacion.
        volume_column: Columna a usar como volumen.
        tolerance: Tolerancia para per_contraction.
        ratio_threshold: Umbral para ratio.
        min_r_squared: R2 minimo para trend.

    Returns:
        Dict ordenado {evaluation_date: VolumeContractionResult | None}.
    """
    results: dict[pd.Timestamp, VolumeContractionResult | None] = {}
    for dt, seq in sequences.items():
        if seq is None:
            results[dt] = None
            continue
        try:
            results[dt] = verify_volume_contraction(
                sequence=seq,
                ohlc=ohlc,
                method=method,
                volume_column=volume_column,
                tolerance=tolerance,
                ratio_threshold=ratio_threshold,
                min_r_squared=min_r_squared,
            )
        except ValueError:
            logger.warning(
                "Skipping volume contraction for %s: missing data", dt.date()
            )
            results[dt] = None

    n_evaluated = sum(1 for v in results.values() if v is not None)
    n_passed = sum(1 for v in results.values() if v is not None and v.passes)
    logger.debug(
        "Volume contraction batch: %d evaluated, %d passed (%.1f%%)",
        n_evaluated,
        n_passed,
        100 * n_passed / max(n_evaluated, 1),
    )
    return results
