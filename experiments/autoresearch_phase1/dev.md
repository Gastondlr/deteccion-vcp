# Experimento `autoresearch_phase1` — Spec

> Fecha: 2025-05
> Autor: Gaston de la Rosa
> Relacionados: `01_run_optimization.ipynb`, `autoresearch/search_space.py`, `autoresearch/backtest.py`

---

## Universo y datos
- **Activos (optimizacion)**: 18 tickers — AAPL, AMZN, AVGO, BRK.B, GLD, GOOGL, IWM, JPM, MSFT, NVDA, QLD, QQQ, SLV, SPY, SQQQ, TIL, TLT, TQQQ
- **Activos (out-of-sample, excluidos)**: 4 tickers — COIN, HOOD, PLTR, SOFI (excluidos por start_date > 2015-12-31; META excluido manualmente)
- **Fuente**: CSVs en `data/csv/`
- **Periodo comun**: 2015-05-27 a 2026-04-08
- **Split**: Sin split temporal (in-sample optimization). OOS pendiente para Fase 2.

## Objetivo
Optimizar automaticamente los hiperparametros del detector VCP usando Optuna (TPE sampler) sobre un universo de 18 tickers. A diferencia de los experimentos de grilla, aqui se exploran ~12+ parametros de forma simultanea con busqueda bayesiana. Se compara el score del mejor trial contra un baseline conocido (parametros del experimento original con volume_ratio_threshold=1.5).

## Sub-experimento 1: Optuna optimization
**Script/Notebook**: `01_run_optimization.ipynb`

### Grilla de parametros

No hay grilla discreta. Optuna explora el espacio de busqueda definido en `autoresearch/search_space.py` con TPE (Tree-structured Parzen Estimator).

### Configs — Search space (de `search_space.py`)
| Parametro | Tipo | Rango | Step |
|---|---|---|---|
| atr_length | int | [10, 25] | 1 |
| atr_mult | float | [1.5, 3.5] | 0.25 |
| min_contractions | int | [2, 3] | 1 |
| max_contractions | int | [max(min_c+2, 5), 7] | 1 |
| lookback_bars | int | [80, 140] | 10 |
| tolerance | float | [0.05, 0.20] | 0.025 |
| max_depth_pct | float | [0.25, 0.45] | continuo |
| max_depth_atr | float | [3.0, 7.0] | 0.5 |
| min_total_reduction | float | [0.65, 0.90] | continuo |
| compression_threshold | float | [0.70, 0.95] | continuo |
| vol_contraction_threshold | float | [0.75, 0.95] | continuo |
| volume_ratio_threshold | float | [1.3, 2.0] | continuo |
| max_gap_days | int | [20, 40] | 1 |
| require_ascending_lows | categorical | [True, False] | - |
| ascending_lows_tolerance | float | [0.0, 0.05] | 0.01 |
| trailing_stop_method | categorical | [sma, atr] | - |
| trailing_atr_period | int | [10, 21] | 1 |
| trailing_atr_multiplier | float | [1.5, 4.0] | 0.25 |
| max_bars_without_progress | categorical | [None, 15, 20, 30, 40] | - |
| min_progress_r | float | [0.25, 1.0] | 0.25 |

### Parametros fijos
| Parametro | Valor |
|---|---|
| use_close_only | False |
| method | tolerance |
| max_gap_between_contractions_days | None |
| compression method | ratio |
| compression atr_period | 14 |
| volume_contraction method | ratio |
| volume_contraction volume_column | volume |
| breakout volume_method | ratio |
| breakout volume_lookback_days | 50 |
| breakout require_volume_confirmation | True |
| max_stop_loss_pct | 0.07 |
| breakeven_r_multiple | 2.0 |
| trailing_sma_period | 20 |
| trailing_volume_factor | 1.5 |

### Configuracion Optuna
| Parametro | Valor |
|---|---|
| N_TRIALS | 50 |
| Sampler | TPESampler (multivariate=True) |
| n_startup_trials | 20 (random sampling) |
| seed | 42 |
| N_JOBS | 1 (secuencial) |
| study_name | vcp_optuna_phase1 |
| direction | maximize |

### Baseline (parametros originales)
| Parametro | Valor |
|---|---|
| atr_length | 14 |
| atr_mult | 2.0 |
| min_contractions | 2 |
| max_contractions | 6 |
| lookback_bars | 126 |
| tolerance | 0.10 |
| max_depth_pct | 0.35 |
| min_total_reduction | 0.80 |
| compression_threshold | 0.85 |
| vol_contraction_threshold | 0.85 |
| volume_ratio_threshold | 1.5 |
| max_gap_days | 30 |

### Funcion de score
`compute_objective_score` de `autoresearch/backtest.py`:
```
score = expectancy_r * penalty * sqrt(n_trades)
penalty = sqrt(min(n_trades / N_MIN_TRADES, 1.0))
N_MIN_TRADES = 10
```
Si n_trades == 0, retorna -1.0.

### Metricas
- Score (Opcion C) — metrica objetivo de Optuna
- N trades
- Expectancy R
- Win Rate
- Profit Factor
- Avg Winner R, Avg Loser R
- Trades per ticker (distribucion)
- fANOVA parameter importance (post-optimizacion)

## Notas de implementacion
- Usa `SwingCache` para evitar recomputar swings/contracciones cuando se repite el swing_config entre trials.
- `build_objective_function` encapsula el pipeline completo (deteccion + simulacion) para cada trial.
- Cada trial corre el pipeline sobre los 18 tickers y agrega metricas.
- Resultados trackeados en MLflow experiment `autoresearch_vcp_phase1` con un parent run y child runs por trial.
- `MLflowOptunaLogger` registra parametros, metricas y atributos por trial.
- Reproducibilidad verificada: re-run del best trial da score identico (diff = 0.0e+00).
- Resultado del baseline: score=+2.70, 78 trades, expectancy_r=+0.31, WR=46%, PF=1.62.
- Resultado best Optuna (trial #25): score=+4.13, 26 trades, expectancy_r=+0.81, WR=50%, PF=3.40.
- Parametros mas importantes segun fANOVA: vol_contraction_threshold (0.21), max_gap_days (0.17), volume_ratio_threshold (0.16), min_total_reduction (0.14), max_depth_pct (0.13).
- Limitaciones: optimizacion in-sample (sin split temporal), solo 50 trials (12+ parametros idealmente necesitan 200-500), solo method=tolerance.
