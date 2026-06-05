"""Prueba: volume_confirmation_forward sobre las configs ganadoras v2 (train).

Para cada ticker usa la COMP#1 exacta del insight correspondiente.
Varia solo volume_confirmation_forward: 0 (baseline), 1, 2, 3, 5.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from models.configs import ATRZigZagConfig
from vcp_detection.heuristic import ATRZigZagDetector, run_full_vcp_pipeline
from vcp_detection.analysis import evaluate_signals_to_trades

DATA_DIR = project_root / "data" / "csv"
TRAIN_CUTOFF = pd.Timestamp("2020-01-01")
FORWARD_VALUES = [0, 1, 2, 3, 5]

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
    },
}


def load_data(ticker: str, split: str = "train") -> pd.DataFrame:
    ohlc = pd.read_csv(DATA_DIR / f"{ticker}.csv", parse_dates=["date"], index_col="date")
    if split == "train":
        return ohlc[ohlc.index < TRAIN_CUTOFF]
    return ohlc[ohlc.index >= TRAIN_CUTOFF]


def run_one(ticker: str, config: dict, forward: int, split: str = "train") -> dict:
    ohlc = load_data(ticker, split)
    detector = ATRZigZagDetector(config["swing"])

    breakout_params = dict(config["breakout"])
    breakout_params["volume_confirmation_forward"] = forward

    results = run_full_vcp_pipeline(
        ohlc=ohlc,
        swing_detector=detector,
        sequence_params=config["sequence"],
        compression_params=config["compression"],
        breakout_params=breakout_params,
        volume_contraction_params=config.get("volume_contraction"),
    )

    signals = {dt: sig for dt, sig in results.items() if sig is not None}
    n_signals = len(signals)
    fwd_count = sum(
        1 for sig in signals.values()
        if sig.volume_confirmation.get("forward_confirmed", False)
    )

    if not signals:
        return {"signals": 0, "trades": 0, "wins": 0, "wr": 0.0,
                "cr": 0.0, "avg_r": 0.0, "fwd_conf": 0}

    trades_list = evaluate_signals_to_trades(
        signals, ohlc, config["risk"], grouping="sequential",
    )
    n_trades = len(trades_list)
    if n_trades == 0:
        return {"signals": n_signals, "trades": 0, "wins": 0, "wr": 0.0,
                "cr": 0.0, "avg_r": 0.0, "fwd_conf": fwd_count}

    wins = sum(1 for _, t in trades_list if t["pnl_pct"] > 0)
    cr = float(np.prod([1 + t["pnl_pct"] for _, t in trades_list]) - 1)
    avg_r = float(np.mean([t["r_multiple"] for _, t in trades_list]))

    return {
        "signals": n_signals, "trades": n_trades, "wins": wins,
        "wr": wins / n_trades, "cr": cr, "avg_r": avg_r,
        "fwd_conf": fwd_count,
    }


def run_split(split: str):
    label = "TRAIN 2015-2019" if split == "train" else "TEST 2020-2026"
    print(f"\n{'=' * 85}")
    print(f"volume_confirmation_forward — configs COMP#1 v2 ({label})")
    print(f"{'=' * 85}")

    for ticker, config in CONFIGS.items():
        vol_info = config["breakout"].get("volume_confirmation_window", 1)
        req = config["breakout"].get("require_volume_confirmation", True)
        thr = config["breakout"].get("volume_ratio_threshold", 1.5)
        vol_label = f"vol={'off' if not req else f'w{vol_info}_t{thr}'}"
        print(f"\n--- {ticker} (COMP#1, {vol_label}) ---")
        print(f"{'fwd':>5} | {'Signals':>7} | {'Trades':>6} | {'WR':>6} | "
              f"{'CR':>10} | {'avg_R':>7} | {'fwd_conf':>8}")
        print("-" * 65)

        for fwd in FORWARD_VALUES:
            r = run_one(ticker, config, fwd, split)
            fwd_info = str(r["fwd_conf"]) if r["fwd_conf"] > 0 else "-"
            print(f"{fwd:>5} | {r['signals']:>7} | {r['trades']:>6} | "
                  f"{r['wr']:>5.0%} | {r['cr']:>+9.2%} | "
                  f"{r['avg_r']:>+6.2f} | {fwd_info:>8}")


def main():
    run_split("train")
    run_split("test")


if __name__ == "__main__":
    main()
