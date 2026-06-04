"""Evaluate top AMZN train configs on test data (2020-2026)."""
import functools
import sys
import time
from pathlib import Path

print = functools.partial(print, flush=True)

import numpy as np
import pandas as pd

project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from models.configs import ATRZigZagConfig
from vcp_detection.heuristic import ATRZigZagDetector, run_full_vcp_pipeline
from vcp_detection.heuristic.contractions import compute_contractions
from vcp_detection.heuristic.atr_compression import compute_atr
from vcp_detection.analysis import evaluate_signals_to_trades
from stages.trend_template import evaluate_trend_template

DATA_DIR = project_root / "data" / "csv"
TRAIN_CUTOFF = "2020-01-01"

RISK_BASE = {
    "trailing_sma_period": 20,
    "trailing_volume_factor": 1.5,
    "trailing_stop_method": "atr",
    "trailing_atr_period": 14,
    "max_bars_without_progress": 15,
    "min_progress_r": 0.5,
}

BREAKOUT_BASE = {
    "volume_method": "ratio", "volume_ratio_threshold": 1.5,
    "volume_lookback_days": 50,
    "require_volume_confirmation": False,
}

TOP_CONFIGS = [
    {
        "name": "COMP#1 (w3_t1.2, red=0.60, VC=Y)",
        "detection": {
            "atr_mult": 3.0, "use_close_only": False,
            "max_depth_atr": None, "min_total_reduction": 0.60,
            "lookback_bars": 126, "compression_threshold": 0.90,
            "tolerance": 0.15, "max_depth_pct": 0.30, "ascending_lows_tolerance": 0.01,
            "trend_template": False,
            "volume_contraction": {"method": "ratio", "ratio_threshold": 0.85},
            "vol_filter": "w3_t1.2",
        },
        "exit": {
            "trailing_atr_multiplier": 2.0, "target_r_multiple": None,
            "early_exit_days": None, "breakeven_r_multiple": 1.5,
            "max_stop_loss_pct": 0.03,
        },
    },
    {
        "name": "COMP#2 (w5_t1.2, red=0.60, VC=Y)",
        "detection": {
            "atr_mult": 3.0, "use_close_only": False,
            "max_depth_atr": None, "min_total_reduction": 0.60,
            "lookback_bars": 126, "compression_threshold": 0.90,
            "tolerance": 0.15, "max_depth_pct": 0.30, "ascending_lows_tolerance": 0.01,
            "trend_template": False,
            "volume_contraction": {"method": "ratio", "ratio_threshold": 0.85},
            "vol_filter": "w5_t1.2",
        },
        "exit": {
            "trailing_atr_multiplier": 2.0, "target_r_multiple": None,
            "early_exit_days": None, "breakeven_r_multiple": 1.5,
            "max_stop_loss_pct": 0.03,
        },
    },
    {
        "name": "COMP#3 (w5_t1.2, red=0.80, VC=Y)",
        "detection": {
            "atr_mult": 3.0, "use_close_only": False,
            "max_depth_atr": None, "min_total_reduction": 0.80,
            "lookback_bars": 126, "compression_threshold": 0.90,
            "tolerance": 0.15, "max_depth_pct": 0.30, "ascending_lows_tolerance": 0.01,
            "trend_template": False,
            "volume_contraction": {"method": "ratio", "ratio_threshold": 0.85},
            "vol_filter": "w5_t1.2",
        },
        "exit": {
            "trailing_atr_multiplier": 2.0, "target_r_multiple": None,
            "early_exit_days": None, "breakeven_r_multiple": 1.5,
            "max_stop_loss_pct": 0.03,
        },
    },
    {
        "name": "CR#1 (no_filter, atr=2.0, Close, VC=N)",
        "detection": {
            "atr_mult": 2.0, "use_close_only": True,
            "max_depth_atr": 8, "min_total_reduction": 0.80,
            "lookback_bars": 126, "compression_threshold": 0.95,
            "tolerance": 0.10, "max_depth_pct": 0.30, "ascending_lows_tolerance": 0.03,
            "trend_template": False,
            "volume_contraction": None,
            "vol_filter": "no_filter",
        },
        "exit": {
            "trailing_atr_multiplier": 2.0, "target_r_multiple": 3.0,
            "early_exit_days": 5, "breakeven_r_multiple": 1.0,
            "max_stop_loss_pct": 0.05,
        },
    },
    {
        "name": "ALT#1 (no_filter, atr=3.0, HL, VC=N, trail=2.0 tg=5R)",
        "detection": {
            "atr_mult": 3.0, "use_close_only": False,
            "max_depth_atr": None, "min_total_reduction": 0.80,
            "lookback_bars": 126, "compression_threshold": 0.90,
            "tolerance": 0.15, "max_depth_pct": 0.30, "ascending_lows_tolerance": 0.01,
            "trend_template": False,
            "volume_contraction": None,
            "vol_filter": "no_filter",
        },
        "exit": {
            "trailing_atr_multiplier": 2.0, "target_r_multiple": 5.0,
            "early_exit_days": 5, "breakeven_r_multiple": 1.0,
            "max_stop_loss_pct": 0.05,
        },
    },
    {
        "name": "ALT#2 (no_filter, atr=3.0, HL, VC=Y, trail=2.0 tg=None)",
        "detection": {
            "atr_mult": 3.0, "use_close_only": False,
            "max_depth_atr": None, "min_total_reduction": 0.80,
            "lookback_bars": 126, "compression_threshold": 0.90,
            "tolerance": 0.15, "max_depth_pct": 0.30, "ascending_lows_tolerance": 0.01,
            "trend_template": False,
            "volume_contraction": {"method": "ratio", "ratio_threshold": 0.85},
            "vol_filter": "no_filter",
        },
        "exit": {
            "trailing_atr_multiplier": 2.0, "target_r_multiple": None,
            "early_exit_days": None, "breakeven_r_multiple": 1.5,
            "max_stop_loss_pct": 0.03,
        },
    },
    {
        "name": "ALT#3 (no_filter, atr=3.0, HL, VC=N, trail=2.0 tg=None)",
        "detection": {
            "atr_mult": 3.0, "use_close_only": False,
            "max_depth_atr": None, "min_total_reduction": 0.80,
            "lookback_bars": 126, "compression_threshold": 0.90,
            "tolerance": 0.15, "max_depth_pct": 0.30, "ascending_lows_tolerance": 0.01,
            "trend_template": False,
            "volume_contraction": None,
            "vol_filter": "no_filter",
        },
        "exit": {
            "trailing_atr_multiplier": 2.0, "target_r_multiple": None,
            "early_exit_days": None, "breakeven_r_multiple": 1.5,
            "max_stop_loss_pct": 0.03,
        },
    },
    {
        "name": "ALT#4 (no_filter, atr=2.0, Close, VC=N, trail=2.0 tg=None)",
        "detection": {
            "atr_mult": 2.0, "use_close_only": True,
            "max_depth_atr": 8, "min_total_reduction": 0.80,
            "lookback_bars": 126, "compression_threshold": 0.95,
            "tolerance": 0.10, "max_depth_pct": 0.30, "ascending_lows_tolerance": 0.03,
            "trend_template": False,
            "volume_contraction": None,
            "vol_filter": "no_filter",
        },
        "exit": {
            "trailing_atr_multiplier": 2.0, "target_r_multiple": None,
            "early_exit_days": None, "breakeven_r_multiple": 1.5,
            "max_stop_loss_pct": 0.03,
        },
    },
]

VOL_FILTERS = {
    "no_filter": {"window": None, "threshold": None},
    "w1_t1.2": {"window": 1, "threshold": 1.2},
    "w1_t1.5": {"window": 1, "threshold": 1.5},
    "w3_t1.2": {"window": 3, "threshold": 1.2},
    "w3_t1.5": {"window": 3, "threshold": 1.5},
    "w5_t1.2": {"window": 5, "threshold": 1.2},
    "w5_t1.5": {"window": 5, "threshold": 1.5},
}


def apply_volume_post_filter(signals, ohlc, window, threshold, lookback_days=50):
    filtered = {}
    for dt, sig in signals.items():
        eval_loc = ohlc.index.get_loc(dt)
        lookback_start = max(0, eval_loc - lookback_days)
        vol_recent = ohlc["volume"].iloc[lookback_start:eval_loc]
        vol_avg = float(vol_recent.mean()) if len(vol_recent) > 0 else 0.0
        if vol_avg <= 0:
            continue
        win_start = max(0, eval_loc - window + 1)
        win_vols = ohlc["volume"].iloc[win_start:eval_loc + 1]
        if any(float(v) >= threshold * vol_avg for v in win_vols):
            filtered[dt] = sig
    return filtered


def evaluate_signals_seq(ohlc, signals, risk, precomputed_atr=None):
    results = evaluate_signals_to_trades(
        signals, ohlc, risk, grouping="sequential",
        precomputed_atr=precomputed_atr,
    )
    n = len(results)
    trades_list = [t for _, t in results]
    wins = sum(1 for t in trades_list if t["pnl_pct"] > 0) if n else 0
    cr = float(np.prod([1 + t["pnl_pct"] for t in trades_list]) - 1) if n else 0
    avg_r = float(np.mean([t["r_multiple"] for t in trades_list])) if n else 0
    reasons = {}
    for t in trades_list:
        reasons[t["exit_reason"]] = reasons.get(t["exit_reason"], 0) + 1

    max_dd = 0.0
    equity = 1.0
    peak = 1.0
    for t in trades_list:
        equity *= (1 + t["pnl_pct"])
        peak = max(peak, equity)
        dd = (equity - peak) / peak
        max_dd = min(max_dd, dd)

    pf_wins = sum(t["pnl_pct"] for t in trades_list if t["pnl_pct"] > 0)
    pf_loss = abs(sum(t["pnl_pct"] for t in trades_list if t["pnl_pct"] <= 0))
    pf = pf_wins / pf_loss if pf_loss > 0 else float('inf')

    return {"trades": n, "wins": wins, "WR": wins / n if n > 0 else 0,
            "CR": cr, "avg_R": avg_r, "reasons": reasons,
            "trade_details": results, "max_dd": max_dd, "profit_factor": pf}


def run_config_on_data(ohlc, cfg, tt_mask):
    det = cfg["detection"]
    config = ATRZigZagConfig(atr_length=14, atr_mult=det["atr_mult"],
                              use_close_only=det["use_close_only"])
    detector = ATRZigZagDetector(config)
    swings = detector.detect(ohlc)
    contractions = compute_contractions(swings, ohlc)
    atr = compute_atr(ohlc, 14)

    seq_params = {
        "method": "tolerance", "min_contractions": 2, "max_contractions": 6,
        "lookback_bars": det["lookback_bars"], "tolerance": det["tolerance"],
        "max_depth_pct": det["max_depth_pct"], "max_depth_atr": det["max_depth_atr"],
        "min_total_reduction": det["min_total_reduction"],
        "max_gap_between_contractions_days": None,
        "require_ascending_lows": True,
        "ascending_lows_tolerance": det["ascending_lows_tolerance"],
    }
    comp_params = {"method": "ratio", "atr_period": 14,
                   "ratio_threshold": det["compression_threshold"]}

    res = run_full_vcp_pipeline(
        ohlc=ohlc, swing_detector=detector,
        sequence_params=seq_params, compression_params=comp_params,
        breakout_params=BREAKOUT_BASE,
        volume_contraction_params=det["volume_contraction"],
        precomputed_swings=swings, precomputed_contractions=contractions,
        precomputed_atr=atr,
    )
    raw_signals = {dt: s for dt, s in res.items() if s is not None}

    if det["trend_template"]:
        raw_signals = {dt: s for dt, s in raw_signals.items()
                       if dt in tt_mask.index and tt_mask.loc[dt]}

    vf = VOL_FILTERS[det["vol_filter"]]
    if vf["window"] is not None:
        filtered = apply_volume_post_filter(raw_signals, ohlc, vf["window"], vf["threshold"])
    else:
        filtered = raw_signals

    risk = {**RISK_BASE, **cfg["exit"]}
    ev = evaluate_signals_seq(ohlc, filtered, risk, precomputed_atr=atr)
    return ev


def compute_buy_and_hold(ohlc):
    first_close = ohlc["close"].iloc[0]
    last_close = ohlc["close"].iloc[-1]
    cr = (last_close / first_close) - 1
    years = len(ohlc) / 252
    cagr = (1 + cr) ** (1 / years) - 1 if years > 0 else 0

    peak = ohlc["close"].cummax()
    dd = (ohlc["close"] - peak) / peak
    max_dd = dd.min()

    daily_ret = ohlc["close"].pct_change().dropna()
    sharpe = (daily_ret.mean() / daily_ret.std()) * np.sqrt(252) if daily_ret.std() > 0 else 0

    return {"CR": cr, "CAGR": cagr, "MaxDD": max_dd, "Sharpe": sharpe}


if __name__ == "__main__":
    print("=" * 70)
    print("  AMZN — Evaluacion en TEST (2020-2026)")
    print("=" * 70)

    daily = pd.read_csv(DATA_DIR / "AMZN.csv", parse_dates=["date"], index_col="date")
    train = daily[daily.index < TRAIN_CUTOFF]
    test = daily[daily.index >= TRAIN_CUTOFF]
    print(f"  TRAIN: {len(train):,} barras ({train.index.min().date()} a {train.index[-1].date()})")
    print(f"  TEST:  {len(test):,} barras ({test.index[0].date()} a {test.index[-1].date()})")

    tt_train_df = evaluate_trend_template(train)
    tt_mask_train = tt_train_df["trend_template"]
    tt_test_df = evaluate_trend_template(test)
    tt_mask_test = tt_test_df["trend_template"]
    print(f"  Stage 2 en train: {tt_mask_train.sum()}/{len(tt_mask_train)} dias")
    print(f"  Stage 2 en test:  {tt_mask_test.sum()}/{len(tt_mask_test)} dias")

    bh_train = compute_buy_and_hold(train)
    bh_test = compute_buy_and_hold(test)
    print(f"\n  Buy & Hold TRAIN: CR={bh_train['CR']:+.2%}, CAGR={bh_train['CAGR']:.2%}, "
          f"MaxDD={bh_train['MaxDD']:.2%}, Sharpe={bh_train['Sharpe']:.2f}")
    print(f"  Buy & Hold TEST:  CR={bh_test['CR']:+.2%}, CAGR={bh_test['CAGR']:.2%}, "
          f"MaxDD={bh_test['MaxDD']:.2%}, Sharpe={bh_test['Sharpe']:.2f}")

    for cfg in TOP_CONFIGS:
        print(f"\n{'─' * 70}")
        print(f"  {cfg['name']}")
        print(f"{'─' * 70}")

        for label, data, tt_mask in [("TRAIN", train, tt_mask_train),
                                      ("TEST", test, tt_mask_test)]:
            t0 = time.time()
            ev = run_config_on_data(data, cfg, tt_mask)
            elapsed = time.time() - t0

            years = len(data) / 252
            cagr = (1 + ev["CR"]) ** (1 / years) - 1 if years > 0 and ev["CR"] > -1 else 0
            exposure = sum(t["duration_days"] for _, t in ev["trade_details"]) / len(data) if ev["trades"] > 0 else 0

            daily_returns = []
            for _, trade in ev["trade_details"]:
                daily_returns.append(trade["pnl_pct"] / max(trade["duration_days"], 1))
            if daily_returns:
                sharpe_approx = (np.mean(daily_returns) / np.std(daily_returns)) * np.sqrt(252) if np.std(daily_returns) > 0 else 0
            else:
                sharpe_approx = 0

            print(f"\n  {label}: {ev['trades']}T, {ev['wins']}W, {ev['trades']-ev['wins']}L, "
                  f"WR={ev['WR']:.0%}, CR={ev['CR']:+.2%}, CAGR={cagr:.2%}, "
                  f"MaxDD={ev['max_dd']:.2%}, avgR={ev['avg_R']:+.2f}, "
                  f"PF={ev['profit_factor']:.1f}, Exp={exposure:.0%} ({elapsed:.1f}s)")

            reasons_str = ", ".join(f"{k}={v}" for k, v in sorted(ev["reasons"].items()))
            print(f"    Salidas: {reasons_str}")

            if ev["trade_details"]:
                for j, (pat, trade) in enumerate(ev["trade_details"], 1):
                    entry_str = pat["first_signal_date"].strftime("%Y-%m-%d")
                    exit_str = trade["exit_date"].strftime("%Y-%m-%d")
                    print(f"    {j:>2d}: {entry_str} -> {exit_str} | "
                          f"{trade['exit_reason']:<15s} | "
                          f"PnL={trade['pnl_pct']:+.2%} | R={trade['r_multiple']:+.1f}R | "
                          f"MaxR={trade['max_r']:.1f}R | Dur={trade['duration_days']}d")

    print(f"\n{'=' * 70}")
    print("  COMPLETO")
    print(f"{'=' * 70}")
