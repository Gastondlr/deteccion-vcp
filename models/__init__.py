"""Dataclasses, enums y configuraciones para el detector de VCP."""

from models.configs import ATRZigZagConfig, ScipyPeaksConfig
from models.enums import SwingType
from models.types import (
    ATRCompressionResult,
    Contraction,
    DecreasingSequence,
    PivotInfo,
    SwingPoint,
    VCPSignal,
    VolumeContractionResult,
)

__all__ = [
    "ATRCompressionResult",
    "ATRZigZagConfig",
    "Contraction",
    "DecreasingSequence",
    "PivotInfo",
    "ScipyPeaksConfig",
    "SwingPoint",
    "SwingType",
    "VCPSignal",
    "VolumeContractionResult",
]
