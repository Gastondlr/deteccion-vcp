"""Tests para Paso 4: Verificacion de compresion de ATR."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from models.configs import ATRZigZagConfig
from vcp_detection.heuristic.atr_compression import verify_atr_compression, compute_atr
from vcp_detection.heuristic.contractions import compute_contractions
from vcp_detection.heuristic.decreasing_sequence import detect_decreasing_sequence
from vcp_detection.heuristic.swing_detector import ATRZigZagDetector


class TestComputeATR:
    """Tests para el calculo de ATR con Wilder's smoothing."""

    def test_atr_has_correct_length(self, synthetic_vcp_ohlc: pd.DataFrame) -> None:
        """ATR debe tener la misma longitud que el input."""
        atr = compute_atr(synthetic_vcp_ohlc, period=14)
        assert len(atr) == len(synthetic_vcp_ohlc)

    def test_atr_nan_for_initial_period(self, synthetic_vcp_ohlc: pd.DataFrame) -> None:
        """Los primeros 'period' valores deben ser NaN."""
        atr = compute_atr(synthetic_vcp_ohlc, period=14)
        assert atr.iloc[:14].isna().all()
        assert atr.iloc[14:].notna().all()

    def test_atr_is_positive(self, synthetic_vcp_ohlc: pd.DataFrame) -> None:
        """ATR debe ser siempre positivo donde esta definido."""
        atr = compute_atr(synthetic_vcp_ohlc, period=14)
        valid = atr.dropna()
        assert (valid > 0).all()


class TestVerifyATRCompression:
    """Tests para verify_atr_compression."""

    def test_ratio_method_on_synthetic(self, synthetic_vcp_ohlc: pd.DataFrame) -> None:
        """Debe poder evaluar compresion ratio sobre datos sinteticos."""
        detector = ATRZigZagDetector(ATRZigZagConfig(atr_length=14, atr_mult=2.0))
        swings = detector.detect(synthetic_vcp_ohlc)
        contractions = compute_contractions(swings, synthetic_vcp_ohlc)

        seq = detect_decreasing_sequence(
            contractions,
            evaluation_date=synthetic_vcp_ohlc.index[-30],
            method="tolerance",
            tolerance=0.10,
            min_contractions=2,
            lookback_bars=200,
        )

        if seq is not None:
            result = verify_atr_compression(
                seq, synthetic_vcp_ohlc, method="ratio", ratio_threshold=0.95
            )
            assert result.atr_start > 0
            assert result.atr_end > 0
            assert "ratio_observed" in result.method_metrics

    def test_invalid_method_raises(self, synthetic_vcp_ohlc: pd.DataFrame) -> None:
        """Metodo invalido debe lanzar ValueError."""
        detector = ATRZigZagDetector()
        swings = detector.detect(synthetic_vcp_ohlc)
        contractions = compute_contractions(swings, synthetic_vcp_ohlc)

        seq = detect_decreasing_sequence(
            contractions,
            evaluation_date=synthetic_vcp_ohlc.index[-30],
            method="tolerance",
            min_contractions=2,
            lookback_bars=200,
        )
        if seq is not None:
            with pytest.raises(ValueError, match="Invalid method"):
                verify_atr_compression(seq, synthetic_vcp_ohlc, method="bad")  # type: ignore
