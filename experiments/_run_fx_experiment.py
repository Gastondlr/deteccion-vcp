"""FX experiment: VCP adapted to EURUSD (daily + hourly)."""
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
    plot_vcp_pattern,
    plot_trade_simulation,
)

pd.set_option("display.float_format", "{:.4f}".format)

# ── Parameters ──────────────────────────────────────────────

STOCK_PARAMS = {
    "swing": ATRZigZagConfig(atr_length=14, atr_mult=2.0, use_close_only=False),
    "sequence": {
        "method": "tolerance", "min_contractions": 2, "max_contractions": 6,
        "lookback_bars": 126, "tolerance": 0.10,
        "max_depth_pct": 0.35, "max_depth_atr": 7, "min_total_reduction": 0.80,
        "max_gap_between_contractions_days": None,
        "require_ascending_lows": True, "ascending_lows_tolerance": 0.10,
    },
    "compression": {"method": "ratio", "atr_period": 14, "ratio_threshold": 0.85},
    "volume_contraction": {"method": "ratio", "volume_column": "volume", "ratio_threshold": 0.85},
    "breakout": {
        "volume_method": "ratio", "volume_ratio_threshold": 1.5,
        "volume_lookback_days": 50, "require_volume_confirmation": False,
        "max_entry_distance_pct": 0.10,
    },
    "risk": {
        "max_stop_loss_pct": 0.05, "breakeven_r_multiple": 2.0,
        "trailing_sma_period": 20, "trailing_volume_factor": 1.5,
        "trailing_stop_method": "atr", "trailing_atr_period": 14,
        "trailing_atr_multiplier": 3.0,
        "max_bars_without_progress": 20, "min_progress_r": 0.5,
        "early_exit_days": 3, "target_r_multiple": None,
    },
}

FX_PARAMS = {
    "swing": ATRZigZagConfig(atr_length=14, atr_mult=1.5, use_close_only=False),
    "sequence": {
        "method": "tolerance", "min_contractions": 2, "max_contractions": 6,
        "lookback_bars": 126, "tolerance": 0.10,
        "max_depth_pct": 0.10, "max_depth_atr": 3, "min_total_reduction": 0.60,
        "max_gap_between_contractions_days": None,
        "require_ascending_lows": True, "ascending_lows_tolerance": 0.03,
    },
    "compression": {"method": "ratio", "atr_period": 14, "ratio_threshold": 0.85},
    "volume_contraction": {"method": "ratio", "volume_column": "volume", "ratio_threshold": 0.85},
    "breakout": {
        "volume_method": "ratio", "volume_ratio_threshold": 1.5,
        "volume_lookback_days": 50,
        "require_volume_confirmation": False,
        "max_entry_distance_pct": 0.03,
    },
    "risk": {
        "max_stop_loss_pct": 0.02, "breakeven_r_multiple": 1.0,
        "trailing_sma_period": 20, "trailing_volume_factor": 1.5,
        "trailing_stop_method": "atr", "trailing_atr_period": 14,
        "trailing_atr_multiplier": 2.0,
        "max_bars_without_progress": 15, "min_progress_r": 0.5,
        "early_exit_days": 3, "target_r_multiple": 3.0,
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


def run_analysis(ohlc, params, label=""):
    detector = ATRZigZagDetector(params["swing"])
    results = run_full_vcp_pipeline(
        ohlc=ohlc, swing_detector=detector,
        sequence_params=params["sequence"],
        compression_params=params["compression"],
        breakout_params=params["breakout"],
        volume_contraction_params=None,
    )
    signals = {dt: s for dt, s in results.items() if s is not None}
    patterns = group_signals_into_patterns(signals, risk_params=params["risk"])
    trades = []
    for p in patterns:
        t = simulate_trade(ohlc, p, params["risk"])
        t["pattern"] = p
        trades.append(t)

    n = len(trades)
    if n > 0:
        wins = sum(1 for t in trades if t["pnl_pct"] > 0)
        cr = float(np.prod([1 + t["pnl_pct"] for t in trades]) - 1)
        avg_r = float(np.mean([t["r_multiple"] for t in trades]))
        avg_pnl = float(np.mean([t["pnl_pct"] for t in trades]))
        max_r = float(max(t["max_r"] for t in trades))
    else:
        wins, cr, avg_r, avg_pnl, max_r = 0, 0, 0, 0, 0

    reasons = {}
    for t in trades:
        reasons[t["exit_reason"]] = reasons.get(t["exit_reason"], 0) + 1

    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"{'='*60}")
    print(f"  Senales: {len(signals)}, Patrones: {len(patterns)}, Trades: {n}")
    if n > 0:
        print(f"  Win/Loss: {wins}W / {n-wins}L  (WR: {wins/n:.0%})")
        print(f"  Retorno acum: {cr:+.2%}")
        print(f"  Avg PnL/trade: {avg_pnl:+.3%}")
        print(f"  Avg R: {avg_r:+.2f}R, Max R alcanzado: {max_r:.1f}R")
        print(f"  Salidas: {reasons}")

    return {"signals": signals, "patterns": patterns, "trades": trades,
            "n_trades": n, "wins": wins, "cr": cr, "avg_r": avg_r, "reasons": reasons}


# ── Section 4: Stock vs FX params ──────────────────────────

print("\n" + "="*70)
print("  SECCION 4: COMPARACION STOCK vs FX PARAMS")
print("="*70)

results = {}
for data_label, ohlc in [("Diario", daily), ("Horario", hourly)]:
    for param_label, params in [("Stock", STOCK_PARAMS), ("FX", FX_PARAMS)]:
        key = f"{data_label}_{param_label}"
        t0 = time.time()
        results[key] = run_analysis(ohlc, params, label=f"EURUSD {data_label} - Params {param_label}")
        print(f"  (took {time.time()-t0:.1f}s)")

rows = []
for key, r in results.items():
    data, params = key.split("_")
    n = r["n_trades"]
    rows.append({
        "Data": data, "Params": params,
        "Senales": len(r["signals"]), "Patrones": len(r["patterns"]),
        "Trades": n, "Wins": r["wins"], "Losses": n - r["wins"],
        "WR": f"{r['wins']/n:.0%}" if n > 0 else "0%",
        "CR": f"{r['cr']:+.2%}", "Avg R": f"{r['avg_r']:+.2f}",
    })

summary = pd.DataFrame(rows)
print("\n\nTABLA RESUMEN:")
print(summary.to_string(index=False))

print("\nExit reasons por config:")
for key, r in results.items():
    print(f"  {key}: {r['reasons']}")


# ── Section 6: Grid target_R x ATR mult ────────────────────

print("\n\n" + "="*70)
print("  SECCION 6: GRILLA TARGET R x ATR MULTIPLIER")
print("="*70)

TARGET_RS = [None, 2.0, 3.0, 5.0]
ATR_MULTS = [1.5, 2.0, 2.5]

print("\n  Precalculando swings/contracciones/ATR para grilla de salida...")
fx_detector = ATRZigZagDetector(FX_PARAMS["swing"])
fx_atr_period = FX_PARAMS["compression"].get("atr_period", 14)
cache_s6 = {}
for data_label, ohlc in [("Diario", daily), ("Horario", hourly)]:
    t0 = time.time()
    swings = fx_detector.detect(ohlc)
    contractions = compute_contractions(swings, ohlc)
    atr = compute_atr(ohlc, fx_atr_period)
    cache_s6[data_label] = (ohlc, swings, contractions, atr)
    print(f"    {data_label}: {time.time()-t0:.1f}s")

grid_results = []
for data_label, ohlc in [("Diario", daily), ("Horario", hourly)]:
    print(f"\n  Procesando {data_label}...")
    _, swings, contractions, atr = cache_s6[data_label]
    for target_r in TARGET_RS:
        for atr_m in ATR_MULTS:
            params = {
                **FX_PARAMS,
                "risk": {**FX_PARAMS["risk"], "target_r_multiple": target_r, "trailing_atr_multiplier": atr_m},
            }
            res = run_full_vcp_pipeline(
                ohlc=ohlc, swing_detector=fx_detector,
                sequence_params=params["sequence"],
                compression_params=params["compression"],
                breakout_params=params["breakout"],
                volume_contraction_params=None,
                precomputed_swings=swings,
                precomputed_contractions=contractions,
                precomputed_atr=atr,
            )
            signals = {dt: s for dt, s in res.items() if s is not None}
            patterns = group_signals_into_patterns(signals, risk_params=params["risk"])
            trades = [simulate_trade(ohlc, p, params["risk"]) | {"pattern": p} for p in patterns]

            n = len(trades)
            wins = sum(1 for t in trades if t["pnl_pct"] > 0) if n else 0
            cr = float(np.prod([1 + t["pnl_pct"] for t in trades]) - 1) if n else 0
            avg_r = float(np.mean([t["r_multiple"] for t in trades])) if n else 0
            reasons = {}
            for t in trades:
                reasons[t["exit_reason"]] = reasons.get(t["exit_reason"], 0) + 1

            grid_results.append({
                "data": data_label, "target_R": str(target_r) if target_r else "None",
                "atr_mult": atr_m, "trades": n, "wins": wins,
                "WR": f"{wins/n:.0%}" if n > 0 else "0%",
                "CR": f"{cr:+.2%}", "avg_R": f"{avg_r:+.2f}",
                "targets": reasons.get("target", 0),
                "stops": reasons.get("stop_loss", 0) + reasons.get("trailing_stop", 0),
                "time_exits": reasons.get("time_exit", 0),
            })
    print(f"  {data_label} done.")

grid_df = pd.DataFrame(grid_results)
for data_label in ["Diario", "Horario"]:
    print(f"\n{'='*60}")
    print(f"  EURUSD {data_label} - Grilla Target R x ATR Multiplier")
    print(f"{'='*60}")
    sub = grid_df[grid_df["data"] == data_label].drop(columns=["data"])
    print(sub.to_string(index=False))


# ── Section 7: Grid depth x reduction ──────────────────────

print("\n\n" + "="*70)
print("  SECCION 7: GRILLA DETECCION (depth x reduction)")
print("="*70)

DEPTH_PCTS = [0.05, 0.08, 0.10, 0.15]
DEPTH_ATRS = [2, 3, 5]
REDUCTIONS = [0.50, 0.60, 0.70]

det_results = []
for data_label, ohlc in [("Diario", daily), ("Horario", hourly)]:
    t0 = time.time()
    _, swings, contractions, atr = cache_s6[data_label]
    print(f"\n  Procesando {data_label} ({len(ohlc):,} barras)...")
    for depth_pct in DEPTH_PCTS:
        for depth_atr in DEPTH_ATRS:
            for reduction in REDUCTIONS:
                params = {
                    **FX_PARAMS,
                    "sequence": {
                        **FX_PARAMS["sequence"],
                        "max_depth_pct": depth_pct,
                        "max_depth_atr": depth_atr,
                        "min_total_reduction": reduction,
                    },
                }
                res = run_full_vcp_pipeline(
                    ohlc=ohlc, swing_detector=fx_detector,
                    sequence_params=params["sequence"],
                    compression_params=params["compression"],
                    breakout_params=params["breakout"],
                    volume_contraction_params=None,
                    precomputed_swings=swings,
                    precomputed_contractions=contractions,
                    precomputed_atr=atr,
                )
                signals = {dt: s for dt, s in res.items() if s is not None}
                patterns = group_signals_into_patterns(signals, risk_params=params["risk"])
                trades = [simulate_trade(ohlc, p, params["risk"]) | {"pattern": p} for p in patterns]

                n = len(trades)
                wins = sum(1 for t in trades if t["pnl_pct"] > 0) if n else 0
                cr = float(np.prod([1 + t["pnl_pct"] for t in trades]) - 1) if n else 0

                det_results.append({
                    "data": data_label, "depth_pct": depth_pct,
                    "depth_atr": depth_atr, "reduction": reduction,
                    "signals": len(signals), "patterns": len(patterns),
                    "trades": n, "wins": wins,
                    "WR": f"{wins/n:.0%}" if n > 0 else "0%",
                    "CR": f"{cr:+.2%}",
                })
    print(f"  {data_label} done in {time.time()-t0:.1f}s")

det_df = pd.DataFrame(det_results)
for data_label in ["Diario", "Horario"]:
    print(f"\n{'='*60}")
    print(f"  EURUSD {data_label} - Grilla Deteccion")
    print(f"{'='*60}")
    sub = det_df[det_df["data"] == data_label].drop(columns=["data"])
    sub_sorted = sub.sort_values("trades", ascending=False)
    print(sub_sorted.to_string(index=False))


# ── Summary ─────────────────────────────────────────────────

print("\n\n" + "="*70)
print("  RESUMEN FINAL")
print("="*70)

print("\nComparacion Stock params vs FX params:")
print(summary.to_string(index=False))

print("\nMejores configs de la grilla de salida (por CR):")
for data_label in ["Diario", "Horario"]:
    sub = grid_df[grid_df["data"] == data_label].copy()
    sub["CR_num"] = sub["CR"].str.replace("%", "").str.replace("+", "").astype(float)
    sub = sub.sort_values("CR_num", ascending=False).head(3)
    print(f"\n  {data_label}:")
    for _, row in sub.iterrows():
        print(f"    target_R={row['target_R']}, atr_mult={row['atr_mult']} -> "
              f"{row['trades']} trades, WR={row['WR']}, CR={row['CR']}")

print("\nMejores configs de la grilla de deteccion (por CR>0):")
for data_label in ["Diario", "Horario"]:
    sub = det_df[det_df["data"] == data_label].copy()
    sub["CR_num"] = sub["CR"].str.replace("%", "").str.replace("+", "").astype(float)
    sub = sub[sub["CR_num"] > 0].sort_values("CR_num", ascending=False).head(3)
    print(f"\n  {data_label}:")
    if len(sub) == 0:
        print("    (ninguna config con CR > 0)")
    for _, row in sub.iterrows():
        print(f"    depth_pct={row['depth_pct']}, depth_atr={row['depth_atr']}, red={row['reduction']} -> "
              f"{row['trades']} trades, WR={row['WR']}, CR={row['CR']}")

print("\nCompleto!")
