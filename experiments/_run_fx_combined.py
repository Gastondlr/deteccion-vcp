"""FX experiment phase 2: combined best detection + exit configs on EURUSD."""
import sys
import time
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from models.configs import ATRZigZagConfig
from vcp_detection.heuristic import ATRZigZagDetector, run_full_vcp_pipeline
from vcp_detection.heuristic.contractions import compute_contractions
from vcp_detection.heuristic.atr_compression import compute_atr
from vcp_detection.analysis import (
    group_signals_into_patterns,
    simulate_trade,
    plot_trade_simulation,
)

pd.set_option("display.float_format", "{:.4f}".format)

# ── Base FX params ──────────────────────────────────────────

FX_BASE = {
    "swing": ATRZigZagConfig(atr_length=14, atr_mult=1.5, use_close_only=False),
    "compression": {"method": "ratio", "atr_period": 14, "ratio_threshold": 0.85},
    "breakout": {
        "volume_method": "ratio", "volume_ratio_threshold": 1.5,
        "volume_lookback_days": 50,
        "require_volume_confirmation": False,
        "max_entry_distance_pct": 0.03,
    },
    "risk_base": {
        "max_stop_loss_pct": 0.02,
        "trailing_sma_period": 20,
        "trailing_volume_factor": 1.5,
        "trailing_stop_method": "atr",
        "trailing_atr_period": 14,
        "max_bars_without_progress": 15,
        "min_progress_r": 0.5,
    },
}

# ── Load data ───────────────────────────────────────────────

daily = pd.read_csv(
    project_root / "data" / "monedas" / "EURUSD.csv",
    parse_dates=["date"], index_col="date",
)
hourly = pd.read_csv(
    project_root / "data" / "monedas_hora" / "EURUSD.csv",
    parse_dates=["date"], index_col="date",
)
print(f"EURUSD diario:  {len(daily):,} barras ({daily.index.min().date()} a {daily.index.max().date()})")
print(f"EURUSD horario: {len(hourly):,} barras ({hourly.index.min()} a {hourly.index.max()})")

# ── Precompute swings/contractions/ATR ──────────────────────

print("\nPrecalculando swings/contracciones/ATR...")
detector = ATRZigZagDetector(FX_BASE["swing"])
atr_period = FX_BASE["compression"]["atr_period"]

cache = {}
for label, ohlc in [("Diario", daily), ("Horario", hourly)]:
    t0 = time.time()
    swings = detector.detect(ohlc)
    contractions = compute_contractions(swings, ohlc)
    atr = compute_atr(ohlc, atr_period)
    cache[label] = {"ohlc": ohlc, "swings": swings, "contractions": contractions, "atr": atr}
    print(f"  {label}: {time.time()-t0:.1f}s")

# ── Config A: Diario optimizada ─────────────────────────────

print("\n" + "="*70)
print("  CONFIG A: DIARIO (depth_atr=5, reduction=0.60)")
print("="*70)

SEQ_A = {
    "method": "tolerance", "min_contractions": 2, "max_contractions": 6,
    "lookback_bars": 126, "tolerance": 0.10,
    "max_depth_pct": 0.50, "max_depth_atr": 5, "min_total_reduction": 0.60,
    "max_gap_between_contractions_days": None,
    "require_ascending_lows": True, "ascending_lows_tolerance": 0.03,
}

TRAILING_MULTS_A = [1.5, 2.0, 2.5]
TARGET_RS_A = [None, 2.0, 3.0, 5.0]
EARLY_EXITS_A = [None, 3, 5]
BREAKEVEN_RS_A = [1.0, 1.5, 2.0]

def detect_once_simulate_many(ohlc, seq_params, risk_variants, cache_entry, label):
    """Detect patterns once, then simulate trades with each risk config."""
    t0 = time.time()
    res = run_full_vcp_pipeline(
        ohlc=ohlc, swing_detector=detector,
        sequence_params=seq_params,
        compression_params=FX_BASE["compression"],
        breakout_params=FX_BASE["breakout"],
        volume_contraction_params=None,
        precomputed_swings=cache_entry["swings"],
        precomputed_contractions=cache_entry["contractions"],
        precomputed_atr=cache_entry["atr"],
    )
    signals = {dt: s for dt, s in res.items() if s is not None}
    print(f"  Deteccion: {len(signals)} senales en {time.time()-t0:.1f}s")

    results = []
    for risk_combo in risk_variants:
        risk = {**FX_BASE["risk_base"], **risk_combo}
        patterns = group_signals_into_patterns(signals, risk_params=risk)
        trades = []
        for p in patterns:
            t = simulate_trade(ohlc, p, risk)
            t["pattern"] = p
            trades.append(t)

        n = len(trades)
        wins = sum(1 for t in trades if t["pnl_pct"] > 0) if n else 0
        cr = float(np.prod([1 + t["pnl_pct"] for t in trades]) - 1) if n else 0
        avg_r = float(np.mean([t["r_multiple"] for t in trades])) if n else 0
        reasons = {}
        for t in trades:
            reasons[t["exit_reason"]] = reasons.get(t["exit_reason"], 0) + 1

        results.append({
            **risk_combo,
            "trades": n, "wins": wins,
            "WR": wins / n if n > 0 else 0,
            "CR": cr, "avg_R": avg_r,
            "early_exits": reasons.get("early_exit", 0),
            "targets": reasons.get("target", 0),
            "trail_stops": reasons.get("trailing_stop", 0),
            "stops": reasons.get("stop_loss", 0),
            "time_exits": reasons.get("time_exit", 0),
        })
    return results, signals


risk_variants_a = [
    {"trailing_atr_multiplier": trail, "target_r_multiple": target,
     "early_exit_days": early, "breakeven_r_multiple": be_r}
    for trail in TRAILING_MULTS_A
    for target in TARGET_RS_A
    for early in EARLY_EXITS_A
    for be_r in BREAKEVEN_RS_A
]
print(f"  {len(risk_variants_a)} combinaciones de riesgo (1 deteccion)...")
t0 = time.time()
results_a, signals_a = detect_once_simulate_many(
    daily, SEQ_A, risk_variants_a, cache["Diario"], "Config A"
)

print(f"  Done in {time.time()-t0:.1f}s")

df_a = pd.DataFrame(results_a)
df_a_sorted = df_a.sort_values("CR", ascending=False)
print(f"\n  Top 15 configs (de {len(df_a)}):")
top_a = df_a_sorted.head(15)
print(top_a.to_string(index=False, float_format=lambda x: f"{x:.2f}" if abs(x) > 1 else f"{x:.4f}"))

print(f"\n  Peores 5 configs:")
print(df_a_sorted.tail(5).to_string(index=False, float_format=lambda x: f"{x:.2f}" if abs(x) > 1 else f"{x:.4f}"))


# ── Config B: Horario conservadora ──────────────────────────

print("\n\n" + "="*70)
print("  CONFIG B: HORARIO (depth_atr=2, reduction=0.70)")
print("="*70)

SEQ_B = {
    "method": "tolerance", "min_contractions": 2, "max_contractions": 6,
    "lookback_bars": 252, "tolerance": 0.10,
    "max_depth_pct": 0.50, "max_depth_atr": 2, "min_total_reduction": 0.70,
    "max_gap_between_contractions_days": None,
    "require_ascending_lows": True, "ascending_lows_tolerance": 0.03,
}

TRAILING_MULTS_B = [2.0, 2.5, 3.0]
TARGET_RS_B = [None, 2.0, 3.0]
EARLY_EXITS_B = [None, 3, 5, 10]
BREAKEVEN_RS_B = [1.0, 1.5, 2.0]

risk_variants_b = [
    {"trailing_atr_multiplier": trail, "target_r_multiple": target,
     "early_exit_days": early, "breakeven_r_multiple": be_r}
    for trail in TRAILING_MULTS_B
    for target in TARGET_RS_B
    for early in EARLY_EXITS_B
    for be_r in BREAKEVEN_RS_B
]
print(f"  {len(risk_variants_b)} combinaciones de riesgo (1 deteccion)...")
t0 = time.time()
results_b, signals_b = detect_once_simulate_many(
    hourly, SEQ_B, risk_variants_b, cache["Horario"], "Config B"
)

print(f"  Done in {time.time()-t0:.1f}s")

df_b = pd.DataFrame(results_b)
df_b_sorted = df_b.sort_values("CR", ascending=False)
print(f"\n  Top 15 configs (de {len(df_b)}):")
top_b = df_b_sorted.head(15)
print(top_b.to_string(index=False, float_format=lambda x: f"{x:.2f}" if abs(x) > 1 else f"{x:.4f}"))

print(f"\n  Peores 5 configs:")
print(df_b_sorted.tail(5).to_string(index=False, float_format=lambda x: f"{x:.2f}" if abs(x) > 1 else f"{x:.4f}"))


# ── Analisis de impacto del early_exit ──────────────────────

print("\n\n" + "="*70)
print("  ANALISIS: IMPACTO DEL EARLY_EXIT")
print("="*70)

for name, df in [("Config A (Diario)", df_a), ("Config B (Horario)", df_b)]:
    print(f"\n  {name}:")
    for early_val in sorted(df["early_exit_days"].unique(), key=lambda x: (x is None, x)):
        sub = df[df["early_exit_days"] == early_val] if early_val is not None else df[df["early_exit_days"].isna()]
        label_e = f"early={early_val}" if early_val is not None else "early=None"
        avg_cr = sub["CR"].mean()
        avg_wr = sub["WR"].mean()
        avg_trades = sub["trades"].mean()
        avg_early = sub["early_exits"].mean()
        best_cr = sub["CR"].max()
        print(f"    {label_e:<14} avg_trades={avg_trades:.0f}, avg_WR={avg_wr:.0%}, "
              f"avg_CR={avg_cr:+.2%}, best_CR={best_cr:+.2%}, avg_early_exits={avg_early:.1f}")


# ── Resumen final ───────────────────────────────────────────

print("\n\n" + "="*70)
print("  RESUMEN: MEJORES CONFIGS COMBINADAS")
print("="*70)

def print_top_configs(df_sorted, n=5):
    for _, row in df_sorted.head(n).iterrows():
        t_r = row['target_r_multiple'] if pd.notna(row['target_r_multiple']) else 'None'
        e_e = int(row['early_exit_days']) if pd.notna(row['early_exit_days']) else 'None'
        print(f"    trail={row['trailing_atr_multiplier']}, target={t_r}, early={e_e}, be_R={row['breakeven_r_multiple']}"
              f" -> {int(row['trades'])}T, WR={row['WR']:.0%}, CR={row['CR']:+.2%}, "
              f"exits: {int(row['early_exits'])}e/{int(row['trail_stops'])}t/{int(row['stops'])}s/{int(row['targets'])}tgt/{int(row['time_exits'])}time")

print("\n  Config A - DIARIO (depth_atr=5, reduction=0.60):")
print_top_configs(df_a_sorted)

print("\n  Config B - HORARIO (depth_atr=2, reduction=0.70):")
print_top_configs(df_b_sorted)


# ── Plots de los mejores trades (Config A) ──────────────────

print("\n\n" + "="*70)
print("  PLOTS: MEJORES TRADES CONFIG A (DIARIO)")
print("="*70)

best_row_a = df_a_sorted.iloc[0]
best_risk_a = {
    **FX_BASE["risk_base"],
    "trailing_atr_multiplier": best_row_a["trailing_atr_multiplier"],
    "target_r_multiple": best_row_a["target_r_multiple"] if pd.notna(best_row_a["target_r_multiple"]) else None,
    "early_exit_days": int(best_row_a["early_exit_days"]) if pd.notna(best_row_a["early_exit_days"]) else None,
    "breakeven_r_multiple": best_row_a["breakeven_r_multiple"],
}

patterns = group_signals_into_patterns(signals_a, risk_params=best_risk_a)
best_trades = []
for p in patterns:
    t = simulate_trade(daily, p, best_risk_a)
    t["pattern"] = p
    best_trades.append(t)

plots_dir = project_root / "experiments" / "fx_combined_plots"
plots_dir.mkdir(exist_ok=True)

for i, (pat, trade) in enumerate(zip(patterns, best_trades), 1):
    pnl = trade["pnl_pct"]
    r = trade["r_multiple"]
    print(f"\n  Trade {i}: {trade['exit_reason']} | PnL={pnl:+.2%} | R={r:+.1f}R")
    save_path = plots_dir / f"config_a_trade_{i}.png"
    plot_trade_simulation(daily, pat, trade, pattern_number=i,
                          risk_params=best_risk_a, ticker="EURUSD",
                          save_path=str(save_path))
    plt.close()

print(f"\n  Plots guardados en {plots_dir}")
print("\nCompleto!")
