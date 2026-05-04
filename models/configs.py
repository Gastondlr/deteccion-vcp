"""Dataclasses de configuracion para los detectores de swing points."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ATRZigZagConfig:
    """Configuracion del detector de swings ATR ZigZag.

    Attributes:
        atr_length: Periodo del ATR para calcular el threshold de reversion.
            Default 14 (estandar de la industria, ~3 semanas de volatilidad).
        atr_mult: Multiplo de ATR que el precio debe revertir desde un extremo
            para confirmar un nuevo swing. Default 2.0.
        use_close_only: Si True, usa solo el precio de cierre para detectar
            extremos. Si False, usa high/low.
    """

    atr_length: int = 14
    atr_mult: float = 2.0
    use_close_only: bool = False


@dataclass
class ScipyPeaksConfig:
    """Configuracion del detector de swings basado en scipy.signal.find_peaks.

    Attributes:
        smoothing_window: Ventana de SMA para suavizar antes de detectar picos.
        prominence: Prominence minima del pico (unidades de precio). Si None,
            se autoescala con ATR.
        prominence_atr_mult: Multiplo de ATR(14) para autoescalar prominence
            cuando prominence es None.
        min_distance_bars: Distancia minima entre picos consecutivos en bars.
        stability_margin: Bars desde el final a excluir en modo causal. Si None,
            usa min_distance_bars.
        causal: Si True, usa SMA no centrada y descarta swings inestables del
            final. Elimina look-ahead para uso en backtesting.
    """

    smoothing_window: int = 3
    prominence: float | None = None
    prominence_atr_mult: float = 1.0
    min_distance_bars: int = 5
    stability_margin: int | None = None
    causal: bool = False
