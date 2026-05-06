"""Backtesting del pipeline VCP con un set de parámetros sobre un universo de tickers."""

from __future__ import annotations

import logging
from math import sqrt
from typing import Any

import numpy as np
import pandas as pd

from models.configs import ATRZigZagConfig
from models.types import VCPSignal, VolumeContractionResult
from vcp_detection.analysis import group_signals_into_patterns, simulate_trade
from vcp_detection.heuristic import ATRZigZagDetector, run_full_vcp_pipeline
from vcp_detection.heuristic.atr_compression import verify_atr_compression
from vcp_detection.heuristic.decreasing_sequence import detect_decreasing_sequence
from vcp_detection.heuristic.pivot_breakout import detect_breakout_signal
from vcp_detection.heuristic.volume_contraction import verify_volume_contraction

from autoresearch.caching import SwingCache

logger = logging.getLogger(__name__)

N_MIN_TRADES = 10


def run_pipeline_cached(
    ohlc: pd.DataFrame,
    ticker: str,
    params: dict[str, Any],
    cache: SwingCache,
    evaluation_dates: pd.DatetimeIndex | None = None,
    deduplicate: bool = False,
    dedup_cooldown_bars: int = 1,
) -> dict[pd.Timestamp, VCPSignal | None]:
    """Pipeline VCP con cache de swings/contracciones.

    Reproduce EXACTAMENTE la lógica de run_full_vcp_pipeline (pivot_breakout.py:376)
    pero obtiene swings y contracciones del cache en lugar de recomputarlos.
    """
    swing_config: ATRZigZagConfig = params["swing_config"]
    sequence_params: dict = params["sequence_params"]
    compression_params: dict = params["compression_params"]
    breakout_params: dict = params["breakout_params"]
    volume_contraction_params: dict | None = params.get("volume_contraction_params")

    if evaluation_dates is None:
        evaluation_dates = ohlc.index

    cached = cache.get_or_compute(ticker, ohlc, swing_config)
    all_contractions = cached["contractions"]

    active_pivot: float | None = None
    active_stop: float | None = None
    invalidated_at: int | None = None

    results: dict[pd.Timestamp, VCPSignal | None] = {}
    for dt in evaluation_dates:
        dt_loc = ohlc.index.get_loc(dt)

        if deduplicate and active_pivot is not None and active_stop is not None:
            close_today = float(ohlc.loc[dt, "close"])
            if close_today < active_stop:
                invalidated_at = dt_loc
                active_pivot = None
                active_stop = None

        seq = detect_decreasing_sequence(
            all_contractions,
            evaluation_date=dt,
            ohlc_index=ohlc.index,
            **sequence_params,
        )
        if seq is None:
            results[dt] = None
            continue

        try:
            atr_result = verify_atr_compression(seq, ohlc, **compression_params)
        except ValueError:
            results[dt] = None
            continue

        if not atr_result.passes:
            results[dt] = None
            continue

        vol_contraction_result: VolumeContractionResult | None = None
        if volume_contraction_params is not None:
            try:
                vol_contraction_result = verify_volume_contraction(
                    sequence=seq, ohlc=ohlc, **volume_contraction_params,
                )
            except ValueError:
                results[dt] = None
                continue
            if not vol_contraction_result.passes:
                results[dt] = None
                continue

        try:
            signal = detect_breakout_signal(
                sequence=seq,
                atr_compression_result=atr_result,
                ohlc=ohlc,
                evaluation_date=dt,
                volume_contraction_result=vol_contraction_result,
                **breakout_params,
            )
        except ValueError:
            results[dt] = None
            continue

        if signal is None:
            results[dt] = None
            continue

        if deduplicate:
            pivot_price = signal.pivot_price
            is_same_pattern = (
                active_pivot is not None
                and abs(pivot_price - active_pivot) < 1e-10
            )
            in_cooldown = (
                invalidated_at is not None
                and (dt_loc - invalidated_at) < dedup_cooldown_bars
            )

            if is_same_pattern or in_cooldown:
                results[dt] = None
                continue

            active_pivot = pivot_price
            active_stop = signal.suggested_stop
            invalidated_at = None

        results[dt] = signal

    n_signals = sum(1 for v in results.values() if v is not None)
    logger.debug(
        "Cached VCP pipeline: %d dates evaluated, %d signals generated (%.1f%%)",
        len(evaluation_dates),
        n_signals,
        100 * n_signals / max(len(evaluation_dates), 1),
    )
    return results


def run_backtest_for_params(
    universe: dict[str, pd.DataFrame],
    params: dict[str, Any],
    evaluation_window: tuple[pd.Timestamp, pd.Timestamp] | None = None,
    cache: SwingCache | None = None,
) -> dict:
    """Corre el pipeline VCP completo sobre todos los tickers del universo.

    Args:
        universe: Dict {ticker: DataFrame OHLCV}.
        params: Dict con keys swing_config, sequence_params, compression_params,
            volume_contraction_params, breakout_params, grouping_params, risk_params.
        evaluation_window: Tupla (start, end) opcional para restringir las fechas
            de evaluación del pipeline.
        cache: SwingCache opcional. Si se pasa, usa run_pipeline_cached para
            evitar recomputar swings/contracciones con el mismo swing_config.

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

        if cache is not None:
            results = run_pipeline_cached(
                ohlc=ohlc,
                ticker=ticker,
                params=params,
                cache=cache,
                evaluation_dates=eval_dates,
            )
        else:
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
