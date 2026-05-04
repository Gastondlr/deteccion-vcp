"""Enumeraciones para el detector de VCP."""

from __future__ import annotations

from enum import Enum, auto


class SwingType(Enum):
    """Tipo de swing point detectado en una serie de precios.

    HIGH: maximo local (pico).
    LOW: minimo local (valle).
    """

    HIGH = auto()
    LOW = auto()
