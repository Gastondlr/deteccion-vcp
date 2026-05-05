"""Espacio de búsqueda de Optuna para el pipeline VCP heurístico."""

from __future__ import annotations

from typing import Any

import optuna

DEFAULT_RISK_PARAMS: dict[str, Any] = {
    "max_depth_first": 0.35,
    "min_contraction_ratio": 0.4,
    "max_contraction_ratio": 0.95,
}


def sample_params(trial: optuna.Trial) -> dict[str, Any]:
    """Muestrea un conjunto completo de hiperparámetros para un trial de Optuna.

    Devuelve un dict con todas las claves que necesita el pipeline, incluyendo
    ``swing_config`` (un dict con keys atr_length, atr_mult, use_close_only).
    """
    atr_length = trial.suggest_int("atr_length", 5, 30)
    atr_mult = trial.suggest_float("atr_mult", 1.0, 4.0, step=0.25)

    swing_config = {
        "atr_length": atr_length,
        "atr_mult": atr_mult,
        "use_close_only": False,
    }

    params: dict[str, Any] = {
        "swing_config": swing_config,
        "atr_length": atr_length,
        "atr_mult": atr_mult,
        "min_depth_pct": trial.suggest_float("min_depth_pct", 0.0, 0.05, step=0.005),
        "min_contractions": trial.suggest_int("min_contractions", 2, 4),
        "max_contractions": trial.suggest_int("max_contractions", 4, 8),
        "max_depth_first": trial.suggest_float("max_depth_first", 0.20, 0.50, step=0.05),
        "min_contraction_ratio": trial.suggest_float("min_contraction_ratio", 0.2, 0.6, step=0.05),
        "max_contraction_ratio": trial.suggest_float("max_contraction_ratio", 0.85, 1.0, step=0.05),
        "pivot_proximity_pct": trial.suggest_float("pivot_proximity_pct", 0.0, 0.10, step=0.01),
        "max_duration_bars": trial.suggest_int("max_duration_bars", 100, 300, step=20),
        "breakout_vol_mult": trial.suggest_float("breakout_vol_mult", 1.0, 3.0, step=0.25),
        "vol_avg_len": trial.suggest_int("vol_avg_len", 20, 60, step=5),
        "max_base_depth": trial.suggest_float("max_base_depth", 0.25, 0.50, step=0.05),
        "rs_min_percentile": trial.suggest_int("rs_min_percentile", 50, 90, step=5),
    }
    return params
