"""Early entry experiment for EURUSD: entry at exact pivot breakout.

Approach: run normal detection pipeline (identical patterns), then for each
sequential trade, look BACKWARD from the signal date to find the first date
after the last HIGH confirmed (and after the previous trade's exit) where
close > pivot. This gives entry at the exact breakout moment.

Compares normal vs early entry on TEST (2020-2026) and logs both to MLflow.

Usage:
    python experiments/fx/run_fx_early_entry_eurusd.py
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
from models.types import VCPSignal
from vcp_detection.heuristic import ATRZigZagDetector, run_full_vcp_pipeline
from vcp_detection.heuristic.contractions import compute_contractions
from vcp_detection.heuristic.atr_compression import compute_atr
from vcp_detection.analysis import (
    evaluate_signals_to_trades,
    group_signals_into_patterns,
    simulate_trade,
)

pd.set_option("display.float_format", "{:.4f}".format)

# ── Config (EURUSD best from TRAIN optimization) ────────────
TICKER = "EURUSD"
CUTOFF = "2020-01-01"
DATA_DIR = project_root / "data" / "monedas"

BEST_ATR_MULT = 2.5
BEST_SEQ = {
    "method": "tolerance",
    "min_contractions": 2,
    "max_contractions": 6,
    "lookback_bars": 63,
    "tolerance": 0.10,
    "max_depth_pct": 0.50,
    "max_depth_atr": 5,
    "min_total_reduction": 0.6,
    "max_gap_between_contractions_days": None,
    "require_ascending_lows": True,
    "ascending_lows_tolerance": 0.03,
}
COMPRESSION = {"method": "ratio", "atr_period": 14, "ratio_threshold": 0.85}
BREAKOUT = {
    "volume_method": "ratio",
    "volume_ratio_threshold": 1.5,
    "volume_lookback_days": 50,
    "require_volume_confirmation": False,
}
RISK = {
    "max_stop_loss_pct": 0.02,
    "trailing_sma_period": 20,
    "trailing_volume_factor": 1.5,
    "trailing_stop_method": "atr",
    "trailing_atr_period": 14,
    "trailing_atr_multiplier": 1.5,
    "target_r_multiple": 5.0,
    "early_exit_days": None,
    "breakeven_r_multiple": 2.0,
    "max_bars_without_progress": 15,
    "min_progress_r": 0.5,
}


# ── Helpers ──────────────────────────────────────────────────

def precompute(ohlc, atr_mult):
    config = ATRZigZagConfig(atr_length=14, atr_mult=atr_mult, use_close_only=False)
    detector = ATRZigZagDetector(config)
    swings = detector.detect(ohlc)
    contractions = compute_contractions(swings, ohlc)
    atr = compute_atr(ohlc, COMPRESSION["atr_period"])
    return {"ohlc": ohlc, "swings": swings, "contractions": contractions,
            "atr": atr, "detector": detector}


def detect_signals(ohlc, seq_params, cache):
    res = run_full_vcp_pipeline(
        ohlc=ohlc, swing_detector=cache["detector"],
        sequence_params=seq_params,
        compression_params=COMPRESSION,
        breakout_params=BREAKOUT,
        volume_contraction_params=None,
        precomputed_swings=cache["swings"],
        precomputed_contractions=cache["contractions"],
        precomputed_atr=cache["atr"],
    )
    return {dt: s for dt, s in res.items() if s is not None}


def find_early_entry_date(sig, ohlc, min_date=None):
    """Find the first date after the last HIGH was confirmed (and after min_date)
    where close > pivot. Returns (date, close) or None."""
    last_contraction = sig.pivot_info.sequence.contractions[-1]
    high_confirmed_at = last_contraction.high_swing.confirmed_at
    pivot = sig.pivot_price

    start = high_confirmed_at
    if min_date is not None and min_date > start:
        start = min_date

    mask = (ohlc.index >= start) & (ohlc.index <= sig.signal_date)
    window = ohlc.loc[mask]

    for d, row in window.iterrows():
        if row["close"] > pivot:
            return d, float(row["close"])
    return None


def evaluate_early_entry(signals, ohlc, risk):
    """Sequential evaluation with early entry: for each trade, try to
    backdate the entry to the first breakout after HIGH confirmation
    (and after previous trade's exit)."""
    sorted_dates = sorted(signals.keys())
    results = []
    i = 0
    while i < len(sorted_dates):
        sig_date = sorted_dates[i]
        sig = signals[sig_date]

        last_exit = results[-1][1]["exit_date"] if results else None
        # min_date for early entry: day after previous exit (can't enter during a trade)
        min_date = None
        if last_exit is not None:
            loc = ohlc.index.get_loc(last_exit)
            if loc + 1 < len(ohlc):
                min_date = ohlc.index[loc + 1]

        early = find_early_entry_date(sig, ohlc, min_date)

        if early is not None:
            early_date, early_close = early
            # Create modified signal with early entry
            stop_distance = (early_close - sig.suggested_stop) / early_close
            early_sig = VCPSignal(
                signal_date=early_date,
                entry_price=early_close,
                pivot_price=sig.pivot_price,
                suggested_stop=sig.suggested_stop,
                suggested_stop_distance_pct=stop_distance,
                pivot_info=sig.pivot_info,
                atr_compression=sig.atr_compression,
                volume_confirmation=sig.volume_confirmation,
                volume_contraction=sig.volume_contraction,
                metadata={
                    **sig.metadata,
                    "original_signal_date": sig_date,
                    "original_entry_price": sig.entry_price,
                    "days_earlier": (sig_date - early_date).days,
                },
            )
            pat = group_signals_into_patterns(
                {early_date: early_sig}, risk_params=risk, max_gap_days=0,
            )
        else:
            pat = group_signals_into_patterns(
                {sig_date: sig}, risk_params=risk, max_gap_days=0,
            )

        if not pat:
            i += 1
            continue

        trade = simulate_trade(ohlc, pat[0], risk)
        results.append((pat[0], trade))

        exit_date = trade["exit_date"]
        while i < len(sorted_dates) and sorted_dates[i] <= exit_date:
            i += 1

    return results


def format_eval_results(trade_details):
    n = len(trade_details)
    trades_list = [t for _, t in trade_details]
    wins = sum(1 for t in trades_list if t["pnl_pct"] > 0) if n else 0
    cr = float(np.prod([1 + t["pnl_pct"] for t in trades_list]) - 1) if n else 0
    avg_r = float(np.mean([t["r_multiple"] for t in trades_list])) if n else 0
    reasons = {}
    for t in trades_list:
        reasons[t["exit_reason"]] = reasons.get(t["exit_reason"], 0) + 1
    return {"trades": n, "wins": wins, "WR": wins / n if n > 0 else 0,
            "CR": cr, "avg_R": avg_r, "reasons": reasons,
            "trade_details": trade_details}


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


def build_trade_table(trade_details, ticker, mode):
    rows = []
    for i, (pat, trade) in enumerate(trade_details, 1):
        rows.append({
            "ticker": ticker, "mode": mode, "trade_num": i,
            "entry_date": pat["first_signal_date"].strftime("%Y-%m-%d"),
            "exit_date": trade["exit_date"].strftime("%Y-%m-%d"),
            "exit_reason": trade["exit_reason"],
            "duration_days": trade["duration_days"],
            "entry_price": pat["entry_price"],
            "exit_price": trade["exit_price"],
            "pivot_price": pat["pivot_price"],
            "pnl_pct": trade["pnl_pct"],
            "r_multiple": trade["r_multiple"],
            "max_r": trade["max_r"],
            "n_contractions": pat["n_contractions"],
        })
    return pd.DataFrame(rows)


def generate_histogram(trade_details, ticker, mode):
    if not trade_details:
        return None
    win_pnls = [t["pnl_pct"] * 100 for _, t in trade_details if t["pnl_pct"] >= 0]
    loss_pnls = [t["pnl_pct"] * 100 for _, t in trade_details if t["pnl_pct"] < 0]

    n_eval = len(win_pnls) + len(loss_pnls)
    if n_eval == 0:
        return None

    avg_w = np.mean(win_pnls) if win_pnls else 0
    avg_l = np.mean(loss_pnls) if loss_pnls else 0
    ratio = abs(avg_w / avg_l) if avg_l != 0 else float("inf")

    fig, ax = plt.subplots(figsize=(10, 5.5))
    all_p = win_pnls + loss_pnls
    bins = np.arange(min(all_p) - 0.3, max(all_p) + 0.55, 0.25)
    ax.hist(win_pnls, bins=bins, color="#2ecc71", edgecolor="white",
            linewidth=0.8, alpha=0.85, label=f"Wins ({len(win_pnls)})")
    if loss_pnls:
        ax.hist(loss_pnls, bins=bins, color="#e74c3c", edgecolor="white",
                linewidth=0.8, alpha=0.85, label=f"Losses ({len(loss_pnls)})")
    ax.axvline(x=0, color="#7f8c8d", linestyle="--", linewidth=1, alpha=0.7)
    if win_pnls:
        ax.axvline(x=avg_w, color="#27ae60", linestyle="--", linewidth=1.8,
                   label=f"Avg win: +{avg_w:.2f}%")
    if loss_pnls:
        ax.axvline(x=avg_l, color="#c0392b", linestyle="--", linewidth=1.8,
                   label=f"Avg loss: {avg_l:.2f}%")

    ratio_str = f"{ratio:.1f}x" if ratio != float("inf") else "inf"
    txt = f"n={n_eval}  |  WR={len(win_pnls)/n_eval*100:.0f}%  |  Ratio={ratio_str}"
    ax.text(0.98, 0.95, txt, transform=ax.transAxes, fontsize=11,
            va="top", ha="right",
            bbox=dict(boxstyle="round,pad=0.4", facecolor="white",
                      edgecolor="#bdc3c7", alpha=0.9))
    ax.set_xlabel("PnL por trade (%)", fontsize=12)
    ax.set_ylabel("Frecuencia", fontsize=12)
    ax.set_title(f"{ticker} — PnL por trade ({mode}) TEST 2020-2026",
                 fontsize=14, fontweight="bold")
    ax.legend(fontsize=11, loc="upper left")
    ax.grid(axis="y", alpha=0.3)
    plt.tight_layout()

    path = f"/tmp/{ticker.lower()}_{mode}_histogram.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print(f"  Histogram ({mode}): {n_eval} trades "
          f"({len(win_pnls)}W/{len(loss_pnls)}L), "
          f"WR={len(win_pnls)/n_eval*100:.0f}%, ratio={ratio_str}")
    return path


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


# ── Main ─────────────────────────────────────────────────────

if __name__ == "__main__":
    mlflow.set_tracking_uri(str(project_root / "mlruns"))
    mlflow.set_experiment("VCP_FX_EarlyEntry")

    daily = pd.read_csv(DATA_DIR / f"{TICKER}.csv", parse_dates=["date"], index_col="date")
    train = daily[daily.index < CUTOFF]
    test = daily[daily.index >= CUTOFF]

    print(f"{'#'*70}")
    print(f"  EURUSD Early Entry Experiment")
    print(f"  Data: {len(daily):,} bars ({daily.index.min().date()} to {daily.index.max().date()})")
    print(f"  TRAIN: {len(train):,} | TEST: {len(test):,}")
    print(f"  Params: atr_mult={BEST_ATR_MULT}, depth_atr={BEST_SEQ['max_depth_atr']}, "
          f"reduction={BEST_SEQ['min_total_reduction']}, lookback={BEST_SEQ['lookback_bars']}")
    print(f"{'#'*70}\n")

    cache = precompute(test, BEST_ATR_MULT)

    all_params = {
        "ticker": TICKER, "cutoff": CUTOFF, "grouping": "sequential",
        "atr_mult": BEST_ATR_MULT,
        **{f"seq_{k}": str(v) for k, v in BEST_SEQ.items()},
        **{f"risk_{k}": str(v) for k, v in RISK.items()},
    }

    bh = buy_and_hold_metrics(test)

    # ── Detect signals (same for both modes) ──
    normal_signals = detect_signals(test, BEST_SEQ, cache)
    print(f"  Signals detected: {len(normal_signals)}")

    # ── Normal evaluation ──
    normal_eval = evaluate_signals_to_trades(normal_signals, test, RISK, grouping="sequential")
    normal_ev = format_eval_results(normal_eval)

    # ── Early entry evaluation ──
    early_eval = evaluate_early_entry(normal_signals, test, RISK)
    early_ev = format_eval_results(early_eval)

    # ── Show backdate details ──
    print(f"\n  Detalle de entradas adelantadas:")
    for pat, trade in early_eval:
        sig = pat["signal_obj"]
        days_earlier = sig.metadata.get("days_earlier", 0)
        if days_earlier > 0:
            orig_date = sig.metadata["original_signal_date"]
            orig_price = sig.metadata["original_entry_price"]
            print(f"    {orig_date.strftime('%Y-%m-%d')} -> "
                  f"{pat['first_signal_date'].strftime('%Y-%m-%d')} "
                  f"({days_earlier}d antes) | "
                  f"Entry: {orig_price:.4f} -> {pat['entry_price']:.4f} "
                  f"(pivot={pat['pivot_price']:.4f}, "
                  f"dist: {(orig_price-pat['pivot_price'])/pat['pivot_price']*100:.2f}% -> "
                  f"{(pat['entry_price']-pat['pivot_price'])/pat['pivot_price']*100:.2f}%)")
        else:
            print(f"    {pat['first_signal_date'].strftime('%Y-%m-%d')} (sin cambio)")

    modes_results = {
        "normal": normal_ev,
        "early_entry": early_ev,
    }

    with mlflow.start_run(run_name="EURUSD_early_entry_v3") as parent:
        for mode_name, ev in modes_results.items():
            print(f"\n{'='*70}")
            print(f"  Mode: {mode_name.upper()}")
            print(f"{'='*70}")

            strat = strategy_metrics(test, ev["trade_details"])

            print(f"  Trades: {ev['trades']} (W={ev['wins']}, L={ev['trades']-ev['wins']})")
            print(f"  WR: {ev['WR']:.0%} | CR: {ev['CR']:+.2%} | Avg R: {ev['avg_R']:+.2f}")
            print(f"  Sharpe: {strat['strat_sharpe']:.2f} | Max DD: {strat['strat_max_drawdown']:.2%}")
            reasons_str = ", ".join(f"{k}={v}" for k, v in sorted(ev["reasons"].items()))
            print(f"  Exits: {reasons_str}")

            if ev["trade_details"]:
                print(f"\n  {'#':>3s}  {'Entry':>10s}  {'Exit':>10s}  {'Reason':<15s}  "
                      f"{'PnL':>8s}  {'R':>6s}  {'Days':>5s}  {'Pivot':>8s}  {'Entry$':>8s}  {'Dist':>6s}")
                print(f"  {'─'*100}")
                for i, (pat, trade) in enumerate(ev["trade_details"], 1):
                    entry_dist = (pat["entry_price"] - pat["pivot_price"]) / pat["pivot_price"] * 100
                    print(f"  {i:>3d}  {pat['first_signal_date'].strftime('%Y-%m-%d'):>10s}  "
                          f"{trade['exit_date'].strftime('%Y-%m-%d'):>10s}  "
                          f"{trade['exit_reason']:<15s}  "
                          f"{trade['pnl_pct']:>+7.2%}  {trade['r_multiple']:>+5.1f}R  "
                          f"{trade['duration_days']:>5d}  "
                          f"{pat['pivot_price']:>8.4f}  {pat['entry_price']:>8.4f}  "
                          f"{entry_dist:>5.1f}%")

            hist_path = generate_histogram(ev["trade_details"], TICKER, mode_name)

            with mlflow.start_run(run_name=f"EURUSD_TEST_{mode_name}", nested=True):
                mlflow.log_params({**all_params, "split": "TEST", "mode": mode_name,
                                   "n_bars": len(test)})
                mlflow.log_metrics({
                    "n_signals": len(normal_signals), "n_trades": ev["trades"],
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
                        for j, (pat, trade) in enumerate(ev["trade_details"], 1):
                            pp = Path(tmpdir) / f"trade_{j}.png"
                            plot_combined(test, pat, trade, pattern_number=j,
                                          risk_params=RISK,
                                          ticker=f"EURUSD ({mode_name})",
                                          save_path=str(pp))
                            mlflow.log_artifact(str(pp), "plots")

                        tdf = build_trade_table(ev["trade_details"], TICKER, mode_name)
                        tcp = Path(tmpdir) / "trades.csv"
                        tdf.to_csv(tcp, index=False)
                        mlflow.log_artifact(str(tcp), "tables")

                if hist_path:
                    mlflow.log_artifact(hist_path)

            modes_results[mode_name] = {**ev, "strat": strat}

        # Summary comparison
        print(f"\n\n{'#'*70}")
        print(f"  COMPARACION: NORMAL vs EARLY ENTRY — EURUSD TEST")
        print(f"{'#'*70}")

        def fval(v, fmt):
            return f"{v:{fmt}}"

        print(f"\n  {'Metric':<25s} | {'Normal':>12s} | {'Early Entry':>12s}")
        print(f"  {'─'*55}")

        rn = modes_results["normal"]
        re = modes_results["early_entry"]
        for label, vn, ve, fmt in [
            ("Trades", rn["trades"], re["trades"], "d"),
            ("Wins", rn["wins"], re["wins"], "d"),
            ("Losses", rn["trades"]-rn["wins"], re["trades"]-re["wins"], "d"),
            ("Win Rate", rn["WR"], re["WR"], ".0%"),
            ("Cum. Return", rn["CR"], re["CR"], "+.2%"),
            ("Avg R", rn["avg_R"], re["avg_R"], "+.2f"),
            ("Sharpe", rn["strat"]["strat_sharpe"], re["strat"]["strat_sharpe"], ".2f"),
            ("Max DD", rn["strat"]["strat_max_drawdown"], re["strat"]["strat_max_drawdown"], ".2%"),
        ]:
            print(f"  {label:<25s} | {fval(vn, fmt):>12s} | {fval(ve, fmt):>12s}")

        print(f"\n  B&H Return: {bh['bh_return']:+.2%}")
        print(f"  B&H Sharpe: {bh['bh_sharpe']:.2f}")

    print("\n\nCompleto! Resultados en MLflow experiment 'VCP_FX_EarlyEntry'")
