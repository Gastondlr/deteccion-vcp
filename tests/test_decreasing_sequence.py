"""Tests para Paso 3: Deteccion de secuencias decrecientes."""

from __future__ import annotations

import pandas as pd
import pytest

from models.enums import SwingType
from models.types import Contraction, SwingPoint
from vcp_detection.heuristic.decreasing_sequence import detect_decreasing_sequence


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


class TestDetectDecreasingSequence:
    """Tests para detect_decreasing_sequence."""

    def test_detects_strict_decreasing(self) -> None:
        """Debe detectar secuencia estrictamente decreciente."""
        contractions = [
            _make_contraction("2023-01-10", "2023-01-20", 100, 85),   # 15%
            _make_contraction("2023-02-10", "2023-02-20", 100, 90),   # 10%
            _make_contraction("2023-03-10", "2023-03-20", 100, 95),   # 5%
        ]
        result = detect_decreasing_sequence(
            contractions,
            evaluation_date=pd.Timestamp("2023-04-01"),
            method="strict",
            min_contractions=2,
            lookback_bars=200,
        )
        assert result is not None
        assert result.n_contractions == 3
        assert result.depths_pct[0] > result.depths_pct[1] > result.depths_pct[2]

    def test_tolerance_accepts_small_increase(self) -> None:
        """Con tolerancia, debe aceptar una contraccion ligeramente mayor."""
        contractions = [
            _make_contraction("2023-01-10", "2023-01-20", 100, 90),   # 10%
            _make_contraction("2023-02-10", "2023-02-20", 100, 89.5), # 10.5% — ligeramente mayor
            _make_contraction("2023-03-10", "2023-03-20", 100, 95),   # 5%
        ]
        result_strict = detect_decreasing_sequence(
            contractions,
            evaluation_date=pd.Timestamp("2023-04-01"),
            method="strict",
            min_contractions=2,
            lookback_bars=200,
        )
        result_tolerance = detect_decreasing_sequence(
            contractions,
            evaluation_date=pd.Timestamp("2023-04-01"),
            method="tolerance",
            tolerance=0.10,
            min_contractions=2,
            lookback_bars=200,
        )
        # strict rechaza la secuencia de 3
        assert result_strict is None or result_strict.n_contractions < 3
        # tolerance la acepta
        assert result_tolerance is not None

    def test_max_depth_filter_rejects_deep_contractions(self) -> None:
        """max_depth_pct debe rechazar secuencias con contracciones muy profundas."""
        contractions = [
            _make_contraction("2023-01-10", "2023-01-20", 100, 65),   # 35% — demasiado
            _make_contraction("2023-02-10", "2023-02-20", 100, 85),   # 15%
            _make_contraction("2023-03-10", "2023-03-20", 100, 95),   # 5%
        ]
        result = detect_decreasing_sequence(
            contractions,
            evaluation_date=pd.Timestamp("2023-04-01"),
            method="tolerance",
            tolerance=0.10,
            min_contractions=2,
            lookback_bars=200,
            max_depth_pct=0.25,
        )
        # La secuencia de 3 incluye la de 35%, deberia rechazarse
        # Podria aceptar subsecuencias de 2 si pasan
        if result is not None:
            assert all(d <= 0.25 for d in result.depths_pct)

    def test_min_total_reduction_rejects_flat_sequences(self) -> None:
        """min_total_reduction debe rechazar secuencias sin compresion real."""
        contractions = [
            _make_contraction("2023-01-10", "2023-01-20", 100, 90),   # 10%
            _make_contraction("2023-02-10", "2023-02-20", 100, 90.2), # 9.8% — casi igual
        ]
        result = detect_decreasing_sequence(
            contractions,
            evaluation_date=pd.Timestamp("2023-04-01"),
            method="tolerance",
            tolerance=0.10,
            min_contractions=2,
            lookback_bars=200,
            min_total_reduction=0.70,  # exige que la ultima sea <= 70% de la primera
        )
        assert result is None

    def test_returns_none_when_insufficient_contractions(self) -> None:
        """Debe retornar None si hay menos contracciones que min_contractions."""
        contractions = [
            _make_contraction("2023-01-10", "2023-01-20", 100, 90),
        ]
        result = detect_decreasing_sequence(
            contractions,
            evaluation_date=pd.Timestamp("2023-04-01"),
            min_contractions=2,
            lookback_bars=200,
        )
        assert result is None

    def test_invalid_method_raises(self) -> None:
        """Metodo invalido debe lanzar ValueError."""
        with pytest.raises(ValueError, match="Invalid method"):
            detect_decreasing_sequence(
                [], pd.Timestamp("2023-01-01"), method="invalid_method"  # type: ignore
            )

    def test_lookback_filters_old_contractions(self) -> None:
        """Contracciones fuera de la ventana lookback deben ignorarse."""
        contractions = [
            _make_contraction("2022-01-10", "2022-01-20", 100, 85),  # Vieja
            _make_contraction("2023-03-10", "2023-03-20", 100, 95),  # Reciente
        ]
        result = detect_decreasing_sequence(
            contractions,
            evaluation_date=pd.Timestamp("2023-04-01"),
            min_contractions=2,
            lookback_bars=60,  # Solo ~60 dias atras
        )
        # Solo 1 contraccion reciente, necesita 2 → None
        assert result is None

    def test_robust_trend_detects_linear_decrease(self) -> None:
        """robust_trend debe detectar secuencia con pendiente negativa clara."""
        contractions = [
            _make_contraction("2023-01-10", "2023-01-20", 100, 80),   # 20%
            _make_contraction("2023-02-10", "2023-02-20", 100, 88),   # 12%
            _make_contraction("2023-03-10", "2023-03-20", 100, 95),   # 5%
        ]
        result = detect_decreasing_sequence(
            contractions,
            evaluation_date=pd.Timestamp("2023-04-01"),
            method="robust_trend",
            min_contractions=3,
            lookback_bars=200,
            min_r_squared=0.5,
        )
        assert result is not None
        assert result.n_contractions == 3
        assert result.method == "robust_trend"
        assert result.method_metrics["slope"] < 0
        assert result.method_metrics["r_squared"] >= 0.5

    def test_robust_trend_rejects_flat_sequence(self) -> None:
        """robust_trend debe rechazar secuencia sin tendencia clara."""
        contractions = [
            _make_contraction("2023-01-10", "2023-01-20", 100, 90),   # 10%
            _make_contraction("2023-02-10", "2023-02-20", 100, 89),   # 11% — sube
            _make_contraction("2023-03-10", "2023-03-20", 100, 90),   # 10% — vuelve
        ]
        result = detect_decreasing_sequence(
            contractions,
            evaluation_date=pd.Timestamp("2023-04-01"),
            method="robust_trend",
            min_contractions=3,
            lookback_bars=200,
            min_r_squared=0.9,
        )
        assert result is None

    def test_robust_trend_needs_three_points(self) -> None:
        """robust_trend con solo 2 contracciones debe retornar None."""
        contractions = [
            _make_contraction("2023-01-10", "2023-01-20", 100, 85),
            _make_contraction("2023-02-10", "2023-02-20", 100, 95),
        ]
        result = detect_decreasing_sequence(
            contractions,
            evaluation_date=pd.Timestamp("2023-04-01"),
            method="robust_trend",
            min_contractions=2,
            max_contractions=2,
            lookback_bars=200,
        )
        assert result is None

    def test_ascending_lows_accepts_valid_vcp(self) -> None:
        """Lows ascendentes (85, 90, 95) deben pasar con require_ascending_lows=True."""
        contractions = [
            _make_contraction("2023-01-10", "2023-01-20", 100, 85),   # 15%
            _make_contraction("2023-02-10", "2023-02-20", 100, 90),   # 10%
            _make_contraction("2023-03-10", "2023-03-20", 100, 95),   # 5%
        ]
        result = detect_decreasing_sequence(
            contractions,
            evaluation_date=pd.Timestamp("2023-04-01"),
            method="tolerance",
            min_contractions=2,
            lookback_bars=200,
            require_ascending_lows=True,
        )
        assert result is not None
        assert result.n_contractions == 3
        assert result.method_metrics["ascending_lows_passed"] is True

    def test_ascending_lows_rejects_descending_lows(self) -> None:
        """Lows descendentes (85, 80, 75) deben ser rechazados."""
        contractions = [
            _make_contraction("2023-01-10", "2023-01-20", 100, 85),   # 15%
            _make_contraction("2023-02-10", "2023-02-20", 95, 80),    # 15.8%
            _make_contraction("2023-03-10", "2023-03-20", 90, 75),    # 16.7%
        ]
        result = detect_decreasing_sequence(
            contractions,
            evaluation_date=pd.Timestamp("2023-04-01"),
            method="tolerance",
            tolerance=0.20,
            min_contractions=2,
            lookback_bars=200,
            require_ascending_lows=True,
        )
        assert result is None

    def test_ascending_lows_tolerance_accepts_small_dip(self) -> None:
        """Con tolerancia de 2%, un low ligeramente menor debe aceptarse."""
        contractions = [
            _make_contraction("2023-01-10", "2023-01-20", 100, 85),   # 15%
            _make_contraction("2023-02-10", "2023-02-20", 100, 84.5), # 15.5% — low baja 0.6%
            _make_contraction("2023-03-10", "2023-03-20", 100, 95),   # 5%
        ]
        result = detect_decreasing_sequence(
            contractions,
            evaluation_date=pd.Timestamp("2023-04-01"),
            method="tolerance",
            tolerance=0.10,
            min_contractions=2,
            lookback_bars=200,
            require_ascending_lows=True,
            ascending_lows_tolerance=0.02,
        )
        assert result is not None

    def test_ascending_lows_disabled(self) -> None:
        """Con require_ascending_lows=False, lows descendentes no rechazan."""
        contractions = [
            _make_contraction("2023-01-10", "2023-01-20", 100, 85),   # 15%
            _make_contraction("2023-02-10", "2023-02-20", 95, 80),    # 15.8%
            _make_contraction("2023-03-10", "2023-03-20", 90, 75),    # 16.7%
        ]
        result = detect_decreasing_sequence(
            contractions,
            evaluation_date=pd.Timestamp("2023-04-01"),
            method="tolerance",
            tolerance=0.20,
            min_contractions=2,
            lookback_bars=200,
            require_ascending_lows=False,
        )
        assert result is not None

    def test_ascending_lows_metrics_populated(self) -> None:
        """Las metricas de ascending lows deben estar en method_metrics."""
        contractions = [
            _make_contraction("2023-01-10", "2023-01-20", 100, 85),
            _make_contraction("2023-02-10", "2023-02-20", 100, 90),
            _make_contraction("2023-03-10", "2023-03-20", 100, 95),
        ]
        result = detect_decreasing_sequence(
            contractions,
            evaluation_date=pd.Timestamp("2023-04-01"),
            method="strict",
            min_contractions=2,
            lookback_bars=200,
            require_ascending_lows=True,
        )
        assert result is not None
        m = result.method_metrics
        assert m["ascending_lows_required"] is True
        assert m["ascending_lows_passed"] is True
        assert m["ascending_lows_values"] == [85.0, 90.0, 95.0]

    def test_zero_depth_handled_in_tolerance(self) -> None:
        """Profundidad cero no debe causar division por cero."""
        contractions = [
            Contraction(
                high_swing=SwingPoint(
                    date=pd.Timestamp("2023-01-10"), price=100, type=SwingType.HIGH,
                    confirmed_at=pd.Timestamp("2023-01-20"),
                ),
                low_swing=SwingPoint(
                    date=pd.Timestamp("2023-01-20"), price=100, type=SwingType.LOW,
                    confirmed_at=pd.Timestamp("2023-01-20"),
                ),
                depth_pct=0.0,
                depth_abs=0.0,
                duration_bars=10,
                confirmed_at=pd.Timestamp("2023-01-20"),
            ),
            _make_contraction("2023-02-10", "2023-02-20", 100, 95),
        ]
        result = detect_decreasing_sequence(
            contractions,
            evaluation_date=pd.Timestamp("2023-04-01"),
            method="tolerance",
            tolerance=0.10,
            min_contractions=2,
            lookback_bars=200,
        )
        assert result is None
