"""Analyze the 66 TEST trades: how many unique patterns, and visualize each."""
import functools
import sys
from pathlib import Path

print = functools.partial(print, flush=True)

import matplotlib
matplotlib.use("Agg")
import numpy as np
import pandas as pd

project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from models.configs import ATRZigZagConfig
from vcp_detection.heuristic import ATRZigZagDetector, run_full_vcp_pipeline
from vcp_detection.heuristic.contractions import compute_contractions
from vcp_detection.heuristic.atr_compression import compute_atr
from vcp_detection.analysis import evaluate_signals_to_trades, plot_vcp_pattern, plot_trade_simulation

TICKER = "EURUSD"
DATA_DIR = project_root / "data" / "monedas_hora"
OUTPUT_DIR = Path(__file__).parent / "pattern_charts"
OUTPUT_DIR.mkdir(exist_ok=True)

ohlc = pd.read_csv(DATA_DIR / f"{TICKER}.csv", parse_dates=["date"], index_col="date")
test = ohlc["2019-01-01":"2027-01-01"]

print(f"TEST: {len(test):,} barras")

# Best detection config from experiment (the one that selects 0 signals in TRAIN
# but generates signals in TEST — using most permissive config that has trades)
# Use atr_mult=5, comp=0.85, red=0.40, lb=240 — this had 0 signals in TRAIN.
# Actually let's use the config that generates the most trades to analyze patterns.
# From the sensitivity analysis: atr_mult=5, comp=0.95, red=0.80, lb=960 gives most signals.
# Let's use a config that actually generates a reasonable number: atr=5, comp=0.95, red=0.40, lb=240
ATR_MULT = 5
config = ATRZigZagConfig(atr_length=14, atr_mult=ATR_MULT, use_close_only=False)
detector = ATRZigZagDetector(config)
swings = detector.detect(test)
contractions = compute_contractions(swings, test)
atr = compute_atr(test, 14)

seq_params = {
    "method": "tolerance", "min_contractions": 2, "max_contractions": 6,
    "lookback_bars": 240, "tolerance": 0.10,
    "max_depth_pct": 0.50, "max_depth_atr": None,
    "min_total_reduction": 0.40,
    "max_gap_between_contractions_days": None,
    "require_ascending_lows": True,
    "ascending_lows_tolerance": 0.03,
}
comp_params = {"method": "ratio", "atr_period": 14, "ratio_threshold": 0.85}
breakout_params = {
    "volume_method": "ratio", "volume_ratio_threshold": 1.5,
    "volume_lookback_days": 50, "require_volume_confirmation": False,
}

print("Running pipeline...")
res = run_full_vcp_pipeline(
    ohlc=test, swing_detector=detector,
    sequence_params=seq_params,
    compression_params=comp_params,
    breakout_params=breakout_params,
    volume_contraction_params=None,
    precomputed_swings=swings,
    precomputed_contractions=contractions,
    precomputed_atr=atr,
)
signals = {dt: s for dt, s in res.items() if s is not None}
print(f"Signals: {len(signals)}")

risk_params = {
    "trailing_sma_period": 20,
    "trailing_volume_factor": 1.5,
    "trailing_stop_method": "atr",
    "trailing_atr_period": 14,
    "min_progress_r": 0.5,
    "early_exit_days": None,
    "max_stop_loss_pct": 0.01,
    "max_bars_without_progress": 10,
    "trailing_atr_multiplier": 1.0,
    "target_r_multiple": None,
    "breakeven_r_multiple": 0.5,
}

results = evaluate_signals_to_trades(
    signals, test, risk_params, grouping="sequential", precomputed_atr=atr,
)
print(f"Trades: {len(results)}")

# Analyze unique patterns
print(f"\n{'='*80}")
print("ANALISIS DE PATRONES UNICOS")
print(f"{'='*80}")

patterns_seen = {}
for i, (pat, trade) in enumerate(results, 1):
    sig = pat["signal_obj"]
    seq = sig.pivot_info.sequence
    # Identify pattern by its contractions (high/low dates)
    key = tuple((c.high_swing.date, c.low_swing.date) for c in seq.contractions)

    if key not in patterns_seen:
        patterns_seen[key] = {
            "first_trade": i,
            "trades": [],
            "pattern": pat,
            "sequence": seq,
        }
    patterns_seen[key]["trades"].append((i, pat, trade))

print(f"\n{len(results)} trades provienen de {len(patterns_seen)} patrones unicos\n")

for pat_idx, (key, info) in enumerate(patterns_seen.items(), 1):
    seq = info["sequence"]
    trades = info["trades"]
    depths = [f"{c.depth_pct:.4f}%" for c in seq.contractions]

    total_pnl = sum(t[2]["pnl_pct"] for t in trades)
    wins = sum(1 for t in trades if t[2]["pnl_pct"] > 0)

    first_date = trades[0][1]["first_signal_date"]
    last_exit = trades[-1][2]["exit_date"]

    print(f"Patron {pat_idx}: {len(seq.contractions)} contracciones, depths={depths}")
    print(f"  Periodo: {first_date} -> {last_exit}")
    print(f"  Trades: {len(trades)} | Wins: {wins}/{len(trades)} | Total PnL: {total_pnl:+.2%}")

    for trade_num, pat_d, trade_d in trades:
        print(f"    T{trade_num}: {pat_d['first_signal_date'].strftime('%Y-%m-%d %H:%M')} -> "
              f"{trade_d['exit_date'].strftime('%Y-%m-%d %H:%M')} | "
              f"{trade_d['exit_reason']:<15s} | PnL={trade_d['pnl_pct']:+.2%} | "
              f"R={trade_d['r_multiple']:+.1f}R")
    print()

# Generate charts for each unique pattern
print(f"\nGenerando graficos en {OUTPUT_DIR}/...")

for pat_idx, (key, info) in enumerate(patterns_seen.items(), 1):
    pat = info["pattern"]
    first_trade = info["trades"][0]

    try:
        fig = plot_vcp_pattern(
            ohlc=test, pattern=pat, pattern_number=pat_idx,
            ticker=f"{TICKER} (hourly)", margin_bars_before=80, margin_bars_after=60,
            save_path=OUTPUT_DIR / f"pattern_{pat_idx:02d}_vcp.png",
        )
        print(f"  pattern_{pat_idx:02d}_vcp.png OK")
    except Exception as e:
        print(f"  pattern_{pat_idx:02d}_vcp.png ERROR: {e}")

    # Also plot the first trade for this pattern
    try:
        fig = plot_trade_simulation(
            ohlc=test, pattern=first_trade[1], trade=first_trade[2],
            trade_number=first_trade[0], ticker=f"{TICKER} (hourly)",
            save_path=OUTPUT_DIR / f"pattern_{pat_idx:02d}_trade.png",
        )
        print(f"  pattern_{pat_idx:02d}_trade.png OK")
    except Exception as e:
        print(f"  pattern_{pat_idx:02d}_trade.png ERROR: {e}")

print(f"\nCompleto! {len(patterns_seen)} patrones graficados en {OUTPUT_DIR}/")
