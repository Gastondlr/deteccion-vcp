# Pipeline de Deteccion VCP: 6 Pasos en Detalle

El pipeline heuristico evalua, para cada fecha del historico, si existe un patron VCP (Volatility Contraction Pattern) valido. Los 6 pasos se ejecutan secuencialmente; si cualquier paso falla, la evaluacion corta y retorna `None` para esa fecha.

---

## Vision general del pipeline

```
OHLCV data (CSV)
    |
    v
[Paso 1] Swing Detection (ATR ZigZag)          -> list[SwingPoint]
    |
    v
[Paso 2] Contraction Calculation                -> list[Contraction]
    |
    v
[Paso 3] Decreasing Sequence + Quality Filters  -> DecreasingSequence | None
    |
    v
[Paso 4] ATR Compression Verification           -> ATRCompressionResult
    |
    v
[Paso 5] Volume Contraction Verification        -> VolumeContractionResult
    |
    v
[Paso 6] Pivot + Breakout Signal                -> VCPSignal | None
```

**Nota**: Los pasos 1 y 2 se ejecutan una sola vez sobre toda la serie. Los pasos 3-6 se evaluan fecha a fecha.

---

## Paso 1 -- Deteccion de Swing Points (ATR ZigZag)

### Algoritmo

El ATR ZigZag recorre la serie barra a barra manteniendo una **direccion** (UP o DOWN) y un **extremo candidato**:

1. Calcula el ATR (Average True Range) con SMA simple sobre `atr_length` barras.
2. En direccion UP, rastrea el high mas alto. Cuando el precio cae al menos `atr_mult * ATR` desde ese high, confirma el swing HIGH y cambia a DOWN.
3. En direccion DOWN, rastrea el low mas bajo. Cuando el precio sube al menos `atr_mult * ATR` desde ese low, confirma el swing LOW y cambia a UP.
4. Al cambiar de direccion, busca el extremo inicial en el rango entre el swing confirmado y la barra actual (`_find_initial_extreme`).

### Calculo del ATR (SMA)

```
TR_t = max(High_t - Low_t, |High_t - Close_{t-1}|, |Low_t - Close_{t-1}|)
ATR = SMA(TR, period)    # con min_periods=1
```

### Anti look-ahead: confirmed_at

Cada `SwingPoint` registra dos fechas:
- `date`: fecha del extremo real (el high o low en la serie).
- `confirmed_at`: fecha en que el detector confirmo la reversion (posterior a `date`).

Todos los pasos posteriores filtran por `confirmed_at <= evaluation_date`. Esto garantiza que en backtesting no se usa informacion futura.

### Parametros

| Parametro | Tipo | Default | Rango tipico | Descripcion |
|-----------|------|---------|--------------|-------------|
| `atr_length` | int | 14 | 10-25 | Periodo del ATR (~3 semanas) |
| `atr_mult` | float | 2.0 | 1.5-3.5 | Multiplo de ATR para confirmar reversion |
| `use_close_only` | bool | False | - | Si True, usa solo close en vez de high/low |

### Codigo

- **Archivo**: `vcp_detection/heuristic/swing_detector.py`
- **Clase**: `ATRZigZagDetector`
- **ABC**: `SwingDetector` (permite implementaciones alternativas)
- **Config**: `models/configs.py` -> `ATRZigZagConfig`
- **Input**: `pd.DataFrame` con columnas open, high, low, close y DatetimeIndex
- **Output**: `list[SwingPoint]` alternando HIGH y LOW

---

## Paso 2 -- Calculo de Contracciones

### Algoritmo

Recorre la lista de swings en pares consecutivos (HIGH, LOW):

1. Para cada par donde `high_sw.type == HIGH` y `low_sw.type == LOW`:
   - Calcula `depth_pct = (high.price - low.price) / high.price`
   - Calcula `depth_abs = high.price - low.price`
   - Calcula `depth_atr = depth_abs / ATR(high.date)` (si se provee ohlc)
   - Cuenta `duration_bars` entre las dos fechas
2. Filtra swings no confirmados (`metadata["confirmed"] == False`)
3. Descarta contracciones con `depth_pct < min_depth_pct`
4. Hereda `confirmed_at = max(high.confirmed_at, low.confirmed_at)`

### Parametros

| Parametro | Tipo | Default | Descripcion |
|-----------|------|---------|-------------|
| `min_depth_pct` | float | 0.0 | Profundidad minima para incluir contraccion |
| `atr_period` | int | 14 | Periodo para calcular ATR de `depth_atr` |

### Codigo

- **Archivo**: `vcp_detection/heuristic/contractions.py`
- **Funcion**: `compute_contractions(swings, ohlc, min_depth_pct, atr_period)`
- **Input**: `list[SwingPoint]` + `pd.DataFrame` opcional
- **Output**: `list[Contraction]` ordenada cronologicamente

### Validaciones

- Swings deben estar ordenados cronologicamente
- Swings deben alternar HIGH/LOW (no permite dos consecutivos del mismo tipo)
- Si `low.price >= high.price`, se loguea warning y se salta el par

---

## Paso 3 -- Deteccion de Secuencia Decreciente + Filtros de Calidad

### Algoritmo

1. Filtra contracciones por `confirmed_at <= evaluation_date` (anti look-ahead).
2. Filtra por ventana temporal: solo contracciones con `low_swing.date >= cutoff`, donde cutoff es `lookback_bars` barras hacia atras.
3. Prueba las ultimas `k` contracciones para `k` desde `max_contractions` hasta `min_contractions`. Retorna la primera (mas larga) que pase.
4. Aplica filtros de calidad sobre la secuencia candidata.

### Metodos de monotonia

| Metodo | Descripcion | Criterio | Dependencias |
|--------|-------------|----------|--------------|
| `"strict"` | Cada `depth[i+1] < depth[i]` estrictamente | Muy restrictivo, sensible a ruido | Python puro |
| `"tolerance"` | `depth[i+1] <= depth[i] * (1 + tolerance)` | Recomendado. Con tolerance=0.10, si la anterior fue 8% se acepta hasta 8.8% | Python puro |
| `"robust_trend"` | Regresion lineal con pendiente < 0 y R^2 >= umbral | Requiere minimo 3 contracciones | `scipy.stats.linregress` |

### Filtros de calidad (post-monotonia)

| Filtro | Parametro | Descripcion | Ejemplo |
|--------|-----------|-------------|---------|
| Profundidad maxima % | `max_depth_pct` | Rechaza si alguna contraccion supera este umbral | 0.25 = max 25% |
| Profundidad maxima ATR | `max_depth_atr` | Rechaza si alguna contraccion supera N multiplos de ATR | 5.0 ATR |
| Reduccion total | `min_total_reduction` | Exige `depths[-1]/depths[0] <= umbral` | 0.70 = ultima <= 70% de la primera |
| Gap entre contracciones | `max_gap_between_contractions_days` | Rechaza si la recuperacion entre contracciones es demasiado larga | 60 dias |
| Lows ascendentes | `require_ascending_lows` | Exige `low[i+1] >= low[i] * (1 - tolerance)` | Compradores entrando mas alto |

### Parametros

| Parametro | Tipo | Default | Rango tipico | Descripcion |
|-----------|------|---------|--------------|-------------|
| `method` | str | "tolerance" | - | Metodo de monotonia |
| `min_contractions` | int | 2 | 2-3 | Minimo para VCP valido |
| `max_contractions` | int | 6 | 5-7 | Maximo (bases muy largas son sospechosas) |
| `lookback_bars` | int | 80 | 80-140 | Ventana temporal en barras de trading |
| `tolerance` | float | 0.10 | 0.05-0.20 | Margen para method="tolerance" |
| `max_depth_pct` | float | None | 0.25-0.45 | Profundidad maxima por contraccion |
| `max_depth_atr` | float | None | 3.0-7.0 | Profundidad maxima en ATR |
| `min_total_reduction` | float | None | 0.65-0.90 | Ratio maximo ultima/primera |
| `max_gap_between_contractions_days` | int | None | - | Maximo dias entre contracciones |
| `require_ascending_lows` | bool | True | - | Exigir lows ascendentes |
| `ascending_lows_tolerance` | float | 0.0 | 0.0-0.05 | Margen para lows ascendentes |

### Codigo

- **Archivo**: `vcp_detection/heuristic/decreasing_sequence.py`
- **Funcion**: `detect_decreasing_sequence(contractions, evaluation_date, ...)`
- **Funcion batch**: `scan_for_sequences(contractions, evaluation_dates, ...)`
- **Input**: `list[Contraction]` + `pd.Timestamp`
- **Output**: `DecreasingSequence | None`

---

## Paso 4 -- Verificacion de Compresion de ATR

### Algoritmo

Verifica que la volatilidad intradia (ATR) se comprime durante la formacion del patron. El rango temporal se define entre el primer `high_swing.date` y el ultimo `low_swing.date` de la secuencia.

### Calculo del ATR (Wilder's Smoothing / RMA)

Esta version usa Wilder's RMA, distinto de la SMA del Paso 1:

```
TR_t = max(H_t - L_t, |H_t - C_{t-1}|, |L_t - C_{t-1}|)
ATR_0 = SMA(TR[1:period+1])                    # Primer valor: SMA
ATR_t = ATR_{t-1} * (1 - 1/period) + TR_t * (1/period)  # Recursivo (alpha = 1/period)
```

El RMA es mas suave que la SMA y reacciona mas lentamente a cambios bruscos, ideal para medir compresion de volatilidad a mediano plazo.

### Metodos

| Metodo | Calculo | Criterio |
|--------|---------|----------|
| `"ratio"` | `ATR_end / ATR_start` | `<= ratio_threshold` (ej: 0.85 exige 15% de compresion) |
| `"trend"` | Regresion lineal del ATR en el rango | Pendiente < 0 y R^2 >= min_r_squared |
| `"ratio_normalized"` | `(ATR_end/P_end) / (ATR_start/P_start)` | `<= ratio_threshold` (corrige por cambio de precio) |

### Parametros

| Parametro | Tipo | Default | Rango tipico | Descripcion |
|-----------|------|---------|--------------|-------------|
| `method` | str | "ratio" | - | Metodo de evaluacion |
| `atr_period` | int | 14 | 14 | Periodo del ATR (Wilder) |
| `ratio_threshold` | float | 0.7 | 0.70-0.95 | Umbral para ratio/ratio_normalized |
| `min_r_squared` | float | 0.5 | - | R^2 minimo para trend |

### Codigo

- **Archivo**: `vcp_detection/heuristic/atr_compression.py`
- **Funcion**: `verify_atr_compression(sequence, ohlc, method, ...)`
- **Funcion batch**: `verify_atr_compression_batch(sequences, ohlc, ...)`
- **Helper**: `compute_atr(ohlc, period)` -> `pd.Series` (RMA, reutilizado por Paso 2)
- **Input**: `DecreasingSequence` + `pd.DataFrame`
- **Output**: `ATRCompressionResult` con `passes: bool`

---

## Paso 5 -- Verificacion de Contraccion de Volumen

### Algoritmo

Para cada contraccion de la secuencia, calcula el volumen promedio en el rango `[high_date, low_date]`, y luego evalua si la serie de volumenes promedio es decreciente.

```
avg_vol_i = mean(volume[high_date_i : low_date_i])
```

### Metodos

| Metodo | Calculo | Criterio |
|--------|---------|----------|
| `"ratio"` | `vol_last / vol_first` | `<= ratio_threshold` (ej: 0.85) |
| `"per_contraction"` | Cada contraccion vs la anterior | `vol[i+1] <= vol[i] * (1 + tolerance)` |
| `"trend"` | Regresion lineal sobre volumenes promedio | Pendiente < 0 y R^2 >= min_r_squared |

### Parametros

| Parametro | Tipo | Default | Rango tipico | Descripcion |
|-----------|------|---------|--------------|-------------|
| `method` | str | "per_contraction" | - | Metodo de evaluacion |
| `volume_column` | str | "volume" | - | Columna de volumen (puede ser "transactions" para FX) |
| `tolerance` | float | 0.10 | - | Margen para per_contraction |
| `ratio_threshold` | float | 0.8 | 0.75-0.95 | Umbral para ratio |
| `min_r_squared` | float | 0.5 | - | R^2 minimo para trend |

### Codigo

- **Archivo**: `vcp_detection/heuristic/volume_contraction.py`
- **Funcion**: `verify_volume_contraction(sequence, ohlc, method, ...)`
- **Funcion batch**: `verify_volume_contraction_batch(sequences, ohlc, ...)`
- **Input**: `DecreasingSequence` + `pd.DataFrame`
- **Output**: `VolumeContractionResult` con `passes: bool`

---

## Paso 6 -- Pivote + Senal de Breakout

### Identificacion del pivote

El pivote se define a partir de la ultima contraccion de la secuencia:
- **Pivot price**: `last_contraction.high_swing.price` (nivel de resistencia)
- **Stop natural**: `last_contraction.low_swing.price` (si el precio cae debajo, el patron fallo)

### Condiciones de breakout

Ambas condiciones deben cumplirse:

1. **Precio**: `close_today > pivot_price`
2. **Volumen** (opcional, controlado por `require_volume_confirmation`):
   - `"ratio"`: `volume_today >= ratio_threshold * mean(volume[lookback_days])` (clasico Minervini: 1.5x media de 50 dias)
   - `"percentile"`: `volume_today >= percentil_P(volume[lookback_days])`

### Parametros

| Parametro | Tipo | Default | Rango tipico | Descripcion |
|-----------|------|---------|--------------|-------------|
| `volume_method` | str | "ratio" | - | Metodo de confirmacion de volumen |
| `volume_ratio_threshold` | float | 1.5 | 1.3-2.0 | Multiplo de volumen promedio |
| `volume_percentile` | int | 80 | - | Percentil para method="percentile" |
| `volume_lookback_days` | int | 50 | 50 | Baseline de ~10 semanas |
| `require_volume_confirmation` | bool | True | - | Si False, bypasea filtro de volumen |

### Pipeline completo (run_full_vcp_pipeline)

`run_full_vcp_pipeline()` orquesta los 6 pasos:

1. Detecta swings (una vez) y calcula contracciones (una vez).
2. Precomputa ATR (RMA) una vez para reutilizar.
3. Para cada fecha de evaluacion:
   - Paso 3: busca secuencia decreciente
   - Paso 4: verifica compresion de ATR
   - Paso 5: verifica contraccion de volumen (opcional)
   - Paso 6: evalua breakout
4. Opcionalmente deduplica senales del mismo patron (`deduplicate=True`).

Acepta `precomputed_swings`, `precomputed_contractions` y `precomputed_atr` para evitar recomputacion en optimizacion.

### Codigo

- **Archivo**: `vcp_detection/heuristic/pivot_breakout.py`
- **Funcion**: `detect_breakout_signal(sequence, atr_compression_result, ohlc, ...)`
- **Helper**: `identify_pivot(sequence)` -> `PivotInfo`
- **Orquestador**: `run_full_vcp_pipeline(ohlc, swing_detector, ...)`
- **Input**: `DecreasingSequence` + `ATRCompressionResult` + `pd.DataFrame`
- **Output**: `VCPSignal | None`

---

## Tabla de parametros tunables

### Parametros del pipeline de deteccion

| Parametro | Paso | Default | Rango Optuna | Tipo |
|-----------|------|---------|--------------|------|
| `atr_length` | 1 | 14 | 10-25 | int |
| `atr_mult` | 1 | 2.0 | 1.5-3.5 (step 0.25) | float |
| `min_contractions` | 3 | 2 | 2-3 | int |
| `max_contractions` | 3 | 6 | 5-7 | int |
| `lookback_bars` | 3 | 80 | 80-140 (step 10) | int |
| `tolerance` | 3 | 0.10 | 0.05-0.20 (step 0.025) | float |
| `max_depth_pct` | 3 | None | 0.25-0.45 | float |
| `max_depth_atr` | 3 | None | 3.0-7.0 (step 0.5) | float |
| `min_total_reduction` | 3 | None | 0.65-0.90 | float |
| `require_ascending_lows` | 3 | True | [True, False] | categorical |
| `ascending_lows_tolerance` | 3 | 0.0 | 0.0-0.05 (step 0.01) | float |
| `compression_threshold` | 4 | 0.7 | 0.70-0.95 | float |
| `vol_contraction_threshold` | 5 | 0.8 | 0.75-0.95 | float |
| `volume_ratio_threshold` | 6 | 1.5 | 1.3-2.0 | float |

### Parametros de riesgo/salida (optimizados)

| Parametro | Default | Rango Optuna | Tipo |
|-----------|---------|--------------|------|
| `trailing_stop_method` | "sma" | ["sma", "atr"] | categorical |
| `trailing_atr_period` | 14 | 10-21 | int |
| `trailing_atr_multiplier` | 3.0 | 1.5-4.0 (step 0.25) | float |
| `max_bars_without_progress` | None | [None, 15, 20, 30, 40] | categorical |
| `min_progress_r` | 0.5 | 0.25-1.0 (step 0.25) | float |

### Parametros de riesgo/salida (fijos)

| Parametro | Valor | Descripcion |
|-----------|-------|-------------|
| `max_stop_loss_pct` | 0.07 (stocks) / 0.02 (FX) | Stop loss maximo como % del precio |
| `breakeven_r_multiple` | 2.0 | Escalones de breakeven en multiplos de R |
| `trailing_sma_period` | 20 | Periodo de SMA para trailing stop SMA |
| `trailing_volume_factor` | 1.5 | Factor de volumen para senal de distribucion |

---

## Adaptaciones FX vs Stocks

El pipeline es el mismo para ambos mercados, pero los parametros difieren:

| Aspecto | Stocks | FX |
|---------|--------|-----|
| ATR mult | 1.5-3.5 | Valores mas bajos (menor volatilidad relativa) |
| Volume column | "volume" | "transactions" (no hay volumen real en FX spot) |
| Volume confirmation | Activada | Desactivada (`require_volume_confirmation=False`) |
| Volume contraction | Sobre "volume" | Sobre "transactions" o desactivada |
| max_stop_loss_pct | 0.07 (7%) | 0.02 (2%) — FX tiene menor rango de movimiento |
| Datos | Diarios | Diarios o horarios (1H) |
| Trend template | Se aplica como prefiltro | No se aplica (no aplica el concepto Stage 2 en FX) |
| Agrupacion | gap mode (30 dias) | gap o sequential |

### Configuracion tipica FX

```python
risk_params = {
    "max_stop_loss_pct": 0.02,       # 2% vs 7% en stocks
    "breakeven_r_multiple": 2.0,
    "trailing_sma_period": 20,
    "trailing_volume_factor": 1.5,
    "trailing_stop_method": "atr",    # ATR trailing mas comun en FX
    "trailing_atr_period": 14,
    "trailing_atr_multiplier": 3.0,
}

breakout_params = {
    "volume_method": "ratio",
    "volume_ratio_threshold": 1.5,
    "volume_lookback_days": 50,
    "require_volume_confirmation": False,  # sin volumen real en FX
}

volume_contraction_params = {
    "method": "ratio",
    "volume_column": "transactions",   # proxy de volumen en FX
    "ratio_threshold": 0.85,
}
```
