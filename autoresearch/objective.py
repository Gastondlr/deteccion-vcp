"""Función objetivo y creación de study para Optuna."""

from __future__ import annotations

from typing import Any, Callable

import optuna
import pandas as pd

from autoresearch.backtest import compute_objective_score, run_backtest_for_params
from autoresearch.search_space import sample_params


def build_objective_function(
    universe: dict[str, pd.DataFrame],
    evaluation_window: tuple[pd.Timestamp, pd.Timestamp] | None = None,
) -> Callable[[optuna.Trial], float]:
    """Construye la función objetivo como closure sobre el universo de datos.

    Args:
        universe: Dict {ticker: DataFrame OHLCV}.
        evaluation_window: Restricción temporal opcional para evaluación.

    Returns:
        Callable que recibe un Trial y retorna el score.
    """

    def objective(trial: optuna.Trial) -> float:
        params = sample_params(trial)
        result = run_backtest_for_params(universe, params, evaluation_window)
        metrics = result["metrics"]
        score = compute_objective_score(metrics)

        trial.set_user_attr("n_trades", metrics["n_trades"])
        trial.set_user_attr("expectancy_r", metrics["expectancy_r"])
        trial.set_user_attr("win_rate", metrics["win_rate"])
        trial.set_user_attr("profit_factor", metrics["profit_factor"])
        trial.set_user_attr("avg_winner_r", metrics["avg_winner_r"])
        trial.set_user_attr("avg_loser_r", metrics["avg_loser_r"])
        trial.set_user_attr("trades_per_ticker", metrics["trades_per_ticker"])

        return score

    return objective


def create_study(
    study_name: str = "vcp_optimization",
    direction: str = "maximize",
    n_startup_trials: int = 20,
    seed: int = 42,
    storage: str | None = None,
) -> optuna.Study:
    """Crea un study Optuna con TPESampler configurado.

    Args:
        study_name: Nombre del study.
        direction: "maximize" o "minimize".
        n_startup_trials: Trials random antes de que TPE empiece a guiar.
        seed: Seed para reproducibilidad.
        storage: URL de storage de Optuna (None = in-memory).

    Returns:
        optuna.Study configurado.
    """
    sampler = optuna.samplers.TPESampler(
        seed=seed,
        n_startup_trials=n_startup_trials,
        multivariate=True,
    )
    return optuna.create_study(
        study_name=study_name,
        direction=direction,
        sampler=sampler,
        storage=storage,
    )
