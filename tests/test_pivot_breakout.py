"""Tests unitarios para Paso 6: identify_pivot y detect_breakout_signal."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from models.configs import ATRZigZagConfig
from models.enums import SwingType
from models.types import (
    ATRCompressionResult,
    Contraction,
    DecreasingSequence,
    SwingPoint,
)
from vcp_detection.heuristic.pivot_breakout import (
    detect_breakout_signal,
    identify_pivot,
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


def _make_sequence() -> DecreasingSequence:
    """Crea una secuencia decreciente de test."""
    contractions = [
        _make_contraction("2023-01-10", "2023-01-20", 100, 85),
        _make_contraction("2023-02-10", "2023-02-20", 100, 90),
        _make_contraction("2023-03-10", "2023-03-20", 100, 95),
    ]
    return DecreasingSequence(
        contractions=contractions,
        evaluation_date=pd.Timestamp("2023-04-01"),
        method="tolerance",
        method_metrics={},
        n_contractions=3,
        depths_pct=[c.depth_pct for c in contractions],
    )


def _make_passing_atr_result() -> ATRCompressionResult:
    """Crea un ATRCompressionResult que pasa."""
    return ATRCompressionResult(
        passes=True,
        method="ratio",
        atr_start=2.0,
        atr_end=1.0,
        start_date=pd.Timestamp("2023-01-10"),
        end_date=pd.Timestamp("2023-03-20"),
        atr_period=14,
        method_metrics={"ratio_observed": 0.5},
    )


def _make_ohlc_around_pivot(pivot_price: float, breakout: bool) -> pd.DataFrame:
    """Genera OHLC con o sin breakout sobre el pivot."""
    dates = pd.bdate_range("2023-01-02", periods=100)
    close = np.full(100, pivot_price - 2.0)
    if breakout:
        close[-1] = pivot_price + 1.0
    else:
        close[-1] = pivot_price - 1.0

    high = close + 0.5
    low = close - 0.5
    volume = np.full(100, 1_000_000.0)
    volume[-1] = 2_000_000.0

    return pd.DataFrame(
        {"open": close, "high": high, "low": low, "close": close, "volume": volume},
        index=dates,
    )


class TestIdentifyPivot:
    """Tests para identify_pivot."""

    def test_pivot_is_last_contraction_high(self) -> None:
        """El pivote debe ser el high de la ultima contraccion."""
        seq = _make_sequence()
        pivot = identify_pivot(seq)
        assert pivot.price == 100.0
        assert pivot.date == pd.Timestamp("2023-03-10")

    def test_pivot_last_low(self) -> None:
        """last_low_price debe ser el low de la ultima contraccion."""
        seq = _make_sequence()
        pivot = identify_pivot(seq)
        assert pivot.last_low_price == 95.0
        assert pivot.last_low_date == pd.Timestamp("2023-03-20")

    def test_pivot_stores_sequence_reference(self) -> None:
        """El pivot debe mantener referencia a la secuencia."""
        seq = _make_sequence()
        pivot = identify_pivot(seq)
        assert pivot.sequence is seq

    def test_empty_contractions_raises(self) -> None:
        """Secuencia con contracciones vacias debe lanzar ValueError."""
        seq = DecreasingSequence(
            contractions=[],
            evaluation_date=pd.Timestamp("2023-04-01"),
            method="tolerance",
            method_metrics={},
            n_contractions=0,
            depths_pct=[],
        )
        with pytest.raises(ValueError, match="empty contractions"):
            identify_pivot(seq)


class TestDetectBreakoutSignal:
    """Tests para detect_breakout_signal."""

    def test_breakout_generates_signal(self) -> None:
        """Close > pivot con volumen debe generar senal."""
        seq = _make_sequence()
        atr_result = _make_passing_atr_result()
        ohlc = _make_ohlc_around_pivot(100.0, breakout=True)
        eval_date = ohlc.index[-1]

        signal = detect_breakout_signal(
            seq, atr_result, ohlc, eval_date,
            require_volume_confirmation=False,
        )
        assert signal is not None
        assert signal.entry_price > 100.0
        assert signal.pivot_price == 100.0
        assert signal.suggested_stop == 95.0

    def test_no_breakout_returns_none(self) -> None:
        """Close < pivot debe retornar None."""
        seq = _make_sequence()
        atr_result = _make_passing_atr_result()
        ohlc = _make_ohlc_around_pivot(100.0, breakout=False)
        eval_date = ohlc.index[-1]

        signal = detect_breakout_signal(
            seq, atr_result, ohlc, eval_date,
            require_volume_confirmation=False,
        )
        assert signal is None

    def test_failing_atr_returns_none(self) -> None:
        """ATR compression que no pasa debe retornar None."""
        seq = _make_sequence()
        atr_result = ATRCompressionResult(
            passes=False, method="ratio", atr_start=1.0, atr_end=2.0,
            start_date=pd.Timestamp("2023-01-10"),
            end_date=pd.Timestamp("2023-03-20"),
            atr_period=14, method_metrics={},
        )
        ohlc = _make_ohlc_around_pivot(100.0, breakout=True)
        eval_date = ohlc.index[-1]

        signal = detect_breakout_signal(
            seq, atr_result, ohlc, eval_date,
            require_volume_confirmation=False,
        )
        assert signal is None

    def test_volume_confirmation_filters(self) -> None:
        """Breakout sin volumen suficiente debe retornar None con require_volume=True."""
        seq = _make_sequence()
        atr_result = _make_passing_atr_result()
        ohlc = _make_ohlc_around_pivot(100.0, breakout=True)
        ohlc.loc[ohlc.index[-1], "volume"] = 100.0
        eval_date = ohlc.index[-1]

        signal = detect_breakout_signal(
            seq, atr_result, ohlc, eval_date,
            require_volume_confirmation=True,
            volume_ratio_threshold=1.5,
        )
        assert signal is None

    def test_signal_metadata(self) -> None:
        """La senal debe incluir metadata con n_contractions."""
        seq = _make_sequence()
        atr_result = _make_passing_atr_result()
        ohlc = _make_ohlc_around_pivot(100.0, breakout=True)
        eval_date = ohlc.index[-1]

        signal = detect_breakout_signal(
            seq, atr_result, ohlc, eval_date,
            require_volume_confirmation=False,
        )
        assert signal is not None
        assert signal.metadata["n_contractions"] == 3
        assert len(signal.metadata["depths_pct"]) == 3

    def test_invalid_volume_method_raises(self) -> None:
        """Metodo de volumen invalido debe lanzar ValueError."""
        seq = _make_sequence()
        atr_result = _make_passing_atr_result()
        ohlc = _make_ohlc_around_pivot(100.0, breakout=True)
        eval_date = ohlc.index[-1]

        with pytest.raises(ValueError, match="Invalid volume_method"):
            detect_breakout_signal(
                seq, atr_result, ohlc, eval_date,
                volume_method="invalid",  # type: ignore
            )

    def test_stop_distance_is_positive_fraction(self) -> None:
        """El stop distance debe ser una fraccion positiva < 1."""
        seq = _make_sequence()
        atr_result = _make_passing_atr_result()
        ohlc = _make_ohlc_around_pivot(100.0, breakout=True)
        eval_date = ohlc.index[-1]

        signal = detect_breakout_signal(
            seq, atr_result, ohlc, eval_date,
            require_volume_confirmation=False,
        )
        assert signal is not None
        assert 0 < signal.suggested_stop_distance_pct < 1
