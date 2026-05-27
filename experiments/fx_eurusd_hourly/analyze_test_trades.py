"""Analyze 139 TEST trades from Experiment 4 to understand TRAIN->TEST collapse.

TRAIN: 21 trades, WR=71%, CR=+4.95%
TEST:  139 trades, WR=37%, CR=-6.89%

Best config: atr_mult=3, red=0.80, lb=72, comp=0.95,
             trail=3.0, target=3.0R, be_R=1.0, sl=0.01, bars=24
"""
import functools
import sys
from pathlib import Path

print = functools.partial(print, flush=True)

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np
import pandas as pd

project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from models.configs import ATRZigZagConfig
from vcp_detection.heuristic import ATRZigZagDetector, run_full_vcp_pipeline
from vcp_detection.heuristic.contractions import compute_contractions
from vcp_detection.heuristic.atr_compression import compute_atr
from vcp_detection.analysis import evaluate_signals_to_trades

OUTPUT_DIR = Path(__file__).parent / "test_analysis"
OUTPUT_DIR.mkdir(exist_ok=True)

TICKER = "EURUSD"
DATA_DIR = project_root / "data" / "monedas_hora"
ohlc = pd.read_csv(DATA_DIR / f"{TICKER}.csv", parse_dates=["date"], index_col="date")

train = ohlc["2018-01-01":"2019-01-01"]
test = ohlc["2019-01-01":"2027-01-01"]

# Best detection config from Exp 4
ATR_MULT = 3
config = ATRZigZagConfig(atr_length=14, atr_mult=ATR_MULT, use_close_only=False)
detector = ATRZigZagDetector(config)

seq_params = {
    "method": "tolerance", "min_contractions": 2, "max_contractions": 4,
    "lookback_bars": 72, "tolerance": 0.15,
    "max_depth_pct": 0.50, "max_depth_atr": None,
    "min_total_reduction": 0.80,
    "max_gap_between_contractions_days": None,
    "require_ascending_lows": False,
    "ascending_lows_tolerance": 0.03,
}
comp_params = {"method": "ratio", "atr_period": 14, "ratio_threshold": 0.95}
breakout_params = {
    "volume_method": "ratio", "volume_ratio_threshold": 1.5,
    "volume_lookback_days": 50, "require_volume_confirmation": False,
}
risk_params = {
    "trailing_sma_period": 20,
    "trailing_volume_factor": 1.5,
    "trailing_stop_method": "atr",
    "trailing_atr_period": 14,
    "min_progress_r": 0.5,
    "early_exit_days": None,
    "max_stop_loss_pct": 0.01,
    "max_bars_without_progress": 24,
    "trailing_atr_multiplier": 3.0,
    "target_r_multiple": 3.0,
    "breakeven_r_multiple": 1.0,
}


def run_split(split_ohlc, label):
    cache_swings = detector.detect(split_ohlc)
    cache_contr = compute_contractions(cache_swings, split_ohlc)
    cache_atr = compute_atr(split_ohlc, 14)
    res = run_full_vcp_pipeline(
        ohlc=split_ohlc, swing_detector=detector,
        sequence_params=seq_params, compression_params=comp_params,
        breakout_params=breakout_params, volume_contraction_params=None,
        precomputed_swings=cache_swings, precomputed_contractions=cache_contr,
        precomputed_atr=cache_atr,
    )
    signals = {dt: s for dt, s in res.items() if s is not None}
    results = evaluate_signals_to_trades(
        signals, split_ohlc, risk_params, grouping="sequential",
        precomputed_atr=cache_atr,
    )
    print(f"{label}: {len(signals)} signals -> {len(results)} trades")
    return results, cache_atr


print("Running pipeline on TRAIN and TEST...")
train_results, train_atr = run_split(train, "TRAIN")
test_results, test_atr = run_split(test, "TEST")


# ══════════════════════════════════════════════════════════════
# 1. BASIC COMPARISON
# ══════════════════════════════════════════════════════════════
print(f"\n{'='*80}")
print("1. COMPARACION TRAIN vs TEST")
print(f"{'='*80}")

for label, results in [("TRAIN", train_results), ("TEST", test_results)]:
    trades = [t for _, t in results]
    wins = sum(1 for t in trades if t["pnl_pct"] > 0)
    cr = float(np.prod([1 + t["pnl_pct"] for t in trades]) - 1)
    pnls = [t["pnl_pct"] for t in trades]
    rs = [t["r_multiple"] for t in trades]
    reasons = {}
    for t in trades:
        reasons[t["exit_reason"]] = reasons.get(t["exit_reason"], 0) + 1

    print(f"\n  {label}:")
    print(f"    Trades: {len(trades)}")
    print(f"    WR: {wins}/{len(trades)} = {wins/len(trades):.0%}")
    print(f"    CR: {cr:+.2%}")
    print(f"    Avg PnL: {np.mean(pnls):+.4%}")
    print(f"    Median PnL: {np.median(pnls):+.4%}")
    print(f"    Avg R: {np.mean(rs):+.2f}R")
    print(f"    Std PnL: {np.std(pnls):.4%}")
    print(f"    Best: {max(pnls):+.2%} | Worst: {min(pnls):+.2%}")
    print(f"    Avg Duration: {np.mean([t['duration_days'] for t in trades]):.1f}d")
    print(f"    Exit reasons: {reasons}")


# ══════════════════════════════════════════════════════════════
# 2. YEARLY BREAKDOWN — TEST
# ══════════════════════════════════════════════════════════════
print(f"\n{'='*80}")
print("2. DESGLOSE POR AÑO — TEST")
print(f"{'='*80}")

yearly = {}
for pat, trade in test_results:
    year = pat["first_signal_date"].year
    if year not in yearly:
        yearly[year] = []
    yearly[year].append((pat, trade))

print(f"\n  {'Año':>4s} | {'Trades':>6s} | {'WR':>5s} | {'CR':>8s} | {'AvgPnL':>8s} | {'AvgR':>6s} | {'AvgDur':>6s} | Salidas")
print(f"  {'─'*90}")

for year in sorted(yearly.keys()):
    items = yearly[year]
    trades = [t for _, t in items]
    wins = sum(1 for t in trades if t["pnl_pct"] > 0)
    cr = float(np.prod([1 + t["pnl_pct"] for t in trades]) - 1)
    avg_pnl = np.mean([t["pnl_pct"] for t in trades])
    avg_r = np.mean([t["r_multiple"] for t in trades])
    avg_dur = np.mean([t["duration_days"] for t in trades])
    reasons = {}
    for t in trades:
        reasons[t["exit_reason"]] = reasons.get(t["exit_reason"], 0) + 1
    reasons_str = ", ".join(f"{k}={v}" for k, v in sorted(reasons.items()))
    print(f"  {year:>4d} | {len(trades):>6d} | {wins/len(trades):>5.0%} | {cr:>+8.2%} | {avg_pnl:>+8.4%} | {avg_r:>+6.2f} | {avg_dur:>6.1f} | {reasons_str}")


# ══════════════════════════════════════════════════════════════
# 3. UNIQUE PATTERNS — TEST
# ══════════════════════════════════════════════════════════════
print(f"\n{'='*80}")
print("3. PATRONES UNICOS — TEST")
print(f"{'='*80}")

patterns_seen = {}
for i, (pat, trade) in enumerate(test_results, 1):
    sig = pat["signal_obj"]
    seq = sig.pivot_info.sequence
    key = tuple((c.high_swing.date, c.low_swing.date) for c in seq.contractions)
    if key not in patterns_seen:
        patterns_seen[key] = {"trades": [], "pattern": pat, "sequence": seq}
    patterns_seen[key]["trades"].append((i, pat, trade))

print(f"\n  {len(test_results)} trades provienen de {len(patterns_seen)} patrones unicos")
print(f"  Ratio trades/patrones: {len(test_results)/len(patterns_seen):.1f}")

print(f"\n  {'Pat':>3s} | {'#T':>3s} | {'WR':>5s} | {'CR':>8s} | {'Periodo':<35s} | {'#C':>2s} | {'Depths'}")
print(f"  {'─'*110}")

for pat_idx, (key, info) in enumerate(patterns_seen.items(), 1):
    seq = info["sequence"]
    trades_list = info["trades"]
    t_trades = [t[2] for t in trades_list]
    wins = sum(1 for t in t_trades if t["pnl_pct"] > 0)
    cr = float(np.prod([1 + t["pnl_pct"] for t in t_trades]) - 1)
    first_date = trades_list[0][1]["first_signal_date"]
    last_exit = trades_list[-1][2]["exit_date"]
    depths = [f"{c.depth_pct:.4f}%" for c in seq.contractions]

    print(f"  {pat_idx:>3d} | {len(trades_list):>3d} | {wins/len(trades_list):>5.0%} | {cr:>+8.2%} | "
          f"{first_date.strftime('%Y-%m-%d %H:%M')} -> {last_exit.strftime('%Y-%m-%d %H:%M'):<15s} | "
          f"{seq.n_contractions:>2d} | {depths}")


# ══════════════════════════════════════════════════════════════
# 4. EXIT REASON ANALYSIS
# ══════════════════════════════════════════════════════════════
print(f"\n{'='*80}")
print("4. ANALISIS POR RAZON DE SALIDA — TEST")
print(f"{'='*80}")

by_exit = {}
for pat, trade in test_results:
    reason = trade["exit_reason"]
    if reason not in by_exit:
        by_exit[reason] = []
    by_exit[reason].append((pat, trade))

for reason in sorted(by_exit.keys()):
    items = by_exit[reason]
    trades = [t for _, t in items]
    pnls = [t["pnl_pct"] for t in trades]
    rs = [t["r_multiple"] for t in trades]
    durs = [t["duration_days"] for t in trades]
    wins = sum(1 for p in pnls if p > 0)
    print(f"\n  {reason}: {len(trades)} trades ({len(trades)/len(test_results):.0%})")
    print(f"    WR: {wins/len(trades):.0%}")
    print(f"    Avg PnL: {np.mean(pnls):+.4%} | Median: {np.median(pnls):+.4%}")
    print(f"    PnL range: [{min(pnls):+.2%}, {max(pnls):+.2%}]")
    print(f"    Avg R: {np.mean(rs):+.2f}R")
    print(f"    Avg Duration: {np.mean(durs):.1f}d")


# ══════════════════════════════════════════════════════════════
# 5. TRADE SIZE DISTRIBUTION (PnL)
# ══════════════════════════════════════════════════════════════
print(f"\n{'='*80}")
print("5. DISTRIBUCION DE PnL — TEST")
print(f"{'='*80}")

pnls = [t["pnl_pct"] for _, t in test_results]
print(f"\n  Percentiles:")
for p in [5, 10, 25, 50, 75, 90, 95]:
    print(f"    P{p:>2d}: {np.percentile(pnls, p):+.4%}")
print(f"  Skew: {pd.Series(pnls).skew():.2f}")
print(f"  Kurtosis: {pd.Series(pnls).kurtosis():.2f}")

big_losses = [(pat, trade) for pat, trade in test_results if trade["pnl_pct"] < -0.005]
big_wins = [(pat, trade) for pat, trade in test_results if trade["pnl_pct"] > 0.005]
print(f"\n  Trades con PnL < -0.5%: {len(big_losses)}")
print(f"  Trades con PnL > +0.5%: {len(big_wins)}")
print(f"  Sum big losses: {sum(t['pnl_pct'] for _, t in big_losses):+.2%}")
print(f"  Sum big wins: {sum(t['pnl_pct'] for _, t in big_wins):+.2%}")


# ══════════════════════════════════════════════════════════════
# 6. REGIME ANALYSIS — ATR at entry
# ══════════════════════════════════════════════════════════════
print(f"\n{'='*80}")
print("6. ATR AL MOMENTO DE ENTRY — TRAIN vs TEST")
print(f"{'='*80}")

train_entry_atrs = []
for pat, trade in train_results:
    dt = pat["first_signal_date"]
    if dt in train_atr.index:
        train_entry_atrs.append(float(train_atr.loc[dt]))

test_entry_atrs = []
for pat, trade in test_results:
    dt = pat["first_signal_date"]
    if dt in test_atr.index:
        test_entry_atrs.append(float(test_atr.loc[dt]))

if train_entry_atrs:
    arr = np.array(train_entry_atrs)
    print(f"\n  TRAIN ATR at entry:")
    print(f"    Mean: {arr.mean():.6f} | Median: {np.median(arr):.6f}")
    print(f"    Min: {arr.min():.6f} | Max: {arr.max():.6f}")

if test_entry_atrs:
    arr = np.array(test_entry_atrs)
    print(f"\n  TEST ATR at entry:")
    print(f"    Mean: {arr.mean():.6f} | Median: {np.median(arr):.6f}")
    print(f"    Min: {arr.min():.6f} | Max: {arr.max():.6f}")

    # ATR by year
    print(f"\n  ATR por año al entry:")
    for year in sorted(yearly.keys()):
        yr_atrs = []
        for pat, trade in yearly[year]:
            dt = pat["first_signal_date"]
            if dt in test_atr.index:
                yr_atrs.append(float(test_atr.loc[dt]))
        if yr_atrs:
            arr = np.array(yr_atrs)
            print(f"    {year}: mean={arr.mean():.6f} median={np.median(arr):.6f} "
                  f"(x{arr.mean()/np.mean(train_entry_atrs):.1f} vs TRAIN)")


# ══════════════════════════════════════════════════════════════
# 7. STOP LOSS ANALYSIS
# ══════════════════════════════════════════════════════════════
print(f"\n{'='*80}")
print("7. ANALISIS DE STOP LOSSES — TEST")
print(f"{'='*80}")

stop_trades = [(pat, trade) for pat, trade in test_results if trade["exit_reason"] == "stop_loss"]
if stop_trades:
    sl_pnls = [t["pnl_pct"] for _, t in stop_trades]
    sl_durs = [t["duration_days"] for _, t in stop_trades]
    print(f"\n  Stop losses: {len(stop_trades)}/{len(test_results)} = {len(stop_trades)/len(test_results):.0%}")
    print(f"  Avg PnL: {np.mean(sl_pnls):+.4%} | Total impact: {sum(sl_pnls):+.2%}")
    print(f"  Avg Duration: {np.mean(sl_durs):.1f}d (pierden rapido)")
    print(f"\n  Stop loss by year:")
    for year in sorted(yearly.keys()):
        yr_stops = [t for _, t in yearly[year] if t["exit_reason"] == "stop_loss"]
        yr_total = len(yearly[year])
        if yr_stops:
            print(f"    {year}: {len(yr_stops)}/{yr_total} = {len(yr_stops)/yr_total:.0%} | "
                  f"Avg PnL: {np.mean([t['pnl_pct'] for t in yr_stops]):+.4%}")


# ══════════════════════════════════════════════════════════════
# 8. SEQUENTIAL CHURNING ANALYSIS
# ══════════════════════════════════════════════════════════════
print(f"\n{'='*80}")
print("8. CHURNING ANALYSIS — multiples trades por patron")
print(f"{'='*80}")

multi_pattern = {k: v for k, v in patterns_seen.items() if len(v["trades"]) > 1}
single_pattern = {k: v for k, v in patterns_seen.items() if len(v["trades"]) == 1}

print(f"\n  Patrones con 1 trade: {len(single_pattern)}")
print(f"  Patrones con >1 trade: {len(multi_pattern)}")

for key, info in multi_pattern.items():
    n_trades = len(info["trades"])
    t_trades = [t[2] for t in info["trades"]]
    cr = float(np.prod([1 + t["pnl_pct"] for t in t_trades]) - 1)
    wins = sum(1 for t in t_trades if t["pnl_pct"] > 0)
    first = info["trades"][0][1]["first_signal_date"]
    last = info["trades"][-1][2]["exit_date"]
    print(f"\n  Patron: {first.strftime('%Y-%m-%d')} -> {last.strftime('%Y-%m-%d')}")
    print(f"    {n_trades} trades, WR={wins/n_trades:.0%}, CR={cr:+.2%}")
    for i, pat, trade in info["trades"]:
        print(f"      T{i}: {pat['first_signal_date'].strftime('%Y-%m-%d %H:%M')} -> "
              f"{trade['exit_date'].strftime('%Y-%m-%d %H:%M')} | "
              f"{trade['exit_reason']:<15s} | PnL={trade['pnl_pct']:+.2%}")


# ══════════════════════════════════════════════════════════════
# 9. EQUITY CURVE
# ══════════════════════════════════════════════════════════════
print(f"\n{'='*80}")
print("9. GENERANDO EQUITY CURVE")
print(f"{'='*80}")

fig, axes = plt.subplots(2, 1, figsize=(16, 10), height_ratios=[2, 1],
                          gridspec_kw={"hspace": 0.15})

# Equity curve
equity = [1.0]
dates = []
for pat, trade in test_results:
    equity.append(equity[-1] * (1 + trade["pnl_pct"]))
    dates.append(trade["exit_date"])

ax = axes[0]
colors_eq = ["#27ae60" if equity[i+1] >= equity[i] else "#e74c3c" for i in range(len(dates))]
ax.plot(dates, equity[1:], color="#2c3e50", linewidth=1.2)
ax.axhline(1.0, color="gray", linewidth=0.5, linestyle="--")
ax.fill_between(dates, 1.0, equity[1:],
                where=[e >= 1.0 for e in equity[1:]],
                color="#27ae60", alpha=0.1)
ax.fill_between(dates, 1.0, equity[1:],
                where=[e < 1.0 for e in equity[1:]],
                color="#e74c3c", alpha=0.1)
ax.set_title(f"EURUSD Hourly VCP — TEST Equity Curve ({len(test_results)} trades)", fontsize=13, fontweight="bold")
ax.set_ylabel("Equity (starting at 1.0)")
ax.grid(True, alpha=0.3)

# PnL per trade
ax2 = axes[1]
trade_pnls = [trade["pnl_pct"] * 100 for _, trade in test_results]
colors_pnl = ["#27ae60" if p >= 0 else "#e74c3c" for p in trade_pnls]
ax2.bar(dates, trade_pnls, color=colors_pnl, width=15, alpha=0.7)
ax2.axhline(0, color="gray", linewidth=0.5)
ax2.set_ylabel("PnL por trade (%)")
ax2.set_xlabel("Fecha")
ax2.grid(True, alpha=0.3)
ax2.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
plt.setp(ax2.xaxis.get_majorticklabels(), rotation=30, ha="right", fontsize=8)

fig.savefig(OUTPUT_DIR / "equity_curve_test.png", dpi=120, bbox_inches="tight")
plt.close(fig)
print(f"  Saved: {OUTPUT_DIR / 'equity_curve_test.png'}")


# ══════════════════════════════════════════════════════════════
# 10. SUMMARY / CONCLUSION
# ══════════════════════════════════════════════════════════════
print(f"\n{'='*80}")
print("10. RESUMEN Y DIAGNOSTICO")
print(f"{'='*80}")

test_trades = [t for _, t in test_results]
train_trades = [t for _, t in train_results]

train_wr = sum(1 for t in train_trades if t["pnl_pct"] > 0) / len(train_trades)
test_wr = sum(1 for t in test_trades if t["pnl_pct"] > 0) / len(test_trades)
train_cr = float(np.prod([1 + t["pnl_pct"] for t in train_trades]) - 1)
test_cr = float(np.prod([1 + t["pnl_pct"] for t in test_trades]) - 1)

train_sl_rate = sum(1 for t in train_trades if t["exit_reason"] == "stop_loss") / len(train_trades)
test_sl_rate = sum(1 for t in test_trades if t["exit_reason"] == "stop_loss") / len(test_trades)

train_target_rate = sum(1 for t in train_trades if t["exit_reason"] == "target") / len(train_trades)
test_target_rate = sum(1 for t in test_trades if t["exit_reason"] == "target") / len(test_trades)

print(f"""
  Metrica              TRAIN       TEST        Delta
  ──────────────────────────────────────────────────
  Trades               {len(train_trades):>5d}       {len(test_trades):>5d}       {len(test_trades)-len(train_trades):>+5d}
  Win Rate             {train_wr:>5.0%}       {test_wr:>5.0%}       {test_wr-train_wr:>+5.0%}
  Cumulative Return    {train_cr:>+8.2%}    {test_cr:>+8.2%}    {test_cr-train_cr:>+8.2%}
  Stop Loss Rate       {train_sl_rate:>5.0%}       {test_sl_rate:>5.0%}       {test_sl_rate-train_sl_rate:>+5.0%}
  Target Rate          {train_target_rate:>5.0%}       {test_target_rate:>5.0%}       {test_target_rate-train_target_rate:>+5.0%}
  Avg Duration (d)     {np.mean([t['duration_days'] for t in train_trades]):>5.1f}       {np.mean([t['duration_days'] for t in test_trades]):>5.1f}
""")

# Key diagnostic signals
print("  DIAGNOSTICO:")
print(f"  - TRAIN tuvo solo {len(train_trades)} trades en 1 año; TEST tiene {len(test_trades)} en ~7 años")
print(f"    -> {len(test_trades)/7:.0f} trades/año en TEST vs {len(train_trades)} en TRAIN")
print(f"  - Stop loss rate salto de {train_sl_rate:.0%} a {test_sl_rate:.0%}")
print(f"  - Target rate bajo de {train_target_rate:.0%} a {test_target_rate:.0%}")
print(f"  - {len(patterns_seen)} patrones unicos generaron {len(test_results)} trades (churning: {len(test_results)/len(patterns_seen):.1f}x)")

# Check if any year is profitable
profitable_years = []
for year in sorted(yearly.keys()):
    items = yearly[year]
    trades = [t for _, t in items]
    cr = float(np.prod([1 + t["pnl_pct"] for t in trades]) - 1)
    if cr > 0:
        profitable_years.append((year, cr))
print(f"  - Años rentables en TEST: {len(profitable_years)}/{len(yearly)} "
      f"({', '.join(f'{y}:{cr:+.2%}' for y, cr in profitable_years) if profitable_years else 'ninguno'})")

print("\nCompleto!")
