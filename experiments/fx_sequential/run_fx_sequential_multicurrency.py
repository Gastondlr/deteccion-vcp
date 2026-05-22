"""Sequential temporal stability experiment for FX currencies (excluding EURUSD).

Same methodology as the EURUSD sequential experiment:
- Two-phase optimization: detection grid (Phase 1) then exit grid (Phase 2)
- Sequential grouping (one trade at a time, no overlapping)
- lookback_bars as variable parameter (63, 84, 105, 126)
- TRAIN (2015-2019) / TEST (2020-2026) split

Usage:
    python run_fx_sequential_multicurrency.py                # all 4 currencies
    python run_fx_sequential_multicurrency.py GBPUSD USDJPY  # specific currencies
"""
import sys
import tempfile
import time
from collections import Counter
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

ALL_TICKERS = ["GBPUSD", "USDJPY", "USDCNH", "USDCNY"]
CUTOFF = "2020-01-01"

ATR_MULTS = [0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 2.5]
DEPTH_ATRS = [2, 3, 4, 5, 6]
REDUCTIONS = [0.40, 0.50, 0.60, 0.70, 0.80]
LOOKBACK_BARS = [63, 84, 105, 126]

TRAILING_MULTS = [1.0, 1.5, 2.0, 2.5, 3.0]
TARGET_RS = [None, 2.0, 3.0, 5.0]
EARLY_EXITS = [None, 3, 5]
BREAKEVEN_RS = [0.5, 1.0, 1.5, 2.0]

COMPRESSION = {"method": "ratio", "atr_period": 14, "ratio_threshold": 0.85}
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

# ── Currency selection ───────────────────────────────────────

DATA_DIR = project_root / "data" / "monedas"

cli_tickers = [t.upper() for t in sys.argv[1:] if not t.startswith("-")]
TICKERS = cli_tickers if cli_tickers else ALL_TICKERS

for ticker in TICKERS:
    fpath = DATA_DIR / f"{ticker}.csv"
    if not fpath.exists():
        print(f"ERROR: {fpath} no encontrado")
        sys.exit(1)

n_det = len(ATR_MULTS) * len(DEPTH_ATRS) * len(REDUCTIONS) * len(LOOKBACK_BARS)
n_exit = len(TRAILING_MULTS) * len(TARGET_RS) * len(EARLY_EXITS) * len(BREAKEVEN_RS)
print(f"Monedas: {TICKERS}")
print(f"Por moneda: {n_det} configs deteccion (incl. lookback_bars) + {n_exit} configs salida")
print(f"Cutoff: {CUTOFF} (TRAIN antes, TEST despues)\n")

# ── Helper functions ──────────────────────────────────────────


def load_ticker(ticker):
    return pd.read_csv(DATA_DIR / f"{ticker}.csv", parse_dates=["date"], index_col="date")


def precompute(ohlc, atr_mult):
    config = ATRZigZagConfig(atr_length=14, atr_mult=atr_mult, use_close_only=False)
    detector = ATRZigZagDetector(config)
    swings = detector.detect(ohlc)
    contractions = compute_contractions(swings, ohlc)
    atr = compute_atr(ohlc, COMPRESSION["atr_period"])
    return {"ohlc": ohlc, "swings": swings, "contractions": contractions,
            "atr": atr, "detector": detector}


def make_seq_params(depth_atr, reduction, lookback_bars):
    return {
        "method": "tolerance", "min_contractions": 2, "max_contractions": 6,
        "lookback_bars": lookback_bars, "tolerance": 0.10,
        "max_depth_pct": 0.50, "max_depth_atr": depth_atr,
        "min_total_reduction": reduction,
        "max_gap_between_contractions_days": None,
        "require_ascending_lows": True, "ascending_lows_tolerance": 0.03,
    }


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


def evaluate_signals(ohlc, signals, risk):
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


def fmt_pct(x):
    return f"{x:+.2%}"


def fmt_wr(x):
    return f"{x:.0%}"


def build_trade_table(trade_details, ticker):
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
            "n_contractions": pat["n_contractions"],
            "atr_ratio": pat["atr_ratio"],
        })
    return pd.DataFrame(rows)


def plot_combined(ohlc, pattern, trade, pattern_number, risk_params, ticker, save_path=None):
    sig = pattern["signal_obj"]
    seq = sig.pivot_info.sequence
    contractions = seq.contractions

    pattern_start = contractions[0].high_swing.date
    entry_date = pattern["first_signal_date"]
    exit_date = trade["exit_date"]
    entry_price = pattern["entry_price"]
    initial_risk = pattern["initial_risk"]

    start_loc = max(0, ohlc.index.get_loc(pattern_start) - 30)
    exit_loc = ohlc.index.get_loc(exit_date)
    end_loc = min(len(ohlc) - 1, exit_loc + 10)
    window = ohlc.iloc[start_loc:end_loc + 1]

    fig, (ax_price, ax_vol) = plt.subplots(
        2, 1, figsize=(16, 9), height_ratios=[3, 1], sharex=True,
        gridspec_kw={"hspace": 0.08},
    )

    ax_price.plot(window.index, window["close"], color="#2c3e50", linewidth=1.2, label="Close", zorder=2)

    colors_c = plt.cm.Blues(np.linspace(0.25, 0.55, len(contractions)))
    for i, c in enumerate(contractions):
        ax_price.axvspan(c.high_swing.date, c.low_swing.date, alpha=0.12, color=colors_c[i], zorder=0)
        mid = c.high_swing.date + (c.low_swing.date - c.high_swing.date) / 2
        ax_price.annotate(
            f"C{i+1}\n{c.depth_pct:.1%}", xy=(mid, (c.high_swing.price + c.low_swing.price) / 2),
            fontsize=8, ha="center", va="center", color="#2c3e50", fontweight="bold",
        )

    sh_dates = [c.high_swing.date for c in contractions]
    sh_prices = [c.high_swing.price for c in contractions]
    sl_dates = [c.low_swing.date for c in contractions]
    sl_prices = [c.low_swing.price for c in contractions]
    ax_price.scatter(sh_dates, sh_prices, marker="v", s=60, color="#e74c3c", zorder=4)
    ax_price.scatter(sl_dates, sl_prices, marker="^", s=60, color="#27ae60", zorder=4)

    pivot_price = pattern["pivot_price"]
    ax_price.axhline(pivot_price, color="#e67e22", linestyle="--", linewidth=1.5, alpha=0.7,
                     label=f"Pivot {pivot_price:.4f}")

    stop_dates, stop_prices = zip(*trade["stop_history"])
    ax_price.step(stop_dates, stop_prices, where="post", color="#e74c3c",
                  linewidth=2.0, alpha=0.8, label="Stop loss")

    ax_price.scatter([entry_date], [entry_price], marker="*", s=250, color="#f39c12",
                     edgecolors="#e67e22", linewidth=1.5, zorder=5,
                     label=f"BUY {entry_price:.4f}")

    exit_colors = {
        "stop_loss": "#e74c3c", "trailing_stop": "#e67e22", "time_exit": "#95a5a6",
        "target": "#27ae60", "open": "#3498db", "early_exit": "#e74c3c",
    }
    exit_markers = {
        "stop_loss": "X", "trailing_stop": "X", "time_exit": "s",
        "target": "*", "open": "o", "early_exit": "X",
    }
    reason = trade["exit_reason"]
    ax_price.scatter(
        [exit_date], [trade["exit_price"]],
        marker=exit_markers.get(reason, "o"), s=200,
        color=exit_colors.get(reason, "#7f8c8d"), edgecolors="black", linewidth=1, zorder=5,
        label=f"EXIT: {reason} {trade['exit_price']:.4f}",
    )

    if initial_risk > 0:
        be_r = risk_params.get("breakeven_r_multiple", 1.0)
        for r_level in range(1, 8):
            r_price = entry_price + r_level * be_r * initial_risk
            if r_price < window["close"].max() * 1.15:
                ax_price.axhline(r_price, color="#27ae60", linestyle=":", linewidth=0.5, alpha=0.3)
                ax_price.text(window.index[-1], r_price, f" {r_level * be_r:.0f}R",
                              fontsize=7, color="#27ae60", va="center")

    pnl_str = f"{trade['pnl_pct']:+.2%}"
    r_str = f"{trade['r_multiple']:+.1f}R"
    ax_price.set_title(
        f"Trade #{pattern_number} — {ticker} — {reason.upper()} — "
        f"P&L: {pnl_str} ({r_str}) — {trade['duration_days']}d — Max: {trade['max_r']:.1f}R",
        fontsize=11, fontweight="bold", pad=10,
    )
    ax_price.set_ylabel("Precio")
    ax_price.legend(loc="upper left", fontsize=7, framealpha=0.9)

    sma_period = risk_params.get("trailing_sma_period", 20)
    vol_ma = ohlc["volume"].rolling(sma_period, min_periods=1).mean()
    vol_colors = ["#27ae60" if window["close"].iloc[i] >= window["open"].iloc[i]
                  else "#e74c3c" for i in range(len(window))]
    ax_vol.bar(window.index, window["volume"], width=0.8, color=vol_colors, alpha=0.5)
    ax_vol.plot(window.index, vol_ma.loc[window.index], color="#3498db", linewidth=1.2,
                label=f"Vol MA({sma_period})")
    ax_vol.set_ylabel("Volumen")
    ax_vol.legend(loc="upper left", fontsize=7)

    ax_vol.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    fig.autofmt_xdate(rotation=30)
    plt.tight_layout()

    if save_path:
        fig.savefig(save_path, dpi=110, bbox_inches="tight")
        plt.close(fig)
    return fig


# ── Per-currency analysis ────────────────────────────────────


def run_single_currency(ticker, daily, train, test):
    """Run full temporal stability analysis for one currency with sequential grouping."""

    print(f"\n{'#'*70}")
    print(f"  {ticker} (sequential mode)")
    print(f"  {len(daily):,} barras ({daily.index.min().date()} a {daily.index.max().date()})")
    print(f"  TRAIN: {len(train):,} barras | TEST: {len(test):,} barras")
    print(f"{'#'*70}")

    # ══════════════════════════════════════════════════════════
    #  FASE 1: GRILLA DE DETECCION — TRAIN
    # ══════════════════════════════════════════════════════════

    print(f"\n{'='*70}")
    print(f"  FASE 1: GRILLA DE DETECCION — {ticker} TRAIN")
    print(f"  atr_mult x depth_atr x reduction x lookback_bars")
    print(f"{'='*70}")

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
                for lookback in LOOKBACK_BARS:
                    seq = make_seq_params(depth_atr, reduction, lookback)
                    signals = detect_signals(train, seq, cache)
                    ev = evaluate_signals(train, signals, fixed_risk)
                    all_det_results.append({
                        "atr_mult": atr_mult, "depth_atr": depth_atr,
                        "reduction": reduction, "lookback_bars": lookback,
                        "n_swings": n_swings, "n_contractions": n_contr,
                        "signals": len(signals),
                        **{k: ev[k] for k in ["trades", "wins", "WR", "CR", "avg_R"]},
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
    print(f"\nTop 20 configs (atr_mult x depth_atr x reduction x lookback):")
    for _, row in det_df_sorted.head(20).iterrows():
        print(f"  atr_mult={row['atr_mult']:.2f}, depth={int(row['depth_atr'])}, "
              f"red={row['reduction']:.2f}, lb={int(row['lookback_bars'])} "
              f"-> {int(row['signals'])} sen, {int(row['trades'])}T, "
              f"WR={fmt_wr(row['WR'])}, CR={fmt_pct(row['CR'])}, avgR={row['avg_R']:+.2f}")

    print("\nMejor config por lookback_bars:")
    for lb in LOOKBACK_BARS:
        sub = det_df[det_df["lookback_bars"] == lb]
        best = sub.sort_values("CR", ascending=False).iloc[0]
        has_trades = sub[sub["trades"] > 0]
        print(f"  lookback={lb}: atr_mult={best['atr_mult']:.2f}, depth={int(best['depth_atr'])}, "
              f"red={best['reduction']:.2f} -> {int(best['trades'])}T, WR={fmt_wr(best['WR'])}, "
              f"CR={fmt_pct(best['CR'])} ({len(has_trades)}/{len(sub)} configs con trades)")

    best_overall = det_df_sorted.iloc[0]
    best_atr_mult = best_overall["atr_mult"]
    best_depth_atr = int(best_overall["depth_atr"])
    best_reduction = best_overall["reduction"]
    best_lookback = int(best_overall["lookback_bars"])
    print(f"\n>>> MEJOR CONFIG TRAIN: atr_mult={best_atr_mult}, "
          f"depth_atr={best_depth_atr}, reduction={best_reduction}, "
          f"lookback_bars={best_lookback}")

    # ══════════════════════════════════════════════════════════
    #  FASE 2: GRILLA DE SALIDA EN TRAIN
    # ══════════════════════════════════════════════════════════

    print(f"\n\n{'='*70}")
    print(f"  FASE 2: GRILLA DE SALIDA — {ticker} TRAIN")
    print(f"  atr_mult={best_atr_mult}, depth_atr={best_depth_atr}, "
          f"red={best_reduction}, lookback={best_lookback}")
    print(f"{'='*70}")

    best_seq = make_seq_params(best_depth_atr, best_reduction, best_lookback)
    best_cache = caches_train[best_atr_mult]
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

    best_exit_row = exit_df_sorted.iloc[0]
    best_exit = {
        "trailing_atr_multiplier": best_exit_row["trailing_atr_multiplier"],
        "target_r_multiple": best_exit_row["target_r_multiple"] if pd.notna(best_exit_row["target_r_multiple"]) else None,
        "early_exit_days": int(best_exit_row["early_exit_days"]) if pd.notna(best_exit_row["early_exit_days"]) else None,
        "breakeven_r_multiple": best_exit_row["breakeven_r_multiple"],
    }

    print(f"\n>>> MEJOR CONFIG TRAIN COMPLETA:")
    print(f"    Swing:     atr_mult={best_atr_mult}")
    print(f"    Deteccion: depth_atr={best_depth_atr}, reduction={best_reduction}, lookback={best_lookback}")
    print(f"    Salida:    trail={best_exit['trailing_atr_multiplier']}, "
          f"target={best_exit['target_r_multiple']}, "
          f"early={best_exit['early_exit_days']}, "
          f"be_R={best_exit['breakeven_r_multiple']}")

    # ══════════════════════════════════════════════════════════
    #  FASE 3: PERFORMANCE TRAIN / TEST / FULL + MLflow
    # ══════════════════════════════════════════════════════════

    print(f"\n\n{'='*70}")
    print(f"  FASE 3: EVALUACION + MLflow — {ticker}")
    print(f"{'='*70}")

    risk_best = {**RISK_BASE, **best_exit}
    splits = {"TRAIN": train, "TEST": test, "FULL": daily}

    all_params = {
        "ticker": ticker,
        "cutoff": CUTOFF,
        "grouping": "sequential",
        "atr_mult": float(best_atr_mult),
        **{f"seq_{k}": str(v) for k, v in best_seq.items()},
        **{f"risk_{k}": str(v) for k, v in risk_best.items()},
    }

    print(f"\n  {'Split':<20s} | {'Sen':>5s} | {'Trades':>6s} | {'WR':>5s} | {'CR':>8s} | {'AvgR':>6s} | Salidas")
    print(f"  {'─'*85}")

    ev_by_split = {}
    all_test_signals = None
    for split_name, ohlc in splits.items():
        cache = precompute(ohlc, best_atr_mult)
        signals = detect_signals(ohlc, best_seq, cache)
        if split_name == "TEST":
            all_test_signals = (signals, ohlc)
        ev = evaluate_signals(ohlc, signals, risk_best)
        ev_by_split[split_name] = (len(signals), ev)
        reasons_str = ", ".join(f"{k}={v}" for k, v in sorted(ev["reasons"].items()))
        print(f"  {split_name:<20s} | {len(signals):>5d} | {ev['trades']:>6d} | "
              f"{fmt_wr(ev['WR']):>5s} | {fmt_pct(ev['CR']):>8s} | {ev['avg_R']:>+6.2f} | {reasons_str}")

    metrics_by_split = {}
    for split_name in ["TRAIN", "TEST", "FULL"]:
        n_sig, ev = ev_by_split[split_name]
        ohlc = splits[split_name]
        bh = buy_and_hold_metrics(ohlc)
        strat = strategy_metrics(ohlc, ev["trade_details"])
        metrics_by_split[split_name] = {**bh, **strat}

    # Generate signal histogram before MLflow logging
    hist_tmp_path = None
    if all_test_signals is not None:
        test_sigs, test_ohlc = all_test_signals
        from vcp_detection.analysis import simulate_trade as _sim, group_signals_into_patterns as _grp
        win_pnls, loss_pnls = [], []
        for dt in sorted(test_sigs.keys()):
            pat = _grp({dt: test_sigs[dt]}, risk_params=risk_best, max_gap_days=0)
            if not pat:
                continue
            t = _sim(test_ohlc, pat[0], risk_best)
            pnl = t["pnl_pct"] * 100
            (win_pnls if pnl >= 0 else loss_pnls).append(pnl)
        n_eval = len(win_pnls) + len(loss_pnls)
        if n_eval > 0:
            avg_w = np.mean(win_pnls) if win_pnls else 0
            avg_l = np.mean(loss_pnls) if loss_pnls else 0
            ratio = abs(avg_w / avg_l) if avg_l != 0 else float("inf")
            fig_h, ax_h = plt.subplots(figsize=(10, 5.5))
            all_p = win_pnls + loss_pnls
            bins_h = np.arange(min(all_p) - 0.3, max(all_p) + 0.55, 0.25)
            ax_h.hist(win_pnls, bins=bins_h, color="#2ecc71", edgecolor="white",
                      linewidth=0.8, alpha=0.85, label=f"Wins ({len(win_pnls)})")
            ax_h.hist(loss_pnls, bins=bins_h, color="#e74c3c", edgecolor="white",
                      linewidth=0.8, alpha=0.85, label=f"Losses ({len(loss_pnls)})")
            ax_h.axvline(x=0, color="#7f8c8d", linestyle="--", linewidth=1, alpha=0.7)
            ax_h.axvline(x=avg_w, color="#27ae60", linestyle="--", linewidth=1.8,
                         label=f"Avg win: +{avg_w:.2f}%")
            ax_h.axvline(x=avg_l, color="#c0392b", linestyle="--", linewidth=1.8,
                         label=f"Avg loss: {avg_l:.2f}%")
            txt = f"n={n_eval}  |  WR={len(win_pnls)/n_eval*100:.0f}%  |  Ratio={ratio:.1f}x"
            ax_h.text(0.98, 0.95, txt, transform=ax_h.transAxes, fontsize=11,
                      va="top", ha="right",
                      bbox=dict(boxstyle="round,pad=0.4", facecolor="white",
                                edgecolor="#bdc3c7", alpha=0.9))
            ax_h.set_xlabel("PnL por senal (%)", fontsize=12)
            ax_h.set_ylabel("Frecuencia", fontsize=12)
            ax_h.set_title(f"{ticker} — Distribucion de PnL por senal (TEST)",
                           fontsize=14, fontweight="bold")
            ax_h.legend(fontsize=11, loc="upper left")
            ax_h.grid(axis="y", alpha=0.3)
            plt.tight_layout()
            hist_tmp_path = f"/tmp/{ticker.lower()}_signal_histogram.png"
            fig_h.savefig(hist_tmp_path, dpi=150)
            plt.close(fig_h)
            print(f"  Histogram: {n_eval} senales ({len(win_pnls)}W/{len(loss_pnls)}L), "
                  f"WR={len(win_pnls)/n_eval*100:.0f}%, ratio={ratio:.1f}x")

    for split_name in ["TRAIN", "TEST", "FULL"]:
        n_sig, ev = ev_by_split[split_name]
        ohlc = splits[split_name]
        extra = metrics_by_split[split_name]

        with mlflow.start_run(run_name=f"{ticker}_{split_name}_seq", nested=True):
            mlflow.log_params({**all_params, "split": split_name, "n_bars": len(ohlc)})
            mlflow.log_metrics({
                "n_signals": n_sig, "n_trades": ev["trades"],
                "n_wins": ev["wins"], "n_losses": ev["trades"] - ev["wins"],
                "winrate": ev["WR"], "cumulative_return": ev["CR"],
                "avg_r_multiple": ev["avg_R"],
                "strategy_sharpe": extra["strat_sharpe"],
                "strategy_max_drawdown": extra["strat_max_drawdown"],
                "buyhold_return": extra["bh_return"],
                "buyhold_sharpe": extra["bh_sharpe"],
                "buyhold_max_drawdown": extra["bh_max_drawdown"],
            })

            if ev["trade_details"]:
                with tempfile.TemporaryDirectory() as tmpdir:
                    for j, (pat, trade) in enumerate(ev["trade_details"], 1):
                        pp = Path(tmpdir) / f"trade_{j}.png"
                        plot_combined(ohlc, pat, trade, pattern_number=j,
                                      risk_params=risk_best, ticker=f"{ticker} ({split_name})",
                                      save_path=str(pp))
                        mlflow.log_artifact(str(pp), "plots")

                    tdf = build_trade_table(ev["trade_details"], ticker)
                    tcp = Path(tmpdir) / "trades.csv"
                    tdf.to_csv(tcp, index=False)
                    mlflow.log_artifact(str(tcp), "tables")

                    if split_name == "TEST" and hist_tmp_path is not None:
                        mlflow.log_artifact(hist_tmp_path)

    print(f"  MLflow: 3 runs logueados para {ticker}")

    # ══════════════════════════════════════════════════════════
    #  FASE 4: DETALLE DE TRADES EN TEST
    # ══════════════════════════════════════════════════════════

    print(f"\n\n{'='*70}")
    print(f"  FASE 4: DETALLE DE TRADES EN TEST — {ticker}")
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
                  f"Dur={trade.get('duration_days', '?')}d")

    # ══════════════════════════════════════════════════════════
    #  RESUMEN
    # ══════════════════════════════════════════════════════════

    _, ev_train_result = ev_by_split["TRAIN"]
    _, ev_test_result = ev_by_split["TEST"]
    _, ev_full_result = ev_by_split["FULL"]

    print(f"\n  RESUMEN {ticker}:")
    print(f"    TRAIN: {ev_train_result['trades']}T, WR={fmt_wr(ev_train_result['WR'])}, CR={fmt_pct(ev_train_result['CR'])}")
    print(f"    TEST:  {ev_test_result['trades']}T, WR={fmt_wr(ev_test_result['WR'])}, CR={fmt_pct(ev_test_result['CR'])}")
    print(f"    FULL:  {ev_full_result['trades']}T, WR={fmt_wr(ev_full_result['WR'])}, CR={fmt_pct(ev_full_result['CR'])}")

    test_metrics = metrics_by_split["TEST"]

    return {
        "ticker": ticker,
        "best_atr_mult": best_atr_mult,
        "best_detection": {"depth_atr": best_depth_atr, "reduction": best_reduction, "lookback_bars": best_lookback},
        "best_exit": best_exit,
        "train_cr": ev_train_result["CR"],
        "train_trades": ev_train_result["trades"],
        "train_wr": ev_train_result["WR"],
        "test_cr": ev_test_result["CR"],
        "test_trades": ev_test_result["trades"],
        "test_wins": ev_test_result["wins"],
        "test_losses": ev_test_result["trades"] - ev_test_result["wins"],
        "test_wr": ev_test_result["WR"],
        "test_signals": ev_by_split["TEST"][0],
        "test_strat_sharpe": test_metrics["strat_sharpe"],
        "test_strat_max_dd": test_metrics["strat_max_drawdown"],
        "test_bh_return": test_metrics["bh_return"],
        "test_bh_sharpe": test_metrics["bh_sharpe"],
        "test_bh_max_dd": test_metrics["bh_max_drawdown"],
        "full_cr": ev_full_result["CR"],
        "det_df": det_df,
    }


# ══════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    mlflow.set_tracking_uri(str(project_root / "mlruns"))
    mlflow.set_experiment("VCP_FX_TemporalStability")

    all_results = []

    with mlflow.start_run(run_name="sequential_multicurrency") as parent_run:
        for ticker in TICKERS:
            daily = load_ticker(ticker)
            train = daily[daily.index < CUTOFF]
            test = daily[daily.index >= CUTOFF]
            result = run_single_currency(ticker, daily, train, test)
            all_results.append(result)

        if len(all_results) > 1:
            mlflow.log_metrics({
                "n_currencies": len(all_results),
                "avg_train_cr": float(np.mean([r["train_cr"] for r in all_results])),
                "avg_test_cr": float(np.mean([r["test_cr"] for r in all_results])),
                "avg_full_cr": float(np.mean([r["full_cr"] for r in all_results])),
                "currencies_positive_test": sum(1 for r in all_results if r["test_cr"] > 0),
            })

            with tempfile.TemporaryDirectory() as tmpdir:
                params_rows = []
                for r in all_results:
                    d = r["best_detection"]
                    e = r["best_exit"]
                    params_rows.append({
                        "ticker": r["ticker"], "atr_mult": r["best_atr_mult"],
                        "depth_atr": d["depth_atr"], "reduction": d["reduction"],
                        "lookback_bars": d["lookback_bars"],
                        "trailing_atr_mult": e["trailing_atr_multiplier"],
                        "target_r": e["target_r_multiple"],
                        "early_exit_days": e["early_exit_days"],
                        "breakeven_r": e["breakeven_r_multiple"],
                        "train_trades": r["train_trades"],
                        "train_wr": r["train_wr"], "train_cr": r["train_cr"],
                    })
                params_df = pd.DataFrame(params_rows)
                pp = Path(tmpdir) / "best_params_per_currency.csv"
                params_df.to_csv(pp, index=False)
                mlflow.log_artifact(str(pp), "summary")

                comp_rows = []
                for r in all_results:
                    comp_rows.append({
                        "ticker": r["ticker"],
                        "test_signals": r["test_signals"],
                        "wins": r["test_wins"], "losses": r["test_losses"],
                        "win_rate": r["test_wr"],
                        "strategy_cr": r["test_cr"],
                        "buyhold_cr": r["test_bh_return"],
                        "strategy_sharpe": r["test_strat_sharpe"],
                        "buyhold_sharpe": r["test_bh_sharpe"],
                        "strategy_max_dd": r["test_strat_max_dd"],
                        "buyhold_max_dd": r["test_bh_max_dd"],
                    })
                comp_df = pd.DataFrame(comp_rows)
                cp = Path(tmpdir) / "strategy_vs_buyhold_test.csv"
                comp_df.to_csv(cp, index=False)
                mlflow.log_artifact(str(cp), "summary")

    # ── Cross-currency summary ──

    if len(all_results) > 1:
        print(f"\n\n{'#'*70}")
        print(f"  COMPARACION ENTRE MONEDAS — PARAMETROS OPTIMOS (SEQUENTIAL)")
        print(f"{'#'*70}")

        print(f"\n  {'Ticker':<8s} | {'atr_m':>5s} | {'depth':>5s} | {'red':>5s} | {'lb':>4s} | "
              f"{'trail':>5s} | {'target':>6s} | {'early':>5s} | {'be_R':>5s} | "
              f"{'Tr T':>4s} | {'Tr WR':>5s} | {'Tr CR':>8s}")
        print(f"  {'─'*95}")

        for r in all_results:
            d = r["best_detection"]
            e = r["best_exit"]
            print(f"  {r['ticker']:<8s} | {r['best_atr_mult']:>5.2f} | {d['depth_atr']:>5d} | {d['reduction']:>5.2f} | "
                  f"{d['lookback_bars']:>4d} | "
                  f"{e['trailing_atr_multiplier']:>5.1f} | {str(e['target_r_multiple']):>6s} | "
                  f"{str(e['early_exit_days']):>5s} | {e['breakeven_r_multiple']:>5.1f} | "
                  f"{r['train_trades']:>4d} | {fmt_wr(r['train_wr']):>5s} | {fmt_pct(r['train_cr']):>8s}")

        print(f"\n\n{'#'*70}")
        print(f"  METODO vs BUY & HOLD — TEST ({CUTOFF} en adelante)")
        print(f"{'#'*70}")

        print(f"\n  {'Ticker':<8s} | {'Sen':>4s} | {'Wins':>4s} | {'Loss':>4s} | {'WR':>5s} | "
              f"{'Strat CR':>8s} | {'BH CR':>8s} | "
              f"{'Strat Sh':>8s} | {'BH Sh':>8s} | "
              f"{'Strat DD':>8s} | {'BH DD':>8s}")
        print(f"  {'─'*105}")

        for r in all_results:
            print(f"  {r['ticker']:<8s} | {r['test_signals']:>4d} | {r['test_wins']:>4d} | {r['test_losses']:>4d} | "
                  f"{fmt_wr(r['test_wr']):>5s} | "
                  f"{fmt_pct(r['test_cr']):>8s} | {fmt_pct(r['test_bh_return']):>8s} | "
                  f"{r['test_strat_sharpe']:>8.2f} | {r['test_bh_sharpe']:>8.2f} | "
                  f"{r['test_strat_max_dd']:>8.2%} | {r['test_bh_max_dd']:>8.2%}")

    print("\n\nCompleto!")
