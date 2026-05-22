# Sistema de Optimizacion (autoresearch)

El modulo `autoresearch/` implementa optimizacion automatica de hiperparametros del pipeline VCP usando Optuna con TPE (Tree-structured Parzen Estimator), logging en MLflow, y cache de resultados intermedios.

---

## 1. Overview

```
                        autoresearch/
  ============================================================================

  data_loader.py                Carga y filtrado de CSVs
      |                         load_universe, filter_tickers_by_start_date
      v
  search_space.py               Definicion del search space
      |                         sample_params(trial) -> dict completo
      v
  objective.py                  Funcion objetivo para Optuna
      |                         build_objective_function (closure)
      |                         create_study (TPESampler)
      v
  backtest.py                   Motor de backtesting
      |                         run_backtest_for_params (orquesta pipeline + simulacion)
      |                         compute_aggregate_metrics
      |                         compute_objective_score
      v
  caching.py                    Cache de pasos 1+2
      |                         SwingCache (key = ticker + swing_config)
      v
  mlflow_integration.py         Logging en MLflow
      |                         MLflowOptunaLogger (parent/child runs)
      v
  results.py                    Analisis post-optimizacion
                                study_to_dataframe, param_importance, reconstruct_pipeline_params

  Flujo de una optimizacion:
  ============================================================================

  load_universe() -> build_objective_function(universe, cache)
                              |
                              v
                     create_study(n_startup_trials=20)
                              |
                              v
                     study.optimize(objective, n_trials=N,
                                    callbacks=[mlflow_logger])
                              |
                     Para cada trial:
                     |  sample_params(trial) -> params
                     |  run_backtest_for_params(universe, params, cache)
                     |      |-- Para cada ticker:
                     |      |      run_pipeline_cached(ohlc, ticker, params, cache)
                     |      |      group_signals_into_patterns(signals, risk_params)
                     |      |      simulate_trade(ohlc, pattern, risk_params)
                     |      |-- compute_aggregate_metrics(all_trades)
                     |  compute_objective_score(metrics) -> score
                     |  mlflow_logger.optuna_callback(study, trial)
                              |
                              v
                     study_to_dataframe(study)
                     param_importance(study)
                     top_trials_summary(study)
```

---

## 2. Search Space

Definido en `autoresearch/search_space.py`, la funcion `sample_params(trial)` genera un diccionario completo de parametros del pipeline usando las primitivas de Optuna:

### Parametros del swing detector (Paso 1)

| Parametro | Tipo Optuna | Rango | Step | Descripcion |
|-----------|-------------|-------|------|-------------|
| `atr_length` | `suggest_int` | 10-25 | 1 | Periodo del ATR |
| `atr_mult` | `suggest_float` | 1.5-3.5 | 0.25 | Multiplo de ATR para reversion |

### Parametros de secuencia decreciente (Paso 3)

| Parametro | Tipo Optuna | Rango | Step | Descripcion |
|-----------|-------------|-------|------|-------------|
| `min_contractions` | `suggest_int` | 2-3 | 1 | Minimo de contracciones |
| `max_contractions` | `suggest_int` | 5-7 | 1 | Maximo de contracciones (>= min+2) |
| `lookback_bars` | `suggest_int` | 80-140 | 10 | Ventana temporal |
| `tolerance` | `suggest_float` | 0.05-0.20 | 0.025 | Tolerancia de monotonia |
| `max_depth_pct` | `suggest_float` | 0.25-0.45 | - | Profundidad maxima por contraccion |
| `max_depth_atr` | `suggest_float` | 3.0-7.0 | 0.5 | Profundidad maxima en ATR |
| `min_total_reduction` | `suggest_float` | 0.65-0.90 | - | Ratio ultima/primera contraccion |
| `require_ascending_lows` | `suggest_categorical` | [True, False] | - | Exigir lows ascendentes |
| `ascending_lows_tolerance` | `suggest_float` | 0.0-0.05 | 0.01 | Margen para lows ascendentes |

### Parametros de compresion y volumen (Pasos 4-6)

| Parametro | Tipo Optuna | Rango | Step | Descripcion |
|-----------|-------------|-------|------|-------------|
| `compression_threshold` | `suggest_float` | 0.70-0.95 | - | Umbral ATR ratio |
| `vol_contraction_threshold` | `suggest_float` | 0.75-0.95 | - | Umbral volume ratio |
| `volume_ratio_threshold` | `suggest_float` | 1.3-2.0 | - | Multiplo volumen breakout |

### Parametros de agrupacion y riesgo

| Parametro | Tipo Optuna | Rango | Step | Descripcion |
|-----------|-------------|-------|------|-------------|
| `max_gap_days` | `suggest_int` | 20-40 | 1 | Gap maximo entre senales |
| `trailing_stop_method` | `suggest_categorical` | ["sma", "atr"] | - | Metodo de trailing stop |
| `trailing_atr_period` | `suggest_int` | 10-21 | 1 | Periodo ATR trailing |
| `trailing_atr_multiplier` | `suggest_float` | 1.5-4.0 | 0.25 | Multiplo ATR trailing |
| `max_bars_without_progress` | `suggest_categorical` | [None, 15, 20, 30, 40] | - | Time exit |
| `min_progress_r` | `suggest_float` | 0.25-1.0 | 0.25 | Progreso minimo |

### Parametros fijos (no optimizados)

| Parametro | Valor fijo | Descripcion |
|-----------|------------|-------------|
| `use_close_only` | False | Siempre usa high/low para swings |
| `method` (seq) | "tolerance" | Metodo de monotonia fijo |
| `method` (compression) | "ratio" | Metodo de ATR fijo |
| `method` (vol contraction) | "ratio" | Metodo de volumen fijo |
| `volume_method` (breakout) | "ratio" | Metodo de volumen breakout fijo |
| `volume_lookback_days` | 50 | Lookback fijo para volumen breakout |
| `require_volume_confirmation` | True | Siempre con confirmacion de volumen |
| `max_stop_loss_pct` | 0.07 | Stop maximo fijo |
| `breakeven_r_multiple` | 2.0 | Step de breakeven fijo |
| `trailing_sma_period` | 20 | SMA period fijo |
| `trailing_volume_factor` | 1.5 | Factor distribucion fijo |
| `atr_period` (compression) | 14 | ATR period del paso 4 fijo |

### Estructura del retorno

`sample_params(trial)` retorna un dict con 7 keys:

```python
{
    "swing_config": ATRZigZagConfig(...),
    "sequence_params": {...},
    "compression_params": {...},
    "volume_contraction_params": {...},
    "breakout_params": {...},
    "grouping_params": {"max_gap_days": ...},
    "risk_params": {...},
}
```

---

## 3. Funcion objetivo

### build_objective_function

Construye un closure que captura el universo de datos y el cache:

```python
def build_objective_function(
    universe: dict[str, pd.DataFrame],
    evaluation_window: tuple[pd.Timestamp, pd.Timestamp] | None = None,
    cache: SwingCache | None = None,
) -> Callable[[optuna.Trial], float]:
```

Si no se provee cache, crea uno nuevo automaticamente.

### Flujo del closure

```python
def objective(trial):
    params = sample_params(trial)                    # 1. Muestrea parametros
    result = run_backtest_for_params(                 # 2. Corre backtest completo
        universe, params, evaluation_window, cache
    )
    metrics = result["metrics"]                       # 3. Extrae metricas
    score = compute_objective_score(metrics)           # 4. Calcula score
    trial.set_user_attr("n_trades", ...)              # 5. Guarda metricas en trial
    return score                                       # 6. Retorna a Optuna
```

### compute_objective_score

```
score = expectancy_r * penalty * sqrt(n_trades)
penalty = sqrt(min(n_trades / 10, 1.0))
```

- Si `n_trades == 0`, retorna -1.0 (peor posible).
- La penalizacion suave evita que Optuna converja a parametros ultra-restrictivos que generan pocos pero buenos trades.
- `sqrt(n_trades)` premia tener mas trades (mayor significancia estadistica).

### create_study

```python
def create_study(
    study_name: str = "vcp_optimization",
    direction: str = "maximize",
    n_startup_trials: int = 20,     # trials random antes de TPE
    seed: int = 42,
    storage: str | None = None,     # None = in-memory
) -> optuna.Study:
```

Usa `TPESampler` con `multivariate=True` para modelar correlaciones entre parametros.

---

## 4. Motor de backtest (run_backtest_for_params)

Orquesta el pipeline VCP completo sobre todos los tickers del universo:

```python
def run_backtest_for_params(
    universe: dict[str, pd.DataFrame],
    params: dict[str, Any],
    evaluation_window: tuple[pd.Timestamp, pd.Timestamp] | None = None,
    cache: SwingCache | None = None,
) -> dict:
```

### Flujo por ticker

1. Si hay cache, usa `run_pipeline_cached()` (evita recomputar swings/contracciones).
2. Si no, crea `ATRZigZagDetector` y llama `run_full_vcp_pipeline()`.
3. Filtra senales no-None.
4. Agrupa con `group_signals_into_patterns()`.
5. Simula cada trade con `simulate_trade()`.

### run_pipeline_cached

Replica exactamente la logica de `run_full_vcp_pipeline` pero obtiene swings y contracciones del `SwingCache` via `cache.get_or_compute(ticker, ohlc, swing_config)`.

### Retorno

```python
{
    "per_ticker": {
        "NVDA": {"n_trades": 5, "trades": [...], "patterns": [...]},
        "AAPL": {"n_trades": 3, "trades": [...], "patterns": [...]},
        ...
    },
    "all_trades": [...],        # lista plana de todos los trades
    "metrics": {                # compute_aggregate_metrics(all_trades)
        "n_trades": 42,
        "expectancy_r": 1.25,
        "win_rate": 0.55,
        "profit_factor": 2.1,
        ...
    },
}
```

---

## 5. SwingCache

**Archivo**: `autoresearch/caching.py`

### Problema que resuelve

Los pasos 1 (swing detection) y 2 (contraction computation) dependen solo de `swing_config` (atr_length, atr_mult, use_close_only). Muchos trials de Optuna comparten el mismo swing_config (especialmente con rangos discretos). Recomputar swings para cada trial desperdicia ~40-60% del tiempo.

### Implementacion

```python
class SwingCache:
    def __init__(self) -> None:
        self._cache: dict[tuple, dict] = {}
        self.hits: int = 0
        self.misses: int = 0
```

**Key del cache**: `(ticker, atr_length, atr_mult, use_close_only)` -- tupla inmutable.

### API

| Metodo | Descripcion |
|--------|-------------|
| `get_or_compute(ticker, ohlc, swing_config)` | Retorna `{"swings": [...], "contractions": [...]}` desde cache o computandolo |
| `stats()` | Retorna `{"hits": N, "misses": M, "hit_rate": 0.75, "size": K}` |
| `clear()` | Limpia cache y resetea contadores |

### Ejemplo de uso

```python
cache = SwingCache()

# Trial 1: atr_length=14, atr_mult=2.0 -> MISS (computa)
# Trial 2: atr_length=14, atr_mult=2.0 -> HIT (reusa)
# Trial 3: atr_length=20, atr_mult=2.5 -> MISS (computa)

print(cache.stats())
# {'hits': 1, 'misses': 2, 'hit_rate': 0.333, 'size': 2}
```

---

## 6. Data loader

**Archivo**: `autoresearch/data_loader.py`

### get_ticker_info

Resume los CSVs disponibles en un directorio:

```python
info = get_ticker_info("data/csv/")
# DataFrame con columnas: start_date, end_date, n_bars (indexado por ticker)
```

### filter_tickers_by_start_date

Separa tickers en conjuntos de optimizacion y out-of-sample basandose en la fecha de inicio de sus datos:

```python
opt_tickers, oos_tickers = filter_tickers_by_start_date(
    data_dir="data/csv/",
    max_start_date="2015-01-01",
    exclude_tickers=["SPY"],
)
# Tickers con start_date <= 2015-01-01 van a opt_tickers
# El resto a oos_tickers
```

### load_universe

Carga DataFrames OHLCV para una lista de tickers:

```python
universe = load_universe(
    tickers=["NVDA", "AAPL", "MSFT"],
    data_dir="data/csv/",
    start_date="2016-01-01",
    end_date="2024-01-01",
)
# Dict {"NVDA": DataFrame, "AAPL": DataFrame, ...}
```

### find_common_period

Encuentra el periodo temporal comun a todos los tickers (interseccion de rangos):

```python
common_start, common_end = find_common_period(universe)
```

---

## 7. Integracion MLflow

**Archivo**: `autoresearch/mlflow_integration.py`

### MLflowOptunaLogger

Registra cada trial de Optuna como un child run dentro de un parent run en MLflow.

### Estructura de runs

```
Experiment: autoresearch_vcp
|
|-- Parent Run: "vcp_optimization" (tags: study_name)
    |
    |-- Child Run: trial_0000 (params + metrics del trial)
    |-- Child Run: trial_0001
    |-- ...
    |-- Child Run: trial_0099
    |
    |-- [Metricas finales: best_score, best_n_trades, ...]
```

### Uso

```python
logger = MLflowOptunaLogger(
    experiment_name="autoresearch_vcp",
    tracking_uri="mlruns/",
)

study = create_study(study_name="vcp_optimization")
objective = build_objective_function(universe, cache=cache)

with logger.parent_run(study_name=study.study_name, tags={"asset_class": "stocks"}):
    study.optimize(objective, n_trials=100, callbacks=[logger.optuna_callback])
    logger.log_study_summary(study, n_tickers=len(universe))
```

### Datos logueados por trial

| Tipo | Datos |
|------|-------|
| **Params** | Todos los hiperparametros del trial (como strings) |
| **Metrics** | score, n_trades, expectancy_r, win_rate, profit_factor, avg_winner_r, avg_loser_r |

### Datos logueados en el parent (resumen)

| Tipo | Datos |
|------|-------|
| **Metrics** | best_score, best_n_trades, best_expectancy_r, best_win_rate, best_profit_factor, total_trials, n_tickers |
| **Params** | best_* para cada hiperparametro del mejor trial |

### Lanzar UI

```bash
mlflow ui --backend-store-uri mlruns/
```

Navegar a `http://localhost:5000` para ver los experimentos.

---

## 8. Analisis de resultados

**Archivo**: `autoresearch/results.py`

### study_to_dataframe

Convierte el study completo a DataFrame con todos los trials, parametros y metricas:

```python
df = study_to_dataframe(study)
# Columnas: trial_number, score, state, atr_length, atr_mult, ..., n_trades, expectancy_r, ...
# Ordenado por score descendente
```

### top_trials_summary

Resumen compacto de los mejores N trials:

```python
summary = top_trials_summary(study, n=10)
# Columnas: trial_number, score, n_trades, expectancy_r, win_rate, profit_factor,
#           atr_length, atr_mult, tolerance, max_depth_pct, compression_threshold, ...
```

### param_importance (fANOVA)

Calcula la importancia de cada parametro usando fANOVA (functional ANOVA):

```python
importance = param_importance(study)
# DataFrame con columnas: param, importance
# Ordenado por importancia descendente
```

Retorna `None` si hay pocos trials o fANOVA falla. Requiere la dependencia `optuna` con soporte fANOVA.

### reconstruct_pipeline_params

Reconstruye el diccionario de parametros completo a partir de los parametros planos de un trial:

```python
best_params = study.best_trial.params
pipeline_params = reconstruct_pipeline_params(best_params)
# Retorna el dict con swing_config, sequence_params, compression_params, etc.
# Listo para pasar a run_backtest_for_params
```

Maneja logica condicional de metodos (preparado para futuras versiones donde el metodo sea muestreado).

### trades_to_dataframe

Convierte la lista de trades a DataFrame para analisis:

```python
trades_df = trades_to_dataframe(result["all_trades"])
# Columnas: trade_num, ticker, entry_date, exit_date, exit_reason,
#           duration_days, entry_price, exit_price, pnl_pct, r_multiple, max_r,
#           n_contractions, stop_method, stop_distance_pct
```

---

## 9. Diferencias vs experimentos manuales (grid search)

El directorio `experiments/` contiene scripts de experimentacion manual que fijan parametros y corren el pipeline. A diferencia de autoresearch:

| Aspecto | Experimentos manuales | autoresearch |
|---------|----------------------|--------------|
| Exploracion | Grid search o parametros fijos | TPE (Bayesian optimization) |
| Escala | ~5-20 configuraciones | 50-500+ trials |
| Cache | No | SwingCache (ahorra 40-60%) |
| Tracking | Archivos .md manuales | MLflow automatico |
| Reproducibilidad | Scripts independientes | Study Optuna serializable |
| Analisis | Notebooks ad-hoc | param_importance, study_to_dataframe |
| Agrupacion | Ambos modos | Configurable via max_gap_days |

Los experimentos manuales son utiles para exploracion rapida y para validar hipotesis especificas. autoresearch es para optimizacion sistematica una vez que el search space esta validado.
