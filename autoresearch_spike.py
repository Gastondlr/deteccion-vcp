"""Spike mínimo para validar integración Optuna + pipeline VCP.

Fase 2: Reproducir el experimento conocido con 3 tickers.
Fase 3: Stress test del search space con 50 random trials.
Fase 4: Mini-optimización con Optuna (5 trials).
"""

from __future__ import annotations

import random
import time

import numpy as np
import pandas as pd

from models.configs import ATRZigZagConfig
from vcp_detection.heuristic import ATRZigZagDetector, run_full_vcp_pipeline
from vcp_detection.analysis import group_signals_into_patterns, simulate_trade

DATA_DIR = "data/csv"
TICKERS = ["AAPL", "AMZN", "NVDA"]


def load_ohlc(ticker: str) -> pd.DataFrame:
    return pd.read_csv(f"{DATA_DIR}/{ticker}.csv", parse_dates=["date"], index_col="date")


def run_pipeline_for_ticker(
    ohlc: pd.DataFrame,
    swing_config: ATRZigZagConfig,
    sequence_params: dict,
    compression_params: dict,
    breakout_params: dict,
    volume_contraction_params: dict | None,
    risk_params: dict,
    max_gap_days: int = 30,
) -> list[dict]:
    detector = ATRZigZagDetector(swing_config)

    results = run_full_vcp_pipeline(
        ohlc=ohlc,
        swing_detector=detector,
        sequence_params=sequence_params,
        compression_params=compression_params,
        breakout_params=breakout_params,
        volume_contraction_params=volume_contraction_params,
    )

    all_signals = {dt: sig for dt, sig in results.items() if sig is not None}
    patterns = group_signals_into_patterns(all_signals, risk_params=risk_params, max_gap_days=max_gap_days)

    trades = []
    for p in patterns:
        trade = simulate_trade(ohlc, p, risk_params)
        trade["pattern"] = p
        trades.append(trade)

    return trades


def fase2_reproduce_experiment():
    """Reproduce el experimento original con params conocidos sobre 3 tickers."""
    swing_config = ATRZigZagConfig(atr_length=14, atr_mult=2.0, use_close_only=False)

    sequence_params = {
        "method": "tolerance",
        "min_contractions": 2,
        "max_contractions": 6,
        "lookback_bars": 126,
        "tolerance": 0.10,
        "max_depth_pct": 0.35,
        "min_total_reduction": 0.80,
        "max_gap_between_contractions_days": None,
    }

    compression_params = {
        "method": "ratio",
        "atr_period": 14,
        "ratio_threshold": 0.85,
    }

    volume_contraction_params = {
        "method": "ratio",
        "volume_column": "volume",
        "ratio_threshold": 0.85,
    }

    breakout_params = {
        "volume_method": "ratio",
        "volume_ratio_threshold": 1.5,
        "volume_lookback_days": 50,
        "require_volume_confirmation": True,
    }

    risk_params = {
        "max_stop_loss_pct": 0.07,
        "breakeven_r_multiple": 2.0,
        "trailing_sma_period": 20,
        "trailing_volume_factor": 1.5,
    }

    max_gap_days = 30

    print("=" * 70)
    print("FASE 2: Reproducción del experimento conocido (volume_ratio_threshold=1.5)")
    print("=" * 70)

    all_trades = []
    for ticker in TICKERS:
        ohlc = load_ohlc(ticker)
        trades = run_pipeline_for_ticker(
            ohlc=ohlc,
            swing_config=swing_config,
            sequence_params=sequence_params,
            compression_params=compression_params,
            breakout_params=breakout_params,
            volume_contraction_params=volume_contraction_params,
            risk_params=risk_params,
            max_gap_days=max_gap_days,
        )

        n_trades = len(trades)
        if n_trades > 0:
            wins = sum(1 for t in trades if t["pnl_pct"] > 0)
            avg_r = np.mean([t["r_multiple"] for t in trades])
            print(f"  {ticker}: {n_trades} trades, win_rate={wins/n_trades:.1%}, avg_R={avg_r:+.2f}")
        else:
            print(f"  {ticker}: 0 trades")

        all_trades.extend(trades)

    print("-" * 70)
    n_total = len(all_trades)
    if n_total > 0:
        total_wins = sum(1 for t in all_trades if t["pnl_pct"] > 0)
        global_win_rate = total_wins / n_total
        global_expectancy = float(np.mean([t["r_multiple"] for t in all_trades]))
        print(f"  GLOBAL: {n_total} trades, win_rate={global_win_rate:.1%}, expectancy(avg_R)={global_expectancy:+.3f}")
    else:
        print("  GLOBAL: 0 trades")
    print("=" * 70)


RISK_PARAMS = {
    "max_stop_loss_pct": 0.07,
    "breakeven_r_multiple": 2.0,
    "trailing_sma_period": 20,
    "trailing_volume_factor": 1.5,
}


def sample_random_params(rng: random.Random) -> dict:
    atr_length = rng.randint(10, 25)
    atr_mult = rng.choice([x / 4 for x in range(6, 15)])  # 1.5 to 3.5 step 0.25
    min_contractions = rng.randint(2, 3)
    max_contractions = rng.randint(max(min_contractions + 2, 5), 7)
    lookback_bars = rng.choice(range(80, 141, 10))
    tolerance = rng.choice([x / 1000 for x in range(50, 201, 25)])  # 0.05 to 0.20 step 0.025
    max_depth_pct = round(rng.uniform(0.25, 0.45), 3)
    min_total_reduction = round(rng.uniform(0.65, 0.90), 3)
    compression_threshold = round(rng.uniform(0.70, 0.95), 3)
    vol_contraction_threshold = round(rng.uniform(0.75, 0.95), 3)
    volume_ratio_threshold = round(rng.uniform(1.3, 2.0), 2)
    max_gap_days = rng.randint(20, 40)

    return {
        "swing_config": ATRZigZagConfig(
            atr_length=atr_length, atr_mult=atr_mult, use_close_only=False,
        ),
        "sequence_params": {
            "method": "tolerance",
            "min_contractions": min_contractions,
            "max_contractions": max_contractions,
            "lookback_bars": lookback_bars,
            "tolerance": tolerance,
            "max_depth_pct": max_depth_pct,
            "min_total_reduction": min_total_reduction,
            "max_gap_between_contractions_days": None,
        },
        "compression_params": {
            "method": "ratio",
            "atr_period": 14,
            "ratio_threshold": compression_threshold,
        },
        "volume_contraction_params": {
            "method": "ratio",
            "volume_column": "volume",
            "ratio_threshold": vol_contraction_threshold,
        },
        "breakout_params": {
            "volume_method": "ratio",
            "volume_ratio_threshold": volume_ratio_threshold,
            "volume_lookback_days": 50,
            "require_volume_confirmation": True,
        },
        "max_gap_days": max_gap_days,
        "flat": {
            "atr_length": atr_length,
            "atr_mult": atr_mult,
            "min_contractions": min_contractions,
            "max_contractions": max_contractions,
            "lookback_bars": lookback_bars,
            "tolerance": tolerance,
            "max_depth_pct": max_depth_pct,
            "min_total_reduction": min_total_reduction,
            "compression_threshold": compression_threshold,
            "vol_contraction_threshold": vol_contraction_threshold,
            "volume_ratio_threshold": volume_ratio_threshold,
            "max_gap_days": max_gap_days,
        },
    }


def compute_score(expectancy: float, n_trades: int) -> float:
    if n_trades == 0:
        return -1.0
    raw = expectancy * np.sqrt(n_trades)
    if n_trades >= 5:
        return raw
    return raw * (n_trades / 5)


def fase3_stress_test(n_trials: int = 50, seed: int = 42):
    print("=" * 70)
    print(f"FASE 3: Stress test del search space ({n_trials} random trials)")
    print("=" * 70)

    ohlc_cache = {ticker: load_ohlc(ticker) for ticker in TICKERS}

    rng = random.Random(seed)
    trial_results = []

    t0 = time.time()
    for i in range(n_trials):
        params = sample_random_params(rng)

        all_trades = []
        for ticker in TICKERS:
            trades = run_pipeline_for_ticker(
                ohlc=ohlc_cache[ticker],
                swing_config=params["swing_config"],
                sequence_params=params["sequence_params"],
                compression_params=params["compression_params"],
                breakout_params=params["breakout_params"],
                volume_contraction_params=params["volume_contraction_params"],
                risk_params=RISK_PARAMS,
                max_gap_days=params["max_gap_days"],
            )
            all_trades.extend(trades)

        n_trades = len(all_trades)
        if n_trades > 0:
            expectancy = float(np.mean([t["r_multiple"] for t in all_trades]))
            win_rate = sum(1 for t in all_trades if t["pnl_pct"] > 0) / n_trades
        else:
            expectancy = 0.0
            win_rate = 0.0

        score = compute_score(expectancy, n_trades)
        trial_results.append({
            "trial": i + 1,
            "n_trades": n_trades,
            "expectancy": expectancy,
            "win_rate": win_rate,
            "score": score,
            "params": params["flat"],
        })

        if (i + 1) % 10 == 0:
            elapsed = time.time() - t0
            print(f"  ... {i+1}/{n_trials} trials done ({elapsed:.1f}s)")

    elapsed_total = time.time() - t0
    print(f"\n  Total time: {elapsed_total:.1f}s ({elapsed_total/n_trials:.2f}s/trial)")

    # --- Analysis ---
    n_trades_list = [r["n_trades"] for r in trial_results]
    n_zero = sum(1 for n in n_trades_list if n == 0)
    n_gte10 = sum(1 for n in n_trades_list if n >= 10)

    print(f"\n  Distribución de n_trades en {n_trials} trials:")
    print(f"  {'Rango':<15} {'Count':>5} {'%':>6}")
    print(f"  {'-'*28}")
    bins = [(0, 0), (1, 4), (5, 9), (10, 19), (20, 29), (30, 50), (51, 999)]
    labels = ["0", "1-4", "5-9", "10-19", "20-29", "30-50", "50+"]
    for (lo, hi), label in zip(bins, labels):
        count = sum(1 for n in n_trades_list if lo <= n <= hi)
        if count > 0:
            bar = "#" * count
            print(f"  {label:<15} {count:>5} {100*count/n_trials:>5.1f}%  {bar}")

    print(f"\n  % trials con n_trades=0:   {100*n_zero/n_trials:.1f}% ({n_zero}/{n_trials})")
    print(f"  % trials con n_trades>=10: {100*n_gte10/n_trials:.1f}% ({n_gte10}/{n_trials})")

    best = max(trial_results, key=lambda r: r["score"])
    print(f"\n  Mejor trial: #{best['trial']}")
    print(f"    n_trades={best['n_trades']}, expectancy={best['expectancy']:+.3f}, "
          f"win_rate={best['win_rate']:.1%}, score={best['score']:+.3f}")
    print(f"    Params:")
    for k, v in best["params"].items():
        print(f"      {k}: {v}")

    print(f"\n  Referencia baseline (Fase 2): 22 trades, expectancy=+0.514, score=+2.41")

    if n_zero / n_trials > 0.7:
        print(f"\n  *** ALERTA: {100*n_zero/n_trials:.0f}% de trials con 0 trades (>70%) ***")
        print("  *** Los rangos son demasiado restrictivos, necesitan ajuste ***")

    return trial_results


def suggest_params(trial) -> dict:
    """Map Optuna trial to pipeline param dicts using validated Fase 3 ranges."""
    import optuna

    atr_length = trial.suggest_int("atr_length", 10, 25)
    atr_mult = trial.suggest_float("atr_mult", 1.5, 3.5, step=0.25)
    min_contractions = trial.suggest_int("min_contractions", 2, 3)
    max_contractions = trial.suggest_int(
        "max_contractions", max(min_contractions + 2, 5), 7,
    )
    lookback_bars = trial.suggest_int("lookback_bars", 80, 140, step=10)
    tolerance = trial.suggest_float("tolerance", 0.05, 0.20, step=0.025)
    max_depth_pct = trial.suggest_float("max_depth_pct", 0.25, 0.45)
    min_total_reduction = trial.suggest_float("min_total_reduction", 0.65, 0.90)
    compression_threshold = trial.suggest_float("compression_threshold", 0.70, 0.95)
    vol_contraction_threshold = trial.suggest_float("vol_contraction_threshold", 0.75, 0.95)
    volume_ratio_threshold = trial.suggest_float("volume_ratio_threshold", 1.3, 2.0)
    max_gap_days = trial.suggest_int("max_gap_days", 20, 40)

    return {
        "swing_config": ATRZigZagConfig(
            atr_length=atr_length, atr_mult=atr_mult, use_close_only=False,
        ),
        "sequence_params": {
            "method": "tolerance",
            "min_contractions": min_contractions,
            "max_contractions": max_contractions,
            "lookback_bars": lookback_bars,
            "tolerance": tolerance,
            "max_depth_pct": max_depth_pct,
            "min_total_reduction": min_total_reduction,
            "max_gap_between_contractions_days": None,
        },
        "compression_params": {
            "method": "ratio",
            "atr_period": 14,
            "ratio_threshold": compression_threshold,
        },
        "volume_contraction_params": {
            "method": "ratio",
            "volume_column": "volume",
            "ratio_threshold": vol_contraction_threshold,
        },
        "breakout_params": {
            "volume_method": "ratio",
            "volume_ratio_threshold": volume_ratio_threshold,
            "volume_lookback_days": 50,
            "require_volume_confirmation": True,
        },
        "max_gap_days": max_gap_days,
    }


def fase4_optuna_mini(n_trials: int = 5):
    import optuna

    print("=" * 70)
    print(f"FASE 4: Mini-optimización con Optuna ({n_trials} trials, TPESampler)")
    print("=" * 70)

    ohlc_cache = {ticker: load_ohlc(ticker) for ticker in TICKERS}

    def objective(trial):
        params = suggest_params(trial)

        all_trades = []
        for ticker in TICKERS:
            trades = run_pipeline_for_ticker(
                ohlc=ohlc_cache[ticker],
                swing_config=params["swing_config"],
                sequence_params=params["sequence_params"],
                compression_params=params["compression_params"],
                breakout_params=params["breakout_params"],
                volume_contraction_params=params["volume_contraction_params"],
                risk_params=RISK_PARAMS,
                max_gap_days=params["max_gap_days"],
            )
            all_trades.extend(trades)

        n_trades = len(all_trades)
        if n_trades > 0:
            expectancy = float(np.mean([t["r_multiple"] for t in all_trades]))
            win_rate = sum(1 for t in all_trades if t["pnl_pct"] > 0) / n_trades
        else:
            expectancy = 0.0
            win_rate = 0.0

        score = compute_score(expectancy, n_trades)

        trial.set_user_attr("n_trades", n_trades)
        trial.set_user_attr("expectancy", expectancy)
        trial.set_user_attr("win_rate", win_rate)

        print(f"  Trial {trial.number}: n_trades={n_trades}, "
              f"expectancy={expectancy:+.3f}, win_rate={win_rate:.1%}, "
              f"score={score:+.3f}")

        return score

    sampler = optuna.samplers.TPESampler(seed=42, n_startup_trials=2)
    study = optuna.create_study(direction="maximize", sampler=sampler)
    study.optimize(objective, n_trials=n_trials)

    print("\n" + "-" * 70)
    print("  Resultados de los 5 trials (orden cronológico):")
    print(f"  {'Trial':>5} {'n_trades':>8} {'expectancy':>11} {'win_rate':>9} {'score':>8}")
    for t in study.trials:
        print(f"  {t.number:>5} {t.user_attrs['n_trades']:>8} "
              f"{t.user_attrs['expectancy']:>+11.3f} "
              f"{t.user_attrs['win_rate']:>8.1%} "
              f"{t.value:>+8.3f}")

    best = study.best_trial
    print(f"\n  Mejor trial: #{best.number}")
    print(f"    score={best.value:+.3f}, n_trades={best.user_attrs['n_trades']}, "
          f"expectancy={best.user_attrs['expectancy']:+.3f}, "
          f"win_rate={best.user_attrs['win_rate']:.1%}")
    print(f"    Params:")
    for k, v in best.params.items():
        print(f"      {k}: {v}")

    print(f"\n  Comparación:")
    print(f"    Baseline (Fase 2):     score=+2.410 (22 trades, exp=+0.514)")
    print(f"    Best random (Fase 3):  score=+1.234 (41 trades, exp=+0.193)")
    print(f"    Best Optuna (Fase 4):  score={best.value:+.3f} "
          f"({best.user_attrs['n_trades']} trades, "
          f"exp={best.user_attrs['expectancy']:+.3f})")
    print("=" * 70)

    return study


if __name__ == "__main__":
    fase4_optuna_mini()
