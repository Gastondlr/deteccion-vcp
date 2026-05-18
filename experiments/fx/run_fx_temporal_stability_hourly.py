"""Temporal stability experiment on HOURLY FX data — true hourly scale.

Detects micro-VCP patterns that form over days and trade out in hours.
Parameters are set at hourly scale (not scaled-to-daily).

Key parameters:
  - atr_length: 14 (14 hours of volatility)
  - lookback_bars: variable [72, 120, 168, 240] (3-10 days)
  - max_bars_without_progress: 48 (2 days)
  - max_hold_bars: 360 (15 days)
  - early_exit (bars): None, 6, 12 (6-12 hours)
  - max_stop_loss_pct: 0.01 (1%)
  - depth_atr grid: 1-4 (smaller patterns)
  - target_r grid: None, 1.5, 2, 3

Usage:
    python run_fx_temporal_stability_hourly.py                # all currencies
    python run_fx_temporal_stability_hourly.py EURUSD GBPUSD  # specific currencies
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
from vcp_detection.analysis import group_signals_into_patterns, simulate_trade

pd.set_option("display.float_format", "{:.4f}".format)
P = lambda *a, **kw: print(*a, **kw, flush=True)

# ── Constants ─────────────────────────────────────────────────

ALL_TICKERS = ["EURUSD", "GBPUSD", "USDJPY", "USDCNH", "USDCNY"]
CUTOFF = "2020-01-01"

BARS_PER_DAY = 24
ANNUALIZATION_FACTOR = np.sqrt(252 * BARS_PER_DAY)

ATR_LENGTH = 14

# Detection grids
ATR_MULTS = [0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 2.5]
DEPTH_ATRS = [1, 2, 3, 4]
REDUCTIONS = [0.40, 0.50, 0.60, 0.70, 0.80]
LOOKBACK_BARS_GRID = [72, 120, 168, 240]

# Exit grids
TRAILING_MULTS = [1.0, 1.5, 2.0, 2.5, 3.0]
TARGET_RS = [None, 1.5, 2.0, 3.0]
EARLY_EXITS = [None, 6, 12]
BREAKEVEN_RS = [0.5, 1.0, 1.5, 2.0]

COMPRESSION = {"method": "ratio", "atr_period": ATR_LENGTH, "ratio_threshold": 0.85}
BREAKOUT = {
    "volume_method": "ratio", "volume_ratio_threshold": 1.5,
    "volume_lookback_days": 50,
    "require_volume_confirmation": False,
}
RISK_BASE = {
    "max_stop_loss_pct": 0.01,
    "trailing_sma_period": 20,
    "trailing_volume_factor": 1.5,
    "trailing_stop_method": "atr",
    "trailing_atr_period": ATR_LENGTH,
    "max_bars_without_progress": 48,
    "min_progress_r": 0.5,
}

MAX_HOLD_BARS = 360

# ── Currency selection ───────────────────────────────────────

DATA_DIR = project_root / "data" / "monedas_hora"

cli_tickers = [t.upper() for t in sys.argv[1:] if not t.startswith("-")]
TICKERS = cli_tickers if cli_tickers else ALL_TICKERS

for ticker in TICKERS:
    fpath = DATA_DIR / f"{ticker}.csv"
    if not fpath.exists():
        P(f"ERROR: {fpath} no encontrado")
        sys.exit(1)

n_det = len(ATR_MULTS) * len(DEPTH_ATRS) * len(REDUCTIONS) * len(LOOKBACK_BARS_GRID)
n_exit = len(TRAILING_MULTS) * len(TARGET_RS) * len(EARLY_EXITS) * len(BREAKEVEN_RS)

P(f"Monedas: {TICKERS}")
P(f"Por moneda: {n_det} configs deteccion + {n_exit} configs salida")
P(f"Cutoff: {CUTOFF} (TRAIN antes, TEST despues)")
P(f"Data: HOURLY | ATR_LENGTH={ATR_LENGTH} | LOOKBACK_GRID={LOOKBACK_BARS_GRID}")
P(f"Scale: hourly (patterns form over days, trade in hours)\n")

# ── Helper functions ──────────────────────────────────────────


def load_ticker(ticker):
    return pd.read_csv(DATA_DIR / f"{ticker}.csv", parse_dates=["date"], index_col="date")


def precompute(ohlc, atr_mult):
    config = ATRZigZagConfig(atr_length=ATR_LENGTH, atr_mult=atr_mult, use_close_only=False)
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
    patterns = group_signals_into_patterns(signals, risk_params=risk)
    trades = [simulate_trade(ohlc, p, risk, max_hold_days=MAX_HOLD_BARS) for p in patterns]
    n = len(trades)
    wins = sum(1 for t in trades if t["pnl_pct"] > 0) if n else 0
    cr = float(np.prod([1 + t["pnl_pct"] for t in trades]) - 1) if n else 0
    avg_r = float(np.mean([t["r_multiple"] for t in trades])) if n else 0
    reasons = {}
    for t in trades:
        reasons[t["exit_reason"]] = reasons.get(t["exit_reason"], 0) + 1
    return {"trades": n, "wins": wins, "WR": wins / n if n > 0 else 0,
            "CR": cr, "avg_R": avg_r, "reasons": reasons,
            "trade_details": [(p, t) for p, t in zip(patterns, trades)]}


def buy_and_hold_metrics(ohlc):
    c = ohlc["close"]
    total_return = float(c.iloc[-1] / c.iloc[0] - 1)
    dd = (c - c.cummax()) / c.cummax()
    max_dd = float(dd.min())
    hourly_ret = c.pct_change().dropna()
    sharpe = float(hourly_ret.mean() / hourly_ret.std() * ANNUALIZATION_FACTOR) if hourly_ret.std() > 0 else 0
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
    sharpe = float(all_rets.mean() / all_rets.std() * ANNUALIZATION_FACTOR) if len(all_rets) > 1 and all_rets.std() > 0 else 0.0
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


def plot_combined(ohlc, pattern, trade, pattern_number, risk_params, ticker, save_path=None):
    sig = pattern["signal_obj"]
    seq = sig.pivot_info.sequence
    contractions = seq.contractions

    pattern_start = contractions[0].high_swing.date
    entry_date = pattern["first_signal_date"]
    exit_date = trade["exit_date"]
    entry_price = pattern["entry_price"]
    initial_risk = pattern["initial_risk"]

    start_loc = max(0, ohlc.index.get_loc(pattern_start) - 5 * BARS_PER_DAY)
    exit_loc = ohlc.index.get_loc(exit_date)
    end_loc = min(len(ohlc) - 1, exit_loc + 2 * BARS_PER_DAY)
    window = ohlc.iloc[start_loc:end_loc + 1]

    fig, (ax_price, ax_vol) = plt.subplots(
        2, 1, figsize=(18, 9), height_ratios=[3, 1], sharex=True,
        gridspec_kw={"hspace": 0.08},
    )

    ax_price.plot(window.index, window["close"], color="#2c3e50", linewidth=0.6, label="Close", zorder=2)

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
        f"Trade #{pattern_number} — {ticker} (HOURLY) — {reason.upper()} — "
        f"P&L: {pnl_str} ({r_str}) — {trade['duration_days']}d — Max: {trade['max_r']:.1f}R",
        fontsize=11, fontweight="bold", pad=10,
    )
    ax_price.set_ylabel("Precio")
    ax_price.legend(loc="upper left", fontsize=7, framealpha=0.9)

    sma_period = risk_params.get("trailing_sma_period", 20)
    vol_ma = ohlc["volume"].rolling(sma_period, min_periods=1).mean()
    vol_colors = ["#27ae60" if window["close"].iloc[i] >= window["open"].iloc[i]
                  else "#e74c3c" for i in range(len(window))]
    ax_vol.bar(window.index, window["volume"], width=0.03, color=vol_colors, alpha=0.5)
    ax_vol.plot(window.index, vol_ma.loc[window.index], color="#3498db", linewidth=1.2,
                label=f"Vol MA({sma_period})")
    ax_vol.set_ylabel("Volumen")
    ax_vol.legend(loc="upper left", fontsize=7)

    ax_vol.xaxis.set_major_formatter(mdates.DateFormatter("%b %d %H:%M"))
    fig.autofmt_xdate(rotation=30)
    plt.tight_layout()

    if save_path:
        fig.savefig(save_path, dpi=110, bbox_inches="tight")
        plt.close(fig)
    return fig


# ── Per-currency analysis (TRAIN only) ───────────────────────


def run_single_currency_train(ticker, train):
    """Run Phases 1-2 on TRAIN only. Returns best config and detection DataFrame."""

    P(f"\n{'#'*70}")
    P(f"  {ticker} (HOURLY — true hourly scale)")
    P(f"  TRAIN: {len(train):,} barras ({train.index.min()} a {train.index.max()})")
    P(f"{'#'*70}")

    # ══════════════════════════════════════════════════════════
    #  FASE 1: GRILLA DE DETECCION — TRAIN
    # ══════════════════════════════════════════════════════════

    P(f"\n{'='*70}")
    P(f"  FASE 1: GRILLA DE DETECCION — {ticker} TRAIN (hourly)")
    P(f"  atr_mult x depth_atr x reduction x lookback_bars")
    P(f"  {n_det} combinaciones")
    P(f"{'='*70}")

    fixed_risk = {**RISK_BASE, "trailing_atr_multiplier": 1.5, "target_r_multiple": 2.0,
                  "early_exit_days": None, "breakeven_r_multiple": 1.0}

    all_det_results = []
    caches_train = {}
    t_total = time.time()

    n_configs_per_mult = len(DEPTH_ATRS) * len(REDUCTIONS) * len(LOOKBACK_BARS_GRID)
    for atr_mult in ATR_MULTS:
        t0 = time.time()
        cache = precompute(train, atr_mult)
        caches_train[atr_mult] = cache
        n_swings = len(cache["swings"])
        n_contr = len(cache["contractions"])
        P(f"  atr_mult={atr_mult:.2f}: {n_swings} swings, {n_contr} contr — {n_configs_per_mult} configs...")

        cfg_i = 0
        for depth_atr in DEPTH_ATRS:
            for reduction in REDUCTIONS:
                for lookback in LOOKBACK_BARS_GRID:
                    cfg_i += 1
                    seq = make_seq_params(depth_atr, reduction, lookback)
                    t_cfg = time.time()
                    signals = detect_signals(train, seq, cache)
                    ev = evaluate_signals(train, signals, fixed_risk)
                    all_det_results.append({
                        "atr_mult": atr_mult, "depth_atr": depth_atr,
                        "reduction": reduction, "lookback_bars": lookback,
                        "n_swings": n_swings, "n_contractions": n_contr,
                        "signals": len(signals),
                        **{k: ev[k] for k in ["trades", "wins", "WR", "CR", "avg_R"]},
                    })
                    if cfg_i % 10 == 0 or cfg_i == n_configs_per_mult:
                        P(f"    [{cfg_i}/{n_configs_per_mult}] last: d={depth_atr} r={reduction:.2f} "
                          f"lb={lookback} -> {len(signals)} sig, {ev['trades']}T, "
                          f"CR={fmt_pct(ev['CR'])} ({time.time()-t_cfg:.1f}s)")

        elapsed = time.time() - t0
        best_in_mult = max((r for r in all_det_results if r["atr_mult"] == atr_mult),
                           key=lambda r: r["CR"], default=None)
        best_cr = fmt_pct(best_in_mult["CR"]) if best_in_mult else "N/A"
        P(f"  >> atr_mult={atr_mult:.2f} DONE: best_CR={best_cr} ({elapsed:.1f}s)")

    det_df = pd.DataFrame(all_det_results)
    det_df_sorted = det_df.sort_values("CR", ascending=False)

    P(f"\nTotal: {len(det_df)} configs en {time.time()-t_total:.1f}s")
    P(f"\nTop 20 configs:")
    for _, row in det_df_sorted.head(20).iterrows():
        P(f"  atr_mult={row['atr_mult']:.2f}, d={int(row['depth_atr'])}, "
          f"r={row['reduction']:.2f}, lb={int(row['lookback_bars'])} "
          f"-> {int(row['signals'])} sig, {int(row['trades'])}T, "
          f"WR={fmt_wr(row['WR'])}, CR={fmt_pct(row['CR'])}, avgR={row['avg_R']:+.2f}")

    P("\nMejor config por atr_mult:")
    for atr_mult in ATR_MULTS:
        sub = det_df[det_df["atr_mult"] == atr_mult]
        best = sub.sort_values("CR", ascending=False).iloc[0]
        has_trades = sub[sub["trades"] > 0]
        P(f"  atr_mult={atr_mult:.2f}: d={int(best['depth_atr'])}, r={best['reduction']:.2f}, "
          f"lb={int(best['lookback_bars'])} -> {int(best['trades'])}T, "
          f"WR={fmt_wr(best['WR'])}, CR={fmt_pct(best['CR'])} "
          f"({len(has_trades)}/{len(sub)} configs con trades)")

    P("\nMejor config por lookback_bars:")
    for lb in LOOKBACK_BARS_GRID:
        sub = det_df[det_df["lookback_bars"] == lb]
        best = sub.sort_values("CR", ascending=False).iloc[0]
        has_trades = sub[sub["trades"] > 0]
        P(f"  lb={lb}: atr_mult={best['atr_mult']:.2f}, d={int(best['depth_atr'])}, "
          f"r={best['reduction']:.2f} -> {int(best['trades'])}T, "
          f"WR={fmt_wr(best['WR'])}, CR={fmt_pct(best['CR'])} "
          f"({len(has_trades)}/{len(sub)} configs con trades)")

    best_overall = det_df_sorted.iloc[0]
    best_atr_mult = best_overall["atr_mult"]
    best_depth_atr = int(best_overall["depth_atr"])
    best_reduction = best_overall["reduction"]
    best_lookback = int(best_overall["lookback_bars"])
    P(f"\n>>> MEJOR CONFIG DETECCION: atr_mult={best_atr_mult}, "
      f"depth_atr={best_depth_atr}, reduction={best_reduction}, "
      f"lookback_bars={best_lookback}")

    # ══════════════════════════════════════════════════════════
    #  FASE 2: GRILLA DE SALIDA EN TRAIN
    # ══════════════════════════════════════════════════════════

    P(f"\n\n{'='*70}")
    P(f"  FASE 2: GRILLA DE SALIDA — {ticker} TRAIN (hourly)")
    P(f"  atr_mult={best_atr_mult}, d={best_depth_atr}, "
      f"r={best_reduction}, lb={best_lookback}")
    P(f"{'='*70}")

    best_seq = make_seq_params(best_depth_atr, best_reduction, best_lookback)
    best_cache = caches_train[best_atr_mult]
    signals_train = detect_signals(train, best_seq, best_cache)
    P(f"  Senales detectadas: {len(signals_train)}")

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
    P(f"  {len(exit_df)} configs en {time.time()-t0:.1f}s")

    P("\nTop 15 configs por CR:")
    for _, row in exit_df_sorted.head(15).iterrows():
        t_r = row['target_r_multiple'] if pd.notna(row['target_r_multiple']) else 'None'
        e_e = int(row['early_exit_days']) if pd.notna(row['early_exit_days']) else 'None'
        P(f"  trail={row['trailing_atr_multiplier']}, target={t_r}, early={e_e}, be_R={row['breakeven_r_multiple']}"
          f" -> {int(row['trades'])}T, WR={fmt_wr(row['WR'])}, CR={fmt_pct(row['CR'])}, "
          f"exits: {int(row['early_exits'])}e/{int(row['trail_stops'])}t/{int(row['stops'])}s/"
          f"{int(row['targets'])}tgt/{int(row['time_exits'])}time")

    P("\n  Impacto early_exit:")
    for early_val in [None, 6, 12]:
        if early_val is None:
            sub = exit_df[exit_df["early_exit_days"].isna()]
            label = "early=None"
        else:
            sub = exit_df[exit_df["early_exit_days"] == early_val]
            label = f"early={early_val}"
        if len(sub) > 0:
            P(f"    {label:<14} avg_WR={sub['WR'].mean():.0%}, "
              f"avg_CR={sub['CR'].mean():+.2%}, best_CR={sub['CR'].max():+.2%}")

    best_exit_row = exit_df_sorted.iloc[0]
    best_exit = {
        "trailing_atr_multiplier": best_exit_row["trailing_atr_multiplier"],
        "target_r_multiple": best_exit_row["target_r_multiple"] if pd.notna(best_exit_row["target_r_multiple"]) else None,
        "early_exit_days": int(best_exit_row["early_exit_days"]) if pd.notna(best_exit_row["early_exit_days"]) else None,
        "breakeven_r_multiple": best_exit_row["breakeven_r_multiple"],
    }

    P(f"\n>>> MEJOR CONFIG TRAIN COMPLETA:")
    P(f"    Swing:     atr_mult={best_atr_mult}")
    P(f"    Deteccion: depth_atr={best_depth_atr}, reduction={best_reduction}, lookback={best_lookback}")
    P(f"    Salida:    trail={best_exit['trailing_atr_multiplier']}, "
      f"target={best_exit['target_r_multiple']}, "
      f"early={best_exit['early_exit_days']}, "
      f"be_R={best_exit['breakeven_r_multiple']}")

    # ── Summary of TRAIN performance ──
    risk_best = {**RISK_BASE, **best_exit}
    ev_train = evaluate_signals(train, signals_train, risk_best)

    P(f"\n  TRAIN performance con mejor config:")
    P(f"    Trades: {ev_train['trades']}, Wins: {ev_train['wins']}, "
      f"WR: {fmt_wr(ev_train['WR'])}, CR: {fmt_pct(ev_train['CR'])}, "
      f"Avg R: {ev_train['avg_R']:+.2f}")
    reasons_str = ", ".join(f"{k}={v}" for k, v in sorted(ev_train["reasons"].items()))
    P(f"    Salidas: {reasons_str}")

    if ev_train["trade_details"]:
        P(f"\n  Detalle trades TRAIN:")
        for i, (pat, trade) in enumerate(ev_train["trade_details"], 1):
            entry_str = pat["first_signal_date"].strftime("%Y-%m-%d %H:%M")
            exit_str = trade["exit_date"].strftime("%Y-%m-%d %H:%M")
            P(f"    Trade {i}: {entry_str} -> {exit_str} | {trade['exit_reason']:<15s} | "
              f"PnL={trade['pnl_pct']:+.2%} | R={trade['r_multiple']:+.1f}R | "
              f"Dur={trade.get('duration_days', '?')}d")

    # ── Effect of atr_mult ──
    P(f"\n  Efecto de atr_mult:")
    P(f"  {'atr_mult':>8s} | {'Swings':>6s} | {'Contr':>5s} | {'Avg Trades':>10s} | "
      f"{'Avg CR':>8s} | {'Best CR':>8s} | {'c/trades':>8s}")
    P(f"  {'─'*70}")
    for atr_mult in ATR_MULTS:
        sub = det_df[det_df["atr_mult"] == atr_mult]
        has_trades = sub[sub["trades"] > 0]
        swings = sub.iloc[0]["n_swings"]
        contr = sub.iloc[0]["n_contractions"]
        P(f"  {atr_mult:>8.2f} | {int(swings):>6d} | {int(contr):>5d} | "
          f"{sub['trades'].mean():>10.1f} | {sub['CR'].mean():>+8.2%} | "
          f"{sub['CR'].max():>+8.2%} | {len(has_trades):>3d}/{len(sub)}")

    return {
        "ticker": ticker,
        "best_atr_mult": best_atr_mult,
        "best_detection": {
            "depth_atr": best_depth_atr,
            "reduction": best_reduction,
            "lookback_bars": best_lookback,
        },
        "best_exit": best_exit,
        "train_cr": float(best_exit_row["CR"]),
        "train_trades": int(best_exit_row["trades"]),
        "train_wr": float(best_exit_row["WR"]),
        "det_df": det_df,
    }


# ══════════════════════════════════════════════════════════════
#  MAIN — TRAIN ONLY
# ══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    all_results = []

    for ticker in TICKERS:
        hourly = load_ticker(ticker)
        train = hourly[hourly.index < CUTOFF]
        result = run_single_currency_train(ticker, train)
        all_results.append(result)

    P("\n\n" + "=" * 70)
    P("  RESUMEN FINAL — TRAIN")
    P("=" * 70)
    for r in all_results:
        d = r["best_detection"]
        e = r["best_exit"]
        P(f"  {r['ticker']}: atr_mult={r['best_atr_mult']}, d={d['depth_atr']}, "
          f"r={d['reduction']}, lb={d['lookback_bars']}, "
          f"trail={e['trailing_atr_multiplier']}, target={e['target_r_multiple']}, "
          f"early={e['early_exit_days']}, be_R={e['breakeven_r_multiple']} "
          f"-> {r['train_trades']}T, WR={fmt_wr(r['train_wr'])}, CR={fmt_pct(r['train_cr'])}")

    P("\n\nCompleto! (solo TRAIN — correr TEST separadamente)")
