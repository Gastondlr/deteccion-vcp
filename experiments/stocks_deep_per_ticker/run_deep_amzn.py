"""Deep per-ticker optimization for AMZN.

Split: 5y train (2015-2019) / rest test (2020-2026)
Phase 1: Detection grid (34,992 configs)
Phase 2: Exit grid (720 configs) on best detection config

Usage:
    python run_deep_amzn.py
"""
import functools
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

TICKER = "AMZN"
TRAIN_CUTOFF = "2020-01-01"
DATA_DIR = project_root / "data" / "csv"

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
TREND_TEMPLATE_OPTIONS = [False, True]
VOLUME_CONTRACTION_OPTIONS = [None, {"method": "ratio", "ratio_threshold": 0.85}]

# ── Phase 2: Exit grid ─────────────────────────────────────

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

# ── Counts ──────────────────────────────────────────────────

n_det = (len(ATR_MULTS) * len(MAX_DEPTH_ATRS) * len(REDUCTIONS)
         * len(LOOKBACK_BARS) * len(COMPRESSION_THRESHOLDS)
         * len(TOLERANCES) * len(MAX_DEPTH_PCTS)
         * len(ASCENDING_LOWS_TOLERANCES)
         * len(USE_CLOSE_ONLY) * len(TREND_TEMPLATE_OPTIONS)
         * len(VOLUME_CONTRACTION_OPTIONS))
n_exit = (len(TRAILING_MULTS) * len(TARGET_RS) * len(EARLY_EXITS)
          * len(BREAKEVEN_RS) * len(MAX_STOP_LOSSES))

print(f"AMZN Deep Per-Ticker Optimization")
print(f"  Deteccion: {n_det:,} configs")
print(f"  Salida:    {n_exit:,} configs")


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


# ── Load data ───────────────────────────────────────────────

print(f"\nCargando {TICKER}...")
daily = pd.read_csv(DATA_DIR / f"{TICKER}.csv", parse_dates=["date"], index_col="date")
train = daily[daily.index < TRAIN_CUTOFF]
test = daily[daily.index >= TRAIN_CUTOFF]
print(f"  Total: {len(daily):,} barras ({daily.index.min().date()} a {daily.index.max().date()})")
print(f"  TRAIN: {len(train):,} barras ({train.index.min().date()} a {train.index[-1].date()})")
print(f"  TEST:  {len(test):,} barras ({test.index[0].date()} a {test.index[-1].date()})")

# ── Precompute ──────────────────────────────────────────────

print(f"\nPrecomputando trend template...")
t0 = time.time()
tt_train = evaluate_trend_template(train)
tt_mask_train = tt_train["trend_template"]
print(f"  {tt_mask_train.sum()}/{len(tt_mask_train)} dias en Stage 2 ({time.time()-t0:.2f}s)")

print(f"\nPrecomputando caches de swings ({len(ATR_MULTS)}x{len(USE_CLOSE_ONLY)}={len(ATR_MULTS)*len(USE_CLOSE_ONLY)} combos)...")
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

# ══════════════════════════════════════════════════════════════
#  FASE 1: GRILLA DE DETECCION — TRAIN
# ══════════════════════════════════════════════════════════════

print(f"\n{'='*70}")
print(f"  FASE 1: DETECCION — {TICKER} TRAIN ({n_det:,} configs)")
print(f"{'='*70}")

fixed_risk = {**RISK_BASE, "max_stop_loss_pct": 0.07,
              "trailing_atr_multiplier": 1.5, "target_r_multiple": 3.0,
              "early_exit_days": None, "breakeven_r_multiple": 1.0}

all_det_results = []
t_total = time.time()
configs_done = 0
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
                                        for use_tt in TREND_TEMPLATE_OPTIONS:
                                            tt_mask = tt_mask_train if use_tt else None

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
                                            signals = {dt: s for dt, s in res.items() if s is not None}

                                            if tt_mask is not None:
                                                signals = {dt: s for dt, s in signals.items()
                                                           if dt in tt_mask.index and tt_mask.loc[dt]}

                                            ev = evaluate_signals_seq(
                                                train, signals, fixed_risk,
                                                precomputed_atr=cache["atr"],
                                            )

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
                                                "signals": len(signals),
                                                "trades": ev["trades"],
                                                "wins": ev["wins"],
                                                "WR": ev["WR"],
                                                "CR": ev["CR"],
                                                "avg_R": ev["avg_R"],
                                            })

                                            configs_done += 1
                                            pct = configs_done * 100 // n_det
                                            if pct >= last_pct_report + 5:
                                                elapsed = time.time() - t_total
                                                rate = configs_done / elapsed
                                                eta = (n_det - configs_done) / rate
                                                print(f"  {pct}% ({configs_done:,}/{n_det:,}) | "
                                                      f"{elapsed:.0f}s | {rate:.1f} cfg/s | "
                                                      f"ETA {eta:.0f}s ({eta/60:.1f}m)")
                                                last_pct_report = pct

t_det_total = time.time() - t_total
det_df = pd.DataFrame(all_det_results)
det_df_sorted = det_df.sort_values("CR", ascending=False)

print(f"\n  Fase 1 completada: {len(det_df):,} configs en {t_det_total:.0f}s ({t_det_total/60:.1f}m)")
print(f"  Con senales: {(det_df['signals'] > 0).sum():,}/{len(det_df):,}")
print(f"  Con trades:  {(det_df['trades'] > 0).sum():,}/{len(det_df):,}")

# ── Sensitivity analysis ────────────────────────────────────

print(f"\n{'─'*70}")
print(f"  ANALISIS DE SENSIBILIDAD")
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
        has_trades = sub[sub["trades"] > 0]
        label = str(val) if val is not None else "None"
        med_cr = has_trades["CR"].median() if len(has_trades) > 0 else 0
        print(f"    {label:>6s}: avg_sig={sub['signals'].mean():>6.1f}, "
              f"avg_T={sub['trades'].mean():>5.1f}, "
              f"avg_CR={sub['CR'].mean():>+.4f}, "
              f"best_CR={sub['CR'].max():>+.4f}, "
              f"med_CR={med_cr:>+.4f}, "
              f"con_T={len(has_trades)}/{len(sub)}")

# ── Top 30 configs ──────────────────────────────────────────

print(f"\n{'─'*70}")
print(f"  TOP 30 CONFIGS")
print(f"{'─'*70}")
for i, (_, row) in enumerate(det_df_sorted.head(30).iterrows(), 1):
    mda = "None" if pd.isna(row['max_depth_atr']) else str(int(row['max_depth_atr']))
    uco = "C" if row['use_close_only'] else "HL"
    tt = "TT" if row['trend_template'] else "  "
    vc = "VC" if row['vol_contraction'] else "  "
    print(f"  {i:>2d}. atr={row['atr_mult']:.1f} {uco} mda={mda:>4s} "
          f"red={row['reduction']:.2f} lb={int(row['lookback_bars']):>3d} "
          f"tol={row['tolerance']:.2f} mdp={row['max_depth_pct']:.2f} "
          f"alt={row['asc_lows_tol']:.2f} comp={row['comp_thresh']:.2f} "
          f"{tt} {vc} "
          f"-> {int(row['signals']):>3d}sen {int(row['trades']):>2d}T "
          f"WR={fmt_wr(row['WR'])} CR={fmt_pct(row['CR'])}")

# ── Interaction: key new params ─────────────────────────────

print(f"\n{'─'*70}")
print(f"  INTERACCIONES CLAVE")
print(f"{'─'*70}")

print(f"\n  --- tolerance x ascending_lows_tolerance ---")
print(f"  {'tol':>5s} | {'alt':>5s} | {'avg_sig':>7s} | {'avg_T':>5s} | "
      f"{'avg_CR':>8s} | {'best_CR':>8s}")
print(f"  {'─'*55}")
for tol in TOLERANCES:
    for alt in ASCENDING_LOWS_TOLERANCES:
        sub = det_df[(det_df["tolerance"] == tol) & (det_df["asc_lows_tol"] == alt)]
        print(f"  {tol:>5.2f} | {alt:>5.2f} | {sub['signals'].mean():>7.1f} | "
              f"{sub['trades'].mean():>5.1f} | {sub['CR'].mean():>+8.4f} | "
              f"{sub['CR'].max():>+8.4f}")

print(f"\n  --- use_close_only x trend_template ---")
for uco in USE_CLOSE_ONLY:
    for tt in TREND_TEMPLATE_OPTIONS:
        sub = det_df[(det_df["use_close_only"] == uco) & (det_df["trend_template"] == tt)]
        has_t = sub[sub["trades"] > 0]
        label = f"{'C' if uco else 'HL'}/{'TT' if tt else 'noTT'}"
        print(f"  {label:>8s}: avg_sig={sub['signals'].mean():>6.1f}, "
              f"avg_T={sub['trades'].mean():>5.1f}, "
              f"avg_CR={sub['CR'].mean():>+.4f}, "
              f"best_CR={sub['CR'].max():>+.4f}, "
              f"con_T={len(has_t)}/{len(sub)}")

print(f"\n  --- vol_contraction x max_depth_pct ---")
for vc in [False, True]:
    for mdp in MAX_DEPTH_PCTS:
        sub = det_df[(det_df["vol_contraction"] == vc) & (det_df["max_depth_pct"] == mdp)]
        has_t = sub[sub["trades"] > 0]
        label = f"{'VC' if vc else 'noVC'}/{mdp:.2f}"
        print(f"  {label:>10s}: avg_sig={sub['signals'].mean():>6.1f}, "
              f"avg_T={sub['trades'].mean():>5.1f}, "
              f"avg_CR={sub['CR'].mean():>+.4f}, "
              f"best_CR={sub['CR'].max():>+.4f}, "
              f"con_T={len(has_t)}/{len(sub)}")

# ══════════════════════════════════════════════════════════════
#  FASE 2: GRILLA DE SALIDA — TRAIN
# ══════════════════════════════════════════════════════════════

best = det_df_sorted.iloc[0]
print(f"\n\n{'='*70}")
print(f"  FASE 2: SALIDA — {TICKER} TRAIN ({n_exit:,} configs)")
print(f"  Mejor config deteccion:")
print(f"    atr={best['atr_mult']:.1f}, close_only={best['use_close_only']}, "
      f"mda={best['max_depth_atr']}, red={best['reduction']:.2f}, "
      f"lb={int(best['lookback_bars'])}")
print(f"    tol={best['tolerance']:.2f}, mdp={best['max_depth_pct']:.2f}, "
      f"alt={best['asc_lows_tol']:.2f}, comp={best['comp_thresh']:.2f}")
print(f"    TT={best['trend_template']}, VC={best['vol_contraction']}")
print(f"    -> {int(best['signals'])} sen, {int(best['trades'])}T, "
      f"CR={fmt_pct(best['CR'])}")
print(f"{'='*70}")

best_cache = caches[(best["atr_mult"], best["use_close_only"])]
best_mda = None if (isinstance(best["max_depth_atr"], float) and np.isnan(best["max_depth_atr"])) else best["max_depth_atr"]
best_seq = {
    "method": "tolerance", "min_contractions": 2, "max_contractions": 6,
    "lookback_bars": int(best["lookback_bars"]),
    "tolerance": best["tolerance"],
    "max_depth_pct": best["max_depth_pct"],
    "max_depth_atr": best_mda,
    "min_total_reduction": best["reduction"],
    "max_gap_between_contractions_days": None,
    "require_ascending_lows": True,
    "ascending_lows_tolerance": best["asc_lows_tol"],
}
best_comp = {"method": "ratio", "atr_period": 14, "ratio_threshold": best["comp_thresh"]}
best_vol_contr = {"method": "ratio", "ratio_threshold": 0.85} if best["vol_contraction"] else None
best_tt_mask = tt_mask_train if best["trend_template"] else None

res = run_full_vcp_pipeline(
    ohlc=train, swing_detector=best_cache["detector"],
    sequence_params=best_seq, compression_params=best_comp,
    breakout_params=BREAKOUT_BASE,
    volume_contraction_params=best_vol_contr,
    precomputed_swings=best_cache["swings"],
    precomputed_contractions=best_cache["contractions"],
    precomputed_atr=best_cache["atr"],
)
signals_train = {dt: s for dt, s in res.items() if s is not None}
if best_tt_mask is not None:
    signals_train = {dt: s for dt, s in signals_train.items()
                     if dt in best_tt_mask.index and best_tt_mask.loc[dt]}
print(f"  Senales en TRAIN: {len(signals_train)}")

if len(signals_train) == 0:
    print("  (0 senales — saltando Fase 2)")
    best_exit = {
        "trailing_atr_multiplier": 1.5, "target_r_multiple": 3.0,
        "early_exit_days": None, "breakeven_r_multiple": 1.0,
        "max_stop_loss_pct": 0.07,
    }
else:
    exit_results = []
    t0 = time.time()
    for trail in TRAILING_MULTS:
        for target in TARGET_RS:
            for early in EARLY_EXITS:
                for be_r in BREAKEVEN_RS:
                    for max_sl in MAX_STOP_LOSSES:
                        risk = {**RISK_BASE, "max_stop_loss_pct": max_sl,
                                "trailing_atr_multiplier": trail,
                                "target_r_multiple": target,
                                "early_exit_days": early,
                                "breakeven_r_multiple": be_r}
                        ev = evaluate_signals_seq(
                            train, signals_train, risk,
                            precomputed_atr=best_cache["atr"],
                        )
                        exit_results.append({
                            "trailing_atr_multiplier": trail,
                            "target_r_multiple": target,
                            "early_exit_days": early,
                            "breakeven_r_multiple": be_r,
                            "max_stop_loss_pct": max_sl,
                            "trades": ev["trades"], "wins": ev["wins"],
                            "WR": ev["WR"], "CR": ev["CR"], "avg_R": ev["avg_R"],
                        })

    exit_df = pd.DataFrame(exit_results)
    exit_df_sorted = exit_df.sort_values("CR", ascending=False)
    t_exit = time.time() - t0
    print(f"  {len(exit_df)} configs en {t_exit:.1f}s")

    print(f"\n  Top 20 configs salida:")
    for i, (_, row) in enumerate(exit_df_sorted.head(20).iterrows(), 1):
        t_r = row['target_r_multiple'] if pd.notna(row['target_r_multiple']) else 'None'
        e_e = int(row['early_exit_days']) if pd.notna(row['early_exit_days']) else 'None'
        print(f"  {i:>2d}. trail={row['trailing_atr_multiplier']:.1f}, target={t_r}, "
              f"early={e_e}, be_R={row['breakeven_r_multiple']:.1f}, "
              f"max_sl={row['max_stop_loss_pct']:.2f} "
              f"-> {int(row['trades'])}T WR={fmt_wr(row['WR'])} CR={fmt_pct(row['CR'])}")

    # Sensitivity: max_stop_loss_pct
    print(f"\n  --- Impacto max_stop_loss_pct ---")
    for sl in MAX_STOP_LOSSES:
        sub = exit_df[exit_df["max_stop_loss_pct"] == sl]
        has_t = sub[sub["trades"] > 0]
        med_cr = has_t["CR"].median() if len(has_t) > 0 else 0
        print(f"    sl={sl:.2f}: avg_T={sub['trades'].mean():>5.1f}, "
              f"avg_CR={sub['CR'].mean():>+.4f}, "
              f"best_CR={sub['CR'].max():>+.4f}, "
              f"med_CR={med_cr:>+.4f}")

    best_exit_row = exit_df_sorted.iloc[0]
    best_exit = {
        "trailing_atr_multiplier": best_exit_row["trailing_atr_multiplier"],
        "target_r_multiple": best_exit_row["target_r_multiple"] if pd.notna(best_exit_row["target_r_multiple"]) else None,
        "early_exit_days": int(best_exit_row["early_exit_days"]) if pd.notna(best_exit_row["early_exit_days"]) else None,
        "breakeven_r_multiple": best_exit_row["breakeven_r_multiple"],
        "max_stop_loss_pct": best_exit_row["max_stop_loss_pct"],
    }

# ══════════════════════════════════════════════════════════════
#  RESUMEN TRAIN
# ══════════════════════════════════════════════════════════════

print(f"\n\n{'#'*70}")
print(f"  RESUMEN TRAIN — {TICKER}")
print(f"{'#'*70}")

risk_final = {**RISK_BASE, **best_exit}
ev_train = evaluate_signals_seq(train, signals_train, risk_final,
                                 precomputed_atr=best_cache["atr"])

print(f"\n  Mejor config completa:")
print(f"    Swing:     atr_mult={best['atr_mult']:.1f}, close_only={best['use_close_only']}")
print(f"    Secuencia: mda={best_mda}, red={best['reduction']:.2f}, "
      f"lb={int(best['lookback_bars'])}, tol={best['tolerance']:.2f}")
print(f"    Filtros:   mdp={best['max_depth_pct']:.2f}, alt={best['asc_lows_tol']:.2f}, "
      f"comp={best['comp_thresh']:.2f}")
print(f"    Opciones:  TT={best['trend_template']}, VC={best['vol_contraction']}")
print(f"    Salida:    trail={best_exit['trailing_atr_multiplier']}, "
      f"target={best_exit['target_r_multiple']}, "
      f"early={best_exit['early_exit_days']}, "
      f"be_R={best_exit['breakeven_r_multiple']}, "
      f"max_sl={best_exit['max_stop_loss_pct']}")

print(f"\n  Resultado TRAIN:")
print(f"    Senales: {len(signals_train)}")
print(f"    Trades:  {ev_train['trades']}")
print(f"    WR:      {fmt_wr(ev_train['WR'])}")
print(f"    CR:      {fmt_pct(ev_train['CR'])}")
print(f"    Avg R:   {ev_train['avg_R']:+.2f}")
reasons_str = ", ".join(f"{k}={v}" for k, v in sorted(ev_train["reasons"].items()))
print(f"    Salidas: {reasons_str}")

if ev_train["trade_details"]:
    print(f"\n  Detalle de trades TRAIN:")
    for i, (pat, trade) in enumerate(ev_train["trade_details"], 1):
        entry_str = pat["first_signal_date"].strftime("%Y-%m-%d")
        exit_str = trade["exit_date"].strftime("%Y-%m-%d")
        print(f"    {i:>2d}: {entry_str} -> {exit_str} | {trade['exit_reason']:<15s} | "
              f"PnL={trade['pnl_pct']:+.2%} | R={trade['r_multiple']:+.1f}R | "
              f"MaxR={trade['max_r']:.1f}R | Dur={trade['duration_days']}d")

# ── Save results ────────────────────────────────────────────

output_dir = Path(__file__).resolve().parent / "results"
output_dir.mkdir(exist_ok=True)

det_df.to_csv(output_dir / "amzn_phase1_detection.csv", index=False)
print(f"\n  Guardado: {output_dir / 'amzn_phase1_detection.csv'}")

if len(signals_train) > 0:
    exit_df.to_csv(output_dir / "amzn_phase2_exit.csv", index=False)
    print(f"  Guardado: {output_dir / 'amzn_phase2_exit.csv'}")

total_time = time.time() - t_total
print(f"\n  Tiempo total: {total_time:.0f}s ({total_time/60:.1f}m)")
print(f"\nCompleto!")
