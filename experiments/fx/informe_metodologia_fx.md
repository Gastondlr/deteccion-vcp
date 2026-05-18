# Informe: Metodologia de Deteccion VCP para Monedas

## 1. Introduccion

El sistema detecta patrones VCP (Volatility Contraction Pattern) en pares de divisas
usando data diaria. El VCP, originado por Mark Minervini para acciones, identifica
consolidaciones donde la volatilidad y profundidad de las correcciones se contraen
progresivamente antes de un breakout alcista.

La adaptacion a FX requiere parametros mas ajustados porque las monedas tienen
movimientos porcentuales mucho menores que acciones (ATR tipico ~0.6% vs ~2.2%),
no tienen fases de crecimiento sostenido (Stage 2), y el volumen no es confiable.

El pipeline tiene 6 pasos secuenciales. Cada paso filtra: solo los patrones que
superan todos los filtros generan una senal de entrada.

---

## 2. Pipeline de Deteccion (6 pasos)

### Paso 1: Deteccion de Swings (ATR ZigZag)

**Que hace:** Identifica los maximos y minimos significativos del precio, filtrando
el ruido intradiario.

**Algoritmo:** Recorre las barras secuencialmente manteniendo una direccion (UP buscando
maximos, DOWN buscando minimos) y un extremo actual. Cuando el precio se revierte al
menos `atr_mult * ATR` desde el extremo actual, se confirma un swing point.

**Anti look-ahead:** Cada SwingPoint tiene dos fechas:
- `date`: la barra donde ocurrio el extremo
- `confirmed_at`: la barra donde se cruzo el umbral de reversion

El sistema usa `confirmed_at` para filtrar senales, garantizando que no se usa
informacion futura en el backtest.

**Parametros configurables:**

| Parametro | Que controla | Valor FX |
|-----------|-------------|----------|
| `atr_length` | Periodo del ATR (SMA del True Range) | 14 |
| `atr_mult` | Multiplicador del ATR para confirmar swing. Mayor = menos swings, solo reversiones grandes | **Variable en grilla: 0.75 a 2.5** |
| `use_close_only` | Si usa solo close o tambien high/low | False |

**Efecto de atr_mult:** Es el parametro mas critico. Con `atr_mult=0.75` EURUSD genera
567 swings; con `atr_mult=2.5` genera solo 125. Menos swings = menos contracciones =
patrones mas selectivos pero menos trades.

---

### Paso 2: Calculo de Contracciones

**Que hace:** Para cada par consecutivo de swings (HIGH, LOW), mide la caida como
una "contraccion" — la correccion desde un maximo local hasta el minimo siguiente.

**Metricas por contraccion:**
- `depth_pct = (high_price - low_price) / high_price` — profundidad porcentual
- `depth_atr = depth_abs / ATR(high_swing.date)` — profundidad normalizada por
  volatilidad. En FX esta metrica es mas util que depth_pct porque las contracciones
  son muy chicas en porcentaje.
- `duration_bars` — duracion en barras de trading

No tiene parametros configurables propios — depende de los swings del paso anterior.

---

### Paso 3: Secuencia Decreciente de Contracciones

**Que hace:** Busca secuencias donde cada contraccion sucesiva es progresivamente menor
que la anterior. Este es el nucleo del patron VCP: la volatilidad se comprime en cada
correccion porque la oferta se va agotando.

**Algoritmo:** Escanea hacia atras dentro de la ventana de lookback, probando desde
`max_contractions` hacia abajo hasta `min_contractions`. Para cada longitud, verifica
que los depths sean montonamente decrecientes (con tolerancia).

**Metodo de monotonia usado:** `tolerance` — permite que depth[i+1] <= depth[i] * (1 + tolerance).
Con tolerance=0.10, una contraccion de 5.0% acepta que la siguiente sea hasta 5.5%.
Esto acomoda el ruido real sin perder la tendencia decreciente.

**Parametros configurables:**

| Parametro | Que controla | Valor FX |
|-----------|-------------|----------|
| `min_contractions` | Minimo de contracciones en la secuencia | 2 |
| `max_contractions` | Maximo de contracciones a buscar | 6 |
| `lookback_bars` | Ventana de barras hacia atras para buscar | **Variable en grilla: 63, 84, 105, 126** |
| `tolerance` | Margen permitido en la monotonia decreciente | 0.10 (10%) |
| `max_depth_pct` | Profundidad maxima porcentual de cualquier contraccion | 0.50 (alto, para que no filtre en FX) |
| `max_depth_atr` | Profundidad maxima en ATRs de cualquier contraccion. **Este es el filtro que realmente importa en FX** | **Variable en grilla: 2 a 6** |
| `min_total_reduction` | Ratio minimo de reduccion total: depth_ultima / depth_primera. 0.60 = la ultima debe ser <= 60% de la primera | **Variable en grilla: 0.40 a 0.80** |
| `require_ascending_lows` | Exige que los minimos de cada contraccion sean progresivamente mas altos | True |
| `ascending_lows_tolerance` | Margen permitido en ascending lows | 0.03 (3%) |

**Por que `max_depth_pct` no importa en FX:** Las contracciones en monedas son tan
chicas en porcentaje (~1-3%) que el filtro porcentual nunca muerde. `max_depth_atr`
es el que realmente discrimina, usando la volatilidad como unidad de medida.

---

### Paso 4: Compresion de ATR

**Que hace:** Verifica que la volatilidad (medida por ATR) este comprimiendose entre
el inicio y el final de la secuencia. Un VCP genuino tiene tanto contracciones
decrecientes como volatilidad decreciente.

**Calculo:** `atr_ratio = ATR(fin_secuencia) / ATR(inicio_secuencia)`

Si el ratio es menor al threshold, la volatilidad se comprimo suficiente.

**Parametros (fijos, no se varian en grilla):**

| Parametro | Que controla | Valor FX |
|-----------|-------------|----------|
| `method` | Metodo de calculo | "ratio" |
| `atr_period` | Periodo del ATR | 14 |
| `ratio_threshold` | Umbral maximo del ratio ATR_fin/ATR_inicio | 0.85 |

---

### Paso 5: Breakout del Pivot

**Que hace:** Determina si el precio rompe por encima de la resistencia del patron
(el pivot), generando la senal de entrada.

**Pivot price:** Es el `high_swing.price` de la ultima contraccion de la secuencia —
el nivel de resistencia que los compradores deben superar.

**Condiciones de breakout:**
1. `close_hoy > pivot_price` — el precio supera la resistencia
2. Volume confirmation (desactivado para FX — el volumen en divisas no es confiable)
3. `max_entry_distance_pct`: si el precio ya avanzo mas de X% por encima del pivot,
   se rechaza la senal (entrada muy extendida, mal risk/reward)

**Parametros (fijos, no se varian en grilla):**

| Parametro | Que controla | Valor FX |
|-----------|-------------|----------|
| `require_volume_confirmation` | Si exige confirmacion por volumen | False |
| `max_entry_distance_pct` | Distancia maxima aceptable entry vs pivot | 0.03 (3%) |
| `volume_ratio_threshold` | Ratio de volumen requerido (no usado) | 1.5 |
| `volume_lookback_days` | Periodo de referencia de volumen (no usado) | 50 |

---

### Paso 6: Agrupacion de Senales y Simulacion de Trade

#### 6a. Agrupacion de senales en patrones

Las senales son por barra — un mismo patron puede emitir senales en dias consecutivos.
El sistema soporta dos modos de agrupacion:

**Modo "gap" (agrupacion por proximidad):**
`group_signals_into_patterns` agrupa senales separadas por menos de `max_gap_days` dias
en un unico patron. Para cada patron, se toma la primera senal como el punto de entrada.
Este modo puede generar trades superpuestos si dos patrones distantes estan activos al
mismo tiempo, lo cual hace que el CR no sea estrictamente compuesto.

**Modo "sequential" (un trade a la vez):**
Procesa las senales cronologicamente. Toma la primera senal, abre el trade, y ignora
todas las senales subsiguientes hasta que el trade cierre. Recien entonces toma la
siguiente senal disponible. Esto garantiza que nunca hay trades superpuestos y que el
CR compuesto es "honesto" — cada trade se financia con el capital resultante del anterior.

El modo sequential se implementa en `evaluate_signals_to_trades()` con `grouping="sequential"`.

**Entry price:** Close de la primera senal del patron.

**Stop loss:** El `low_swing.price` de la ultima contraccion de la secuencia (el piso
natural del patron). Si este stop implica una perdida mayor a `max_stop_loss_pct` (2%
para FX), se sube el stop para limitar la perdida al 2%.

**Initial risk:** `entry_price - stop_price` — la distancia en precio entre entrada y
stop. Es la unidad de medida "R" para todo el trade.

#### 6b. Simulacion del trade

Recorre las barras desde la entrada hacia adelante, evaluando condiciones de salida
en cada barra. Sale en la primera condicion que se cumpla:

| Mecanismo de salida | Condicion | Label |
|--------------------|-----------|-------|
| **Stop loss** | close <= stop (stop no se movio desde el inicial) | `stop_loss` |
| **Trailing stop ATR** | stop se recalcula cada barra como `max_close_historico - trailing_atr_mult * ATR`. Si close <= stop actualizado | `trailing_stop` |
| **Breakeven** | Cuando el trade alcanza N*R de ganancia, el stop sube a breakeven + fraccion. Se aplica por escalones via `breakeven_r_multiple` | (modifica el stop, no es salida en si) |
| **Target** | close >= entry + target_r_multiple * initial_risk | `target` |
| **Time exit** | Si el R-multiple no mejoro en `min_progress_r` durante `max_bars_without_progress` barras | `time_exit` |
| **Early exit** | close < entry dentro de los primeros `early_exit_days` dias | `early_exit` |

**Parametros de salida configurables:**

| Parametro | Que controla | Valor FX base |
|-----------|-------------|---------------|
| `max_stop_loss_pct` | Stop maximo como % del entry | 0.02 (2%) |
| `trailing_stop_method` | Metodo de trailing | "atr" |
| `trailing_atr_period` | Periodo ATR para trailing | 14 |
| `trailing_atr_multiplier` | Multiplicador ATR para trailing. Menor = stop mas apretado | **Variable en grilla: 1.0 a 3.0** |
| `breakeven_r_multiple` | Cada cuantos R se sube el stop | **Variable en grilla: 0.5 a 2.0** |
| `target_r_multiple` | Target de ganancia en R-multiples. None = sin target | **Variable en grilla: None, 2, 3, 5** |
| `early_exit_days` | Dias para salida rapida si cae debajo de entry. None = desactivado | **Variable en grilla: None, 3, 5** |
| `max_bars_without_progress` | Barras sin progreso antes de time exit | 15 |
| `min_progress_r` | Progreso minimo en R para evitar time exit | 0.5 |

---

## 3. Experimento de Estabilidad Temporal

### Objetivo

Encontrar los mejores parametros para cada moneda optimizando sobre los primeros
~5 anios de data (TRAIN: 2015-2019), y validar que funcionen en los siguientes
~6 anios (TEST: 2020-2026) que el optimizador nunca vio.

### Que parametros se varian

El experimento tiene dos fases de busqueda por grilla:

#### Por que optimizacion secuencial y no conjunta

La alternativa seria variar todos los parametros juntos (deteccion + salida) en una
sola grilla: 700 deteccion x 240 salida = **168,000 combinaciones**. Esto encontraria
el optimo global, pero tiene problemas serios para FX:

1. **Overfitting:** Con pocos trades por moneda en el periodo de entrenamiento (tipicamente
   3 a 15), probar 168K combinaciones casi garantiza encontrar una configuracion que
   funciona "por suerte" en TRAIN pero no generaliza a datos nuevos. Cuantas mas
   combinaciones se prueban relativo al numero de observaciones, mayor el riesgo de
   ajustarse al ruido.

2. **Costo computacional:** ~100x mas evaluaciones, sin garantia de que el resultado
   sea mejor out-of-sample.

3. **Interpretabilidad:** Con optimizacion conjunta es dificil separar si el resultado
   viene de detectar buenos patrones o de tener exits que se ajustaron al ruido.

El enfoque secuencial se basa en un supuesto razonable: **si un patron VCP es genuino,
deberia generar retorno positivo con cualquier gestion de salida razonable**. Si un
patron solo funciona con una combinacion de salida muy especifica, probablemente es
ruido y no un patron real del mercado. Por eso en la Fase 1 se usan exits fijos como
"juez neutral" — la unica variable es que patrones entran, y el CR mide si esos
patrones tenian valor predictivo.

#### Fase 1: Grilla de deteccion (en TRAIN)

Se varian los parametros que afectan QUE patrones se detectan:

| Parametro | Valores probados | N |
|-----------|-----------------|---|
| `atr_mult` (swing) | 0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 2.5 | 7 |
| `max_depth_atr` | 2, 3, 4, 5, 6 | 5 |
| `min_total_reduction` | 0.40, 0.50, 0.60, 0.70, 0.80 | 5 |
| `lookback_bars` | 63 (~3m), 84 (~4m), 105 (~5m), 126 (~6m) | 4 |

**Total: 7 x 5 x 5 x 4 = 700 combinaciones de deteccion**

Los demas parametros de deteccion se mantienen fijos en valores razonables
(tolerance=0.10, min_contractions=2, ascending_lows=True, etc.).

Para cada combinacion, se corre el pipeline completo sobre TRAIN y se simulan
trades con **parametros de salida fijos** que actuan como baseline neutral:

| Parametro de salida | Valor fijo |
|---------------------|------------|
| `trailing_atr_multiplier` | 1.5 |
| `target_r_multiple` | 3.0 (target a 3R) |
| `early_exit_days` | None (desactivado) |
| `breakeven_r_multiple` | 1.0 |

Es decir, no se evalua cuantos patrones detecto cada configuracion (cantidad), sino
**que tan buenos fueron esos patrones como trades**. Una configuracion que detecta 3
patrones excelentes le gana a una que detecta 20 mediocres.

Se selecciona la combinacion con mejor **cumulative return (CR)** en TRAIN.

#### Fase 2: Grilla de salida (en TRAIN)

Con la mejor deteccion de la Fase 1 fija, se varian los parametros que afectan
COMO se gestiona cada trade:

| Parametro | Valores probados | N |
|-----------|-----------------|---|
| `trailing_atr_multiplier` | 1.0, 1.5, 2.0, 2.5, 3.0 | 5 |
| `target_r_multiple` | None, 2.0, 3.0, 5.0 | 4 |
| `early_exit_days` | None, 3, 5 | 3 |
| `breakeven_r_multiple` | 0.5, 1.0, 1.5, 2.0 | 4 |

**Total: 5 x 4 x 3 x 4 = 240 combinaciones de salida**

Se selecciona la combinacion con mejor **cumulative return (CR)** en TRAIN.

#### Total de evaluaciones por moneda

700 (deteccion) + 240 (salida) = **940 configuraciones evaluadas por moneda**.

Con 5 monedas: **4,700 evaluaciones totales**.

Comparado con las 168,000 combinaciones de optimizacion conjunta (840,000 con 5 monedas),
el enfoque secuencial reduce el espacio de busqueda ~180x, lo cual es critico para
evitar overfitting con datasets tan chicos como los de FX.

### Criterio de seleccion

El criterio es **cumulative return (CR)** — el retorno acumulado compuesto de todos
los trades en el periodo.

`CR = prod(1 + pnl_pct_i) - 1` para todos los trades i.

Se elige la configuracion con el CR mas alto. Esto premia tanto el win rate como
la magnitud de las ganancias vs perdidas.

### Que se hace con la mejor configuracion

Una vez encontrada la mejor config en TRAIN, se evalua en tres periodos:
- **TRAIN (2015-2019):** donde se optimizo (in-sample)
- **TEST (2020-2026):** datos que el optimizador nunca vio (out-of-sample)
- **FULL (2015-2026):** periodo completo

Si la configuracion funciona bien en TEST, hay evidencia de que los parametros
capturan algo real del mercado y no estan sobreajustados a la historia particular
del periodo de entrenamiento.

### Metricas logueadas

Para cada moneda y split, se registran en MLflow:
- Senales, trades, wins, losses, win rate
- Cumulative return (estrategia vs buy & hold)
- Sharpe ratio (estrategia vs buy & hold)
- Max drawdown (estrategia vs buy & hold)
- Plots combinados de cada trade (patron + simulacion con evolucion del stop)
- CSVs con detalle de trades

---

## 4. Parametros Fijos vs Variables — Resumen

### Fijos (no se optimizan)

| Parametro | Valor | Razon |
|-----------|-------|-------|
| `atr_length` | 14 | Estandar industria |
| `tolerance` | 0.10 | Valor razonable para ruido |
| `min_contractions` | 2 | Minimo para ser VCP |
| `max_contractions` | 6 | Maximo razonable |
| `max_depth_pct` | 0.50 | Alto para que no filtre (depth_atr manda en FX) |
| `ascending_lows_tolerance` | 0.03 | 3%, ajustado para FX |
| `atr_compression_threshold` | 0.85 | Moderado |
| `require_volume_confirmation` | False | Volumen FX no confiable |
| `max_entry_distance_pct` | 0.03 | 3% maximo |
| `max_stop_loss_pct` | 0.02 | 2%, ajustado para FX |
| `max_bars_without_progress` | 15 | ~3 semanas |

### Variables (se optimizan en grilla)

| Parametro | Grilla | Afecta |
|-----------|--------|--------|
| `atr_mult` | 7 valores (0.75 a 2.5) | Deteccion de swings |
| `max_depth_atr` | 5 valores (2 a 6) | Filtro de profundidad |
| `min_total_reduction` | 5 valores (0.40 a 0.80) | Exigencia de compresion |
| `lookback_bars` | 4 valores (63, 84, 105, 126) | Ventana de busqueda de patrones |
| `trailing_atr_multiplier` | 5 valores (1.0 a 3.0) | Gestion del trailing stop |
| `target_r_multiple` | 4 valores (None, 2, 3, 5) | Objetivo de ganancia |
| `early_exit_days` | 3 valores (None, 3, 5) | Salida rapida por debilidad |
| `breakeven_r_multiple` | 4 valores (0.5 a 2.0) | Velocidad de subida del stop |

---

## 5. Resultados del Experimento Sequential

### Modo de agrupacion

Se utiliza el modo **sequential**: un trade a la vez, sin superposicion. El CR
compuesto es estrictamente secuencial — cada trade se financia con el resultado
del anterior.

### Parametros optimos por moneda

| Moneda | atr_mult | depth_atr | reduction | lookback | trail | target | early | be_R |
|--------|:--------:|:---------:|:---------:|:--------:|:-----:|:------:|:-----:|:----:|
| EURUSD | 2.50 | 5 | 0.60 | 63 | 1.5 | 5.0 | None | 2.0 |
| GBPUSD | 1.50 | 3 | 0.80 | 63 | 1.5 | 2.0 | None | 0.5 |
| USDJPY | 2.50 | 6 | 0.50 | 105 | 1.5 | 5.0 | 3 | 1.5 |
| USDCNH | 2.50 | 4 | 0.60 | 105 | 3.0 | 3.0 | None | 2.0 |
| USDCNY | 2.50 | 5 | 0.80 | 105 | 2.5 | 3.0 | None | 0.5 |

**Observaciones sobre parametros:**
- `atr_mult=2.5` domina en 4 de 5 monedas. Solo GBPUSD prefiere 1.50 (swings mas sensibles).
- `lookback_bars`: EURUSD y GBPUSD prefieren 63 (~3 meses), las demas 105 (~5 meses).
- `early_exit_days=None` en 4 de 5 monedas. Solo USDJPY usa early exit de 3 dias.
- `target_r_multiple` varia: 5.0R para EURUSD/USDJPY (deja correr), 2.0-3.0R para el resto.

### Performance por periodo

| Moneda | Train T | Train WR | Train CR | Test T | Test WR | Test CR | Full CR |
|--------|:-------:|:--------:|:--------:|:------:|:-------:|:-------:|:-------:|
| EURUSD | 3 | 100% | +2.38% | 5 | 80% | +7.93% | +10.50% |
| GBPUSD | 8 | 62% | +9.89% | 15 | 53% | +5.80% | +14.05% |
| USDJPY | 10 | 30% | +15.33% | 13 | 8% | -2.96% | +7.12% |
| USDCNH | 9 | 100% | +14.57% | 3 | 33% | +1.62% | +16.42% |
| USDCNY | 11 | 91% | +22.16% | 2 | 50% | +1.52% | +24.01% |

### Estrategia vs Buy & Hold en TEST (2020-2026)

| Moneda | Strat CR | B&H CR | Strat DD | B&H DD | Strat Sharpe | B&H Sharpe |
|--------|:--------:|:------:|:--------:|:------:|:------------:|:----------:|
| EURUSD | +7.93% | +4.91% | -0.74% | -22.23% | - | 0.12 |
| GBPUSD | +5.80% | +3.24% | -1.82% | -24.61% | 1.27 | 0.09 |
| USDJPY | -2.96% | +44.70% | -1.74% | -14.84% | -1.84 | 0.59 |
| USDCNH | +1.62% | -1.84% | -1.63% | -12.21% | 1.09 | 0.01 |
| USDCNY | +1.52% | -1.93% | -2.01% | -12.35% | 1.48 | -0.01 |

### Interpretacion

**Resultados positivos (4 de 5 monedas con CR > 0 en TEST):**
- **EURUSD:** Mejor caso. +7.93% en TEST vs +4.91% B&H. Solo 5 trades, 80% WR.
  Drawdown minimo (-0.74%). El lookback corto (63 bars) fue clave: genera menos
  senales pero de mayor calidad.
- **GBPUSD:** +5.80% vs +3.24% B&H. 15 trades, 53% WR. Drawdown de -1.82% vs
  -24.61% del B&H — la estrategia reduce el riesgo significativamente.
- **USDCNH/USDCNY:** CR positivo y superan al B&H (que fue negativo), pero con
  muy pocos trades (2-3) para ser estadisticamente concluyente.

**Resultado negativo:**
- **USDJPY:** El peor caso. Solo 8% WR en TEST, pierde -2.96% mientras B&H sube
  +44.70%. El yen tuvo una depreciacion fuerte y sostenida (2020-2024) que beneficia
  al B&H en USDJPY. El VCP no esta disenado para captar tendencias largas sin
  contracciones intermedias.

**Conclusion general:** La estrategia funciona mejor en pares que oscilan en rango
(EURUSD, GBPUSD, USDCNH, USDCNY) donde las contracciones de volatilidad preceden
movimientos significativos. No funciona en tendencias unidireccionales fuertes (USDJPY
2020-2024). El drawdown de la estrategia es consistentemente mucho menor que el del
B&H en todos los pares.

### Tracking

Todos los resultados estan logueados en MLflow bajo el experimento `VCP_FX_TemporalStability`:
- `EURUSD_sequential_experiment` — run con 3 child runs (TRAIN/TEST/FULL)
- `sequential_multicurrency` — run con 12 child runs (3 por moneda x 4 monedas)

Cada run contiene:
- Parametros completos de deteccion y salida
- Metricas (CR, WR, Sharpe, drawdown, etc.)
- Graficos combinados patron+trade para cada trade (carpeta `plots/`)
- CSV con detalle de trades (carpeta `tables/`)
