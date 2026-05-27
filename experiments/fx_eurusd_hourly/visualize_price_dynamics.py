"""Visualize EURUSD hourly price dynamics at 3 scales: 1 day, 1 week, 1 month."""
import functools
import sys
from pathlib import Path

print = functools.partial(print, flush=True)

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd
import numpy as np

project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

DATA_DIR = project_root / "data" / "monedas_hora"
OUTPUT_DIR = Path(__file__).parent / "price_dynamics"
OUTPUT_DIR.mkdir(exist_ok=True)

ohlc = pd.read_csv(DATA_DIR / "EURUSD.csv", parse_dates=["date"], index_col="date")

from vcp_detection.heuristic.atr_compression import compute_atr
atr14 = compute_atr(ohlc, 14)

# Pick representative periods (midweek, no holidays, 2019 for TEST period)
DAY_START = "2019-03-13"
DAY_END = "2019-03-14"
WEEK_START = "2019-03-11"
WEEK_END = "2019-03-16"
MONTH_START = "2019-03-01"
MONTH_END = "2019-04-01"

windows = [
    ("1 dia (13 Mar 2019)", DAY_START, DAY_END),
    ("1 semana (11-15 Mar 2019)", WEEK_START, WEEK_END),
    ("1 mes (Mar 2019)", MONTH_START, MONTH_END),
]

for label, start, end in windows:
    chunk = ohlc.loc[start:end]
    atr_chunk = atr14.loc[start:end]

    fig, axes = plt.subplots(3, 1, figsize=(16, 12), height_ratios=[3, 1, 1],
                              gridspec_kw={"hspace": 0.12})

    # Panel 1: OHLC as candlestick-style (close line + high/low range)
    ax = axes[0]
    ax.plot(chunk.index, chunk["close"], color="#2c3e50", linewidth=1.3, label="Close", zorder=3)
    ax.fill_between(chunk.index, chunk["low"], chunk["high"], alpha=0.15, color="#3498db", label="High-Low range")
    ax.set_title(f"EURUSD Hourly — {label}", fontsize=14, fontweight="bold")
    ax.set_ylabel("Precio")
    ax.legend(loc="upper left", fontsize=9)
    ax.grid(True, alpha=0.3)

    # Add ATR bands
    mid = chunk["close"]
    ax.plot(chunk.index, mid + atr_chunk, color="#e74c3c", linewidth=0.7, linestyle="--", alpha=0.5, label="±ATR(14)")
    ax.plot(chunk.index, mid - atr_chunk, color="#e74c3c", linewidth=0.7, linestyle="--", alpha=0.5)

    # Mark sessions if daily view
    if "dia" in label:
        for h in chunk.index:
            if h.hour == 8:
                ax.axvline(h, color="#27ae60", alpha=0.3, linestyle=":", linewidth=1)
                ax.text(h, ax.get_ylim()[1], " London", fontsize=7, color="#27ae60", va="top")
            elif h.hour == 13:
                ax.axvline(h, color="#e67e22", alpha=0.3, linestyle=":", linewidth=1)
                ax.text(h, ax.get_ylim()[1], " NY", fontsize=7, color="#e67e22", va="top")

    if "semana" in label:
        for d in pd.date_range(start, end, freq="D"):
            if d.dayofweek < 5 and d in chunk.index:
                ax.axvline(d, color="gray", alpha=0.2, linestyle="-", linewidth=0.5)

    # Panel 2: Hourly returns
    ax2 = axes[1]
    returns = chunk["close"].pct_change() * 100
    colors = ["#27ae60" if r >= 0 else "#e74c3c" for r in returns]
    ax2.bar(chunk.index, returns, color=colors, width=0.03, alpha=0.7)
    ax2.axhline(0, color="gray", linewidth=0.5)
    ax2.set_ylabel("Retorno horario (%)")
    ax2.grid(True, alpha=0.3)

    # Stats box
    ret_clean = returns.dropna()
    stats_text = (f"μ={ret_clean.mean():.4f}%  σ={ret_clean.std():.4f}%  "
                  f"max={ret_clean.max():.3f}%  min={ret_clean.min():.3f}%")
    ax2.text(0.02, 0.92, stats_text, transform=ax2.transAxes, fontsize=8,
             bbox=dict(boxstyle="round,pad=0.3", facecolor="wheat", alpha=0.5))

    # Panel 3: ATR(14) evolution
    ax3 = axes[2]
    ax3.plot(chunk.index, atr_chunk * 100, color="#8e44ad", linewidth=1.2)
    ax3.set_ylabel("ATR(14) (%)")
    ax3.set_xlabel("Fecha")
    ax3.grid(True, alpha=0.3)

    # Format x-axis
    if "dia" in label:
        ax3.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    elif "semana" in label:
        ax3.xaxis.set_major_formatter(mdates.DateFormatter("%a %d %H:%M"))
        plt.setp(ax3.xaxis.get_majorticklabels(), rotation=30, ha="right", fontsize=8)
    else:
        ax3.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))

    slug = label.split("(")[0].strip().replace(" ", "_")
    path = OUTPUT_DIR / f"eurusd_{slug}.png"
    fig.savefig(path, dpi=120, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved: {path}")

# Also do a 3-month view to see larger structure
fig, ax = plt.subplots(figsize=(18, 6))
q1 = ohlc.loc["2019-01-01":"2019-04-01"]
ax.plot(q1.index, q1["close"], color="#2c3e50", linewidth=0.8)
ax.fill_between(q1.index, q1["low"], q1["high"], alpha=0.1, color="#3498db")
ax.set_title("EURUSD Hourly — Q1 2019 (3 meses)", fontsize=14, fontweight="bold")
ax.set_ylabel("Precio")
ax.grid(True, alpha=0.3)
ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
ax.xaxis.set_major_locator(mdates.WeekdayLocator(byweekday=mdates.MO))
plt.setp(ax.xaxis.get_majorticklabels(), rotation=30, ha="right", fontsize=8)
fig.savefig(OUTPUT_DIR / "eurusd_3_meses.png", dpi=120, bbox_inches="tight")
plt.close(fig)
print(f"Saved: {OUTPUT_DIR / 'eurusd_3_meses.png'}")

print("\nCompleto!")
