"""Detectores heuristicos de VCP y swing points.

Expone las funciones principales del pipeline:
- ATRZigZagDetector: Paso 1 (deteccion de swings).
- compute_contractions: Paso 2 (calculo de contracciones).
- detect_decreasing_sequence: Paso 3 (secuencia decreciente + filtros de calidad).
- verify_atr_compression: Paso 4 (compresion de ATR).
- verify_volume_contraction: Paso 5 (contraccion de volumen).
- identify_pivot / detect_breakout_signal: Paso 6 (pivote + breakout).
- run_full_vcp_pipeline: Orquestador de pasos 1-6.
"""

from vcp_detection.heuristic.atr_compression import (
    compute_atr,
    verify_atr_compression,
    verify_atr_compression_batch,
)
from vcp_detection.heuristic.contractions import (
    compute_contractions,
    contractions_to_dataframe,
)
from vcp_detection.heuristic.decreasing_sequence import (
    detect_decreasing_sequence,
    scan_for_sequences,
)
from vcp_detection.heuristic.pivot_breakout import (
    detect_breakout_signal,
    detect_breakout_signals_batch,
    identify_pivot,
    run_full_vcp_pipeline,
)
from vcp_detection.heuristic.swing_detector import (
    ATRZigZagDetector,
    SwingDetector,
)
from vcp_detection.heuristic.volume_contraction import (
    verify_volume_contraction,
    verify_volume_contraction_batch,
)

__all__ = [
    "ATRZigZagDetector",
    "compute_atr",
    "SwingDetector",
    "compute_contractions",
    "contractions_to_dataframe",
    "detect_breakout_signal",
    "detect_breakout_signals_batch",
    "detect_decreasing_sequence",
    "identify_pivot",
    "run_full_vcp_pipeline",
    "scan_for_sequences",
    "verify_atr_compression",
    "verify_atr_compression_batch",
    "verify_volume_contraction",
    "verify_volume_contraction_batch",
]
