"""Tests para simulate_trade: trailing stop ATR adaptativo y time-based exit."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from vcp_detection.analysis import simulate_trade


def _make_ohlc(closes: list[float], start: str = "2023-01-02") -> pd.DataFrame:
    """Genera OHLC simple a partir de una lista de closes."""
    n = len(closes)
    dates = pd.bdate_range(start=start, periods=n)
    close = np.array(closes, dtype=float)
    high = close + 0.5
    low = close - 0.5
    volume = np.full(n, 1_000_000.0)
    return pd.DataFrame(
        {"open": close, "high": high, "low": low, "close": close, "volume": volume},
        index=dates,
    )


def _make_pattern(ohlc: pd.DataFrame, entry_idx: int = 0) -> dict:
    """Genera un pattern dict minimo para simulate_trade."""
    entry_date = ohlc.index[entry_idx]
    entry_price = float(ohlc["close"].iloc[entry_idx])
    stop = entry_price * 0.93
    return {
        "first_signal_date": entry_date,
        "entry_price": entry_price,
        "effective_stop": stop,
        "initial_risk": entry_price - stop,
    }


BASE_RISK_PARAMS = {
    "max_stop_loss_pct": 0.07,
    "breakeven_r_multiple": 2.0,
    "trailing_sma_period": 20,
    "trailing_volume_factor": 1.5,
}


class TestBackwardCompatibility:
    """Parametros originales deben funcionar identicamente."""

    def test_default_params_no_error(self) -> None:
        closes = [100.0] + [101.0 + i * 0.5 for i in range(50)]
        ohlc = _make_ohlc(closes)
        pattern = _make_pattern(ohlc)
        result = simulate_trade(ohlc, pattern, BASE_RISK_PARAMS)
        assert "exit_reason" in result
        assert "exit_price" in result

    def test_missing_new_keys_uses_defaults(self) -> None:
        closes = [100.0] + [101.0 + i * 0.5 for i in range(50)]
        ohlc = _make_ohlc(closes)
        pattern = _make_pattern(ohlc)
        result = simulate_trade(ohlc, pattern, BASE_RISK_PARAMS)
        assert result["exit_reason"] != "time_exit"


class TestATRTrailingStop:
    """Tests para trailing_stop_method='atr'."""

    def test_atr_trailing_stop_basic(self) -> None:
        """Con ATR trail, el stop debe subir a medida que el precio sube."""
        closes = [100.0] + [100.0 + i * 1.0 for i in range(1, 60)]
        ohlc = _make_ohlc(closes)
        pattern = _make_pattern(ohlc)
        risk = {**BASE_RISK_PARAMS, "trailing_stop_method": "atr",
                "trailing_atr_period": 14, "trailing_atr_multiplier": 2.0}
        result = simulate_trade(ohlc, pattern, risk)
        stops = [s[1] for s in result["stop_history"]]
        assert stops[-1] > stops[0]

    def test_atr_trailing_stop_never_decreases(self) -> None:
        """El stop nunca debe bajar."""
        closes = [100.0] + [100.0 + i * 0.5 for i in range(1, 80)]
        ohlc = _make_ohlc(closes)
        pattern = _make_pattern(ohlc)
        risk = {**BASE_RISK_PARAMS, "trailing_stop_method": "atr",
                "trailing_atr_period": 14, "trailing_atr_multiplier": 3.0}
        result = simulate_trade(ohlc, pattern, risk)
        stops = [s[1] for s in result["stop_history"]]
        for i in range(1, len(stops)):
            assert stops[i] >= stops[i - 1] - 1e-10

    def test_atr_method_skips_distribution_exit(self) -> None:
        """Con trailing_stop_method='atr', no debe haber exit por distribution."""
        closes = [100.0] + [105.0] * 5 + [98.0] * 30
        ohlc = _make_ohlc(closes)
        ohlc.loc[ohlc.index[-1], "volume"] = 10_000_000.0
        pattern = _make_pattern(ohlc)
        risk = {**BASE_RISK_PARAMS, "trailing_stop_method": "atr",
                "trailing_atr_period": 14, "trailing_atr_multiplier": 3.0}
        result = simulate_trade(ohlc, pattern, risk)
        assert result["exit_reason"] != "distribution"

    def test_sma_method_can_trigger_distribution(self) -> None:
        """Con trailing_stop_method='sma', distribution exit sigue funcionando."""
        n = 50
        closes = [100.0] * n
        ohlc = _make_ohlc(closes)
        sma_period = 20
        ohlc.iloc[-1, ohlc.columns.get_loc("close")] = 90.0
        ohlc.iloc[-1, ohlc.columns.get_loc("volume")] = 5_000_000.0
        pattern = _make_pattern(ohlc)
        pattern["effective_stop"] = 80.0
        pattern["initial_risk"] = 20.0
        risk = {**BASE_RISK_PARAMS, "trailing_stop_method": "sma",
                "trailing_sma_period": sma_period, "trailing_volume_factor": 1.5}
        result = simulate_trade(ohlc, pattern, risk)
        assert result["exit_reason"] == "distribution"

    def test_atr_tightens_in_low_volatility(self) -> None:
        """En volatilidad baja (high-low chico), el ATR trail se acerca al precio."""
        n = 80
        closes = [100.0 + i * 0.3 for i in range(n)]
        ohlc = _make_ohlc(closes)
        ohlc["high"] = ohlc["close"] + 0.1
        ohlc["low"] = ohlc["close"] - 0.1
        pattern = _make_pattern(ohlc)
        risk_tight = {**BASE_RISK_PARAMS, "trailing_stop_method": "atr",
                      "trailing_atr_period": 14, "trailing_atr_multiplier": 2.0}
        result = simulate_trade(ohlc, pattern, risk_tight)
        final_close = float(ohlc["close"].iloc[-1])
        final_stop = result["stop_history"][-1][1]
        gap = final_close - final_stop
        assert gap < 5.0


class TestTimeBasedExit:
    """Tests para max_bars_without_progress."""

    def test_time_exit_triggers_after_n_bars(self) -> None:
        """Precio plano post-entry debe triggear time exit."""
        closes = [100.0] + [101.0] * 40
        ohlc = _make_ohlc(closes)
        pattern = _make_pattern(ohlc)
        risk = {**BASE_RISK_PARAMS, "max_bars_without_progress": 15, "min_progress_r": 0.5}
        result = simulate_trade(ohlc, pattern, risk)
        assert result["exit_reason"] == "time_exit"

    def test_time_exit_disabled_by_default(self) -> None:
        """Con max_bars_without_progress=None, no hay time exit."""
        closes = [100.0] + [101.0] * 40
        ohlc = _make_ohlc(closes)
        pattern = _make_pattern(ohlc)
        risk = {**BASE_RISK_PARAMS, "max_bars_without_progress": None}
        result = simulate_trade(ohlc, pattern, risk)
        assert result["exit_reason"] != "time_exit"

    def test_time_exit_resets_on_progress(self) -> None:
        """Avance de R suficiente debe resetear el timer."""
        initial_risk = 100.0 * 0.07
        r_step = 0.5
        progress_price = 100.0 + r_step * initial_risk
        closes = [100.0]
        closes += [100.5] * 10
        closes += [progress_price + 1.0] * 5
        closes += [progress_price + 1.0] * 20
        ohlc = _make_ohlc(closes)
        pattern = _make_pattern(ohlc)
        risk = {**BASE_RISK_PARAMS, "max_bars_without_progress": 15, "min_progress_r": r_step}
        result = simulate_trade(ohlc, pattern, risk)
        entry_loc = ohlc.index.get_loc(pattern["first_signal_date"])
        exit_loc = ohlc.index.get_loc(result["exit_date"])
        assert exit_loc - entry_loc > 15

    def test_time_exit_reason_string(self) -> None:
        closes = [100.0] + [100.5] * 30
        ohlc = _make_ohlc(closes)
        pattern = _make_pattern(ohlc)
        risk = {**BASE_RISK_PARAMS, "max_bars_without_progress": 10, "min_progress_r": 0.5}
        result = simulate_trade(ohlc, pattern, risk)
        assert result["exit_reason"] == "time_exit"


class TestCombined:
    """Tests con ambas features activadas."""

    def test_stop_takes_priority_over_time_exit(self) -> None:
        """Si el stop se toca antes del time limit, sale por stop."""
        closes = [100.0, 105.0, 90.0]  # stop loss rapido
        ohlc = _make_ohlc(closes)
        pattern = _make_pattern(ohlc)
        risk = {**BASE_RISK_PARAMS, "trailing_stop_method": "atr",
                "trailing_atr_period": 14, "trailing_atr_multiplier": 2.0,
                "max_bars_without_progress": 30, "min_progress_r": 0.5}
        result = simulate_trade(ohlc, pattern, risk)
        assert result["exit_reason"] in ("stop_loss", "trailing_stop")

    def test_both_features_enabled_runs_cleanly(self) -> None:
        """Ambas features activadas no causan errores."""
        closes = [100.0] + [100.0 + i * 0.3 for i in range(1, 100)]
        ohlc = _make_ohlc(closes)
        pattern = _make_pattern(ohlc)
        risk = {**BASE_RISK_PARAMS, "trailing_stop_method": "atr",
                "trailing_atr_period": 14, "trailing_atr_multiplier": 3.0,
                "max_bars_without_progress": 30, "min_progress_r": 0.5}
        result = simulate_trade(ohlc, pattern, risk)
        assert result["exit_reason"] in ("stop_loss", "trailing_stop", "time_exit", "open")
        assert result["max_r"] >= 0
        assert len(result["stop_history"]) > 1
