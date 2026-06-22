"""Deep per-ticker VCP optimization v4 — trend template corregido (Minervini Stage 2).

Mismo grid que v3 (forward volume confirmation), pero corrige la implementacion
de la plantilla de tendencia (trend template):

v2/v3 (incorrecto): chequea las 7 condiciones de Stage 2 en el dia del breakout.
v4 (correcto): chequea las 7 condiciones en el PRIMER PICO del patron (inicio
de la formacion VCP). Durante la formacion (primer pico -> senal), solo exige
que se mantengan las condiciones estructurales:
  - cond_2: SMA150 > SMA200
  - cond_3: SMA200 sigue subiendo (> shift 22)
  - cond_4: SMA50 > SMA150 y SMA50 > SMA200
Si alguna de estas se rompe durante la formacion, el patron se descarta.

Usage:
    python3 run_deep_v4.py MSFT
    python3 run_deep_v4.py AAPL MSFT --top-n 10 --min-trades 3
"""
import argparse
import functools
import itertools
import sys
import time
from dataclasses import replace
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

DATA_DIR = project_root / "data" / "csv"
OUTPUT_DIR = Path(__file__).resolve().parent / "results"

# ── Phase 1: Detection grid ────────────────────────────────

ATR_MULTS = [2.0, 3.0, 4.0]
MAX_DEPTH_ATRS = [None, 6, 8]
REDUCTIONS = [0.40, 0.60, 0.80]
LOOKBACK_BARS = [63, 126]
COMPRESSION_THRESHOLDS = [0.85, 0.90, 0.95]
TOLERANCES = [0.10, 0.15, 0.20]
MAX_DEPTH_PCTS = [0.25, 0.30, 0.35]
ASCENDING_LOWS_TOLERANCES = [0.01, 0.03, 0.08]
USE_CLOSE_ONLY = [False, True]
TREND_TEMPLATE_OPTIONS = [True]
VOLUME_CONTRACTION_OPTIONS = [None, {"method": "ratio", "ratio_threshold": 0.85}]

VOLUME_FILTER_VARIANTS = [
    # Baseline: sin confirmacion de volumen
    {"name": "no_filter", "window": None, "threshold": None, "forward": 0},
    # Backward + forward (backward-only ya evaluados en v2)
    {"name": "w1_t1.2_f3", "window": 1, "threshold": 1.2, "forward": 3},
    {"name": "w1_t1.2_f5", "window": 1, "threshold": 1.2, "forward": 5},
    {"name": "w3_t1.2_f3", "window": 3, "threshold": 1.2, "forward": 3},
    {"name": "w3_t1.2_f5", "window": 3, "threshold": 1.2, "forward": 5},
    {"name": "w1_t1.5_f3", "window": 1, "threshold": 1.5, "forward": 3},
    {"name": "w3_t1.5_f3", "window": 3, "threshold": 1.5, "forward": 3},
]

EXIT_PROFILES = [
    {"name": "tight",  "trailing_atr_multiplier": 1.5, "target_r_multiple": None,
     "early_exit_days": None, "breakeven_r_multiple": 1.0, "max_stop_loss_pct": 0.07},
    {"name": "medium", "trailing_atr_multiplier": 2.5, "target_r_multiple": None,
     "early_exit_days": None, "breakeven_r_multiple": 1.0, "max_stop_loss_pct": 0.07},
    {"name": "loose",  "trailing_atr_multiplier": 3.5, "target_r_multiple": None,
     "early_exit_days": None, "breakeven_r_multiple": 1.0, "max_stop_loss_pct": 0.07},
]

# ── Phase 2: Exit grid ─────────────────────────────────────

TRAILING_MULTS = [1.0, 1.5, 2.0, 2.5, 3.0]
TARGET_RS = [None, 2.0, 3.0, 5.0]
EARLY_EXITS = [None, 3, 5]
BREAKEVEN_RS = [0.5, 1.0, 1.5, 2.0]
MAX_STOP_LOSSES = [0.03, 0.05, 0.07]

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

CONFIG_COLS = [
    "atr_mult", "use_close_only", "max_depth_atr", "reduction",
    "lookback_bars", "tolerance", "max_depth_pct", "asc_lows_tol",
    "comp_thresh", "vol_contraction", "trend_template", "vol_filter",
]

# ── Counts ──────────────────────────────────────────────────

n_pipeline = (len(ATR_MULTS) * len(USE_CLOSE_ONLY) * len(MAX_DEPTH_ATRS)
              * len(REDUCTIONS) * len(LOOKBACK_BARS) * len(COMPRESSION_THRESHOLDS)
              * len(TOLERANCES) * len(MAX_DEPTH_PCTS) * len(ASCENDING_LOWS_TOLERANCES)
              * len(VOLUME_CONTRACTION_OPTIONS))
n_det_rows = n_pipeline * len(TREND_TEMPLATE_OPTIONS) * len(VOLUME_FILTER_VARIANTS)
n_eval_total = n_det_rows * len(EXIT_PROFILES)
n_exit = (len(TRAILING_MULTS) * len(TARGET_RS) * len(EARLY_EXITS)
          * len(BREAKEVEN_RS) * len(MAX_STOP_LOSSES))


# ── Helpers ─────────────────────────────────────────────────


def fmt_pct(x):
    return f"{x:+.2%}"


def fmt_wr(x):
    return f"{x:.0%}"


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
    return {"trades": n, "wins": wins, "WR": wins / n if n > 0 else 0,
            "CR": cr, "avg_R": avg_r, "reasons": reasons,
            "trade_details": results}


def apply_volume_post_filter(signals, ohlc, window, threshold, forward=0, lookback_days=50):
    """Filter signals by breakout volume confirmation (post-hoc).

    Supports backward window (same as v2) plus forward lookahead.
    For forward-confirmed signals, adjusts entry date and price to the
    confirmation day.
    """
    filtered = {}
    for dt, sig in signals.items():
        eval_loc = ohlc.index.get_loc(dt)
        lookback_start = max(0, eval_loc - lookback_days)
        vol_recent = ohlc["volume"].iloc[lookback_start:eval_loc]
        vol_avg = float(vol_recent.mean()) if len(vol_recent) > 0 else 0.0
        if vol_avg <= 0:
            continue

        threshold_vol = threshold * vol_avg

        # Backward check
        win_start = max(0, eval_loc - window + 1)
        win_vols = ohlc["volume"].iloc[win_start:eval_loc + 1]
        if any(float(v) >= threshold_vol for v in win_vols):
            filtered[dt] = sig
            continue

        # Forward check
        if forward > 0:
            pivot_price = sig.pivot_price
            max_fwd_loc = min(eval_loc + forward, len(ohlc) - 1)
            for fwd_loc in range(eval_loc + 1, max_fwd_loc + 1):
                fwd_date = ohlc.index[fwd_loc]
                fwd_close = float(ohlc.iloc[fwd_loc]["close"])

                if fwd_close <= pivot_price:
                    break

                fwd_vol = float(ohlc.iloc[fwd_loc]["volume"])
                if fwd_vol >= threshold_vol:
                    new_entry = fwd_close
                    new_stop_dist = (new_entry - sig.suggested_stop) / new_entry
                    new_sig = replace(
                        sig,
                        signal_date=fwd_date,
                        entry_price=new_entry,
                        suggested_stop_distance_pct=new_stop_dist,
                        volume_confirmation={
                            **sig.volume_confirmation,
                            "forward_confirmed": True,
                            "breakout_date": dt,
                            "confirmation_delay_days": fwd_loc - eval_loc,
                        },
                    )
                    filtered[fwd_date] = new_sig
                    break

    return filtered


def apply_trend_template_filter(signals, tt_data):
    """Filter signals using correct Minervini Stage 2 implementation.

    Checks all 7 conditions at the first peak (start of VCP formation).
    During formation (first peak to signal date), only conditions 2, 3, 4
    must hold on every bar.
    """
    filtered = {}
    for dt, sig in signals.items():
        first_peak_date = sig.pivot_info.sequence.contractions[0].high_swing.date
        if first_peak_date not in tt_data.index:
            continue
        if not tt_data.loc[first_peak_date, "trend_template"]:
            continue
        formation_mask = (tt_data.index >= first_peak_date) & (tt_data.index <= dt)
        formation_data = tt_data.loc[formation_mask]
        if formation_data.empty:
            continue
        if not (formation_data["cond_2"].all() and
                formation_data["cond_3"].all() and
                formation_data["cond_4"].all()):
            continue
        filtered[dt] = sig
    return filtered


def run_ticker(ticker, train_cutoff, top_n, min_trades):
    """Run full v4 optimization for a single ticker (train only)."""

    print(f"\n{'#'*70}")
    print(f"  {ticker} — Deep Per-Ticker Optimization v4 (trend template corregido)")
    print(f"{'#'*70}")
    print(f"  Pipeline runs:  {n_pipeline:,}")
    print(f"  Detection rows: {n_det_rows:,} (x{len(VOLUME_FILTER_VARIANTS)} vol x{len(TREND_TEMPLATE_OPTIONS)} TT)")
    print(f"  Evaluations:    {n_eval_total:,} (x{len(EXIT_PROFILES)} exit profiles)")
    print(f"  Exit grid:      {n_exit:,} configs")
    print(f"  Volume variants: {len(VOLUME_FILTER_VARIANTS)} "
          f"({sum(1 for v in VOLUME_FILTER_VARIANTS if v['forward'] == 0)} backward, "
          f"{sum(1 for v in VOLUME_FILTER_VARIANTS if v['forward'] > 0)} forward)")

    # ── Load data ───────────────────────────────────────────

    print(f"\nCargando {ticker}...")
    csv_path = DATA_DIR / f"{ticker}.csv"
    if not csv_path.exists():
        print(f"  ERROR: {csv_path} no existe")
        return
    daily = pd.read_csv(csv_path, parse_dates=["date"], index_col="date")
    train = daily[daily.index < train_cutoff]
    test = daily[daily.index >= train_cutoff]
    print(f"  Total: {len(daily):,} barras ({daily.index.min().date()} a {daily.index.max().date()})")
    print(f"  TRAIN: {len(train):,} barras ({train.index.min().date()} a {train.index[-1].date()})")
    print(f"  TEST:  {len(test):,} barras ({test.index[0].date()} a {test.index[-1].date()})")

    # ── Precompute ──────────────────────────────────────────

    print(f"\nPrecomputando trend template...")
    t0 = time.time()
    tt_train = evaluate_trend_template(train)
    tt_mask_train = tt_train["trend_template"]
    print(f"  {tt_mask_train.sum()}/{len(tt_mask_train)} dias en Stage 2 ({time.time()-t0:.2f}s)")

    n_caches = len(ATR_MULTS) * len(USE_CLOSE_ONLY)
    print(f"\nPrecomputando caches de swings ({n_caches} combos)...")
    caches = {}
    t0 = time.time()
    for atr_mult in ATR_MULTS:
        for use_close in USE_CLOSE_ONLY:
            config = ATRZigZagConfig(atr_length=14, atr_mult=atr_mult, use_close_only=use_close)
            detector = ATRZigZagDetector(config)
            swings = detector.detect(train)
            contractions = compute_contractions(swings, train)
            atr = compute_atr(train, 14)
            caches[(atr_mult, use_close)] = {
                "swings": swings, "contractions": contractions,
                "atr": atr, "detector": detector,
            }
            print(f"  atr={atr_mult:.1f}, close_only={use_close}: "
                  f"{len(swings)} sw, {len(contractions)} contr")
    print(f"  Caches en {time.time()-t0:.2f}s")

    # ══════════════════════════════════════════════════════════
    #  FASE 1: GRILLA DE DETECCION — TRAIN
    # ══════════════════════════════════════════════════════════

    print(f"\n{'='*70}")
    print(f"  FASE 1: DETECCION — {ticker} TRAIN")
    print(f"  {n_pipeline:,} pipeline runs -> {n_det_rows:,} rows ({n_eval_total:,} evals)")
    print(f"{'='*70}")

    all_det_results = []
    t_total = time.time()
    pipelines_done = 0
    last_pct_report = -1

    for atr_mult in ATR_MULTS:
        for use_close in USE_CLOSE_ONLY:
            cache = caches[(atr_mult, use_close)]

            for max_depth_atr in MAX_DEPTH_ATRS:
                for reduction in REDUCTIONS:
                    for lookback in LOOKBACK_BARS:
                        for tolerance in TOLERANCES:
                            for max_depth_pct in MAX_DEPTH_PCTS:
                                for asc_tol in ASCENDING_LOWS_TOLERANCES:
                                    seq_params = {
                                        "method": "tolerance",
                                        "min_contractions": 2,
                                        "max_contractions": 6,
                                        "lookback_bars": lookback,
                                        "tolerance": tolerance,
                                        "max_depth_pct": max_depth_pct,
                                        "max_depth_atr": max_depth_atr,
                                        "min_total_reduction": reduction,
                                        "max_gap_between_contractions_days": None,
                                        "require_ascending_lows": True,
                                        "ascending_lows_tolerance": asc_tol,
                                    }

                                    for comp_thresh in COMPRESSION_THRESHOLDS:
                                        comp_params = {
                                            "method": "ratio",
                                            "atr_period": 14,
                                            "ratio_threshold": comp_thresh,
                                        }

                                        for vol_contr in VOLUME_CONTRACTION_OPTIONS:
                                            res = run_full_vcp_pipeline(
                                                ohlc=train,
                                                swing_detector=cache["detector"],
                                                sequence_params=seq_params,
                                                compression_params=comp_params,
                                                breakout_params=BREAKOUT_BASE,
                                                volume_contraction_params=vol_contr,
                                                precomputed_swings=cache["swings"],
                                                precomputed_contractions=cache["contractions"],
                                                precomputed_atr=cache["atr"],
                                            )
                                            raw_signals = {dt: s for dt, s in res.items() if s is not None}

                                            for use_tt in TREND_TEMPLATE_OPTIONS:
                                                tt_filtered = raw_signals
                                                if use_tt:
                                                    tt_filtered = apply_trend_template_filter(raw_signals, tt_train)

                                                for vf in VOLUME_FILTER_VARIANTS:
                                                    if vf["window"] is None:
                                                        vol_filtered = tt_filtered
                                                    else:
                                                        vol_filtered = apply_volume_post_filter(
                                                            tt_filtered, train,
                                                            vf["window"], vf["threshold"],
                                                            forward=vf["forward"])

                                                    exit_metrics = []
                                                    for ep in EXIT_PROFILES:
                                                        risk = {**RISK_BASE,
                                                                "trailing_atr_multiplier": ep["trailing_atr_multiplier"],
                                                                "target_r_multiple": ep["target_r_multiple"],
                                                                "early_exit_days": ep["early_exit_days"],
                                                                "breakeven_r_multiple": ep["breakeven_r_multiple"],
                                                                "max_stop_loss_pct": ep["max_stop_loss_pct"]}
                                                        ev = evaluate_signals_seq(
                                                            train, vol_filtered, risk,
                                                            precomputed_atr=cache["atr"])
                                                        exit_metrics.append(ev)

                                                    avg_trades = np.mean([e["trades"] for e in exit_metrics])
                                                    avg_wins = np.mean([e["wins"] for e in exit_metrics])
                                                    avg_wr = np.mean([e["WR"] for e in exit_metrics])
                                                    avg_cr = np.mean([e["CR"] for e in exit_metrics])
                                                    avg_r = np.mean([e["avg_R"] for e in exit_metrics])

                                                    all_det_results.append({
                                                        "atr_mult": atr_mult,
                                                        "use_close_only": use_close,
                                                        "max_depth_atr": max_depth_atr,
                                                        "reduction": reduction,
                                                        "lookback_bars": lookback,
                                                        "tolerance": tolerance,
                                                        "max_depth_pct": max_depth_pct,
                                                        "asc_lows_tol": asc_tol,
                                                        "comp_thresh": comp_thresh,
                                                        "vol_contraction": vol_contr is not None,
                                                        "trend_template": use_tt,
                                                        "vol_filter": vf["name"],
                                                        "signals": len(vol_filtered),
                                                        "avg_trades": avg_trades,
                                                        "avg_wins": avg_wins,
                                                        "avg_WR": avg_wr,
                                                        "avg_CR": avg_cr,
                                                        "avg_R": avg_r,
                                                        "CR_tight": exit_metrics[0]["CR"],
                                                        "CR_medium": exit_metrics[1]["CR"],
                                                        "CR_loose": exit_metrics[2]["CR"],
                                                        "WR_tight": exit_metrics[0]["WR"],
                                                        "WR_medium": exit_metrics[1]["WR"],
                                                        "WR_loose": exit_metrics[2]["WR"],
                                                    })

                                            pipelines_done += 1
                                            pct = pipelines_done * 100 // n_pipeline
                                            if pct >= last_pct_report + 5:
                                                elapsed = time.time() - t_total
                                                rate = pipelines_done / elapsed
                                                eta = (n_pipeline - pipelines_done) / rate
                                                print(f"  {pct}% ({pipelines_done:,}/{n_pipeline:,}) | "
                                                      f"{elapsed:.0f}s | {rate:.1f} pipe/s | "
                                                      f"ETA {eta:.0f}s ({eta/60:.1f}m)")
                                                last_pct_report = pct

    t_det_total = time.time() - t_total
    det_df = pd.DataFrame(all_det_results)

    print(f"\n  Fase 1 completada: {len(det_df):,} rows en {t_det_total:.0f}s ({t_det_total/60:.1f}m)")
    print(f"  Con senales: {(det_df['signals'] > 0).sum():,}/{len(det_df):,}")
    print(f"  Con trades:  {(det_df['avg_trades'] > 0).sum():,}/{len(det_df):,}")

    # ── Sensitivity analysis ────────────────────────────────

    print(f"\n{'─'*70}")
    print(f"  ANALISIS DE SENSIBILIDAD (promedios across 3 exit profiles)")
    print(f"{'─'*70}")

    sensitivity_dims = [
        ("atr_mult", ATR_MULTS, "atr_mult"),
        ("max_depth_atr", MAX_DEPTH_ATRS, "max_depth_atr"),
        ("reduction", REDUCTIONS, "reduction"),
        ("lookback_bars", LOOKBACK_BARS, "lookback_bars"),
        ("comp_thresh", COMPRESSION_THRESHOLDS, "comp_thresh"),
        ("tolerance", TOLERANCES, "tolerance"),
        ("max_depth_pct", MAX_DEPTH_PCTS, "max_depth_pct"),
        ("asc_lows_tol", ASCENDING_LOWS_TOLERANCES, "asc_lows_tol"),
        ("use_close_only", USE_CLOSE_ONLY, "use_close_only"),
        ("trend_template", TREND_TEMPLATE_OPTIONS, "trend_template"),
        ("vol_contraction", [False, True], "vol_contraction"),
        ("vol_filter", [v["name"] for v in VOLUME_FILTER_VARIANTS], "vol_filter"),
    ]

    for dim_name, dim_values, col_name in sensitivity_dims:
        print(f"\n  --- {dim_name} ---")
        for val in dim_values:
            if val is None:
                sub = det_df[det_df[col_name].isna()]
            else:
                sub = det_df[det_df[col_name] == val]
            if len(sub) == 0:
                continue
            has_trades = sub[sub["avg_trades"] > 0]
            label = str(val) if val is not None else "None"
            print(f"    {label:>14s}: avg_sig={sub['signals'].mean():>6.1f}, "
                  f"avg_T={sub['avg_trades'].mean():>5.1f}, "
                  f"avg_CR={sub['avg_CR'].mean():>+.4f}, "
                  f"avg_WR={sub['avg_WR'].mean():>.3f}, "
                  f"best_CR={sub['avg_CR'].max():>+.4f}, "
                  f"con_T={len(has_trades)}/{len(sub)}")

    # ── Forward vs backward comparison ──────────────────────

    print(f"\n{'─'*70}")
    print(f"  COMPARATIVA: FORWARD vs BACKWARD-ONLY")
    print(f"{'─'*70}")

    has_t = det_df[det_df["avg_trades"] > 0]
    backward_names = [v["name"] for v in VOLUME_FILTER_VARIANTS if v["forward"] == 0 and v["window"] is not None]
    forward_names = [v["name"] for v in VOLUME_FILTER_VARIANTS if v["forward"] > 0]

    print(f"\n  Backward-only variants (avg across configs with trades):")
    for name in backward_names:
        sub = has_t[has_t["vol_filter"] == name]
        if len(sub) > 0:
            print(f"    {name:>14s}: avg_CR={sub['avg_CR'].mean():>+.4f}, "
                  f"avg_WR={sub['avg_WR'].mean():>.3f}, "
                  f"avg_T={sub['avg_trades'].mean():>5.1f}, "
                  f"n={len(sub)}")

    print(f"\n  Forward variants (avg across configs with trades):")
    for name in forward_names:
        sub = has_t[has_t["vol_filter"] == name]
        if len(sub) > 0:
            print(f"    {name:>14s}: avg_CR={sub['avg_CR'].mean():>+.4f}, "
                  f"avg_WR={sub['avg_WR'].mean():>.3f}, "
                  f"avg_T={sub['avg_trades'].mean():>5.1f}, "
                  f"n={len(sub)}")

    # ── Paired comparison: forward vs its backward base ─────

    print(f"\n  Paired: forward variant vs backward base (same detection config)")
    forward_pairs = [
        ("w1_t1.2_f3", "w1_t1.2"), ("w1_t1.2_f5", "w1_t1.2"),
        ("w3_t1.2_f3", "w3_t1.2"), ("w3_t1.2_f5", "w3_t1.2"),
        ("w1_t1.5_f3", "w1_t1.5"), ("w3_t1.5_f3", "w3_t1.5"),
    ]
    for fwd_name, bwd_name in forward_pairs:
        fwd_sub = det_df[det_df["vol_filter"] == fwd_name]
        bwd_sub = det_df[det_df["vol_filter"] == bwd_name]
        if len(fwd_sub) == 0 or len(bwd_sub) == 0:
            continue
        fwd_cr = fwd_sub["avg_CR"].values
        bwd_cr = bwd_sub["avg_CR"].values
        diff = fwd_cr - bwd_cr
        improved = (diff > 0.001).sum()
        degraded = (diff < -0.001).sum()
        equal = len(diff) - improved - degraded
        print(f"    {fwd_name:>14s} vs {bwd_name:>10s}: "
              f"avg_delta_CR={diff.mean():>+.4f}, "
              f"improved={improved}, degraded={degraded}, equal={equal}")

    # ── Stability across exit profiles ──────────────────────

    print(f"\n{'─'*70}")
    print(f"  ESTABILIDAD: CR por exit profile")
    print(f"{'─'*70}")

    if len(has_t) > 0:
        print(f"\n  Correlacion entre CRs de los 3 perfiles (configs con trades):")
        cr_corr = has_t[["CR_tight", "CR_medium", "CR_loose"]].corr()
        print(f"    tight-medium:  {cr_corr.loc['CR_tight', 'CR_medium']:.3f}")
        print(f"    tight-loose:   {cr_corr.loc['CR_tight', 'CR_loose']:.3f}")
        print(f"    medium-loose:  {cr_corr.loc['CR_medium', 'CR_loose']:.3f}")

    # ── Top 30 by avg_CR ────────────────────────────────────

    det_df_by_cr = det_df.sort_values("avg_CR", ascending=False)

    print(f"\n{'─'*70}")
    print(f"  TOP 30 por avg_CR")
    print(f"{'─'*70}")
    for i, (_, row) in enumerate(det_df_by_cr.head(30).iterrows(), 1):
        mda = "None" if pd.isna(row['max_depth_atr']) else str(int(row['max_depth_atr']))
        uco = "C" if row['use_close_only'] else "HL"
        tt = "TT" if row['trend_template'] else "  "
        vc = "VC" if row['vol_contraction'] else "  "
        print(f"  {i:>2d}. atr={row['atr_mult']:.1f} {uco} mda={mda:>4s} "
              f"red={row['reduction']:.2f} lb={int(row['lookback_bars']):>3d} "
              f"comp={row['comp_thresh']:.2f} {tt} {vc} "
              f"vf={row['vol_filter']:<14s} "
              f"-> {int(row['signals']):>3d}sen T={row['avg_trades']:.1f} "
              f"WR={row['avg_WR']:.0%} CR={row['avg_CR']:+.2%}")

    print(f"\n{'─'*70}")
    print(f"  TOP 30 por avg_WR (min {min_trades} trades)")
    print(f"{'─'*70}")
    eligible_wr = det_df[det_df["avg_trades"] >= min_trades]
    eligible_wr_sorted = eligible_wr.sort_values(["avg_WR", "avg_CR"], ascending=[False, False])
    for i, (_, row) in enumerate(eligible_wr_sorted.head(30).iterrows(), 1):
        mda = "None" if pd.isna(row['max_depth_atr']) else str(int(row['max_depth_atr']))
        uco = "C" if row['use_close_only'] else "HL"
        tt = "TT" if row['trend_template'] else "  "
        vc = "VC" if row['vol_contraction'] else "  "
        print(f"  {i:>2d}. atr={row['atr_mult']:.1f} {uco} mda={mda:>4s} "
              f"red={row['reduction']:.2f} lb={int(row['lookback_bars']):>3d} "
              f"comp={row['comp_thresh']:.2f} {tt} {vc} "
              f"vf={row['vol_filter']:<14s} "
              f"-> {int(row['signals']):>3d}sen T={row['avg_trades']:.1f} "
              f"WR={row['avg_WR']:.0%} CR={row['avg_CR']:+.2%}")

    # ══════════════════════════════════════════════════════════
    #  SELECCION DE CANDIDATOS
    # ══════════════════════════════════════════════════════════

    eligible = det_df[det_df["avg_trades"] >= min_trades].copy()

    RESULT_COLS = ["signals", "avg_trades", "avg_WR", "avg_CR", "avg_R"]
    eligible_dedup = eligible.drop_duplicates(subset=RESULT_COLS)

    print(f"\n{'='*70}")
    print(f"  SELECCION DE CANDIDATOS")
    print(f"  Eligible: {len(eligible):,}/{len(det_df):,} (min {min_trades} trades promedio)")
    print(f"  Dedup por resultados: {len(eligible_dedup):,} configs unicas")
    print(f"{'='*70}")

    top_cr = eligible_dedup.nlargest(top_n, "avg_CR")
    top_wr = eligible_dedup.nlargest(top_n, ["avg_WR", "avg_CR"])
    candidates = pd.concat([top_cr, top_wr]).drop_duplicates(subset=RESULT_COLS)

    print(f"  Top {top_n} por avg_CR + Top {top_n} por avg_WR = {len(candidates)} candidatos unicos")

    if len(candidates) == 0:
        print(f"\n  SIN CANDIDATOS ELEGIBLES para {ticker}. Guardando solo Fase 1.")
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        det_path = OUTPUT_DIR / f"{ticker.lower()}_phase1_detection.csv"
        det_df.to_csv(det_path, index=False)
        print(f"  Guardado: {det_path}")
        total_time = time.time() - t_total
        print(f"\n  Tiempo total {ticker}: {total_time:.0f}s ({total_time/60:.1f}m)")
        print(f"\n{'#'*70}")
        print(f"  {ticker} — COMPLETO (sin candidatos)")
        print(f"{'#'*70}")
        return

    for i, (_, row) in enumerate(candidates.iterrows(), 1):
        source = "CR" if i <= top_n else "WR"
        mda = "None" if pd.isna(row['max_depth_atr']) else str(int(row['max_depth_atr']))
        print(f"  {i:>2d}. [{source:>2s}] atr={row['atr_mult']:.1f} "
              f"mda={mda:>4s} red={row['reduction']:.2f} "
              f"lb={int(row['lookback_bars'])} "
              f"TT={'Y' if row['trend_template'] else 'N'} "
              f"VC={'Y' if row['vol_contraction'] else 'N'} "
              f"vf={row['vol_filter']:<14s} "
              f"-> T={row['avg_trades']:.1f} "
              f"WR={row['avg_WR']:.0%} CR={row['avg_CR']:+.2%}")

    # ══════════════════════════════════════════════════════════
    #  FASE 2: GRILLA DE SALIDA — TRAIN
    # ══════════════════════════════════════════════════════════

    print(f"\n{'='*70}")
    print(f"  FASE 2: SALIDA — {ticker} TRAIN ({n_exit} configs x {len(candidates)} candidatos)")
    print(f"{'='*70}")

    all_phase2 = []
    t0_phase2 = time.time()

    for cand_idx, (_, cand) in enumerate(candidates.iterrows()):
        cand_cache = caches[(cand["atr_mult"], cand["use_close_only"])]
        cand_mda = None if (isinstance(cand["max_depth_atr"], float) and np.isnan(cand["max_depth_atr"])) else cand["max_depth_atr"]

        cand_seq = {
            "method": "tolerance", "min_contractions": 2, "max_contractions": 6,
            "lookback_bars": int(cand["lookback_bars"]),
            "tolerance": cand["tolerance"],
            "max_depth_pct": cand["max_depth_pct"],
            "max_depth_atr": cand_mda,
            "min_total_reduction": cand["reduction"],
            "max_gap_between_contractions_days": None,
            "require_ascending_lows": True,
            "ascending_lows_tolerance": cand["asc_lows_tol"],
        }
        cand_comp = {"method": "ratio", "atr_period": 14, "ratio_threshold": cand["comp_thresh"]}
        cand_vol_contr = {"method": "ratio", "ratio_threshold": 0.85} if cand["vol_contraction"] else None

        res = run_full_vcp_pipeline(
            ohlc=train, swing_detector=cand_cache["detector"],
            sequence_params=cand_seq, compression_params=cand_comp,
            breakout_params=BREAKOUT_BASE,
            volume_contraction_params=cand_vol_contr,
            precomputed_swings=cand_cache["swings"],
            precomputed_contractions=cand_cache["contractions"],
            precomputed_atr=cand_cache["atr"],
        )
        raw_sigs = {dt: s for dt, s in res.items() if s is not None}

        if cand["trend_template"]:
            raw_sigs = apply_trend_template_filter(raw_sigs, tt_train)

        vf_name = cand["vol_filter"]
        vf = next(v for v in VOLUME_FILTER_VARIANTS if v["name"] == vf_name)
        if vf["window"] is not None:
            filtered_sigs = apply_volume_post_filter(
                raw_sigs, train, vf["window"], vf["threshold"],
                forward=vf["forward"])
        else:
            filtered_sigs = raw_sigs

        print(f"  Candidato {cand_idx+1}/{len(candidates)}: "
              f"{len(filtered_sigs)} senales (vf={vf_name}), evaluando {n_exit} exits...")

        for trail, target, early, be_r, max_sl in itertools.product(
            TRAILING_MULTS, TARGET_RS, EARLY_EXITS, BREAKEVEN_RS, MAX_STOP_LOSSES
        ):
            risk = {**RISK_BASE, "max_stop_loss_pct": max_sl,
                    "trailing_atr_multiplier": trail,
                    "target_r_multiple": target,
                    "early_exit_days": early,
                    "breakeven_r_multiple": be_r}
            ev = evaluate_signals_seq(
                train, filtered_sigs, risk,
                precomputed_atr=cand_cache["atr"])

            all_phase2.append({
                "candidate_idx": cand_idx,
                **{c: cand[c] for c in CONFIG_COLS},
                "trailing_atr_multiplier": trail,
                "target_r_multiple": target,
                "early_exit_days": early,
                "breakeven_r_multiple": be_r,
                "max_stop_loss_pct": max_sl,
                "trades": ev["trades"], "wins": ev["wins"],
                "WR": ev["WR"], "CR": ev["CR"], "avg_R": ev["avg_R"],
            })

    t_phase2 = time.time() - t0_phase2
    phase2_df = pd.DataFrame(all_phase2)
    print(f"\n  Fase 2 completada: {len(phase2_df):,} rows en {t_phase2:.0f}s ({t_phase2/60:.1f}m)")

    # ── Best exit per candidate ─────────────────────────────

    print(f"\n  Top exit por candidato:")
    for cand_idx in range(len(candidates)):
        cand_exits = phase2_df[phase2_df["candidate_idx"] == cand_idx]
        if len(cand_exits) == 0:
            continue
        best = cand_exits.nlargest(1, "CR").iloc[0]
        t_r = best['target_r_multiple'] if pd.notna(best['target_r_multiple']) else 'None'
        e_e = int(best['early_exit_days']) if pd.notna(best['early_exit_days']) else 'None'
        vf = best['vol_filter']
        print(f"    C{cand_idx+1:>2d}: trail={best['trailing_atr_multiplier']:.1f}, "
              f"target={t_r}, early={e_e}, "
              f"be_R={best['breakeven_r_multiple']:.1f}, sl={best['max_stop_loss_pct']:.2f}, "
              f"vf={vf} "
              f"-> {int(best['trades'])}T WR={fmt_wr(best['WR'])} CR={fmt_pct(best['CR'])}")

    # ══════════════════════════════════════════════════════════
    #  RANKING FINAL
    # ══════════════════════════════════════════════════════════

    print(f"\n{'='*70}")
    print(f"  RANKING FINAL — {ticker} TRAIN")
    print(f"{'='*70}")

    best_per_cand = []
    for cand_idx in range(len(candidates)):
        cand_exits = phase2_df[phase2_df["candidate_idx"] == cand_idx]
        if len(cand_exits) == 0:
            continue
        best_row = cand_exits.nlargest(1, "CR").iloc[0].to_dict()
        best_per_cand.append(best_row)

    final_df = pd.DataFrame(best_per_cand)

    for col in ["CR", "WR", "avg_R"]:
        col_min, col_max = final_df[col].min(), final_df[col].max()
        if col_max > col_min:
            final_df[f"{col}_norm"] = (final_df[col] - col_min) / (col_max - col_min)
        else:
            final_df[f"{col}_norm"] = 0.5

    final_df["composite"] = (
        0.5 * final_df["CR_norm"]
        + 0.3 * final_df["WR_norm"]
        + 0.2 * final_df["avg_R_norm"]
    )
    final_df_sorted = final_df.sort_values("composite", ascending=False)

    print(f"\n  Top {min(10, len(final_df_sorted))} combos por composite "
          f"(50% CR + 30% WR + 20% avg_R):\n")
    print(f"  {'#':>3s}  {'Comp':>5s}  {'T':>3s}  {'WR':>5s}  {'CR':>9s}  {'avgR':>6s}  "
          f"{'trail':>5s} {'target':>6s} {'early':>5s} {'be_R':>4s} {'sl':>5s}  "
          f"{'vf':>14s} {'TT':>2s} {'VC':>2s}")
    print(f"  {'─'*105}")

    for i, (_, row) in enumerate(final_df_sorted.head(10).iterrows(), 1):
        t_r = f"{row['target_r_multiple']:.1f}" if pd.notna(row['target_r_multiple']) else "None"
        e_e = f"{int(row['early_exit_days'])}" if pd.notna(row['early_exit_days']) else "None"
        print(f"  {i:>3d}  {row['composite']:.3f}  {int(row['trades']):>3d}  "
              f"{row['WR']:.0%}  {row['CR']:>+9.2%}  {row['avg_R']:>+5.2f}  "
              f"{row['trailing_atr_multiplier']:>5.1f} {t_r:>6s} {e_e:>5s} "
              f"{row['breakeven_r_multiple']:>4.1f} {row['max_stop_loss_pct']:>5.2f}  "
              f"{row['vol_filter']:>14s} "
              f"{'Y' if row['trend_template'] else 'N':>2s} "
              f"{'Y' if row['vol_contraction'] else 'N':>2s}")

    # ── Trade details for top 3 ─────────────────────────────

    print(f"\n{'─'*70}")
    print(f"  DETALLE DE TRADES — Top 3 combos")
    print(f"{'─'*70}")

    for rank, (_, row) in enumerate(final_df_sorted.head(3).iterrows(), 1):
        cand_idx = int(row["candidate_idx"])
        cand = candidates.iloc[cand_idx]
        cand_cache = caches[(cand["atr_mult"], cand["use_close_only"])]
        cand_mda = None if (isinstance(cand["max_depth_atr"], float) and np.isnan(cand["max_depth_atr"])) else cand["max_depth_atr"]

        cand_seq = {
            "method": "tolerance", "min_contractions": 2, "max_contractions": 6,
            "lookback_bars": int(cand["lookback_bars"]),
            "tolerance": cand["tolerance"],
            "max_depth_pct": cand["max_depth_pct"],
            "max_depth_atr": cand_mda,
            "min_total_reduction": cand["reduction"],
            "max_gap_between_contractions_days": None,
            "require_ascending_lows": True,
            "ascending_lows_tolerance": cand["asc_lows_tol"],
        }
        cand_comp = {"method": "ratio", "atr_period": 14, "ratio_threshold": cand["comp_thresh"]}
        cand_vol_contr = {"method": "ratio", "ratio_threshold": 0.85} if cand["vol_contraction"] else None

        res = run_full_vcp_pipeline(
            ohlc=train, swing_detector=cand_cache["detector"],
            sequence_params=cand_seq, compression_params=cand_comp,
            breakout_params=BREAKOUT_BASE,
            volume_contraction_params=cand_vol_contr,
            precomputed_swings=cand_cache["swings"],
            precomputed_contractions=cand_cache["contractions"],
            precomputed_atr=cand_cache["atr"],
        )
        raw_sigs = {dt: s for dt, s in res.items() if s is not None}
        if cand["trend_template"]:
            raw_sigs = apply_trend_template_filter(raw_sigs, tt_train)
        vf = next(v for v in VOLUME_FILTER_VARIANTS if v["name"] == cand["vol_filter"])
        if vf["window"] is not None:
            filtered_sigs = apply_volume_post_filter(
                raw_sigs, train, vf["window"], vf["threshold"],
                forward=vf["forward"])
        else:
            filtered_sigs = raw_sigs

        risk_final = {**RISK_BASE,
                      "trailing_atr_multiplier": row["trailing_atr_multiplier"],
                      "target_r_multiple": row["target_r_multiple"] if pd.notna(row["target_r_multiple"]) else None,
                      "early_exit_days": int(row["early_exit_days"]) if pd.notna(row["early_exit_days"]) else None,
                      "breakeven_r_multiple": row["breakeven_r_multiple"],
                      "max_stop_loss_pct": row["max_stop_loss_pct"]}
        ev = evaluate_signals_seq(train, filtered_sigs, risk_final,
                                   precomputed_atr=cand_cache["atr"])

        t_r = f"{row['target_r_multiple']:.1f}" if pd.notna(row['target_r_multiple']) else "None"
        print(f"\n  #{rank} (composite={row['composite']:.3f}): "
              f"trail={row['trailing_atr_multiplier']:.1f}, target={t_r}, "
              f"vf={row['vol_filter']}, "
              f"TT={'Y' if row['trend_template'] else 'N'}")
        print(f"     {ev['trades']}T, WR={fmt_wr(ev['WR'])}, CR={fmt_pct(ev['CR'])}, "
              f"avgR={ev['avg_R']:+.2f}")
        reasons_str = ", ".join(f"{k}={v}" for k, v in sorted(ev["reasons"].items()))
        print(f"     Salidas: {reasons_str}")

        if ev["trade_details"]:
            for j, (pat, trade) in enumerate(ev["trade_details"], 1):
                fwd_info = ""
                sig = pat.get("signal_obj")
                if sig and sig.volume_confirmation.get("forward_confirmed"):
                    delay = sig.volume_confirmation.get("confirmation_delay_days", "?")
                    fwd_info = f" [fwd+{delay}d]"
                entry_str = pat["first_signal_date"].strftime("%Y-%m-%d")
                exit_str = trade["exit_date"].strftime("%Y-%m-%d")
                print(f"     {j:>2d}: {entry_str} -> {exit_str} | "
                      f"{trade['exit_reason']:<15s} | "
                      f"PnL={trade['pnl_pct']:+.2%} | R={trade['r_multiple']:+.1f}R | "
                      f"MaxR={trade['max_r']:.1f}R | Dur={trade['duration_days']}d{fwd_info}")

    # ── Save results ────────────────────────────────────────

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    det_path = OUTPUT_DIR / f"{ticker.lower()}_phase1_detection.csv"
    det_df.to_csv(det_path, index=False)
    print(f"\n  Guardado: {det_path}")

    phase2_path = OUTPUT_DIR / f"{ticker.lower()}_phase2_exit.csv"
    phase2_df.to_csv(phase2_path, index=False)
    print(f"  Guardado: {phase2_path}")

    total_time = time.time() - t_total
    print(f"\n  Tiempo total {ticker}: {total_time:.0f}s ({total_time/60:.1f}m)")
    print(f"\n{'#'*70}")
    print(f"  {ticker} — COMPLETO")
    print(f"{'#'*70}")


# ── Main ────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Deep per-ticker VCP optimization v4 (trend template corregido)")
    parser.add_argument("tickers", nargs="+", help="Tickers to process (e.g. MSFT AAPL)")
    parser.add_argument("--train-cutoff", default="2020-01-01",
                        help="Train/test split date (default: 2020-01-01)")
    parser.add_argument("--top-n", type=int, default=10,
                        help="Top N per criterion for candidate selection (default: 10)")
    parser.add_argument("--min-trades", type=int, default=3,
                        help="Min avg trades to be eligible (default: 3)")
    args = parser.parse_args()

    print(f"Deep Per-Ticker VCP Optimization v4 (trend template corregido)")
    print(f"  Tickers: {', '.join(args.tickers)}")
    print(f"  Train cutoff: {args.train_cutoff}")
    print(f"  Top N: {args.top_n}")
    print(f"  Min trades: {args.min_trades}")

    for ticker in args.tickers:
        run_ticker(ticker.upper(), args.train_cutoff, args.top_n, args.min_trades)

    print(f"\nTodo completo!")
