"""Tests de integracion para el pipeline completo (Pasos 1-6)."""

from __future__ import annotations

import pandas as pd
import pytest

from models.configs import ATRZigZagConfig
from vcp_detection.heuristic.pivot_breakout import run_full_vcp_pipeline
from vcp_detection.heuristic.swing_detector import ATRZigZagDetector


class TestRunFullVCPPipeline:
    """Tests de integracion para run_full_vcp_pipeline."""

    def test_pipeline_runs_without_errors(self, synthetic_vcp_ohlc: pd.DataFrame) -> None:
        """El pipeline debe ejecutarse sin errores sobre datos sinteticos."""
        detector = ATRZigZagDetector(ATRZigZagConfig(atr_length=14, atr_mult=2.0))
        results = run_full_vcp_pipeline(
            ohlc=synthetic_vcp_ohlc,
            swing_detector=detector,
            sequence_params={
                "method": "tolerance",
                "min_contractions": 2,
                "max_contractions": 6,
                "lookback_bars": 126,
                "tolerance": 0.10,
            },
            compression_params={
                "method": "ratio",
                "atr_period": 14,
                "ratio_threshold": 0.95,
            },
            breakout_params={
                "volume_method": "ratio",
                "volume_ratio_threshold": 1.5,
                "volume_lookback_days": 50,
                "require_volume_confirmation": False,
            },
        )
        assert len(results) == len(synthetic_vcp_ohlc)
        assert all(isinstance(k, pd.Timestamp) for k in results.keys())

    def test_pipeline_with_volume_contraction(self, synthetic_vcp_ohlc: pd.DataFrame) -> None:
        """El pipeline debe funcionar con verificacion de contraccion de volumen."""
        detector = ATRZigZagDetector(ATRZigZagConfig(atr_length=14, atr_mult=2.0))
        results = run_full_vcp_pipeline(
            ohlc=synthetic_vcp_ohlc,
            swing_detector=detector,
            sequence_params={
                "method": "tolerance",
                "min_contractions": 2,
                "max_contractions": 6,
                "lookback_bars": 126,
                "tolerance": 0.10,
            },
            compression_params={
                "method": "ratio",
                "atr_period": 14,
                "ratio_threshold": 0.95,
            },
            breakout_params={
                "volume_method": "ratio",
                "volume_ratio_threshold": 1.5,
                "volume_lookback_days": 50,
                "require_volume_confirmation": False,
            },
            volume_contraction_params={
                "method": "ratio",
                "volume_column": "volume",
                "ratio_threshold": 0.95,
            },
        )
        assert len(results) == len(synthetic_vcp_ohlc)

    def test_flat_market_produces_few_signals(self, flat_ohlc: pd.DataFrame) -> None:
        """Un mercado lateral no deberia producir muchas senales VCP."""
        detector = ATRZigZagDetector(ATRZigZagConfig(atr_length=14, atr_mult=2.0))
        results = run_full_vcp_pipeline(
            ohlc=flat_ohlc,
            swing_detector=detector,
            sequence_params={
                "method": "tolerance",
                "min_contractions": 2,
                "max_contractions": 6,
                "lookback_bars": 126,
                "tolerance": 0.10,
                "max_depth_pct": 0.25,
                "min_total_reduction": 0.70,
            },
            compression_params={
                "method": "ratio",
                "atr_period": 14,
                "ratio_threshold": 0.85,
            },
            breakout_params={
                "volume_method": "ratio",
                "volume_ratio_threshold": 1.5,
                "volume_lookback_days": 50,
                "require_volume_confirmation": True,
            },
        )
        n_signals = sum(1 for v in results.values() if v is not None)
        total = len(results)
        signal_rate = n_signals / total if total > 0 else 0
        assert signal_rate < 0.1, f"Signal rate {signal_rate:.1%} is too high for flat market"

    def test_signal_has_valid_structure(self, synthetic_vcp_ohlc: pd.DataFrame) -> None:
        """Las senales generadas deben tener la estructura correcta."""
        detector = ATRZigZagDetector(ATRZigZagConfig(atr_length=14, atr_mult=2.0))
        results = run_full_vcp_pipeline(
            ohlc=synthetic_vcp_ohlc,
            swing_detector=detector,
            sequence_params={
                "method": "tolerance",
                "min_contractions": 2,
                "max_contractions": 6,
                "lookback_bars": 200,
                "tolerance": 0.10,
            },
            compression_params={
                "method": "ratio",
                "atr_period": 14,
                "ratio_threshold": 0.99,
            },
            breakout_params={
                "volume_method": "ratio",
                "volume_ratio_threshold": 1.0,
                "volume_lookback_days": 50,
                "require_volume_confirmation": False,
            },
        )
        signals = [v for v in results.values() if v is not None]
        for sig in signals:
            assert sig.entry_price > 0
            assert sig.pivot_price > 0
            assert sig.suggested_stop > 0
            assert sig.suggested_stop < sig.entry_price
            assert 0 < sig.suggested_stop_distance_pct < 1
            assert sig.atr_compression.passes
            assert "n_contractions" in sig.metadata
            assert sig.metadata["n_contractions"] >= 2

    def test_deduplicate_reduces_signals(self, synthetic_vcp_ohlc: pd.DataFrame) -> None:
        """Deduplicacion debe reducir el numero de senales."""
        detector = ATRZigZagDetector(ATRZigZagConfig(atr_length=14, atr_mult=2.0))
        common_params = dict(
            ohlc=synthetic_vcp_ohlc,
            swing_detector=detector,
            sequence_params={
                "method": "tolerance",
                "min_contractions": 2,
                "max_contractions": 6,
                "lookback_bars": 200,
                "tolerance": 0.10,
            },
            compression_params={
                "method": "ratio",
                "atr_period": 14,
                "ratio_threshold": 0.99,
            },
            breakout_params={
                "volume_method": "ratio",
                "volume_ratio_threshold": 1.0,
                "volume_lookback_days": 50,
                "require_volume_confirmation": False,
            },
        )

        results_no_dedup = run_full_vcp_pipeline(**common_params, deduplicate=False)
        results_dedup = run_full_vcp_pipeline(**common_params, deduplicate=True)

        n_no_dedup = sum(1 for v in results_no_dedup.values() if v is not None)
        n_dedup = sum(1 for v in results_dedup.values() if v is not None)

        assert n_dedup <= n_no_dedup
