# Deteccion de Patrones VCP (Volatility Contraction Pattern)

Implementacion del detector heuristico de patrones **VCP** (*Volatility Contraction Pattern*) segun el metodo **SEPA** (*Specific Entry Point Analysis*) de Mark Minervini.

El VCP es un patron de consolidacion donde, despues de un avance significativo, una accion forma una base con contracciones de precio cada vez menores, volatilidad decreciente, y volumen en descenso. Cuando el precio supera el nivel de resistencia (pivote) con volumen alto, se genera una senal de compra.

---

## Pipeline de deteccion — 7 pasos

```
OHLCV data (CSV)
    |
    v
[Paso 0] Carga y validacion de datos         -> pd.DataFrame (OHLCV)
    |
    v
[Paso 1] Swing Detection (ATR ZigZag)        -> list[SwingPoint]
    |
    v
[Paso 2] Contraction Calculation              -> list[Contraction]
    |
    v
[Paso 3] Decreasing Sequence Detection        -> DecreasingSequence | None
         + Quality Filters
    |
    v
[Paso 4] ATR Compression Verification         -> ATRCompressionResult
    |
    v
[Paso 5] Volume Contraction Verification      -> VolumeContractionResult
    |
    v
[Paso 6] Pivot + Breakout Signal              -> VCPSignal | None
```

---

## Descripcion detallada de cada paso

### Paso 0 — Carga y validacion de datos

**Archivo**: No tiene modulo propio; se realiza en el notebook o script caller.

**Que hace**: Lee un CSV con datos OHLCV (Open, High, Low, Close, Volume) de una accion, parsea fechas como indice, y valida que las columnas requeridas existan.

**Formato del CSV esperado**:
| Columna | Descripcion |
|---------|-------------|
| `date` | Fecha de la barra (YYYY-MM-DD) |
| `open` | Precio de apertura |
| `high` | Precio maximo |
| `low` | Precio minimo |
| `close` | Precio de cierre |
| `volume` | Volumen transaccionado |

Columnas opcionales: `vwap` (Volume Weighted Average Price), `transactions`.

**Libreria**: `pandas.read_csv` con `parse_dates=["date"]` e `index_col="date"`.

**Ejemplo**:
```python
import pandas as pd

ohlc = pd.read_csv("data/csv/NVDA.csv", parse_dates=["date"], index_col="date")
ohlc = ohlc.loc["2016-01-01":].copy()
```

---

### Paso 1 — Deteccion de Swing Points (ATR ZigZag)

**Archivo**: `vcp_detection/heuristic/swing_detector.py`

**Que hace**: Identifica los maximos y minimos locales significativos (swing points) en la serie de precios. Estos puntos definen la estructura del patron VCP.

**Algoritmo (ATR ZigZag)**:
1. Calcula el **ATR** (Average True Range) con periodo configurable (default 14 barras).
2. Recorre la serie barra a barra manteniendo:
   - Una **direccion** actual: UP (buscando highs) o DOWN (buscando lows).
   - Un **extremo candidato**: el high o low mas extremo visto en la direccion actual.
3. Cuando el precio revierte al menos `atr_mult * ATR` desde el extremo, **confirma** el swing y cambia de direccion.
4. Cada swing registra `confirmed_at` — la fecha en que se confirmo la reversion (no la fecha del extremo), para evitar look-ahead bias.

**Calculo del ATR (True Range)**:
```
TR_t = max(High_t - Low_t, |High_t - Close_{t-1}|, |Low_t - Close_{t-1}|)
ATR = SMA(TR, period)
```

**Parametros**:
| Parametro | Default | Descripcion |
|-----------|---------|-------------|
| `atr_length` | 14 | Periodo del ATR (~3 semanas) |
| `atr_mult` | 2.0 | Multiplo de ATR para confirmar reversion |
| `use_close_only` | False | Si True, usa solo close; si False, usa high/low |

**Librerias**:
- `numpy`: Operaciones vectorizadas (True Range, argmax/argmin).
- `pandas`: Rolling window para SMA del True Range.
- `scipy.signal.find_peaks`: Solo en el detector alternativo (ScipyPeaksDetector).

**Output**: `list[SwingPoint]` alternando HIGH y LOW en orden cronologico.

**Ejemplo**:
```python
from models.configs import ATRZigZagConfig
from vcp_detection.heuristic import ATRZigZagDetector

detector = ATRZigZagDetector(ATRZigZagConfig(atr_length=14, atr_mult=2.0))
swings = detector.detect(ohlc)
# [SwingPoint(date=2023-03-15, price=15.2, type=HIGH, confirmed_at=2023-03-22), ...]
```

---

### Paso 2 — Calculo de Contracciones

**Archivo**: `vcp_detection/heuristic/contractions.py`

**Que hace**: Calcula las contracciones de precio entre cada par (HIGH, LOW) consecutivo. Una contraccion es la caida porcentual desde un pico hasta el valle siguiente.

**Calculo**:
```
depth_pct = (high_swing.price - low_swing.price) / high_swing.price
depth_abs = high_swing.price - low_swing.price
```

**Ejemplo**: Si el high es $100 y el low es $85, la contraccion es 15%.

**Validaciones**:
- Los swings deben estar ordenados cronologicamente.
- Los swings deben alternar HIGH/LOW.
- Pares (LOW, HIGH) se ignoran (representan subidas, no contracciones).
- Opcionalmente filtra por `min_depth_pct` para descartar contracciones triviales.

**Librerias**: `pandas` (para contar barras de trading reales entre fechas).

**Output**: `list[Contraction]` ordenada cronologicamente.

**Ejemplo**:
```python
from vcp_detection.heuristic import compute_contractions

contractions = compute_contractions(swings, ohlc)
# [Contraction(depth_pct=0.15, duration_bars=12), Contraction(depth_pct=0.10, ...), ...]
```

---

### Paso 3 — Deteccion de Secuencia Decreciente + Filtros de Calidad

**Archivo**: `vcp_detection/heuristic/decreasing_sequence.py`

**Que hace**: Evalua si las ultimas N contracciones dentro de una ventana temporal forman una secuencia monotonicamente decreciente. Esta es la **regla central** del patron VCP.

**Algoritmo**:
1. Filtra contracciones por `confirmed_at <= evaluation_date` (anti look-ahead).
2. Filtra por ventana temporal (`lookback_bars` barras hacia atras).
3. Prueba las ultimas k contracciones (de `max_contractions` a `min_contractions`). Retorna la secuencia mas larga que pase.
4. Aplica filtros de calidad opcionales.

**Metodos de monotonia**:
| Metodo | Descripcion | Libreria |
|--------|-------------|----------|
| `"strict"` | Cada depth[i+1] < depth[i] estrictamente | Python puro |
| `"tolerance"` (recomendado) | depth[i+1] <= depth[i] * (1 + tolerance) | Python puro |
| `"robust_trend"` | Regresion lineal con pendiente negativa y R^2 minimo | `scipy.stats.linregress` |

**Filtros de calidad**:
| Filtro | Descripcion | Ejemplo |
|--------|-------------|---------|
| `max_depth_pct` | Rechaza si alguna contraccion > umbral | 0.25 = max 25% |
| `min_total_reduction` | Exige depths[-1]/depths[0] <= umbral | 0.70 = la ultima debe ser <= 70% de la primera |

**Parametros**:
| Parametro | Default | Descripcion |
|-----------|---------|-------------|
| `method` | "tolerance" | Metodo de monotonia |
| `min_contractions` | 2 | Minimo para VCP valido |
| `max_contractions` | 6 | Maximo (bases largas son sospechosas) |
| `lookback_bars` | 126 | ~6 meses de trading |
| `tolerance` | 0.10 | 10% de margen (solo con method="tolerance") |
| `max_depth_pct` | None | Filtro de profundidad maxima |
| `min_total_reduction` | None | Filtro de reduccion total |

**Librerias**: `numpy`, `scipy.stats.linregress` (solo para "robust_trend").

**Output**: `DecreasingSequence | None`.

---

### Paso 4 — Verificacion de Compresion de ATR

**Archivo**: `vcp_detection/heuristic/atr_compression.py`

**Que hace**: Verifica que la volatilidad intradia (ATR) se comprime durante el patron. No basta con que las contracciones de precio sean menores — la volatilidad general tambien debe disminuir.

**Calculo del ATR (Wilder's Smoothing / RMA)**:
```
TR_t = max(H_t - L_t, |H_t - C_{t-1}|, |L_t - C_{t-1}|)
ATR_0 = SMA(TR[1:period+1])                    # Primer valor: SMA
ATR_t = ATR_{t-1} * (1 - 1/period) + TR_t * (1/period)  # Recursivo
```

> **Nota**: El ATR del Paso 1 usa SMA simple; este usa Wilder's RMA (mas suave, estandar de la industria).

**Metodos**:
| Metodo | Calculo | Parametros |
|--------|---------|------------|
| `"ratio"` (recomendado) | ATR_end / ATR_start <= threshold | `ratio_threshold=0.85` |
| `"trend"` | Regresion lineal del ATR, pendiente < 0 y R^2 >= min | `min_r_squared=0.5` |
| `"ratio_normalized"` | (ATR_end/P_end) / (ATR_start/P_start) <= threshold | `ratio_threshold=0.85` |

**Librerias**: `numpy`, `pandas`, `scipy.stats.linregress` (para "trend").

**Output**: `ATRCompressionResult` con `passes: bool` y metricas del calculo.

---

### Paso 5 — Verificacion de Contraccion de Volumen

**Archivo**: `vcp_detection/heuristic/volume_contraction.py`

**Que hace**: Verifica que el volumen decrece durante la formacion del patron. Segun Minervini, la **oferta debe secarse** — si el volumen se mantiene alto, indica presion vendedora persistente.

**Calculo**: Para cada contraccion de la secuencia, calcula el volumen promedio en el rango [high_date, low_date]:
```
avg_vol_i = mean(volume[high_date_i : low_date_i])
```

**Metodos**:
| Metodo | Descripcion | Parametros |
|--------|-------------|------------|
| `"ratio"` (recomendado) | vol_last / vol_first <= threshold | `ratio_threshold=0.85` |
| `"per_contraction"` | Cada contraccion tiene menor vol que la anterior (con tolerancia) | `tolerance=0.10` |
| `"trend"` | Regresion lineal sobre volumenes promedio | `min_r_squared=0.5` |

**Librerias**: `numpy`, `pandas`, `scipy.stats.linregress` (para "trend").

**Output**: `VolumeContractionResult` con `passes: bool` y volumenes promedio.

---

### Paso 6 — Pivote + Senal de Breakout

**Archivo**: `vcp_detection/heuristic/pivot_breakout.py`

**Que hace**: Identifica el punto de pivote y genera una senal de compra cuando el precio lo supera con confirmacion de volumen.

**Identificacion del pivote**:
- El pivote es el `high_swing.price` de la **ultima** contraccion de la secuencia.
- El stop-loss natural es el `low_swing.price` de esa misma contraccion.

**Trigger de breakout** (ambas condiciones deben cumplirse):
1. `close_today > pivot_price` — el precio supero la resistencia.
2. Confirmacion de volumen (opcional):
   - `"ratio"`: `volume_today >= ratio_threshold * mean(volume_50d)`. Default: 1.5x (clasico de Minervini).
   - `"percentile"`: `volume_today >= percentil_P(volume_50d)`.

**Parametros del breakout**:
| Parametro | Default | Descripcion |
|-----------|---------|-------------|
| `volume_method` | "ratio" | Metodo de confirmacion |
| `volume_ratio_threshold` | 1.5 | 1.5x el promedio de 50 dias |
| `volume_lookback_days` | 50 | Baseline de ~10 semanas |
| `require_volume_confirmation` | True | Si False, bypasea volumen |

**Librerias**: `numpy` (percentiles), `pandas` (acceso a datos por fecha).

**Output**: `VCPSignal | None` con entry_price, pivot_price, suggested_stop, y toda la trazabilidad.

**Ejemplo de VCPSignal**:
```python
VCPSignal(
    signal_date=Timestamp('2024-01-08'),
    entry_price=52.25,
    pivot_price=50.43,
    suggested_stop=47.32,
    suggested_stop_distance_pct=0.094,
    metadata={'n_contractions': 4, 'depths_pct': [0.179, 0.176, 0.110, 0.062]},
)
```

---

## Estructura del proyecto

```
deteccion-vcp/
├── README.md                   # Este archivo
├── pyproject.toml              # Dependencias y configuracion
│
├── models/                     # Dataclasses y tipos
│   ├── __init__.py
│   ├── enums.py                # SwingType (HIGH, LOW)
│   ├── configs.py              # ATRZigZagConfig, ScipyPeaksConfig
│   └── types.py                # SwingPoint, Contraction, DecreasingSequence,
│                               # ATRCompressionResult, VolumeContractionResult,
│                               # PivotInfo, VCPSignal
│
├── vcp_detection/              # Pipeline de deteccion
│   ├── __init__.py
│   └── heuristic/
│       ├── __init__.py         # Re-exports de todas las funciones publicas
│       ├── swing_detector.py   # Paso 1: ATRZigZagDetector, ScipyPeaksDetector
│       ├── contractions.py     # Paso 2: compute_contractions
│       ├── decreasing_sequence.py  # Paso 3: detect_decreasing_sequence
│       ├── atr_compression.py  # Paso 4: verify_atr_compression
│       ├── volume_contraction.py   # Paso 5: verify_volume_contraction
│       └── pivot_breakout.py   # Paso 6: detect_breakout_signal, run_full_vcp_pipeline
│
├── notebooks/
│   └── 06_vcp_detection_demo.ipynb  # Demo completo sobre NVDA
│
├── data/
│   └── csv/                    # Colocar CSVs OHLCV aqui
│
└── tests/
    ├── conftest.py             # Fixtures: datos sinteticos con VCP conocido
    ├── test_swing_detector.py  # Tests Paso 1
    ├── test_contractions.py    # Tests Paso 2
    ├── test_decreasing_sequence.py  # Tests Paso 3
    ├── test_atr_compression.py     # Tests Paso 4
    └── test_pipeline.py        # Tests de integracion (Pasos 1-6)
```

---

## Instalacion

```bash
cd deteccion-vcp
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Ejecucion de tests

```bash
pytest tests/ -v
```

## Uso rapido

```python
import pandas as pd
from models.configs import ATRZigZagConfig
from vcp_detection.heuristic import ATRZigZagDetector, run_full_vcp_pipeline

# Cargar datos
ohlc = pd.read_csv("data/csv/NVDA.csv", parse_dates=["date"], index_col="date")

# Configurar detector
detector = ATRZigZagDetector(ATRZigZagConfig(atr_length=14, atr_mult=2.0))

# Ejecutar pipeline completo
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

# Filtrar senales
signals = {dt: sig for dt, sig in results.items() if sig is not None}
print(f"Senales detectadas: {len(signals)}")

for dt, sig in signals.items():
    print(f"  {dt.date()}: entry=${sig.entry_price:.2f}, "
          f"pivot=${sig.pivot_price:.2f}, stop=${sig.suggested_stop:.2f}")
```

---

## Dependencias

| Libreria | Version | Uso |
|----------|---------|-----|
| `numpy` | >= 1.24 | Operaciones vectorizadas, ATR, percentiles |
| `pandas` | >= 2.0 | Series temporales, OHLCV, rolling windows |
| `scipy` | >= 1.10 | `linregress` (regresion lineal), `find_peaks` (detector alternativo) |
| `matplotlib` | >= 3.7 | Visualizacion en notebooks |
| `pyyaml` | >= 6.0 | Carga de configuracion desde YAML |

---

## Origen

Extraido del proyecto [minervini-sepa](https://github.com/Gastondlr/minervini-sepa) — implementacion del metodo SEPA de Mark Minervini para stock selection como parte de una tesis de Licenciatura en Fisica.
