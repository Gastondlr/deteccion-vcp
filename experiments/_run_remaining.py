"""Run remaining TrendTemplate thresholds (1.5, 2.0) that timed out."""
import sys
import tempfile
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import mlflow

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from models.configs import ATRZigZagConfig
from vcp_detection.heuristic import ATRZigZagDetector, run_full_vcp_pipeline
from vcp_detection.analysis import (
    group_signals_into_patterns, simulate_trade,
    plot_vcp_pattern, plot_trade_simulation,
)
from stages.trend_template import evaluate_trend_template

SWING_CONFIG = ATRZigZagConfig(atr_length=14, atr_mult=2.0, use_close_only=False)
SEQUENCE_PARAMS = {
    "method": "tolerance", "min_contractions": 2, "max_contractions": 6,
    "lookback_bars": 126, "tolerance": 0.10, "max_depth_pct": 0.35,
    "max_depth_atr": 7, "min_total_reduction": 0.80,
    "max_gap_between_contractions_days": None,
    "require_ascending_lows": True, "ascending_lows_tolerance": 0.10,
}
COMPRESSION_PARAMS = {"method": "ratio", "atr_period": 14, "ratio_threshold": 0.85}
VOLUME_CONTRACTION_PARAMS = {"method": "ratio", "volume_column": "volume", "ratio_threshold": 0.85}
BREAKOUT_PARAMS = {
    "volume_method": "ratio", "volume_ratio_threshold": 1.5,
    "volume_lookback_days": 50, "require_volume_confirmation": True,
    "max_entry_distance_pct": 0.10,
}
RISK_PARAMS = {
    "max_stop_loss_pct": 0.05, "breakeven_r_multiple": 2.0,
    "trailing_sma_period": 20, "trailing_volume_factor": 1.5,
    "trailing_stop_method": "atr", "trailing_atr_period": 14,
    "trailing_atr_multiplier": 3.0, "max_bars_without_progress": 20,
    "min_progress_r": 0.5, "early_exit_days": 3,
}

DATA_DIR = project_root / "data" / "csv"
TICKERS = sorted([p.stem for p in DATA_DIR.glob("*.csv")])

USE_TREND_TEMPLATE = True
USE_VOLUME_CONTRACTION = True

ALL_PARAMS_BASE = {
    "atr_length": SWING_CONFIG.atr_length, "atr_mult": SWING_CONFIG.atr_mult,
    "use_close_only": SWING_CONFIG.use_close_only,
    "seq_method": SEQUENCE_PARAMS["method"],
    "min_contractions": SEQUENCE_PARAMS["min_contractions"],
    "max_contractions": SEQUENCE_PARAMS["max_contractions"],
    "lookback_bars": SEQUENCE_PARAMS["lookback_bars"],
    "tolerance": SEQUENCE_PARAMS["tolerance"],
    "max_depth_pct": str(SEQUENCE_PARAMS["max_depth_pct"]),
    "max_depth_atr": str(SEQUENCE_PARAMS.get("max_depth_atr")),
    "min_total_reduction": str(SEQUENCE_PARAMS["min_total_reduction"]),
    "max_gap_days": str(SEQUENCE_PARAMS["max_gap_between_contractions_days"]),
    "require_ascending_lows": SEQUENCE_PARAMS["require_ascending_lows"],
    "ascending_lows_tolerance": SEQUENCE_PARAMS["ascending_lows_tolerance"],
    "compression_method": COMPRESSION_PARAMS["method"],
    "compression_threshold": COMPRESSION_PARAMS["ratio_threshold"],
    "use_volume_contraction": USE_VOLUME_CONTRACTION,
    "vol_contraction_method": VOLUME_CONTRACTION_PARAMS["method"],
    "vol_contraction_threshold": VOLUME_CONTRACTION_PARAMS["ratio_threshold"],
    "max_entry_distance_pct": str(BREAKOUT_PARAMS["max_entry_distance_pct"]),
    "max_stop_loss_pct": RISK_PARAMS["max_stop_loss_pct"],
    "breakeven_r_multiple": RISK_PARAMS["breakeven_r_multiple"],
    "trailing_sma_period": RISK_PARAMS["trailing_sma_period"],
    "trailing_volume_factor": RISK_PARAMS["trailing_volume_factor"],
    "trailing_stop_method": RISK_PARAMS.get("trailing_stop_method", "sma"),
    "trailing_atr_period": RISK_PARAMS.get("trailing_atr_period", 14),
    "trailing_atr_multiplier": RISK_PARAMS.get("trailing_atr_multiplier", 3.0),
    "max_bars_without_progress": str(RISK_PARAMS.get("max_bars_without_progress")),
    "min_progress_r": RISK_PARAMS.get("min_progress_r", 0.5),
    "early_exit_days": str(RISK_PARAMS.get("early_exit_days")),
}


def load_ohlc(ticker):
    return pd.read_csv(DATA_DIR / f"{ticker}.csv", parse_dates=["date"], index_col="date")

def compute_trade_max_drawdown(ohlc, entry_date, exit_date):
    tc = ohlc.loc[entry_date:exit_date, "close"]
    if len(tc) < 2: return 0.0
    return float(((tc - tc.cummax()) / tc.cummax()).min())

def compute_asset_max_drawdown(ohlc):
    c = ohlc["close"]; return float(((c - c.cummax()) / c.cummax()).min())

def compute_in_trade_sharpe(ohlc, trades, ann=252.0):
    dr = []
    for t in trades:
        tc = ohlc.loc[t["pattern"]["first_signal_date"]:t["exit_date"], "close"]
        if len(tc) >= 2: dr.append(tc.pct_change().dropna())
    if not dr: return 0.0
    ar = pd.concat(dr)
    if len(ar) < 2 or ar.std() == 0: return 0.0
    return float(ar.mean() / ar.std() * np.sqrt(ann))

def run_ticker_analysis(ticker, ohlc, template_df, breakout_params, risk_params):
    sd = ATRZigZagDetector(SWING_CONFIG)
    vp = VOLUME_CONTRACTION_PARAMS if USE_VOLUME_CONTRACTION else None
    results = run_full_vcp_pipeline(ohlc=ohlc, swing_detector=sd,
        sequence_params=SEQUENCE_PARAMS, compression_params=COMPRESSION_PARAMS,
        breakout_params=breakout_params, volume_contraction_params=vp)
    sr = {dt: s for dt, s in results.items() if s is not None}
    asig, nf = {}, 0
    if USE_TREND_TEMPLATE and template_df is not None:
        for dt, s in sr.items():
            if dt in template_df.index and bool(template_df.loc[dt, "trend_template"]):
                asig[dt] = s
            else: nf += 1
    else: asig = dict(sr)
    patterns = group_signals_into_patterns(asig, risk_params=risk_params)
    trades = []
    for p in patterns:
        t = simulate_trade(ohlc, p, risk_params); t["pattern"] = p
        t["max_drawdown"] = compute_trade_max_drawdown(ohlc, p["first_signal_date"], t["exit_date"])
        trades.append(t)
    nt = len(trades)
    if nt > 0:
        w = sum(1 for t in trades if t["pnl_pct"] > 0)
        cr = float(np.prod([1+t["pnl_pct"] for t in trades])-1)
        ar = float(np.mean([t["r_multiple"] for t in trades]))
        wd = float(min(t["max_drawdown"] for t in trades))
        ad = float(np.mean([t["max_drawdown"] for t in trades]))
        ae = float(np.mean([t["pattern"].get("metadata",{}).get("entry_distance_pct",0) for t in trades]))
    else: w,cr,ar,wd,ad,ae = 0,0,0,0,0,0
    return {"signals":asig,"patterns":patterns,"trades":trades,"metrics":{
        "n_signals_raw":len(sr),"n_signals":len(asig),"n_filtered_by_template":nf,
        "n_patterns":len(patterns),"n_trades":nt,"winrate":w/nt if nt else 0,
        "cumulative_return":cr,"avg_r_multiple":ar,"worst_trade_drawdown":wd,
        "avg_trade_drawdown":ad,"asset_max_drawdown":compute_asset_max_drawdown(ohlc),
        "avg_entry_distance":ae,"sharpe_ratio":compute_in_trade_sharpe(ohlc,trades)}}

def build_trade_table(trades, ticker):
    rows = []
    for i,t in enumerate(trades,1):
        ed = t["pattern"].get("metadata",{}).get("entry_distance_pct",None)
        rows.append({"ticker":ticker,"trade_num":i,
            "entry_date":t["pattern"]["first_signal_date"].strftime("%Y-%m-%d"),
            "exit_date":t["exit_date"].strftime("%Y-%m-%d"),
            "exit_reason":t["exit_reason"],"duration_days":t["duration_days"],
            "entry_price":t["pattern"]["entry_price"],"exit_price":t["exit_price"],
            "pnl_pct":t["pnl_pct"],"r_multiple":t["r_multiple"],"max_r":t["max_r"],
            "max_drawdown":t["max_drawdown"],"entry_distance_pct":ed,
            "stop_method":t["pattern"]["stop_method"],
            "n_contractions":t["pattern"]["n_contractions"],
            "atr_ratio":t["pattern"]["atr_ratio"]})
    return pd.DataFrame(rows)

# Pre-compute template
print("Pre-computing trend template...")
template_cache = {}
for ticker in TICKERS:
    template_cache[ticker] = evaluate_trend_template(load_ohlc(ticker))
print(f"Done for {len(TICKERS)} tickers")

mlflow.set_tracking_uri(str(project_root / "mlruns"))
mlflow.set_experiment("VCP_FullFilters_TrendTemplate")

REMAINING_THRESHOLDS = [1.5, 2.0]

for threshold in REMAINING_THRESHOLDS:
    breakout_params = {**BREAKOUT_PARAMS, "volume_ratio_threshold": threshold,
                       "require_volume_confirmation": threshold > 0}
    config_name = f"threshold_{threshold}"
    print(f"\n{'='*60}\nCONFIG: {config_name}\n{'='*60}")

    all_params = {**ALL_PARAMS_BASE, "use_trend_template": True,
                  "volume_ratio_threshold": threshold,
                  "require_volume_confirmation": threshold > 0}

    with mlflow.start_run(run_name=config_name) as parent_run:
        mlflow.log_params(all_params)
        ticker_summaries = []
        all_trades_for_config = []

        for ticker in TICKERS:
            print(f"  {ticker}...", end=" ")
            ohlc = load_ohlc(ticker)
            template_df = template_cache.get(ticker)

            with mlflow.start_run(run_name=ticker, nested=True):
                mlflow.log_params({**all_params, "ticker": ticker, "n_bars": len(ohlc)})
                analysis = run_ticker_analysis(ticker, ohlc, template_df, breakout_params, RISK_PARAMS)
                m = analysis["metrics"]
                nw = sum(1 for t in analysis["trades"] if t["pnl_pct"] > 0)
                nl = m["n_trades"] - nw

                mlflow.log_metrics({
                    "n_signals_raw":m["n_signals_raw"],"n_signals":m["n_signals"],
                    "n_filtered_by_template":m["n_filtered_by_template"],
                    "n_patterns":m["n_patterns"],"n_trades":m["n_trades"],
                    "n_wins":nw,"n_losses":nl,"winrate":m["winrate"],
                    "cumulative_return":m["cumulative_return"],
                    "avg_r_multiple":m["avg_r_multiple"],
                    "worst_trade_drawdown":m["worst_trade_drawdown"],
                    "avg_trade_drawdown":m["avg_trade_drawdown"],
                    "asset_max_drawdown":m["asset_max_drawdown"],
                    "avg_entry_distance":m["avg_entry_distance"],
                    "sharpe_ratio":m["sharpe_ratio"],
                })

                with tempfile.TemporaryDirectory() as tmpdir:
                    for j, pat in enumerate(analysis["patterns"], 1):
                        pp = Path(tmpdir)/f"pattern_{j}.png"
                        plot_vcp_pattern(ohlc, pat, pattern_number=j, ticker=ticker, save_path=str(pp))
                        mlflow.log_artifact(str(pp), "pattern_plots")
                    for j, (pat, trade) in enumerate(zip(analysis["patterns"], analysis["trades"]), 1):
                        tp = Path(tmpdir)/f"trade_{j}.png"
                        plot_trade_simulation(ohlc, pat, trade, pattern_number=j,
                            risk_params=RISK_PARAMS, ticker=ticker, save_path=str(tp))
                        mlflow.log_artifact(str(tp), "trade_plots")
                    if analysis["trades"]:
                        tdf = build_trade_table(analysis["trades"], ticker)
                        tcp = Path(tmpdir)/"trades.csv"; tdf.to_csv(tcp, index=False)
                        mlflow.log_artifact(str(tcp), "tables")
                        all_trades_for_config.append(tdf)

                ticker_summaries.append({"ticker":ticker,**{k:m[k] for k in m},
                    "n_wins":nw,"n_losses":nl})
                print(f"{m['n_trades']} trades ({nw}W/{nl}L), WR={m['winrate']:.0%}, CR={m['cumulative_return']:+.1%}")

        sdf = pd.DataFrame(ticker_summaries)
        twt = sdf[sdf["n_trades"]>0]
        agg = {
            "total_signals_raw":int(sdf["n_signals_raw"].sum()),
            "total_signals_filtered":int(sdf["n_signals"].sum()),
            "total_filtered_by_template":int(sdf["n_filtered_by_template"].sum()),
            "total_patterns":int(sdf["n_patterns"].sum()),
            "total_trades":int(sdf["n_trades"].sum()),
            "total_wins":int(sdf["n_wins"].sum()),
            "total_losses":int(sdf["n_losses"].sum()),
            "tickers_with_patterns":int((sdf["n_patterns"]>0).sum()),
            "tickers_with_trades":int((sdf["n_trades"]>0).sum()),
            "avg_winrate":float(twt["winrate"].mean()) if len(twt)>0 else 0,
            "median_winrate":float(twt["winrate"].median()) if len(twt)>0 else 0,
            "avg_cumulative_return":float(twt["cumulative_return"].mean()) if len(twt)>0 else 0,
            "avg_r_multiple":float(twt["avg_r_multiple"].mean()) if len(twt)>0 else 0,
            "worst_trade_drawdown":float(twt["worst_trade_drawdown"].min()) if len(twt)>0 else 0,
            "avg_trade_drawdown":float(twt["avg_trade_drawdown"].mean()) if len(twt)>0 else 0,
            "avg_entry_distance":float(twt["avg_entry_distance"].mean()) if len(twt)>0 else 0,
            "avg_sharpe_ratio":float(twt["sharpe_ratio"].mean()) if len(twt)>0 else 0,
        }
        mlflow.log_metrics(agg)
        print(f"\n  AGREGADO: {agg['total_trades']} trades ({agg['total_wins']}W/{agg['total_losses']}L), "
              f"avg WR={agg['avg_winrate']:.0%}, avg CR={agg['avg_cumulative_return']:+.1%}")

print("\nCompleto!")
