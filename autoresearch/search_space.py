"""Search space para optimización de hiperparámetros del detector VCP.

Rangos validados en el spike (Fase 3): 68% de trials random generan trades,
solo 6% dan 0 trades. El search space es fértil para TPE.
"""

from __future__ import annotations

from typing import Any

import optuna

from models.configs import ATRZigZagConfig

DEFAULT_RISK_PARAMS: dict[str, float | int | str | None] = {
    "max_stop_loss_pct": 0.07,
    "breakeven_r_multiple": 2.0,
    "trailing_sma_period": 20,
    "trailing_volume_factor": 1.5,
    "trailing_stop_method": "sma",
    "trailing_atr_period": 14,
    "trailing_atr_multiplier": 3.0,
    "max_bars_without_progress": None,
    "min_progress_r": 0.5,
}


def sample_params(trial: optuna.Trial) -> dict[str, Any]:
    """Genera un set completo de parámetros del pipeline VCP desde un trial Optuna.

    Retorna un dict listo para pasar a run_backtest_for_params, con keys:
    swing_config, sequence_params, compression_params, volume_contraction_params,
    breakout_params, grouping_params, risk_params.

    Args:
        trial: Optuna Trial object.

    Returns:
        Dict con la configuración completa del pipeline.
    """
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
    require_ascending_lows = trial.suggest_categorical(
        "require_ascending_lows", [True, False],
    )
    ascending_lows_tolerance = trial.suggest_float(
        "ascending_lows_tolerance", 0.0, 0.05, step=0.01,
    )
    max_entry_distance_pct = trial.suggest_float(
        "max_entry_distance_pct", 0.02, 0.08, step=0.01,
    )
    trailing_stop_method = trial.suggest_categorical(
        "trailing_stop_method", ["sma", "atr"],
    )
    trailing_atr_period = trial.suggest_int("trailing_atr_period", 10, 21)
    trailing_atr_multiplier = trial.suggest_float(
        "trailing_atr_multiplier", 1.5, 4.0, step=0.25,
    )
    max_bars_without_progress = trial.suggest_categorical(
        "max_bars_without_progress", [None, 15, 20, 30, 40],
    )
    min_progress_r = trial.suggest_float("min_progress_r", 0.25, 1.0, step=0.25)

    return {
        "swing_config": ATRZigZagConfig(
            atr_length=atr_length,
            atr_mult=atr_mult,
            use_close_only=False,
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
            "require_ascending_lows": require_ascending_lows,
            "ascending_lows_tolerance": ascending_lows_tolerance,
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
            "max_entry_distance_pct": max_entry_distance_pct,
        },
        "grouping_params": {
            "max_gap_days": max_gap_days,
        },
        "risk_params": {
            "max_stop_loss_pct": 0.07,
            "breakeven_r_multiple": 2.0,
            "trailing_sma_period": 20,
            "trailing_volume_factor": 1.5,
            "trailing_stop_method": trailing_stop_method,
            "trailing_atr_period": trailing_atr_period,
            "trailing_atr_multiplier": trailing_atr_multiplier,
            "max_bars_without_progress": max_bars_without_progress,
            "min_progress_r": min_progress_r,
        },
    }
