"""Backtesting del pipeline VCP con un set de parámetros sobre un universo de tickers."""

from __future__ import annotations

from math import sqrt
from typing import Any

import numpy as np
import pandas as pd

from models.configs import ATRZigZagConfig
from vcp_detection.analysis import group_signals_into_patterns, simulate_trade
from vcp_detection.heuristic import ATRZigZagDetector, run_full_vcp_pipeline

N_MIN_TRADES = 10


def run_backtest_for_params(
    universe: dict[str, pd.DataFrame],
    params: dict[str, Any],
    evaluation_window: tuple[pd.Timestamp, pd.Timestamp] | None = None,
) -> dict:
    """Corre el pipeline VCP completo sobre todos los tickers del universo.

    Args:
        universe: Dict {ticker: DataFrame OHLCV}.
        params: Dict con keys swing_config, sequence_params, compression_params,
            volume_contraction_params, breakout_params, grouping_params, risk_params.
        evaluation_window: Tupla (start, end) opcional para restringir las fechas
            de evaluación del pipeline.

    Returns:
        Dict con keys:
        - per_ticker: dict {ticker: {n_trades, trades, patterns}}
        - all_trades: list de todos los trade dicts (con key "ticker" agregada)
        - metrics: resultado de compute_aggregate_metrics
    """
    swing_config: ATRZigZagConfig = params["swing_config"]
    sequence_params: dict = params["sequence_params"]
    compression_params: dict = params["compression_params"]
    volume_contraction_params: dict = params["volume_contraction_params"]
    breakout_params: dict = params["breakout_params"]
    grouping_params: dict = params["grouping_params"]
    risk_params: dict = params["risk_params"]

    per_ticker = {}
    all_trades = []

    for ticker, ohlc in universe.items():
        eval_dates = None
        if evaluation_window is not None:
            start, end = evaluation_window
            eval_dates = ohlc.index[(ohlc.index >= start) & (ohlc.index <= end)]

        detector = ATRZigZagDetector(swing_config)
        results = run_full_vcp_pipeline(
            ohlc=ohlc,
            swing_detector=detector,
            sequence_params=sequence_params,
            compression_params=compression_params,
            breakout_params=breakout_params,
            evaluation_dates=eval_dates,
            volume_contraction_params=volume_contraction_params,
        )

        signals = {dt: sig for dt, sig in results.items() if sig is not None}
        patterns = group_signals_into_patterns(
            signals,
            risk_params=risk_params,
            max_gap_days=grouping_params["max_gap_days"],
        )

        trades = []
        for p in patterns:
            trade = simulate_trade(ohlc, p, risk_params)
            trade["ticker"] = ticker
            trade["pattern"] = p
            trades.append(trade)

        per_ticker[ticker] = {
            "n_trades": len(trades),
            "trades": trades,
            "patterns": patterns,
        }
        all_trades.extend(trades)

    metrics = compute_aggregate_metrics(all_trades)
    return {
        "per_ticker": per_ticker,
        "all_trades": all_trades,
        "metrics": metrics,
    }


def compute_aggregate_metrics(trades: list[dict]) -> dict:
    """Calcula métricas agregadas sobre una lista de trades.

    Args:
        trades: Lista de trade dicts (output de simulate_trade con key "ticker").

    Returns:
        Dict con n_trades, expectancy_r, win_rate, profit_factor,
        avg_winner_r, avg_loser_r, max_r, min_r, trades_per_ticker.
    """
    n_trades = len(trades)
    if n_trades == 0:
        return {
            "n_trades": 0,
            "expectancy_r": 0.0,
            "win_rate": 0.0,
            "profit_factor": 0.0,
            "avg_winner_r": 0.0,
            "avg_loser_r": 0.0,
            "max_r": 0.0,
            "min_r": 0.0,
            "trades_per_ticker": {},
        }

    r_multiples = [t["r_multiple"] for t in trades]
    winners = [r for r in r_multiples if r > 0]
    losers = [r for r in r_multiples if r <= 0]

    gross_profit = sum(winners) if winners else 0.0
    gross_loss = abs(sum(losers)) if losers else 0.0

    trades_per_ticker: dict[str, int] = {}
    for t in trades:
        ticker = t.get("ticker", "unknown")
        trades_per_ticker[ticker] = trades_per_ticker.get(ticker, 0) + 1

    return {
        "n_trades": n_trades,
        "expectancy_r": float(np.mean(r_multiples)),
        "win_rate": len(winners) / n_trades,
        "profit_factor": gross_profit / gross_loss if gross_loss > 0 else float("inf"),
        "avg_winner_r": float(np.mean(winners)) if winners else 0.0,
        "avg_loser_r": float(np.mean(losers)) if losers else 0.0,
        "max_r": float(max(r_multiples)),
        "min_r": float(min(r_multiples)),
        "trades_per_ticker": trades_per_ticker,
    }


def compute_objective_score(metrics: dict) -> float:
    """Calcula el score objetivo para Optuna (Opción C - penalización suave).

    score = expectancy_r * penalty * sqrt(n_trades)
    penalty = sqrt(min(n_trades / N_MIN_TRADES, 1.0))

    Args:
        metrics: Dict output de compute_aggregate_metrics.

    Returns:
        Score float. -1.0 si n_trades == 0.
    """
    n_trades = metrics["n_trades"]
    if n_trades == 0:
        return -1.0

    expectancy = metrics["expectancy_r"]
    penalty = sqrt(min(n_trades / N_MIN_TRADES, 1.0))
    return expectancy * penalty * sqrt(n_trades)
