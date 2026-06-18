"""Evaluate TSLA v2+v3 top configs on train+test."""
import functools, sys, numpy as np, pandas as pd
from dataclasses import replace
from pathlib import Path
print = functools.partial(print, flush=True)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from models.configs import ATRZigZagConfig
from vcp_detection.heuristic import ATRZigZagDetector, run_full_vcp_pipeline
from vcp_detection.heuristic.contractions import compute_contractions
from vcp_detection.heuristic.atr_compression import compute_atr
from vcp_detection.analysis import evaluate_signals_to_trades

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "csv"
RISK_BASE = {"trailing_sma_period": 20, "trailing_volume_factor": 1.5,
    "trailing_stop_method": "atr", "trailing_atr_period": 14,
    "max_bars_without_progress": 15, "min_progress_r": 0.5}
BREAKOUT_BASE = {"volume_method": "ratio", "volume_ratio_threshold": 1.5,
    "volume_lookback_days": 50, "require_volume_confirmation": False}


def apply_volume_post_filter(signals, ohlc, window, threshold, forward=0, lookback_days=50):
    filtered = {}
    for dt, sig in signals.items():
        eval_loc = ohlc.index.get_loc(dt)
        ls = max(0, eval_loc - lookback_days)
        va = float(ohlc["volume"].iloc[ls:eval_loc].mean()) if eval_loc > ls else 0.0
        if va <= 0:
            continue
        threshold_vol = threshold * va
        ws = max(0, eval_loc - window + 1)
        if any(float(v) >= threshold_vol for v in ohlc["volume"].iloc[ws:eval_loc + 1]):
            filtered[dt] = sig
            continue
        if forward > 0:
            pivot_price = sig.pivot_price
            max_fwd_loc = min(eval_loc + forward, len(ohlc) - 1)
            for fwd_loc in range(eval_loc + 1, max_fwd_loc + 1):
                fwd_date = ohlc.index[fwd_loc]
                fwd_close = float(ohlc.iloc[fwd_loc]["close"])
                if fwd_close <= pivot_price:
                    break
                fwd_vol = float(ohlc.iloc[fwd_loc]["volume"])
                if fwd_vol >= threshold_vol:
                    new_entry = fwd_close
                    new_stop_dist = (new_entry - sig.suggested_stop) / new_entry
                    new_sig = replace(sig, signal_date=fwd_date, entry_price=new_entry,
                                      suggested_stop_distance_pct=new_stop_dist,
                                      volume_confirmation={**sig.volume_confirmation,
                                          "forward_confirmed": True, "breakout_date": dt,
                                          "confirmation_delay_days": fwd_loc - eval_loc})
                    filtered[fwd_date] = new_sig
                    break
    return filtered


def run_eval(ohlc, det, exit_cfg):
    config = ATRZigZagConfig(atr_length=14, atr_mult=det["atr_mult"], use_close_only=det["use_close_only"])
    detector = ATRZigZagDetector(config)
    sw = detector.detect(ohlc)
    contr = compute_contractions(sw, ohlc)
    atr = compute_atr(ohlc, 14)
    seq = {"method": "tolerance", "min_contractions": 2, "max_contractions": 6,
           "lookback_bars": det["lookback_bars"], "tolerance": det["tolerance"],
           "max_depth_pct": det["max_depth_pct"], "max_depth_atr": det["max_depth_atr"],
           "min_total_reduction": det["min_total_reduction"],
           "max_gap_between_contractions_days": None, "require_ascending_lows": True,
           "ascending_lows_tolerance": det["ascending_lows_tolerance"]}
    comp = {"method": "ratio", "atr_period": 14, "ratio_threshold": det["compression_threshold"]}
    res = run_full_vcp_pipeline(ohlc=ohlc, swing_detector=detector, sequence_params=seq,
        compression_params=comp, breakout_params=BREAKOUT_BASE,
        volume_contraction_params=det.get("volume_contraction"),
        precomputed_swings=sw, precomputed_contractions=contr, precomputed_atr=atr)
    sigs = {dt: s for dt, s in res.items() if s is not None}
    vf = det["vol_filter"]
    if vf != "no_filter":
        sigs = apply_volume_post_filter(sigs, ohlc, vf["window"], vf["threshold"],
                                         forward=vf.get("forward", 0))
    risk = {**RISK_BASE, **exit_cfg}
    results = evaluate_signals_to_trades(sigs, ohlc, risk, grouping="sequential", precomputed_atr=atr)
    n = len(results)
    if n == 0:
        return {"trades": 0, "wins": 0, "WR": 0, "CR": 0, "avg_R": 0, "max_dd": 0,
                "PF": 0, "details": [], "Sharpe": 0, "Exp": 0, "CAGR": 0, "reasons": {}}
    trades = [t for _, t in results]
    wins = sum(1 for t in trades if t["pnl_pct"] > 0)
    cr = float(np.prod([1 + t["pnl_pct"] for t in trades]) - 1)
    avg_r = float(np.mean([t["r_multiple"] for t in trades]))
    eq, peak, mdd = 1.0, 1.0, 0.0
    for t in trades:
        eq *= (1 + t["pnl_pct"])
        peak = max(peak, eq)
        mdd = min(mdd, (eq - peak) / peak)
    pw = sum(t["pnl_pct"] for t in trades if t["pnl_pct"] > 0)
    pl = abs(sum(t["pnl_pct"] for t in trades if t["pnl_pct"] <= 0))
    pf = pw / pl if pl > 0 else float("inf")
    years = len(ohlc) / 252
    rets = np.array([t["pnl_pct"] for t in trades])
    tpy = n / years if years > 0 else n
    sharpe = (rets.mean() / rets.std()) * np.sqrt(tpy) if rets.std() > 0 else 0
    exp = sum(t["duration_days"] for t in trades) / len(ohlc)
    cagr = (1 + cr) ** (1 / years) - 1 if years > 0 and cr > -1 else 0
    reasons = {}
    for t in trades:
        reasons[t["exit_reason"]] = reasons.get(t["exit_reason"], 0) + 1
    return {"trades": n, "wins": wins, "WR": wins / n, "CR": cr, "CAGR": cagr, "avg_R": avg_r,
            "max_dd": mdd, "PF": pf, "Sharpe": sharpe, "Exp": exp, "reasons": reasons, "details": results}


# Det A: mda=None, lb=126
TSLA_DET_A = {"atr_mult": 2.0, "use_close_only": True, "max_depth_atr": None,
    "min_total_reduction": 0.80, "lookback_bars": 126, "compression_threshold": 0.95,
    "tolerance": 0.10, "max_depth_pct": 0.35, "ascending_lows_tolerance": 0.08,
    "volume_contraction": None}

# Det B: mda=8, lb=126
TSLA_DET_B = {"atr_mult": 2.0, "use_close_only": True, "max_depth_atr": 8,
    "min_total_reduction": 0.80, "lookback_bars": 126, "compression_threshold": 0.95,
    "tolerance": 0.10, "max_depth_pct": 0.35, "ascending_lows_tolerance": 0.08,
    "volume_contraction": None}

CONFIGS = [
    # v2 baseline: no_filter, most trades
    {"name": "Baseline no_filter tr=1.5 tg=5R sl=5%",
     "det": {**TSLA_DET_B, "vol_filter": "no_filter"},
     "exit": {"trailing_atr_multiplier": 1.5, "target_r_multiple": 5.0, "early_exit_days": None,
              "breakeven_r_multiple": 0.5, "max_stop_loss_pct": 0.05}},

    # v2 COMP#1: w3_t1.5, composite winner
    {"name": "COMP#1 w3_t1.5 tr=1.5 tg=5R sl=7%",
     "det": {**TSLA_DET_A, "vol_filter": {"window": 3, "threshold": 1.5}},
     "exit": {"trailing_atr_multiplier": 1.5, "target_r_multiple": 5.0, "early_exit_days": None,
              "breakeven_r_multiple": 0.5, "max_stop_loss_pct": 0.07}},

    # v2 COMP#3: w1_t1.2
    {"name": "COMP#3 w1_t1.2 tr=1.5 tg=5R sl=7%",
     "det": {**TSLA_DET_B, "vol_filter": {"window": 1, "threshold": 1.2}},
     "exit": {"trailing_atr_multiplier": 1.5, "target_r_multiple": 5.0, "early_exit_days": None,
              "breakeven_r_multiple": 0.5, "max_stop_loss_pct": 0.07}},

    # v3 FWD#1: w3_t1.5_f3 (forward version of COMP#1)
    {"name": "FWD#1 w3_t1.5_f3 tr=1.5 tg=5R sl=7%",
     "det": {**TSLA_DET_A, "vol_filter": {"window": 3, "threshold": 1.5, "forward": 3}},
     "exit": {"trailing_atr_multiplier": 1.5, "target_r_multiple": 5.0, "early_exit_days": None,
              "breakeven_r_multiple": 0.5, "max_stop_loss_pct": 0.07}},

    # v3 FWD#3: w1_t1.2_f3 (forward version of COMP#3)
    {"name": "FWD#3 w1_t1.2_f3 tr=1.5 tg=5R sl=7%",
     "det": {**TSLA_DET_B, "vol_filter": {"window": 1, "threshold": 1.2, "forward": 3}},
     "exit": {"trailing_atr_multiplier": 1.5, "target_r_multiple": 5.0, "early_exit_days": None,
              "breakeven_r_multiple": 0.5, "max_stop_loss_pct": 0.07}},
]

if __name__ == "__main__":
    daily = pd.read_csv(DATA_DIR / "TSLA.csv", parse_dates=["date"], index_col="date")
    train = daily[daily.index < "2020-01-01"]
    test = daily[daily.index >= "2020-01-01"]

    bh_train_cr = train["close"].iloc[-1] / train["close"].iloc[0] - 1
    bh_test_cr = test["close"].iloc[-1] / test["close"].iloc[0] - 1
    bh_train_dd = ((train["close"] - train["close"].cummax()) / train["close"].cummax()).min()
    bh_test_dd = ((test["close"] - test["close"].cummax()) / test["close"].cummax()).min()

    print(f"{'='*70}")
    print(f"  TSLA — Evaluacion Train + Test (v2 + v3 forward volume)")
    print(f"{'='*70}")
    print(f"  TRAIN: {len(train)} barras ({train.index.min().date()} a {train.index[-1].date()})")
    print(f"  TEST:  {len(test)} barras ({test.index[0].date()} a {test.index[-1].date()})")
    print(f"  B&H TRAIN: CR={bh_train_cr:+.2%}, MaxDD={bh_train_dd:.2%}")
    print(f"  B&H TEST:  CR={bh_test_cr:+.2%}, MaxDD={bh_test_dd:.2%}")

    for cfg in CONFIGS:
        print(f"\n{'─'*70}")
        print(f"  {cfg['name']}")
        print(f"{'─'*70}")
        for label, data in [("TRAIN", train), ("TEST", test)]:
            ev = run_eval(data, cfg["det"], cfg["exit"])
            reasons_str = ", ".join(f"{k}={v}" for k, v in sorted(ev.get("reasons", {}).items()))
            print(f"\n  {label}: {ev['trades']}T, {ev['wins']}W, {ev['trades']-ev['wins']}L, "
                  f"WR={ev['WR']:.0%}, CR={ev['CR']:+.2%}, CAGR={ev.get('CAGR',0):.2%}, "
                  f"MaxDD={ev['max_dd']:.2%}, Sharpe={ev['Sharpe']:.2f}, "
                  f"avgR={ev['avg_R']:+.2f}, PF={ev['PF']:.1f}, Exp={ev['Exp']:.0%}")
            if reasons_str:
                print(f"    Salidas: {reasons_str}")
            for j, (pat, trade) in enumerate(ev["details"], 1):
                entry = pat["first_signal_date"].strftime("%Y-%m-%d")
                exit_ = trade["exit_date"].strftime("%Y-%m-%d")
                fwd_info = ""
                sig = pat.get("signal_obj")
                if sig and sig.volume_confirmation.get("forward_confirmed"):
                    delay = sig.volume_confirmation.get("confirmation_delay_days", "?")
                    fwd_info = f" [fwd+{delay}d]"
                print(f"    {j:>2d}: {entry} -> {exit_} | {trade['exit_reason']:<15s} | "
                      f"PnL={trade['pnl_pct']:+.2%} | R={trade['r_multiple']:+.1f}R | "
                      f"MaxR={trade['max_r']:.1f}R | Dur={trade['duration_days']}d{fwd_info}")

    print(f"\n{'='*70}\n  COMPLETO\n{'='*70}")
