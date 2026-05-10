"""FX multi-currency experiment: best daily + hourly configs on all FX pairs.
Tracks results in MLflow with combined pattern+trade plots."""
import sys
import tempfile
import time
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np
import pandas as pd
import mlflow

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from models.configs import ATRZigZagConfig
from vcp_detection.heuristic import ATRZigZagDetector, run_full_vcp_pipeline
from vcp_detection.heuristic.contractions import compute_contractions
from vcp_detection.heuristic.atr_compression import compute_atr
from vcp_detection.analysis import group_signals_into_patterns, simulate_trade

TICKERS = ["EURUSD", "GBPUSD", "USDJPY", "USDCNH", "USDCNY"]

SWING_CONFIG = ATRZigZagConfig(atr_length=14, atr_mult=1.5, use_close_only=False)
COMPRESSION = {"method": "ratio", "atr_period": 14, "ratio_threshold": 0.85}
BREAKOUT = {
    "volume_method": "ratio", "volume_ratio_threshold": 1.5,
    "volume_lookback_days": 50, "require_volume_confirmation": False,
    "max_entry_distance_pct": 0.03,
}

CONFIGS = {
    "Diario": {
        "data_dir": project_root / "data" / "monedas",
        "experiment_name": "VCP_FX_Diario",
        "sequence": {
            "method": "tolerance", "min_contractions": 2, "max_contractions": 6,
            "lookback_bars": 126, "tolerance": 0.10,
            "max_depth_pct": 0.50, "max_depth_atr": 5, "min_total_reduction": 0.60,
            "max_gap_between_contractions_days": None,
            "require_ascending_lows": True, "ascending_lows_tolerance": 0.03,
        },
        "risk": {
            "max_stop_loss_pct": 0.02, "breakeven_r_multiple": 1.0,
            "trailing_sma_period": 20, "trailing_volume_factor": 1.5,
            "trailing_stop_method": "atr", "trailing_atr_period": 14,
            "trailing_atr_multiplier": 1.5,
            "target_r_multiple": 3.0, "early_exit_days": None,
            "max_bars_without_progress": 15, "min_progress_r": 0.5,
        },
    },
    "Horario": {
        "data_dir": project_root / "data" / "monedas_hora",
        "experiment_name": "VCP_FX_Horario",
        "sequence": {
            "method": "tolerance", "min_contractions": 2, "max_contractions": 6,
            "lookback_bars": 252, "tolerance": 0.10,
            "max_depth_pct": 0.50, "max_depth_atr": 2, "min_total_reduction": 0.70,
            "max_gap_between_contractions_days": None,
            "require_ascending_lows": True, "ascending_lows_tolerance": 0.03,
        },
        "risk": {
            "max_stop_loss_pct": 0.02, "breakeven_r_multiple": 1.0,
            "trailing_sma_period": 20, "trailing_volume_factor": 1.5,
            "trailing_stop_method": "atr", "trailing_atr_period": 14,
            "trailing_atr_multiplier": 2.0,
            "target_r_multiple": None, "early_exit_days": None,
            "max_bars_without_progress": 15, "min_progress_r": 0.5,
        },
    },
}


def load_ohlc(ticker, data_dir):
    return pd.read_csv(data_dir / f"{ticker}.csv", parse_dates=["date"], index_col="date")


def buy_and_hold_metrics(ohlc, ann_factor):
    c = ohlc["close"]
    total_return = float(c.iloc[-1] / c.iloc[0] - 1)
    dd = (c - c.cummax()) / c.cummax()
    max_dd = float(dd.min())
    daily_ret = c.pct_change().dropna()
    sharpe = float(daily_ret.mean() / daily_ret.std() * np.sqrt(ann_factor)) if daily_ret.std() > 0 else 0
    return {"buy_hold_return": total_return, "buy_hold_max_drawdown": max_dd, "buy_hold_sharpe": sharpe}


def trade_max_drawdown(ohlc, entry_date, exit_date):
    tc = ohlc.loc[entry_date:exit_date, "close"]
    if len(tc) < 2:
        return 0.0
    return float(((tc - tc.cummax()) / tc.cummax()).min())


def in_trade_sharpe(ohlc, trades, ann=252.0):
    dr = []
    for t in trades:
        tc = ohlc.loc[t["pattern"]["first_signal_date"]:t["exit_date"], "close"]
        if len(tc) >= 2:
            dr.append(tc.pct_change().dropna())
    if not dr:
        return 0.0
    ar = pd.concat(dr)
    if len(ar) < 2 or ar.std() == 0:
        return 0.0
    return float(ar.mean() / ar.std() * np.sqrt(ann))


def build_trade_table(trades, ticker):
    rows = []
    for i, t in enumerate(trades, 1):
        rows.append({
            "ticker": ticker, "trade_num": i,
            "entry_date": t["pattern"]["first_signal_date"].strftime("%Y-%m-%d"),
            "exit_date": t["exit_date"].strftime("%Y-%m-%d"),
            "exit_reason": t["exit_reason"],
            "duration_days": t["duration_days"],
            "entry_price": t["pattern"]["entry_price"],
            "exit_price": t["exit_price"],
            "pnl_pct": t["pnl_pct"], "r_multiple": t["r_multiple"],
            "max_r": t["max_r"], "max_drawdown": t.get("max_drawdown", 0),
            "n_contractions": t["pattern"]["n_contractions"],
            "atr_ratio": t["pattern"]["atr_ratio"],
        })
    return pd.DataFrame(rows)


def plot_combined(ohlc, pattern, trade, pattern_number, risk_params, ticker, save_path=None):
    """Single figure: pattern detection + trade simulation with stop evolution."""
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


def run_experiment(config_name, config):
    data_dir = config["data_dir"]
    experiment_name = config["experiment_name"]
    seq_params = config["sequence"]
    risk_params = config["risk"]

    print(f"\n{'='*70}")
    print(f"  EXPERIMENTO: {experiment_name} ({config_name})")
    print(f"{'='*70}")

    detector = ATRZigZagDetector(SWING_CONFIG)
    atr_period = COMPRESSION["atr_period"]

    print("  Cargando y precalculando...")
    cache = {}
    for ticker in TICKERS:
        fpath = data_dir / f"{ticker}.csv"
        if not fpath.exists():
            print(f"    {ticker}: archivo no encontrado, saltando")
            continue
        ohlc = load_ohlc(ticker, data_dir)
        t0 = time.time()
        swings = detector.detect(ohlc)
        contrs = compute_contractions(swings, ohlc)
        atr = compute_atr(ohlc, atr_period)
        cache[ticker] = {"ohlc": ohlc, "swings": swings, "contractions": contrs, "atr": atr}
        print(f"    {ticker}: {len(ohlc):,} barras, precalc {time.time()-t0:.1f}s")

    is_daily = "diario" in config_name.lower()
    ann_factor = 252 if is_daily else 252 * 20

    mlflow.set_tracking_uri(str(project_root / "mlruns"))
    mlflow.set_experiment(experiment_name)

    all_params = {
        "atr_length": SWING_CONFIG.atr_length, "atr_mult": SWING_CONFIG.atr_mult,
        "config": config_name,
        **{f"seq_{k}": str(v) for k, v in seq_params.items()},
        **{f"risk_{k}": str(v) for k, v in risk_params.items()},
    }

    ticker_summaries = []
    all_trades_dfs = []

    with mlflow.start_run(run_name=f"FX_{config_name}") as parent_run:
        mlflow.log_params(all_params)

        for ticker, c in cache.items():
            ohlc = c["ohlc"]
            print(f"\n  {ticker}...", end=" ")
            t0 = time.time()

            res = run_full_vcp_pipeline(
                ohlc=ohlc, swing_detector=detector,
                sequence_params=seq_params,
                compression_params=COMPRESSION,
                breakout_params=BREAKOUT,
                volume_contraction_params=None,
                precomputed_swings=c["swings"],
                precomputed_contractions=c["contractions"],
                precomputed_atr=c["atr"],
            )
            signals = {dt: s for dt, s in res.items() if s is not None}
            patterns = group_signals_into_patterns(signals, risk_params=risk_params)

            trades = []
            for p in patterns:
                t = simulate_trade(ohlc, p, risk_params)
                t["pattern"] = p
                t["max_drawdown"] = trade_max_drawdown(ohlc, p["first_signal_date"], t["exit_date"])
                trades.append(t)

            nt = len(trades)
            if nt > 0:
                nw = sum(1 for t in trades if t["pnl_pct"] > 0)
                nl = nt - nw
                cr = float(np.prod([1 + t["pnl_pct"] for t in trades]) - 1)
                avg_r = float(np.mean([t["r_multiple"] for t in trades]))
                wd = float(min(t["max_drawdown"] for t in trades))
                ad = float(np.mean([t["max_drawdown"] for t in trades]))
                sharpe = in_trade_sharpe(ohlc, trades, ann_factor)
            else:
                nw, nl, cr, avg_r, wd, ad, sharpe = 0, 0, 0, 0, 0, 0, 0

            bh = buy_and_hold_metrics(ohlc, ann_factor)

            with mlflow.start_run(run_name=ticker, nested=True):
                mlflow.log_params({**all_params, "ticker": ticker, "n_bars": len(ohlc)})
                metrics = {
                    "n_signals": len(signals), "n_patterns": len(patterns),
                    "n_trades": nt, "n_wins": nw, "n_losses": nl,
                    "winrate": nw / nt if nt > 0 else 0,
                    "cumulative_return": cr, "avg_r_multiple": avg_r,
                    "sharpe_ratio": sharpe,
                    "worst_trade_drawdown": wd, "avg_trade_drawdown": ad,
                    **bh,
                }
                mlflow.log_metrics(metrics)

                with tempfile.TemporaryDirectory() as tmpdir:
                    for j, (pat, trade) in enumerate(zip(patterns, trades), 1):
                        pp = Path(tmpdir) / f"trade_{j}.png"
                        plot_combined(ohlc, pat, trade, pattern_number=j,
                                      risk_params=risk_params, ticker=ticker, save_path=str(pp))
                        mlflow.log_artifact(str(pp), "plots")

                    if trades:
                        tdf = build_trade_table(trades, ticker)
                        tcp = Path(tmpdir) / "trades.csv"
                        tdf.to_csv(tcp, index=False)
                        mlflow.log_artifact(str(tcp), "tables")
                        all_trades_dfs.append(tdf)

            elapsed = time.time() - t0
            wr_str = f"{nw/nt:.0%}" if nt > 0 else "N/A"
            print(f"{nt} trades ({nw}W/{nl}L), WR={wr_str}, CR={cr:+.2%}, "
                  f"Sharpe={sharpe:.2f} ({elapsed:.1f}s)")

            ticker_summaries.append({
                "ticker": ticker, "n_bars": len(ohlc),
                "n_signals": len(signals), "n_patterns": len(patterns),
                "n_trades": nt, "n_wins": nw, "n_losses": nl,
                "winrate": nw / nt if nt > 0 else 0,
                "cumulative_return": cr, "avg_r_multiple": avg_r,
                "sharpe_ratio": sharpe,
                "worst_trade_drawdown": wd, "avg_trade_drawdown": ad,
                **bh,
            })

        sdf = pd.DataFrame(ticker_summaries)

        twt = sdf[sdf["n_trades"] > 0]
        agg = {
            "total_signals": int(sdf["n_signals"].sum()),
            "total_patterns": int(sdf["n_patterns"].sum()),
            "total_trades": int(sdf["n_trades"].sum()),
            "total_wins": int(sdf["n_wins"].sum()),
            "total_losses": int(sdf["n_losses"].sum()),
            "tickers_with_trades": int((sdf["n_trades"] > 0).sum()),
            "avg_winrate": float(twt["winrate"].mean()) if len(twt) > 0 else 0,
            "avg_cumulative_return": float(twt["cumulative_return"].mean()) if len(twt) > 0 else 0,
            "avg_r_multiple": float(twt["avg_r_multiple"].mean()) if len(twt) > 0 else 0,
            "avg_sharpe_ratio": float(twt["sharpe_ratio"].mean()) if len(twt) > 0 else 0,
            "worst_trade_drawdown": float(twt["worst_trade_drawdown"].min()) if len(twt) > 0 else 0,
            "avg_trade_drawdown": float(twt["avg_trade_drawdown"].mean()) if len(twt) > 0 else 0,
        }
        mlflow.log_metrics(agg)

        agg_row = {
            "ticker": "AGREGADO", "n_bars": int(sdf["n_bars"].sum()),
            "n_signals": agg["total_signals"], "n_patterns": agg["total_patterns"],
            "n_trades": agg["total_trades"], "n_wins": agg["total_wins"],
            "n_losses": agg["total_losses"],
            "winrate": agg["total_wins"] / agg["total_trades"] if agg["total_trades"] > 0 else 0,
            "cumulative_return": agg["avg_cumulative_return"],
            "avg_r_multiple": agg["avg_r_multiple"],
            "sharpe_ratio": agg["avg_sharpe_ratio"],
            "worst_trade_drawdown": agg["worst_trade_drawdown"],
            "avg_trade_drawdown": agg["avg_trade_drawdown"],
            "buy_hold_return": float(sdf["buy_hold_return"].mean()),
            "buy_hold_max_drawdown": float(sdf["buy_hold_max_drawdown"].min()),
            "buy_hold_sharpe": float(sdf["buy_hold_sharpe"].mean()),
        }
        summary = pd.concat([sdf, pd.DataFrame([agg_row])], ignore_index=True)

        with tempfile.TemporaryDirectory() as tmpdir:
            sp = Path(tmpdir) / "summary.csv"
            summary.to_csv(sp, index=False)
            mlflow.log_artifact(str(sp), "tables")

            if all_trades_dfs:
                all_trades = pd.concat(all_trades_dfs, ignore_index=True)
                atp = Path(tmpdir) / "all_trades.csv"
                all_trades.to_csv(atp, index=False)
                mlflow.log_artifact(str(atp), "tables")

    print(f"\n  {'='*60}")
    print(f"  RESUMEN {config_name.upper()}")
    print(f"  {'='*60}")
    fmt = {
        "winrate": "{:.0%}", "cumulative_return": "{:+.2%}",
        "avg_r_multiple": "{:+.2f}", "sharpe_ratio": "{:.2f}",
        "worst_trade_drawdown": "{:.2%}", "avg_trade_drawdown": "{:.2%}",
        "buy_hold_return": "{:+.2%}", "buy_hold_max_drawdown": "{:.2%}",
        "buy_hold_sharpe": "{:.2f}",
    }
    display_cols = ["ticker", "n_trades", "n_wins", "n_losses", "winrate",
                    "cumulative_return", "avg_r_multiple", "sharpe_ratio",
                    "worst_trade_drawdown", "avg_trade_drawdown",
                    "buy_hold_return", "buy_hold_max_drawdown", "buy_hold_sharpe"]
    display_df = summary[display_cols].copy()
    for col, f in fmt.items():
        if col in display_df.columns:
            display_df[col] = display_df[col].apply(lambda x: f.format(x) if pd.notna(x) else "")
    print(display_df.to_string(index=False))

    return summary


# ── Main ────────────────────────────────────────────────────

if __name__ == "__main__":
    results = {}
    for config_name, config in CONFIGS.items():
        results[config_name] = run_experiment(config_name, config)

    print("\n\n" + "="*70)
    print("  EXPERIMENTO COMPLETO")
    print("="*70)
    print("\nCompleto!")
