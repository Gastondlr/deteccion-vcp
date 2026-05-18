"""Paso 2: Calculo de contracciones de precio entre swings HIGH->LOW consecutivos.

============================================================================
DESCRIPCION DEL PASO
============================================================================
Una **contraccion** es la caida porcentual desde un swing high hasta el swing
low inmediatamente siguiente. Es la unidad de medida fundamental del patron
VCP de Minervini: el VCP requiere que las ultimas N contracciones sean
monotonicamente decrecientes.

Dado un par (HIGH, LOW) consecutivo:
    depth_pct = (high.price - low.price) / high.price

Por ejemplo, si el high es $100 y el low es $85, la contraccion es 15%.

============================================================================
CALCULO
============================================================================
1. Recorre la lista de swings en orden cronologico.
2. Para cada par (HIGH, LOW) consecutivo donde HIGH precede a LOW, genera
   una Contraction.
3. Los pares (LOW, HIGH) se ignoran (representan subidas, no contracciones).
4. Opcionalmente filtra por profundidad minima (min_depth_pct) para descartar
   contracciones triviales producidas por ruido.

============================================================================
LIBRERIAS UTILIZADAS
============================================================================
- pandas: Para contar bars de trading reales entre fechas (si se provee ohlc).
- Logica pura de Python para el resto (no requiere numpy ni scipy).

============================================================================
VALIDACIONES
============================================================================
- La lista de swings debe estar ordenada cronologicamente.
- Los swings deben alternar HIGH/LOW (no puede haber dos HIGH consecutivos).
- Si low.price >= high.price (anomalia), se loguea warning y se salta el par.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from models.enums import SwingType
from models.types import Contraction, SwingPoint
from vcp_detection.heuristic.atr_compression import compute_atr

logger = logging.getLogger(__name__)


def compute_contractions(
    swings: list[SwingPoint],
    ohlc: pd.DataFrame | None = None,
    min_depth_pct: float = 0.0,
    atr_period: int = 14,
) -> list[Contraction]:
    """Calcula las contracciones HIGH->LOW a partir de una lista de swings.

    Recorre la lista de swings en orden cronologico y, para cada par
    (HIGH, LOW) consecutivo donde el HIGH precede al LOW, genera una
    Contraction. Los pares (LOW, HIGH) se ignoran.

    Args:
        swings: Lista de SwingPoint ordenada cronologicamente, alternando
            tipos HIGH y LOW. Debe ser el output directo de un SwingDetector.
        ohlc: DataFrame OHLC opcional con DatetimeIndex. Si se provee, se usa
            para calcular duration_bars contando bars de trading reales entre
            fechas. Si es None, duration_bars se aproxima con dias calendario.
        min_depth_pct: Profundidad minima (como fraccion, ej: 0.02 = 2%) para
            incluir una contraccion. Contracciones menores se descartan como
            ruido. Default 0.0 (aceptar todas).
        atr_period: Periodo para calcular ATR (Wilder's smoothing). Se usa
            para computar depth_atr = depth_abs / ATR en cada contraccion.
            Solo se computa si ohlc es proporcionado. Default 14.

    Returns:
        Lista de Contraction ordenada cronologicamente por high_swing.date.
        Lista vacia si no hay pares HIGH->LOW validos.

    Raises:
        ValueError: Si la lista de swings no esta ordenada cronologicamente
            o si contiene swings consecutivos del mismo tipo.
    """
    if len(swings) <= 1:
        return []

    _validate_swing_sequence(swings)

    atr_series: pd.Series | None = None
    if ohlc is not None:
        atr_series = compute_atr(ohlc, period=atr_period)

    contractions: list[Contraction] = []
    for i in range(len(swings) - 1):
        high_sw = swings[i]
        low_sw = swings[i + 1]

        if high_sw.type != SwingType.HIGH or low_sw.type != SwingType.LOW:
            continue

        if not high_sw.metadata.get("confirmed", True):
            continue
        if not low_sw.metadata.get("confirmed", True):
            continue

        if low_sw.price >= high_sw.price:
            logger.warning(
                "Swing LOW price (%.4f) >= HIGH price (%.4f) at %s -> %s, skipping",
                low_sw.price,
                high_sw.price,
                high_sw.date.date(),
                low_sw.date.date(),
            )
            continue

        depth_abs = high_sw.price - low_sw.price
        depth_pct = depth_abs / high_sw.price

        if depth_pct < min_depth_pct:
            continue

        if ohlc is not None:
            mask = (ohlc.index >= high_sw.date) & (ohlc.index <= low_sw.date)
            duration_bars = int(mask.sum())
        else:
            duration_bars = (low_sw.date - high_sw.date).days

        confirmed_at = max(high_sw.confirmed_at, low_sw.confirmed_at)

        depth_atr: float | None = None
        if atr_series is not None and high_sw.date in atr_series.index:
            atr_val = float(atr_series.loc[high_sw.date])
            if not np.isnan(atr_val) and atr_val > 0:
                depth_atr = depth_abs / atr_val

        contractions.append(
            Contraction(
                high_swing=high_sw,
                low_swing=low_sw,
                depth_pct=depth_pct,
                depth_abs=depth_abs,
                duration_bars=duration_bars,
                confirmed_at=confirmed_at,
                depth_atr=depth_atr,
            )
        )

    logger.debug(
        "Computed %d contractions from %d swings (min_depth_pct=%.4f)",
        len(contractions),
        len(swings),
        min_depth_pct,
    )
    return contractions


def make_early_contractions(contractions: list[Contraction]) -> list[Contraction]:
    """Crea contracciones visibles desde que el HIGH se confirma (sin esperar al LOW).

    En el modo normal, confirmed_at = max(high.confirmed_at, low.confirmed_at).
    Aquí usamos confirmed_at = high.confirmed_at, permitiendo que la contracción
    sea "visible" antes — el LOW ya ocurrió en esa fecha (D_L <= T_H) pero no
    estaba confirmado aún. Esto permite detectar el patrón VCP antes del breakout
    y entrar exactamente cuando el precio rompe el pivot.
    """
    return [
        Contraction(
            high_swing=c.high_swing,
            low_swing=c.low_swing,
            depth_pct=c.depth_pct,
            depth_abs=c.depth_abs,
            duration_bars=c.duration_bars,
            confirmed_at=c.high_swing.confirmed_at,
            depth_atr=c.depth_atr,
        )
        for c in contractions
    ]


def contractions_to_dataframe(contractions: list[Contraction]) -> pd.DataFrame:
    """Convierte una lista de Contraction a DataFrame para analisis tabular.

    Args:
        contractions: Lista de Contraction.

    Returns:
        DataFrame con columnas: high_date, high_price, low_date, low_price,
        depth_pct, depth_abs, duration_bars, confirmed_at.
    """
    if not contractions:
        return pd.DataFrame(
            columns=[
                "high_date",
                "high_price",
                "low_date",
                "low_price",
                "depth_pct",
                "depth_abs",
                "depth_atr",
                "duration_bars",
                "confirmed_at",
            ]
        )

    rows = []
    for c in contractions:
        rows.append(
            {
                "high_date": c.high_swing.date,
                "high_price": c.high_swing.price,
                "low_date": c.low_swing.date,
                "low_price": c.low_swing.price,
                "depth_pct": c.depth_pct,
                "depth_abs": c.depth_abs,
                "depth_atr": c.depth_atr,
                "duration_bars": c.duration_bars,
                "confirmed_at": c.confirmed_at,
            }
        )
    return pd.DataFrame(rows)


def _validate_swing_sequence(swings: list[SwingPoint]) -> None:
    """Valida orden cronologico y alternancia de tipos en la lista de swings.

    Args:
        swings: Lista de SwingPoint a validar.

    Raises:
        ValueError: Si los swings no estan ordenados o hay tipos consecutivos repetidos.
    """
    for i in range(1, len(swings)):
        if swings[i].date < swings[i - 1].date:
            raise ValueError(
                f"Swings not in chronological order: swing {i - 1} at "
                f"{swings[i - 1].date.date()} comes before swing {i} at "
                f"{swings[i].date.date()}"
            )
        if swings[i].type == swings[i - 1].type:
            raise ValueError(
                f"Consecutive swings have same type {swings[i].type.name}: "
                f"swing {i - 1} at {swings[i - 1].date.date()} and "
                f"swing {i} at {swings[i].date.date()}"
            )
