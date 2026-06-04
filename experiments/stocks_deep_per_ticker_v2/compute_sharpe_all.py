"""Compute Sharpe and full metrics for top configs across AAPL, AMZN, GOOGL."""
import functools, sys, numpy as np, pandas as pd
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

def apply_volume_post_filter(signals, ohlc, window, threshold, lookback_days=50):
    filtered = {}
    for dt, sig in signals.items():
        eval_loc = ohlc.index.get_loc(dt)
        lookback_start = max(0, eval_loc - lookback_days)
        vol_recent = ohlc["volume"].iloc[lookback_start:eval_loc]
        vol_avg = float(vol_recent.mean()) if len(vol_recent) > 0 else 0.0
        if vol_avg <= 0: continue
        win_start = max(0, eval_loc - window + 1)
        win_vols = ohlc["volume"].iloc[win_start:eval_loc + 1]
        if any(float(v) >= threshold * vol_avg for v in win_vols):
            filtered[dt] = sig
    return filtered

VOL_FILTERS = {
    "no_filter": (None, None), "w1_t1.2": (1, 1.2), "w1_t1.5": (1, 1.5),
    "w3_t1.2": (3, 1.2), "w3_t1.5": (3, 1.5), "w5_t1.2": (5, 1.2), "w5_t1.5": (5, 1.5),
}

def run_and_metrics(ohlc, det, exit_cfg):
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
    vf_name = det["vol_filter"]
    w, t = VOL_FILTERS[vf_name]
    if w is not None:
        sigs = apply_volume_post_filter(sigs, ohlc, w, t)
    risk = {**RISK_BASE, **exit_cfg}
    results = evaluate_signals_to_trades(sigs, ohlc, risk, grouping="sequential", precomputed_atr=atr)
    n = len(results)
    if n == 0:
        return None
    trades = [t for _, t in results]
    wins = sum(1 for t in trades if t["pnl_pct"] > 0)
    cr = float(np.prod([1 + t["pnl_pct"] for t in trades]) - 1)
    avg_r = float(np.mean([t["r_multiple"] for t in trades]))
    years = len(ohlc) / 252
    cagr = (1 + cr) ** (1 / years) - 1 if years > 0 and cr > -1 else 0
    eq, peak, max_dd = 1.0, 1.0, 0.0
    for t in trades:
        eq *= (1 + t["pnl_pct"]); peak = max(peak, eq); max_dd = min(max_dd, (eq - peak) / peak)
    pf_w = sum(t["pnl_pct"] for t in trades if t["pnl_pct"] > 0)
    pf_l = abs(sum(t["pnl_pct"] for t in trades if t["pnl_pct"] <= 0))
    pf = pf_w / pf_l if pf_l > 0 else float("inf")
    total_days = sum(t["duration_days"] for t in trades)
    exposure = total_days / len(ohlc)
    # Sharpe: annualized from per-trade returns
    rets = np.array([t["pnl_pct"] for t in trades])
    trades_per_year = n / years if years > 0 else n
    sharpe = (rets.mean() / rets.std()) * np.sqrt(trades_per_year) if rets.std() > 0 else 0
    return {"T": n, "W": wins, "L": n - wins, "WR": wins / n, "CR": cr, "CAGR": cagr,
            "MaxDD": max_dd, "Sharpe": sharpe, "avgR": avg_r, "PF": pf, "Exp": exposure}

# ── All configs to evaluate ──────────────────────────────────

TICKERS = {
    "AAPL": [
        {"name": "COMP#1 tr=2.0 tg=2R sl=5% no_filter VC",
         "det": {"atr_mult": 2.0, "use_close_only": False, "max_depth_atr": 6, "min_total_reduction": 0.80,
                 "lookback_bars": 126, "compression_threshold": 0.85, "tolerance": 0.10, "max_depth_pct": 0.25,
                 "ascending_lows_tolerance": 0.01, "volume_contraction": {"method": "ratio", "ratio_threshold": 0.85},
                 "vol_filter": "no_filter"},
         "exit": {"trailing_atr_multiplier": 2.0, "target_r_multiple": 2.0, "early_exit_days": None,
                  "breakeven_r_multiple": 1.0, "max_stop_loss_pct": 0.05}},
        {"name": "COMP#2 tr=2.0 tg=2R sl=3% be=1.5 w3_t1.2",
         "det": {"atr_mult": 2.0, "use_close_only": False, "max_depth_atr": 6, "min_total_reduction": 0.80,
                 "lookback_bars": 126, "compression_threshold": 0.85, "tolerance": 0.10, "max_depth_pct": 0.25,
                 "ascending_lows_tolerance": 0.01, "volume_contraction": None,
                 "vol_filter": "w3_t1.2"},
         "exit": {"trailing_atr_multiplier": 2.0, "target_r_multiple": 2.0, "early_exit_days": None,
                  "breakeven_r_multiple": 1.5, "max_stop_loss_pct": 0.03}},
        {"name": "COMP#3 tr=2.0 tg=2R sl=5% no_filter comp=0.85",
         "det": {"atr_mult": 2.0, "use_close_only": False, "max_depth_atr": 6, "min_total_reduction": 0.80,
                 "lookback_bars": 126, "compression_threshold": 0.85, "tolerance": 0.10, "max_depth_pct": 0.25,
                 "ascending_lows_tolerance": 0.01, "volume_contraction": None,
                 "vol_filter": "no_filter"},
         "exit": {"trailing_atr_multiplier": 2.0, "target_r_multiple": 2.0, "early_exit_days": None,
                  "breakeven_r_multiple": 1.0, "max_stop_loss_pct": 0.05}},
        {"name": "CR#1 tr=2.0 tg=2R sl=5% no_filter comp=0.95",
         "det": {"atr_mult": 2.0, "use_close_only": False, "max_depth_atr": 6, "min_total_reduction": 0.80,
                 "lookback_bars": 126, "compression_threshold": 0.95, "tolerance": 0.10, "max_depth_pct": 0.25,
                 "ascending_lows_tolerance": 0.01, "volume_contraction": None,
                 "vol_filter": "no_filter"},
         "exit": {"trailing_atr_multiplier": 2.0, "target_r_multiple": 2.0, "early_exit_days": None,
                  "breakeven_r_multiple": 1.0, "max_stop_loss_pct": 0.05}},
        {"name": "WR#1 tr=1.0 tg=3R sl=3% w5_t1.2",
         "det": {"atr_mult": 2.0, "use_close_only": False, "max_depth_atr": None, "min_total_reduction": 0.60,
                 "lookback_bars": 63, "compression_threshold": 0.85, "tolerance": 0.10, "max_depth_pct": 0.25,
                 "ascending_lows_tolerance": 0.01, "volume_contraction": None,
                 "vol_filter": "w5_t1.2"},
         "exit": {"trailing_atr_multiplier": 1.0, "target_r_multiple": 3.0, "early_exit_days": None,
                  "breakeven_r_multiple": 1.0, "max_stop_loss_pct": 0.03}},
    ],
    "AMZN": [
        {"name": "COMP#1 tr=2.0 tg=None be=1.5 sl=3% w3_t1.2 VC",
         "det": {"atr_mult": 3.0, "use_close_only": False, "max_depth_atr": None, "min_total_reduction": 0.60,
                 "lookback_bars": 126, "compression_threshold": 0.90, "tolerance": 0.15, "max_depth_pct": 0.30,
                 "ascending_lows_tolerance": 0.01, "volume_contraction": {"method": "ratio", "ratio_threshold": 0.85},
                 "vol_filter": "w3_t1.2"},
         "exit": {"trailing_atr_multiplier": 2.0, "target_r_multiple": None, "early_exit_days": None,
                  "breakeven_r_multiple": 1.5, "max_stop_loss_pct": 0.03}},
        {"name": "COMP#3 tr=2.0 tg=None be=1.5 sl=3% w5_t1.2 VC red=0.80",
         "det": {"atr_mult": 3.0, "use_close_only": False, "max_depth_atr": None, "min_total_reduction": 0.80,
                 "lookback_bars": 126, "compression_threshold": 0.90, "tolerance": 0.15, "max_depth_pct": 0.30,
                 "ascending_lows_tolerance": 0.01, "volume_contraction": {"method": "ratio", "ratio_threshold": 0.85},
                 "vol_filter": "w5_t1.2"},
         "exit": {"trailing_atr_multiplier": 2.0, "target_r_multiple": None, "early_exit_days": None,
                  "breakeven_r_multiple": 1.5, "max_stop_loss_pct": 0.03}},
        {"name": "CR#1 tr=2.0 tg=3R early=5 sl=5% no_filter",
         "det": {"atr_mult": 2.0, "use_close_only": True, "max_depth_atr": 8, "min_total_reduction": 0.80,
                 "lookback_bars": 126, "compression_threshold": 0.95, "tolerance": 0.10, "max_depth_pct": 0.30,
                 "ascending_lows_tolerance": 0.03, "volume_contraction": None,
                 "vol_filter": "no_filter"},
         "exit": {"trailing_atr_multiplier": 2.0, "target_r_multiple": 3.0, "early_exit_days": 5,
                  "breakeven_r_multiple": 1.0, "max_stop_loss_pct": 0.05}},
        {"name": "WR#1 tr=2.5 tg=2R sl=3% w5_t1.2",
         "det": {"atr_mult": 2.0, "use_close_only": True, "max_depth_atr": None, "min_total_reduction": 0.60,
                 "lookback_bars": 63, "compression_threshold": 0.95, "tolerance": 0.10, "max_depth_pct": 0.30,
                 "ascending_lows_tolerance": 0.03, "volume_contraction": None,
                 "vol_filter": "w5_t1.2"},
         "exit": {"trailing_atr_multiplier": 2.5, "target_r_multiple": 2.0, "early_exit_days": None,
                  "breakeven_r_multiple": 1.0, "max_stop_loss_pct": 0.03}},
        {"name": "WR#2 tr=2.5 tg=3R be=1.5 sl=3% w3_t1.2 VC",
         "det": {"atr_mult": 3.0, "use_close_only": False, "max_depth_atr": 8, "min_total_reduction": 0.80,
                 "lookback_bars": 63, "compression_threshold": 0.85, "tolerance": 0.15, "max_depth_pct": 0.30,
                 "ascending_lows_tolerance": 0.01, "volume_contraction": {"method": "ratio", "ratio_threshold": 0.85},
                 "vol_filter": "w3_t1.2"},
         "exit": {"trailing_atr_multiplier": 2.5, "target_r_multiple": 3.0, "early_exit_days": None,
                  "breakeven_r_multiple": 1.5, "max_stop_loss_pct": 0.03}},
    ],
    "GOOGL": [
        {"name": "COMP#1 tr=2.5 tg=None sl=7% w3_t1.2",
         "det": {"atr_mult": 2.0, "use_close_only": True, "max_depth_atr": 8, "min_total_reduction": 0.80,
                 "lookback_bars": 126, "compression_threshold": 0.95, "tolerance": 0.10, "max_depth_pct": 0.25,
                 "ascending_lows_tolerance": 0.08, "volume_contraction": None,
                 "vol_filter": "w3_t1.2"},
         "exit": {"trailing_atr_multiplier": 2.5, "target_r_multiple": None, "early_exit_days": None,
                  "breakeven_r_multiple": 1.0, "max_stop_loss_pct": 0.07}},
        {"name": "COMP#2 tr=2.5 tg=None sl=7% w1_t1.2",
         "det": {"atr_mult": 2.0, "use_close_only": True, "max_depth_atr": 8, "min_total_reduction": 0.80,
                 "lookback_bars": 126, "compression_threshold": 0.95, "tolerance": 0.10, "max_depth_pct": 0.25,
                 "ascending_lows_tolerance": 0.08, "volume_contraction": None,
                 "vol_filter": "w1_t1.2"},
         "exit": {"trailing_atr_multiplier": 2.5, "target_r_multiple": None, "early_exit_days": None,
                  "breakeven_r_multiple": 1.0, "max_stop_loss_pct": 0.07}},
        {"name": "COMP#3 tr=2.5 tg=None sl=7% w3_t1.2 alt=0.01",
         "det": {"atr_mult": 2.0, "use_close_only": True, "max_depth_atr": 8, "min_total_reduction": 0.80,
                 "lookback_bars": 126, "compression_threshold": 0.95, "tolerance": 0.10, "max_depth_pct": 0.25,
                 "ascending_lows_tolerance": 0.01, "volume_contraction": None,
                 "vol_filter": "w3_t1.2"},
         "exit": {"trailing_atr_multiplier": 2.5, "target_r_multiple": None, "early_exit_days": None,
                  "breakeven_r_multiple": 1.0, "max_stop_loss_pct": 0.07}},
        {"name": "CR#1 tr=2.5 tg=2R early=3 be=1.5 sl=3% no_filter",
         "det": {"atr_mult": 2.0, "use_close_only": True, "max_depth_atr": 8, "min_total_reduction": 0.80,
                 "lookback_bars": 126, "compression_threshold": 0.95, "tolerance": 0.10, "max_depth_pct": 0.25,
                 "ascending_lows_tolerance": 0.08, "volume_contraction": None,
                 "vol_filter": "no_filter"},
         "exit": {"trailing_atr_multiplier": 2.5, "target_r_multiple": 2.0, "early_exit_days": 3,
                  "breakeven_r_multiple": 1.5, "max_stop_loss_pct": 0.03}},
        {"name": "WR#1 tr=2.5 tg=3R be=1.0 sl=5% w5_t1.2 VC",
         "det": {"atr_mult": 2.0, "use_close_only": True, "max_depth_atr": 8, "min_total_reduction": 0.80,
                 "lookback_bars": 126, "compression_threshold": 0.85, "tolerance": 0.10, "max_depth_pct": 0.25,
                 "ascending_lows_tolerance": 0.08, "volume_contraction": {"method": "ratio", "ratio_threshold": 0.85},
                 "vol_filter": "w5_t1.2"},
         "exit": {"trailing_atr_multiplier": 2.5, "target_r_multiple": 3.0, "early_exit_days": None,
                  "breakeven_r_multiple": 1.0, "max_stop_loss_pct": 0.05}},
    ],
}

if __name__ == "__main__":
    for ticker, configs in TICKERS.items():
        daily = pd.read_csv(DATA_DIR / f"{ticker}.csv", parse_dates=["date"], index_col="date")
        train = daily[daily.index < "2020-01-01"]

        bh_cr = train["close"].iloc[-1] / train["close"].iloc[0] - 1
        bh_dd = ((train["close"] - train["close"].cummax()) / train["close"].cummax()).min()
        bh_ret = train["close"].pct_change().dropna()
        bh_sharpe = (bh_ret.mean() / bh_ret.std()) * np.sqrt(252) if bh_ret.std() > 0 else 0
        bh_cagr = (1 + bh_cr) ** (1 / (len(train) / 252)) - 1

        print(f"\n{'='*80}")
        print(f"  {ticker} — Metricas completas (Train)")
        print(f"{'='*80}")
        print(f"  Buy & Hold: CR={bh_cr:+.2%}, CAGR={bh_cagr:.2%}, MaxDD={bh_dd:.2%}, Sharpe={bh_sharpe:.2f}")

        results = []
        for cfg in configs:
            m = run_and_metrics(train, cfg["det"], cfg["exit"])
            if m:
                results.append({"name": cfg["name"], **m})
                print(f"  {cfg['name']}: T={m['T']} WR={m['WR']:.0%} CR={m['CR']:+.2%} "
                      f"CAGR={m['CAGR']:.2%} MaxDD={m['MaxDD']:.2%} Sharpe={m['Sharpe']:.2f} "
                      f"avgR={m['avgR']:+.2f} PF={m['PF']:.1f} Exp={m['Exp']:.0%}")

        print(f"\n  --- Top 3 por Sharpe ---")
        by_sharpe = sorted(results, key=lambda x: x["Sharpe"], reverse=True)
        for i, r in enumerate(by_sharpe[:3], 1):
            print(f"  {i}. Sharpe={r['Sharpe']:.2f} | {r['name']}: T={r['T']} WR={r['WR']:.0%} "
                  f"CR={r['CR']:+.2%} MaxDD={r['MaxDD']:.2%} avgR={r['avgR']:+.2f} PF={r['PF']:.1f}")
