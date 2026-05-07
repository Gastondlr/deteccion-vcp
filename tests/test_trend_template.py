"""Tests para el módulo stages/trend_template.py."""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from stages.trend_template import (
    compute_52w_extremes,
    compute_smas,
    evaluate_trend_template,
    screen_universe,
)

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "csv"


def _make_trending_df(n_days: int, start: float, end: float) -> pd.DataFrame:
    """Genera un DataFrame OHLCV con tendencia lineal + ruido pequeño."""
    rng = np.random.default_rng(42)
    dates = pd.bdate_range(start="2020-01-01", periods=n_days, freq="B")
    base = np.linspace(start, end, n_days)
    noise = rng.normal(0, 0.005 * np.abs(base), n_days)
    close = base + noise

    high = close * (1 + rng.uniform(0.001, 0.015, n_days))
    low = close * (1 - rng.uniform(0.001, 0.015, n_days))
    open_ = close * (1 + rng.uniform(-0.01, 0.01, n_days))
    volume = rng.integers(1_000_000, 10_000_000, n_days).astype(float)

    return pd.DataFrame({
        "date": dates,
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    })


@pytest.fixture
def bull_stock_df():
    return _make_trending_df(500, start=50.0, end=150.0)


@pytest.fixture
def bear_stock_df():
    return _make_trending_df(500, start=150.0, end=50.0)


class TestComputeSmas:
    def test_columns_exist(self, bull_stock_df):
        result = compute_smas(bull_stock_df)
        assert "sma_50" in result.columns
        assert "sma_150" in result.columns
        assert "sma_200" in result.columns

    def test_does_not_modify_input(self, bull_stock_df):
        original_cols = list(bull_stock_df.columns)
        compute_smas(bull_stock_df)
        assert list(bull_stock_df.columns) == original_cols

    def test_sma_values_are_correct(self, bull_stock_df):
        result = compute_smas(bull_stock_df)
        idx = 250
        expected_50 = bull_stock_df["close"].iloc[idx - 49 : idx + 1].mean()
        assert result["sma_50"].iloc[idx] == pytest.approx(expected_50, rel=1e-10)

    def test_nan_before_window(self, bull_stock_df):
        result = compute_smas(bull_stock_df)
        assert pd.isna(result["sma_200"].iloc[198])
        assert pd.notna(result["sma_200"].iloc[199])


class TestCompute52wExtremes:
    def test_columns_exist(self, bull_stock_df):
        result = compute_52w_extremes(bull_stock_df)
        assert "low_52w" in result.columns
        assert "high_52w" in result.columns

    def test_does_not_modify_input(self, bull_stock_df):
        original_cols = list(bull_stock_df.columns)
        compute_52w_extremes(bull_stock_df)
        assert list(bull_stock_df.columns) == original_cols

    def test_extremes_are_correct(self, bull_stock_df):
        result = compute_52w_extremes(bull_stock_df)
        idx = 300
        window = bull_stock_df.iloc[idx - 251 : idx + 1]
        expected_low = window["low"].min()
        expected_high = window["high"].max()
        assert result["low_52w"].iloc[idx] == pytest.approx(expected_low, rel=1e-10)
        assert result["high_52w"].iloc[idx] == pytest.approx(expected_high, rel=1e-10)

    def test_nan_before_window(self, bull_stock_df):
        result = compute_52w_extremes(bull_stock_df)
        assert pd.isna(result["low_52w"].iloc[250])
        assert pd.notna(result["low_52w"].iloc[251])


class TestEvaluateTrendTemplate:
    def test_bull_stock_passes_all_conditions(self, bull_stock_df):
        result = evaluate_trend_template(bull_stock_df)
        last_rows = result.tail(50)
        passing = last_rows["trend_template"].sum()
        assert passing > 0, "Bull stock should pass trend template in at least some of the last 50 rows"

    def test_bear_stock_fails_most_conditions(self, bear_stock_df):
        result = evaluate_trend_template(bear_stock_df)
        last_rows = result.tail(50)
        assert last_rows["trend_template"].sum() == 0

    def test_conditions_count_matches(self, bull_stock_df):
        result = evaluate_trend_template(bull_stock_df)
        cond_cols = [f"cond_{i}" for i in range(1, 8)]
        manual_sum = result[cond_cols].sum(axis=1).astype(int)
        pd.testing.assert_series_equal(
            result["conditions_met"], manual_sum, check_names=False,
        )

    def test_trend_template_is_and_of_all_conditions(self, bull_stock_df):
        result = evaluate_trend_template(bull_stock_df)
        cond_cols = [f"cond_{i}" for i in range(1, 8)]
        manual_and = result[cond_cols].all(axis=1)
        pd.testing.assert_series_equal(
            result["trend_template"], manual_and, check_names=False,
        )

    def test_nan_handling(self):
        df = _make_trending_df(210, start=50.0, end=80.0)
        result = evaluate_trend_template(df)
        assert result["trend_template"].iloc[0] is np.bool_(False)
        assert result["conditions_met"].iloc[0] == 0

    def test_output_dtypes(self, bull_stock_df):
        result = evaluate_trend_template(bull_stock_df)
        for i in range(1, 8):
            assert result[f"cond_{i}"].dtype == bool
        assert result["trend_template"].dtype == bool
        assert pd.api.types.is_integer_dtype(result["conditions_met"])

    def test_does_not_modify_input(self, bull_stock_df):
        original_cols = list(bull_stock_df.columns)
        evaluate_trend_template(bull_stock_df)
        assert list(bull_stock_df.columns) == original_cols

    def test_all_expected_columns_present(self, bull_stock_df):
        result = evaluate_trend_template(bull_stock_df)
        expected = {
            "sma_50", "sma_150", "sma_200", "low_52w", "high_52w",
            "cond_1", "cond_2", "cond_3", "cond_4", "cond_5", "cond_6", "cond_7",
            "trend_template", "conditions_met",
        }
        assert expected.issubset(set(result.columns))


class TestScreenUniverse:
    def test_returns_correct_format(self, bull_stock_df, bear_stock_df):
        last_date = str(bull_stock_df["date"].iloc[-1].date())
        dfs = {"BULL": bull_stock_df, "BEAR": bear_stock_df}
        result = screen_universe(dfs, date=last_date)

        expected_cols = (
            ["ticker", "close", "sma_50", "sma_150", "sma_200"]
            + [f"cond_{i}" for i in range(1, 8)]
            + ["trend_template", "conditions_met"]
        )
        for col in expected_cols:
            assert col in result.columns

    def test_sorted_by_conditions_met(self, bull_stock_df, bear_stock_df):
        last_date = str(bull_stock_df["date"].iloc[-1].date())
        dfs = {"BULL": bull_stock_df, "BEAR": bear_stock_df}
        result = screen_universe(dfs, date=last_date)
        conditions = result["conditions_met"].tolist()
        assert conditions == sorted(conditions, reverse=True)

    def test_empty_universe(self):
        result = screen_universe({}, date="2024-01-15")
        assert len(result) == 0
        assert "ticker" in result.columns

    def test_date_not_found_skips_ticker(self, bull_stock_df):
        dfs = {"BULL": bull_stock_df}
        result = screen_universe(dfs, date="1999-01-01")
        assert len(result) == 0


class TestWithRealCSV:
    @pytest.mark.skipif(
        not (DATA_DIR / "NVDA.csv").exists(),
        reason="NVDA.csv not found in data/csv/",
    )
    def test_nvda_runs_without_error(self):
        df = pd.read_csv(DATA_DIR / "NVDA.csv")
        result = evaluate_trend_template(df)

        expected = {
            "sma_50", "sma_150", "sma_200", "low_52w", "high_52w",
            "cond_1", "cond_2", "cond_3", "cond_4", "cond_5", "cond_6", "cond_7",
            "trend_template", "conditions_met",
        }
        assert expected.issubset(set(result.columns))
        assert len(result) == len(df)
        assert result["conditions_met"].max() <= 7
        assert result["conditions_met"].min() >= 0

    @pytest.mark.skipif(
        not (DATA_DIR / "NVDA.csv").exists(),
        reason="NVDA.csv not found in data/csv/",
    )
    def test_screen_universe_with_real_data(self):
        dfs = {}
        for path in sorted(DATA_DIR.glob("*.csv"))[:5]:
            dfs[path.stem] = pd.read_csv(path)

        dates = pd.read_csv(DATA_DIR / "NVDA.csv")["date"]
        mid_date = dates.iloc[len(dates) // 2]

        result = screen_universe(dfs, date=mid_date)
        assert len(result) > 0
        assert result["conditions_met"].is_monotonic_decreasing
