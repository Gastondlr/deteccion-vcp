"""Temporal stability experiment: find best VCP params on first 5 years of EURUSD,
including swing atr_mult, compare with full-dataset params, and test out-of-sample."""
import sys
import time
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import numpy as np
import pandas as pd

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from models.configs import ATRZigZagConfig
from vcp_detection.heuristic import ATRZigZagDetector, run_full_vcp_pipeline
from vcp_detection.heuristic.contractions import compute_contractions
from vcp_detection.heuristic.atr_compression import compute_atr
from vcp_detection.analysis import group_signals_into_patterns, simulate_trade

pd.set_option("display.float_format", "{:.4f}".format)

# ── Constants ─────────────────────────────────────────────────

ATR_MULTS = [0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 2.5]
DEPTH_ATRS = [2, 3, 4, 5, 6]
REDUCTIONS = [0.40, 0.50, 0.60, 0.70, 0.80]

TRAILING_MULTS = [1.0, 1.5, 2.0, 2.5, 3.0]
TARGET_RS = [None, 2.0, 3.0, 5.0]
EARLY_EXITS = [None, 3, 5]
BREAKEVEN_RS = [0.5, 1.0, 1.5, 2.0]

COMPRESSION = {"method": "ratio", "atr_period": 14, "ratio_threshold": 0.85}
BREAKOUT = {
    "volume_method": "ratio", "volume_ratio_threshold": 1.5,
    "volume_lookback_days": 50,
    "require_volume_confirmation": False,
    "max_entry_distance_pct": 0.03,
}
RISK_BASE = {
    "max_stop_loss_pct": 0.02,
    "trailing_sma_period": 20,
    "trailing_volume_factor": 1.5,
    "trailing_stop_method": "atr",
    "trailing_atr_period": 14,
    "max_bars_without_progress": 15,
    "min_progress_r": 0.5,
}

FULL_DATASET_BEST = {
    "atr_mult": 1.5,
    "detection": {"max_depth_pct": 0.50, "max_depth_atr": 5, "min_total_reduction": 0.60},
    "exit": {
        "trailing_atr_multiplier": 1.5,
        "target_r_multiple": 3.0,
        "early_exit_days": None,
        "breakeven_r_multiple": 1.0,
    },
}

# ── Load and split data ──────────────────────────────────────

daily = pd.read_csv(
    project_root / "data" / "monedas" / "EURUSD.csv",
    parse_dates=["date"], index_col="date",
)

CUTOFF = "2020-01-01"
train = daily[daily.index < CUTOFF]
test = daily[daily.index >= CUTOFF]

print(f"EURUSD diario total: {len(daily):,} barras ({daily.index.min().date()} a {daily.index.max().date()})")
print(f"  TRAIN (primeros ~5 anios): {len(train):,} barras ({train.index.min().date()} a {train.index.max().date()})")
print(f"  TEST  (restantes ~6 anios): {len(test):,} barras ({test.index.min().date()} a {test.index.max().date()})")
print(f"\nGrilla: {len(ATR_MULTS)} atr_mults x {len(DEPTH_ATRS)} depth_atrs x {len(REDUCTIONS)} reductions "
      f"= {len(ATR_MULTS) * len(DEPTH_ATRS) * len(REDUCTIONS)} configs deteccion")
print(f"Salida: {len(TRAILING_MULTS)} trail x {len(TARGET_RS)} target x {len(EARLY_EXITS)} early x {len(BREAKEVEN_RS)} be "
      f"= {len(TRAILING_MULTS) * len(TARGET_RS) * len(EARLY_EXITS) * len(BREAKEVEN_RS)} configs salida")

# ── Helper functions ──────────────────────────────────────────

def precompute(ohlc, atr_mult):
    config = ATRZigZagConfig(atr_length=14, atr_mult=atr_mult, use_close_only=False)
    detector = ATRZigZagDetector(config)
    swings = detector.detect(ohlc)
    contractions = compute_contractions(swings, ohlc)
    atr = compute_atr(ohlc, COMPRESSION["atr_period"])
    return {"ohlc": ohlc, "swings": swings, "contractions": contractions,
            "atr": atr, "detector": detector}


def make_seq_params(depth_atr, reduction):
    return {
        "method": "tolerance", "min_contractions": 2, "max_contractions": 6,
        "lookback_bars": 126, "tolerance": 0.10,
        "max_depth_pct": 0.50, "max_depth_atr": depth_atr,
        "min_total_reduction": reduction,
        "max_gap_between_contractions_days": None,
        "require_ascending_lows": True, "ascending_lows_tolerance": 0.03,
    }


def evaluate_signals(ohlc, signals, risk):
    patterns = group_signals_into_patterns(signals, risk_params=risk)
    trades = [simulate_trade(ohlc, p, risk) for p in patterns]
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


def fmt_pct(x):
    return f"{x:+.2%}"

def fmt_wr(x):
    return f"{x:.0%}"


# ══════════════════════════════════════════════════════════════
#  FASE 1: GRILLA COMPLETA EN TRAIN — atr_mult x depth_atr x reduction
# ══════════════════════════════════════════════════════════════

print("\n" + "="*70)
print("  FASE 1: GRILLA DE DETECCION — TRAIN (2015-2019)")
print("  atr_mult x depth_atr x reduction")
print("="*70)

fixed_risk = {**RISK_BASE, "trailing_atr_multiplier": 1.5, "target_r_multiple": 3.0,
              "early_exit_days": None, "breakeven_r_multiple": 1.0}

all_det_results = []
caches_train = {}
t_total = time.time()

for atr_mult in ATR_MULTS:
    t0 = time.time()
    cache = precompute(train, atr_mult)
    caches_train[atr_mult] = cache
    n_swings = len(cache["swings"])
    n_contr = len(cache["contractions"])

    for depth_atr in DEPTH_ATRS:
        for reduction in REDUCTIONS:
            seq = make_seq_params(depth_atr, reduction)
            signals = detect_signals(train, seq, cache)
            ev = evaluate_signals(train, signals, fixed_risk)
            all_det_results.append({
                "atr_mult": atr_mult, "depth_atr": depth_atr, "reduction": reduction,
                "n_swings": n_swings, "n_contractions": n_contr,
                "signals": len(signals), **{k: ev[k] for k in ["trades", "wins", "WR", "CR", "avg_R"]},
            })

    elapsed = time.time() - t0
    best_in_mult = max((r for r in all_det_results if r["atr_mult"] == atr_mult),
                       key=lambda r: r["CR"], default=None)
    best_cr = fmt_pct(best_in_mult["CR"]) if best_in_mult else "N/A"
    print(f"  atr_mult={atr_mult:.2f}: {n_swings} swings, {n_contr} contr, "
          f"best_CR={best_cr} ({elapsed:.1f}s)")

det_df = pd.DataFrame(all_det_results)
det_df_sorted = det_df.sort_values("CR", ascending=False)

print(f"\nTotal: {len(det_df)} configs en {time.time()-t_total:.1f}s")
print(f"\nTop 20 configs (atr_mult x depth_atr x reduction):")
for _, row in det_df_sorted.head(20).iterrows():
    print(f"  atr_mult={row['atr_mult']:.2f}, depth_atr={int(row['depth_atr'])}, red={row['reduction']:.2f} "
          f"-> {int(row['signals'])} sen, {int(row['trades'])}T, "
          f"WR={fmt_wr(row['WR'])}, CR={fmt_pct(row['CR'])}, avgR={row['avg_R']:+.2f}")

# Best per atr_mult
print("\nMejor config por atr_mult:")
for atr_mult in ATR_MULTS:
    sub = det_df[det_df["atr_mult"] == atr_mult]
    best = sub.sort_values("CR", ascending=False).iloc[0]
    has_trades = sub[sub["trades"] > 0]
    print(f"  atr_mult={atr_mult:.2f}: depth_atr={int(best['depth_atr'])}, red={best['reduction']:.2f} "
          f"-> {int(best['trades'])}T, WR={fmt_wr(best['WR'])}, CR={fmt_pct(best['CR'])} "
          f"({len(has_trades)}/{len(sub)} configs con trades)")

# Overall best
best_overall = det_df_sorted.iloc[0]
BEST_ATR_MULT = best_overall["atr_mult"]
BEST_DEPTH_ATR = int(best_overall["depth_atr"])
BEST_REDUCTION = best_overall["reduction"]
print(f"\n>>> MEJOR CONFIG TRAIN: atr_mult={BEST_ATR_MULT}, "
      f"depth_atr={BEST_DEPTH_ATR}, reduction={BEST_REDUCTION}")


# ══════════════════════════════════════════════════════════════
#  FASE 2: GRILLA DE SALIDA EN TRAIN (con mejor deteccion)
# ══════════════════════════════════════════════════════════════

print("\n\n" + "="*70)
print(f"  FASE 2: GRILLA DE SALIDA — TRAIN")
print(f"  atr_mult={BEST_ATR_MULT}, depth_atr={BEST_DEPTH_ATR}, red={BEST_REDUCTION}")
print("="*70)

best_seq = make_seq_params(BEST_DEPTH_ATR, BEST_REDUCTION)
best_cache = caches_train[BEST_ATR_MULT]
signals_train = detect_signals(train, best_seq, best_cache)
print(f"  Senales detectadas: {len(signals_train)}")

exit_results = []
t0 = time.time()
for trail in TRAILING_MULTS:
    for target in TARGET_RS:
        for early in EARLY_EXITS:
            for be_r in BREAKEVEN_RS:
                risk = {**RISK_BASE, "trailing_atr_multiplier": trail,
                        "target_r_multiple": target, "early_exit_days": early,
                        "breakeven_r_multiple": be_r}
                ev = evaluate_signals(train, signals_train, risk)
                exit_results.append({
                    "trailing_atr_multiplier": trail, "target_r_multiple": target,
                    "early_exit_days": early, "breakeven_r_multiple": be_r,
                    **{k: ev[k] for k in ["trades", "wins", "WR", "CR", "avg_R"]},
                    "early_exits": ev["reasons"].get("early_exit", 0),
                    "trail_stops": ev["reasons"].get("trailing_stop", 0),
                    "stops": ev["reasons"].get("stop_loss", 0),
                    "targets": ev["reasons"].get("target", 0),
                    "time_exits": ev["reasons"].get("time_exit", 0),
                })

exit_df = pd.DataFrame(exit_results)
exit_df_sorted = exit_df.sort_values("CR", ascending=False)
print(f"  {len(exit_df)} configs en {time.time()-t0:.1f}s")

print("\nTop 15 configs por CR:")
for _, row in exit_df_sorted.head(15).iterrows():
    t_r = row['target_r_multiple'] if pd.notna(row['target_r_multiple']) else 'None'
    e_e = int(row['early_exit_days']) if pd.notna(row['early_exit_days']) else 'None'
    print(f"  trail={row['trailing_atr_multiplier']}, target={t_r}, early={e_e}, be_R={row['breakeven_r_multiple']}"
          f" -> {int(row['trades'])}T, WR={fmt_wr(row['WR'])}, CR={fmt_pct(row['CR'])}, "
          f"exits: {int(row['early_exits'])}e/{int(row['trail_stops'])}t/{int(row['stops'])}s/"
          f"{int(row['targets'])}tgt/{int(row['time_exits'])}time")

# Early exit analysis
print("\n  Impacto early_exit:")
for early_val in [None, 3, 5]:
    if early_val is None:
        sub = exit_df[exit_df["early_exit_days"].isna()]
        label = "early=None"
    else:
        sub = exit_df[exit_df["early_exit_days"] == early_val]
        label = f"early={early_val}"
    if len(sub) > 0:
        print(f"    {label:<14} avg_WR={sub['WR'].mean():.0%}, "
              f"avg_CR={sub['CR'].mean():+.2%}, best_CR={sub['CR'].max():+.2%}")

best_exit_row = exit_df_sorted.iloc[0]
BEST_EXIT = {
    "trailing_atr_multiplier": best_exit_row["trailing_atr_multiplier"],
    "target_r_multiple": best_exit_row["target_r_multiple"] if pd.notna(best_exit_row["target_r_multiple"]) else None,
    "early_exit_days": int(best_exit_row["early_exit_days"]) if pd.notna(best_exit_row["early_exit_days"]) else None,
    "breakeven_r_multiple": best_exit_row["breakeven_r_multiple"],
}

print(f"\n>>> MEJOR CONFIG TRAIN COMPLETA:")
print(f"    Swing:     atr_mult={BEST_ATR_MULT}")
print(f"    Deteccion: depth_atr={BEST_DEPTH_ATR}, reduction={BEST_REDUCTION}")
print(f"    Salida:    trail={BEST_EXIT['trailing_atr_multiplier']}, "
      f"target={BEST_EXIT['target_r_multiple']}, "
      f"early={BEST_EXIT['early_exit_days']}, "
      f"be_R={BEST_EXIT['breakeven_r_multiple']}")


# ══════════════════════════════════════════════════════════════
#  FASE 3: COMPARACION — TRAIN-BEST vs FULL-DATASET-BEST
# ══════════════════════════════════════════════════════════════

print("\n\n" + "="*70)
print("  FASE 3: COMPARACION DE PARAMETROS")
print("="*70)

comparisons = [
    ("atr_mult", BEST_ATR_MULT, FULL_DATASET_BEST["atr_mult"]),
    ("depth_atr", BEST_DEPTH_ATR, FULL_DATASET_BEST["detection"]["max_depth_atr"]),
    ("min_total_reduction", BEST_REDUCTION, FULL_DATASET_BEST["detection"]["min_total_reduction"]),
    ("trailing_atr_multiplier", BEST_EXIT["trailing_atr_multiplier"], FULL_DATASET_BEST["exit"]["trailing_atr_multiplier"]),
    ("target_r_multiple", BEST_EXIT["target_r_multiple"], FULL_DATASET_BEST["exit"]["target_r_multiple"]),
    ("early_exit_days", BEST_EXIT["early_exit_days"], FULL_DATASET_BEST["exit"]["early_exit_days"]),
    ("breakeven_r_multiple", BEST_EXIT["breakeven_r_multiple"], FULL_DATASET_BEST["exit"]["breakeven_r_multiple"]),
]

print(f"\n  {'Parametro':<30s} {'TRAIN (5y)':>15s} {'FULL (11y)':>15s} {'Iguales?':>10s}")
print(f"  {'─'*72}")
n_equal = 0
for name, train_val, full_val in comparisons:
    match = "SI" if train_val == full_val else "NO"
    if match == "SI":
        n_equal += 1
    print(f"  {name:<30s} {str(train_val):>15s} {str(full_val):>15s} {match:>10s}")
print(f"\n  Coincidencia: {n_equal}/{len(comparisons)} parametros iguales")


# ══════════════════════════════════════════════════════════════
#  FASE 4: OUT-OF-SAMPLE — TRAIN-best vs FULL-best en TEST
# ══════════════════════════════════════════════════════════════

print("\n\n" + "="*70)
print("  FASE 4: OUT-OF-SAMPLE — TEST (2020-2026)")
print("="*70)

seq_train = make_seq_params(BEST_DEPTH_ATR, BEST_REDUCTION)
risk_train = {**RISK_BASE, **BEST_EXIT}

seq_full = make_seq_params(
    FULL_DATASET_BEST["detection"]["max_depth_atr"],
    FULL_DATASET_BEST["detection"]["min_total_reduction"],
)
risk_full = {**RISK_BASE, **FULL_DATASET_BEST["exit"]}

configs = {
    "Train-optimized (5y)": (BEST_ATR_MULT, seq_train, risk_train),
    "Full-dataset (11y)": (FULL_DATASET_BEST["atr_mult"], seq_full, risk_full),
}

splits = {"TRAIN (2015-2019)": train, "TEST (2020-2026)": test, "FULL (2015-2026)": daily}

print(f"\n  {'Config':<25s} | {'Split':<20s} | {'Sen':>5s} | {'Trades':>6s} | {'WR':>5s} | {'CR':>8s} | {'AvgR':>6s} | Salidas")
print(f"  {'─'*110}")

for config_name, (atr_m, seq, risk) in configs.items():
    for split_name, ohlc in splits.items():
        cache = precompute(ohlc, atr_m)
        signals = detect_signals(ohlc, seq, cache)
        ev = evaluate_signals(ohlc, signals, risk)
        reasons_str = ", ".join(f"{k}={v}" for k, v in sorted(ev["reasons"].items()))
        print(f"  {config_name:<25s} | {split_name:<20s} | {len(signals):>5d} | {ev['trades']:>6d} | "
              f"{fmt_wr(ev['WR']):>5s} | {fmt_pct(ev['CR']):>8s} | {ev['avg_R']:>+6.2f} | {reasons_str}")


# ══════════════════════════════════════════════════════════════
#  FASE 5: DETALLE DE TRADES EN TEST
# ══════════════════════════════════════════════════════════════

print("\n\n" + "="*70)
print("  FASE 5: DETALLE DE TRADES EN TEST (2020-2026)")
print("="*70)

for config_name, (atr_m, seq, risk) in configs.items():
    cache = precompute(test, atr_m)
    signals = detect_signals(test, seq, cache)
    ev = evaluate_signals(test, signals, risk)
    print(f"\n  {config_name} (atr_mult={atr_m}):")
    if not ev["trade_details"]:
        print("    (sin trades)")
        continue
    for i, (pat, trade) in enumerate(ev["trade_details"], 1):
        entry_str = pat["first_signal_date"].strftime("%Y-%m-%d") if hasattr(pat["first_signal_date"], "strftime") else str(pat["first_signal_date"])
        exit_str = trade["exit_date"].strftime("%Y-%m-%d") if hasattr(trade["exit_date"], "strftime") else str(trade["exit_date"])
        print(f"    Trade {i}: {entry_str} -> {exit_str} | {trade['exit_reason']:<15s} | "
              f"PnL={trade['pnl_pct']:+.2%} | R={trade['r_multiple']:+.1f}R | "
              f"Dur={trade.get('duration_days', '?')}d")


# ══════════════════════════════════════════════════════════════
#  FASE 6: ANALISIS DEL EFECTO DE atr_mult
# ══════════════════════════════════════════════════════════════

print("\n\n" + "="*70)
print("  FASE 6: EFECTO DE atr_mult EN LA DETECCION")
print("="*70)

print("\n  Resumen por atr_mult (promedio de todas las configs depth_atr x reduction):")
print(f"  {'atr_mult':>8s} | {'Swings':>6s} | {'Contr':>5s} | {'Avg Sen':>7s} | {'Avg Trades':>10s} | "
      f"{'Avg CR':>8s} | {'Best CR':>8s} | {'Configs c/trades':>16s}")
print(f"  {'─'*90}")

for atr_mult in ATR_MULTS:
    sub = det_df[det_df["atr_mult"] == atr_mult]
    has_trades = sub[sub["trades"] > 0]
    swings = sub.iloc[0]["n_swings"]
    contr = sub.iloc[0]["n_contractions"]
    print(f"  {atr_mult:>8.2f} | {int(swings):>6d} | {int(contr):>5d} | {sub['signals'].mean():>7.0f} | "
          f"{sub['trades'].mean():>10.1f} | {sub['CR'].mean():>+8.2%} | {sub['CR'].max():>+8.2%} | "
          f"{len(has_trades):>3d}/{len(sub)}")


# ══════════════════════════════════════════════════════════════
#  RESUMEN FINAL
# ══════════════════════════════════════════════════════════════

print("\n\n" + "="*70)
print("  RESUMEN FINAL")
print("="*70)

print(f"""
Pregunta: Los parametros optimizados con 5 anios de data (2015-2019)
coinciden con los optimizados con 11 anios (2015-2026)?

Parametros coincidentes: {n_equal}/{len(comparisons)}

TRAIN (5y):  atr_mult={BEST_ATR_MULT}, depth_atr={BEST_DEPTH_ATR}, red={BEST_REDUCTION}, \
trail={BEST_EXIT['trailing_atr_multiplier']}, target={BEST_EXIT['target_r_multiple']}, \
early={BEST_EXIT['early_exit_days']}, be_R={BEST_EXIT['breakeven_r_multiple']}

FULL  (11y): atr_mult=1.5, depth_atr=5, red=0.60, trail=1.5, target=3.0, early=None, be_R=1.0
""")

print("Completo!")
