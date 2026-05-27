"""EURUSD hourly VCP detection — Exp 4: short patterns (<=5 days), mid atr_mult.

Explores the unexplored atr_mult 2-4 range with short lookback windows (3-5 days)
to find intra-week VCP patterns. max_depth_atr disabled, tolerance and
ascending_lows fixed (both proven inert).

Phase 1: Detection grid (54 configs)
  - atr_mult: [2, 3, 4]
  - lookback_bars: [72, 120]  (3d, 5d)
  - reduction: [0.4, 0.6, 0.8]
  - compression_threshold: [0.90, 0.95, 1.00]
  - max_depth_atr: None (disabled)
  - tolerance: 0.15 (fixed — minimal effect)
  - require_ascending_lows: False (fixed — always inert)
  - max_contractions: 4 (short patterns)

Phase 2: Exit grid (216 configs)
  - trailing_atr_multiplier: [1.0, 1.5, 2.0, 3.0]
  - target_r_multiple: [None, 2.0, 3.0]
  - breakeven_r_multiple: [0.5, 1.0, 1.5]
  - max_stop_loss_pct: [0.01, 0.015]
  - max_bars_without_progress: [10, 24, None]
  - early_exit_days: None (fixed)

Split: TRAIN 2018 / TEST 2019-2026
Data: hourly EURUSD (~6K bars/year)

Usage:
    python run_eurusd_hourly.py
"""
import functools
import sys
import tempfile
import time
from pathlib import Path

print = functools.partial(print, flush=True)

import matplotlib
matplotlib.use("Agg")
import mlflow
import numpy as np
import pandas as pd

project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from models.configs import ATRZigZagConfig
from vcp_detection.heuristic import ATRZigZagDetector, run_full_vcp_pipeline
from vcp_detection.heuristic.contractions import compute_contractions
from vcp_detection.heuristic.atr_compression import compute_atr
from vcp_detection.analysis import evaluate_signals_to_trades

pd.set_option("display.float_format", "{:.4f}".format)

# ── Constants ─────────────────────────────────────────────────

TICKER = "EURUSD"
TRAIN_START = "2018-01-01"
TRAIN_END = "2019-01-01"
TEST_END = "2027-01-01"

# Phase 1: Detection grid
ATR_MULTS = [2, 3, 4]
REDUCTIONS = [0.40, 0.60, 0.80]
LOOKBACK_BARS = [72, 120]
COMPRESSION_THRESHOLDS = [0.90, 0.95, 1.00]

# Phase 2: Exit grid
TRAILING_MULTS = [1.0, 1.5, 2.0, 3.0]
TARGET_RS = [None, 2.0, 3.0]
BREAKEVEN_RS = [0.5, 1.0, 1.5]
MAX_STOP_LOSS_PCTS = [0.01, 0.015]
MAX_BARS_WITHOUT_PROGRESS = [10, 24, None]

BREAKOUT = {
    "volume_method": "ratio", "volume_ratio_threshold": 1.5,
    "volume_lookback_days": 50,
    "require_volume_confirmation": False,
}
RISK_FIXED = {
    "trailing_sma_period": 20,
    "trailing_volume_factor": 1.5,
    "trailing_stop_method": "atr",
    "trailing_atr_period": 14,
    "min_progress_r": 0.5,
    "early_exit_days": None,
}

DATA_DIR = project_root / "data" / "monedas_hora"
fpath = DATA_DIR / f"{TICKER}.csv"
if not fpath.exists():
    print(f"ERROR: {fpath} no encontrado")
    sys.exit(1)

n_det = len(ATR_MULTS) * len(REDUCTIONS) * len(LOOKBACK_BARS) * len(COMPRESSION_THRESHOLDS)
n_exit = (len(TRAILING_MULTS) * len(TARGET_RS) * len(BREAKEVEN_RS)
          * len(MAX_STOP_LOSS_PCTS) * len(MAX_BARS_WITHOUT_PROGRESS))
print(f"Moneda: {TICKER} (HOURLY)")
print(f"Fase 1: {n_det:,} configs deteccion")
print(f"Fase 2: {n_exit:,} configs salida")
print(f"TRAIN: {TRAIN_START} a {TRAIN_END}")
print(f"TEST: {TRAIN_END} a {TEST_END}\n")


# ── Helpers ──────────────────────────────────────────────────


def load_ticker():
    return pd.read_csv(fpath, parse_dates=["date"], index_col="date")


def precompute(ohlc, atr_mult):
    config = ATRZigZagConfig(atr_length=14, atr_mult=atr_mult, use_close_only=False)
    detector = ATRZigZagDetector(config)
    swings = detector.detect(ohlc)
    contractions = compute_contractions(swings, ohlc)
    atr = compute_atr(ohlc, 14)
    return {"ohlc": ohlc, "swings": swings, "contractions": contractions,
            "atr": atr, "detector": detector}


def make_seq_params(reduction, lookback):
    return {
        "method": "tolerance", "min_contractions": 2, "max_contractions": 4,
        "lookback_bars": lookback, "tolerance": 0.15,
        "max_depth_pct": 0.50, "max_depth_atr": None,
        "min_total_reduction": reduction,
        "max_gap_between_contractions_days": None,
        "require_ascending_lows": False,
        "ascending_lows_tolerance": 0.03,
    }


def detect_signals(ohlc, seq_params, cache_entry, compression_params):
    res = run_full_vcp_pipeline(
        ohlc=ohlc, swing_detector=cache_entry["detector"],
        sequence_params=seq_params,
        compression_params=compression_params,
        breakout_params=BREAKOUT,
        volume_contraction_params=None,
        precomputed_swings=cache_entry["swings"],
        precomputed_contractions=cache_entry["contractions"],
        precomputed_atr=cache_entry["atr"],
    )
    return {dt: s for dt, s in res.items() if s is not None}


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


def fmt_pct(x):
    return f"{x:+.2%}"


def fmt_wr(x):
    return f"{x:.0%}"


def buy_and_hold_metrics(ohlc):
    c = ohlc["close"]
    total_return = float(c.iloc[-1] / c.iloc[0] - 1)
    dd = (c - c.cummax()) / c.cummax()
    max_dd = float(dd.min())
    hourly_ret = c.pct_change().dropna()
    sharpe = float(hourly_ret.mean() / hourly_ret.std() * np.sqrt(252 * 24)) if hourly_ret.std() > 0 else 0
    return {"bh_return": total_return, "bh_max_drawdown": max_dd, "bh_sharpe": sharpe}


def strategy_metrics(ohlc, trade_details):
    if not trade_details:
        return {"strat_sharpe": 0.0, "strat_max_drawdown": 0.0}
    bar_rets = []
    worst_dd = 0.0
    for pat, trade in trade_details:
        tc = ohlc.loc[pat["first_signal_date"]:trade["exit_date"], "close"]
        if len(tc) >= 2:
            bar_rets.append(tc.pct_change().dropna())
            dd = float(((tc - tc.cummax()) / tc.cummax()).min())
            worst_dd = min(worst_dd, dd)
    if not bar_rets:
        return {"strat_sharpe": 0.0, "strat_max_drawdown": 0.0}
    all_rets = pd.concat(bar_rets)
    sharpe = float(all_rets.mean() / all_rets.std() * np.sqrt(252 * 24)) if len(all_rets) > 1 and all_rets.std() > 0 else 0.0
    return {"strat_sharpe": sharpe, "strat_max_drawdown": worst_dd}


def build_trade_table(trade_details):
    rows = []
    for i, (pat, trade) in enumerate(trade_details, 1):
        rows.append({
            "ticker": TICKER, "trade_num": i,
            "entry_date": pat["first_signal_date"].strftime("%Y-%m-%d %H:%M"),
            "exit_date": trade["exit_date"].strftime("%Y-%m-%d %H:%M"),
            "exit_reason": trade["exit_reason"],
            "duration_days": trade["duration_days"],
            "entry_price": pat["entry_price"],
            "exit_price": trade["exit_price"],
            "pnl_pct": trade["pnl_pct"], "r_multiple": trade["r_multiple"],
            "max_r": trade["max_r"],
            "n_contractions": pat["n_contractions"],
            "atr_ratio": pat["atr_ratio"],
        })
    return pd.DataFrame(rows)


# ══════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    hourly = load_ticker()
    train = hourly[(hourly.index >= TRAIN_START) & (hourly.index < TRAIN_END)]
    test = hourly[(hourly.index >= TRAIN_END) & (hourly.index < TEST_END)]
    full = hourly[(hourly.index >= TRAIN_START) & (hourly.index < TEST_END)]

    print(f"{TICKER}: {len(hourly):,} barras totales ({hourly.index.min()} a {hourly.index.max()})")
    print(f"TRAIN: {len(train):,} barras | TEST: {len(test):,} barras | FULL: {len(full):,} barras\n")

    mlflow.set_tracking_uri(str(project_root / "mlruns"))
    mlflow.set_experiment("VCP_FX_EURUSD_Hourly")

    # ══════════════════════════════════════════════════════════
    #  FASE 1: GRILLA DE DETECCION — TRAIN
    # ══════════════════════════════════════════════════════════

    print(f"{'='*70}")
    print(f"  FASE 1: GRILLA DE DETECCION — {TICKER} HOURLY TRAIN")
    print(f"  {n_det:,} configs totales")
    print(f"{'='*70}")

    fixed_risk = {
        **RISK_FIXED,
        "max_stop_loss_pct": 0.01,
        "max_bars_without_progress": 24,
        "trailing_atr_multiplier": 1.5,
        "target_r_multiple": 3.0,
        "breakeven_r_multiple": 1.0,
    }

    all_det_results = []
    caches_train = {}
    t_total = time.time()
    configs_done = 0

    for atr_mult in ATR_MULTS:
        t0 = time.time()
        cache = precompute(train, atr_mult)
        caches_train[atr_mult] = cache
        n_swings = len(cache["swings"])
        n_contr = len(cache["contractions"])
        print(f"\n  atr_mult={atr_mult:.2f}: {n_swings} swings, {n_contr} contractions")

        configs_per_mult = len(REDUCTIONS) * len(LOOKBACK_BARS) * len(COMPRESSION_THRESHOLDS)
        mult_done = 0
        last_pct = -1

        for reduction in REDUCTIONS:
            for lookback in LOOKBACK_BARS:
                for comp_thresh in COMPRESSION_THRESHOLDS:
                    seq = make_seq_params(reduction, lookback)
                    comp_params = {"method": "ratio", "atr_period": 14,
                                   "ratio_threshold": comp_thresh}
                    signals = detect_signals(train, seq, cache, comp_params)
                    ev = evaluate_signals_seq(train, signals, fixed_risk,
                                              precomputed_atr=cache["atr"])
                    all_det_results.append({
                        "atr_mult": atr_mult,
                        "reduction": reduction, "lookback_bars": lookback,
                        "compression_threshold": comp_thresh,
                        "n_swings": n_swings, "n_contractions": n_contr,
                        "signals": len(signals),
                        **{k: ev[k] for k in ["trades", "wins", "WR", "CR", "avg_R"]},
                    })
                    configs_done += 1
                    mult_done += 1
                    pct = mult_done * 100 // configs_per_mult
                    if pct >= last_pct + 10:
                        elapsed_mult = time.time() - t0
                        eta_mult = elapsed_mult / mult_done * (configs_per_mult - mult_done) if mult_done > 0 else 0
                        elapsed_total = time.time() - t_total
                        eta_total = elapsed_total / configs_done * (n_det - configs_done) if configs_done > 0 else 0
                        print(f"    atr_mult={atr_mult}: {pct}% ({mult_done}/{configs_per_mult}) "
                              f"| total {configs_done:,}/{n_det:,} "
                              f"| ETA mult {eta_mult:.0f}s | ETA total {eta_total:.0f}s")
                        last_pct = pct

        elapsed = time.time() - t0
        best_in_mult = max((r for r in all_det_results if r["atr_mult"] == atr_mult),
                           key=lambda r: r["CR"], default=None)
        best_cr = fmt_pct(best_in_mult["CR"]) if best_in_mult else "N/A"
        print(f"  atr_mult={atr_mult:.2f}: best_CR={best_cr} ({elapsed:.1f}s)")

    det_df = pd.DataFrame(all_det_results)
    total_time = time.time() - t_total
    det_df_sorted = det_df.sort_values("CR", ascending=False)

    print(f"\nFase 1 total: {len(det_df):,} configs en {total_time:.1f}s")
    print(f"Configs con trades: {len(det_df[det_df['trades'] > 0]):,}/{len(det_df):,}")
    print(f"Configs con senales: {len(det_df[det_df['signals'] > 0]):,}/{len(det_df):,}")

    # ── Sensitivity analysis ─────────────────────────────────

    print(f"\n{'='*70}")
    print(f"  ANALISIS DE SENSIBILIDAD — FASE 1")
    print(f"{'='*70}")

    for param_name, param_values in [
        ("atr_mult", ATR_MULTS),
        ("reduction", REDUCTIONS),
        ("lookback_bars", LOOKBACK_BARS),
        ("compression_threshold", COMPRESSION_THRESHOLDS),
    ]:
        print(f"\n  --- {param_name} ---")
        for val in param_values:
            sub = det_df[det_df[param_name] == val]
            has_signals = sub[sub["signals"] > 0]
            has_trades = sub[sub["trades"] > 0]
            print(f"    {str(val):>5s}: avg_signals={sub['signals'].mean():.1f}, "
                  f"avg_trades={sub['trades'].mean():.1f}, "
                  f"avg_CR={sub['CR'].mean():+.4f}, best_CR={sub['CR'].max():+.4f}, "
                  f"w/signals={len(has_signals)}/{len(sub)}, "
                  f"w/trades={len(has_trades)}/{len(sub)}")

    # ── Top 30 ────────────────────────────────────────────────

    print(f"\nTop 30 configs deteccion:")
    for _, row in det_df_sorted.head(30).iterrows():
        print(f"  atr={row['atr_mult']:.1f}, "
              f"red={row['reduction']:.2f}, lb={int(row['lookback_bars'])}, "
              f"comp={row['compression_threshold']} "
              f"-> {int(row['signals'])} sen, {int(row['trades'])}T, "
              f"WR={fmt_wr(row['WR'])}, CR={fmt_pct(row['CR'])}")

    # ══════════════════════════════════════════════════════════
    #  FASE 2: GRILLA DE SALIDA — TRAIN
    # ══════════════════════════════════════════════════════════

    best = det_df_sorted.iloc[0]
    best_det = {
        "atr_mult": best["atr_mult"],
        "reduction": best["reduction"],
        "lookback_bars": int(best["lookback_bars"]),
        "compression_threshold": best["compression_threshold"],
    }

    print(f"\n\n{'='*70}")
    print(f"  FASE 2: GRILLA DE SALIDA — {TICKER} HOURLY TRAIN")
    print(f"  atr_mult={best_det['atr_mult']}, "
          f"red={best_det['reduction']}, lb={best_det['lookback_bars']}, "
          f"comp={best_det['compression_threshold']}")
    print(f"  {n_exit:,} configs salida")
    print(f"{'='*70}")

    best_seq = make_seq_params(best_det["reduction"], best_det["lookback_bars"])
    best_comp = {"method": "ratio", "atr_period": 14,
                 "ratio_threshold": best_det["compression_threshold"]}
    best_cache = caches_train[best_det["atr_mult"]]
    signals_train = detect_signals(train, best_seq, best_cache, best_comp)
    print(f"  Senales detectadas en TRAIN: {len(signals_train)}")

    exit_results = []
    t0 = time.time()
    configs_done = 0
    last_pct = -1

    for max_sl in MAX_STOP_LOSS_PCTS:
        for max_bars in MAX_BARS_WITHOUT_PROGRESS:
            for trail in TRAILING_MULTS:
                for target in TARGET_RS:
                    for be_r in BREAKEVEN_RS:
                        risk = {
                            **RISK_FIXED,
                            "max_stop_loss_pct": max_sl,
                            "max_bars_without_progress": max_bars,
                            "trailing_atr_multiplier": trail,
                            "target_r_multiple": target,
                            "breakeven_r_multiple": be_r,
                        }
                        ev = evaluate_signals_seq(
                            train, signals_train, risk,
                            precomputed_atr=best_cache["atr"],
                        )
                        exit_results.append({
                            "max_stop_loss_pct": max_sl,
                            "max_bars_without_progress": max_bars,
                            "trailing_atr_multiplier": trail,
                            "target_r_multiple": target,
                            "breakeven_r_multiple": be_r,
                            **{k: ev[k] for k in ["trades", "wins", "WR", "CR", "avg_R"]},
                            "trail_stops": ev["reasons"].get("trailing_stop", 0),
                            "stops": ev["reasons"].get("stop_loss", 0),
                            "targets": ev["reasons"].get("target", 0),
                            "time_exits": ev["reasons"].get("time_exit", 0),
                        })
                        configs_done += 1
                        pct = configs_done * 100 // n_exit
                        if pct >= last_pct + 10:
                            elapsed = time.time() - t0
                            eta = elapsed / configs_done * (n_exit - configs_done) if configs_done > 0 else 0
                            print(f"    Fase 2: {pct}% ({configs_done:,}/{n_exit:,}) "
                                  f"| {elapsed:.0f}s | ETA {eta:.0f}s")
                            last_pct = pct

    exit_df = pd.DataFrame(exit_results)
    exit_df_sorted = exit_df.sort_values("CR", ascending=False)
    print(f"  {len(exit_df):,} configs en {time.time()-t0:.1f}s")

    # ── Sensitivity analysis Phase 2 ─────────────────────────

    print(f"\n  --- Sensibilidad: max_stop_loss_pct ---")
    for val in MAX_STOP_LOSS_PCTS:
        sub = exit_df[exit_df["max_stop_loss_pct"] == val]
        has_trades = sub[sub["trades"] > 0]
        print(f"    {val:.3f}: avg_trades={sub['trades'].mean():.1f}, "
              f"avg_CR={sub['CR'].mean():+.4f}, best_CR={sub['CR'].max():+.4f}, "
              f"w/trades={len(has_trades)}/{len(sub)}")

    print(f"\n  --- Sensibilidad: max_bars_without_progress ---")
    for val in MAX_BARS_WITHOUT_PROGRESS:
        if val is None:
            sub = exit_df[exit_df["max_bars_without_progress"].isna()]
        else:
            sub = exit_df[exit_df["max_bars_without_progress"] == val]
        has_trades = sub[sub["trades"] > 0]
        label = str(val) if val is not None else "None"
        print(f"    {label:>4s}: avg_trades={sub['trades'].mean():.1f}, "
              f"avg_CR={sub['CR'].mean():+.4f}, best_CR={sub['CR'].max():+.4f}, "
              f"w/trades={len(has_trades)}/{len(sub)}")

    print(f"\n  --- Sensibilidad: trailing_atr_multiplier ---")
    for val in TRAILING_MULTS:
        sub = exit_df[exit_df["trailing_atr_multiplier"] == val]
        has_trades = sub[sub["trades"] > 0]
        print(f"    {val:.1f}: avg_trades={sub['trades'].mean():.1f}, "
              f"avg_CR={sub['CR'].mean():+.4f}, best_CR={sub['CR'].max():+.4f}, "
              f"w/trades={len(has_trades)}/{len(sub)}")

    # ── Top 15 exit ───────────────────────────────────────────

    print(f"\n  Top 15 configs salida:")
    for _, row in exit_df_sorted.head(15).iterrows():
        t_r = row['target_r_multiple'] if pd.notna(row['target_r_multiple']) else 'None'
        m_b = int(row['max_bars_without_progress']) if pd.notna(row['max_bars_without_progress']) else 'None'
        print(f"    sl={row['max_stop_loss_pct']:.3f}, bars={m_b}, "
              f"trail={row['trailing_atr_multiplier']}, target={t_r}, "
              f"be_R={row['breakeven_r_multiple']}"
              f" -> {int(row['trades'])}T, WR={fmt_wr(row['WR'])}, CR={fmt_pct(row['CR'])}")

    best_exit_row = exit_df_sorted.iloc[0]
    best_exit = {
        "max_stop_loss_pct": best_exit_row["max_stop_loss_pct"],
        "max_bars_without_progress": best_exit_row["max_bars_without_progress"]
            if pd.notna(best_exit_row["max_bars_without_progress"]) else None,
        "trailing_atr_multiplier": best_exit_row["trailing_atr_multiplier"],
        "target_r_multiple": best_exit_row["target_r_multiple"]
            if pd.notna(best_exit_row["target_r_multiple"]) else None,
        "breakeven_r_multiple": best_exit_row["breakeven_r_multiple"],
    }

    # ══════════════════════════════════════════════════════════
    #  FASE 3: EVALUACION TRAIN / TEST / FULL + MLflow
    # ══════════════════════════════════════════════════════════

    print(f"\n\n{'='*70}")
    print(f"  FASE 3: EVALUACION FINAL — TRAIN / TEST / FULL")
    print(f"{'='*70}")

    risk_best = {**RISK_FIXED, **best_exit}
    splits = {"TRAIN": train, "TEST": test, "FULL": full}

    print(f"\n  Deteccion: atr={best_det['atr_mult']}, "
          f"red={best_det['reduction']}, lb={best_det['lookback_bars']}, "
          f"comp={best_det['compression_threshold']}")
    print(f"  Salida: sl={best_exit['max_stop_loss_pct']}, "
          f"bars={best_exit['max_bars_without_progress']}, "
          f"trail={best_exit['trailing_atr_multiplier']}, "
          f"target={best_exit['target_r_multiple']}, "
          f"be_R={best_exit['breakeven_r_multiple']}")

    print(f"\n  {'Split':<8s} | {'Sen':>5s} | {'Trades':>6s} | {'WR':>5s} | {'CR':>8s} | {'AvgR':>6s} | Salidas")
    print(f"  {'─'*80}")

    all_params = {
        "ticker": TICKER, "train_start": TRAIN_START, "train_end": TRAIN_END,
        "test_end": TEST_END, "data_type": "hourly", "grouping": "sequential",
        **{f"det_{k}": str(v) for k, v in best_det.items()},
        **{f"risk_{k}": str(v) for k, v in risk_best.items()},
    }

    ev_by_split = {}
    with mlflow.start_run(run_name="eurusd_hourly") as parent_run:
        for split_name, ohlc in splits.items():
            cache = precompute(ohlc, best_det["atr_mult"])
            signals = detect_signals(ohlc, best_seq, cache, best_comp)
            ev = evaluate_signals_seq(ohlc, signals, risk_best,
                                      precomputed_atr=cache["atr"])
            ev_by_split[split_name] = (len(signals), ev)
            reasons_str = ", ".join(f"{k}={v}" for k, v in sorted(ev["reasons"].items()))
            print(f"  {split_name:<8s} | {len(signals):>5d} | {ev['trades']:>6d} | "
                  f"{fmt_wr(ev['WR']):>5s} | {fmt_pct(ev['CR']):>8s} | {ev['avg_R']:>+6.2f} | {reasons_str}")

        for split_name in ["TRAIN", "TEST", "FULL"]:
            n_sig, ev = ev_by_split[split_name]
            ohlc = splits[split_name]
            bh = buy_and_hold_metrics(ohlc)
            strat = strategy_metrics(ohlc, ev["trade_details"])

            with mlflow.start_run(run_name=f"{TICKER}_{split_name}_hourly", nested=True):
                mlflow.log_params({**all_params, "split": split_name, "n_bars": len(ohlc)})
                mlflow.log_metrics({
                    "n_signals": n_sig, "n_trades": ev["trades"],
                    "n_wins": ev["wins"], "n_losses": ev["trades"] - ev["wins"],
                    "winrate": ev["WR"], "cumulative_return": ev["CR"],
                    "avg_r_multiple": ev["avg_R"],
                    "strategy_sharpe": strat["strat_sharpe"],
                    "strategy_max_drawdown": strat["strat_max_drawdown"],
                    "buyhold_return": bh["bh_return"],
                    "buyhold_sharpe": bh["bh_sharpe"],
                    "buyhold_max_drawdown": bh["bh_max_drawdown"],
                })

                if ev["trade_details"]:
                    with tempfile.TemporaryDirectory() as tmpdir:
                        tdf = build_trade_table(ev["trade_details"])
                        tcp = Path(tmpdir) / "trades.csv"
                        tdf.to_csv(tcp, index=False)
                        mlflow.log_artifact(str(tcp), "tables")

        with tempfile.TemporaryDirectory() as tmpdir:
            det_path = Path(tmpdir) / "phase1_all_configs.csv"
            det_df.to_csv(det_path, index=False)
            mlflow.log_artifact(str(det_path), "grids")

            exit_path = Path(tmpdir) / "phase2_all_configs.csv"
            exit_df.to_csv(exit_path, index=False)
            mlflow.log_artifact(str(exit_path), "grids")

    # ── Trade detail ──────────────────────────────────────────

    for split_name in ["TRAIN", "TEST"]:
        _, ev_split = ev_by_split[split_name]
        if ev_split["trade_details"]:
            print(f"\n  Detalle trades {split_name}:")
            for i, (pat, trade) in enumerate(ev_split["trade_details"], 1):
                entry_str = pat["first_signal_date"].strftime("%Y-%m-%d %H:%M")
                exit_str = trade["exit_date"].strftime("%Y-%m-%d %H:%M")
                print(f"    Trade {i}: {entry_str} -> {exit_str} | {trade['exit_reason']:<15s} | "
                      f"PnL={trade['pnl_pct']:+.2%} | R={trade['r_multiple']:+.1f}R | "
                      f"Dur={trade['duration_days']}d")

    print("\nCompleto!")
