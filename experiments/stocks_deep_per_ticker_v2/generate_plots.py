"""Genera graficos de patrones y trades para las configs COMP#1 de cada ticker.

Corre el pipeline con la config ganadora, simula trades en sequential mode,
y guarda plots de patrones VCP y simulaciones de trades.

Uso:
    python generate_plots.py              # todos los tickers, train + test
    python generate_plots.py AAPL         # solo AAPL
    python generate_plots.py AAPL --test  # solo AAPL test
"""
import argparse
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import numpy as np
import pandas as pd

project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from models.configs import ATRZigZagConfig
from vcp_detection.heuristic import ATRZigZagDetector, run_full_vcp_pipeline
from vcp_detection.analysis import (
    evaluate_signals_to_trades,
    plot_vcp_trade_combined,
)

DATA_DIR = project_root / "data" / "csv"
OUTPUT_DIR = Path(__file__).resolve().parent / "plots"
TRAIN_CUTOFF = pd.Timestamp("2020-01-01")


def apply_volume_post_filter(signals, ohlc, window, threshold, lookback_days=50):
    filtered = {}
    for dt, sig in signals.items():
        eval_loc = ohlc.index.get_loc(dt)
        ls = max(0, eval_loc - lookback_days)
        va = float(ohlc["volume"].iloc[ls:eval_loc].mean()) if eval_loc > ls else 0.0
        if va <= 0:
            continue
        ws = max(0, eval_loc - window + 1)
        if any(float(v) >= threshold * va for v in ohlc["volume"].iloc[ws:eval_loc + 1]):
            filtered[dt] = sig
    return filtered


CONFIGS = {
    "AAPL": {
        "swing": ATRZigZagConfig(atr_mult=2.0, use_close_only=False),
        "sequence": {
            "method": "tolerance", "min_contractions": 2, "max_contractions": 6,
            "lookback_bars": 126, "tolerance": 0.10, "max_depth_pct": 0.25,
            "max_depth_atr": 6, "min_total_reduction": 0.80,
            "require_ascending_lows": True, "ascending_lows_tolerance": 0.01,
        },
        "compression": {"method": "ratio", "atr_period": 14, "ratio_threshold": 0.85},
        "volume_contraction": {"method": "ratio", "ratio_threshold": 0.85},
        "breakout": {
            "volume_method": "ratio", "volume_ratio_threshold": 1.0,
            "volume_lookback_days": 50, "require_volume_confirmation": False,
        },
        "risk": {
            "trailing_stop_method": "atr", "trailing_atr_multiplier": 2.0,
            "trailing_atr_period": 14, "target_r_multiple": 2.0,
            "early_exit_days": None, "breakeven_r_multiple": 1.0,
            "max_stop_loss_pct": 0.05, "max_bars_without_progress": 15,
            "min_progress_r": 0.5,
            "trailing_sma_period": 20, "trailing_volume_factor": 1.5,
        },
    },
    "AMZN": {
        "swing": ATRZigZagConfig(atr_mult=3.0, use_close_only=False),
        "sequence": {
            "method": "tolerance", "min_contractions": 2, "max_contractions": 6,
            "lookback_bars": 126, "tolerance": 0.15, "max_depth_pct": 0.30,
            "max_depth_atr": None, "min_total_reduction": 0.60,
            "require_ascending_lows": True, "ascending_lows_tolerance": 0.01,
        },
        "compression": {"method": "ratio", "atr_period": 14, "ratio_threshold": 0.90},
        "volume_contraction": {"method": "ratio", "ratio_threshold": 0.85},
        "breakout": {
            "volume_method": "ratio", "volume_ratio_threshold": 1.2,
            "volume_lookback_days": 50, "require_volume_confirmation": True,
            "volume_confirmation_window": 3,
        },
        "risk": {
            "trailing_stop_method": "atr", "trailing_atr_multiplier": 2.0,
            "trailing_atr_period": 14, "target_r_multiple": None,
            "early_exit_days": None, "breakeven_r_multiple": 1.5,
            "max_stop_loss_pct": 0.03, "max_bars_without_progress": 15,
            "min_progress_r": 0.5,
            "trailing_sma_period": 20, "trailing_volume_factor": 1.5,
        },
    },
    "GOOGL": {
        "swing": ATRZigZagConfig(atr_mult=2.0, use_close_only=True),
        "sequence": {
            "method": "tolerance", "min_contractions": 2, "max_contractions": 6,
            "lookback_bars": 126, "tolerance": 0.10, "max_depth_pct": 0.25,
            "max_depth_atr": 8, "min_total_reduction": 0.80,
            "require_ascending_lows": True, "ascending_lows_tolerance": 0.08,
        },
        "compression": {"method": "ratio", "atr_period": 14, "ratio_threshold": 0.95},
        "volume_contraction": None,
        "breakout": {
            "volume_method": "ratio", "volume_ratio_threshold": 1.2,
            "volume_lookback_days": 50, "require_volume_confirmation": True,
            "volume_confirmation_window": 3,
        },
        "risk": {
            "trailing_stop_method": "atr", "trailing_atr_multiplier": 2.5,
            "trailing_atr_period": 14, "target_r_multiple": None,
            "early_exit_days": None, "breakeven_r_multiple": 1.0,
            "max_stop_loss_pct": 0.07, "max_bars_without_progress": 15,
            "min_progress_r": 0.5,
            "trailing_sma_period": 20, "trailing_volume_factor": 1.5,
        },
    },
    "MSFT": {
        "swing": ATRZigZagConfig(atr_mult=2.0, use_close_only=False),
        "sequence": {
            "method": "tolerance", "min_contractions": 2, "max_contractions": 6,
            "lookback_bars": 126, "tolerance": 0.10, "max_depth_pct": 0.25,
            "max_depth_atr": None, "min_total_reduction": 0.80,
            "require_ascending_lows": True, "ascending_lows_tolerance": 0.03,
        },
        "compression": {"method": "ratio", "atr_period": 14, "ratio_threshold": 0.90},
        "volume_contraction": {"method": "ratio", "ratio_threshold": 0.85},
        "breakout": {
            "volume_method": "ratio", "volume_ratio_threshold": 1.0,
            "volume_lookback_days": 50, "require_volume_confirmation": False,
        },
        "risk": {
            "trailing_stop_method": "atr", "trailing_atr_multiplier": 3.0,
            "trailing_atr_period": 14, "target_r_multiple": 2.0,
            "early_exit_days": None, "breakeven_r_multiple": 0.5,
            "max_stop_loss_pct": 0.05, "max_bars_without_progress": 15,
            "min_progress_r": 0.5,
            "trailing_sma_period": 20, "trailing_volume_factor": 1.5,
        },
    },
    "NVDA": {
        "swing": ATRZigZagConfig(atr_mult=2.0, use_close_only=False),
        "sequence": {
            "method": "tolerance", "min_contractions": 2, "max_contractions": 6,
            "lookback_bars": 63, "tolerance": 0.10, "max_depth_pct": 0.30,
            "max_depth_atr": None, "min_total_reduction": 0.60,
            "require_ascending_lows": True, "ascending_lows_tolerance": 0.01,
        },
        "compression": {"method": "ratio", "atr_period": 14, "ratio_threshold": 0.95},
        "volume_contraction": None,
        "breakout": {
            "volume_method": "ratio", "volume_ratio_threshold": 1.2,
            "volume_lookback_days": 50, "require_volume_confirmation": True,
            "volume_confirmation_window": 3,
        },
        "risk": {
            "trailing_stop_method": "atr", "trailing_atr_multiplier": 2.5,
            "trailing_atr_period": 14, "target_r_multiple": 5.0,
            "early_exit_days": None, "breakeven_r_multiple": 1.5,
            "max_stop_loss_pct": 0.05, "max_bars_without_progress": 15,
            "min_progress_r": 0.5,
            "trailing_sma_period": 20, "trailing_volume_factor": 1.5,
        },
        "risk_test_override": {
            "target_r_multiple": None,
        },
    },
    "TSLA": {
        "swing": ATRZigZagConfig(atr_mult=2.0, use_close_only=True),
        "sequence": {
            "method": "tolerance", "min_contractions": 2, "max_contractions": 6,
            "lookback_bars": 126, "tolerance": 0.10, "max_depth_pct": 0.35,
            "max_depth_atr": None, "min_total_reduction": 0.80,
            "require_ascending_lows": True, "ascending_lows_tolerance": 0.08,
        },
        "compression": {"method": "ratio", "atr_period": 14, "ratio_threshold": 0.95},
        "volume_contraction": None,
        "breakout": {
            "volume_method": "ratio", "volume_ratio_threshold": 1.5,
            "volume_lookback_days": 50, "require_volume_confirmation": False,
        },
        "vol_filter": {"window": 3, "threshold": 1.5},
        "risk": {
            "trailing_stop_method": "atr", "trailing_atr_multiplier": 1.5,
            "trailing_atr_period": 14, "target_r_multiple": 5.0,
            "early_exit_days": None, "breakeven_r_multiple": 0.5,
            "max_stop_loss_pct": 0.07, "max_bars_without_progress": 15,
            "min_progress_r": 0.5,
            "trailing_sma_period": 20, "trailing_volume_factor": 1.5,
        },
    },
}


def generate_plots(ticker: str, split: str):
    config = CONFIGS[ticker]
    ohlc_full = pd.read_csv(DATA_DIR / f"{ticker}.csv", parse_dates=["date"], index_col="date")

    if split == "train":
        ohlc = ohlc_full[ohlc_full.index < TRAIN_CUTOFF]
    else:
        ohlc = ohlc_full[ohlc_full.index >= TRAIN_CUTOFF]

    detector = ATRZigZagDetector(config["swing"])
    results = run_full_vcp_pipeline(
        ohlc=ohlc,
        swing_detector=detector,
        sequence_params=config["sequence"],
        compression_params=config["compression"],
        breakout_params=config["breakout"],
        volume_contraction_params=config.get("volume_contraction"),
    )

    signals = {dt: sig for dt, sig in results.items() if sig is not None}

    vf = config.get("vol_filter")
    if vf:
        signals = apply_volume_post_filter(signals, ohlc, vf["window"], vf["threshold"])

    if not signals:
        print(f"  {ticker} {split}: 0 senales, sin graficos")
        return

    risk = dict(config["risk"])
    if split == "test" and "risk_test_override" in config:
        risk.update(config["risk_test_override"])

    trades_list = evaluate_signals_to_trades(
        signals, ohlc, risk, grouping="sequential",
    )

    if not trades_list:
        print(f"  {ticker} {split}: 0 trades, sin graficos")
        return

    out_dir = OUTPUT_DIR / ticker.lower() / split
    out_dir.mkdir(parents=True, exist_ok=True)

    n_trades = len(trades_list)
    wins = sum(1 for _, t in trades_list if t["pnl_pct"] > 0)
    cr = float(np.prod([1 + t["pnl_pct"] for _, t in trades_list]) - 1)
    print(f"  {ticker} {split}: {n_trades}T, {wins}W, CR={cr:+.2%}")

    for i, (pattern, trade) in enumerate(trades_list, 1):
        pnl = trade["pnl_pct"]
        exit_reason = trade["exit_reason"]
        r_mult = trade["r_multiple"]
        entry = pattern["first_signal_date"].strftime("%Y-%m-%d")
        exit_d = trade["exit_date"].strftime("%Y-%m-%d")

        plot_path = out_dir / f"trade_{i:02d}_{exit_reason}_{pnl:+.1%}.png"
        plot_vcp_trade_combined(
            ohlc, pattern, trade, pattern_number=i,
            risk_params=risk, ticker=ticker,
            margin_bars_before=40, margin_bars_after=10,
            save_path=plot_path,
        )

        print(f"    #{i} {entry} -> {exit_d} | {pnl:+.2%} ({r_mult:+.1f}R) {exit_reason}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("tickers", nargs="*", default=list(CONFIGS.keys()))
    parser.add_argument("--train", action="store_true")
    parser.add_argument("--test", action="store_true")
    args = parser.parse_args()

    splits = []
    if args.train:
        splits.append("train")
    if args.test:
        splits.append("test")
    if not splits:
        splits = ["train", "test"]

    for ticker in args.tickers:
        ticker = ticker.upper()
        if ticker not in CONFIGS:
            print(f"Ticker {ticker} no tiene config COMP#1. Disponibles: {list(CONFIGS.keys())}")
            continue
        for split in splits:
            generate_plots(ticker, split)

    print(f"\nGraficos guardados en {OUTPUT_DIR}/")


if __name__ == "__main__":
    main()
