"""Save AAPL train results to MLflow with trade plots.

Best config: trail=2.5, bars=15, minR=0.5, Vol 1.2x win=3d
Variants: with and without Trend Template.
"""
import functools
import sys
import tempfile
from pathlib import Path

print = functools.partial(print, flush=True)

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.ticker as mticker
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
from stages.trend_template import evaluate_trend_template

TICKER = "AAPL"
TRAIN_CUTOFF = "2020-01-01"
DATA_DIR = project_root / "data" / "csv"

DETECTION_PARAMS = {
    "atr_mult": 2.0,
    "use_close_only": False,
    "max_depth_atr": 6,
    "min_total_reduction": 0.80,
    "lookback_bars": 126,
    "tolerance": 0.10,
    "max_depth_pct": 0.25,
    "ascending_lows_tolerance": 0.01,
    "compression_threshold": 0.95,
}

EXIT_PARAMS = {
    "trailing_atr_multiplier": 2.5,
    "target_r_multiple": None,
    "early_exit_days": None,
    "breakeven_r_multiple": 1.5,
    "max_stop_loss_pct": 0.05,
    "max_bars_without_progress": 15,
    "min_progress_r": 0.5,
}

BREAKOUT_PARAMS = {
    "volume_method": "ratio",
    "volume_ratio_threshold": 1.2,
    "volume_lookback_days": 50,
    "require_volume_confirmation": True,
    "volume_confirmation_window": 3,
}

RISK_BASE = {
    "trailing_sma_period": 20,
    "trailing_volume_factor": 1.5,
    "trailing_stop_method": "atr",
    "trailing_atr_period": 14,
}


def plot_trade(ohlc, pattern, trade, trade_number, risk_params, ticker, save_path=None):
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
                     label=f"Pivot {pivot_price:.2f}")

    stop_dates, stop_prices = zip(*trade["stop_history"])
    ax_price.step(stop_dates, stop_prices, where="post", color="#e74c3c",
                  linewidth=2.0, alpha=0.8, label="Stop loss")

    ax_price.scatter([entry_date], [entry_price], marker="*", s=250, color="#f39c12",
                     edgecolors="#e67e22", linewidth=1.5, zorder=5,
                     label=f"BUY {entry_price:.2f}")

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
        label=f"EXIT: {reason} {trade['exit_price']:.2f}",
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
        f"Trade #{trade_number} — {ticker} — {reason.upper()} — "
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
    ax_vol.yaxis.set_major_formatter(
        mticker.FuncFormatter(lambda x, _: f"{x/1e6:.0f}M" if x >= 1e6 else f"{x/1e3:.0f}K"))

    ax_vol.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    fig.autofmt_xdate(rotation=30)
    plt.tight_layout()

    if save_path:
        fig.savefig(save_path, dpi=110, bbox_inches="tight")
        plt.close(fig)
    return fig


def compute_equity_and_metrics(train, results, years):
    close = train["close"]
    bh_eq = close / close.iloc[0]
    bh_rets = close.pct_change().dropna()
    bh_dd = (bh_eq - bh_eq.cummax()) / bh_eq.cummax()

    trades_list = [t for _, t in results]
    n = len(results)
    wins = sum(1 for t in trades_list if t["pnl_pct"] > 0)
    cr = float(np.prod([1 + t["pnl_pct"] for t in trades_list]) - 1) if n else 0
    avg_r = float(np.mean([t["r_multiple"] for t in trades_list])) if n else 0
    sum_w = sum(t["pnl_pct"] for t in trades_list if t["pnl_pct"] > 0)
    sum_l = abs(sum(t["pnl_pct"] for t in trades_list if t["pnl_pct"] <= 0))
    pf = sum_w / sum_l if sum_l > 0 else float("inf")

    equity_values = []
    equity = 1.0
    trade_periods = [(pat["first_signal_date"], trade["exit_date"], pat["entry_price"])
                     for pat, trade in results]
    period_idx = 0
    in_trade = False
    prev_close_px = 0
    total_days_in = 0
    for i, dt in enumerate(train.index):
        if period_idx < len(trade_periods):
            entry_dt, exit_dt, entry_px = trade_periods[period_idx]
            if dt == entry_dt:
                in_trade = True
                prev_close_px = entry_px
            if in_trade and dt >= entry_dt:
                today_close = float(train["close"].iloc[i])
                daily_ret = (today_close - prev_close_px) / prev_close_px
                equity *= (1 + daily_ret)
                prev_close_px = today_close
                total_days_in += 1
            if dt >= exit_dt and in_trade:
                in_trade = False
                period_idx += 1
        equity_values.append(equity)

    strat_eq = pd.Series(equity_values, index=train.index)
    strat_rets = strat_eq.pct_change().dropna()
    strat_dd = (strat_eq - strat_eq.cummax()) / strat_eq.cummax()

    return {
        "n_trades": n,
        "n_wins": wins,
        "n_losses": n - wins,
        "winrate": wins / n if n else 0,
        "cumulative_return": cr,
        "cagr": float((strat_eq.iloc[-1]) ** (1 / years) - 1),
        "max_drawdown": float(strat_dd.min()),
        "sharpe": float(strat_rets.mean() / strat_rets.std() * np.sqrt(252)) if strat_rets.std() > 0 else 0,
        "avg_r_multiple": avg_r,
        "profit_factor": pf if pf != float("inf") else 999.0,
        "exposure_pct": total_days_in / len(train),
        "avg_duration_days": float(np.mean([t["duration_days"] for t in trades_list])) if n else 0,
        "buyhold_return": float(bh_eq.iloc[-1] - 1),
        "buyhold_cagr": float((bh_eq.iloc[-1]) ** (1 / years) - 1),
        "buyhold_max_drawdown": float(bh_dd.min()),
        "buyhold_sharpe": float(bh_rets.mean() / bh_rets.std() * np.sqrt(252)),
    }


if __name__ == "__main__":
    print(f"Cargando {TICKER}...")
    daily = pd.read_csv(DATA_DIR / f"{TICKER}.csv", parse_dates=["date"], index_col="date")
    train = daily[daily.index < TRAIN_CUTOFF]
    years = len(train) / 252

    print(f"  TRAIN: {len(train):,} barras ({train.index.min().date()} a {train.index[-1].date()})")

    config = ATRZigZagConfig(
        atr_length=14,
        atr_mult=DETECTION_PARAMS["atr_mult"],
        use_close_only=DETECTION_PARAMS["use_close_only"],
    )
    detector = ATRZigZagDetector(config)
    swings = detector.detect(train)
    contractions = compute_contractions(swings, train)
    atr = compute_atr(train, 14)
    tt_eval = evaluate_trend_template(train)
    tt_mask = tt_eval["trend_template"]

    seq_params = {
        "method": "tolerance",
        "min_contractions": 2,
        "max_contractions": 6,
        "lookback_bars": DETECTION_PARAMS["lookback_bars"],
        "tolerance": DETECTION_PARAMS["tolerance"],
        "max_depth_pct": DETECTION_PARAMS["max_depth_pct"],
        "max_depth_atr": DETECTION_PARAMS["max_depth_atr"],
        "min_total_reduction": DETECTION_PARAMS["min_total_reduction"],
        "max_gap_between_contractions_days": None,
        "require_ascending_lows": True,
        "ascending_lows_tolerance": DETECTION_PARAMS["ascending_lows_tolerance"],
    }
    comp_params = {
        "method": "ratio",
        "atr_period": 14,
        "ratio_threshold": DETECTION_PARAMS["compression_threshold"],
    }
    risk = {**RISK_BASE, **EXIT_PARAMS}

    res = run_full_vcp_pipeline(
        ohlc=train, swing_detector=detector,
        sequence_params=seq_params, compression_params=comp_params,
        breakout_params=BREAKOUT_PARAMS, volume_contraction_params=None,
        precomputed_swings=swings, precomputed_contractions=contractions,
        precomputed_atr=atr,
    )
    all_signals = {dt: s for dt, s in res.items() if s is not None}

    mlflow.set_tracking_uri(str(project_root / "mlruns"))
    mlflow.set_experiment("VCP_AAPL_DeepPerTicker")

    all_params = {
        "ticker": TICKER,
        "split": "TRAIN",
        "cutoff": TRAIN_CUTOFF,
        "n_bars": len(train),
        **{f"det_{k}": str(v) for k, v in DETECTION_PARAMS.items()},
        **{f"exit_{k}": str(v) for k, v in EXIT_PARAMS.items()},
        **{f"bkout_{k}": str(v) for k, v in BREAKOUT_PARAMS.items()},
    }

    with mlflow.start_run(run_name=f"{TICKER}_deep_train") as parent_run:

        for variant_name, use_tt in [("Vol_1.2x_win3d", False), ("Vol_1.2x_win3d_TT", True)]:
            signals = dict(all_signals)
            if use_tt:
                signals = {dt: s for dt, s in signals.items()
                           if dt in tt_mask.index and tt_mask.loc[dt]}

            results = evaluate_signals_to_trades(
                signals, train, risk, grouping="sequential", precomputed_atr=atr,
            )

            metrics = compute_equity_and_metrics(train, results, years)

            print(f"\n  {variant_name}: {metrics['n_trades']}T, "
                  f"WR={metrics['winrate']:.0%}, CR={metrics['cumulative_return']:+.2%}, "
                  f"Sharpe={metrics['sharpe']:.2f}, MaxDD={metrics['max_drawdown']:.2%}")

            with mlflow.start_run(run_name=f"{TICKER}_TRAIN_{variant_name}", nested=True):
                mlflow.log_params({**all_params, "trend_template": str(use_tt), "variant": variant_name})
                mlflow.log_metrics(metrics)

                if results:
                    with tempfile.TemporaryDirectory() as tmpdir:
                        for j, (pat, trade) in enumerate(results, 1):
                            pp = Path(tmpdir) / f"trade_{j}.png"
                            plot_trade(train, pat, trade, trade_number=j,
                                       risk_params=risk,
                                       ticker=f"{TICKER} TRAIN ({variant_name})",
                                       save_path=str(pp))
                            mlflow.log_artifact(str(pp), "plots")

                        rows = []
                        for j, (pat, trade) in enumerate(results, 1):
                            rows.append({
                                "trade_num": j,
                                "entry_date": pat["first_signal_date"].strftime("%Y-%m-%d"),
                                "exit_date": trade["exit_date"].strftime("%Y-%m-%d"),
                                "exit_reason": trade["exit_reason"],
                                "duration_days": trade["duration_days"],
                                "entry_price": pat["entry_price"],
                                "exit_price": trade["exit_price"],
                                "pivot_price": pat["pivot_price"],
                                "stop_price": pat["effective_stop"],
                                "pnl_pct": trade["pnl_pct"],
                                "r_multiple": trade["r_multiple"],
                                "max_r": trade["max_r"],
                                "n_contractions": pat["n_contractions"],
                            })
                        tdf = pd.DataFrame(rows)
                        tcp = Path(tmpdir) / "trades.csv"
                        tdf.to_csv(tcp, index=False)
                        mlflow.log_artifact(str(tcp), "tables")

                    for j, (pat, trade) in enumerate(results, 1):
                        entry_str = pat["first_signal_date"].strftime("%Y-%m-%d")
                        exit_str = trade["exit_date"].strftime("%Y-%m-%d")
                        print(f"    {j}: {entry_str} -> {exit_str} | {trade['exit_reason']:<15s} | "
                              f"PnL={trade['pnl_pct']:+.2%} | R={trade['r_multiple']:+.1f}R | "
                              f"MaxR={trade['max_r']:.1f}R | Dur={trade['duration_days']}d")

    print(f"\nMLflow: guardado en experimento VCP_AAPL_DeepPerTicker")
    print("Completo!")
