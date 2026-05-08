"""Tests para Paso 2: Calculo de contracciones."""

from __future__ import annotations

import pandas as pd
import pytest

from models.configs import ATRZigZagConfig
from models.enums import SwingType
from models.types import SwingPoint
from vcp_detection.heuristic.contractions import (
    compute_contractions,
    contractions_to_dataframe,
)
from vcp_detection.heuristic.swing_detector import ATRZigZagDetector


class TestComputeContractions:
    """Tests para compute_contractions."""

    def test_computes_from_swings(self, synthetic_vcp_ohlc: pd.DataFrame) -> None:
        """Debe calcular contracciones a partir de swings detectados."""
        detector = ATRZigZagDetector(ATRZigZagConfig(atr_length=14, atr_mult=2.0))
        swings = detector.detect(synthetic_vcp_ohlc)
        contractions = compute_contractions(swings, synthetic_vcp_ohlc)

        assert len(contractions) > 0
        for c in contractions:
            assert c.high_swing.type == SwingType.HIGH
            assert c.low_swing.type == SwingType.LOW
            assert 0 < c.depth_pct < 1
            assert c.depth_abs > 0
            assert c.duration_bars > 0

    def test_depth_atr_computed_with_ohlc(self, synthetic_vcp_ohlc: pd.DataFrame) -> None:
        """depth_atr debe computarse cuando se provee ohlc."""
        detector = ATRZigZagDetector(ATRZigZagConfig(atr_length=14, atr_mult=2.0))
        swings = detector.detect(synthetic_vcp_ohlc)
        contractions = compute_contractions(swings, synthetic_vcp_ohlc)

        has_depth_atr = [c for c in contractions if c.depth_atr is not None]
        assert len(has_depth_atr) > 0
        for c in has_depth_atr:
            assert c.depth_atr > 0

    def test_depth_atr_none_without_ohlc(self) -> None:
        """depth_atr debe ser None cuando no se provee ohlc."""
        dates = pd.bdate_range("2023-01-01", periods=3)
        swings = [
            SwingPoint(date=dates[0], price=100.0, type=SwingType.HIGH, confirmed_at=dates[1]),
            SwingPoint(date=dates[1], price=85.0, type=SwingType.LOW, confirmed_at=dates[2]),
        ]
        contractions = compute_contractions(swings)
        assert len(contractions) == 1
        assert contractions[0].depth_atr is None

    def test_depth_pct_is_correct(self) -> None:
        """depth_pct debe ser (high - low) / high."""
        dates = pd.bdate_range("2023-01-01", periods=3)
        swings = [
            SwingPoint(
                date=dates[0], price=100.0, type=SwingType.HIGH,
                confirmed_at=dates[1],
            ),
            SwingPoint(
                date=dates[1], price=85.0, type=SwingType.LOW,
                confirmed_at=dates[2],
            ),
        ]
        contractions = compute_contractions(swings)
        assert len(contractions) == 1
        assert contractions[0].depth_pct == pytest.approx(0.15)
        assert contractions[0].depth_abs == pytest.approx(15.0)

    def test_min_depth_filter(self) -> None:
        """min_depth_pct debe filtrar contracciones triviales."""
        dates = pd.bdate_range("2023-01-01", periods=5)
        swings = [
            SwingPoint(date=dates[0], price=100.0, type=SwingType.HIGH, confirmed_at=dates[1]),
            SwingPoint(date=dates[1], price=99.0, type=SwingType.LOW, confirmed_at=dates[2]),
            SwingPoint(date=dates[2], price=101.0, type=SwingType.HIGH, confirmed_at=dates[3]),
            SwingPoint(date=dates[3], price=85.0, type=SwingType.LOW, confirmed_at=dates[4]),
        ]
        # Sin filtro: 2 contracciones (1% y ~15.8%)
        all_contractions = compute_contractions(swings)
        assert len(all_contractions) == 2

        # Con filtro 5%: solo la contraccion grande
        filtered = compute_contractions(swings, min_depth_pct=0.05)
        assert len(filtered) == 1
        assert filtered[0].depth_pct > 0.05

    def test_empty_swings_returns_empty(self) -> None:
        """Lista vacia o con un solo swing debe retornar lista vacia."""
        assert compute_contractions([]) == []

    def test_unordered_swings_raises(self) -> None:
        """Swings desordenados cronologicamente deben lanzar ValueError."""
        dates = pd.bdate_range("2023-01-01", periods=2)
        swings = [
            SwingPoint(date=dates[1], price=100.0, type=SwingType.HIGH, confirmed_at=dates[1]),
            SwingPoint(date=dates[0], price=90.0, type=SwingType.LOW, confirmed_at=dates[0]),
        ]
        with pytest.raises(ValueError, match="chronological"):
            compute_contractions(swings)


class TestContractionsToDataframe:
    """Tests para contractions_to_dataframe."""

    def test_empty_list(self) -> None:
        """Lista vacia debe producir DataFrame vacio con columnas correctas."""
        df = contractions_to_dataframe([])
        assert len(df) == 0
        assert "depth_pct" in df.columns

    def test_produces_dataframe(self, synthetic_vcp_ohlc: pd.DataFrame) -> None:
        """Debe producir un DataFrame con las columnas esperadas."""
        detector = ATRZigZagDetector()
        swings = detector.detect(synthetic_vcp_ohlc)
        contractions = compute_contractions(swings, synthetic_vcp_ohlc)
        df = contractions_to_dataframe(contractions)

        assert len(df) == len(contractions)
        assert "high_date" in df.columns
        assert "depth_pct" in df.columns
