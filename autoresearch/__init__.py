"""Autoresearch: optimización de hiperparámetros para el detector VCP."""

from autoresearch.backtest import (
    compute_aggregate_metrics,
    compute_objective_score,
    run_backtest_for_params,
)
from autoresearch.data_loader import (
    filter_tickers_by_start_date,
    find_common_period,
    get_ticker_info,
    load_universe,
)
from autoresearch.mlflow_integration import MLflowOptunaLogger
from autoresearch.objective import build_objective_function, create_study
from autoresearch.results import (
    param_importance,
    reconstruct_pipeline_params,
    study_to_dataframe,
    top_trials_summary,
    trades_to_dataframe,
)
from autoresearch.search_space import DEFAULT_RISK_PARAMS, sample_params

__all__ = [
    "DEFAULT_RISK_PARAMS",
    "MLflowOptunaLogger",
    "build_objective_function",
    "compute_aggregate_metrics",
    "compute_objective_score",
    "create_study",
    "filter_tickers_by_start_date",
    "find_common_period",
    "get_ticker_info",
    "load_universe",
    "param_importance",
    "reconstruct_pipeline_params",
    "run_backtest_for_params",
    "sample_params",
    "study_to_dataframe",
    "top_trials_summary",
    "trades_to_dataframe",
]
