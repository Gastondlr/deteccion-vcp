# Guia de Uso

Guia end-to-end para usar el detector de patrones VCP, simular trades, ejecutar experimentos y optimizar hiperparametros.

---

## 1. Instalacion

### Requisitos

- Python >= 3.11
- pip (o uv)

### Setup

```bash
cd deteccion-vcp
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### Dependencias principales

| Libreria | Version | Uso |
|----------|---------|-----|
| `numpy` | >= 1.24 | Operaciones vectorizadas, ATR, percentiles |
| `pandas` | >= 2.0 | Series temporales, OHLCV, rolling windows |
| `scipy` | >= 1.10 | `linregress` (regresion lineal), `find_peaks` |
| `matplotlib` | >= 3.7 | Visualizacion en notebooks |
| `pyyaml` | >= 6.0 | Carga de configuracion desde YAML |
| `mlflow` | >= 2.10 | Tracking de experimentos |

### Dependencias de desarrollo

| Libreria | Uso |
|----------|-----|
| `pytest` | Tests unitarios y de integracion |
| `pytest-cov` | Cobertura de tests |
| `jupyter` | Notebooks interactivos |

---

## 2. Inicio rapido

Ejemplo minimo para detectar patrones VCP en un ticker:

```python
import pandas as pd
from models.configs import ATRZigZagConfig
from vcp_detection.heuristic import ATRZigZagDetector, run_full_vcp_pipeline

# 1. Cargar datos OHLCV
ohlc = pd.read_csv("data/csv/NVDA.csv", parse_dates=["date"], index_col="date")
ohlc = ohlc.loc["2020-01-01":].copy()

# 2. Configurar detector de swings
config = ATRZigZagConfig(atr_length=14, atr_mult=2.0)
detector = ATRZigZagDetector(config)

# 3. Ejecutar pipeline completo
results = run_full_vcp_pipeline(
    ohlc=ohlc,
    swing_detector=detector,
    sequence_params={
        "method": "tolerance",
        "min_contractions": 2,
        "max_contractions": 6,
        "lookback_bars": 126,
        "tolerance": 0.10,
        "max_depth_pct": 0.35,
        "min_total_reduction": 0.80,
    },
    compression_params={
        "method": "ratio",
        "atr_period": 14,
        "ratio_threshold": 0.85,
    },
    breakout_params={
        "volume_method": "ratio",
        "volume_ratio_threshold": 1.5,
        "volume_lookback_days": 50,
        "require_volume_confirmation": True,
    },
    volume_contraction_params={
        "method": "ratio",
        "volume_column": "volume",
        "ratio_threshold": 0.85,
    },
)

# 4. Filtrar senales
signals = {dt: sig for dt, sig in results.items() if sig is not None}
print(f"Senales detectadas: {len(signals)}")

for dt, sig in signals.items():
    print(f"  {dt.date()}: entry=${sig.entry_price:.2f}, "
          f"pivot=${sig.pivot_price:.2f}, stop=${sig.suggested_stop:.2f}")
```

---

## 3. Deteccion de patrones (paso a paso)

Para mayor control, se puede ejecutar cada paso individualmente:

```python
import pandas as pd
from models.configs import ATRZigZagConfig
from vcp_detection.heuristic import (
    ATRZigZagDetector,
    compute_contractions,
    contractions_to_dataframe,
    detect_decreasing_sequence,
    verify_atr_compression,
    verify_volume_contraction,
    detect_breakout_signal,
)

ohlc = pd.read_csv("data/csv/NVDA.csv", parse_dates=["date"], index_col="date")
ohlc = ohlc.loc["2020-01-01":].copy()

# Paso 1: Detectar swings
detector = ATRZigZagDetector(ATRZigZagConfig(atr_length=14, atr_mult=2.0))
swings = detector.detect(ohlc)
print(f"Swings detectados: {len(swings)}")

# Paso 2: Calcular contracciones
contractions = compute_contractions(swings, ohlc)
print(f"Contracciones: {len(contractions)}")

# Ver contracciones como tabla
df_c = contractions_to_dataframe(contractions)
print(df_c[["high_date", "low_date", "depth_pct", "duration_bars"]].to_string())

# Paso 3: Buscar secuencia decreciente en una fecha especifica
eval_date = pd.Timestamp("2024-01-08")
seq = detect_decreasing_sequence(
    contractions,
    evaluation_date=eval_date,
    method="tolerance",
    min_contractions=2,
    max_contractions=6,
    lookback_bars=126,
    tolerance=0.10,
    max_depth_pct=0.35,
    min_total_reduction=0.80,
    ohlc_index=ohlc.index,
    require_ascending_lows=True,
    ascending_lows_tolerance=0.02,
)

if seq is not None:
    print(f"Secuencia encontrada: {seq.n_contractions} contracciones")
    print(f"  Profundidades: {[f'{d:.1%}' for d in seq.depths_pct]}")

    # Paso 4: Verificar compresion de ATR
    atr_result = verify_atr_compression(
        seq, ohlc, method="ratio", atr_period=14, ratio_threshold=0.85,
    )
    print(f"  ATR compression: {'PASS' if atr_result.passes else 'FAIL'} "
          f"(ratio={atr_result.method_metrics.get('ratio_observed', 0):.3f})")

    if atr_result.passes:
        # Paso 5: Verificar contraccion de volumen
        vol_result = verify_volume_contraction(
            seq, ohlc, method="ratio", volume_column="volume", ratio_threshold=0.85,
        )
        print(f"  Vol contraction: {'PASS' if vol_result.passes else 'FAIL'}")

        if vol_result.passes:
            # Paso 6: Detectar breakout
            signal = detect_breakout_signal(
                sequence=seq,
                atr_compression_result=atr_result,
                ohlc=ohlc,
                evaluation_date=eval_date,
                volume_method="ratio",
                volume_ratio_threshold=1.5,
                volume_lookback_days=50,
                require_volume_confirmation=True,
                volume_contraction_result=vol_result,
            )
            if signal:
                print(f"  SENAL: entry=${signal.entry_price:.2f}, "
                      f"pivot=${signal.pivot_price:.2f}, "
                      f"stop=${signal.suggested_stop:.2f}")
```

---

## 4. Simulacion de trades

### Modo basico (gap grouping)

```python
from vcp_detection.analysis import evaluate_signals_to_trades

risk_params = {
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

# Usando senales del pipeline
trades = evaluate_signals_to_trades(
    signals=signals,
    ohlc=ohlc,
    risk_params=risk_params,
    grouping="gap",
    max_gap_days=30,
)

for pattern, trade in trades:
    print(f"Entry: {pattern['first_signal_date'].date()} "
          f"${pattern['entry_price']:.2f} -> "
          f"Exit: {trade['exit_date'].date()} ${trade['exit_price']:.2f} "
          f"({trade['exit_reason']}) R={trade['r_multiple']:.1f}")
```

### Modo sequential (un trade a la vez)

```python
trades_seq = evaluate_signals_to_trades(
    signals=signals,
    ohlc=ohlc,
    risk_params=risk_params,
    grouping="sequential",
)

for pattern, trade in trades_seq:
    print(f"{trade['exit_reason']:15s} R={trade['r_multiple']:+.1f} "
          f"({trade['duration_days']}d)")
```

### Visualizacion

```python
from vcp_detection.analysis import plot_vcp_pattern, plot_trade_simulation

for i, (pattern, trade) in enumerate(trades, 1):
    # Grafico del patron VCP
    plot_vcp_pattern(ohlc, pattern, pattern_number=i, ticker="NVDA")

    # Grafico de la simulacion del trade
    plot_trade_simulation(
        ohlc, pattern, trade, pattern_number=i,
        risk_params=risk_params, ticker="NVDA",
    )
```

---

## 5. Ejecutar experimentos

El directorio `experiments/` contiene scripts organizados por tipo de activo:

```
experiments/
|-- autoresearch_phase1/            Notebook de optimizacion Optuna
|   |-- 01_run_optimization.ipynb
|
|-- stocks_exploration/             Exploracion en acciones
|   |-- run_vcp_full_filters.ipynb
|   |-- run_vcp_with_trend_template.ipynb
|   |-- run_stocks_temporal_stability.py
|
|-- stocks_sequential/              Stocks con agrupacion sequential
|   |-- run_stocks_sequential.py
|
|-- fx_exploration/                 Exploracion en FX
|   |-- run_fx_temporal_stability.py
|   |-- run_fx_temporal_stability_hourly.py
|   |-- compare_hourly_configs.py
|   |-- compare_hourly_no_early.py
|   |-- generate_signal_histogram.py
|
|-- fx_sequential/                  FX con agrupacion sequential
|   |-- run_fx_sequential_multicurrency.py
|
|-- informe_resultados_sequential.md  Reporte de resultados
```

### Ejecutar un script de experimento

```bash
# Desde el directorio raiz del proyecto
python experiments/stocks_sequential/run_stocks_sequential.py
python experiments/fx_sequential/run_fx_sequential_multicurrency.py
```

### Ejecutar un notebook

```bash
jupyter notebook experiments/autoresearch_phase1/01_run_optimization.ipynb
```

### Estructura tipica de un experimento

Cada directorio de experimento puede contener:
- Scripts `.py` para ejecucion automatizada
- Notebooks `.ipynb` para exploracion interactiva
- Archivos `.md` con reportes de resultados e insights (ej: `reporte_fx_experiment.md`)

---

## 6. Optimizacion con Optuna (autoresearch)

### Ejemplo completo

```python
from autoresearch import (
    SwingCache,
    build_objective_function,
    create_study,
    load_universe,
    filter_tickers_by_start_date,
    find_common_period,
    MLflowOptunaLogger,
    study_to_dataframe,
    top_trials_summary,
    param_importance,
    reconstruct_pipeline_params,
    run_backtest_for_params,
    trades_to_dataframe,
)

# 1. Cargar universo de datos
opt_tickers, oos_tickers = filter_tickers_by_start_date(
    data_dir="data/csv/",
    max_start_date="2015-01-01",
)
universe = load_universe(opt_tickers, data_dir="data/csv/", start_date="2016-01-01")
common_start, common_end = find_common_period(universe)

# 2. Crear cache y funcion objetivo
cache = SwingCache()
objective = build_objective_function(
    universe=universe,
    evaluation_window=(common_start, common_end),
    cache=cache,
)

# 3. Crear study Optuna
study = create_study(
    study_name="vcp_stocks_v1",
    n_startup_trials=20,
    seed=42,
)

# 4. Optimizar con logging MLflow
logger = MLflowOptunaLogger(experiment_name="autoresearch_vcp")
with logger.parent_run(study_name=study.study_name):
    study.optimize(objective, n_trials=100, callbacks=[logger.optuna_callback])
    logger.log_study_summary(study, n_tickers=len(universe))

# 5. Analizar resultados
print(f"Mejor score: {study.best_value:.4f}")
print(f"Mejores parametros: {study.best_params}")

# DataFrame con todos los trials
df = study_to_dataframe(study)
print(df.head(10))

# Top 10 trials
summary = top_trials_summary(study, n=10)
print(summary.to_string())

# Importancia de parametros (fANOVA)
imp = param_importance(study)
if imp is not None:
    print(imp.to_string())

# Stats del cache
print(f"Cache stats: {cache.stats()}")
```

### Usar el mejor trial para backtest

```python
# Reconstruir parametros del mejor trial
best_params = reconstruct_pipeline_params(study.best_params)

# Correr backtest con los mejores parametros
result = run_backtest_for_params(universe, best_params, cache=cache)
trades_df = trades_to_dataframe(result["all_trades"])
print(trades_df.to_string())
print(f"\nMetricas: {result['metrics']}")
```

### Out-of-sample validation

```python
# Cargar universe OOS
oos_universe = load_universe(oos_tickers, data_dir="data/csv/", start_date="2016-01-01")

# Correr con mismos parametros
oos_result = run_backtest_for_params(oos_universe, best_params)
print(f"OOS Metrics: {oos_result['metrics']}")
```

---

## 7. MLflow

### Lanzar la UI

```bash
mlflow ui --backend-store-uri mlruns/
```

Navegar a `http://localhost:5000`.

### Navegar experimentos

1. **Experiments** (sidebar izquierdo): Seleccionar el experimento (ej: "autoresearch_vcp").
2. **Runs**: Ver el parent run y expandir para ver child runs (un trial por run).
3. **Compare**: Seleccionar multiples runs para comparar metricas y parametros.
4. **Charts**: Visualizar scatter plots de parametros vs score.

### Metricas logueadas

- **Por trial** (child run): score, n_trades, expectancy_r, win_rate, profit_factor, avg_winner_r, avg_loser_r + todos los hiperparametros.
- **Resumen** (parent run): best_score, best_n_trades, best_expectancy_r, best_win_rate, best_profit_factor, total_trials, n_tickers + best_* para cada parametro.

---

## 8. Tests

### Ejecutar todos los tests

```bash
pytest tests/ -v
```

### Tests disponibles

| Archivo | Cobertura |
|---------|-----------|
| `tests/conftest.py` | Fixtures: datos sinteticos con VCP conocido |
| `tests/test_swing_detector.py` | Paso 1: deteccion de swings |
| `tests/test_contractions.py` | Paso 2: calculo de contracciones |
| `tests/test_decreasing_sequence.py` | Paso 3: secuencia decreciente |
| `tests/test_atr_compression.py` | Paso 4: compresion de ATR |
| `tests/test_pipeline.py` | Integracion: pasos 1-6 |

### Ejecutar un test especifico

```bash
pytest tests/test_swing_detector.py -v
pytest tests/test_pipeline.py -v -k "test_nombre_especifico"
```

### Tests con cobertura

```bash
pytest tests/ --cov=vcp_detection --cov=models --cov-report=html
```

---

## 9. Referencia de parametros

### Parametros del swing detector (Paso 1)

| Parametro | Tipo | Default | Descripcion |
|-----------|------|---------|-------------|
| `atr_length` | int | 14 | Periodo del ATR para threshold de reversion. ~3 semanas |
| `atr_mult` | float | 2.0 | Multiplo de ATR que el precio debe revertir para confirmar swing |
| `use_close_only` | bool | False | Si True, usa solo close en vez de high/low para comparar |

### Parametros de contracciones (Paso 2)

| Parametro | Tipo | Default | Descripcion |
|-----------|------|---------|-------------|
| `min_depth_pct` | float | 0.0 | Profundidad minima para incluir una contraccion (fraccion, ej: 0.02 = 2%) |
| `atr_period` | int | 14 | Periodo ATR para calcular depth_atr |

### Parametros de secuencia decreciente (Paso 3)

| Parametro | Tipo | Default | Descripcion |
|-----------|------|---------|-------------|
| `method` | str | "tolerance" | Metodo de monotonia: "strict", "tolerance", "robust_trend" |
| `min_contractions` | int | 2 | Minimo de contracciones para VCP valido |
| `max_contractions` | int | 6 | Maximo de contracciones a considerar |
| `lookback_bars` | int | 80 | Ventana temporal en barras de trading (~4 meses) |
| `tolerance` | float | 0.10 | Margen de tolerancia para method="tolerance" (10%) |
| `min_r_squared` | float | 0.5 | R^2 minimo para method="robust_trend" |
| `max_depth_pct` | float/None | None | Profundidad maxima permitida por contraccion |
| `max_depth_atr` | float/None | None | Profundidad maxima en multiplos de ATR |
| `min_total_reduction` | float/None | None | Ratio maximo depths[-1]/depths[0] |
| `max_gap_between_contractions_days` | int/None | None | Maximo dias calendario entre contracciones |
| `require_ascending_lows` | bool | True | Exigir que los lows sean ascendentes |
| `ascending_lows_tolerance` | float | 0.0 | Margen para lows ascendentes (0.02 = 2%) |

### Parametros de compresion de ATR (Paso 4)

| Parametro | Tipo | Default | Descripcion |
|-----------|------|---------|-------------|
| `method` | str | "ratio" | Metodo: "ratio", "trend", "ratio_normalized" |
| `atr_period` | int | 14 | Periodo del ATR (Wilder's RMA) |
| `ratio_threshold` | float | 0.7 | Umbral para ratio y ratio_normalized (0.85 = max 85%) |
| `min_r_squared` | float | 0.5 | R^2 minimo para method="trend" |

### Parametros de contraccion de volumen (Paso 5)

| Parametro | Tipo | Default | Descripcion |
|-----------|------|---------|-------------|
| `method` | str | "per_contraction" | Metodo: "ratio", "per_contraction", "trend" |
| `volume_column` | str | "volume" | Columna de volumen ("volume" o "transactions" para FX) |
| `tolerance` | float | 0.10 | Margen para method="per_contraction" |
| `ratio_threshold` | float | 0.8 | Umbral para method="ratio" |
| `min_r_squared` | float | 0.5 | R^2 minimo para method="trend" |

### Parametros de breakout (Paso 6)

| Parametro | Tipo | Default | Descripcion |
|-----------|------|---------|-------------|
| `volume_method` | str | "ratio" | Metodo de confirmacion: "ratio", "percentile" |
| `volume_ratio_threshold` | float | 1.5 | Multiplo sobre media de volumen (clasico Minervini: 1.5x) |
| `volume_percentile` | int | 80 | Percentil para method="percentile" |
| `volume_lookback_days` | int | 50 | Dias de lookback para baseline de volumen (~10 semanas) |
| `require_volume_confirmation` | bool | True | Si False, bypasea filtro de volumen (usar para FX) |

### Parametros de riesgo/salida (risk_params)

| Parametro | Tipo | Default | Descripcion |
|-----------|------|---------|-------------|
| `max_stop_loss_pct` | float | 0.07 | Stop loss maximo como % del entry. 0.02 para FX |
| `breakeven_r_multiple` | float | 2.0 | Escalones de breakeven (cada N*R sube el stop) |
| `trailing_sma_period` | int | 20 | Periodo SMA para trailing stop y distribution check |
| `trailing_volume_factor` | float | 1.5 | Factor de volumen para senal de distribucion |
| `trailing_stop_method` | str | "sma" | "sma" (distribucion check) o "atr" (ATR trailing) |
| `trailing_atr_period` | int | 14 | Periodo ATR para trailing stop ATR |
| `trailing_atr_multiplier` | float | 3.0 | Multiplo ATR: stop = highest_close - mult * ATR |
| `max_bars_without_progress` | int/None | None | Barras sin progreso antes de time exit |
| `min_progress_r` | float | 0.5 | Progreso minimo en R para resetear contador de time exit |
| `target_r_multiple` | float/None | None | Target de ganancia en R (cierra si se alcanza) |
| `early_exit_days` | int/None | None | Dias iniciales: cierra si close < entry |

### Parametros de agrupacion

| Parametro | Tipo | Default | Descripcion |
|-----------|------|---------|-------------|
| `grouping` | str | "gap" | Modo de agrupacion: "gap" o "sequential" |
| `max_gap_days` | int | 30 | Gap maximo entre senales para agruparlas (solo mode "gap") |

### Parametros del pipeline completo (run_full_vcp_pipeline)

| Parametro | Tipo | Default | Descripcion |
|-----------|------|---------|-------------|
| `evaluation_dates` | DatetimeIndex/None | None (=todo) | Fechas a evaluar |
| `deduplicate` | bool | False | Si True, emite solo primera senal por patron |
| `dedup_cooldown_bars` | int | 1 | Barras de cooldown tras invalidacion del patron |
| `precomputed_swings` | list/None | None | Swings precalculados (para optimizacion) |
| `precomputed_contractions` | list/None | None | Contracciones precalculadas |
| `precomputed_atr` | Series/None | None | ATR precalculado |
