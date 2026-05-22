"""Genera histograma de PnL por senal individual para un ticker FX.

Usa exactamente las mismas funciones que run_fx_sequential_multicurrency.py
para garantizar consistencia en el conteo de senales.

Uso: python experiments/fx/generate_signal_histogram.py EURUSD
"""
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

import mlflow
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from models.configs import ATRZigZagConfig
from vcp_detection.heuristic import ATRZigZagDetector, run_full_vcp_pipeline
from vcp_detection.heuristic.contractions import compute_contractions
from vcp_detection.heuristic.atr_compression import compute_atr
from vcp_detection.analysis import simulate_trade, group_signals_into_patterns

COMPRESSION = {"method": "ratio", "atr_period": 14, "ratio_threshold": 0.85}
BREAKOUT = {
    "require_volume_confirmation": False,
    "volume_ratio_threshold": 1.5,
    "volume_method": "ratio",
    "volume_lookback_days": 50,
}
CUTOFF = "2020-01-01"
DATA_DIR = project_root / "data" / "monedas"

ticker = sys.argv[1].upper() if len(sys.argv) > 1 else "EURUSD"

mlflow.set_tracking_uri("mlruns")
client = mlflow.tracking.MlflowClient()

# Find TRAIN and TEST runs
train_params = None
test_run_id = None
for exp in client.search_experiments():
    if "FX" in exp.name:
        for r in client.search_runs(exp.experiment_id):
            name = r.data.tags.get("mlflow.runName", "")
            if name == f"{ticker}_TRAIN_seq":
                train_params = r.data.params
            elif name == f"{ticker}_TEST_seq":
                test_run_id = r.info.run_id

if train_params is None:
    print(f"ERROR: No se encontro {ticker}_TRAIN_seq en MLflow")
    sys.exit(1)

p = train_params
atr_mult = float(p["atr_mult"])

seq_params = {
    "method": p["seq_method"],
    "min_contractions": int(p["seq_min_contractions"]),
    "max_contractions": int(p["seq_max_contractions"]),
    "lookback_bars": int(p["seq_lookback_bars"]),
    "tolerance": float(p["seq_tolerance"]),
    "max_depth_pct": float(p["seq_max_depth_pct"]),
    "max_depth_atr": float(p["seq_max_depth_atr"]),
    "min_total_reduction": float(p["seq_min_total_reduction"]),
    "max_gap_between_contractions_days": None,
    "require_ascending_lows": str(p["seq_require_ascending_lows"]).lower() == "true",
    "ascending_lows_tolerance": float(p["seq_ascending_lows_tolerance"]),
}

risk_params = {}
for k, v in p.items():
    if k.startswith("risk_"):
        key = k[5:]
        if v == "None":
            risk_params[key] = None
        elif v in ("True", "true"):
            risk_params[key] = True
        elif v in ("False", "false"):
            risk_params[key] = False
        else:
            try:
                risk_params[key] = int(v)
            except ValueError:
                try:
                    risk_params[key] = float(v)
                except ValueError:
                    risk_params[key] = v

print(f"Ticker: {ticker}")
print(f"atr_mult={atr_mult}, lookback={seq_params['lookback_bars']}, "
      f"depth_atr={seq_params['max_depth_atr']}, reduction={seq_params['min_total_reduction']}")

# Load and split data
daily = pd.read_csv(DATA_DIR / f"{ticker}.csv", parse_dates=["date"], index_col="date")
test = daily.loc[CUTOFF:]

# Detect signals on TEST split
config = ATRZigZagConfig(atr_length=14, atr_mult=atr_mult, use_close_only=False)
detector = ATRZigZagDetector(config)
swings = detector.detect(test)
contractions = compute_contractions(swings, test)
atr = compute_atr(test, COMPRESSION["atr_period"])

res = run_full_vcp_pipeline(
    ohlc=test, swing_detector=detector,
    sequence_params=seq_params, compression_params=COMPRESSION,
    breakout_params=BREAKOUT, volume_contraction_params=None,
    precomputed_swings=swings, precomputed_contractions=contractions,
    precomputed_atr=atr,
)
signals = {dt: s for dt, s in res.items() if s is not None}
print(f"Senales en TEST: {len(signals)}")

# Evaluate each signal individually
win_pnls, loss_pnls = [], []
for dt in sorted(signals.keys()):
    pat = group_signals_into_patterns(
        {dt: signals[dt]}, risk_params=risk_params, max_gap_days=0,
    )
    if not pat:
        continue
    trade = simulate_trade(test, pat[0], risk_params)
    pnl = trade["pnl_pct"] * 100
    if pnl >= 0:
        win_pnls.append(pnl)
    else:
        loss_pnls.append(pnl)

total = len(win_pnls) + len(loss_pnls)
avg_w = np.mean(win_pnls) if win_pnls else 0
avg_l = np.mean(loss_pnls) if loss_pnls else 0
ratio = abs(avg_w / avg_l) if avg_l != 0 else float("inf")

print(f"Evaluadas: {total} | Wins: {len(win_pnls)} ({len(win_pnls)/total*100:.1f}%) "
      f"| Losses: {len(loss_pnls)} ({len(loss_pnls)/total*100:.1f}%)")
print(f"Avg win: +{avg_w:.2f}% | Avg loss: {avg_l:.2f}% | Ratio: {ratio:.1f}x")

# Plot histogram
fig, ax = plt.subplots(figsize=(10, 5.5))

all_pnls = win_pnls + loss_pnls
lo = min(all_pnls) - 0.3
hi = max(all_pnls) + 0.3
bins = np.arange(lo, hi + 0.25, 0.25)

ax.hist(win_pnls, bins=bins, color="#2ecc71", edgecolor="white", linewidth=0.8,
        alpha=0.85, label=f"Wins ({len(win_pnls)})")
ax.hist(loss_pnls, bins=bins, color="#e74c3c", edgecolor="white", linewidth=0.8,
        alpha=0.85, label=f"Losses ({len(loss_pnls)})")

ax.axvline(x=0, color="#7f8c8d", linestyle="--", linewidth=1, alpha=0.7)
ax.axvline(x=avg_w, color="#27ae60", linestyle="--", linewidth=1.8,
           label=f"Avg win: +{avg_w:.2f}%")
ax.axvline(x=avg_l, color="#c0392b", linestyle="--", linewidth=1.8,
           label=f"Avg loss: {avg_l:.2f}%")

textstr = f"n={total}  |  WR={len(win_pnls)/total*100:.0f}%  |  Ratio={ratio:.1f}x"
ax.text(0.98, 0.95, textstr, transform=ax.transAxes, fontsize=11,
        verticalalignment="top", horizontalalignment="right",
        bbox=dict(boxstyle="round,pad=0.4", facecolor="white",
                  edgecolor="#bdc3c7", alpha=0.9))

ax.set_xlabel("PnL por senal (%)", fontsize=12)
ax.set_ylabel("Frecuencia", fontsize=12)
ax.set_title(f"{ticker} — Distribucion de PnL por senal (TEST 2020-2026)",
             fontsize=14, fontweight="bold")
ax.legend(fontsize=11, loc="upper left")
ax.grid(axis="y", alpha=0.3)
ax.set_yticks(range(0, int(ax.get_ylim()[1]) + 2))

plt.tight_layout()
out_path = f"/tmp/{ticker.lower()}_signal_histogram.png"
plt.savefig(out_path, dpi=150)
print(f"Saved: {out_path}")

# Log to MLflow
if test_run_id:
    client.log_artifact(test_run_id, out_path)
    print(f"Logged to {ticker}_TEST_seq")
