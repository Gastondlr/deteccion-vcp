from __future__ import annotations

from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd

from models.types import VCPSignal
from vcp_detection.heuristic.atr_compression import compute_atr


def group_signals_into_patterns(
    signals: dict[pd.Timestamp, VCPSignal],
    risk_params: dict,
    max_gap_days: int = 30,
) -> list[dict]:
    if not signals:
        return []

    max_stop_pct = risk_params.get("max_stop_loss_pct", 0.07)

    sorted_dates = sorted(signals.keys())
    patterns = []
    current_group = [sorted_dates[0]]

    for i in range(1, len(sorted_dates)):
        gap = (sorted_dates[i] - sorted_dates[i - 1]).days
        if gap <= max_gap_days:
            current_group.append(sorted_dates[i])
        else:
            patterns.append(current_group)
            current_group = [sorted_dates[i]]
    patterns.append(current_group)

    result = []
    for group in patterns:
        first_sig = signals[group[0]]
        vol_contr = first_sig.volume_contraction
        vol_ratio = (
            vol_contr.method_metrics.get("ratio_observed")
            if vol_contr is not None
            else None
        )

        entry = first_sig.entry_price
        stop_pattern = first_sig.suggested_stop
        stop_pct = entry * (1.0 - max_stop_pct)
        effective_stop = max(stop_pattern, stop_pct)
        stop_method = "fixed_pct" if stop_pct >= stop_pattern else "pattern"
        stop_distance = (entry - effective_stop) / entry
        initial_risk = entry - effective_stop

        result.append(
            {
                "first_signal_date": group[0],
                "last_signal_date": group[-1],
                "n_signal_days": len(group),
                "pivot_price": first_sig.pivot_price,
                "entry_price": entry,
                "stop_pattern": stop_pattern,
                "stop_pct": stop_pct,
                "effective_stop": effective_stop,
                "stop_method": stop_method,
                "stop_distance_pct": stop_distance,
                "initial_risk": initial_risk,
                "n_contractions": first_sig.metadata["n_contractions"],
                "depths_pct": first_sig.metadata["depths_pct"],
                "atr_ratio": first_sig.atr_compression.method_metrics.get(
                    "ratio_observed"
                ),
                "vol_contr_ratio": vol_ratio,
                "signal_obj": first_sig,
            }
        )
    return result


def simulate_trade(
    ohlc: pd.DataFrame,
    pattern: dict,
    risk_params: dict,
    max_hold_days: int = 252,
) -> dict:
    entry_date = pattern["first_signal_date"]
    entry_price = pattern["entry_price"]
    initial_stop = pattern["effective_stop"]
    initial_risk = pattern["initial_risk"]
    step = risk_params["breakeven_r_multiple"]
    sma_period = risk_params["trailing_sma_period"]
    vol_factor = risk_params["trailing_volume_factor"]

    trailing_stop_method = risk_params.get("trailing_stop_method", "sma")
    trailing_atr_period = risk_params.get("trailing_atr_period", 14)
    trailing_atr_multiplier = risk_params.get("trailing_atr_multiplier", 3.0)
    max_bars_no_progress = risk_params.get("max_bars_without_progress", None)
    min_progress_r = risk_params.get("min_progress_r", 0.5)
    early_exit_days = risk_params.get("early_exit_days", None)
    target_r_multiple = risk_params.get("target_r_multiple", None)

    entry_loc = ohlc.index.get_loc(entry_date)
    end_loc = min(entry_loc + max_hold_days, len(ohlc) - 1)

    atr_series = None
    if trailing_stop_method == "atr":
        atr_series = compute_atr(ohlc, trailing_atr_period)

    stop = initial_stop
    stop_history = [(entry_date, stop)]
    max_r = 0.0
    highest_close = entry_price
    last_progress_loc = entry_loc
    best_r_at_check = 0.0

    def _make_result(dt, close, profit, reason):
        return {
            "exit_date": dt,
            "exit_price": close,
            "exit_reason": reason,
            "duration_days": (dt - entry_date).days,
            "pnl_pct": (close - entry_price) / entry_price,
            "r_multiple": profit / initial_risk if initial_risk > 0 else 0,
            "max_r": max_r,
            "stop_history": stop_history,
        }

    for loc in range(entry_loc + 1, end_loc + 1):
        dt = ohlc.index[loc]
        close = float(ohlc["close"].iloc[loc])
        profit = close - entry_price
        r_mult = 0.0

        if initial_risk > 0:
            r_mult = profit / initial_risk
            max_r = max(max_r, r_mult)

            steps_completed = int(r_mult / step)
            if steps_completed >= 1:
                new_stop = entry_price + (steps_completed - 1) * step * initial_risk
                if new_stop > stop:
                    stop = new_stop

        if close > highest_close:
            highest_close = close

        if trailing_stop_method == "atr" and atr_series is not None:
            atr_val = float(atr_series.iloc[loc])
            if not np.isnan(atr_val):
                atr_trail = highest_close - trailing_atr_multiplier * atr_val
                if atr_trail > stop:
                    stop = atr_trail

        stop_history.append((dt, stop))

        if target_r_multiple is not None and initial_risk > 0:
            if r_mult >= target_r_multiple:
                return _make_result(dt, close, profit, "target")

        if early_exit_days is not None and (loc - entry_loc) <= early_exit_days:
            if close < entry_price:
                return _make_result(dt, close, profit, "early_exit")

        if close <= stop:
            reason = "trailing_stop" if stop >= entry_price - 1e-10 else "stop_loss"
            return _make_result(dt, close, profit, reason)

        if trailing_stop_method == "sma":
            if loc >= sma_period:
                sma_slice = ohlc["close"].iloc[loc - sma_period + 1 : loc + 1]
                sma_val = float(sma_slice.mean())
                if close < sma_val and "volume" in ohlc.columns:
                    vol_slice = ohlc["volume"].iloc[loc - sma_period + 1 : loc + 1]
                    avg_vol = float(vol_slice.mean())
                    cur_vol = float(ohlc["volume"].iloc[loc])
                    if avg_vol > 0 and cur_vol > avg_vol * vol_factor:
                        return _make_result(dt, close, profit, "distribution")

        if max_bars_no_progress is not None:
            if initial_risk > 0 and r_mult > best_r_at_check + min_progress_r:
                best_r_at_check = r_mult
                last_progress_loc = loc
            if loc - last_progress_loc >= max_bars_no_progress:
                return _make_result(dt, close, profit, "time_exit")

    last_close = float(ohlc["close"].iloc[end_loc])
    last_profit = last_close - entry_price
    return {
        "exit_date": ohlc.index[end_loc],
        "exit_price": last_close,
        "exit_reason": "open",
        "duration_days": (ohlc.index[end_loc] - entry_date).days,
        "pnl_pct": (last_close - entry_price) / entry_price,
        "r_multiple": last_profit / initial_risk if initial_risk > 0 else 0,
        "max_r": max_r,
        "stop_history": stop_history,
    }


def plot_vcp_pattern(
    ohlc: pd.DataFrame,
    pattern: dict,
    pattern_number: int,
    ticker: str = "",
    margin_bars_before: int = 40,
    margin_bars_after: int = 30,
    save_path: str | Path | None = None,
) -> plt.Figure:
    sig = pattern["signal_obj"]
    seq = sig.pivot_info.sequence
    contractions = seq.contractions

    pattern_start = contractions[0].high_swing.date
    signal_date = pattern["first_signal_date"]

    start_loc = max(0, ohlc.index.get_loc(pattern_start) - margin_bars_before)
    end_loc = min(
        len(ohlc) - 1, ohlc.index.get_loc(signal_date) + margin_bars_after
    )
    window = ohlc.iloc[start_loc : end_loc + 1]

    swing_highs_dates = [c.high_swing.date for c in contractions]
    swing_highs_prices = [c.high_swing.price for c in contractions]
    swing_lows_dates = [c.low_swing.date for c in contractions]
    swing_lows_prices = [c.low_swing.price for c in contractions]

    vol_ma50 = ohlc["volume"].rolling(50, min_periods=1).mean()

    fig, (ax_price, ax_vol) = plt.subplots(
        2,
        1,
        figsize=(14, 8),
        height_ratios=[3, 1],
        sharex=True,
        gridspec_kw={"hspace": 0.08},
    )

    ax_price.plot(
        window.index,
        window["close"],
        color="#2c3e50",
        linewidth=1.2,
        label="Close",
        zorder=2,
    )

    colors_contraction = plt.cm.Blues(np.linspace(0.25, 0.55, len(contractions)))
    for i, c in enumerate(contractions):
        ax_price.axvspan(
            c.high_swing.date,
            c.low_swing.date,
            alpha=0.12,
            color=colors_contraction[i],
            zorder=0,
        )
        mid_date = c.high_swing.date + (c.low_swing.date - c.high_swing.date) / 2
        ax_price.annotate(
            f"C{i+1}\n{c.depth_pct:.1%}",
            xy=(mid_date, (c.high_swing.price + c.low_swing.price) / 2),
            fontsize=8,
            ha="center",
            va="center",
            color="#2c3e50",
            fontweight="bold",
        )

    ax_price.scatter(
        swing_highs_dates,
        swing_highs_prices,
        marker="v",
        s=80,
        color="#e74c3c",
        zorder=4,
        label="Swing High",
    )
    ax_price.scatter(
        swing_lows_dates,
        swing_lows_prices,
        marker="^",
        s=80,
        color="#27ae60",
        zorder=4,
        label="Swing Low",
    )

    pivot_price = pattern["pivot_price"]
    ax_price.axhline(
        pivot_price,
        color="#e67e22",
        linestyle="--",
        linewidth=1.5,
        alpha=0.8,
        label=f"Pivot ${pivot_price:.2f}",
    )

    effective_stop = pattern["effective_stop"]
    stop_method = pattern["stop_method"]
    ax_price.axhline(
        effective_stop,
        color="#e74c3c",
        linestyle="-",
        linewidth=1.5,
        alpha=0.8,
        label=f"Stop ${effective_stop:.2f} ({stop_method})",
    )
    alt_stop = (
        pattern["stop_pct"] if stop_method == "pattern" else pattern["stop_pattern"]
    )
    ax_price.axhline(
        alt_stop,
        color="#e74c3c",
        linestyle=":",
        linewidth=0.8,
        alpha=0.35,
    )

    entry_price = pattern["entry_price"]
    ax_price.scatter(
        [signal_date],
        [entry_price],
        marker="*",
        s=300,
        color="#f39c12",
        edgecolors="#e67e22",
        linewidth=1.5,
        zorder=5,
        label=f"BUY ${entry_price:.2f}",
    )

    depths_str = " -> ".join(f"{d:.1%}" for d in pattern["depths_pct"])
    ax_price.set_title(
        f"Patron VCP #{pattern_number} — {ticker} — "
        f"Senal: {signal_date.strftime('%Y-%m-%d')}  |  "
        f"Contracciones: [{depths_str}]  |  "
        f"ATR ratio: {pattern['atr_ratio']:.3f}",
        fontsize=11,
        fontweight="bold",
        pad=10,
    )
    ax_price.set_ylabel("Precio (USD)", fontsize=10)
    ax_price.legend(loc="upper left", fontsize=8, framealpha=0.9)

    vol_window = window["volume"]
    vol_ma_window = vol_ma50.loc[window.index]

    vol_colors = [
        "#27ae60"
        if window["close"].iloc[i] >= window["open"].iloc[i]
        else "#e74c3c"
        for i in range(len(window))
    ]
    ax_vol.bar(
        window.index,
        vol_window,
        width=0.8,
        color=vol_colors,
        alpha=0.6,
        zorder=2,
    )
    ax_vol.plot(
        window.index,
        vol_ma_window,
        color="#3498db",
        linewidth=1.5,
        label="Vol MA(50)",
        zorder=3,
    )

    if signal_date in window.index:
        signal_vol = ohlc.loc[signal_date, "volume"]
        signal_ma = vol_ma50.loc[signal_date]
        vol_ratio = signal_vol / signal_ma if signal_ma > 0 else 0
        ax_vol.bar(
            [signal_date],
            [signal_vol],
            width=0.8,
            color="#f39c12",
            alpha=0.9,
            zorder=4,
            label=f"Breakout vol ({vol_ratio:.1f}x avg)",
        )

    ax_vol.set_ylabel("Volumen", fontsize=10)
    ax_vol.legend(loc="upper left", fontsize=8, framealpha=0.9)
    ax_vol.yaxis.set_major_formatter(
        mticker.FuncFormatter(
            lambda x, _: f"{x/1e6:.0f}M" if x >= 1e6 else f"{x/1e3:.0f}K"
        )
    )

    ax_vol.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    ax_vol.xaxis.set_major_locator(mdates.MonthLocator(interval=1))
    fig.autofmt_xdate(rotation=30)

    plt.tight_layout()
    if save_path is not None:
        fig.savefig(save_path, dpi=110, bbox_inches="tight")
        plt.close(fig)
    else:
        plt.show()
    return fig


def plot_trade_simulation(
    ohlc: pd.DataFrame,
    pattern: dict,
    trade_result: dict,
    pattern_number: int,
    risk_params: dict,
    ticker: str = "",
    margin_bars_before: int = 10,
    save_path: str | Path | None = None,
) -> plt.Figure:
    entry_date = pattern["first_signal_date"]
    exit_date = trade_result["exit_date"]
    entry_price = pattern["entry_price"]
    initial_risk = pattern["initial_risk"]

    entry_loc = ohlc.index.get_loc(entry_date)
    exit_loc = ohlc.index.get_loc(exit_date)
    start_loc = max(0, entry_loc - margin_bars_before)
    window = ohlc.iloc[start_loc : exit_loc + 5]

    stop_dates, stop_prices = zip(*trade_result["stop_history"])

    fig, (ax_price, ax_vol) = plt.subplots(
        2,
        1,
        figsize=(14, 7),
        height_ratios=[3, 1],
        sharex=True,
        gridspec_kw={"hspace": 0.08},
    )

    ax_price.plot(
        window.index,
        window["close"],
        color="#2c3e50",
        linewidth=1.2,
        label="Close",
    )

    ax_price.step(
        stop_dates,
        stop_prices,
        where="post",
        color="#e74c3c",
        linewidth=2.0,
        alpha=0.8,
        label="Stop loss",
    )

    ax_price.axhline(
        entry_price,
        color="#95a5a6",
        linestyle=":",
        linewidth=0.8,
        alpha=0.5,
    )
    ax_price.scatter(
        [entry_date],
        [entry_price],
        marker="*",
        s=250,
        color="#f39c12",
        edgecolors="#e67e22",
        linewidth=1.5,
        zorder=5,
        label=f"BUY ${entry_price:.2f}",
    )

    exit_colors = {
        "stop_loss": "#e74c3c",
        "trailing_stop": "#e67e22",
        "distribution": "#9b59b6",
        "time_exit": "#95a5a6",
        "early_exit": "#e74c3c",
        "target": "#27ae60",
        "open": "#3498db",
    }
    exit_markers = {
        "stop_loss": "X",
        "trailing_stop": "X",
        "distribution": "D",
        "time_exit": "s",
        "early_exit": "X",
        "target": "*",
        "open": "o",
    }
    reason = trade_result["exit_reason"]
    ax_price.scatter(
        [exit_date],
        [trade_result["exit_price"]],
        marker=exit_markers.get(reason, "o"),
        s=200,
        color=exit_colors.get(reason, "#7f8c8d"),
        edgecolors="black",
        linewidth=1,
        zorder=5,
        label=f"EXIT: {reason} ${trade_result['exit_price']:.2f}",
    )

    step = risk_params["breakeven_r_multiple"]
    for r_level in range(1, 8):
        r_price = entry_price + r_level * step * initial_risk
        if r_price < window["close"].max() * 1.1:
            ax_price.axhline(
                r_price,
                color="#27ae60",
                linestyle=":",
                linewidth=0.5,
                alpha=0.3,
            )
            ax_price.text(
                window.index[-1],
                r_price,
                f" {r_level * step:.0f}R",
                fontsize=7,
                color="#27ae60",
                va="center",
            )

    pnl_str = f"{trade_result['pnl_pct']:+.1%}"
    r_str = f"{trade_result['r_multiple']:+.1f}R"
    ax_price.set_title(
        f"Trade #{pattern_number} — {ticker} — {reason.upper()} — "
        f"P&L: {pnl_str} ({r_str}) — "
        f"{trade_result['duration_days']}d — "
        f"Max: {trade_result['max_r']:.1f}R",
        fontsize=11,
        fontweight="bold",
        pad=10,
    )
    ax_price.set_ylabel("Precio (USD)")
    ax_price.legend(loc="upper left", fontsize=8, framealpha=0.9)

    sma_period = risk_params["trailing_sma_period"]
    vol_ma = ohlc["volume"].rolling(sma_period, min_periods=1).mean()

    vol_colors = [
        "#27ae60"
        if window["close"].iloc[i] >= window["open"].iloc[i]
        else "#e74c3c"
        for i in range(len(window))
    ]
    ax_vol.bar(
        window.index, window["volume"], width=0.8, color=vol_colors, alpha=0.5
    )
    ax_vol.plot(
        window.index,
        vol_ma.loc[window.index],
        color="#3498db",
        linewidth=1.2,
        label=f"Vol MA({sma_period})",
    )

    vol_threshold = vol_ma.loc[window.index] * risk_params["trailing_volume_factor"]
    ax_vol.plot(
        window.index,
        vol_threshold,
        color="#9b59b6",
        linewidth=0.8,
        linestyle="--",
        alpha=0.5,
        label=f"{risk_params['trailing_volume_factor']}x avg (distrib.)",
    )

    ax_vol.set_ylabel("Volumen")
    ax_vol.legend(loc="upper left", fontsize=8, framealpha=0.9)
    ax_vol.yaxis.set_major_formatter(
        mticker.FuncFormatter(
            lambda x, _: f"{x/1e6:.0f}M" if x >= 1e6 else f"{x/1e3:.0f}K"
        )
    )
    ax_vol.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    fig.autofmt_xdate(rotation=30)

    plt.tight_layout()
    if save_path is not None:
        fig.savefig(save_path, dpi=110, bbox_inches="tight")
        plt.close(fig)
    else:
        plt.show()
    return fig
