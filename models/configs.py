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
