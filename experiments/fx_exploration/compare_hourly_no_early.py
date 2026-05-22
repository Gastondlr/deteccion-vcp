"""Config B (atr_mult=2.5, d=4, r=0.8, lb=72) without early_exit."""
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from models.configs import ATRZigZagConfig
from vcp_detection.heuristic import ATRZigZagDetector, run_full_vcp_pipeline
from vcp_detection.heuristic.contractions import compute_contractions
from vcp_detection.heuristic.atr_compression import compute_atr
from vcp_detection.analysis import group_signals_into_patterns, simulate_trade

P = lambda *a, **kw: print(*a, **kw, flush=True)

ATR_LENGTH = 14
CUTOFF = "2020-01-01"
MAX_HOLD_BARS = 360

COMPRESSION = {"method": "ratio", "atr_period": ATR_LENGTH, "ratio_threshold": 0.85}
BREAKOUT = {
    "volume_method": "ratio", "volume_ratio_threshold": 1.5,
    "volume_lookback_days": 50,
    "require_volume_confirmation": False,
}
RISK_BASE = {
    "max_stop_loss_pct": 0.01,
    "trailing_sma_period": 20,
    "trailing_volume_factor": 1.5,
    "trailing_stop_method": "atr",
    "trailing_atr_period": ATR_LENGTH,
    "max_bars_without_progress": 48,
    "min_progress_r": 0.5,
}

TRAILING_MULTS = [1.0, 1.5, 2.0, 2.5, 3.0]
TARGET_RS = [None, 1.5, 2.0, 3.0]
BREAKEVEN_RS = [0.5, 1.0, 1.5, 2.0]

DATA_DIR = project_root / "data" / "monedas_hora"


def precompute(ohlc, atr_mult):
    config = ATRZigZagConfig(atr_length=ATR_LENGTH, atr_mult=atr_mult, use_close_only=False)
    detector = ATRZigZagDetector(config)
    swings = detector.detect(ohlc)
    contractions = compute_contractions(swings, ohlc)
    atr = compute_atr(ohlc, COMPRESSION["atr_period"])
    return {"ohlc": ohlc, "swings": swings, "contractions": contractions,
            "atr": atr, "detector": detector}


def make_seq_params(depth_atr, reduction, lookback_bars):
    return {
        "method": "tolerance", "min_contractions": 2, "max_contractions": 6,
        "lookback_bars": lookback_bars, "tolerance": 0.10,
        "max_depth_pct": 0.50, "max_depth_atr": depth_atr,
        "min_total_reduction": reduction,
        "max_gap_between_contractions_days": None,
        "require_ascending_lows": True, "ascending_lows_tolerance": 0.03,
    }


def detect_signals(ohlc, seq_params, cache_entry):
    res = run_full_vcp_pipeline(
        ohlc=ohlc, swing_detector=cache_entry["detector"],
        sequence_params=seq_params,
        compression_params=COMPRESSION,
        breakout_params=BREAKOUT,
        volume_contraction_params=None,
        precomputed_swings=cache_entry["swings"],
        precomputed_contractions=cache_entry["contractions"],
        precomputed_atr=cache_entry["atr"],
    )
    return {dt: s for dt, s in res.items() if s is not None}


def evaluate_signals(ohlc, signals, risk):
    patterns = group_signals_into_patterns(signals, risk_params=risk)
    trades = [simulate_trade(ohlc, p, risk, max_hold_days=MAX_HOLD_BARS) for p in patterns]
    n = len(trades)
    wins = sum(1 for t in trades if t["pnl_pct"] > 0) if n else 0
    cr = float(np.prod([1 + t["pnl_pct"] for t in trades]) - 1) if n else 0
    avg_r = float(np.mean([t["r_multiple"] for t in trades])) if n else 0
    reasons = {}
    for t in trades:
        reasons[t["exit_reason"]] = reasons.get(t["exit_reason"], 0) + 1
    return {"trades": n, "wins": wins, "WR": wins / n if n > 0 else 0,
            "CR": cr, "avg_R": avg_r, "reasons": reasons,
            "trade_details": [(p, t) for p, t in zip(patterns, trades)]}


def fmt_pct(x): return f"{x:+.2%}"
def fmt_wr(x): return f"{x:.0%}"


if __name__ == "__main__":
    P("Cargando EURUSD hourly...")
    hourly = pd.read_csv(DATA_DIR / "EURUSD.csv", parse_dates=["date"], index_col="date")
    train = hourly[hourly.index < CUTOFF]
    test = hourly[hourly.index >= CUTOFF]
    P(f"TRAIN: {len(train):,} barras | TEST: {len(test):,} barras")

    cfg = {"atr_mult": 2.5, "depth_atr": 4, "reduction": 0.80, "lookback_bars": 72}

    P(f"\nConfig B sin early_exit: atr_mult={cfg['atr_mult']}, d={cfg['depth_atr']}, "
      f"r={cfg['reduction']}, lb={cfg['lookback_bars']}")

    t0 = time.time()
    cache_train = precompute(train, cfg["atr_mult"])
    seq = make_seq_params(cfg["depth_atr"], cfg["reduction"], cfg["lookback_bars"])
    signals_train = detect_signals(train, seq, cache_train)
    P(f"Senales TRAIN: {len(signals_train)} ({time.time()-t0:.1f}s)")

    cache_test = precompute(test, cfg["atr_mult"])
    signals_test = detect_signals(test, seq, cache_test)
    P(f"Senales TEST:  {len(signals_test)}")

    results = []
    t0 = time.time()
    for trail in TRAILING_MULTS:
        for target in TARGET_RS:
            for be_r in BREAKEVEN_RS:
                risk = {**RISK_BASE, "trailing_atr_multiplier": trail,
                        "target_r_multiple": target, "early_exit_days": None,
                        "breakeven_r_multiple": be_r}
                ev_train = evaluate_signals(train, signals_train, risk)
                ev_test = evaluate_signals(test, signals_test, risk)
                results.append({
                    "trailing": trail, "target": target, "be_R": be_r,
                    "train_trades": ev_train["trades"], "train_WR": ev_train["WR"],
                    "train_CR": ev_train["CR"], "train_avgR": ev_train["avg_R"],
                    "test_trades": ev_test["trades"], "test_WR": ev_test["WR"],
                    "test_CR": ev_test["CR"], "test_avgR": ev_test["avg_R"],
                })

    P(f"\n80 exit configs en {time.time()-t0:.1f}s")

    df = pd.DataFrame(results).sort_values("train_CR", ascending=False)

    P(f"\nTop 15 configs (ordenadas por TRAIN CR):")
    P(f"  {'trail':>5s} {'target':>6s} {'be_R':>4s} | "
      f"{'T_trades':>8s} {'T_WR':>5s} {'T_CR':>8s} {'T_avgR':>7s} | "
      f"{'S_trades':>8s} {'S_WR':>5s} {'S_CR':>8s} {'S_avgR':>7s}")
    P(f"  {'─'*85}")
    for _, row in df.head(15).iterrows():
        t_r = f"{row['target']:.1f}" if pd.notna(row['target']) else 'None'
        P(f"  {row['trailing']:>5.1f} {t_r:>6s} {row['be_R']:>4.1f} | "
          f"{int(row['train_trades']):>8d} {fmt_wr(row['train_WR']):>5s} "
          f"{fmt_pct(row['train_CR']):>8s} {row['train_avgR']:>+7.2f} | "
          f"{int(row['test_trades']):>8d} {fmt_wr(row['test_WR']):>5s} "
          f"{fmt_pct(row['test_CR']):>8s} {row['test_avgR']:>+7.2f}")

    best = df.iloc[0]
    P(f"\n>>> MEJOR (TRAIN): trail={best['trailing']}, "
      f"target={best['target'] if pd.notna(best['target']) else 'None'}, "
      f"be_R={best['be_R']}")
    P(f"    TRAIN: {int(best['train_trades'])}T, WR={fmt_wr(best['train_WR'])}, "
      f"CR={fmt_pct(best['train_CR'])}, avgR={best['train_avgR']:+.2f}")
    P(f"    TEST:  {int(best['test_trades'])}T, WR={fmt_wr(best['test_WR'])}, "
      f"CR={fmt_pct(best['test_CR'])}, avgR={best['test_avgR']:+.2f}")

    t_r_val = best["target"] if pd.notna(best["target"]) else None
    risk_best = {**RISK_BASE, "trailing_atr_multiplier": best["trailing"],
                 "target_r_multiple": t_r_val, "early_exit_days": None,
                 "breakeven_r_multiple": best["be_R"]}

    P(f"\n--- Detalle trades TRAIN ---")
    ev = evaluate_signals(train, signals_train, risk_best)
    reasons_str = ", ".join(f"{k}={v}" for k, v in sorted(ev["reasons"].items()))
    P(f"    Salidas: {reasons_str}")
    for i, (pat, trade) in enumerate(ev["trade_details"], 1):
        P(f"  Trade {i}: {pat['first_signal_date'].strftime('%Y-%m-%d %H:%M')} -> "
          f"{trade['exit_date'].strftime('%Y-%m-%d %H:%M')} | {trade['exit_reason']:<15s} | "
          f"PnL={trade['pnl_pct']:+.2%} | R={trade['r_multiple']:+.1f}R | Dur={trade['duration_days']}d")

    P(f"\n--- Detalle trades TEST ---")
    ev_t = evaluate_signals(test, signals_test, risk_best)
    reasons_str = ", ".join(f"{k}={v}" for k, v in sorted(ev_t["reasons"].items()))
    P(f"    Salidas: {reasons_str}")
    for i, (pat, trade) in enumerate(ev_t["trade_details"], 1):
        P(f"  Trade {i}: {pat['first_signal_date'].strftime('%Y-%m-%d %H:%M')} -> "
          f"{trade['exit_date'].strftime('%Y-%m-%d %H:%M')} | {trade['exit_reason']:<15s} | "
          f"PnL={trade['pnl_pct']:+.2%} | R={trade['r_multiple']:+.1f}R | Dur={trade['duration_days']}d")

    P("\nCompleto!")
