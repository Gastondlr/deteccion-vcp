"""Evaluate top configs on train+test for any ticker. Usage: python eval_test_generic.py TICKER"""
import argparse, functools, json, sys, numpy as np, pandas as pd
from pathlib import Path
print = functools.partial(print, flush=True)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from models.configs import ATRZigZagConfig
from vcp_detection.heuristic import ATRZigZagDetector, run_full_vcp_pipeline
from vcp_detection.heuristic.contractions import compute_contractions
from vcp_detection.heuristic.atr_compression import compute_atr
from vcp_detection.analysis import evaluate_signals_to_trades
from stages.trend_template import evaluate_trend_template

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "csv"
RISK_BASE = {"trailing_sma_period": 20, "trailing_volume_factor": 1.5,
    "trailing_stop_method": "atr", "trailing_atr_period": 14,
    "max_bars_without_progress": 15, "min_progress_r": 0.5}
BREAKOUT_BASE = {"volume_method": "ratio", "volume_ratio_threshold": 1.5,
    "volume_lookback_days": 50, "require_volume_confirmation": False}
VOL_FILTERS = {"no_filter": (None, None), "w1_t1.2": (1, 1.2), "w1_t1.5": (1, 1.5),
    "w3_t1.2": (3, 1.2), "w3_t1.5": (3, 1.5), "w5_t1.2": (5, 1.2), "w5_t1.5": (5, 1.5)}

def apply_volume_post_filter(signals, ohlc, window, threshold, lookback_days=50):
    filtered = {}
    for dt, sig in signals.items():
        eval_loc = ohlc.index.get_loc(dt)
        ls = max(0, eval_loc - lookback_days)
        va = float(ohlc["volume"].iloc[ls:eval_loc].mean()) if eval_loc > ls else 0.0
        if va <= 0: continue
        ws = max(0, eval_loc - window + 1)
        if any(float(v) >= threshold * va for v in ohlc["volume"].iloc[ws:eval_loc+1]):
            filtered[dt] = sig
    return filtered

def run_eval(ohlc, det, exit_cfg):
    config = ATRZigZagConfig(atr_length=14, atr_mult=det["atr_mult"], use_close_only=det["use_close_only"])
    detector = ATRZigZagDetector(config)
    sw = detector.detect(ohlc); contr = compute_contractions(sw, ohlc); atr = compute_atr(ohlc, 14)
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
    w, t = VOL_FILTERS[det["vol_filter"]]
    if w is not None: sigs = apply_volume_post_filter(sigs, ohlc, w, t)
    risk = {**RISK_BASE, **exit_cfg}
    results = evaluate_signals_to_trades(sigs, ohlc, risk, grouping="sequential", precomputed_atr=atr)
    n = len(results)
    if n == 0: return {"trades": 0, "wins": 0, "WR": 0, "CR": 0, "avg_R": 0, "max_dd": 0, "PF": 0, "details": [], "Sharpe": 0, "Exp": 0}
    trades = [t for _, t in results]
    wins = sum(1 for t in trades if t["pnl_pct"] > 0)
    cr = float(np.prod([1 + t["pnl_pct"] for t in trades]) - 1)
    avg_r = float(np.mean([t["r_multiple"] for t in trades]))
    eq, peak, mdd = 1.0, 1.0, 0.0
    for t in trades: eq *= (1+t["pnl_pct"]); peak = max(peak, eq); mdd = min(mdd, (eq-peak)/peak)
    pw = sum(t["pnl_pct"] for t in trades if t["pnl_pct"] > 0)
    pl = abs(sum(t["pnl_pct"] for t in trades if t["pnl_pct"] <= 0))
    pf = pw/pl if pl > 0 else float("inf")
    years = len(ohlc)/252
    rets = np.array([t["pnl_pct"] for t in trades])
    tpy = n/years if years > 0 else n
    sharpe = (rets.mean()/rets.std())*np.sqrt(tpy) if rets.std() > 0 else 0
    exp = sum(t["duration_days"] for t in trades)/len(ohlc)
    cagr = (1+cr)**(1/years)-1 if years > 0 and cr > -1 else 0
    reasons = {}
    for t in trades: reasons[t["exit_reason"]] = reasons.get(t["exit_reason"], 0) + 1
    return {"trades": n, "wins": wins, "WR": wins/n, "CR": cr, "CAGR": cagr, "avg_R": avg_r,
            "max_dd": mdd, "PF": pf, "Sharpe": sharpe, "Exp": exp, "reasons": reasons, "details": results}

CONFIGS = {
    "MSFT": [
        {"name": "COMP#1 tr=3.0 tg=2R sl=5% no_filter VC",
         "det": {"atr_mult": 2.0, "use_close_only": False, "max_depth_atr": None, "min_total_reduction": 0.80,
                 "lookback_bars": 126, "compression_threshold": 0.90, "tolerance": 0.10, "max_depth_pct": 0.25,
                 "ascending_lows_tolerance": 0.03, "volume_contraction": {"method": "ratio", "ratio_threshold": 0.85},
                 "vol_filter": "no_filter"},
         "exit": {"trailing_atr_multiplier": 3.0, "target_r_multiple": 2.0, "early_exit_days": None,
                  "breakeven_r_multiple": 0.5, "max_stop_loss_pct": 0.05}},
        {"name": "COMP#2 tr=1.5 tg=3R sl=3% no_filter",
         "det": {"atr_mult": 2.0, "use_close_only": False, "max_depth_atr": None, "min_total_reduction": 0.60,
                 "lookback_bars": 126, "compression_threshold": 0.85, "tolerance": 0.10, "max_depth_pct": 0.25,
                 "ascending_lows_tolerance": 0.03, "volume_contraction": None,
                 "vol_filter": "no_filter"},
         "exit": {"trailing_atr_multiplier": 1.5, "target_r_multiple": 3.0, "early_exit_days": None,
                  "breakeven_r_multiple": 0.5, "max_stop_loss_pct": 0.03}},
        {"name": "COMP#3 tr=3.0 tg=2R sl=5% no_filter VC red=0.60",
         "det": {"atr_mult": 2.0, "use_close_only": False, "max_depth_atr": None, "min_total_reduction": 0.60,
                 "lookback_bars": 126, "compression_threshold": 0.85, "tolerance": 0.10, "max_depth_pct": 0.25,
                 "ascending_lows_tolerance": 0.03, "volume_contraction": {"method": "ratio", "ratio_threshold": 0.85},
                 "vol_filter": "no_filter"},
         "exit": {"trailing_atr_multiplier": 3.0, "target_r_multiple": 2.0, "early_exit_days": None,
                  "breakeven_r_multiple": 0.5, "max_stop_loss_pct": 0.05}},
    ],
    "NVDA": [
        {"name": "COMP#1 tr=2.5 tg=5R sl=5% w5_t1.2",
         "det": {"atr_mult": 2.0, "use_close_only": False, "max_depth_atr": None, "min_total_reduction": 0.60,
                 "lookback_bars": 63, "compression_threshold": 0.95, "tolerance": 0.10, "max_depth_pct": 0.30,
                 "ascending_lows_tolerance": 0.01, "volume_contraction": None,
                 "vol_filter": "w5_t1.2"},
         "exit": {"trailing_atr_multiplier": 2.5, "target_r_multiple": 5.0, "early_exit_days": None,
                  "breakeven_r_multiple": 1.5, "max_stop_loss_pct": 0.05}},
        {"name": "COMP#2 tr=2.5 tg=5R sl=5% w3_t1.2",
         "det": {"atr_mult": 2.0, "use_close_only": False, "max_depth_atr": None, "min_total_reduction": 0.60,
                 "lookback_bars": 63, "compression_threshold": 0.95, "tolerance": 0.10, "max_depth_pct": 0.30,
                 "ascending_lows_tolerance": 0.01, "volume_contraction": None,
                 "vol_filter": "w3_t1.2"},
         "exit": {"trailing_atr_multiplier": 2.5, "target_r_multiple": 5.0, "early_exit_days": None,
                  "breakeven_r_multiple": 1.5, "max_stop_loss_pct": 0.05}},
        {"name": "COMP#3 tr=2.5 tg=5R sl=5% w1_t1.2",
         "det": {"atr_mult": 2.0, "use_close_only": False, "max_depth_atr": None, "min_total_reduction": 0.60,
                 "lookback_bars": 63, "compression_threshold": 0.95, "tolerance": 0.10, "max_depth_pct": 0.30,
                 "ascending_lows_tolerance": 0.01, "volume_contraction": None,
                 "vol_filter": "w1_t1.2"},
         "exit": {"trailing_atr_multiplier": 2.5, "target_r_multiple": 5.0, "early_exit_days": None,
                  "breakeven_r_multiple": 1.5, "max_stop_loss_pct": 0.05}},
    ],
}

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("ticker")
    args = parser.parse_args()
    ticker = args.ticker.upper()
    configs = CONFIGS[ticker]

    daily = pd.read_csv(DATA_DIR / f"{ticker}.csv", parse_dates=["date"], index_col="date")
    train = daily[daily.index < "2020-01-01"]
    test = daily[daily.index >= "2020-01-01"]

    bh_train_cr = train["close"].iloc[-1]/train["close"].iloc[0]-1
    bh_test_cr = test["close"].iloc[-1]/test["close"].iloc[0]-1
    bh_test_dd = ((test["close"]-test["close"].cummax())/test["close"].cummax()).min()
    bh_train_dd = ((train["close"]-train["close"].cummax())/train["close"].cummax()).min()

    print(f"{'='*70}")
    print(f"  {ticker} — Evaluacion Train + Test")
    print(f"{'='*70}")
    print(f"  TRAIN: {len(train)} barras ({train.index.min().date()} a {train.index[-1].date()})")
    print(f"  TEST:  {len(test)} barras ({test.index[0].date()} a {test.index[-1].date()})")
    print(f"  B&H TRAIN: CR={bh_train_cr:+.2%}, MaxDD={bh_train_dd:.2%}")
    print(f"  B&H TEST:  CR={bh_test_cr:+.2%}, MaxDD={bh_test_dd:.2%}")

    for cfg in configs:
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
            if reasons_str: print(f"    Salidas: {reasons_str}")
            for j, (pat, trade) in enumerate(ev["details"], 1):
                entry = pat["first_signal_date"].strftime("%Y-%m-%d")
                exit_ = trade["exit_date"].strftime("%Y-%m-%d")
                print(f"    {j:>2d}: {entry} -> {exit_} | {trade['exit_reason']:<15s} | "
                      f"PnL={trade['pnl_pct']:+.2%} | R={trade['r_multiple']:+.1f}R | "
                      f"MaxR={trade['max_r']:.1f}R | Dur={trade['duration_days']}d")
    print(f"\n{'='*70}\n  COMPLETO\n{'='*70}")
