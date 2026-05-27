"""High atr_mult + max_depth_atr exploration for stocks.

Analogous to fx_eurusd_high_atr but for NVDA, MSFT, GOOGL, AAPL, AMZN.
Tests whether disabling max_depth_atr unlocks profitable patterns with
higher atr_mult values, as discovered in the hourly FX experiments.

Key differences from the FX version:
  - max_stop_loss_pct: 7% (stocks) vs 2% (FX)
  - max_depth_pct: 0.35 (Minervini standard for stocks)
  - Train/Test split: 70% / 30% (temporal)

Phase 1: 432 detection configs per ticker
Phase 2: 240 exit configs per ticker

Usage:
    python run_stocks_high_atr.py                  # all 5 stocks
    python run_stocks_high_atr.py AAPL NVDA        # specific stocks
"""
import functools
import sys
import tempfile
import time
from pathlib import Path

print = functools.partial(print, flush=True)

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

ALL_TICKERS = ["AAPL", "AMZN", "GOOGL", "MSFT", "NVDA"]
TRAIN_RATIO = 0.70

# Phase 1: Detection grid
ATR_MULTS = [2.5, 3.0, 4.0, 5.0]
MAX_DEPTH_ATRS = [None, 4, 6, 8]
REDUCTIONS = [0.40, 0.60, 0.80]
LOOKBACK_BARS = [63, 84, 126]
COMPRESSION_THRESHOLDS = [0.85, 0.90, 0.95]

TOLERANCE = 0.15
ASCENDING_LOWS = False

# Phase 2: Exit grid
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
    "max_stop_loss_pct": 0.07,
    "trailing_sma_period": 20,
    "trailing_volume_factor": 1.5,
    "trailing_stop_method": "atr",
    "trailing_atr_period": 14,
    "max_bars_without_progress": 15,
    "min_progress_r": 0.5,
}

DATA_DIR = project_root / "data" / "csv"

cli_tickers = [t.upper() for t in sys.argv[1:] if not t.startswith("-")]
TICKERS = cli_tickers if cli_tickers else ALL_TICKERS

for ticker in TICKERS:
    fpath = DATA_DIR / f"{ticker}.csv"
    if not fpath.exists():
        print(f"ERROR: {fpath} no encontrado")
        sys.exit(1)

n_det = (len(ATR_MULTS) * len(MAX_DEPTH_ATRS) * len(REDUCTIONS)
         * len(LOOKBACK_BARS) * len(COMPRESSION_THRESHOLDS))
n_exit = len(TRAILING_MULTS) * len(TARGET_RS) * len(EARLY_EXITS) * len(BREAKEVEN_RS)
print(f"Stocks: {TICKERS}")
print(f"Por stock: {n_det} configs deteccion + {n_exit} configs salida")
print(f"Train/Test split: {TRAIN_RATIO:.0%} / {1-TRAIN_RATIO:.0%}\n")


# ── Helpers ──────────────────────────────────────────────────


def load_ticker(ticker):
    return pd.read_csv(DATA_DIR / f"{ticker}.csv", parse_dates=["date"], index_col="date")


def split_data(ohlc):
    n = len(ohlc)
    cutoff_idx = int(n * TRAIN_RATIO)
    cutoff_date = ohlc.index[cutoff_idx]
    train = ohlc.iloc[:cutoff_idx]
    test = ohlc.iloc[cutoff_idx:]
    return train, test, cutoff_date


def precompute(ohlc, atr_mult):
    config = ATRZigZagConfig(atr_length=14, atr_mult=atr_mult, use_close_only=False)
    detector = ATRZigZagDetector(config)
    swings = detector.detect(ohlc)
    contractions = compute_contractions(swings, ohlc)
    atr = compute_atr(ohlc, 14)
    return {"ohlc": ohlc, "swings": swings, "contractions": contractions,
            "atr": atr, "detector": detector}


def make_seq_params(max_depth_atr, reduction, lookback_bars):
    return {
        "method": "tolerance", "min_contractions": 2, "max_contractions": 6,
        "lookback_bars": lookback_bars, "tolerance": TOLERANCE,
        "max_depth_pct": 0.35, "max_depth_atr": max_depth_atr,
        "min_total_reduction": reduction,
        "max_gap_between_contractions_days": None,
        "require_ascending_lows": ASCENDING_LOWS,
        "ascending_lows_tolerance": 0.01,
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


def build_trade_table(ticker, trade_details):
    rows = []
    for i, (pat, trade) in enumerate(trade_details, 1):
        rows.append({
            "ticker": ticker, "trade_num": i,
            "entry_date": pat["first_signal_date"].strftime("%Y-%m-%d"),
            "exit_date": trade["exit_date"].strftime("%Y-%m-%d"),
            "exit_reason": trade["exit_reason"],
            "duration_days": trade["duration_days"],
            "entry_price": pat["entry_price"],
            "exit_price": trade["exit_price"],
            "pnl_pct": trade["pnl_pct"], "r_multiple": trade["r_multiple"],
            "max_r": trade["max_r"],
        })
    return pd.DataFrame(rows)


def mda_label(val):
    return "None" if val is None else str(int(val)) if isinstance(val, float) and not np.isnan(val) else str(val)


# ══════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    mlflow.set_tracking_uri(str(project_root / "mlruns"))
    mlflow.set_experiment("VCP_Stocks_HighATR")

    summary_rows = []

    for ticker in TICKERS:
        daily = load_ticker(ticker)
        train, test, cutoff_date = split_data(daily)

        print(f"\n{'#'*70}")
        print(f"  {ticker}: {len(daily):,} barras ({daily.index.min().date()} a {daily.index.max().date()})")
        print(f"  TRAIN: {len(train):,} barras (hasta {train.index[-1].date()})")
        print(f"  TEST:  {len(test):,} barras (desde {test.index[0].date()})")
        print(f"{'#'*70}")

        # ══════════════════════════════════════════════════════
        #  FASE 1: GRILLA DE DETECCION — TRAIN
        # ══════════════════════════════════════════════════════

        print(f"\n{'='*70}")
        print(f"  FASE 1: DETECCION — {ticker} TRAIN ({n_det} configs)")
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

            configs_per_mult = (len(MAX_DEPTH_ATRS) * len(REDUCTIONS)
                                * len(LOOKBACK_BARS) * len(COMPRESSION_THRESHOLDS))
            mult_done = 0
            last_pct = -1

            for max_depth_atr in MAX_DEPTH_ATRS:
                for reduction in REDUCTIONS:
                    for lookback in LOOKBACK_BARS:
                        for comp_thresh in COMPRESSION_THRESHOLDS:
                            seq = make_seq_params(max_depth_atr, reduction, lookback)
                            comp_params = {"method": "ratio", "atr_period": 14,
                                           "ratio_threshold": comp_thresh}
                            signals = detect_signals(train, seq, cache, comp_params)
                            ev = evaluate_signals_seq(train, signals, fixed_risk,
                                                      precomputed_atr=cache["atr"])
                            all_det_results.append({
                                "atr_mult": atr_mult,
                                "max_depth_atr": max_depth_atr,
                                "reduction": reduction, "lookback_bars": lookback,
                                "compression_threshold": comp_thresh,
                                "n_swings": n_swings, "n_contractions": n_contr,
                                "signals": len(signals),
                                **{k: ev[k] for k in ["trades", "wins", "WR", "CR", "avg_R"]},
                            })
                            configs_done += 1
                            mult_done += 1
                            pct = mult_done * 100 // configs_per_mult
                            if pct >= last_pct + 25:
                                elapsed_total = time.time() - t_total
                                eta_total = elapsed_total / configs_done * (n_det - configs_done) if configs_done > 0 else 0
                                print(f"    atr_mult={atr_mult:.1f}: {pct}% | "
                                      f"total {configs_done}/{n_det} | ETA {eta_total:.0f}s")
                                last_pct = pct

            elapsed = time.time() - t0
            best_in_mult = max((r for r in all_det_results if r["atr_mult"] == atr_mult),
                               key=lambda r: r["CR"], default=None)
            best_cr = fmt_pct(best_in_mult["CR"]) if best_in_mult else "N/A"
            print(f"  atr_mult={atr_mult:.1f}: {n_swings} sw, {n_contr} contr, "
                  f"best_CR={best_cr} ({elapsed:.1f}s)")

        det_df = pd.DataFrame(all_det_results)
        total_time = time.time() - t_total
        det_df_sorted = det_df.sort_values("CR", ascending=False)
        print(f"  Total Fase 1: {len(det_df)} configs en {total_time:.1f}s")

        # ── Sensitivity: max_depth_atr ────────────────────────

        print(f"\n  --- max_depth_atr ---")
        for val in MAX_DEPTH_ATRS:
            if val is None:
                sub = det_df[det_df["max_depth_atr"].isna()]
            else:
                sub = det_df[det_df["max_depth_atr"] == val]
            if len(sub) == 0:
                continue
            has_trades = sub[sub["trades"] > 0]
            label = mda_label(val)
            print(f"  mda={label:>4s}: avg_sig={sub['signals'].mean():>6.1f}, "
                  f"avg_T={sub['trades'].mean():>5.1f}, avg_CR={sub['CR'].mean():+.4f}, "
                  f"best_CR={sub['CR'].max():+.4f}, con_T={len(has_trades)}/{len(sub)}")

        print(f"\n  --- atr_mult ---")
        for val in ATR_MULTS:
            sub = det_df[det_df["atr_mult"] == val]
            has_trades = sub[sub["trades"] > 0]
            print(f"  atr={val:.1f}: avg_sig={sub['signals'].mean():>6.1f}, "
                  f"avg_T={sub['trades'].mean():>5.1f}, avg_CR={sub['CR'].mean():+.4f}, "
                  f"best_CR={sub['CR'].max():+.4f}, con_T={len(has_trades)}/{len(sub)}")

        # ── Interaction: atr_mult x max_depth_atr ────────────

        print(f"\n  --- Interaccion atr_mult x max_depth_atr ---")
        print(f"  {'atr':>5s} | {'mda':>4s} | {'avg_sig':>7s} | {'avg_T':>5s} | "
              f"{'avg_CR':>8s} | {'best_CR':>8s} | {'con_T':>5s}")
        print(f"  {'─'*55}")
        for am in ATR_MULTS:
            for mda in MAX_DEPTH_ATRS:
                if mda is None:
                    sub = det_df[(det_df["atr_mult"] == am) & (det_df["max_depth_atr"].isna())]
                else:
                    sub = det_df[(det_df["atr_mult"] == am) & (det_df["max_depth_atr"] == mda)]
                if len(sub) == 0:
                    continue
                has_t = sub[sub["trades"] > 0]
                label = mda_label(mda)
                print(f"  {am:>5.1f} | {label:>4s} | {sub['signals'].mean():>7.1f} | "
                      f"{sub['trades'].mean():>5.1f} | {sub['CR'].mean():>+8.4f} | "
                      f"{sub['CR'].max():>+8.4f} | {len(has_t):>2d}/{len(sub)}")

        # ── Top 10 configs ────────────────────────────────────

        print(f"\n  Top 10 configs:")
        for _, row in det_df_sorted.head(10).iterrows():
            label = mda_label(row['max_depth_atr'])
            print(f"    atr={row['atr_mult']:.1f}, mda={label:>4s}, "
                  f"red={row['reduction']:.2f}, lb={int(row['lookback_bars'])}, "
                  f"comp={row['compression_threshold']} "
                  f"-> {int(row['signals'])} sen, {int(row['trades'])}T, "
                  f"WR={fmt_wr(row['WR'])}, CR={fmt_pct(row['CR'])}")

        # ══════════════════════════════════════════════════════
        #  FASE 2: GRILLA DE SALIDA EN TRAIN
        # ══════════════════════════════════════════════════════

        best = det_df_sorted.iloc[0]
        best_atr_mult = best["atr_mult"]
        best_max_depth_atr = best["max_depth_atr"]
        best_reduction = best["reduction"]
        best_lookback = int(best["lookback_bars"])
        best_comp = best["compression_threshold"]

        b_mda = mda_label(best_max_depth_atr)
        print(f"\n{'='*70}")
        print(f"  FASE 2: SALIDA — {ticker} TRAIN")
        print(f"  atr={best_atr_mult}, mda={b_mda}, red={best_reduction}, "
              f"lb={best_lookback}, comp={best_comp}")
        print(f"{'='*70}")

        best_seq = make_seq_params(
            None if (isinstance(best_max_depth_atr, float) and np.isnan(best_max_depth_atr)) else best_max_depth_atr,
            best_reduction, best_lookback)
        best_comp_params = {"method": "ratio", "atr_period": 14, "ratio_threshold": best_comp}
        best_cache = caches_train[best_atr_mult]
        signals_train = detect_signals(train, best_seq, best_cache, best_comp_params)
        print(f"  Senales en TRAIN: {len(signals_train)}")

        if len(signals_train) == 0:
            print("  (0 senales — Fase 2 trivial)")
            best_exit = {
                "trailing_atr_multiplier": 1.5, "target_r_multiple": 3.0,
                "early_exit_days": None, "breakeven_r_multiple": 1.0,
            }
        else:
            exit_results = []
            t0 = time.time()
            for trail in TRAILING_MULTS:
                for target in TARGET_RS:
                    for early in EARLY_EXITS:
                        for be_r in BREAKEVEN_RS:
                            risk = {**RISK_BASE, "trailing_atr_multiplier": trail,
                                    "target_r_multiple": target, "early_exit_days": early,
                                    "breakeven_r_multiple": be_r}
                            ev = evaluate_signals_seq(train, signals_train, risk,
                                                      precomputed_atr=best_cache["atr"])
                            exit_results.append({
                                "trailing_atr_multiplier": trail, "target_r_multiple": target,
                                "early_exit_days": early, "breakeven_r_multiple": be_r,
                                **{k: ev[k] for k in ["trades", "wins", "WR", "CR", "avg_R"]},
                            })

            exit_df = pd.DataFrame(exit_results)
            exit_df_sorted = exit_df.sort_values("CR", ascending=False)
            print(f"  {len(exit_df)} configs en {time.time()-t0:.1f}s")

            print(f"\n  Top 10 configs salida:")
            for _, row in exit_df_sorted.head(10).iterrows():
                t_r = row['target_r_multiple'] if pd.notna(row['target_r_multiple']) else 'None'
                e_e = int(row['early_exit_days']) if pd.notna(row['early_exit_days']) else 'None'
                print(f"    trail={row['trailing_atr_multiplier']}, target={t_r}, "
                      f"early={e_e}, be_R={row['breakeven_r_multiple']}"
                      f" -> {int(row['trades'])}T, WR={fmt_wr(row['WR'])}, CR={fmt_pct(row['CR'])}")

            best_exit_row = exit_df_sorted.iloc[0]
            best_exit = {
                "trailing_atr_multiplier": best_exit_row["trailing_atr_multiplier"],
                "target_r_multiple": best_exit_row["target_r_multiple"] if pd.notna(best_exit_row["target_r_multiple"]) else None,
                "early_exit_days": int(best_exit_row["early_exit_days"]) if pd.notna(best_exit_row["early_exit_days"]) else None,
                "breakeven_r_multiple": best_exit_row["breakeven_r_multiple"],
            }

        # ══════════════════════════════════════════════════════
        #  FASE 3: EVALUACION TRAIN / TEST / FULL + MLflow
        # ══════════════════════════════════════════════════════

        print(f"\n{'='*70}")
        print(f"  FASE 3: EVALUACION — {ticker}")
        print(f"{'='*70}")

        risk_best = {**RISK_BASE, **best_exit}
        splits = {"TRAIN": train, "TEST": test, "FULL": daily}

        real_mda = None if (isinstance(best_max_depth_atr, float) and np.isnan(best_max_depth_atr)) else best_max_depth_atr
        all_params = {
            "ticker": ticker, "cutoff": str(cutoff_date.date()),
            "train_ratio": TRAIN_RATIO, "grouping": "sequential",
            "atr_mult": float(best_atr_mult),
            "max_depth_atr": str(real_mda),
            "reduction": best_reduction,
            "lookback_bars": best_lookback,
            "compression_threshold": best_comp,
            "tolerance": TOLERANCE,
            "require_ascending_lows": ASCENDING_LOWS,
            **{f"risk_{k}": str(v) for k, v in risk_best.items()},
        }

        print(f"\n  {'Split':<8s} | {'Sen':>5s} | {'Trades':>6s} | {'WR':>5s} | {'CR':>8s} | {'AvgR':>6s} | Salidas")
        print(f"  {'─'*80}")

        ev_by_split = {}
        with mlflow.start_run(run_name=f"{ticker}_high_atr") as parent_run:
            for split_name, ohlc in splits.items():
                cache = precompute(ohlc, best_atr_mult)
                signals = detect_signals(ohlc, best_seq, cache, best_comp_params)
                ev = evaluate_signals_seq(ohlc, signals, risk_best,
                                          precomputed_atr=cache["atr"])
                ev_by_split[split_name] = (len(signals), ev)
                reasons_str = ", ".join(f"{k}={v}" for k, v in sorted(ev["reasons"].items()))
                print(f"  {split_name:<8s} | {len(signals):>5d} | {ev['trades']:>6d} | "
                      f"{fmt_wr(ev['WR']):>5s} | {fmt_pct(ev['CR']):>8s} | "
                      f"{ev['avg_R']:>+6.2f} | {reasons_str}")

            for split_name in ["TRAIN", "TEST", "FULL"]:
                n_sig, ev = ev_by_split[split_name]
                ohlc = splits[split_name]
                bh = buy_and_hold_metrics(ohlc)
                strat = strategy_metrics(ohlc, ev["trade_details"])

                with mlflow.start_run(run_name=f"{ticker}_{split_name}_high_atr", nested=True):
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
                            tdf = build_trade_table(ticker, ev["trade_details"])
                            tcp = Path(tmpdir) / "trades.csv"
                            tdf.to_csv(tcp, index=False)
                            mlflow.log_artifact(str(tcp), "tables")

            with tempfile.TemporaryDirectory() as tmpdir:
                det_path = Path(tmpdir) / "phase1_all_configs.csv"
                det_df.to_csv(det_path, index=False)
                mlflow.log_artifact(str(det_path), "grids")
                if len(signals_train) > 0:
                    exit_path = Path(tmpdir) / "phase2_all_configs.csv"
                    exit_df.to_csv(exit_path, index=False)
                    mlflow.log_artifact(str(exit_path), "grids")

        # ── Trade detail (TEST) ───────────────────────────────

        print(f"\n  Trades en TEST:")
        _, ev_test = ev_by_split["TEST"]
        if not ev_test["trade_details"]:
            print("  (sin trades)")
        else:
            for i, (pat, trade) in enumerate(ev_test["trade_details"], 1):
                entry_str = pat["first_signal_date"].strftime("%Y-%m-%d")
                exit_str = trade["exit_date"].strftime("%Y-%m-%d")
                print(f"    {i}: {entry_str} -> {exit_str} | {trade['exit_reason']:<15s} | "
                      f"PnL={trade['pnl_pct']:+.2%} | R={trade['r_multiple']:+.1f}R | "
                      f"Dur={trade['duration_days']}d")

        # ── Year-by-year (TEST) ───────────────────────────────

        if ev_test["trade_details"]:
            print(f"\n  Desglose por ano (TEST):")
            test_trades = []
            for pat, trade in ev_test["trade_details"]:
                test_trades.append({
                    "year": pat["first_signal_date"].year,
                    "pnl_pct": trade["pnl_pct"],
                    "exit_reason": trade["exit_reason"],
                })
            tdf = pd.DataFrame(test_trades)
            for year in sorted(tdf["year"].unique()):
                yt = tdf[tdf["year"] == year]
                n = len(yt)
                wins = (yt["pnl_pct"] > 0).sum()
                cr = float(np.prod(1 + yt["pnl_pct"]) - 1)
                sl_rate = (yt["exit_reason"] == "stop_loss").sum() / n if n > 0 else 0
                print(f"    {year}: {n}T, WR={wins}/{n} ({wins/n:.0%}), "
                      f"CR={cr:+.2%}, SL_rate={sl_rate:.0%}")

        # ── Summary row ───────────────────────────────────────

        _, ev_train = ev_by_split["TRAIN"]
        _, ev_test = ev_by_split["TEST"]
        summary_rows.append({
            "ticker": ticker,
            "cutoff": str(cutoff_date.date()),
            "atr_mult": best_atr_mult,
            "max_depth_atr": mda_label(real_mda),
            "reduction": best_reduction,
            "lookback": best_lookback,
            "compression": best_comp,
            "trail": best_exit["trailing_atr_multiplier"],
            "target_R": best_exit["target_r_multiple"],
            "be_R": best_exit["breakeven_r_multiple"],
            "early": best_exit["early_exit_days"],
            "train_trades": ev_train["trades"],
            "train_WR": ev_train["WR"],
            "train_CR": ev_train["CR"],
            "test_trades": ev_test["trades"],
            "test_WR": ev_test["WR"],
            "test_CR": ev_test["CR"],
        })

    # ══════════════════════════════════════════════════════════
    #  RESUMEN GLOBAL
    # ══════════════════════════════════════════════════════════

    print(f"\n\n{'#'*70}")
    print(f"  RESUMEN GLOBAL — {len(TICKERS)} STOCKS")
    print(f"{'#'*70}")

    print(f"\n  {'Ticker':<6s} | {'atr':>3s} | {'mda':>4s} | {'red':>4s} | {'lb':>3s} | "
          f"{'trail':>5s} | {'tgt':>4s} | "
          f"{'T_T':>3s} | {'T_WR':>4s} | {'T_CR':>7s} | "
          f"{'Te_T':>4s} | {'Te_WR':>5s} | {'Te_CR':>7s}")
    print(f"  {'─'*90}")

    for row in summary_rows:
        tgt = str(row['target_R']) if row['target_R'] is not None else 'None'
        print(f"  {row['ticker']:<6s} | {row['atr_mult']:>3.1f} | {row['max_depth_atr']:>4s} | "
              f"{row['reduction']:>4.2f} | {row['lookback']:>3d} | "
              f"{row['trail']:>5.1f} | {tgt:>4s} | "
              f"{row['train_trades']:>3d} | {row['train_WR']:>4.0%} | {row['train_CR']:>+7.2%} | "
              f"{row['test_trades']:>4d} | {row['test_WR']:>5.0%} | {row['test_CR']:>+7.2%}")

    print("\nCompleto!")
