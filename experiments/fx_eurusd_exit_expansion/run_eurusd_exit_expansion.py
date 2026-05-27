"""Expanded exit grid for EURUSD — two detection configs.

Tests both the original (fx_sequential) and expanded (fx_eurusd_detection)
Phase 1 configs with an enlarged Phase 2 grid that varies:
  - trailing_atr_multiplier: [1.0, 1.5, 2.0, 2.5, 3.0]
  - target_r_multiple: [None, 2.0, 3.0, 5.0]
  - early_exit_days: [None, 3, 5]
  - breakeven_r_multiple: [0.5, 1.0, 1.5, 2.0]
  - max_stop_loss_pct: [0.01, 0.015, 0.02]          (NEW)
  - max_bars_without_progress: [10, 15, 20, None]    (NEW)

Total: 2 detection configs x 2,880 exit configs = 5,760 evaluations.

Usage:
    python run_eurusd_exit_expansion.py
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

TICKER = "EURUSD"
CUTOFF = "2020-01-01"

DETECTION_CONFIGS = {
    "original": {
        "atr_mult": 2.5, "depth_atr": 5, "reduction": 0.6, "lookback_bars": 63,
        "compression_threshold": 0.85, "require_ascending_lows": True, "tolerance": 0.10,
    },
    "expanded": {
        "atr_mult": 1.5, "depth_atr": 4, "reduction": 0.7, "lookback_bars": 84,
        "compression_threshold": 0.90, "require_ascending_lows": False, "tolerance": 0.15,
    },
}

# Exit grid (original 4 + 2 new)
TRAILING_MULTS = [1.0, 1.5, 2.0, 2.5, 3.0]
TARGET_RS = [None, 2.0, 3.0, 5.0]
EARLY_EXITS = [None, 3, 5]
BREAKEVEN_RS = [0.5, 1.0, 1.5, 2.0]
MAX_STOP_LOSS_PCTS = [0.01, 0.015, 0.02]
MAX_BARS_WITHOUT_PROGRESS = [10, 15, 20, None]

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
}

DATA_DIR = project_root / "data" / "monedas"
fpath = DATA_DIR / f"{TICKER}.csv"
if not fpath.exists():
    print(f"ERROR: {fpath} no encontrado")
    sys.exit(1)

n_exit = (len(TRAILING_MULTS) * len(TARGET_RS) * len(EARLY_EXITS)
          * len(BREAKEVEN_RS) * len(MAX_STOP_LOSS_PCTS) * len(MAX_BARS_WITHOUT_PROGRESS))
print(f"Moneda: {TICKER}")
print(f"Configs deteccion: {len(DETECTION_CONFIGS)} (original + expanded)")
print(f"Configs salida: {n_exit:,}")
print(f"Total evaluaciones: {len(DETECTION_CONFIGS) * n_exit:,}")
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


def make_seq_params(det_cfg):
    return {
        "method": "tolerance", "min_contractions": 2, "max_contractions": 6,
        "lookback_bars": det_cfg["lookback_bars"], "tolerance": det_cfg["tolerance"],
        "max_depth_pct": 0.50, "max_depth_atr": det_cfg["depth_atr"],
        "min_total_reduction": det_cfg["reduction"],
        "max_gap_between_contractions_days": None,
        "require_ascending_lows": det_cfg["require_ascending_lows"],
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
    mlflow.set_experiment("VCP_FX_EURUSD_Exit_Expansion")

    best_results = {}

    for det_name, det_cfg in DETECTION_CONFIGS.items():
        print(f"\n{'='*70}")
        print(f"  DETECCION: {det_name.upper()}")
        print(f"  atr_mult={det_cfg['atr_mult']}, depth={det_cfg['depth_atr']}, "
              f"red={det_cfg['reduction']}, lb={det_cfg['lookback_bars']}")
        print(f"  comp={det_cfg['compression_threshold']}, "
              f"asc={det_cfg['require_ascending_lows']}, tol={det_cfg['tolerance']}")
        print(f"{'='*70}")

        # Precompute and detect signals on TRAIN
        cache_train = precompute(train, det_cfg["atr_mult"])
        seq_params = make_seq_params(det_cfg)
        comp_params = {"method": "ratio", "atr_period": 14,
                       "ratio_threshold": det_cfg["compression_threshold"]}
        signals_train = detect_signals(train, seq_params, cache_train, comp_params)
        print(f"  Senales en TRAIN: {len(signals_train)}")

        # ── Exit grid on TRAIN ────────────────────────────────
        exit_results = []
        t0 = time.time()
        configs_done = 0
        last_pct = -1

        for max_sl in MAX_STOP_LOSS_PCTS:
            for max_bars in MAX_BARS_WITHOUT_PROGRESS:
                for trail in TRAILING_MULTS:
                    for target in TARGET_RS:
                        for early in EARLY_EXITS:
                            for be_r in BREAKEVEN_RS:
                                risk = {
                                    **RISK_FIXED,
                                    "max_stop_loss_pct": max_sl,
                                    "max_bars_without_progress": max_bars,
                                    "trailing_atr_multiplier": trail,
                                    "target_r_multiple": target,
                                    "early_exit_days": early,
                                    "breakeven_r_multiple": be_r,
                                }
                                ev = evaluate_signals_seq(
                                    train, signals_train, risk,
                                    precomputed_atr=cache_train["atr"],
                                )
                                exit_results.append({
                                    "max_stop_loss_pct": max_sl,
                                    "max_bars_without_progress": max_bars,
                                    "trailing_atr_multiplier": trail,
                                    "target_r_multiple": target,
                                    "early_exit_days": early,
                                    "breakeven_r_multiple": be_r,
                                    **{k: ev[k] for k in ["trades", "wins", "WR", "CR", "avg_R"]},
                                    "early_exits": ev["reasons"].get("early_exit", 0),
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
                                    print(f"    {det_name}: {pct}% ({configs_done:,}/{n_exit:,}) "
                                          f"| {elapsed:.0f}s | ETA {eta:.0f}s")
                                    last_pct = pct

        exit_df = pd.DataFrame(exit_results)
        exit_df_sorted = exit_df.sort_values("CR", ascending=False)
        elapsed_total = time.time() - t0
        print(f"  {len(exit_df):,} configs en {elapsed_total:.1f}s")

        # ── Sensitivity analysis on new parameters ────────────
        print(f"\n  --- Sensibilidad: max_stop_loss_pct ---")
        for val in MAX_STOP_LOSS_PCTS:
            sub = exit_df[exit_df["max_stop_loss_pct"] == val]
            has_trades = sub[sub["trades"] > 0]
            print(f"    {val:.3f}: avg_trades={sub['trades'].mean():.1f}, "
                  f"avg_CR={sub['CR'].mean():+.4f}, best_CR={sub['CR'].max():+.4f}, "
                  f"configs_con_trades={len(has_trades)}/{len(sub)}")

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
                  f"configs_con_trades={len(has_trades)}/{len(sub)}")

        # ── Top 15 ────────────────────────────────────────────
        print(f"\n  Top 15 configs salida ({det_name}):")
        for _, row in exit_df_sorted.head(15).iterrows():
            t_r = row['target_r_multiple'] if pd.notna(row['target_r_multiple']) else 'None'
            e_e = int(row['early_exit_days']) if pd.notna(row['early_exit_days']) else 'None'
            m_b = int(row['max_bars_without_progress']) if pd.notna(row['max_bars_without_progress']) else 'None'
            print(f"    sl={row['max_stop_loss_pct']:.3f}, bars={m_b}, "
                  f"trail={row['trailing_atr_multiplier']}, target={t_r}, "
                  f"early={e_e}, be_R={row['breakeven_r_multiple']}"
                  f" -> {int(row['trades'])}T, WR={fmt_wr(row['WR'])}, CR={fmt_pct(row['CR'])}")

        best_exit_row = exit_df_sorted.iloc[0]
        best_exit = {
            "max_stop_loss_pct": best_exit_row["max_stop_loss_pct"],
            "max_bars_without_progress": best_exit_row["max_bars_without_progress"]
                if pd.notna(best_exit_row["max_bars_without_progress"]) else None,
            "trailing_atr_multiplier": best_exit_row["trailing_atr_multiplier"],
            "target_r_multiple": best_exit_row["target_r_multiple"]
                if pd.notna(best_exit_row["target_r_multiple"]) else None,
            "early_exit_days": int(best_exit_row["early_exit_days"])
                if pd.notna(best_exit_row["early_exit_days"]) else None,
            "breakeven_r_multiple": best_exit_row["breakeven_r_multiple"],
        }

        best_results[det_name] = {
            "det_cfg": det_cfg,
            "best_exit": best_exit,
            "exit_df": exit_df,
            "cache_train": cache_train,
            "seq_params": seq_params,
            "comp_params": comp_params,
            "signals_train": signals_train,
        }

    # ══════════════════════════════════════════════════════════
    #  EVALUACION TRAIN / TEST / FULL + MLflow
    # ══════════════════════════════════════════════════════════

    print(f"\n\n{'='*70}")
    print(f"  EVALUACION FINAL — TRAIN / TEST / FULL")
    print(f"{'='*70}")

    splits = {"TRAIN": train, "TEST": test, "FULL": daily}

    for det_name, br in best_results.items():
        det_cfg = br["det_cfg"]
        best_exit = br["best_exit"]
        risk_best = {**RISK_FIXED, **best_exit}

        print(f"\n  ── {det_name.upper()} ──")
        print(f"  Deteccion: atr={det_cfg['atr_mult']}, d={det_cfg['depth_atr']}, "
              f"red={det_cfg['reduction']}, lb={det_cfg['lookback_bars']}, "
              f"comp={det_cfg['compression_threshold']}, tol={det_cfg['tolerance']}")
        print(f"  Salida: sl={best_exit['max_stop_loss_pct']}, "
              f"bars={best_exit['max_bars_without_progress']}, "
              f"trail={best_exit['trailing_atr_multiplier']}, "
              f"target={best_exit['target_r_multiple']}, "
              f"early={best_exit['early_exit_days']}, "
              f"be_R={best_exit['breakeven_r_multiple']}")

        print(f"\n  {'Split':<8s} | {'Sen':>5s} | {'Trades':>6s} | {'WR':>5s} | {'CR':>8s} | {'AvgR':>6s} | Salidas")
        print(f"  {'─'*80}")

        all_params = {
            "ticker": TICKER, "cutoff": CUTOFF, "grouping": "sequential",
            "detection_config": det_name,
            "atr_mult": float(det_cfg["atr_mult"]),
            "depth_atr": det_cfg["depth_atr"],
            "reduction": det_cfg["reduction"],
            "lookback_bars": det_cfg["lookback_bars"],
            "compression_threshold": det_cfg["compression_threshold"],
            "require_ascending_lows": det_cfg["require_ascending_lows"],
            "tolerance": det_cfg["tolerance"],
            **{f"risk_{k}": str(v) for k, v in risk_best.items()},
        }

        ev_by_split = {}
        with mlflow.start_run(run_name=f"eurusd_exit_exp_{det_name}") as parent_run:
            for split_name, ohlc in splits.items():
                cache = precompute(ohlc, det_cfg["atr_mult"])
                signals = detect_signals(ohlc, br["seq_params"], cache, br["comp_params"])
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

                with mlflow.start_run(run_name=f"{TICKER}_{split_name}_{det_name}", nested=True):
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
                exit_path = Path(tmpdir) / f"exit_grid_{det_name}.csv"
                br["exit_df"].to_csv(exit_path, index=False)
                mlflow.log_artifact(str(exit_path), "grids")

        # ── Trade detail TEST ─────────────────────────────────
        _, ev_test = ev_by_split["TEST"]
        if ev_test["trade_details"]:
            print(f"\n  Detalle trades TEST ({det_name}):")
            for i, (pat, trade) in enumerate(ev_test["trade_details"], 1):
                entry_str = pat["first_signal_date"].strftime("%Y-%m-%d")
                exit_str = trade["exit_date"].strftime("%Y-%m-%d")
                print(f"    Trade {i}: {entry_str} -> {exit_str} | {trade['exit_reason']:<15s} | "
                      f"PnL={trade['pnl_pct']:+.2%} | R={trade['r_multiple']:+.1f}R | "
                      f"Dur={trade['duration_days']}d")

    # ══════════════════════════════════════════════════════════
    #  COMPARACION FINAL
    # ══════════════════════════════════════════════════════════

    print(f"\n\n{'='*70}")
    print(f"  COMPARACION FINAL — ORIGINAL vs EXPANDED")
    print(f"{'='*70}")

    print(f"\n  {'Config':<12s} | {'Split':<6s} | {'Sen':>5s} | {'T':>3s} | {'WR':>5s} | {'CR':>8s} | {'AvgR':>6s}")
    print(f"  {'─'*60}")

    for det_name, br in best_results.items():
        det_cfg = br["det_cfg"]
        best_exit = br["best_exit"]
        risk_best = {**RISK_FIXED, **best_exit}

        for split_name, ohlc in splits.items():
            cache = precompute(ohlc, det_cfg["atr_mult"])
            signals = detect_signals(ohlc, br["seq_params"], cache, br["comp_params"])
            ev = evaluate_signals_seq(ohlc, signals, risk_best,
                                      precomputed_atr=cache["atr"])
            print(f"  {det_name:<12s} | {split_name:<6s} | {len(signals):>5d} | {ev['trades']:>3d} | "
                  f"{fmt_wr(ev['WR']):>5s} | {fmt_pct(ev['CR']):>8s} | {ev['avg_R']:>+6.2f}")

    print("\nCompleto!")
