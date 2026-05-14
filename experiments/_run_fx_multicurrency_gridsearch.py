"""Multi-currency grid search: find best VCP params per currency on TRAIN (2015-2019),
compare across currencies, and validate out-of-sample on TEST (2020-2026)."""
import sys
import time
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import numpy as np
import pandas as pd

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from models.configs import ATRZigZagConfig
from vcp_detection.heuristic import ATRZigZagDetector, run_full_vcp_pipeline
from vcp_detection.heuristic.contractions import compute_contractions
from vcp_detection.heuristic.atr_compression import compute_atr
from vcp_detection.analysis import group_signals_into_patterns, simulate_trade

pd.set_option("display.float_format", "{:.4f}".format)

# ── Constants ─────────────────────────────────────────────────

TICKERS = ["EURUSD", "GBPUSD", "USDJPY", "USDCNH", "USDCNY"]
CUTOFF = "2020-01-01"

DEPTH_ATRS = [2, 3, 4, 5, 6]
REDUCTIONS = [0.40, 0.50, 0.60, 0.70, 0.80]

TRAILING_MULTS = [1.0, 1.5, 2.0, 2.5, 3.0]
TARGET_RS = [None, 2.0, 3.0, 5.0]
EARLY_EXITS = [None, 3, 5]
BREAKEVEN_RS = [0.5, 1.0, 1.5, 2.0]

# atr_mult fijo en 1.5 (confirmado por experimento de estabilidad temporal)
ATR_MULT = 1.5

COMPRESSION = {"method": "ratio", "atr_period": 14, "ratio_threshold": 0.85}
BREAKOUT = {
    "volume_method": "ratio", "volume_ratio_threshold": 1.5,
    "volume_lookback_days": 50,
    "require_volume_confirmation": False,
    "max_entry_distance_pct": 0.03,
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

EURUSD_BEST = {
    "detection": {"max_depth_atr": 5, "min_total_reduction": 0.60},
    "exit": {"trailing_atr_multiplier": 1.5, "target_r_multiple": 3.0,
             "early_exit_days": None, "breakeven_r_multiple": 1.0},
}

# ── Helper functions ──────────────────────────────────────────

def load_ticker(ticker):
    return pd.read_csv(
        project_root / "data" / "monedas" / f"{ticker}.csv",
        parse_dates=["date"], index_col="date",
    )


def precompute(ohlc):
    config = ATRZigZagConfig(atr_length=14, atr_mult=ATR_MULT, use_close_only=False)
    detector = ATRZigZagDetector(config)
    swings = detector.detect(ohlc)
    contractions = compute_contractions(swings, ohlc)
    atr = compute_atr(ohlc, COMPRESSION["atr_period"])
    return {"ohlc": ohlc, "swings": swings, "contractions": contractions,
            "atr": atr, "detector": detector}


def make_seq(depth_atr, reduction):
    return {
        "method": "tolerance", "min_contractions": 2, "max_contractions": 6,
        "lookback_bars": 126, "tolerance": 0.10,
        "max_depth_pct": 0.50, "max_depth_atr": depth_atr,
        "min_total_reduction": reduction,
        "max_gap_between_contractions_days": None,
        "require_ascending_lows": True, "ascending_lows_tolerance": 0.03,
    }


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


def evaluate(ohlc, signals, risk):
    patterns = group_signals_into_patterns(signals, risk_params=risk)
    trades = [simulate_trade(ohlc, p, risk) for p in patterns]
    n = len(trades)
    wins = sum(1 for t in trades if t["pnl_pct"] > 0) if n else 0
    cr = float(np.prod([1 + t["pnl_pct"] for t in trades]) - 1) if n else 0
    avg_r = float(np.mean([t["r_multiple"] for t in trades])) if n else 0
    reasons = {}
    for t in trades:
        reasons[t["exit_reason"]] = reasons.get(t["exit_reason"], 0) + 1
    return {"trades": n, "wins": wins, "WR": wins / n if n > 0 else 0,
            "CR": cr, "avg_R": avg_r, "reasons": reasons,
            "trade_list": list(zip(patterns, trades))}


def fmt_pct(x): return f"{x:+.2%}"
def fmt_wr(x): return f"{x:.0%}"


# ══════════════════════════════════════════════════════════════
#  LOAD DATA
# ══════════════════════════════════════════════════════════════

print("Cargando datos...")
data = {}
for ticker in TICKERS:
    full = load_ticker(ticker)
    tr = full[full.index < CUTOFF]
    te = full[full.index >= CUTOFF]
    data[ticker] = {"full": full, "train": tr, "test": te}
    print(f"  {ticker}: {len(full):,} barras ({full.index.min().date()} - {full.index.max().date()}), "
          f"train={len(tr):,}, test={len(te):,}")

n_det = len(DEPTH_ATRS) * len(REDUCTIONS)
n_exit = len(TRAILING_MULTS) * len(TARGET_RS) * len(EARLY_EXITS) * len(BREAKEVEN_RS)
print(f"\nPor moneda: {n_det} configs deteccion + {n_exit} configs salida")


# ══════════════════════════════════════════════════════════════
#  PER-CURRENCY GRID SEARCH ON TRAIN
# ══════════════════════════════════════════════════════════════

fixed_risk = {**RISK_BASE, "trailing_atr_multiplier": 1.5, "target_r_multiple": 3.0,
              "early_exit_days": None, "breakeven_r_multiple": 1.0}

currency_results = {}

for ticker in TICKERS:
    print(f"\n{'='*70}")
    print(f"  {ticker}")
    print(f"{'='*70}")

    ohlc_train = data[ticker]["train"]
    t0 = time.time()
    cache_train = precompute(ohlc_train)
    print(f"  Precompute: {len(cache_train['swings'])} swings, "
          f"{len(cache_train['contractions'])} contracciones ({time.time()-t0:.1f}s)")

    # ── Phase 1: detection grid ──
    det_results = []
    for depth_atr in DEPTH_ATRS:
        for reduction in REDUCTIONS:
            seq = make_seq(depth_atr, reduction)
            signals = detect_signals(ohlc_train, seq, cache_train)
            ev = evaluate(ohlc_train, signals, fixed_risk)
            det_results.append({
                "depth_atr": depth_atr, "reduction": reduction,
                "signals": len(signals), **{k: ev[k] for k in ["trades", "wins", "WR", "CR", "avg_R"]},
            })

    det_df = pd.DataFrame(det_results).sort_values("CR", ascending=False)
    has_trades = det_df[det_df["trades"] > 0]
    print(f"  Grilla deteccion: {len(has_trades)}/{len(det_df)} configs con trades")

    if len(has_trades) > 0:
        print(f"  Top 5:")
        for _, row in det_df.head(5).iterrows():
            print(f"    depth_atr={int(row['depth_atr'])}, red={row['reduction']:.2f} "
                  f"-> {int(row['signals'])} sen, {int(row['trades'])}T, "
                  f"WR={fmt_wr(row['WR'])}, CR={fmt_pct(row['CR'])}")
    else:
        print(f"  (!) Ninguna config genero trades rentables en TRAIN")

    best_det = det_df.iloc[0]
    best_depth_atr = int(best_det["depth_atr"])
    best_reduction = best_det["reduction"]

    # ── Phase 2: exit grid ──
    best_seq = make_seq(best_depth_atr, best_reduction)
    signals_train = detect_signals(ohlc_train, best_seq, cache_train)

    exit_results = []
    for trail in TRAILING_MULTS:
        for target in TARGET_RS:
            for early in EARLY_EXITS:
                for be_r in BREAKEVEN_RS:
                    risk = {**RISK_BASE, "trailing_atr_multiplier": trail,
                            "target_r_multiple": target, "early_exit_days": early,
                            "breakeven_r_multiple": be_r}
                    ev = evaluate(ohlc_train, signals_train, risk)
                    exit_results.append({
                        "trailing_atr_multiplier": trail, "target_r_multiple": target,
                        "early_exit_days": early, "breakeven_r_multiple": be_r,
                        **{k: ev[k] for k in ["trades", "wins", "WR", "CR", "avg_R"]},
                    })

    exit_df = pd.DataFrame(exit_results).sort_values("CR", ascending=False)
    best_exit_row = exit_df.iloc[0]
    best_exit = {
        "trailing_atr_multiplier": best_exit_row["trailing_atr_multiplier"],
        "target_r_multiple": best_exit_row["target_r_multiple"] if pd.notna(best_exit_row["target_r_multiple"]) else None,
        "early_exit_days": int(best_exit_row["early_exit_days"]) if pd.notna(best_exit_row["early_exit_days"]) else None,
        "breakeven_r_multiple": best_exit_row["breakeven_r_multiple"],
    }

    elapsed = time.time() - t0
    print(f"\n  MEJOR CONFIG TRAIN ({elapsed:.1f}s):")
    print(f"    Deteccion: depth_atr={best_depth_atr}, reduction={best_reduction}")
    print(f"    Salida:    trail={best_exit['trailing_atr_multiplier']}, "
          f"target={best_exit['target_r_multiple']}, "
          f"early={best_exit['early_exit_days']}, "
          f"be_R={best_exit['breakeven_r_multiple']}")
    print(f"    TRAIN:     {int(best_exit_row['trades'])}T, "
          f"WR={fmt_wr(best_exit_row['WR'])}, CR={fmt_pct(best_exit_row['CR'])}")

    currency_results[ticker] = {
        "det_df": det_df,
        "exit_df": exit_df,
        "best_detection": {"depth_atr": best_depth_atr, "reduction": best_reduction},
        "best_exit": best_exit,
        "train_cr": best_exit_row["CR"],
        "train_trades": int(best_exit_row["trades"]),
        "train_wr": best_exit_row["WR"],
    }


# ══════════════════════════════════════════════════════════════
#  CROSS-CURRENCY COMPARISON
# ══════════════════════════════════════════════════════════════

print("\n\n" + "="*70)
print("  COMPARACION DE PARAMETROS ENTRE MONEDAS")
print("="*70)

print(f"\n  {'Ticker':<8s} | {'depth_atr':>9s} | {'reduction':>9s} | {'trail':>5s} | {'target':>6s} | "
      f"{'early':>5s} | {'be_R':>5s} | {'Train T':>7s} | {'Train WR':>8s} | {'Train CR':>8s}")
print(f"  {'─'*100}")

for ticker in TICKERS:
    r = currency_results[ticker]
    d = r["best_detection"]
    e = r["best_exit"]
    print(f"  {ticker:<8s} | {d['depth_atr']:>9d} | {d['reduction']:>9.2f} | "
          f"{e['trailing_atr_multiplier']:>5.1f} | {str(e['target_r_multiple']):>6s} | "
          f"{str(e['early_exit_days']):>5s} | {e['breakeven_r_multiple']:>5.1f} | "
          f"{r['train_trades']:>7d} | {fmt_wr(r['train_wr']):>8s} | {fmt_pct(r['train_cr']):>8s}")

# Check parameter stability
print("\n  Parametros mas comunes (moda):")
det_params = [(r["best_detection"]["depth_atr"], r["best_detection"]["reduction"]) for r in currency_results.values()]
exit_params = [(r["best_exit"]["trailing_atr_multiplier"], r["best_exit"]["early_exit_days"]) for r in currency_results.values()]

from collections import Counter
depth_atrs = Counter(d for d, _ in det_params)
reductions = Counter(r for _, r in det_params)
trails = Counter(t for t, _ in exit_params)
earlies = Counter(e for _, e in exit_params)

print(f"    depth_atr:  {depth_atrs.most_common()}")
print(f"    reduction:  {reductions.most_common()}")
print(f"    trail:      {trails.most_common()}")
print(f"    early_exit: {earlies.most_common()}")


# ══════════════════════════════════════════════════════════════
#  OUT-OF-SAMPLE: per-currency best AND EURUSD-best on all currencies
# ══════════════════════════════════════════════════════════════

print("\n\n" + "="*70)
print("  OUT-OF-SAMPLE: TEST (2020-2026)")
print("="*70)

print(f"\n  A) Cada moneda con sus propios mejores parametros (optimizados en TRAIN):")
print(f"  {'Ticker':<8s} | {'Split':<8s} | {'Sen':>5s} | {'Trades':>6s} | {'WR':>5s} | {'CR':>8s} | {'AvgR':>6s} | Salidas")
print(f"  {'─'*90}")

for ticker in TICKERS:
    r = currency_results[ticker]
    seq = make_seq(r["best_detection"]["depth_atr"], r["best_detection"]["reduction"])
    risk = {**RISK_BASE, **r["best_exit"]}

    for split_name, split_key in [("TRAIN", "train"), ("TEST", "test"), ("FULL", "full")]:
        ohlc = data[ticker][split_key]
        cache = precompute(ohlc)
        signals = detect_signals(ohlc, seq, cache)
        ev = evaluate(ohlc, signals, risk)
        reasons_str = ", ".join(f"{k}={v}" for k, v in sorted(ev["reasons"].items())) if ev["reasons"] else "-"
        print(f"  {ticker:<8s} | {split_name:<8s} | {len(signals):>5d} | {ev['trades']:>6d} | "
              f"{fmt_wr(ev['WR']):>5s} | {fmt_pct(ev['CR']):>8s} | {ev['avg_R']:>+6.2f} | {reasons_str}")
    print()

print(f"\n  B) Todas las monedas con params de EURUSD (depth_atr=5, red=0.60, trail=1.5, target=3R):")
print(f"  {'Ticker':<8s} | {'Split':<8s} | {'Sen':>5s} | {'Trades':>6s} | {'WR':>5s} | {'CR':>8s} | {'AvgR':>6s} | Salidas")
print(f"  {'─'*90}")

seq_eur = make_seq(EURUSD_BEST["detection"]["max_depth_atr"],
                   EURUSD_BEST["detection"]["min_total_reduction"])
risk_eur = {**RISK_BASE, **EURUSD_BEST["exit"]}

for ticker in TICKERS:
    for split_name, split_key in [("TRAIN", "train"), ("TEST", "test"), ("FULL", "full")]:
        ohlc = data[ticker][split_key]
        cache = precompute(ohlc)
        signals = detect_signals(ohlc, seq_eur, cache)
        ev = evaluate(ohlc, signals, risk_eur)
        reasons_str = ", ".join(f"{k}={v}" for k, v in sorted(ev["reasons"].items())) if ev["reasons"] else "-"
        print(f"  {ticker:<8s} | {split_name:<8s} | {len(signals):>5d} | {ev['trades']:>6d} | "
              f"{fmt_wr(ev['WR']):>5s} | {fmt_pct(ev['CR']):>8s} | {ev['avg_R']:>+6.2f} | {reasons_str}")
    print()


# ══════════════════════════════════════════════════════════════
#  TRADE DETAILS PER CURRENCY (per-currency best, TEST split)
# ══════════════════════════════════════════════════════════════

print("\n" + "="*70)
print("  DETALLE DE TRADES EN TEST (2020-2026)")
print("="*70)

for ticker in TICKERS:
    r = currency_results[ticker]
    seq = make_seq(r["best_detection"]["depth_atr"], r["best_detection"]["reduction"])
    risk = {**RISK_BASE, **r["best_exit"]}
    ohlc = data[ticker]["test"]
    cache = precompute(ohlc)
    signals = detect_signals(ohlc, seq, cache)
    ev = evaluate(ohlc, signals, risk)

    print(f"\n  {ticker} (depth_atr={r['best_detection']['depth_atr']}, "
          f"red={r['best_detection']['reduction']}, "
          f"trail={r['best_exit']['trailing_atr_multiplier']}, "
          f"target={r['best_exit']['target_r_multiple']}, "
          f"early={r['best_exit']['early_exit_days']}):")

    if not ev["trade_list"]:
        print("    (sin trades en TEST)")
        continue
    for i, (pat, trade) in enumerate(ev["trade_list"], 1):
        entry_str = pat["first_signal_date"].strftime("%Y-%m-%d") if hasattr(pat["first_signal_date"], "strftime") else str(pat["first_signal_date"])
        exit_str = trade["exit_date"].strftime("%Y-%m-%d") if hasattr(trade["exit_date"], "strftime") else str(trade["exit_date"])
        print(f"    Trade {i}: {entry_str} -> {exit_str} | {trade['exit_reason']:<15s} | "
              f"PnL={trade['pnl_pct']:+.2%} | R={trade['r_multiple']:+.1f}R | "
              f"Dur={trade.get('duration_days', '?')}d")


# ══════════════════════════════════════════════════════════════
#  SUMMARY TABLE
# ══════════════════════════════════════════════════════════════

print("\n\n" + "="*70)
print("  RESUMEN FINAL: PARAMS POR MONEDA vs PARAMS EURUSD")
print("="*70)

print(f"\n  {'Ticker':<8s} | {'Config':<18s} | {'Train CR':>8s} | {'Test CR':>8s} | {'Full CR':>8s} | "
      f"{'Test T':>6s} | {'Test WR':>7s}")
print(f"  {'─'*85}")

for ticker in TICKERS:
    r = currency_results[ticker]

    # Per-currency best
    seq_own = make_seq(r["best_detection"]["depth_atr"], r["best_detection"]["reduction"])
    risk_own = {**RISK_BASE, **r["best_exit"]}
    crs_own = {}
    for split_key in ["train", "test", "full"]:
        ohlc = data[ticker][split_key]
        cache = precompute(ohlc)
        signals = detect_signals(ohlc, seq_own, cache)
        ev = evaluate(ohlc, signals, risk_own)
        crs_own[split_key] = ev

    # EURUSD params
    crs_eur = {}
    for split_key in ["train", "test", "full"]:
        ohlc = data[ticker][split_key]
        cache = precompute(ohlc)
        signals = detect_signals(ohlc, seq_eur, cache)
        ev = evaluate(ohlc, signals, risk_eur)
        crs_eur[split_key] = ev

    print(f"  {ticker:<8s} | {'Propios (train)':<18s} | {fmt_pct(crs_own['train']['CR']):>8s} | "
          f"{fmt_pct(crs_own['test']['CR']):>8s} | {fmt_pct(crs_own['full']['CR']):>8s} | "
          f"{crs_own['test']['trades']:>6d} | {fmt_wr(crs_own['test']['WR']):>7s}")
    print(f"  {'':8s} | {'EURUSD params':<18s} | {fmt_pct(crs_eur['train']['CR']):>8s} | "
          f"{fmt_pct(crs_eur['test']['CR']):>8s} | {fmt_pct(crs_eur['full']['CR']):>8s} | "
          f"{crs_eur['test']['trades']:>6d} | {fmt_wr(crs_eur['test']['WR']):>7s}")
    print()

print("Completo!")
