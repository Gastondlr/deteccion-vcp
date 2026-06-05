# Parametros del algoritmo de deteccion VCP

Descripcion detallada de cada parametro del pipeline, que controla, como se varia
y por que. Organizado por paso del pipeline.

El pipeline evalua cada fecha del historico y determina si existe un patron VCP
valido. Los 6 pasos se ejecutan secuencialmente: si cualquier paso falla, se
retorna `None` para esa fecha y se pasa a la siguiente.

```
OHLCV → [1] Swings → [2] Contracciones → [3] Secuencia decreciente
     → [4] Compresion ATR → [5] Contraccion volumen → [6] Breakout → VCPSignal
```

---

## Paso 1 — Swing Detection (ATR ZigZag)

**Que hace:** Identifica los extremos de precio significativos (swing highs y
swing lows) en la serie temporal. Un swing es un punto donde el precio cambia
de direccion de manera significativa. El detector usa ATR (Average True Range)
como unidad de medida de volatilidad: solo registra un cambio de direccion si
el precio se movio al menos `atr_mult` veces el ATR desde el ultimo swing.

**Algoritmo:**
1. Calcular ATR sobre `atr_length` barras
2. Iniciar con direction=UP, rastrear el extremo actual
3. Si direction=UP y `low[i]` cae >= `atr_mult × ATR` desde el extremo → confirmar
   swing HIGH, cambiar a DOWN
4. Si direction=DOWN y `high[i]` sube >= `atr_mult × ATR` desde el extremo →
   confirmar swing LOW, cambiar a UP
5. Cada swing registra la fecha del extremo real y la fecha de confirmacion
   (para evitar look-ahead bias)

**Importante:** El ATR aqui se calcula con SMA (media simple), no con el metodo
de Wilder. Esto es diferente al ATR del paso 4 (que usa Wilder/RMA).

### Parametros

#### `atr_length` (default: 14)

**Que es:** Periodo en barras para calcular el ATR. 14 dias es el estandar de la
industria (aproximadamente 3 semanas de trading).

**Efecto:** Determina la "memoria" de volatilidad del detector.
- Valores mas bajos (10): ATR reacciona mas rapido a cambios de volatilidad.
  En periodos de volatilidad alta transitoria, el umbral de swing sube rapido y
  el detector se vuelve menos sensible temporalmente.
- Valores mas altos (20-25): ATR es mas estable. El detector mantiene sensibilidad
  mas constante independientemente de spikes de volatilidad recientes.

**Rango explorado:** [10, 25]

**Hallazgo experimental:** Importancia muy baja. El detector es robusto al
periodo de ATR. Se mantiene fijo en 14 en la mayoria de los experimentos.

---

#### `atr_mult` (default: 2.0)

**Que es:** Multiplicador del ATR para considerar un movimiento como significativo.
El precio debe moverse al menos `atr_mult × ATR` desde el ultimo swing para que
se registre un nuevo swing en la direccion opuesta.

**Efecto:** Controla la sensibilidad del detector.
- Valores bajos (0.75-1.5): Detecta mas swings, incluyendo movimientos menores.
  Produce mas contracciones pero tambien mas ruido. Util en FX donde los
  movimientos son proporcionalmente menores.
- Valores medios (1.5-2.5): Balance entre sensibilidad y ruido. Rango optimo
  encontrado experimentalmente para la mayoria de activos.
- Valores altos (3.0-5.0): Solo detecta movimientos muy grandes. Produce pocas
  contracciones. En stocks, atr_mult >= 3.0 combinado con max_depth_atr numerico
  produce 0 senales (bloqueo). Solo funciona con max_depth_atr=None, pero las
  senales adicionales resultaron ser ruido.

**Rango explorado:** [0.75, 5.0]

**Hallazgos experimentales:**
- Stocks: atr_mult=2.0 domina (+10.15% avg CR vs +1.40% a 4.0 en AAPL)
- FX daily: atr_mult=1.5 es optimo (mejor CR y WR en ambos splits)
- FX hourly: ningún valor funciona (probados 1.0 a 7.0)
- Importancia moderada, pero critico para FX vs stocks

---

#### `use_close_only` (default: False)

**Que es:** Determina que precios se usan para detectar swings.
- `False` (High/Low): Usa precios high para swing highs y low para swing lows.
  Captura los extremos intradiarios reales.
- `True` (Close only): Usa solo precios de cierre para ambos tipos de swing.
  Mas conservador, ignora mechas (wicks). Puede ser mejor en activos con mechas
  largas que no representan niveles significativos.

**Hallazgos experimentales:**
- En general, False (HL) es superior: +7.77% vs +2.31% avg CR en AAPL
- Excepcion notable: GOOGL requiere `use_close_only=True` — con HL da CR negativo.
  Es el unico ticker donde esta particularidad es critica.

---

## Paso 2 — Contraction Computation

**Que hace:** Toma los swings del paso 1 y calcula la profundidad de cada
contraccion. Una contraccion es un par (swing HIGH → swing LOW) consecutivo.
Calcula tres medidas de profundidad:
- `depth_pct`: caida porcentual = (high - low) / high
- `depth_abs`: caida absoluta en precio
- `depth_atr`: caida relativa al ATR = depth_abs / ATR en la fecha del high

**Algoritmo:**
1. Iterar los swings en orden cronologico
2. Solo procesar pares donde swings[i].type == HIGH y swings[i+1].type == LOW
3. Saltar swings no confirmados
4. Calcular profundidad en las 3 metricas
5. Filtrar por `min_depth_pct` si se especifica

**Nota:** El ATR aqui se calcula con Wilder's Smoothing (RMA), que es diferente
al SMA del paso 1. La formula recursiva es:
`ATR[t] = ATR[t-1] × (1 - 1/period) + TR[t] × (1/period)`

### Parametros

#### `min_depth_pct` (default: 0.0)

**Que es:** Profundidad minima como fraccion del precio para considerar una
contraccion valida. Con 0.0, toda contraccion (por minima que sea) se incluye.

**Efecto:** Filtra micro-contracciones que son ruido. Util en activos muy liquidos
con contracciones de 0.1-0.5% que no representan VCPs reales.

**Rango explorado:** Nunca variado sistematicamente. Candidato para exploracion
futura (documentado en `mejoras_pendientes.md`).

---

## Paso 3 — Decreasing Sequence Detection

**Que hace:** Busca secuencias de contracciones donde cada contraccion sucesiva
es de menor profundidad que la anterior. Esta es la firma central del VCP: la
volatilidad se contrae progresivamente porque los tenedores debiles van saliendo
en cada correccion mientras las instituciones absorben la oferta.

**Algoritmo:**
1. Filtrar contracciones con `confirmed_at <= evaluation_date`
2. Aplicar ventana temporal: solo contracciones con `low_swing.date >= (evaluation_date - lookback_bars)`
3. Probar longitudes desde `max_contractions` hacia abajo hasta `min_contractions`
4. Para cada longitud, tomar las ultimas N contracciones y verificar monotonia
5. Aplicar filtros de calidad (profundidad, gaps, ascending lows)
6. Retornar la primera (mas larga) secuencia valida encontrada

### Parametros

#### `method` (default: "tolerance")

**Que es:** Metodo para determinar si la secuencia es monotonamente decreciente.

- `"strict"`: Cada depth[i+1] debe ser estrictamente menor que depth[i]. Muy
  restrictivo, rechaza secuencias donde dos contracciones tienen profundidad
  similar.
- `"tolerance"`: depth[i+1] puede ser hasta un (1 + tolerance) × depth[i]. Permite
  secuencias "casi decrecientes" donde una contraccion es marginalmente mayor que
  la anterior. Es el metodo usado en todos los experimentos.
- `"robust_trend"`: Regresion lineal sobre las profundidades. Requiere pendiente
  negativa y R² >= min_r_squared. Mas robusto ante outliers individuales pero
  menos interpretable.

**Hallazgo:** Solo se uso "tolerance" en todos los experimentos. "strict" es
demasiado restrictivo y "robust_trend" fue propuesto pero nunca testeado
sistematicamente.

---

#### `min_contractions` (default: 2)

**Que es:** Minimo de contracciones para considerar un patron VCP valido.
Minervini define 2-6 contracciones.

**Efecto:**
- min=2: Acepta patrones simples con solo 2 correcciones. Mas senales, pero
  patrones menos desarrollados.
- min=3: Exige patrones mas maduros con al menos 3 correcciones decrecientes.
  Menos senales, pero mayor calidad por patron.

**Rango explorado:** [2, 3]

**Hallazgo:** min_contractions=3 fue optimo en la optimizacion automatica. Pero
la diferencia no es dramatica — la mayoria de los experimentos mantiene min=2.

---

#### `max_contractions` (default: 6)

**Que es:** Maximo de contracciones a considerar. El algoritmo prueba desde
max_contractions hacia abajo y retorna la secuencia mas larga que sea valida.

**Efecto:** Tope de complejidad del patron. Mas de 6 contracciones generalmente
indica que la accion no logra resolver la consolidacion — esta "atascada" en
lugar de comprimir volatilidad progresivamente.

**Rango explorado:** [5, 7]. No tiene impacto significativo.

---

#### `lookback_bars` (default: 80)

**Que es:** Ventana temporal en barras (dias de trading) hacia atras desde la
fecha de evaluacion. Solo se consideran contracciones cuyo `low_swing.date` cae
dentro de esta ventana.

**Efecto:**
- Valores bajos (63 ≈ 3 meses): Solo detecta patrones recientes. Filtra
  patrones viejos que ya perdieron relevancia. Mejor para activos con ciclos
  cortos (NVDA: lookback=63 es optimo).
- Valores altos (126 ≈ 6 meses): Permite detectar patrones de larga formacion.
  Mejor para activos con consolidaciones largas (AAPL, MSFT, GOOGL: lookback=126
  es optimo).

**Rango explorado:** [63, 84, 105, 126]

**Hallazgo:** lookback=126 generalmente superior en stocks (+8.07% vs +2.01%
en AAPL). En FX hourly, lookback_bars es completamente inerte (72, 120, 240,
480 producen resultados identicos — los patrones ya estan dentro de 72 barras).

---

#### `tolerance` (default: 0.10)

**Que es:** Margen de tolerancia para el metodo "tolerance". Con 0.10, una
contraccion puede ser hasta 10% mas profunda que la anterior sin romper la
secuencia.

**Ejemplo:** Si la primera contraccion tiene depth_pct=0.20 (20%), la segunda
puede ser hasta 0.20 × 1.10 = 0.22 (22%) y aun considerarse decreciente.

**Efecto:**
- Valores bajos (0.05): Exige secuencias casi estrictamente decrecientes.
  Mas selectivo, menos senales.
- Valores altos (0.15-0.20): Permite desviaciones mayores. Mas senales pero
  patrones menos "limpios".

**Rango explorado:** [0.05, 0.20]

**Hallazgo:** Parametro inerte en AAPL (0.10, 0.15, 0.20 producen resultados
identicos). En FX, tolerance=0.15 es optimo.

---

#### `max_depth_pct` (default: None → 0.35 en stocks)

**Que es:** Profundidad maxima permitida para cualquier contraccion individual,
como fraccion del precio. Si alguna contraccion de la secuencia excede este
valor, la secuencia se rechaza.

**Efecto:** Filtro de Minervini — 35% es el limite superior. Correcciones mas
profundas indican debilidad estructural (la accion puede estar en Etapa 3 o 4,
no en Etapa 2).

**Rango explorado:** [0.25, 0.35] en stocks, 0.50 en FX

**Hallazgo:** Parametro inerte en AAPL (0.25, 0.30, 0.35 producen resultados
casi identicos — las contracciones de AAPL rara vez exceden 25%). Importancia
Puede tener impacto en tickers con contracciones mas profundas.

---

#### `max_depth_atr` (default: None → tipicamente 5-8)

**Que es:** Profundidad maxima permitida para una contraccion, medida en
multiplos de ATR. Alternativa a max_depth_pct que se adapta automaticamente
a la volatilidad del activo.

**Efecto:**
- Valores numericos (4, 6, 8): Filtran contracciones "demasiado profundas"
  relativo a la volatilidad normal del activo.
- None (deshabilitado): No filtra por profundidad ATR. Permite contracciones
  de cualquier profundidad relativa.

**Interaccion critica con atr_mult:** Cuando atr_mult >= 3.0 y max_depth_atr
tiene valor numerico, se produce un bloqueo: los swings ya requieren >= 3×ATR
de movimiento, asi que las contracciones siempre tienen depth_atr >= 3.0, y un
filtro de max_depth_atr=4 rechaza casi todas. Esto fue descubierto en el
experimento hourly y confirmado en daily.

**Rango explorado:** [None, 4, 6, 8]

**Hallazgo:** max_depth_atr=6 es optimo en AAPL. max_depth_atr=None agrega ruido
en daily (las senales extra son patrones no-VCP con contracciones profundas).

---

#### `min_total_reduction` (default: None → tipicamente 0.60-0.80)

**Que es:** Reduccion total minima exigida entre la primera y la ultima
contraccion. Se calcula como `depths[-1] / depths[0]`.

**Efecto:** Con 0.80, la ultima contraccion debe ser al menos 80% menor que la
primera. Ejemplo: si la primera contraccion fue del 20%, la ultima debe ser
<= 4%.

**Ejemplo numerico:**
- depths = [0.20, 0.12, 0.04] → reduction = 0.04/0.20 = 0.20 → pasa con 0.80
  (0.20 <= 0.80)
- depths = [0.20, 0.18, 0.16] → reduction = 0.16/0.20 = 0.80 → borderline

**Rango explorado:** [0.40, 0.60, 0.80]

**Hallazgo:** Parametro importante. reduction=0.60-0.80 es el rango optimo.
Valores muy bajos (0.40) permiten secuencias donde la contraccion apenas se
reduce, lo que no es un VCP genuino.

---

#### `max_gap_between_contractions_days` (default: None)

**Que es:** Maximo de dias calendario permitido entre contracciones consecutivas.
Se mide desde el low de una contraccion hasta el high de la siguiente (el
periodo de recuperacion).

**Efecto:** Filtra patrones "estirados" donde las contracciones estan separadas
por meses. Un VCP genuino tiene contracciones que se suceden sin largos periodos
de inactividad.

**Rango explorado:** [20, 40]

**Hallazgo:** Activar este filtro con valores de 30-40 dias mejora calidad
significativamente. None (sin limite) permite patrones fragmentados que no
son VCPs reales.

---

#### `require_ascending_lows` (default: True)

**Que es:** Exige que los lows de las contracciones sucesivas sean ascendentes.
En un VCP sano, cada correccion hace un minimo mas alto que la anterior —
indicando que los compradores entran a niveles cada vez mas altos.

**Efecto:** Filtro de calidad estructural.
- True: Cada low[i+1] >= low[i] × (1 - ascending_lows_tolerance)
- False: No verifica la relacion entre lows

**Hallazgo:** Completamente inerte en EURUSD (0 efecto — las contracciones FX
son tan chicas que los lows siempre son ascendentes). En stocks, su efecto
depende del ticker.

---

#### `ascending_lows_tolerance` (default: 0.0)

**Que es:** Margen de tolerancia para ascending lows. Con 0.01, un low puede
ser hasta 1% menor que el anterior sin romper la condicion.

**Rango explorado:** [0.01, 0.03, 0.08]

**Hallazgo:** Parametro inerte en AAPL (los 3 valores producen resultados
identicos). En FX se usa 0.03 por la menor magnitud de los movimientos.

---

## Paso 4 — ATR Compression Verification

**Que hace:** Verifica que la volatilidad medida por ATR disminuyo durante la
formacion del patron. El VCP genuino requiere que no solo las contracciones de
precio sean decrecientes, sino que la volatilidad del activo se haya "calmado"
genuinamente durante la consolidacion.

**Algoritmo:**
1. Extraer fecha inicio (primer high de la secuencia) y fecha fin (ultimo low)
2. Calcular ATR (Wilder's smoothing) en ambas fechas
3. Comparar ATR_fin vs ATR_inicio segun el metodo elegido

### Parametros

#### `method` (default: "ratio")

**Que es:** Metodo de verificacion de compresion.

- `"ratio"`: `atr_end / atr_start <= ratio_threshold`. Simple y directo. Es el
  metodo usado en todos los experimentos.
- `"trend"`: Regresion lineal sobre la serie de ATR entre start y end. Requiere
  pendiente negativa y R² >= min_r_squared.
- `"ratio_normalized"`: Normaliza por precio antes de comparar:
  `(atr_end/price_end) / (atr_start/price_start) <= ratio_threshold`. Util si
  el precio cambio mucho durante el patron.

---

#### `atr_period` (default: 14)

**Que es:** Periodo del ATR para la verificacion. Mismo significado que en el
paso 1, pero este usa Wilder's smoothing (RMA) en vez de SMA.

---

#### `ratio_threshold` (default: 0.85 en experimentos, 0.70 en codigo)

**Que es:** Ratio maximo ATR_fin/ATR_inicio para pasar la verificacion.

**Efecto:**
- Valores bajos (0.70): Exige una reduccion de volatilidad de al menos 30%.
  Muy estricto, rechaza muchos patrones.
- Valores medios (0.85): Exige 15% de reduccion. Balance entre selectividad y
  cobertura. Valor usado en la mayoria de los experimentos.
- Valores altos (0.95-1.0): Acepta patrones con volatilidad casi constante.
  Demasiado permisivo — con 1.0 el filtro se deshabilita efectivamente.

**Rango explorado:** [0.85, 0.90, 0.95, 1.0]

**Hallazgo:** compression_threshold=0.90 es optimo en EURUSD (+47% mas senales
que 0.85, misma calidad). En AAPL, 0.95 es ligeramente mejor (las contracciones
de AAPL son limpias y la compresion siempre pasa).

---

## Paso 5 — Volume Contraction Verification (opcional)

**Que hace:** Verifica que el volumen promedio disminuyo durante la formacion
del patron. Volumen decreciente en las correcciones confirma que las instituciones
no estan vendiendo — solo los tenedores debiles estan saliendo. Este paso es
opcional y se activa pasando `volume_contraction_params` al pipeline.

**Algoritmo:**
1. Para cada contraccion de la secuencia, calcular volumen promedio (mean del
   volumen diario entre el high y el low)
2. Verificar que los volumenes promedio son decrecientes segun el metodo

### Parametros

#### `method` (default: "per_contraction")

- `"per_contraction"`: Cada vol[i+1] <= vol[i] × (1 + tolerance)
- `"ratio"`: vol_ultimo / vol_primero <= ratio_threshold
- `"trend"`: Regresion lineal con pendiente negativa y R² >= min_r_squared

---

#### `ratio_threshold` (default: 0.85 en experimentos)

**Que es:** Ratio maximo volumen_fin/volumen_inicio.

**Hallazgo:** Parametro de alto impacto — el mas influyente en la calidad
de los patrones detectados.

---

## Paso 6 — Pivot Identification y Breakout Signal

**Que hace:** Define el punto de breakout y verifica si el precio lo supero con
confirmacion de volumen.

**Pivot:** El precio high del ultimo swing HIGH de la secuencia. Representa el
nivel de resistencia que el precio debe superar para confirmar el breakout.

**Stop sugerido:** El precio low del ultimo swing LOW de la secuencia. Es el
nivel natural de stop-loss tecnico.

**Senal de compra:** Se activa cuando:
1. `close[hoy] > pivot_price` (el precio supero la resistencia)
2. El volumen confirma la ruptura (si `require_volume_confirmation=True`)

### Parametros

#### `volume_ratio_threshold` (default: 1.5)

**Que es:** Ratio minimo de volumen en el dia de breakout vs el promedio
reciente. Con 1.5, el volumen debe ser al menos 50% superior al promedio.

**Efecto:**
- 1.0 (sin filtro): Cualquier volumen es aceptable. Mas senales.
- 1.5 (Minervini clasico): Exige confirmacion institucional moderada.
- 2.0 (estricto): El volumen debe duplicar el promedio. Muy selectivo.

**Rango explorado:** [1.0, 1.5, 2.0]

**Hallazgo:** Este fue el parametro del primer experimento. threshold=1.0 (sin
filtro) domina consistentemente. El filtro de volumen en breakout descarta mas
senales buenas que malas. Confirmado en 8/8 stocks.

Parametro de alto impacto.

---

#### `volume_lookback_days` (default: 50)

**Que es:** Periodo en dias para calcular el volumen promedio de referencia.
50 dias ≈ 10 semanas de trading.

---

#### `require_volume_confirmation` (default: True)

**Que es:** Si False, el breakout se confirma solo por precio (close > pivot),
sin verificar volumen. Util en mercados donde el volumen no es confiable
(FX, donde se usa False).

---

#### `volume_confirmation_window` (default: 1)

**Que es:** Numero de dias hacia atras (incluyendo el dia del breakout) donde
buscar el spike de volumen.

- 1: Solo el dia exacto del breakout debe tener volumen alto.
- 3: Cualquiera de los ultimos 3 dias (hoy y los 2 anteriores) puede tener el
  spike. Mas permisivo — captura breakouts donde el volumen institucional llego
  uno o dos dias antes de la ruptura de precio.

Solo mira hacia atras. No mira dias futuros (ver `volume_confirmation_forward`
para eso).

**Hallazgo (v2):** `w3_t1.2` (ventana=3 dias, threshold=1.2x) es el mejor
balance. Mejora WR sin sobrerestringir. Es la config recomendada para AAPL.

---

#### `volume_confirmation_forward` (default: 0)

**Que es:** Numero de dias hacia adelante donde buscar confirmacion de volumen
despues del breakout de precio. Complementa a `volume_confirmation_window` que
solo mira hacia atras.

**Logica:**
1. Dia T: close > pivot (breakout de precio). Se busca volumen en la ventana
   backward [T-window, T].
2. Si el volumen no se confirma en la ventana backward y
   `volume_confirmation_forward > 0`, se inicia una busqueda forward.
3. Para cada dia T+1, T+2, ..., T+N:
   - Si close <= pivot → se cancela (el breakout fallo, el precio volvio debajo
     de la resistencia).
   - Si close > pivot Y volumen alto → senal confirmada. La entrada se registra
     en ese dia (no en el dia del breakout de precio original).
4. Si ningun dia forward confirma → no hay senal.

**Efecto:**
- 0 (default): Solo busca volumen hacia atras. Comportamiento original.
- 3: Despues de un breakout de precio sin volumen, espera hasta 3 dias a que
  aparezca el volumen, siempre que el precio se mantenga arriba del pivot.
- 5: Idem con 5 dias de gracia.

**Motivacion:** En la practica, el volumen institucional no siempre coincide con
el dia exacto del breakout de precio. A veces las instituciones empiezan a
comprar uno o dos dias despues de que el precio supera la resistencia, una vez
que confirman que el breakout se sostiene. Este parametro modela esa realidad
sin introducir look-ahead bias: la entrada se registra en el dia donde se ve
el volumen, no antes.

**Metadata adicional cuando confirma forward:** La senal incluye
`forward_confirmed=True`, `breakout_date` (fecha original del cruce de precio),
y `confirmation_delay_days` (dias entre breakout y confirmacion).

**Rango sugerido para explorar:** [0, 1, 2, 3, 5]

---

## Simulacion de trades — Risk Management

Una vez que se detecta una senal de breakout, se simula la operacion completa.
La simulacion avanza barra por barra desde la entrada y aplica las reglas de
salida en orden de prioridad.

### Agrupacion de senales

#### `grouping` (default: "gap")

**Que es:** Como se agrupan las senales en trades.

- `"gap"`: Senales dentro de `max_gap_days` dias se agrupan en un unico trade
  multi-leg. El trade se inicia con la primera senal y se mantiene mientras
  sigan llegando senales cercanas. Sobreestima el numero de trades porque no
  modela el capital comprometido.
- `"sequential"`: Un trade a la vez, sin overlap. La segunda senal se ignora
  hasta que el primer trade cierra. Refleja trading real con capital limitado
  y filtra severamente (57 senales → 5 trades en EURUSD).

**Hallazgo:** Sequential mode produce resultados mucho mas honestos y es el
estandar desde el 18 de mayo de 2026.

---

### Parametros de salida

#### `max_stop_loss_pct` (default: 0.07)

**Que es:** Stop-loss maximo como porcentaje del precio de entrada.

**Efecto:** Si el precio cae este porcentaje desde la entrada, se cierra la
posicion. Es el limite de riesgo absoluto por trade.

- Stocks: 7% (rango de Minervini 5-8%)
- FX: 2% (los movimientos son 3-4x menores)

**Rango explorado:** [0.03, 0.05, 0.07]

**Hallazgo:** 5% es optimo en AAPL v2 (COMP#1). 3% funciona bien con
vol_filter (COMP#2). En FX, 2% es necesario por la menor amplitud de
movimientos.

---

#### `breakeven_r_multiple` (default: 2.0)

**Que es:** Cuando la ganancia no realizada alcanza este multiplo del riesgo
inicial (R), el stop se mueve al precio de entrada (breakeven). A partir de
ahi, la operacion es "gratis" — en el peor caso se sale sin ganar ni perder.

**Ejemplo:** Entrada a $50, stop en $46 (riesgo=$4, 1R=$4). Con be_R=2.0,
cuando el precio llega a $58 (ganancia=$8 = 2R), el stop sube de $46 a $50.

**Rango explorado:** [0.5, 1.0, 1.5, 2.0]

---

#### `trailing_stop_method` (default: "atr")

**Que es:** Metodo para el trailing stop una vez activado.

- `"atr"`: trailing_stop = max_close - (trailing_atr_multiplier × ATR).
  Se ajusta automaticamente a la volatilidad del activo.
- `"sma"`: Sale si close < SMA(trailing_sma_period) con volumen alto
  (> trailing_volume_factor × promedio).

**Hallazgo:** "atr" es el metodo estandar desde los primeros experimentos.

---

#### `trailing_atr_multiplier` (default: 3.0 en codigo, varía en experimentos)

**Que es:** Multiplo de ATR para el trailing stop. El stop se coloca a
`trailing_atr_multiplier × ATR` por debajo del cierre mas alto alcanzado.

**Efecto:**
- Valores bajos (1.0-1.5): Trailing apretado. Sale rapido ante retrocesos.
  Captura ganancias menores pero con mayor frecuencia.
- Valores medios (2.0-2.5): Balance. Es el rango optimo encontrado.
- Valores altos (3.0-3.5): Trailing suelto. Da mas espacio al precio para
  respirar. Puede capturar movimientos mas grandes pero devuelve mas ganancia
  en retrocesos.

**Rango explorado:** [1.0, 1.5, 2.0, 2.5, 3.0]

**Hallazgo:**
- AAPL: trail=2.0 es optimo en v2, trail=2.5 en v1
- FX: trail=1.5 es optimo (movimientos mas chicos, necesita trailing mas apretado)
- La salida importa tanto como la deteccion: trail=1.5 + target=5R es superior
  a trail=2.0 + target=2R en EURUSD, independientemente del set de senales

---

#### `target_r_multiple` (default: None)

**Que es:** Take profit en multiplos de riesgo inicial (R). Cuando la ganancia
alcanza `target × R`, se cierra la posicion.

**Efecto:**
- None: Sin target. El trade se cierra solo por trailing stop, time exit, o
  stop loss. Deja correr las ganancias indefinidamente.
- 2R: Sale cuando la ganancia es 2x el riesgo. Libera capital rapido para
  nuevas oportunidades.
- 5R: Solo sale en ganancias grandes. Captura los home runs pero mantiene
  capital comprometido mas tiempo.

**Rango explorado:** [None, 2.0, 3.0, 5.0]

**Hallazgo:** Cambio importante entre v1 y v2:
- v1 (AAPL): target=None fue elegido. Los trades "respiran" y trailing maneja salida.
- v2 (AAPL): target=2R domina en todos los top combos. Libera capital rapido,
  mejora Sharpe.
- FX: target=5R es optimo para EURUSD (movimientos mas chicos, necesita dejar
  correr los pocos ganadores).

---

#### `early_exit_days` (default: None)

**Que es:** Si el precio esta por debajo del precio de entrada despues de N dias,
se cierra la posicion. La logica es que si un breakout genuino no se sostiene en
los primeros dias, la premisa de la operacion se invalido.

**Efecto:**
- None: Sin early exit. El trade se mantiene hasta que otro mecanismo lo cierre.
- 3: Si despues de 3 dias el precio esta debajo del entry, se cierra.
- 5: Idem con 5 dias.

**Hallazgo critico:** **early_exit es toxico en FX.** Deshabilitarlo mejora WR
de 20% a 70% y CR de +2.41% a +8.80%. En FX los breakouts tardan mas en
desarrollarse y el precio frecuentemente cae debajo del entry en los primeros
dias antes de avanzar. early_exit=None es universal en FX.

En stocks, early_exit puede funcionar en algunos tickers (AVGO usa 5d, AMZN y
GOOGL usan 3d) pero en los mejores tickers (AAPL, MSFT, NVDA) es None.

---

#### `max_bars_without_progress` (default: None → 15 en v2)

**Que es:** Maximo de barras sin progreso antes de salir. El progreso se mide
como ganancia >= `min_progress_r` × R desde el ultimo check. Si el trade no
progresa en N barras, se cierra (time exit).

**Efecto:** Evita que el capital quede atrapado en trades que no van a ninguna
parte. Un VCP genuino deberia generar movimiento direccional dentro de las
primeras semanas post-breakout.

---

#### `min_progress_r` (default: 0.5)

**Que es:** Ganancia minima en R para considerar que hubo "progreso" y resetear
el contador de `max_bars_without_progress`.

---

## Trend Template (filtro pre-deteccion, opcional)

**Que hace:** Verifica 7 condiciones que caracterizan una accion en Etapa 2 de
Weinstein. Si alguna condicion falla, la senal se descarta. Se aplica como
post-filtro sobre las senales del pipeline.

### Las 7 condiciones

1. close > SMA(150) AND close > SMA(200)
2. SMA(150) > SMA(200)
3. SMA(200) hoy > SMA(200) hace 22 dias (tendencia alcista minimo 1 mes)
4. SMA(50) > SMA(150) AND SMA(50) > SMA(200)
5. close > SMA(50)
6. close >= low_52w × 1.30 (al menos 30% sobre minimo anual)
7. close >= high_52w × 0.75 (dentro del 25% del maximo anual)

### Parametro: `trend_template` (True/False)

**Hallazgo unanime:** **Trend Template = False gana en 8/8 stocks.** El filtro
sobreajusta — mejora WR en train pero falla en test. En AAPL v1: TT=True da
100% WR en train pero 67% WR en test; TT=False da 86% WR en train y 80% en test.

La razon probable es que el pipeline VCP de 6 pasos ya captura la informacion
relevante que el Trend Template verificaria, haciendo el filtro redundante.
Ademas, el TT es un filtro binario estricto que puede rechazar patrones VCP
validos en acciones que temporalmente violan una condicion (ej: precio debajo
de SMA(50) durante la ultima contraccion del VCP).

---

## Volume Contraction vs Volume en Breakout — Dos conceptos distintos

Es importante distinguir dos usos diferentes del volumen en el pipeline:

1. **Volume Contraction (paso 5):** Verifica que el volumen promedio *durante la
   formacion del patron* disminuyo de contraccion en contraccion. Es un filtro
   de calidad del patron — un VCP con volumen constante o creciente indica que
   los institucionales siguen activos (vendiendo o especulando), no que la oferta
   se seco.

2. **Volume en Breakout (paso 6):** Verifica que el volumen *en el dia del
   breakout* es alto relativo al promedio reciente. Confirma que la ruptura
   tiene respaldo institucional — no es un movimiento aleatorio sin participacion.

Los experimentos muestran que estos dos filtros tienen efectos opuestos:
- Volume contraction (paso 5) **mejora calidad** cuando se activa (filtra 3
  trades ruidosos en AAPL, sube WR de 73% a 88% en train)
- Volume en breakout (paso 6) **empeora resultados** cuando se exige. threshold=1.0
  (sin filtro) domina en 8/8 stocks. El filtro descarta mas senales buenas que malas.

La solucion encontrada en v2 es usar `volume_confirmation_window` = 3 dias con
threshold = 1.2x (variante `w3_t1.2`), que es mucho menos estricto que el
threshold clasico de 1.5x en el dia exacto.

---

## Resumen de sensibilidad por parametro

### Parametros de alto impacto (varian significativamente los resultados)

| Parametro | Impacto | Motivo |
|---|---|---|
| vol_contraction_threshold | Muy alto | Calidad de patron |
| max_gap_days | Alto | Filtra patrones fragmentados |
| volume_ratio_threshold | Alto | Breakout confirmation |
| min_total_reduction | Alto | Exigencia de contraccion real |
| max_depth_pct | Alto | Filtra crashs |
| atr_mult | Critico en FX | Define escala de deteccion |
| lookback_bars | Alto en stocks | Ventana temporal |
| trailing_atr_multiplier | Alto | Salida importa tanto como deteccion |
| target_r_multiple | Alto en v2 | Gestion de capital |
| early_exit_days | Critico en FX | Toxico en FX, opcional en stocks |

### Parametros inertes (no cambian resultados significativamente)

| Parametro | Evidencia |
|---|---|
| atr_length | Muy bajo |
| tolerance | Identico en 0.10/0.15/0.20 para AAPL |
| max_depth_pct | Identico en 0.25/0.30/0.35 para AAPL |
| ascending_lows_tolerance | Identico en 0.01/0.03/0.08 para AAPL |
| require_ascending_lows | 0 efecto en EURUSD |
| lookback_bars (hourly FX) | 72-480 identico |
