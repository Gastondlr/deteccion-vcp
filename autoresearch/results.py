"""Helpers de análisis para estudios Optuna completados."""

from __future__ import annotations

from typing import Any

import optuna
import pandas as pd

from models.configs import ATRZigZagConfig
from autoresearch.search_space import DEFAULT_RISK_PARAMS


def study_to_dataframe(study: optuna.Study) -> pd.DataFrame:
    """Convierte un study completo a DataFrame con params + métricas.

    Args:
        study: Study Optuna completado.

    Returns:
        DataFrame con una fila por trial, columnas: trial_number, score,
        state, todos los params, y todos los user_attrs.
    """
    rows = []
    for trial in study.trials:
        row: dict[str, Any] = {
            "trial_number": trial.number,
            "score": trial.value,
            "state": trial.state.name,
        }
        row.update(trial.params)
        row.update(trial.user_attrs)
        rows.append(row)

    df = pd.DataFrame(rows)
    if "score" in df.columns:
        df = df.sort_values("score", ascending=False).reset_index(drop=True)
    return df


def top_trials_summary(study: optuna.Study, n: int = 10) -> pd.DataFrame:
    """Resumen de los top N trials del study.

    Args:
        study: Study Optuna completado.
        n: Cantidad de trials a mostrar.

    Returns:
        DataFrame con las columnas más relevantes, ordenado por score desc.
    """
    df = study_to_dataframe(study)
    display_cols = [
        "trial_number", "score", "n_trades", "expectancy_r",
        "win_rate", "profit_factor",
    ]
    param_cols = [c for c in df.columns if c in {
        "atr_length", "atr_mult", "tolerance", "max_depth_pct",
        "compression_threshold", "vol_contraction_threshold",
        "volume_ratio_threshold", "lookback_bars",
        "min_contractions", "max_contractions", "min_total_reduction",
        "max_gap_days",
    }]
    cols = [c for c in display_cols + param_cols if c in df.columns]
    return df[cols].head(n)


def param_importance(study: optuna.Study) -> pd.DataFrame | None:
    """Calcula la importancia de cada parámetro usando fANOVA.

    Args:
        study: Study Optuna con suficientes trials completados.

    Returns:
        DataFrame con columnas param, importance ordenado desc.
        None si no se puede calcular (pocos trials, errores de fANOVA).
    """
    try:
        importance = optuna.importance.get_param_importances(study)
    except Exception:
        return None

    rows = [{"param": k, "importance": v} for k, v in importance.items()]
    return pd.DataFrame(rows).sort_values("importance", ascending=False).reset_index(drop=True)


def reconstruct_pipeline_params(best_params: dict[str, Any]) -> dict[str, Any]:
    """Reconstruye el dict de params completo para run_backtest_for_params
    a partir de los best_params planos de un trial Optuna.

    Maneja la lógica condicional de kwargs según el método seleccionado
    (preparado para v2 donde method puede ser muestreado).

    Args:
        best_params: Dict plano {param_name: value} de trial.params.

    Returns:
        Dict con keys swing_config, sequence_params, compression_params,
        volume_contraction_params, breakout_params, grouping_params, risk_params.
    """
    seq_method = best_params.get("seq_method", "tolerance")
    compression_method = best_params.get("compression_method", "ratio")
    vol_contraction_method = best_params.get("vol_contraction_method", "ratio")

    sequence_params: dict[str, Any] = {
        "method": seq_method,
        "min_contractions": best_params["min_contractions"],
        "max_contractions": best_params["max_contractions"],
        "lookback_bars": best_params["lookback_bars"],
        "max_depth_pct": best_params.get("max_depth_pct"),
        "max_depth_atr": best_params.get("max_depth_atr"),
        "min_total_reduction": best_params.get("min_total_reduction"),
        "max_gap_between_contractions_days": None,
    }
    if seq_method == "tolerance":
        sequence_params["tolerance"] = best_params["tolerance"]
    elif seq_method == "robust_trend":
        sequence_params["min_r_squared"] = best_params.get("min_r_squared", 0.5)

    compression_params: dict[str, Any] = {
        "method": compression_method,
        "atr_period": 14,
    }
    if compression_method in ("ratio", "ratio_normalized"):
        compression_params["ratio_threshold"] = best_params["compression_threshold"]
    elif compression_method == "trend":
        compression_params["min_r_squared"] = best_params.get("compression_min_r_squared", 0.5)

    vol_contraction_params: dict[str, Any] = {
        "method": vol_contraction_method,
        "volume_column": "volume",
    }
    if vol_contraction_method == "ratio":
        vol_contraction_params["ratio_threshold"] = best_params["vol_contraction_threshold"]
    elif vol_contraction_method == "per_contraction":
        vol_contraction_params["tolerance"] = best_params.get("vol_contraction_tolerance", 0.1)
    elif vol_contraction_method == "trend":
        vol_contraction_params["min_r_squared"] = best_params.get("vol_contraction_min_r_squared", 0.5)

    return {
        "swing_config": ATRZigZagConfig(
            atr_length=best_params["atr_length"],
            atr_mult=best_params["atr_mult"],
            use_close_only=False,
        ),
        "sequence_params": sequence_params,
        "compression_params": compression_params,
        "volume_contraction_params": vol_contraction_params,
        "breakout_params": {
            "volume_method": "ratio",
            "volume_ratio_threshold": best_params["volume_ratio_threshold"],
            "volume_lookback_days": 50,
            "require_volume_confirmation": True,
        },
        "grouping_params": {
            "max_gap_days": best_params["max_gap_days"],
        },
        "risk_params": {
            **dict(DEFAULT_RISK_PARAMS),
            "trailing_stop_method": best_params.get("trailing_stop_method", "sma"),
            "trailing_atr_period": best_params.get("trailing_atr_period", 14),
            "trailing_atr_multiplier": best_params.get("trailing_atr_multiplier", 3.0),
            "max_bars_without_progress": best_params.get("max_bars_without_progress", None),
            "min_progress_r": best_params.get("min_progress_r", 0.5),
        },
    }


def trades_to_dataframe(trades: list[dict]) -> pd.DataFrame:
    """Convierte una lista de trade dicts a DataFrame para análisis.

    Args:
        trades: Lista de dicts output de simulate_trade (con keys "ticker" y "pattern").

    Returns:
        DataFrame con una fila por trade.
    """
    rows = []
    for i, t in enumerate(trades, 1):
        pattern = t.get("pattern", {})
        row = {
            "trade_num": i,
            "ticker": t.get("ticker", "unknown"),
            "entry_date": pattern.get("first_signal_date"),
            "exit_date": t["exit_date"],
            "exit_reason": t["exit_reason"],
            "duration_days": t["duration_days"],
            "entry_price": pattern.get("entry_price"),
            "exit_price": t["exit_price"],
            "pnl_pct": t["pnl_pct"],
            "r_multiple": t["r_multiple"],
            "max_r": t["max_r"],
            "n_contractions": pattern.get("n_contractions"),
            "stop_method": pattern.get("stop_method"),
            "stop_distance_pct": pattern.get("stop_distance_pct"),
        }
        rows.append(row)
    return pd.DataFrame(rows)
