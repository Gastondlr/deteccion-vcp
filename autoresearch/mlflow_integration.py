"""Integración MLflow con Optuna para logging de estudios de optimización VCP."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Generator

import mlflow
import optuna


class MLflowOptunaLogger:
    """Logger que registra cada trial de Optuna como un child run en MLflow.

    Uso:
        logger = MLflowOptunaLogger(experiment_name="autoresearch_vcp")
        study = create_study(...)
        with logger.parent_run(study_name=study.study_name, tags={...}):
            study.optimize(objective, n_trials=50, callbacks=[logger.optuna_callback])

    Args:
        experiment_name: Nombre del experimento MLflow.
        tracking_uri: URI del tracking server. Default "mlruns/".
    """

    def __init__(
        self,
        experiment_name: str,
        tracking_uri: str = "mlruns/",
    ) -> None:
        self.experiment_name = experiment_name
        self.tracking_uri = tracking_uri
        self._parent_run_id: str | None = None

        mlflow.set_tracking_uri(tracking_uri)
        mlflow.set_experiment(experiment_name)

    @contextmanager
    def parent_run(
        self,
        study_name: str = "vcp_optimization",
        tags: dict[str, str] | None = None,
    ) -> Generator[mlflow.ActiveRun, None, None]:
        """Context manager que crea y cierra el parent run.

        Args:
            study_name: Nombre del study (se usa como run name).
            tags: Tags adicionales para el parent run.

        Yields:
            El ActiveRun de MLflow.
        """
        run_tags = {"study_name": study_name}
        if tags:
            run_tags.update(tags)

        with mlflow.start_run(run_name=study_name, tags=run_tags) as run:
            self._parent_run_id = run.info.run_id
            yield run
            self._parent_run_id = None

    def optuna_callback(
        self,
        study: optuna.Study,
        trial: optuna.trial.FrozenTrial,
    ) -> None:
        """Callback de Optuna que loguea cada trial completado como child run.

        Se pasa a study.optimize(callbacks=[logger.optuna_callback]).

        Args:
            study: El study Optuna.
            trial: El trial recién completado.
        """
        if trial.state != optuna.trial.TrialState.COMPLETE:
            return

        run_name = f"trial_{trial.number:04d}"
        tags = {
            "trial_number": str(trial.number),
            "study_name": study.study_name,
        }

        with mlflow.start_run(
            run_name=run_name,
            nested=True,
            tags=tags,
        ):
            self._log_params(trial.params)
            self._log_metrics(trial)

    def log_study_summary(self, study: optuna.Study, n_tickers: int = 0) -> None:
        """Loguea resumen final del study en el parent run activo.

        Llamar dentro del context manager parent_run, después de optimize.

        Args:
            study: Study completado.
            n_tickers: Cantidad de tickers en el universo.
        """
        best = study.best_trial

        mlflow.log_metrics({
            "best_score": best.value,
            "best_n_trades": best.user_attrs.get("n_trades", 0),
            "best_expectancy_r": best.user_attrs.get("expectancy_r", 0.0),
            "best_win_rate": best.user_attrs.get("win_rate", 0.0),
            "best_profit_factor": min(
                best.user_attrs.get("profit_factor", 0.0), 999.0,
            ),
            "total_trials": len(study.trials),
            "n_tickers": n_tickers,
        })

        best_params = {f"best_{k}": str(v) for k, v in best.params.items()}
        mlflow.log_params(best_params)

    def _log_params(self, params: dict[str, Any]) -> None:
        mlflow_params = {}
        for k, v in params.items():
            mlflow_params[k] = str(v)
        mlflow.log_params(mlflow_params)

    def _log_metrics(self, trial: optuna.trial.FrozenTrial) -> None:
        metrics: dict[str, float] = {"score": trial.value}

        metric_keys = [
            "n_trades", "expectancy_r", "win_rate", "profit_factor",
            "avg_winner_r", "avg_loser_r",
        ]
        for key in metric_keys:
            val = trial.user_attrs.get(key)
            if val is not None:
                if key == "profit_factor":
                    val = min(val, 999.0)
                metrics[key] = float(val)

        mlflow.log_metrics(metrics)
