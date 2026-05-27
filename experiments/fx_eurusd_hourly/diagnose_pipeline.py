"""Diagnose why atr_mult=5 produces 61 contractions but 0 VCP signals.

Traces each step of the pipeline with the most permissive config and counts
how many evaluation dates pass each filter.
"""
import functools
import sys
from pathlib import Path

print = functools.partial(print, flush=True)

import pandas as pd
import numpy as np

project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from models.configs import ATRZigZagConfig
from vcp_detection.heuristic import ATRZigZagDetector
from vcp_detection.heuristic.contractions import compute_contractions
from vcp_detection.heuristic.atr_compression import compute_atr, verify_atr_compression
from vcp_detection.heuristic.decreasing_sequence import detect_decreasing_sequence
from vcp_detection.heuristic.pivot_breakout import identify_pivot

# ── Load data ────────────────────────────────────────────────
DATA_DIR = project_root / "data" / "monedas_hora"
ohlc = pd.read_csv(DATA_DIR / "EURUSD.csv", parse_dates=["date"], index_col="date")
train = ohlc["2018-01-01":"2019-01-01"]
print(f"TRAIN bars: {len(train)}")

# ── Precompute with atr_mult=5 ──────────────────────────────
ATR_MULT = 5
config = ATRZigZagConfig(atr_length=14, atr_mult=ATR_MULT, use_close_only=False)
detector = ATRZigZagDetector(config)
swings = detector.detect(train)
contractions = compute_contractions(swings, train)
atr = compute_atr(train, 14)

print(f"\natr_mult={ATR_MULT}")
print(f"Swings: {len(swings)}")
print(f"Contractions: {len(contractions)}")

# Show contraction details
print(f"\n{'='*80}")
print("CONTRACCIONES DETECTADAS:")
print(f"{'='*80}")
for i, c in enumerate(contractions):
    datr = f"{c.depth_atr:.2f}" if c.depth_atr is not None else "N/A"
    print(f"  [{i}] high={c.high_swing.date} @ {c.high_swing.price:.5f}  ->  "
          f"low={c.low_swing.date} @ {c.low_swing.price:.5f}  |  "
          f"depth={c.depth_pct:.4f}%  depth_atr={datr}")

# ── Most permissive sequence params ─────────────────────────
seq_params = {
    "method": "tolerance",
    "min_contractions": 2,
    "max_contractions": 6,
    "lookback_bars": 960,       # 40 days - widest window
    "tolerance": 0.20,          # most permissive
    "max_depth_pct": 0.50,      # very permissive
    "max_depth_atr": None,      # DISABLED
    "min_total_reduction": 0.80, # most permissive
    "max_gap_between_contractions_days": None,
    "require_ascending_lows": False,  # disabled
    "ascending_lows_tolerance": 0.03,
}

compression_params_list = [0.85, 0.90, 0.95, 1.00, 1.10, 1.50]

# ── Trace pipeline step by step ─────────────────────────────
print(f"\n{'='*80}")
print("PIPELINE DIAGNOSIS — step by step")
print(f"{'='*80}")

dates = train.index
n_seq_found = 0
n_atr_pass = {t: 0 for t in compression_params_list}
n_breakout = 0
seq_examples = []
atr_fail_examples = []
breakout_fail_examples = []

for dt in dates:
    seq = detect_decreasing_sequence(
        contractions,
        evaluation_date=dt,
        ohlc_index=train.index,
        **seq_params,
    )
    if seq is None:
        continue

    n_seq_found += 1
    if len(seq_examples) < 5:
        seq_examples.append((dt, seq))

    for threshold in compression_params_list:
        try:
            atr_result = verify_atr_compression(
                seq, train,
                method="ratio",
                atr_period=14,
                ratio_threshold=threshold,
                precomputed_atr=atr,
            )
            if atr_result.passes:
                n_atr_pass[threshold] += 1

                if threshold == 0.95 and len(atr_fail_examples) < 3:
                    atr_fail_examples.append((dt, seq, atr_result))
        except ValueError:
            pass

    # Check breakout with most permissive compression (threshold=1.5, always passes)
    try:
        atr_result = verify_atr_compression(
            seq, train,
            method="ratio",
            atr_period=14,
            ratio_threshold=1.50,
            precomputed_atr=atr,
        )
    except ValueError:
        continue

    if atr_result.passes:
        pivot = identify_pivot(seq)
        close = float(train.loc[dt, "close"])
        if close > pivot.price:
            n_breakout += 1
            if len(breakout_fail_examples) < 3:
                breakout_fail_examples.append((dt, seq, pivot, close))

# ── Report ───────────────────────────────────────────────────
print(f"\nStep 1 — Contracciones: {len(contractions)}")
print(f"Step 2 — Fechas con secuencia decreciente valida: {n_seq_found} / {len(dates)}")

print(f"\nStep 3 — ATR compression (ratio method, atr_end/atr_start <= threshold):")
for threshold in compression_params_list:
    pct = 100 * n_atr_pass[threshold] / max(n_seq_found, 1)
    print(f"  threshold={threshold:.2f}: {n_atr_pass[threshold]:>5} pass ({pct:.1f}%)")

print(f"\nStep 4 — Breakout (close > pivot, ignoring ATR filter): {n_breakout}")

# ── Show sequence examples ──────────────────────────────────
print(f"\n{'='*80}")
print("EJEMPLO SECUENCIAS ENCONTRADAS (primeras 5):")
print(f"{'='*80}")
for dt, seq in seq_examples:
    print(f"\n  Fecha evaluacion: {dt}")
    print(f"  Contracciones: {seq.n_contractions}")
    print(f"  Depths: {[f'{d:.4f}%' for d in seq.depths_pct]}")
    for c in seq.contractions:
        print(f"    high={c.high_swing.date} @ {c.high_swing.price:.5f} -> "
              f"low={c.low_swing.date} @ {c.low_swing.price:.5f} "
              f"depth={c.depth_pct:.4f}%")

    # Show ATR compression details
    try:
        atr_result = verify_atr_compression(
            seq, train, method="ratio", atr_period=14,
            ratio_threshold=0.95, precomputed_atr=atr,
        )
        print(f"  ATR: start={atr_result.atr_start:.6f} end={atr_result.atr_end:.6f} "
              f"ratio={atr_result.atr_end/atr_result.atr_start:.4f} "
              f"passes@0.95={atr_result.passes}")
    except ValueError as e:
        print(f"  ATR: error — {e}")

    pivot = identify_pivot(seq)
    close = float(train.loc[dt, "close"])
    print(f"  Pivot: {pivot.price:.5f}  Close: {close:.5f}  "
          f"Breakout={'YES' if close > pivot.price else 'NO'}")

# ── ATR ratio distribution for sequences that exist ─────────
print(f"\n{'='*80}")
print("DISTRIBUCION ATR RATIO (atr_end/atr_start) para secuencias encontradas:")
print(f"{'='*80}")
atr_ratios = []
for dt in dates:
    seq = detect_decreasing_sequence(
        contractions, evaluation_date=dt, ohlc_index=train.index, **seq_params,
    )
    if seq is None:
        continue
    try:
        atr_result = verify_atr_compression(
            seq, train, method="ratio", atr_period=14,
            ratio_threshold=99.0, precomputed_atr=atr,
        )
        atr_ratios.append(atr_result.atr_end / atr_result.atr_start)
    except ValueError:
        pass

if atr_ratios:
    arr = np.array(atr_ratios)
    print(f"  N: {len(arr)}")
    print(f"  Min: {arr.min():.4f}")
    print(f"  P25: {np.percentile(arr, 25):.4f}")
    print(f"  Median: {np.median(arr):.4f}")
    print(f"  P75: {np.percentile(arr, 75):.4f}")
    print(f"  Max: {arr.max():.4f}")
    print(f"  % <= 0.85: {100*np.mean(arr <= 0.85):.1f}%")
    print(f"  % <= 0.90: {100*np.mean(arr <= 0.90):.1f}%")
    print(f"  % <= 0.95: {100*np.mean(arr <= 0.95):.1f}%")
    print(f"  % <= 1.00: {100*np.mean(arr <= 1.00):.1f}%")
else:
    print("  No ATR ratios computed (0 sequences)")

# ── Analyze WHY no decreasing sequences form ────────────────
print(f"\n{'='*80}")
print("ANALISIS: POR QUE NO HAY SECUENCIAS DECRECIENTES")
print(f"{'='*80}")

depths = [c.depth_pct for c in contractions]
print(f"\nDepths de las 61 contracciones (en %):")
for i, d in enumerate(depths):
    print(f"  [{i:2d}] {d:.4f}%", end="")
    if i > 0:
        ratio = d / depths[i-1]
        direction = "↓" if d < depths[i-1] else "↑"
        print(f"  {direction} (ratio vs prev: {ratio:.2f})", end="")
    print()

# Check consecutive pairs
print(f"\nPares consecutivos decrecientes (depth[i+1] < depth[i]):")
n_decreasing = 0
n_increasing = 0
for i in range(len(depths)-1):
    if depths[i+1] < depths[i]:
        n_decreasing += 1
    else:
        n_increasing += 1
print(f"  Decrecientes: {n_decreasing}")
print(f"  Crecientes/iguales: {n_increasing}")

# Check with tolerance
print(f"\nPares consecutivos decrecientes con tolerance=0.20:")
n_dec_tol = 0
for i in range(len(depths)-1):
    if depths[i+1] <= depths[i] * (1 + 0.20):
        n_dec_tol += 1
print(f"  Pasan: {n_dec_tol} / {len(depths)-1}")

# Check all possible pairs of 2 consecutive contractions within lookback
print(f"\nBuscando pares de 2+ contracciones consecutivas con depths decrecientes (tolerance=0.20):")
runs = []
current_run = [0]
for i in range(1, len(contractions)):
    if contractions[i].depth_pct <= contractions[i-1].depth_pct * (1 + 0.20):
        current_run.append(i)
    else:
        if len(current_run) >= 2:
            runs.append(current_run[:])
        current_run = [i]
if len(current_run) >= 2:
    runs.append(current_run[:])

print(f"  Runs encontrados: {len(runs)}")
for run in runs:
    print(f"    Indices: {run}")
    for idx in run:
        c = contractions[idx]
        print(f"      [{idx}] depth={c.depth_pct:.4f}% | "
              f"high={c.high_swing.date} low={c.low_swing.date}")

# Also check: max_depth_atr filter
print(f"\nFiltro max_depth_atr=4: cuantas contracciones pasan?")
datr_vals = [c.depth_atr for c in contractions if c.depth_atr is not None]
n_pass_4 = sum(1 for d in datr_vals if d <= 4)
n_pass_10 = sum(1 for d in datr_vals if d <= 10)
n_pass_20 = sum(1 for d in datr_vals if d <= 20)
print(f"  depth_atr <= 4:  {n_pass_4} / {len(datr_vals)}")
print(f"  depth_atr <= 10: {n_pass_10} / {len(datr_vals)}")
print(f"  depth_atr <= 20: {n_pass_20} / {len(datr_vals)}")
print(f"  depth_atr values: min={min(datr_vals):.2f} median={np.median(datr_vals):.2f} max={max(datr_vals):.2f}")
