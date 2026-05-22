"""Expanded detection grid for EURUSD — Phase 1 only.

Adds 3 previously-fixed parameters to the grid:
  - compression_threshold: [0.85, 0.90, 0.95, 1.0]
  - require_ascending_lows: [True, False]
  - tolerance: [0.10, 0.15, 0.20]

Total Phase 1 configs: 7 * 5 * 5 * 4 * 4 * 2 * 3 = 16,800
Phase 2: same 240 exit configs as fx_sequential.

Usage:
    python run_eurusd_detection.py
"""
import sys
import tempfile
import time
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
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
CUTOFF = "2020-01-01"

# Phase 1: Detection grid (original 4 + 3 new)
ATR_MULTS = [0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 2.5]
DEPTH_ATRS = [2, 3, 4, 5, 6]
REDUCTIONS = [0.40, 0.50, 0.60, 0.70, 0.80]
LOOKBACK_BARS = [63, 84, 105, 126]

# New variable parameters (previously fixed)
COMPRESSION_THRESHOLDS = [0.85, 0.90, 0.95, 1.0]
ASCENDING_LOWS = [True, False]
TOLERANCES = [0.10, 0.15, 0.20]

# Phase 2: Exit grid (unchanged)
TRAILING_MULTS = [1.0, 1.5, 2.0, 2.5, 3.0]
TARGET_RS = [None, 2.0, 3.0, 5.0]
EARLY_EXITS = [None, 3, 5]
BREAKEVEN_RS = [0.5, 1.0, 1.5, 2.0]

BREAKOUT = {
    "volume_method": "ratio", "volume_ratio_threshold": 1.5,
    "volume_lookback_days": 50,
    "require_volume_confirmation": False,
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

DATA_DIR = project_root / "data" / "monedas"
fpath = DATA_DIR / f"{TICKER}.csv"
if not fpath.exists():
    print(f"ERROR: {fpath} no encontrado")
    sys.exit(1)

n_det = (len(ATR_MULTS) * len(DEPTH_ATRS) * len(REDUCTIONS) * len(LOOKBACK_BARS)
         * len(COMPRESSION_THRESHOLDS) * len(ASCENDING_LOWS) * len(TOLERANCES))
n_exit = len(TRAILING_MULTS) * len(TARGET_RS) * len(EARLY_EXITS) * len(BREAKEVEN_RS)
print(f"Moneda: {TICKER}")
print(f"Fase 1: {n_det:,} configs deteccion")
print(f"Fase 2: {n_exit} configs salida")
print(f"Cutoff: {CUTOFF}\n")


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


def make_seq_params(depth_atr, reduction, lookback_bars, tolerance, require_ascending_lows):
    return {
        "method": "tolerance", "min_contractions": 2, "max_contractions": 6,
        "lookback_bars": lookback_bars, "tolerance": tolerance,
        "max_depth_pct": 0.50, "max_depth_atr": depth_atr,
        "min_total_reduction": reduction,
        "max_gap_between_contractions_days": None,
        "require_ascending_lows": require_ascending_lows,
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


def evaluate_signals_seq(ohlc, signals, risk):
    results = evaluate_signals_to_trades(
        signals, ohlc, risk, grouping="sequential",
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
    daily_ret = c.pct_change().dropna()
    sharpe = float(daily_ret.mean() / daily_ret.std() * np.sqrt(252)) if daily_ret.std() > 0 else 0
    return {"bh_return": total_return, "bh_max_drawdown": max_dd, "bh_sharpe": sharpe}


def strategy_metrics(ohlc, trade_details):
    if not trade_details:
        return {"strat_sharpe": 0.0, "strat_max_drawdown": 0.0}
    daily_rets = []
    worst_dd = 0.0
    for pat, trade in trade_details:
        tc = ohlc.loc[pat["first_signal_date"]:trade["exit_date"], "close"]
        if len(tc) >= 2:
            daily_rets.append(tc.pct_change().dropna())
            dd = float(((tc - tc.cummax()) / tc.cummax()).min())
            worst_dd = min(worst_dd, dd)
    if not daily_rets:
        return {"strat_sharpe": 0.0, "strat_max_drawdown": 0.0}
    all_rets = pd.concat(daily_rets)
    sharpe = float(all_rets.mean() / all_rets.std() * np.sqrt(252)) if len(all_rets) > 1 and all_rets.std() > 0 else 0.0
    return {"strat_sharpe": sharpe, "strat_max_drawdown": worst_dd}


def build_trade_table(trade_details):
    rows = []
    for i, (pat, trade) in enumerate(trade_details, 1):
        rows.append({
            "ticker": TICKER, "trade_num": i,
            "entry_date": pat["first_signal_date"].strftime("%Y-%m-%d"),
            "exit_date": trade["exit_date"].strftime("%Y-%m-%d"),
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
    daily = load_ticker()
    train = daily[daily.index < CUTOFF]
    test = daily[daily.index >= CUTOFF]

    print(f"{TICKER}: {len(daily):,} barras ({daily.index.min().date()} a {daily.index.max().date()})")
    print(f"TRAIN: {len(train):,} barras | TEST: {len(test):,} barras\n")

    mlflow.set_tracking_uri(str(project_root / "mlruns"))
    mlflow.set_experiment("VCP_FX_EURUSD_Detection")

    # ══════════════════════════════════════════════════════════
    #  FASE 1: GRILLA DE DETECCION EXPANDIDA — TRAIN
    # ══════════════════════════════════════════════════════════

    print(f"{'='*70}")
    print(f"  FASE 1: GRILLA DE DETECCION EXPANDIDA — {TICKER} TRAIN")
    print(f"  {n_det:,} configs totales")
    print(f"{'='*70}")

    fixed_risk = {**RISK_BASE, "trailing_atr_multiplier": 1.5, "target_r_multiple": 3.0,
                  "early_exit_days": None, "breakeven_r_multiple": 1.0}

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

        for depth_atr in DEPTH_ATRS:
            for reduction in REDUCTIONS:
                for lookback in LOOKBACK_BARS:
                    for comp_thresh in COMPRESSION_THRESHOLDS:
                        for asc_lows in ASCENDING_LOWS:
                            for tol in TOLERANCES:
                                seq = make_seq_params(depth_atr, reduction, lookback, tol, asc_lows)
                                comp_params = {"method": "ratio", "atr_period": 14,
                                               "ratio_threshold": comp_thresh}
                                signals = detect_signals(train, seq, cache, comp_params)
                                ev = evaluate_signals_seq(train, signals, fixed_risk)
                                all_det_results.append({
                                    "atr_mult": atr_mult, "depth_atr": depth_atr,
                                    "reduction": reduction, "lookback_bars": lookback,
                                    "compression_threshold": comp_thresh,
                                    "require_ascending_lows": asc_lows,
                                    "tolerance": tol,
                                    "n_swings": n_swings, "n_contractions": n_contr,
                                    "signals": len(signals),
                                    **{k: ev[k] for k in ["trades", "wins", "WR", "CR", "avg_R"]},
                                })
                                configs_done += 1

        elapsed = time.time() - t0
        best_in_mult = max((r for r in all_det_results if r["atr_mult"] == atr_mult),
                           key=lambda r: r["CR"], default=None)
        best_cr = fmt_pct(best_in_mult["CR"]) if best_in_mult else "N/A"
        print(f"  atr_mult={atr_mult:.2f}: {n_swings} swings, {n_contr} contr, "
              f"best_CR={best_cr} ({configs_done:,}/{n_det:,} done, {elapsed:.1f}s)")

    det_df = pd.DataFrame(all_det_results)
    total_time = time.time() - t_total
    det_df_sorted = det_df.sort_values("CR", ascending=False)

    print(f"\nTotal: {len(det_df):,} configs en {total_time:.1f}s")

    # ── Sensitivity analysis per new parameter ────────────────

    print(f"\n{'='*70}")
    print(f"  ANALISIS DE SENSIBILIDAD — NUEVOS PARAMETROS")
    print(f"{'='*70}")

    for param_name, param_values in [
        ("compression_threshold", COMPRESSION_THRESHOLDS),
        ("require_ascending_lows", ASCENDING_LOWS),
        ("tolerance", TOLERANCES),
    ]:
        print(f"\n  --- {param_name} ---")
        for val in param_values:
            sub = det_df[det_df[param_name] == val]
            has_trades = sub[sub["trades"] > 0]
            avg_signals = sub["signals"].mean()
            avg_trades = sub["trades"].mean()
            avg_cr = sub["CR"].mean()
            best_cr_val = sub["CR"].max()
            print(f"  {param_name}={str(val):>5s}: avg_signals={avg_signals:.1f}, "
                  f"avg_trades={avg_trades:.1f}, avg_CR={avg_cr:+.4f}, "
                  f"best_CR={best_cr_val:+.4f}, configs_con_trades={len(has_trades)}/{len(sub)}")

    # ── Comparison: original fixed vs best new ────────────────

    print(f"\n  --- Comparacion: config original vs expandida ---")
    original_mask = (
        (det_df["compression_threshold"] == 0.85) &
        (det_df["require_ascending_lows"] == True) &
        (det_df["tolerance"] == 0.10)
    )
    original_best = det_df[original_mask].sort_values("CR", ascending=False).iloc[0]
    expanded_best = det_df_sorted.iloc[0]

    print(f"  Original (comp=0.85, asc=True, tol=0.10):")
    print(f"    atr_mult={original_best['atr_mult']}, depth={int(original_best['depth_atr'])}, "
          f"red={original_best['reduction']}, lb={int(original_best['lookback_bars'])}")
    print(f"    {int(original_best['signals'])} sen, {int(original_best['trades'])}T, "
          f"WR={fmt_wr(original_best['WR'])}, CR={fmt_pct(original_best['CR'])}")

    print(f"  Expandida (mejor global):")
    print(f"    atr_mult={expanded_best['atr_mult']}, depth={int(expanded_best['depth_atr'])}, "
          f"red={expanded_best['reduction']}, lb={int(expanded_best['lookback_bars'])}")
    print(f"    comp={expanded_best['compression_threshold']}, "
          f"asc={expanded_best['require_ascending_lows']}, "
          f"tol={expanded_best['tolerance']}")
    print(f"    {int(expanded_best['signals'])} sen, {int(expanded_best['trades'])}T, "
          f"WR={fmt_wr(expanded_best['WR'])}, CR={fmt_pct(expanded_best['CR'])}")

    # ── Top 30 configs ────────────────────────────────────────

    print(f"\nTop 30 configs globales:")
    for _, row in det_df_sorted.head(30).iterrows():
        print(f"  atr={row['atr_mult']:.2f}, d={int(row['depth_atr'])}, "
              f"red={row['reduction']:.2f}, lb={int(row['lookback_bars'])}, "
              f"comp={row['compression_threshold']}, asc={row['require_ascending_lows']}, "
              f"tol={row['tolerance']:.2f} "
              f"-> {int(row['signals'])} sen, {int(row['trades'])}T, "
              f"WR={fmt_wr(row['WR'])}, CR={fmt_pct(row['CR'])}")

    # ══════════════════════════════════════════════════════════
    #  FASE 2: GRILLA DE SALIDA EN TRAIN
    # ══════════════════════════════════════════════════════════

    best = det_df_sorted.iloc[0]
    best_atr_mult = best["atr_mult"]
    best_depth_atr = int(best["depth_atr"])
    best_reduction = best["reduction"]
    best_lookback = int(best["lookback_bars"])
    best_comp = best["compression_threshold"]
    best_asc = best["require_ascending_lows"]
    best_tol = best["tolerance"]

    print(f"\n\n{'='*70}")
    print(f"  FASE 2: GRILLA DE SALIDA — {TICKER} TRAIN")
    print(f"  atr_mult={best_atr_mult}, depth={best_depth_atr}, red={best_reduction}, "
          f"lb={best_lookback}")
    print(f"  comp={best_comp}, asc={best_asc}, tol={best_tol}")
    print(f"{'='*70}")

    best_seq = make_seq_params(best_depth_atr, best_reduction, best_lookback, best_tol, best_asc)
    best_comp_params = {"method": "ratio", "atr_period": 14, "ratio_threshold": best_comp}
    best_cache = caches_train[best_atr_mult]
    signals_train = detect_signals(train, best_seq, best_cache, best_comp_params)
    print(f"  Senales detectadas en TRAIN: {len(signals_train)}")

    exit_results = []
    t0 = time.time()
    for trail in TRAILING_MULTS:
        for target in TARGET_RS:
            for early in EARLY_EXITS:
                for be_r in BREAKEVEN_RS:
                    risk = {**RISK_BASE, "trailing_atr_multiplier": trail,
                            "target_r_multiple": target, "early_exit_days": early,
                            "breakeven_r_multiple": be_r}
                    ev = evaluate_signals_seq(train, signals_train, risk)
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

    print("\nTop 15 configs salida:")
    for _, row in exit_df_sorted.head(15).iterrows():
        t_r = row['target_r_multiple'] if pd.notna(row['target_r_multiple']) else 'None'
        e_e = int(row['early_exit_days']) if pd.notna(row['early_exit_days']) else 'None'
        print(f"  trail={row['trailing_atr_multiplier']}, target={t_r}, early={e_e}, "
              f"be_R={row['breakeven_r_multiple']}"
              f" -> {int(row['trades'])}T, WR={fmt_wr(row['WR'])}, CR={fmt_pct(row['CR'])}")

    best_exit_row = exit_df_sorted.iloc[0]
    best_exit = {
        "trailing_atr_multiplier": best_exit_row["trailing_atr_multiplier"],
        "target_r_multiple": best_exit_row["target_r_multiple"] if pd.notna(best_exit_row["target_r_multiple"]) else None,
        "early_exit_days": int(best_exit_row["early_exit_days"]) if pd.notna(best_exit_row["early_exit_days"]) else None,
        "breakeven_r_multiple": best_exit_row["breakeven_r_multiple"],
    }

    # ══════════════════════════════════════════════════════════
    #  FASE 3: EVALUACION TRAIN / TEST / FULL + MLflow
    # ══════════════════════════════════════════════════════════

    print(f"\n\n{'='*70}")
    print(f"  FASE 3: EVALUACION + MLflow — {TICKER}")
    print(f"{'='*70}")

    risk_best = {**RISK_BASE, **best_exit}
    splits = {"TRAIN": train, "TEST": test, "FULL": daily}

    all_params = {
        "ticker": TICKER, "cutoff": CUTOFF, "grouping": "sequential",
        "atr_mult": float(best_atr_mult),
        "depth_atr": best_depth_atr, "reduction": best_reduction,
        "lookback_bars": best_lookback,
        "compression_threshold": best_comp,
        "require_ascending_lows": best_asc,
        "tolerance": best_tol,
        **{f"risk_{k}": str(v) for k, v in risk_best.items()},
    }

    print(f"\n  {'Split':<8s} | {'Sen':>5s} | {'Trades':>6s} | {'WR':>5s} | {'CR':>8s} | {'AvgR':>6s} | Salidas")
    print(f"  {'─'*80}")

    ev_by_split = {}
    with mlflow.start_run(run_name=f"eurusd_expanded_detection") as parent_run:
        for split_name, ohlc in splits.items():
            cache = precompute(ohlc, best_atr_mult)
            signals = detect_signals(ohlc, best_seq, cache, best_comp_params)
            ev = evaluate_signals_seq(ohlc, signals, risk_best)
            ev_by_split[split_name] = (len(signals), ev)
            reasons_str = ", ".join(f"{k}={v}" for k, v in sorted(ev["reasons"].items()))
            print(f"  {split_name:<8s} | {len(signals):>5d} | {ev['trades']:>6d} | "
                  f"{fmt_wr(ev['WR']):>5s} | {fmt_pct(ev['CR']):>8s} | {ev['avg_R']:>+6.2f} | {reasons_str}")

        for split_name in ["TRAIN", "TEST", "FULL"]:
            n_sig, ev = ev_by_split[split_name]
            ohlc = splits[split_name]
            bh = buy_and_hold_metrics(ohlc)
            strat = strategy_metrics(ohlc, ev["trade_details"])

            with mlflow.start_run(run_name=f"{TICKER}_{split_name}_expanded", nested=True):
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

        # Log sensitivity analysis as artifact
        with tempfile.TemporaryDirectory() as tmpdir:
            det_path = Path(tmpdir) / "phase1_all_configs.csv"
            det_df.to_csv(det_path, index=False)
            mlflow.log_artifact(str(det_path), "grids")

            exit_path = Path(tmpdir) / "phase2_all_configs.csv"
            exit_df.to_csv(exit_path, index=False)
            mlflow.log_artifact(str(exit_path), "grids")

    # ── Trade detail ──────────────────────────────────────────

    print(f"\n\n{'='*70}")
    print(f"  DETALLE DE TRADES EN TEST")
    print(f"{'='*70}")

    _, ev_test = ev_by_split["TEST"]
    if not ev_test["trade_details"]:
        print("  (sin trades en TEST)")
    else:
        for i, (pat, trade) in enumerate(ev_test["trade_details"], 1):
            entry_str = pat["first_signal_date"].strftime("%Y-%m-%d")
            exit_str = trade["exit_date"].strftime("%Y-%m-%d")
            print(f"  Trade {i}: {entry_str} -> {exit_str} | {trade['exit_reason']:<15s} | "
                  f"PnL={trade['pnl_pct']:+.2%} | R={trade['r_multiple']:+.1f}R | "
                  f"Dur={trade['duration_days']}d")

    # ── Final summary ─────────────────────────────────────────

    print(f"\n\n{'='*70}")
    print(f"  RESUMEN FINAL")
    print(f"{'='*70}")
    print(f"  Config deteccion:")
    print(f"    atr_mult={best_atr_mult}, depth_atr={best_depth_atr}, "
          f"reduction={best_reduction}, lookback={best_lookback}")
    print(f"    compression_threshold={best_comp}, "
          f"require_ascending_lows={best_asc}, tolerance={best_tol}")
    print(f"  Config salida:")
    print(f"    trail={best_exit['trailing_atr_multiplier']}, "
          f"target={best_exit['target_r_multiple']}, "
          f"early={best_exit['early_exit_days']}, "
          f"be_R={best_exit['breakeven_r_multiple']}")

    for split_name in ["TRAIN", "TEST", "FULL"]:
        n_sig, ev = ev_by_split[split_name]
        print(f"  {split_name}: {n_sig} sen, {ev['trades']}T, "
              f"WR={fmt_wr(ev['WR'])}, CR={fmt_pct(ev['CR'])}")

    print("\nCompleto!")
