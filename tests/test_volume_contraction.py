"""Tests para Paso 5: Verificacion de contraccion de volumen."""

from __future__ import annotations

import pandas as pd
import pytest

from models.configs import ATRZigZagConfig
from models.enums import SwingType
from models.types import Contraction, DecreasingSequence, SwingPoint
from vcp_detection.heuristic.contractions import compute_contractions
from vcp_detection.heuristic.decreasing_sequence import detect_decreasing_sequence
from vcp_detection.heuristic.swing_detector import ATRZigZagDetector
from vcp_detection.heuristic.volume_contraction import (
    verify_volume_contraction,
    verify_volume_contraction_batch,
)


def _make_contraction(
    high_date: str,
    low_date: str,
    high_price: float,
    low_price: float,
) -> Contraction:
    """Helper para crear contracciones de test."""
    hd = pd.Timestamp(high_date)
    ld = pd.Timestamp(low_date)
    return Contraction(
        high_swing=SwingPoint(date=hd, price=high_price, type=SwingType.HIGH, confirmed_at=ld),
        low_swing=SwingPoint(date=ld, price=low_price, type=SwingType.LOW, confirmed_at=ld),
        depth_pct=(high_price - low_price) / high_price,
        depth_abs=high_price - low_price,
        duration_bars=10,
        confirmed_at=ld,
    )


def _make_sequence_and_ohlc() -> tuple[DecreasingSequence, pd.DataFrame]:
    """Crea una secuencia y OHLC sinteticos con volumen decreciente conocido."""
    dates = pd.bdate_range("2023-01-02", periods=60)
    close = [50.0] * 60
    high = [51.0] * 60
    low = [49.0] * 60
    volume = [1_000_000.0] * 60

    volume[5:15] = [1_200_000] * 10
    volume[25:35] = [800_000] * 10
    volume[45:55] = [500_000] * 10

    ohlc = pd.DataFrame(
        {"open": close, "high": high, "low": low, "close": close, "volume": volume},
        index=dates,
    )

    contractions = [
        _make_contraction(
            str(dates[5].date()), str(dates[14].date()), 55.0, 48.0
        ),
        _make_contraction(
            str(dates[25].date()), str(dates[34].date()), 54.0, 49.0
        ),
        _make_contraction(
            str(dates[45].date()), str(dates[54].date()), 53.0, 50.0
        ),
    ]

    seq = DecreasingSequence(
        contractions=contractions,
        evaluation_date=dates[59],
        method="tolerance",
        method_metrics={},
        n_contractions=3,
        depths_pct=[c.depth_pct for c in contractions],
    )
    return seq, ohlc


class TestVerifyVolumeContraction:
    """Tests para verify_volume_contraction."""

    def test_ratio_method_passes_with_decreasing_volume(self) -> None:
        """Metodo ratio debe pasar cuando el volumen se contrae."""
        seq, ohlc = _make_sequence_and_ohlc()
        result = verify_volume_contraction(
            seq, ohlc, method="ratio", ratio_threshold=0.95,
        )
        assert result.passes is True
        assert result.method == "ratio"
        assert result.method_metrics["ratio_observed"] < 0.95

    def test_ratio_method_fails_with_high_threshold(self) -> None:
        """Metodo ratio debe fallar con un threshold muy bajo."""
        seq, ohlc = _make_sequence_and_ohlc()
        result = verify_volume_contraction(
            seq, ohlc, method="ratio", ratio_threshold=0.1,
        )
        assert result.passes is False

    def test_per_contraction_method(self) -> None:
        """Metodo per_contraction verifica cada par consecutivo."""
        seq, ohlc = _make_sequence_and_ohlc()
        result = verify_volume_contraction(
            seq, ohlc, method="per_contraction", tolerance=0.1,
        )
        assert result.passes is True
        assert result.method == "per_contraction"

    def test_trend_method_with_decreasing_volume(self) -> None:
        """Metodo trend debe detectar pendiente negativa en volumen decreciente."""
        seq, ohlc = _make_sequence_and_ohlc()
        result = verify_volume_contraction(
            seq, ohlc, method="trend", min_r_squared=0.5,
        )
        assert result.passes is True
        assert result.method_metrics["slope"] < 0

    def test_trend_method_needs_three_contractions(self) -> None:
        """Metodo trend con solo 2 contracciones debe fallar."""
        seq, ohlc = _make_sequence_and_ohlc()
        seq_2 = DecreasingSequence(
            contractions=seq.contractions[:2],
            evaluation_date=seq.evaluation_date,
            method="tolerance",
            method_metrics={},
            n_contractions=2,
            depths_pct=seq.depths_pct[:2],
        )
        result = verify_volume_contraction(
            seq_2, ohlc, method="trend", min_r_squared=0.5,
        )
        assert result.passes is False

    def test_invalid_method_raises(self) -> None:
        """Metodo invalido debe lanzar ValueError."""
        seq, ohlc = _make_sequence_and_ohlc()
        with pytest.raises(ValueError, match="Invalid method"):
            verify_volume_contraction(seq, ohlc, method="bad")  # type: ignore

    def test_missing_volume_column_raises(self) -> None:
        """Columna de volumen inexistente debe lanzar ValueError."""
        seq, ohlc = _make_sequence_and_ohlc()
        with pytest.raises(ValueError, match="not found in ohlc"):
            verify_volume_contraction(seq, ohlc, volume_column="transactions")

    def test_avg_volumes_are_populated(self) -> None:
        """El resultado debe contener los volumenes promedio por contraccion."""
        seq, ohlc = _make_sequence_and_ohlc()
        result = verify_volume_contraction(seq, ohlc, method="ratio")
        assert len(result.avg_volumes) == 3
        assert all(v > 0 for v in result.avg_volumes)

    def test_integration_with_pipeline(self, synthetic_vcp_ohlc: pd.DataFrame) -> None:
        """Debe funcionar con datos del pipeline real (swings -> contracciones -> secuencia)."""
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
            result = verify_volume_contraction(
                seq, synthetic_vcp_ohlc, method="ratio", ratio_threshold=0.99,
            )
            assert result.method == "ratio"
            assert len(result.avg_volumes) == seq.n_contractions


class TestVerifyVolumeContractionBatch:
    """Tests para verify_volume_contraction_batch."""

    def test_batch_handles_none_sequences(self) -> None:
        """Batch debe retornar None para secuencias None."""
        seq, ohlc = _make_sequence_and_ohlc()
        sequences = {
            pd.Timestamp("2023-02-01"): None,
            seq.evaluation_date: seq,
        }
        results = verify_volume_contraction_batch(sequences, ohlc, method="ratio")
        assert results[pd.Timestamp("2023-02-01")] is None
        assert results[seq.evaluation_date] is not None
