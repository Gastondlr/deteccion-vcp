"""Re-run Phase 2 from saved Phase 1 CSV with fixed deduplication.

Usage:
    python3 rerun_phase2.py AAPL
"""
import argparse
import functools
import itertools
import sys
import time
from pathlib import Path

print = functools.partial(print, flush=True)

import matplotlib
matplotlib.use("Agg")
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

pd.set_option("display.float_format", "{:.4f}".format)

DATA_DIR = project_root / "data" / "csv"
OUTPUT_DIR = Path(__file__).resolve().parent / "results"

TRAILING_MULTS = [1.0, 1.5, 2.0, 2.5, 3.0]
TARGET_RS = [None, 2.0, 3.0, 5.0]
EARLY_EXITS = [None, 3, 5]
BREAKEVEN_RS = [0.5, 1.0, 1.5, 2.0]
MAX_STOP_LOSSES = [0.03, 0.05, 0.07]

RISK_BASE = {
    "trailing_sma_period": 20,
    "trailing_volume_factor": 1.5,
    "trailing_stop_method": "atr",
    "trailing_atr_period": 14,
    "max_bars_without_progress": 15,
    "min_progress_r": 0.5,
}

BREAKOUT_BASE = {
    "volume_method": "ratio", "volume_ratio_threshold": 1.5,
    "volume_lookback_days": 50,
    "require_volume_confirmation": False,
}

VOLUME_FILTER_VARIANTS = [
    {"name": "no_filter", "window": None, "threshold": None},
    {"name": "w1_t1.2", "window": 1, "threshold": 1.2},
    {"name": "w1_t1.5", "window": 1, "threshold": 1.5},
    {"name": "w3_t1.2", "window": 3, "threshold": 1.2},
    {"name": "w3_t1.5", "window": 3, "threshold": 1.5},
    {"name": "w5_t1.2", "window": 5, "threshold": 1.2},
    {"name": "w5_t1.5", "window": 5, "threshold": 1.5},
]

CONFIG_COLS = [
    "atr_mult", "use_close_only", "max_depth_atr", "reduction",
    "lookback_bars", "tolerance", "max_depth_pct", "asc_lows_tol",
    "comp_thresh", "vol_contraction", "trend_template", "vol_filter",
]
RESULT_COLS = ["signals", "avg_trades", "avg_WR", "avg_CR", "avg_R"]

n_exit = len(TRAILING_MULTS) * len(TARGET_RS) * len(EARLY_EXITS) * len(BREAKEVEN_RS) * len(MAX_STOP_LOSSES)


def fmt_pct(x):
    return f"{x:+.2%}"


def fmt_wr(x):
    return f"{x:.0%}"


def evaluate_signals_seq(ohlc, signals, risk, precomputed_atr=None):
    results = evaluate_signals_to_trades(
        signals, ohlc, risk, grouping="sequential",
        precomputed_atr=precomputed_atr,
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


def apply_volume_post_filter(signals, ohlc, window, threshold, lookback_days=50):
    filtered = {}
    for dt, sig in signals.items():
        eval_loc = ohlc.index.get_loc(dt)
        lookback_start = max(0, eval_loc - lookback_days)
        vol_recent = ohlc["volume"].iloc[lookback_start:eval_loc]
        vol_avg = float(vol_recent.mean()) if len(vol_recent) > 0 else 0.0
        if vol_avg <= 0:
            continue
        win_start = max(0, eval_loc - window + 1)
        win_vols = ohlc["volume"].iloc[win_start:eval_loc + 1]
        if any(float(v) >= threshold * vol_avg for v in win_vols):
            filtered[dt] = sig
    return filtered


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("ticker", help="Ticker to process")
    parser.add_argument("--train-cutoff", default="2020-01-01")
    parser.add_argument("--top-n", type=int, default=10)
    parser.add_argument("--min-trades", type=int, default=3)
    args = parser.parse_args()

    ticker = args.ticker.upper()
    top_n = args.top_n
    min_trades = args.min_trades

    csv_path = OUTPUT_DIR / f"{ticker.lower()}_phase1_detection.csv"
    print(f"Cargando Fase 1 desde {csv_path}...")
    det_df = pd.read_csv(csv_path)
    print(f"  {len(det_df):,} rows")

    # ── Dedup + selection ───────────────────────────────────

    eligible = det_df[det_df["avg_trades"] >= min_trades].copy()
    eligible_dedup = eligible.drop_duplicates(subset=RESULT_COLS)

    print(f"\n{'='*70}")
    print(f"  SELECCION DE CANDIDATOS (dedup por resultados)")
    print(f"  Eligible: {len(eligible):,} (min {min_trades} trades)")
    print(f"  Dedup: {len(eligible_dedup):,} configs unicas")
    print(f"{'='*70}")

    top_cr = eligible_dedup.nlargest(top_n, "avg_CR")
    top_wr = eligible_dedup.nlargest(top_n, ["avg_WR", "avg_CR"])
    candidates = pd.concat([top_cr, top_wr]).drop_duplicates(subset=RESULT_COLS)

    print(f"  Top {top_n} por avg_CR + Top {top_n} por avg_WR = {len(candidates)} candidatos unicos\n")

    for i, (_, row) in enumerate(candidates.iterrows(), 1):
        in_cr = i <= top_n
        in_wr = any((top_wr[RESULT_COLS] == row[RESULT_COLS]).all(axis=1))
        source = "CR+WR" if in_cr and in_wr else ("CR" if in_cr else "WR")
        mda = "None" if pd.isna(row['max_depth_atr']) else str(int(row['max_depth_atr']))
        print(f"  {i:>2d}. [{source:>5s}] atr={row['atr_mult']:.1f} "
              f"mda={mda:>4s} red={row['reduction']:.2f} "
              f"lb={int(row['lookback_bars'])} "
              f"TT={'Y' if row['trend_template'] else 'N'} "
              f"VC={'Y' if row['vol_contraction'] else 'N'} "
              f"vf={row['vol_filter']:<10s} "
              f"-> {int(row['signals']):>3d}sen T={row['avg_trades']:.1f} "
              f"WR={row['avg_WR']:.0%} CR={row['avg_CR']:+.2%}")

    # ── Load data + precompute ──────────────────────────────

    print(f"\nCargando {ticker} para Fase 2...")
    daily = pd.read_csv(DATA_DIR / f"{ticker}.csv", parse_dates=["date"], index_col="date")
    train = daily[daily.index < args.train_cutoff]

    tt_train = evaluate_trend_template(train)
    tt_mask_train = tt_train["trend_template"]

    needed_combos = set()
    for _, cand in candidates.iterrows():
        needed_combos.add((cand["atr_mult"], cand["use_close_only"]))

    caches = {}
    for atr_mult, use_close in needed_combos:
        config = ATRZigZagConfig(atr_length=14, atr_mult=atr_mult, use_close_only=use_close)
        detector = ATRZigZagDetector(config)
        swings = detector.detect(train)
        contractions = compute_contractions(swings, train)
        atr = compute_atr(train, 14)
        caches[(atr_mult, use_close)] = {
            "swings": swings, "contractions": contractions,
            "atr": atr, "detector": detector,
        }

    # ── Phase 2 ─────────────────────────────────────────────

    print(f"\n{'='*70}")
    print(f"  FASE 2: SALIDA — {ticker} TRAIN ({n_exit} configs x {len(candidates)} candidatos)")
    print(f"{'='*70}")

    all_phase2 = []
    t0 = time.time()

    for cand_idx, (_, cand) in enumerate(candidates.iterrows()):
        cand_cache = caches[(cand["atr_mult"], cand["use_close_only"])]
        cand_mda = None if (isinstance(cand["max_depth_atr"], float) and pd.isna(cand["max_depth_atr"])) else cand["max_depth_atr"]
        if cand_mda is not None:
            cand_mda = int(cand_mda)

        cand_seq = {
            "method": "tolerance", "min_contractions": 2, "max_contractions": 6,
            "lookback_bars": int(cand["lookback_bars"]),
            "tolerance": cand["tolerance"],
            "max_depth_pct": cand["max_depth_pct"],
            "max_depth_atr": cand_mda,
            "min_total_reduction": cand["reduction"],
            "max_gap_between_contractions_days": None,
            "require_ascending_lows": True,
            "ascending_lows_tolerance": cand["asc_lows_tol"],
        }
        cand_comp = {"method": "ratio", "atr_period": 14, "ratio_threshold": cand["comp_thresh"]}
        cand_vol_contr = {"method": "ratio", "ratio_threshold": 0.85} if cand["vol_contraction"] else None

        res = run_full_vcp_pipeline(
            ohlc=train, swing_detector=cand_cache["detector"],
            sequence_params=cand_seq, compression_params=cand_comp,
            breakout_params=BREAKOUT_BASE,
            volume_contraction_params=cand_vol_contr,
            precomputed_swings=cand_cache["swings"],
            precomputed_contractions=cand_cache["contractions"],
            precomputed_atr=cand_cache["atr"],
        )
        raw_sigs = {dt: s for dt, s in res.items() if s is not None}

        if cand["trend_template"]:
            raw_sigs = {dt: s for dt, s in raw_sigs.items()
                        if dt in tt_mask_train.index and tt_mask_train.loc[dt]}

        vf_name = cand["vol_filter"]
        vf = next(v for v in VOLUME_FILTER_VARIANTS if v["name"] == vf_name)
        if vf["window"] is not None:
            filtered_sigs = apply_volume_post_filter(raw_sigs, train, vf["window"], vf["threshold"])
        else:
            filtered_sigs = raw_sigs

        print(f"  Candidato {cand_idx+1}/{len(candidates)}: "
              f"{len(filtered_sigs)} senales, vf={vf_name}, evaluando {n_exit} exits...")

        for trail, target, early, be_r, max_sl in itertools.product(
            TRAILING_MULTS, TARGET_RS, EARLY_EXITS, BREAKEVEN_RS, MAX_STOP_LOSSES
        ):
            risk = {**RISK_BASE, "max_stop_loss_pct": max_sl,
                    "trailing_atr_multiplier": trail,
                    "target_r_multiple": target,
                    "early_exit_days": early,
                    "breakeven_r_multiple": be_r}
            ev = evaluate_signals_seq(
                train, filtered_sigs, risk,
                precomputed_atr=cand_cache["atr"])

            all_phase2.append({
                "candidate_idx": cand_idx,
                **{c: cand[c] for c in CONFIG_COLS},
                "trailing_atr_multiplier": trail,
                "target_r_multiple": target,
                "early_exit_days": early,
                "breakeven_r_multiple": be_r,
                "max_stop_loss_pct": max_sl,
                "trades": ev["trades"], "wins": ev["wins"],
                "WR": ev["WR"], "CR": ev["CR"], "avg_R": ev["avg_R"],
            })

    t_phase2 = time.time() - t0
    phase2_df = pd.DataFrame(all_phase2)
    print(f"\n  Fase 2 completada: {len(phase2_df):,} rows en {t_phase2:.0f}s ({t_phase2/60:.1f}m)")

    # ── Best exit per candidate ─────────────────────────────

    print(f"\n  Mejor exit por candidato:")
    for cand_idx in range(len(candidates)):
        cand_exits = phase2_df[phase2_df["candidate_idx"] == cand_idx]
        best = cand_exits.nlargest(1, "CR").iloc[0]
        t_r = f"{best['target_r_multiple']:.1f}" if pd.notna(best['target_r_multiple']) else 'None'
        e_e = f"{int(best['early_exit_days'])}" if pd.notna(best['early_exit_days']) else 'None'
        print(f"    C{cand_idx+1:>2d}: trail={best['trailing_atr_multiplier']:.1f}, "
              f"target={t_r}, early={e_e}, "
              f"be_R={best['breakeven_r_multiple']:.1f}, sl={best['max_stop_loss_pct']:.2f} "
              f"-> {int(best['trades'])}T WR={fmt_wr(best['WR'])} CR={fmt_pct(best['CR'])}")

    # ── Final ranking ───────────────────────────────────────

    print(f"\n{'='*70}")
    print(f"  RANKING FINAL — {ticker} TRAIN")
    print(f"{'='*70}")

    best_per_cand = []
    for cand_idx in range(len(candidates)):
        cand_exits = phase2_df[phase2_df["candidate_idx"] == cand_idx]
        if len(cand_exits) == 0:
            continue
        best_row = cand_exits.nlargest(1, "CR").iloc[0].to_dict()
        best_per_cand.append(best_row)

    final_df = pd.DataFrame(best_per_cand)

    for col in ["CR", "WR", "avg_R"]:
        col_min, col_max = final_df[col].min(), final_df[col].max()
        if col_max > col_min:
            final_df[f"{col}_norm"] = (final_df[col] - col_min) / (col_max - col_min)
        else:
            final_df[f"{col}_norm"] = 0.5

    final_df["composite"] = (
        0.5 * final_df["CR_norm"]
        + 0.3 * final_df["WR_norm"]
        + 0.2 * final_df["avg_R_norm"]
    )
    final_df_sorted = final_df.sort_values("composite", ascending=False)

    print(f"\n  Top {min(len(final_df_sorted), 20)} combos por composite "
          f"(50% CR + 30% WR + 20% avg_R):\n")
    print(f"  {'#':>3s}  {'Comp':>5s}  {'T':>3s}  {'WR':>5s}  {'CR':>9s}  {'avgR':>6s}  "
          f"{'trail':>5s} {'target':>6s} {'early':>5s} {'be_R':>4s} {'sl':>5s}  "
          f"{'vf':>10s} {'TT':>2s} {'VC':>2s}")
    print(f"  {'─'*100}")

    for i, (_, row) in enumerate(final_df_sorted.head(20).iterrows(), 1):
        t_r = f"{row['target_r_multiple']:.1f}" if pd.notna(row['target_r_multiple']) else "None"
        e_e = f"{int(row['early_exit_days'])}" if pd.notna(row['early_exit_days']) else "None"
        print(f"  {i:>3d}  {row['composite']:.3f}  {int(row['trades']):>3d}  "
              f"{row['WR']:.0%}  {row['CR']:>+9.2%}  {row['avg_R']:>+5.2f}  "
              f"{row['trailing_atr_multiplier']:>5.1f} {t_r:>6s} {e_e:>5s} "
              f"{row['breakeven_r_multiple']:>4.1f} {row['max_stop_loss_pct']:>5.2f}  "
              f"{row['vol_filter']:>10s} "
              f"{'Y' if row['trend_template'] else 'N':>2s} "
              f"{'Y' if row['vol_contraction'] else 'N':>2s}")

    # ── Trade details for top 5 ─────────────────────────────

    print(f"\n{'─'*70}")
    print(f"  DETALLE DE TRADES — Top 5 combos")
    print(f"{'─'*70}")

    for rank, (_, row) in enumerate(final_df_sorted.head(5).iterrows(), 1):
        cand_idx = int(row["candidate_idx"])
        cand = candidates.iloc[cand_idx]
        cand_cache = caches[(cand["atr_mult"], cand["use_close_only"])]
        cand_mda = None if (isinstance(cand["max_depth_atr"], float) and pd.isna(cand["max_depth_atr"])) else int(cand["max_depth_atr"])

        cand_seq = {
            "method": "tolerance", "min_contractions": 2, "max_contractions": 6,
            "lookback_bars": int(cand["lookback_bars"]),
            "tolerance": cand["tolerance"],
            "max_depth_pct": cand["max_depth_pct"],
            "max_depth_atr": cand_mda,
            "min_total_reduction": cand["reduction"],
            "max_gap_between_contractions_days": None,
            "require_ascending_lows": True,
            "ascending_lows_tolerance": cand["asc_lows_tol"],
        }
        cand_comp = {"method": "ratio", "atr_period": 14, "ratio_threshold": cand["comp_thresh"]}
        cand_vol_contr = {"method": "ratio", "ratio_threshold": 0.85} if cand["vol_contraction"] else None

        res = run_full_vcp_pipeline(
            ohlc=train, swing_detector=cand_cache["detector"],
            sequence_params=cand_seq, compression_params=cand_comp,
            breakout_params=BREAKOUT_BASE,
            volume_contraction_params=cand_vol_contr,
            precomputed_swings=cand_cache["swings"],
            precomputed_contractions=cand_cache["contractions"],
            precomputed_atr=cand_cache["atr"],
        )
        raw_sigs = {dt: s for dt, s in res.items() if s is not None}
        if cand["trend_template"]:
            raw_sigs = {dt: s for dt, s in raw_sigs.items()
                        if dt in tt_mask_train.index and tt_mask_train.loc[dt]}
        vf = next(v for v in VOLUME_FILTER_VARIANTS if v["name"] == cand["vol_filter"])
        if vf["window"] is not None:
            filtered_sigs = apply_volume_post_filter(raw_sigs, train, vf["window"], vf["threshold"])
        else:
            filtered_sigs = raw_sigs

        risk_final = {**RISK_BASE,
                      "trailing_atr_multiplier": row["trailing_atr_multiplier"],
                      "target_r_multiple": row["target_r_multiple"] if pd.notna(row["target_r_multiple"]) else None,
                      "early_exit_days": int(row["early_exit_days"]) if pd.notna(row["early_exit_days"]) else None,
                      "breakeven_r_multiple": row["breakeven_r_multiple"],
                      "max_stop_loss_pct": row["max_stop_loss_pct"]}
        ev = evaluate_signals_seq(train, filtered_sigs, risk_final,
                                   precomputed_atr=cand_cache["atr"])

        t_r = f"{row['target_r_multiple']:.1f}" if pd.notna(row['target_r_multiple']) else "None"
        mda = "None" if pd.isna(cand['max_depth_atr']) else str(int(cand['max_depth_atr']))
        print(f"\n  #{rank} (composite={row['composite']:.3f})")
        print(f"     Det: atr={cand['atr_mult']:.1f} HL={'C' if cand['use_close_only'] else 'HL'} "
              f"mda={mda} red={cand['reduction']:.2f} lb={int(cand['lookback_bars'])} "
              f"comp={cand['comp_thresh']:.2f} "
              f"TT={'Y' if cand['trend_template'] else 'N'} "
              f"VC={'Y' if cand['vol_contraction'] else 'N'} "
              f"vf={cand['vol_filter']}")
        print(f"     Exit: trail={row['trailing_atr_multiplier']:.1f}, target={t_r}, "
              f"early={'None' if pd.isna(row['early_exit_days']) else int(row['early_exit_days'])}, "
              f"be_R={row['breakeven_r_multiple']:.1f}, sl={row['max_stop_loss_pct']:.2f}")
        print(f"     {ev['trades']}T, WR={fmt_wr(ev['WR'])}, CR={fmt_pct(ev['CR'])}, "
              f"avgR={ev['avg_R']:+.2f}")
        reasons_str = ", ".join(f"{k}={v}" for k, v in sorted(ev["reasons"].items()))
        print(f"     Salidas: {reasons_str}")

        if ev["trade_details"]:
            for j, (pat, trade) in enumerate(ev["trade_details"], 1):
                entry_str = pat["first_signal_date"].strftime("%Y-%m-%d")
                exit_str = trade["exit_date"].strftime("%Y-%m-%d")
                print(f"     {j:>2d}: {entry_str} -> {exit_str} | "
                      f"{trade['exit_reason']:<15s} | "
                      f"PnL={trade['pnl_pct']:+.2%} | R={trade['r_multiple']:+.1f}R | "
                      f"MaxR={trade['max_r']:.1f}R | Dur={trade['duration_days']}d")

    # ── Save ────────────────────────────────────────────────

    phase2_path = OUTPUT_DIR / f"{ticker.lower()}_phase2_exit.csv"
    phase2_df.to_csv(phase2_path, index=False)
    print(f"\n  Guardado: {phase2_path}")
    print(f"\nCompleto!")


if __name__ == "__main__":
    main()
