"""Test v3 best configs (first config per ticker) with v4 Trend Template filter.

Purpose: determine if TT is what kills the v3 signals in test.
Runs each ticker's v3 #1 config with and without TT, showing the difference.
"""
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
from stages.trend_template import evaluate_trend_template

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


def apply_trend_template_filter(signals, tt_data):
    """v4 TT: check all 7 conditions at first peak."""
    filtered = {}
    for dt, sig in signals.items():
        first_peak_date = sig.pivot_info.sequence.contractions[0].high_swing.date
        if first_peak_date not in tt_data.index:
            continue
        if not tt_data.loc[first_peak_date, "trend_template"]:
            continue
        formation_mask = (tt_data.index >= first_peak_date) & (tt_data.index <= dt)
        formation_data = tt_data.loc[formation_mask]
        if formation_data.empty:
            continue
        if not (formation_data["cond_2"].all() and
                formation_data["cond_3"].all() and
                formation_data["cond_4"].all()):
            continue
        filtered[dt] = sig
    return filtered


def run_eval(ohlc, det, exit_cfg, tt_data=None):
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
    vol_contr = det.get("volume_contraction")
    res = run_full_vcp_pipeline(ohlc=ohlc, swing_detector=detector, sequence_params=seq,
        compression_params=comp, breakout_params=BREAKOUT_BASE,
        volume_contraction_params=vol_contr,
        precomputed_swings=sw, precomputed_contractions=contr, precomputed_atr=atr)
    sigs = {dt: s for dt, s in res.items() if s is not None}
    n_raw = len(sigs)
    if tt_data is not None:
        sigs = apply_trend_template_filter(sigs, tt_data)
    n_after_tt = len(sigs)
    vf = det.get("vol_filter", "no_filter")
    if vf != "no_filter":
        sigs = apply_volume_post_filter(sigs, ohlc, vf["window"], vf["threshold"],
                                         forward=vf.get("forward", 0))
    n_final = len(sigs)
    risk = {**RISK_BASE, **exit_cfg}
    results = evaluate_signals_to_trades(sigs, ohlc, risk, grouping="sequential", precomputed_atr=atr)
    n = len(results)
    if n == 0:
        return {"trades": 0, "wins": 0, "WR": 0, "CR": 0, "avg_R": 0, "max_dd": 0,
                "PF": 0, "details": [], "Sharpe": 0, "Exp": 0, "CAGR": 0, "reasons": {},
                "raw_signals": n_raw, "after_tt": n_after_tt, "after_vol": n_final}
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
            "max_dd": mdd, "PF": pf, "Sharpe": sharpe, "Exp": exp, "reasons": reasons, "details": results,
            "raw_signals": n_raw, "after_tt": n_after_tt, "after_vol": n_final}


# ── V3 best #1 configs per ticker ──────────────────────────────

TICKERS = {
    "NVDA": {
        "name": "v3 FWD#1 w3_t1.2_f3 tr=2.5 be=1.5 sl=3%",
        "det": {"atr_mult": 2.0, "use_close_only": False, "max_depth_atr": None,
                "min_total_reduction": 0.60, "lookback_bars": 63, "compression_threshold": 0.95,
                "tolerance": 0.10, "max_depth_pct": 0.25, "ascending_lows_tolerance": 0.01,
                "volume_contraction": None,
                "vol_filter": {"window": 3, "threshold": 1.2, "forward": 3}},
        "exit": {"trailing_atr_multiplier": 2.5, "target_r_multiple": None, "early_exit_days": None,
                 "breakeven_r_multiple": 1.5, "max_stop_loss_pct": 0.03},
    },
    "AMZN": {
        "name": "v3 FWD#1 w3_t1.2_f3 tr=2.0 be=1.5 sl=3% VC",
        "det": {"atr_mult": 3.0, "use_close_only": False, "max_depth_atr": None,
                "min_total_reduction": 0.60, "lookback_bars": 126, "compression_threshold": 0.90,
                "tolerance": 0.15, "max_depth_pct": 0.30, "ascending_lows_tolerance": 0.01,
                "volume_contraction": {"method": "ratio", "ratio_threshold": 0.85},
                "vol_filter": {"window": 3, "threshold": 1.2, "forward": 3}},
        "exit": {"trailing_atr_multiplier": 2.0, "target_r_multiple": None, "early_exit_days": None,
                 "breakeven_r_multiple": 1.5, "max_stop_loss_pct": 0.03},
    },
    "AAPL": {
        "name": "v3 FWD#1 w3_t1.2_f5 tr=3.0 be=1.0 sl=3% VC",
        "det": {"atr_mult": 2.0, "use_close_only": False, "max_depth_atr": 6.0,
                "min_total_reduction": 0.80, "lookback_bars": 126, "compression_threshold": 0.85,
                "tolerance": 0.10, "max_depth_pct": 0.25, "ascending_lows_tolerance": 0.01,
                "volume_contraction": {"method": "ratio", "ratio_threshold": 0.85},
                "vol_filter": {"window": 3, "threshold": 1.2, "forward": 5}},
        "exit": {"trailing_atr_multiplier": 3.0, "target_r_multiple": None, "early_exit_days": None,
                 "breakeven_r_multiple": 1.0, "max_stop_loss_pct": 0.03},
    },
    "GOOGL": {
        "name": "v3 COMP#1 w3_t1.2_f3 tr=2.5 sl=7%",
        "det": {"atr_mult": 2.0, "use_close_only": True, "max_depth_atr": 8,
                "min_total_reduction": 0.80, "lookback_bars": 126, "compression_threshold": 0.95,
                "tolerance": 0.10, "max_depth_pct": 0.25, "ascending_lows_tolerance": 0.08,
                "volume_contraction": None,
                "vol_filter": {"window": 3, "threshold": 1.2, "forward": 3}},
        "exit": {"trailing_atr_multiplier": 2.5, "target_r_multiple": None, "early_exit_days": None,
                 "breakeven_r_multiple": 1.0, "max_stop_loss_pct": 0.07},
    },
    "META": {
        "name": "v3 v2#1 no_filter VC tr=1.5 tg=2R sl=3%",
        "det": {"atr_mult": 2.0, "use_close_only": False, "max_depth_atr": None,
                "min_total_reduction": 0.80, "lookback_bars": 126, "compression_threshold": 0.95,
                "tolerance": 0.10, "max_depth_pct": 0.25, "ascending_lows_tolerance": 0.01,
                "volume_contraction": {"method": "ratio", "ratio_threshold": 0.85},
                "vol_filter": "no_filter"},
        "exit": {"trailing_atr_multiplier": 1.5, "target_r_multiple": 2.0, "early_exit_days": None,
                 "breakeven_r_multiple": 1.0, "max_stop_loss_pct": 0.03},
    },
    "MSFT": {
        "name": "v3 FWD#1 w3_t1.2_f3 tr=3.0 be=1.5 sl=3%",
        "det": {"atr_mult": 2.0, "use_close_only": False, "max_depth_atr": None,
                "min_total_reduction": 0.60, "lookback_bars": 126, "compression_threshold": 0.85,
                "tolerance": 0.15, "max_depth_pct": 0.25, "ascending_lows_tolerance": 0.03,
                "volume_contraction": None,
                "vol_filter": {"window": 3, "threshold": 1.2, "forward": 3}},
        "exit": {"trailing_atr_multiplier": 3.0, "target_r_multiple": None, "early_exit_days": None,
                 "breakeven_r_multiple": 1.5, "max_stop_loss_pct": 0.03},
    },
}


if __name__ == "__main__":
    print(f"{'='*80}")
    print(f"  CONFIGS v3 #1 CON Y SIN TREND TEMPLATE (v4)")
    print(f"  Proposito: ver cuantas senales v3 sobreviven al filtro TT")
    print(f"{'='*80}")

    for ticker, cfg in TICKERS.items():
        daily = pd.read_csv(DATA_DIR / f"{ticker}.csv", parse_dates=["date"], index_col="date")
        train = daily[daily.index < "2020-01-01"]
        test = daily[daily.index >= "2020-01-01"]

        tt_train = evaluate_trend_template(train)
        tt_test = evaluate_trend_template(test)

        bh_test_cr = test["close"].iloc[-1] / test["close"].iloc[0] - 1

        print(f"\n{'─'*80}")
        print(f"  {ticker} — {cfg['name']}")
        print(f"  B&H Test: {bh_test_cr:+.2%}")
        print(f"{'─'*80}")

        for label, data, tt_data in [("TRAIN", train, tt_train), ("TEST", test, tt_test)]:
            ev_no_tt = run_eval(data, cfg["det"], cfg["exit"], tt_data=None)
            ev_tt = run_eval(data, cfg["det"], cfg["exit"], tt_data=tt_data)

            print(f"\n  {label} SIN TT:  senales={ev_no_tt['raw_signals']:>3d} -> vol_filter={ev_no_tt['after_vol']:>3d} -> "
                  f"{ev_no_tt['trades']}T, WR={ev_no_tt['WR']:.0%}, CR={ev_no_tt['CR']:+.2%}")
            if ev_no_tt["details"]:
                for j, (pat, trade) in enumerate(ev_no_tt["details"], 1):
                    entry = pat["first_signal_date"].strftime("%Y-%m-%d")
                    exit_ = trade["exit_date"].strftime("%Y-%m-%d")
                    fwd = ""
                    sig = pat.get("signal_obj")
                    if sig and sig.volume_confirmation.get("forward_confirmed"):
                        fwd = f" [fwd+{sig.volume_confirmation.get('confirmation_delay_days','?')}d]"
                    print(f"           {j:>2d}: {entry}->{exit_} {trade['exit_reason']:<15s} PnL={trade['pnl_pct']:+.2%} R={trade['r_multiple']:+.1f}R{fwd}")

            print(f"  {label} CON TT:  senales={ev_tt['raw_signals']:>3d} -> TT={ev_tt['after_tt']:>3d} -> vol_filter={ev_tt['after_vol']:>3d} -> "
                  f"{ev_tt['trades']}T, WR={ev_tt['WR']:.0%}, CR={ev_tt['CR']:+.2%}")
            if ev_tt["details"]:
                for j, (pat, trade) in enumerate(ev_tt["details"], 1):
                    entry = pat["first_signal_date"].strftime("%Y-%m-%d")
                    exit_ = trade["exit_date"].strftime("%Y-%m-%d")
                    fwd = ""
                    sig = pat.get("signal_obj")
                    if sig and sig.volume_confirmation.get("forward_confirmed"):
                        fwd = f" [fwd+{sig.volume_confirmation.get('confirmation_delay_days','?')}d]"
                    print(f"           {j:>2d}: {entry}->{exit_} {trade['exit_reason']:<15s} PnL={trade['pnl_pct']:+.2%} R={trade['r_multiple']:+.1f}R{fwd}")

            killed = ev_no_tt['raw_signals'] - ev_tt['after_tt']
            pct_killed = killed / ev_no_tt['raw_signals'] * 100 if ev_no_tt['raw_signals'] > 0 else 0
            print(f"  {label} TT FILTRO: {killed}/{ev_no_tt['raw_signals']} senales eliminadas ({pct_killed:.0f}%)")

    print(f"\n{'='*80}")
    print(f"  COMPLETO")
    print(f"{'='*80}")
