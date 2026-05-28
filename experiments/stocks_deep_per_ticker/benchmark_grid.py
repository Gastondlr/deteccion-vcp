"""Benchmark: corre ~1% de la grilla completa para estimar tiempo total.

Grilla completa por ticker:
  Fase 1 (deteccion): 93,312 configs
  Fase 2 (salida):       720 configs

Este script samplea ~1% de cada fase y reporta tiempos.

Usage:
    python benchmark_grid.py
"""
import functools
import itertools
import random
import sys
import time
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
from vcp_detection.analysis import evaluate_signals_to_trades
from stages.trend_template import evaluate_trend_template

pd.set_option("display.float_format", "{:.4f}".format)

TICKER = "AAPL"
TRAIN_CUTOFF = "2020-01-01"
DATA_DIR = project_root / "data" / "csv"

# ── Full grid definition ────────────────────────────────────

# Phase 1: Detection
ATR_MULTS = [2.0, 2.5, 3.0, 4.0]
MAX_DEPTH_ATRS = [None, 4, 6, 8]
REDUCTIONS = [0.40, 0.60, 0.80]
LOOKBACK_BARS = [63, 84, 126]
COMPRESSION_THRESHOLDS = [0.85, 0.90, 0.95]
TOLERANCES = [0.10, 0.15, 0.20]
MAX_DEPTH_PCTS = [0.25, 0.30, 0.35]
ASCENDING_LOWS_TOLERANCES = [0.01, 0.03, 0.08]
USE_CLOSE_ONLY = [False, True]
TREND_TEMPLATE_OPTIONS = [False, True]
VOLUME_CONTRACTION_OPTIONS = [None, {"method": "ratio", "ratio_threshold": 0.85}]

# Phase 2: Exit
TRAILING_MULTS = [1.0, 1.5, 2.0, 2.5, 3.0]
TARGET_RS = [None, 2.0, 3.0, 5.0]
EARLY_EXITS = [None, 3, 5]
BREAKEVEN_RS = [0.5, 1.0, 1.5, 2.0]
MAX_STOP_LOSSES = [0.03, 0.05, 0.07]

BREAKOUT_BASE = {
    "volume_method": "ratio", "volume_ratio_threshold": 1.5,
    "volume_lookback_days": 50,
    "require_volume_confirmation": False,
}
RISK_BASE = {
    "trailing_sma_period": 20,
    "trailing_volume_factor": 1.5,
    "trailing_stop_method": "atr",
    "trailing_atr_period": 14,
    "max_bars_without_progress": 15,
    "min_progress_r": 0.5,
}

# ── Count full grid ─────────────────────────────────────────

n_det_full = (len(ATR_MULTS) * len(MAX_DEPTH_ATRS) * len(REDUCTIONS)
              * len(LOOKBACK_BARS) * len(COMPRESSION_THRESHOLDS)
              * len(TOLERANCES) * len(MAX_DEPTH_PCTS)
              * len(ASCENDING_LOWS_TOLERANCES)
              * len(USE_CLOSE_ONLY) * len(TREND_TEMPLATE_OPTIONS)
              * len(VOLUME_CONTRACTION_OPTIONS))
n_exit_full = (len(TRAILING_MULTS) * len(TARGET_RS) * len(EARLY_EXITS)
               * len(BREAKEVEN_RS) * len(MAX_STOP_LOSSES))

print(f"Grilla completa:")
print(f"  Deteccion: {n_det_full:,} configs")
print(f"  Salida:    {n_exit_full:,} configs")
print(f"  Total:     {n_det_full + n_exit_full:,}")

# ── Build all detection combos and sample 1% ────────────────

det_combos = list(itertools.product(
    ATR_MULTS, MAX_DEPTH_ATRS, REDUCTIONS, LOOKBACK_BARS,
    COMPRESSION_THRESHOLDS, TOLERANCES, MAX_DEPTH_PCTS,
    ASCENDING_LOWS_TOLERANCES, USE_CLOSE_ONLY, TREND_TEMPLATE_OPTIONS,
    range(len(VOLUME_CONTRACTION_OPTIONS)),
))

sample_size_det = max(1, int(len(det_combos) * 0.01))
random.seed(42)
det_sample = random.sample(det_combos, sample_size_det)

exit_combos = list(itertools.product(
    TRAILING_MULTS, TARGET_RS, EARLY_EXITS, BREAKEVEN_RS, MAX_STOP_LOSSES,
))
sample_size_exit = max(1, int(len(exit_combos) * 0.01))
exit_sample = random.sample(exit_combos, sample_size_exit)

print(f"\nSample 1%:")
print(f"  Deteccion: {sample_size_det:,} configs")
print(f"  Salida:    {sample_size_exit:,} configs")

# ── Load data ───────────────────────────────────────────────

print(f"\nCargando {TICKER}...")
daily = pd.read_csv(DATA_DIR / f"{TICKER}.csv", parse_dates=["date"], index_col="date")
train = daily[daily.index < TRAIN_CUTOFF]
test = daily[daily.index >= TRAIN_CUTOFF]
print(f"  Total: {len(daily):,} barras ({daily.index.min().date()} a {daily.index.max().date()})")
print(f"  TRAIN: {len(train):,} barras (hasta {train.index[-1].date()})")
print(f"  TEST:  {len(test):,} barras (desde {test.index[0].date()})")

# ── Precompute trend template ───────────────────────────────

print(f"\nPrecomputando trend template...")
t0 = time.time()
tt_train = evaluate_trend_template(train)
tt_mask_train = tt_train["trend_template"]
print(f"  Trend template: {tt_mask_train.sum()}/{len(tt_mask_train)} dias en Stage 2 ({time.time()-t0:.2f}s)")

# ── Precompute caches ───────────────────────────────────────

unique_swing_keys = set()
for combo in det_sample:
    atr_mult, _, _, _, _, _, _, _, use_close, _, _ = combo
    unique_swing_keys.add((atr_mult, use_close))

print(f"\nPrecomputando {len(unique_swing_keys)} caches de swings...")
caches = {}
t0 = time.time()
for atr_mult, use_close in sorted(unique_swing_keys):
    config = ATRZigZagConfig(atr_length=14, atr_mult=atr_mult, use_close_only=use_close)
    detector = ATRZigZagDetector(config)
    swings = detector.detect(train)
    contractions = compute_contractions(swings, train)
    atr = compute_atr(train, 14)
    caches[(atr_mult, use_close)] = {
        "swings": swings, "contractions": contractions,
        "atr": atr, "detector": detector,
    }
    print(f"  atr_mult={atr_mult:.1f}, close_only={use_close}: "
          f"{len(swings)} swings, {len(contractions)} contractions")
print(f"  Caches en {time.time()-t0:.2f}s")

# ── Precompute ALL caches (for full grid estimate) ──────────

print(f"\nPrecomputando TODOS los {len(ATR_MULTS)*len(USE_CLOSE_ONLY)} caches...")
t_all_caches = time.time()
all_caches = {}
for atr_mult in ATR_MULTS:
    for use_close in USE_CLOSE_ONLY:
        if (atr_mult, use_close) in caches:
            all_caches[(atr_mult, use_close)] = caches[(atr_mult, use_close)]
        else:
            config = ATRZigZagConfig(atr_length=14, atr_mult=atr_mult, use_close_only=use_close)
            detector = ATRZigZagDetector(config)
            swings = detector.detect(train)
            contractions = compute_contractions(swings, train)
            atr = compute_atr(train, 14)
            all_caches[(atr_mult, use_close)] = {
                "swings": swings, "contractions": contractions,
                "atr": atr, "detector": detector,
            }
t_all_caches = time.time() - t_all_caches
print(f"  {len(all_caches)} caches en {t_all_caches:.2f}s")

# ── Run detection sample ────────────────────────────────────

print(f"\n{'='*70}")
print(f"  FASE 1 BENCHMARK: {sample_size_det} configs de deteccion")
print(f"{'='*70}")

fixed_risk = {**RISK_BASE, "max_stop_loss_pct": 0.07,
              "trailing_atr_multiplier": 1.5, "target_r_multiple": 3.0,
              "early_exit_days": None, "breakeven_r_multiple": 1.0}

det_results = []
t_det_start = time.time()
last_report = 0

for idx, combo in enumerate(det_sample):
    (atr_mult, max_depth_atr, reduction, lookback, comp_thresh,
     tolerance, max_depth_pct, asc_lows_tol, use_close, use_tt, vol_contr_idx) = combo

    cache = caches[(atr_mult, use_close)]
    vol_contr = VOLUME_CONTRACTION_OPTIONS[vol_contr_idx]

    seq_params = {
        "method": "tolerance", "min_contractions": 2, "max_contractions": 6,
        "lookback_bars": lookback, "tolerance": tolerance,
        "max_depth_pct": max_depth_pct, "max_depth_atr": max_depth_atr,
        "min_total_reduction": reduction,
        "max_gap_between_contractions_days": None,
        "require_ascending_lows": True, "ascending_lows_tolerance": asc_lows_tol,
    }
    comp_params = {"method": "ratio", "atr_period": 14, "ratio_threshold": comp_thresh}
    tt_mask = tt_mask_train if use_tt else None

    res = run_full_vcp_pipeline(
        ohlc=train, swing_detector=cache["detector"],
        sequence_params=seq_params,
        compression_params=comp_params,
        breakout_params=BREAKOUT_BASE,
        volume_contraction_params=vol_contr,
        precomputed_swings=cache["swings"],
        precomputed_contractions=cache["contractions"],
        precomputed_atr=cache["atr"],
    )
    signals = {dt: s for dt, s in res.items() if s is not None}

    if tt_mask is not None:
        signals = {dt: s for dt, s in signals.items()
                   if dt in tt_mask.index and tt_mask.loc[dt]}

    ev = {"trades": 0, "CR": 0.0}
    if signals:
        results = evaluate_signals_to_trades(
            signals, train, fixed_risk, grouping="sequential",
            precomputed_atr=cache["atr"],
        )
        n = len(results)
        trades_list = [t for _, t in results]
        wins = sum(1 for t in trades_list if t["pnl_pct"] > 0) if n else 0
        cr = float(np.prod([1 + t["pnl_pct"] for t in trades_list]) - 1) if n else 0
        ev = {"trades": n, "wins": wins, "WR": wins / n if n > 0 else 0, "CR": cr}

    det_results.append({**dict(zip(
        ["atr_mult", "max_depth_atr", "reduction", "lookback", "comp_thresh",
         "tolerance", "max_depth_pct", "asc_lows_tol", "use_close", "use_tt", "vol_contr"],
        combo)), **ev, "signals": len(signals)})

    pct = (idx + 1) * 100 // sample_size_det
    if pct >= last_report + 10:
        elapsed = time.time() - t_det_start
        rate = (idx + 1) / elapsed
        eta = (sample_size_det - idx - 1) / rate
        print(f"  {pct}% ({idx+1}/{sample_size_det}) | {elapsed:.1f}s elapsed | "
              f"{rate:.1f} cfg/s | ETA {eta:.0f}s")
        last_report = pct

t_det_total = time.time() - t_det_start

# ── Detection benchmark results ─────────────────────────────

configs_with_signals = sum(1 for r in det_results if r["signals"] > 0)
configs_with_trades = sum(1 for r in det_results if r["trades"] > 0)

print(f"\n  Resultado Fase 1:")
print(f"    {sample_size_det} configs en {t_det_total:.1f}s ({sample_size_det/t_det_total:.1f} cfg/s)")
print(f"    Con senales: {configs_with_signals}/{sample_size_det}")
print(f"    Con trades:  {configs_with_trades}/{sample_size_det}")

# ── Run exit sample ─────────────────────────────────────────

print(f"\n{'='*70}")
print(f"  FASE 2 BENCHMARK: {sample_size_exit} configs de salida")
print(f"{'='*70}")

best_det = max(det_results, key=lambda r: r["CR"])
print(f"  Usando mejor config de deteccion: CR={best_det['CR']:+.2%}, "
      f"{best_det['signals']} senales, {best_det['trades']} trades")

best_cache = caches[(best_det["atr_mult"], best_det["use_close"])]
best_seq = {
    "method": "tolerance", "min_contractions": 2, "max_contractions": 6,
    "lookback_bars": best_det["lookback"], "tolerance": best_det["tolerance"],
    "max_depth_pct": best_det["max_depth_pct"],
    "max_depth_atr": best_det["max_depth_atr"],
    "min_total_reduction": best_det["reduction"],
    "max_gap_between_contractions_days": None,
    "require_ascending_lows": True,
    "ascending_lows_tolerance": best_det["asc_lows_tol"],
}
best_comp = {"method": "ratio", "atr_period": 14,
             "ratio_threshold": best_det["comp_thresh"]}
best_vol_contr = VOLUME_CONTRACTION_OPTIONS[best_det["vol_contr"]]
best_tt_mask = tt_mask_train if best_det["use_tt"] else None

res = run_full_vcp_pipeline(
    ohlc=train, swing_detector=best_cache["detector"],
    sequence_params=best_seq,
    compression_params=best_comp,
    breakout_params=BREAKOUT_BASE,
    volume_contraction_params=best_vol_contr,
    precomputed_swings=best_cache["swings"],
    precomputed_contractions=best_cache["contractions"],
    precomputed_atr=best_cache["atr"],
)
best_signals = {dt: s for dt, s in res.items() if s is not None}
if best_tt_mask is not None:
    best_signals = {dt: s for dt, s in best_signals.items()
                    if dt in best_tt_mask.index and best_tt_mask.loc[dt]}

print(f"  Senales para Fase 2: {len(best_signals)}")

t_exit_start = time.time()
exit_results = []
for combo in exit_sample:
    trail, target, early, be_r, max_sl = combo
    risk = {**RISK_BASE, "max_stop_loss_pct": max_sl,
            "trailing_atr_multiplier": trail, "target_r_multiple": target,
            "early_exit_days": early, "breakeven_r_multiple": be_r}
    results = evaluate_signals_to_trades(
        best_signals, train, risk, grouping="sequential",
        precomputed_atr=best_cache["atr"],
    )
    n = len(results)
    trades_list = [t for _, t in results]
    cr = float(np.prod([1 + t["pnl_pct"] for t in trades_list]) - 1) if n else 0
    exit_results.append({"trail": trail, "target": target, "early": early,
                         "be_r": be_r, "max_sl": max_sl, "trades": n, "CR": cr})
t_exit_total = time.time() - t_exit_start

print(f"\n  Resultado Fase 2:")
print(f"    {sample_size_exit} configs en {t_exit_total:.1f}s "
      f"({sample_size_exit/t_exit_total:.1f} cfg/s)" if t_exit_total > 0
      else f"    {sample_size_exit} configs en {t_exit_total:.3f}s")

# ── Projection ──────────────────────────────────────────────

print(f"\n\n{'#'*70}")
print(f"  PROYECCION A GRILLA COMPLETA — {TICKER}")
print(f"{'#'*70}")

det_rate = sample_size_det / t_det_total if t_det_total > 0 else 1
exit_rate = sample_size_exit / t_exit_total if t_exit_total > 0 else 1

t_det_projected = n_det_full / det_rate
t_exit_projected = n_exit_full / exit_rate
t_cache_projected = t_all_caches
t_total_projected = t_det_projected + t_exit_projected + t_cache_projected

print(f"\n  Tiempos medidos:")
print(f"    Deteccion: {t_det_total:.1f}s para {sample_size_det} cfg ({det_rate:.1f} cfg/s)")
print(f"    Salida:    {t_exit_total:.2f}s para {sample_size_exit} cfg ({exit_rate:.1f} cfg/s)")
print(f"    Caches:    {t_all_caches:.2f}s para {len(all_caches)} combos")

print(f"\n  Proyeccion grilla completa ({TICKER}):")
print(f"    Caches:    {t_cache_projected:.0f}s")
print(f"    Deteccion: {t_det_projected:.0f}s ({t_det_projected/60:.1f} min) para {n_det_full:,} cfg")
print(f"    Salida:    {t_exit_projected:.0f}s ({t_exit_projected/60:.1f} min) para {n_exit_full:,} cfg")
print(f"    TOTAL:     {t_total_projected:.0f}s ({t_total_projected/60:.1f} min)")
print(f"    x5 stocks: {t_total_projected*5:.0f}s ({t_total_projected*5/60:.1f} min / {t_total_projected*5/3600:.1f} hrs)")

print(f"\n  Si es demasiado, opciones para reducir:")
configs_per_dim = {
    "atr_mult": len(ATR_MULTS),
    "max_depth_atr": len(MAX_DEPTH_ATRS),
    "reduction": len(REDUCTIONS),
    "lookback_bars": len(LOOKBACK_BARS),
    "comp_thresh": len(COMPRESSION_THRESHOLDS),
    "tolerance": len(TOLERANCES),
    "max_depth_pct": len(MAX_DEPTH_PCTS),
    "asc_lows_tol": len(ASCENDING_LOWS_TOLERANCES),
    "use_close_only": len(USE_CLOSE_ONLY),
    "trend_template": len(TREND_TEMPLATE_OPTIONS),
    "vol_contraction": len(VOLUME_CONTRACTION_OPTIONS),
}
for name, cnt in sorted(configs_per_dim.items(), key=lambda x: -x[1]):
    reduced = n_det_full // cnt * (cnt - 1)
    savings_pct = (n_det_full - reduced) / n_det_full * 100
    t_saved = t_det_projected * (1 - reduced / n_det_full)
    print(f"    Quitar 1 valor de {name} ({cnt}->{cnt-1}): "
          f"{reduced:,} cfg (-{savings_pct:.0f}%, ahorra {t_saved:.0f}s)")

print("\nBenchmark completo!")
