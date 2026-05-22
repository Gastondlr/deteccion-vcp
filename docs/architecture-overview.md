# Arquitectura General del Proyecto

Deteccion algorítmica de patrones VCP (Volatility Contraction Pattern) segun el metodo SEPA de Mark Minervini, aplicado a acciones y pares FX.

---

## 1. Diagrama de componentes

```
                              deteccion-vcp
  ============================================================================

  data/csv/                     Datos OHLCV crudos (un CSV por ticker)
      |                         Columnas: date, open, high, low, close, volume
      v
  models/                       Dataclasses, configs y enums
  |-- enums.py                  SwingType (HIGH | LOW)
  |-- configs.py                ATRZigZagConfig (atr_length, atr_mult, use_close_only)
  |-- types.py                  SwingPoint, Contraction, DecreasingSequence,
      |                         ATRCompressionResult, VolumeContractionResult,
      |                         PivotInfo, VCPSignal
      v
  vcp_detection/heuristic/      Pipeline de deteccion (6 pasos secuenciales)
  |-- swing_detector.py         Paso 1: ATRZigZagDetector -> list[SwingPoint]
  |-- contractions.py           Paso 2: compute_contractions -> list[Contraction]
  |-- decreasing_sequence.py    Paso 3: detect_decreasing_sequence -> DecreasingSequence
  |-- atr_compression.py        Paso 4: verify_atr_compression -> ATRCompressionResult
  |-- volume_contraction.py     Paso 5: verify_volume_contraction -> VolumeContractionResult
  |-- pivot_breakout.py         Paso 6: detect_breakout_signal -> VCPSignal
  |                             + run_full_vcp_pipeline (orquestador)
      |
      v
  vcp_detection/analysis.py     Simulacion de trades
  |                             evaluate_signals_to_trades, simulate_trade
  |                             group_signals_into_patterns
  |                             plot_vcp_pattern, plot_trade_simulation
      |
      v
  stages/trend_template.py      Filtro pre-VCP: Plantilla de Tendencia (7 condiciones Stage 2)
      |
      v
  autoresearch/                 Optimizacion de hiperparametros con Optuna
  |-- search_space.py           sample_params (define ~20 parametros a optimizar)
  |-- objective.py              build_objective_function, create_study
  |-- backtest.py               run_backtest_for_params, compute_objective_score
  |-- caching.py                SwingCache (cache de pasos 1+2)
  |-- data_loader.py            load_universe, filter_tickers_by_start_date
  |-- mlflow_integration.py     MLflowOptunaLogger (parent/child runs)
  |-- results.py                study_to_dataframe, param_importance, reconstruct_pipeline_params
      |
      v
  experiments/                  Scripts y notebooks de experimentacion
  |-- autoresearch_phase1/      Notebook de optimizacion Optuna
  |-- stocks_exploration/       Exploracion sobre acciones (filtros, trend template)
  |-- stocks_sequential/        Experimentos con agrupacion sequential en stocks
  |-- fx_exploration/           Exploracion sobre pares FX (hourly, stability)
  |-- fx_sequential/            Experimentos con agrupacion sequential en FX
      |
      v
  MLflow (mlruns/)              Tracking de metricas, parametros y artefactos
```

### Flujo de datos resumido

```
CSV OHLCV --> [Pipeline 6 pasos] --> VCPSignal --> [Simulacion] --> Trades --> [Metricas]
                                                                                    |
                                                                                    v
                                                                [Optuna] <-- score = f(metricas)
                                                                    |
                                                                    v
                                                                [MLflow] --> UI de resultados
```

---

## 2. Reglas de dependencia

El proyecto sigue un grafo de dependencias acíclico estricto. Los modulos se organizan en capas donde cada capa solo depende de capas inferiores.

```
Capa 0 (base):     models/enums.py
                        |
Capa 1 (configs):   models/configs.py     (depende de nada)
                        |
Capa 2 (types):     models/types.py       (depende de enums)
                        |
Capa 3 (pipeline):  vcp_detection/heuristic/
                    swing_detector.py      (depende de configs, enums, types)
                    contractions.py        (depende de types, enums, atr_compression)
                    decreasing_sequence.py (depende de types)
                    atr_compression.py     (depende de types)
                    volume_contraction.py  (depende de types)
                    pivot_breakout.py      (depende de types, y todos los pasos 1-5)
                        |
Capa 4 (analisis):  vcp_detection/analysis.py  (depende de types, atr_compression)
                    stages/trend_template.py   (independiente, solo usa pandas)
                        |
Capa 5 (optuna):    autoresearch/              (depende de capas 3 y 4)
```

**Regla clave**: Ningun modulo de `models/` importa de `vcp_detection/` ni `autoresearch/`. Las dependencias son estrictamente unidireccionales.

**Nota sobre `contractions.py`**: Importa `compute_atr` de `atr_compression.py` para calcular `depth_atr` (profundidad normalizada por ATR). Esta es la unica dependencia cruzada dentro de la capa del pipeline.

---

## 3. Patrones de diseno

### Pipeline Pattern (filtro secuencial)

El nucleo del sistema es un pipeline de 6 pasos donde cada paso filtra candidatos:

```
Datos -> Paso 1 (swings) -> Paso 2 (contracciones) -> Paso 3 (secuencia decreciente)
      -> Paso 4 (ATR compression) -> Paso 5 (volume contraction) -> Paso 6 (breakout)
```

Cada paso recibe la salida del anterior y produce un tipo de dato distinto. Si un paso no genera resultado (`None`), el pipeline corta para esa fecha de evaluacion. Esta logica esta orquestada en `run_full_vcp_pipeline()`.

### Strategy Pattern (detectores intercambiables)

`SwingDetector` es una clase abstracta (ABC) con el metodo `detect()`. La implementacion concreta `ATRZigZagDetector` puede reemplazarse por otro detector sin cambiar el pipeline. El contrato exige retornar `list[SwingPoint]` con tipos alternados HIGH/LOW.

### Configuration Objects (dataclasses inmutables)

Los parametros del detector se encapsulan en `ATRZigZagConfig`, un dataclass con defaults sensatos. Esto separa la configuracion de la logica y permite serializar/deserializar desde YAML.

### Anti Look-Ahead (confirmed_at)

Cada `SwingPoint` tiene un campo `confirmed_at` que registra la fecha en que el swing fue confirmado por el detector (posterior a la fecha del extremo). Todos los pasos posteriores filtran por `confirmed_at <= evaluation_date`, garantizando que el backtesting no usa informacion futura. Las `Contraction` heredan `confirmed_at = max(high.confirmed_at, low.confirmed_at)`.

### Closure Pattern (funcion objetivo)

`build_objective_function()` retorna un closure que captura el universo de datos y el cache, exponiendo solo la interfaz `(Trial) -> float` que Optuna requiere.

---

## 4. Convenciones

| Aspecto | Convencion |
|---------|------------|
| Archivos | `snake_case.py` |
| Clases | `PascalCase` (ej: `ATRZigZagDetector`, `SwingCache`) |
| Funciones | `snake_case` (ej: `compute_contractions`, `detect_breakout_signal`) |
| Constantes | `UPPER_SNAKE_CASE` (ej: `N_MIN_TRADES`, `_REQUIRED_COLUMNS`) |
| Type hints | Todos los parametros y retornos tienen type hints |
| Docstrings | Google style con secciones Args, Returns, Raises |
| Comentarios | En espanol (sin acentos en terminos tecnicos) |
| Dataclasses | `frozen=True` para tipos de datos inmutables del pipeline |
| Logging | `logging.getLogger(__name__)` en cada modulo |
| Validacion | Cada funcion publica valida sus inputs y lanza `ValueError` |
| Imports | `from __future__ import annotations` en todos los modulos |

---

## 5. Recetas de extension

### Agregar un nuevo swing detector

1. Crear una clase que herede de `SwingDetector` (en `swing_detector.py` o nuevo archivo).
2. Implementar el metodo `detect(self, ohlc: pd.DataFrame) -> list[SwingPoint]`.
3. Asegurar que los swings alternan HIGH/LOW y tienen `confirmed_at` valido.
4. Registrar la clase en `vcp_detection/heuristic/__init__.py`.

```python
class MiDetector(SwingDetector):
    def __init__(self, config: MiConfig) -> None:
        self.config = config

    def detect(self, ohlc: pd.DataFrame) -> list[SwingPoint]:
        self._validate_ohlc(ohlc)
        # ... logica de deteccion ...
        return swings  # list[SwingPoint] alternando HIGH/LOW
```

Luego usarlo:

```python
detector = MiDetector(MiConfig(...))
results = run_full_vcp_pipeline(ohlc=ohlc, swing_detector=detector, ...)
```

### Agregar un nuevo mecanismo de salida

1. Editar `simulate_trade()` en `vcp_detection/analysis.py`.
2. Agregar el parametro al dict `risk_params` (extraerlo al inicio de la funcion).
3. Agregar la logica de evaluacion dentro del loop `for loc in range(...)`, en el orden de prioridad correcto.
4. Retornar con `_make_result(dt, close, profit, "mi_exit_reason")`.
5. Agregar la razon al dict `exit_colors`/`exit_markers` en `plot_trade_simulation`.

**Orden de evaluacion de salidas** (en `simulate_trade`):
1. Breakeven escalator (actualiza stop)
2. ATR trailing stop (actualiza stop)
3. Target R-multiple
4. Early exit
5. Stop loss / trailing stop (close <= stop)
6. SMA distribution check
7. Time exit (max bars sin progreso)

### Agregar un nuevo parametro a la optimizacion

1. Agregar `trial.suggest_*()` en `sample_params()` (`autoresearch/search_space.py`).
2. Colocar el valor en el dict de parametros correspondiente (sequence_params, risk_params, etc.).
3. Agregar la reconstruccion inversa en `reconstruct_pipeline_params()` (`autoresearch/results.py`).
4. Opcionalmente incluirlo en `top_trials_summary()` para visualizacion.

### Agregar un nuevo metodo de compresion/volumen

Los pasos 3, 4 y 5 soportan multiples metodos. Para agregar uno:

1. Implementar la funcion `_check_mi_metodo()` que retorne `tuple[bool, dict]`.
2. Agregar el nombre al set `_VALID_METHODS`.
3. Agregar el branch al `if/elif` en la funcion `verify_*` principal.
4. Si tiene parametros nuevos, agregarlos como kwargs con defaults.
