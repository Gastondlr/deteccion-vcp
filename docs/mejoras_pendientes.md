# Mejoras Pendientes del Pipeline VCP

Estado actual del pipeline (mayo 2025): 6 pasos de deteccion + simulacion de trades.
Los items ~~tachados~~ ya fueron implementados.

---

## Paso 1 — Deteccion de Swings (ATR ZigZag)

### 1. Multi-timeframe swings

**Que es:** Detectar swings en multiples timeframes (diario + semanal) y confirmar que
la estructura VCP es consistente en ambos.

**Que mejora:** Reduce falsos positivos en activos ruidosos. Un VCP valido deberia verse
como consolidacion tanto en el grafico diario como en el semanal. Si solo aparece en
diario puede ser ruido intradiario.

**Implementacion:** Resamplear OHLC a semanal, correr el detector de swings en ambos
timeframes, y agregar un filtro que exija que las contracciones diarias esten contenidas
dentro de una estructura semanal coherente (ej. el rango semanal tambien se comprime).

**Complejidad:** Media. Requiere logica de alineacion temporal entre timeframes.

**Impacto esperado:** Medio. Principalmente util para activos small-cap con mucho ruido.

---

## Paso 2 — Contracciones

### ~~2. Profundidad relativa al ATR~~ (IMPLEMENTADO)

Cada contraccion ahora tiene `depth_atr = depth_abs / ATR(14)` calculado en
`compute_contractions`. El filtro `max_depth_atr` en `detect_decreasing_sequence`
rechaza secuencias donde alguna contraccion excede N multiplos de ATR.
Complementa `max_depth_pct` normalizando por volatilidad del activo.

---

## Paso 3 — Secuencia Decreciente

### 3. Metodo robust_trend (regresion lineal)

**Que es:** Detectar la tendencia decreciente de los rangos de contraccion usando
regresion lineal sobre los rangos en vez del metodo `tolerance` (comparacion par a par).

**Que mejora:** Mas robusto ante outliers. Si una contraccion intermedia es ligeramente
mas grande que la anterior pero la tendencia general sigue siendo claramente descendente,
el metodo `tolerance` puede rechazarla mientras que la regresion la acepta.

**Implementacion:** Ya existe el esqueleto en `detect_decreasing_sequence` con
`method="robust_trend"`. Falta implementar: ajustar regresion lineal sobre los rangos,
verificar que la pendiente sea negativa y que R^2 supere `min_r_squared`.

**Complejidad:** Baja. Es un `np.polyfit` de grado 1 sobre pocos puntos (2-7 contracciones).

**Impacto esperado:** Medio. Puede rescatar secuencias validas que el metodo tolerance
descarta por un outlier, sin perder rigurosidad.

### 4. Penalizacion por gaps temporales

**Que es:** Penalizar o rechazar secuencias donde las contracciones sucesivas estan
muy separadas en el tiempo. Un VCP tipico se forma en 3-6 meses; si hay 2 meses de
gap entre contracciones, el patron se "enfrio".

**Que mejora:** Filtra patrones fragmentados que tecnicamente cumplen los criterios
geometricos pero no representan una consolidacion continua. El mercado "olvido" el
patron si paso mucho tiempo.

**Implementacion:** El parametro `max_gap_between_contractions_days` ya existe en
`detect_decreasing_sequence` pero esta hardcodeado a `None`. Activarlo con un default
sensato (ej. 40-60 dias) y agregarlo al search space de Optuna.

**Complejidad:** Muy baja. El codigo ya esta; solo hay que calibrar el valor.

**Impacto esperado:** Bajo-medio. Depende de cuantos patrones fragmentados existan
en el dataset actual.

---

## Paso 4 — Compresion ATR

### 5. Compresion normalizada por regimen de volatilidad

**Que es:** Ajustar el threshold de compresion ATR segun el regimen de volatilidad del
mercado general (VIX o ATR de un indice de referencia como SPY).

**Que mejora:** En mercados de alta volatilidad, es mas dificil que el ATR de un activo
individual se comprima al mismo ratio que en mercados calmos. Un threshold fijo de 0.85
puede ser demasiado exigente en regimenes volatiles y demasiado laxo en calmos.

**Implementacion:** Calcular el ATR del benchmark (SPY/QQQ) en la ventana del patron.
Ajustar el `ratio_threshold` proporcionalmente: si el ATR del mercado esta elevado,
relajar el threshold (ej. 0.90); si esta bajo, endurecerlo (ej. 0.80).

**Complejidad:** Media. Requiere datos del benchmark alineados temporalmente y definir
la funcion de ajuste.

**Impacto esperado:** Medio. Principalmente util si se opera en distintas condiciones
de mercado (bull vs bear vs sideways).

---

## Paso 5 — Contraccion de Volumen

### 6. Volumen relativo per-contraccion

**Que es:** En vez de comparar volumen promedio al inicio vs al final de la secuencia
(metodo "ratio" actual), verificar que cada contraccion sucesiva tenga menos volumen
que la anterior.

**Que mejora:** Captura de forma mas granular el "secado" de oferta que Minervini
describe. El metodo ratio actual puede pasar un patron donde la contraccion 2 tuvo
mas volumen que la 1 pero la 4 tuvo mucho menos, promediando bien pero con una
anomalia en el medio.

**Implementacion:** Ya existe el esqueleto con `method="per_contraction"` en
`verify_volume_contraction`. Falta implementar: para cada par de contracciones
consecutivas, verificar que `vol_avg[i+1] <= vol_avg[i] * (1 + tolerance)`.

**Complejidad:** Baja. Similar al metodo tolerance de la secuencia decreciente.

**Impacto esperado:** Alto. El volumen es clave en la confirmacion del VCP segun
Minervini — un analisis mas granular deberia mejorar la calidad de las senales.

---

## Paso 6 — Breakout del Pivote

### ~~7. ATR trailing stop adaptativo~~ (IMPLEMENTADO)

Trailing stop basado en `highest_close - N * ATR(period)` que se adapta a la
volatilidad del activo. Reemplaza el exit por distribucion (SMA) cuando esta activo.

### ~~8. Time-based exit~~ (IMPLEMENTADO)

Sale de trades que no hacen progreso de R-multiplo en N barras. Libera capital de
trades "zombie" que no avanzan ni retroceden.

### 9. Confirmacion de breakout multi-dia

**Que es:** Exigir que el precio se mantenga sobre el nivel de pivote durante N dias
consecutivos (ej. 2-3) antes de confirmar la entrada, en vez de entrar el mismo dia
del breakout.

**Que mejora:** Filtra breakouts falsos (fakeouts) que rompen el pivote intradía o por
1 dia y luego revierten. Estos son los trades con peor R-multiplo porque entran en el
punto mas alto antes de la reversion.

**Implementacion:** Despues de detectar el breakout, esperar N dias verificando que
cada cierre sea >= pivot_level. Si alguno cae por debajo, descartar. El entry_price
se toma del cierre del dia N (confirmacion). Agregar parametro `breakout_confirmation_days`
(default: 1 = comportamiento actual).

**Complejidad:** Baja. Es un loop adicional post-deteccion del breakout.

**Impacto esperado:** Alto. Los fakeouts son una fuente principal de perdidas en
sistemas de breakout. Incluso 1 dia extra de confirmacion puede mejorar
significativamente el win rate a costa de un entry price ligeramente peor.

### 10. Breakout con analisis de vela

**Que es:** Evaluar la calidad de la vela de breakout: cuerpo real grande (close - open),
cierre cerca del high, sin mecha superior larga. Una vela de breakout ideal muestra
conviccion compradora.

**Que mejora:** Filtra breakouts debiles donde el precio toca el pivote pero cierra
con mecha superior larga (indicando rechazo) o con cuerpo chico (indecision).

**Implementacion:** Calcular metricas de la vela del dia de breakout:
- `body_ratio = abs(close - open) / (high - low)` — debe ser > 0.5
- `upper_wick_ratio = (high - max(open, close)) / (high - low)` — debe ser < 0.3
- `close_position = (close - low) / (high - low)` — debe ser > 0.6
Agregar como filtro opcional con parametros configurables.

**Complejidad:** Baja. Son calculos simples sobre OHLC del dia.

**Impacto esperado:** Medio. Complementa bien la confirmacion multi-dia (#9).
Puede filtrar breakouts por gap que luego se llenan.

---

## Trade Management

### 11. Partial profit taking

**Que es:** Tomar ganancia parcial en hitos de R-multiplo. Por ejemplo, vender 50% de
la posicion en 2R y dejar correr el resto con trailing stop.

**Que mejora:** Mejora el perfil de riesgo/retorno. Asegura ganancia parcial en trades
que llegan a un nivel de profit aceptable, mientras mantiene exposicion al upside.
Reduce la varianza de los retornos.

**Implementacion:** En `simulate_trade`, trackear posicion parcial. Cuando `r_mult`
cruza un threshold (ej. `partial_take_r = 2.0`), registrar venta parcial (50%) y
continuar simulando el resto. El PnL final es la combinacion ponderada.

**Complejidad:** Media. Requiere refactorear `simulate_trade` para manejar posicion
variable y calcular PnL combinado.

**Impacto esperado:** Medio. Mejora metricas de riesgo (max drawdown, worst trade)
pero puede reducir el upside de los mejores trades.

### 12. Volatility-adjusted position sizing

**Que es:** Tamano de posicion inversamente proporcional al ATR del activo. Activos
mas volatiles reciben posiciones mas chicas para ecualizar el riesgo en dolares.

**Que mejora:** Ecualiza el impacto de cada trade en el portfolio. Sin esto, un trade
en un activo volatil (ej. MELI con ATR de 3%) domina el P&L vs uno estable (ej. KO
con ATR de 0.8%), aunque ambos tengan el mismo R-multiplo.

**Implementacion:** Calcular `position_size = risk_budget / (N * ATR)` donde
`risk_budget` es el monto fijo en dolares a arriesgar y N es el multiplicador ATR
del stop. Integrar en la simulacion de trades para que el PnL refleje el sizing.

**Complejidad:** Media. Requiere definir capital inicial y risk budget, y ajustar
todas las metricas de retorno para reflejar sizing variable.

**Impacto esperado:** Alto a nivel portfolio. No cambia las senales ni el win rate,
pero puede mejorar dramaticamente el retorno ajustado por riesgo y el Sharpe ratio.

---

## Prioridad sugerida

Ordenadas por relacion impacto/esfuerzo:

| # | Mejora | Impacto | Esfuerzo | Prioridad |
|---|--------|---------|----------|-----------|
| 9 | Confirmacion breakout multi-dia | Alto | Bajo | 1 |
| ~~2~~ | ~~Profundidad relativa al ATR~~ | ~~Alto~~ | ~~Bajo~~ | ~~DONE~~ |
| 6 | Volumen per-contraccion | Alto | Bajo | 3 |
| 4 | Penalizacion gaps temporales | Medio | Muy bajo | 4 |
| 10 | Analisis de vela de breakout | Medio | Bajo | 5 |
| 3 | Metodo robust_trend | Medio | Bajo | 6 |
| 12 | Position sizing por volatilidad | Alto | Medio | 7 |
| 11 | Partial profit taking | Medio | Medio | 8 |
| 5 | Compresion normalizada por VIX | Medio | Medio | 9 |
| 1 | Multi-timeframe swings | Medio | Medio | 10 |
