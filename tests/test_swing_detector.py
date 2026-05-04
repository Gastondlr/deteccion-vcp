"""Tests para Paso 1: Deteccion de swing points."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from models.configs import ATRZigZagConfig, ScipyPeaksConfig
from models.enums import SwingType
from vcp_detection.heuristic.swing_detector import ATRZigZagDetector, ScipyPeaksDetector


class TestATRZigZagDetector:
    """Tests para el detector ATR ZigZag."""

    def test_detects_swings_on_synthetic_data(self, synthetic_vcp_ohlc: pd.DataFrame) -> None:
        """Debe detectar swings alternando HIGH/LOW."""
        detector = ATRZigZagDetector(ATRZigZagConfig(atr_length=14, atr_mult=2.0))
        swings = detector.detect(synthetic_vcp_ohlc)

        assert len(swings) > 0
        for i in range(1, len(swings)):
            assert swings[i].type != swings[i - 1].type, (
                f"Swings {i-1} and {i} have same type {swings[i].type}"
            )

    def test_swing_dates_are_chronological(self, synthetic_vcp_ohlc: pd.DataFrame) -> None:
        """Las fechas de los swings deben ser cronologicas."""
        detector = ATRZigZagDetector()
        swings = detector.detect(synthetic_vcp_ohlc)

        for i in range(1, len(swings)):
            assert swings[i].date >= swings[i - 1].date

    def test_confirmed_at_is_after_date(self, synthetic_vcp_ohlc: pd.DataFrame) -> None:
        """confirmed_at debe ser >= date (confirmacion causal)."""
        detector = ATRZigZagDetector()
        swings = detector.detect(synthetic_vcp_ohlc)

        for sw in swings:
            assert sw.confirmed_at >= sw.date

    def test_high_prices_use_high_column(self, synthetic_vcp_ohlc: pd.DataFrame) -> None:
        """Swings HIGH deben usar precios del high column."""
        detector = ATRZigZagDetector(ATRZigZagConfig(use_close_only=False))
        swings = detector.detect(synthetic_vcp_ohlc)

        for sw in swings:
            if sw.type == SwingType.HIGH:
                date_high = float(synthetic_vcp_ohlc.loc[sw.date, "high"])
                assert sw.price == pytest.approx(date_high)

    def test_empty_dataframe_raises(self) -> None:
        """DataFrame vacio debe lanzar ValueError."""
        detector = ATRZigZagDetector()
        empty = pd.DataFrame(
            columns=["open", "high", "low", "close"],
            index=pd.DatetimeIndex([]),
        )
        with pytest.raises(ValueError, match="empty"):
            detector.detect(empty)

    def test_missing_columns_raises(self) -> None:
        """DataFrame sin columnas requeridas debe lanzar ValueError."""
        detector = ATRZigZagDetector()
        df = pd.DataFrame({"close": [1, 2, 3]}, index=pd.bdate_range("2023-01-01", periods=3))
        with pytest.raises(ValueError, match="missing required columns"):
            detector.detect(df)

    def test_short_series_returns_empty(self) -> None:
        """Serie mas corta que atr_length debe retornar lista vacia."""
        detector = ATRZigZagDetector(ATRZigZagConfig(atr_length=14))
        dates = pd.bdate_range("2023-01-01", periods=10)
        df = pd.DataFrame(
            {
                "open": np.random.uniform(10, 11, 10),
                "high": np.random.uniform(11, 12, 10),
                "low": np.random.uniform(9, 10, 10),
                "close": np.random.uniform(10, 11, 10),
            },
            index=dates,
        )
        swings = detector.detect(df)
        assert len(swings) == 0


class TestScipyPeaksDetector:
    """Tests para el detector basado en scipy."""

    def test_detects_swings(self, synthetic_vcp_ohlc: pd.DataFrame) -> None:
        """Debe detectar swings en datos sinteticos."""
        detector = ScipyPeaksDetector(ScipyPeaksConfig(min_distance_bars=10))
        swings = detector.detect(synthetic_vcp_ohlc)
        assert len(swings) > 0

    def test_alternation(self, synthetic_vcp_ohlc: pd.DataFrame) -> None:
        """Swings deben alternar HIGH/LOW."""
        detector = ScipyPeaksDetector()
        swings = detector.detect(synthetic_vcp_ohlc)

        for i in range(1, len(swings)):
            assert swings[i].type != swings[i - 1].type
