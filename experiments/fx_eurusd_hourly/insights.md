# FX EURUSD Hourly — Insights

---

## Config general

- **Modo:** sequential (un trade a la vez, sin overlap)
- **Split temporal:** TRAIN 2018 (6,206 barras) / TEST 2019-2026 (45,668 barras)
- **Data:** hourly EURUSD (70,523 barras totales, 2015-2026)
- **Optimizacion:** 2 fases — Fase 1 (grilla deteccion, 1,944 configs) + Fase 2 (grilla salida, 960 configs)
- **Comision:** no modelada
- **Metrica principal:** CR (Cumulative Return) = prod(1 + pnl_i) - 1
- **ATR period:** 14 (horas)

---

## Objetivo

Evaluar si el patron VCP funciona a escala horaria en EURUSD, con una grilla de parametros diseñada para detectar patrones de corto plazo (2 a 20 dias).

---

## Grilla de parametros

### Fase 1 — Deteccion (1,944 configs)

| Parametro | Valores |
|-----------|---------|
| atr_mult | 1.0, 1.5, 2.0 |
| depth_atr | 2, 3, 4 |
| reduction | 0.4, 0.6, 0.8 |
| lookback_bars | 72, 120, 240, 480 (3d, 5d, 10d, 20d) |
| compression_threshold | 0.85, 0.90, 0.95 |
| tolerance | 0.10, 0.15, 0.20 |
| require_ascending_lows | True, False |

### Fase 2 — Salida (960 configs)

| Parametro | Valores |
|-----------|---------|
| trailing_atr_multiplier | 1.0, 1.5, 2.0, 2.5, 3.0 |
| target_r_multiple | None, 2.0, 3.0, 5.0 |
| breakeven_r_multiple | 0.5, 1.0, 1.5, 2.0 |
| max_stop_loss_pct | 0.01, 0.015, 0.02 |
| max_bars_without_progress | 10, 15, 20, None |
| early_exit_days | None (fijo) |

---

## Resultado principal

**Ninguna de las 1,944 configs de deteccion fue rentable en TRAIN 2018.**

Best CR por atr_mult en TRAIN:

| atr_mult | Swings | Contracciones | Avg senales | Avg CR | Best CR |
|----------|--------|---------------|-------------|--------|---------|
| 1.0 | 1,728 | 863 | 116.0 | -2.11% | -0.21% |
| 1.5 | 1,077 | 538 | 83.5 | -1.30% | +0.00% |
| 2.0 | 669 | 334 | 45.7 | -0.48% | +0.00% |

Las configs con best CR = +0.00% son aquellas que no generaron senales (0 trades = 0 loss).

---

## Analisis de sensibilidad — Fase 1

### lookback_bars — COMPLETAMENTE INERTE

| lookback_bars | Avg senales | Avg trades | Avg CR | Best CR |
|---------------|-------------|------------|--------|---------|
| 72 (3d) | 80.8 | 17.9 | -1.30% | +0.00% |
| 120 (5d) | 82.0 | 18.0 | -1.30% | +0.00% |
| 240 (10d) | 82.0 | 18.0 | -1.30% | +0.00% |
| 480 (20d) | 82.0 | 18.0 | -1.30% | +0.00% |

Resultado identico entre 120 y 480. Los patrones que se detectan ya estan dentro de las 72 barras mas recientes; ventanas mas largas no agregan nada.

### require_ascending_lows — INERTE

Identico con True y False, igual que en daily.

### depth_atr

| depth_atr | Avg senales | Avg trades | Avg CR | Best CR |
|-----------|-------------|------------|--------|---------|
| 2 | 24.2 | 6.3 | -0.59% | +0.00% |
| 3 | 79.8 | 18.7 | -1.69% | +0.00% |
| 4 | 141.1 | 29.0 | -1.62% | -0.20% |

Depth mas restrictivo (2) genera menos senales y pierde menos, pero nunca es positivo.

### reduction

| reduction | Avg senales | Avg trades | Avg CR | Best CR |
|-----------|-------------|------------|--------|---------|
| 0.4 | 25.0 | 6.0 | -0.58% | +0.00% |
| 0.6 | 77.7 | 19.5 | -1.72% | +0.00% |
| 0.8 | 142.4 | 28.6 | -1.59% | +0.00% |

Mismo patron: mas exigente = menos senales = menos perdida, pero nunca positivo.

### compression_threshold

| compression_threshold | Avg senales | Avg trades | Avg CR | Best CR |
|-----------------------|-------------|------------|--------|---------|
| 0.85 | 56.9 | 13.9 | -1.21% | +0.00% |
| 0.90 | 80.8 | 18.2 | -1.30% | +0.00% |
| 0.95 | 107.4 | 22.0 | -1.38% | +0.00% |

Relajar el umbral solo agrega mas senales malas.

### tolerance

| tolerance | Avg senales | Avg trades | Avg CR | Best CR |
|-----------|-------------|------------|--------|---------|
| 0.10 | 79.0 | 17.7 | -1.26% | +0.00% |
| 0.15 | 82.3 | 18.0 | -1.29% | +0.00% |
| 0.20 | 83.8 | 18.3 | -1.35% | +0.00% |

Efecto minimo.

---

## Fase 2 y evaluacion final

La "mejor" config de Fase 1 tenia 0 senales en TRAIN (CR=+0.00% por ausencia de trades). La Fase 2 corrio sobre 0 senales — resultado trivial.

Evaluacion final con la config seleccionada:

| Split | Senales | Trades | WR | CR |
|-------|---------|--------|----|----|
| TRAIN | 0 | 0 | — | +0.00% |
| TEST | 2 | 1 | 0% | -0.18% |

El unico trade en TEST: 2020-05-01 14:00 -> 2020-05-01 16:00, stop_loss, PnL=-0.18%, R=-0.6R, duracion 0 dias.

---

## Experimento 2 — atr_mult alto (5, 6, 7)

### Hipotesis

Con atr_mult bajo (1-2), el ZigZag detecta micro-swings que son ruido. Escalar atr_mult a 5-7× ATR(14h) deberia capturar movimientos reales de 0.7-1.0% (equivalentes a ~1 dia de volatilidad), produciendo contracciones significativas.

### Grilla de parametros — Fase 1 (1,944 configs)

| Parametro | Valores |
|-----------|---------|
| atr_mult | 5, 6, 7 |
| depth_atr | 2, 3, 4 |
| reduction | 0.4, 0.6, 0.8 |
| lookback_bars | 240, 480, 720, 960 (10d, 20d, 30d, 40d) |
| compression_threshold | 0.85, 0.90, 0.95 |
| tolerance | 0.10, 0.15, 0.20 |
| require_ascending_lows | True, False |

### Resultado

**0 senales VCP en las 1,944 configs de deteccion.**

| atr_mult | Swings | Contracciones | Senales | Trades |
|----------|--------|---------------|---------|--------|
| 5 | ~95 | 61 | 0 | 0 |
| 6 | ~70 | ~40 | 0 | 0 |
| 7 | ~50 | ~25 | 0 | 0 |

Con atr_mult=5, las contracciones tienen mediana de depth=1.12% y duracion=51h (movimientos reales). Pero el pipeline completo (compression_threshold + breakout filters) rechaza todas las secuencias. Las contracciones existen pero no forman patrones VCP validos.

### Diagnostico

El problema es de "zona muerta":
- **atr_mult bajo (1-2):** ZigZag detecta ruido → muchas senales, todas perdedoras
- **atr_mult alto (5-7):** ZigZag detecta movimientos reales → contracciones significativas, pero 0 pasan los filtros VCP completos

No hay un atr_mult intermedio que funcione: entre 2 y 5, las contracciones transicionan de ruido a movimientos reales, pero la pipeline VCP no encuentra secuencias de contracciones decrecientes con compresion de ATR en ninguno de los rangos.

---

## Experimento 3 — atr_mult alto con max_depth_atr deshabilitado

### Diagnostico del Experimento 2

Investigacion del pipeline revelo que el filtro `max_depth_atr` (valores 2, 3, 4) bloqueaba **todas** las contracciones. Con atr_mult=5, los swings son >= 5× ATR por construccion, entonces cada contraccion tiene depth_atr >= 4.75. El filtro mas permisivo (max_depth_atr=4) rechaza el 100% de las contracciones — es contradictorio con atr_mult alto.

Sin embargo, analisis manual confirmo que existen **20 runs de 2+ contracciones decrecientes** en TRAIN 2018. Ejemplos:
- [9,10,11,12]: 4 contracciones 0.0139% -> 0.0125% -> 0.0096% -> 0.0083% (marzo 2018)
- [44,45,46,47]: 4 contracciones 0.0248% -> 0.0112% -> 0.0102% -> 0.0066% (octubre 2018)

### Grilla de parametros — Fase 1 (648 configs)

| Parametro | Valores |
|-----------|---------|
| atr_mult | 5, 6, 7 |
| max_depth_atr | None (deshabilitado) |
| reduction | 0.4, 0.6, 0.8 |
| lookback_bars | 240, 480, 720, 960 (10d, 20d, 30d, 40d) |
| compression_threshold | 0.85, 0.90, 0.95 |
| tolerance | 0.10, 0.15, 0.20 |
| require_ascending_lows | True, False |

Fase 2: misma grilla que experimentos anteriores (960 configs).

### Resultado TRAIN

**624/648 configs generan senales, pero ninguna es rentable.**

| atr_mult | Avg senales | Avg trades | Avg CR | Best CR |
|----------|-------------|------------|--------|---------|
| 5 | 148.9 | 18.1 | -2.12% | +0.00% |
| 6 | 160.1 | 19.2 | -2.06% | +0.00% |
| 7 | 118.3 | 14.7 | -1.72% | -0.43% |

Las configs con best CR = +0.00% son las que tienen 0 senales (comp=0.85 + lookback=240 + reduction exigente).

### Sensibilidad Fase 1

| Parametro | Mejor valor | Avg CR | Best CR | Nota |
|-----------|-------------|--------|---------|------|
| atr_mult | 7 | -1.72% | -0.43% | Menos contracciones = menos perdida |
| reduction | 0.40 | -1.17% | +0.00% | Mas exigente = menos senales malas |
| lookback_bars | 240 | -0.86% | +0.00% | Ventanas cortas mejor; 480-960 identicos |
| compression_threshold | 0.85 | -1.56% | +0.00% | Mas estricto = menos senales |
| tolerance | 0.10 | -1.83% | +0.00% | Efecto minimo |
| require_ascending_lows | inerte | identico | identico | True = False |

### Fase 2 y evaluacion final

La "mejor" config de Fase 1 tenia 0 senales en TRAIN. Fase 2 trivial.

Evaluacion final:

| Split | Senales | Trades | WR | CR |
|-------|---------|--------|----|----|
| TRAIN | 0 | 0 | — | +0.00% |
| TEST | 435 | 66 | 38% | -1.38% |

### Analisis de patrones en TEST

Los 66 trades provienen de solo **11 patrones unicos**. El modo sequential re-entra inmediatamente despues de cada salida si el patron sigue activo, generando churning.

| Patron | Fecha | Contracciones | Trades | WR | Total PnL |
|--------|-------|---------------|--------|----|-----------| 
| 1 | 2019-01 | 3 (2.0%->0.9%->0.4%) | 5 | 2/5 | -0.27% |
| 2 | 2019-04 | 2 (2.3%->0.4%) | 9 | 3/9 | +0.02% |
| 3 | 2019-05 | 2 (1.2%->0.5%) | 7 | 2/7 | -0.24% |
| 4 | 2020-04 | 2 (3.4%->0.7%) | 2 | 1/2 | -0.06% |
| 5 | 2020-05 | 2 (2.3%->0.8%) | 2 | 0/2 | -0.39% |
| 6 | 2021-02 | 2 (1.7%->0.6%) | 1 | 0/1 | -0.04% |
| 7 | 2021-04 | 2 (2.4%->0.4%) | 20 | 9/20 | +1.23% |
| 8 | 2021-10 | 2 (1.9%->0.6%) | 12 | 4/12 | -0.16% |
| 9 | 2021-10 | 3 (1.9%->0.6%->0.5%) | 4 | 2/4 | -0.05% |
| 10 | 2024-02 | 2 (1.5%->0.4%) | 1 | 0/1 | -0.21% |
| 11 | 2025-01 | 3 (3.1%->2.2%->1.0%) | 3 | 2/3 | -1.20% |

### Problemas identificados en los graficos

1. **Re-entrada compulsiva:** un patron genera multiples trades hora a hora (ej: patron 7 = 20 trades en 8 dias). Los PnL se cancelan entre si.

2. **Patrones en contexto bajista:** la mayoria de los patrones detectados estan en tendencia bajista previa, no alcista. Un VCP clasico requiere Stage 2 (uptrend).

3. **Muestra insuficiente:** 11 patrones en 7 anos de TEST no permiten inferencia estadistica.

4. **Trades de duracion 0 dias:** la mayoria de los trades duran pocas horas. Stop loss es la salida dominante (38/66 trades).

### Analisis de microestructura horaria

Visualizacion de la dinamica de precio a distintas escalas:

- **1 dia:** retornos horarios con μ≈0%, σ≈0.05%. El precio se mueve ~0.3% en el dia. Ruido puro.
- **1 semana:** rango de ~0.7%. Movimientos intraday de ida y vuelta sin direccion.
- **1 mes:** movimientos mas estructurados (~1%), pero laterales con reversiones.
- **3 meses:** tendencia visible (-2.5%), gaps de fin de semana claros. Esta es la escala que ya captura el detector daily.

---

## Experimento 4 — Patrones cortos (<=5 dias), atr_mult medio (2-4)

### Hipotesis

Los experimentos 1-3 exploraron extremos: atr_mult 1-2 (ruido) y 5-7 (muy pocos patrones). El rango intermedio atr_mult 2-4 con lookback corto (3-5 dias) podria capturar micro-patrones intra-semana. Se simplifica la grilla: tolerance=0.15 fijo, ascending_lows=False fijo, max_depth_atr=None (deshabilitado).

### Grilla de parametros — Fase 1 (54 configs)

| Parametro | Valores |
|-----------|---------|
| atr_mult | 2, 3, 4 |
| max_depth_atr | None (deshabilitado) |
| reduction | 0.40, 0.60, 0.80 |
| lookback_bars | 72, 120 (3d, 5d) |
| compression_threshold | 0.90, 0.95, 1.00 |
| tolerance | 0.15 (fijo) |
| require_ascending_lows | False (fijo) |
| max_contractions | 4 |

### Fase 2 — Salida (216 configs)

| Parametro | Valores |
|-----------|---------|
| trailing_atr_multiplier | 1.0, 1.5, 2.0, 3.0 |
| target_r_multiple | None, 2.0, 3.0 |
| breakeven_r_multiple | 0.5, 1.0, 1.5 |
| max_stop_loss_pct | 0.01, 0.015 |
| max_bars_without_progress | 10, 24, None |

### Resultado TRAIN — primer positivo

**atr_mult=3 produce la primera config rentable en TRAIN de todos los experimentos hourly.**

| atr_mult | Swings | Contracciones | Avg senales | Avg CR | Best CR |
|----------|--------|---------------|-------------|--------|---------|
| 2 | 669 | 334 | 49.3 | -0.78% | +0.00% |
| 3 | 350 | 175 | 37.8 | -0.46% | **+4.95%** |
| 4 | 194 | 97 | 12.9 | -0.14% | +0.00% |

Mejor config deteccion TRAIN: atr_mult=3, red=0.80, lb=72, comp=0.95
Mejor config salida TRAIN: trail=3.0, target=3.0R, be_R=1.0, sl=0.01, bars=24

### Evaluacion final TRAIN / TEST

| Split | Senales | Trades | WR | CR | Avg R | Salidas |
|-------|---------|--------|----|----|-------|---------|
| TRAIN | 313 | 21 | 71% | **+4.95%** | +0.44R | target=2, stop=4, trail=7, time=8 |
| TEST | 1,677 | 139 | 37% | **-6.89%** | -0.04R | stop=69, time=48, trail=20, target=2 |

### Analisis de colapso TRAIN -> TEST

#### Desglose por año (TEST)

| Año | Trades | WR | CR | SL rate | Nota |
|-----|--------|----|----|---------|------|
| 2019 | 29 | 34% | -0.14% | 55% | Bajo ATR (0.7x TRAIN) |
| 2020 | 22 | 55% | **+1.56%** | 36% | Unico año claramente rentable |
| 2021 | 10 | 20% | -0.82% | 60% | Pocos trades, todos malos |
| 2022 | 18 | 17% | **-5.21%** | 72% | Peor año — alta volatilidad (1.4x ATR TRAIN) |
| 2023 | 17 | 41% | -1.46% | 53% | |
| 2024 | 18 | 33% | -1.86% | 44% | |
| 2025 | 17 | 59% | **+1.39%** | 35% | Segundo año rentable |
| 2026 | 8 | 25% | -0.40% | 38% | Parcial (hasta ~abril) |

Solo 2 de 8 años rentables. 2022 concentra la mayoria de la perdida (-5.21%).

#### Metricas comparativas

| Metrica | TRAIN | TEST | Delta |
|---------|-------|------|-------|
| Trades | 21 | 139 | +118 |
| Win Rate | 71% | 37% | -34% |
| Cumulative Return | +4.95% | -6.89% | -11.84% |
| Stop Loss Rate | 19% | 50% | **+31%** |
| Target Rate | 10% | 1% | -8% |
| Avg Duration | 0.8d | 0.9d | ~igual |
| Avg PnL | +0.23% | -0.05% | -0.28% |
| Best trade | +1.49% | +1.09% | |
| Worst trade | -0.32% | -0.93% | |

#### Razon de salida (TEST)

| Razon | N | % | WR | Avg PnL |
|-------|---|---|-------|---------|
| stop_loss | 69 | 50% | 0% | -0.34% |
| time_exit | 48 | 35% | 71% | +0.20% |
| trailing_stop | 20 | 14% | 80% | +0.23% |
| target | 2 | 1% | 100% | +0.94% |

Los stop losses dominan TEST (50% vs 19% en TRAIN) y representan -23.28% de impacto total acumulado. Los time_exits y trailing_stops son marginalmente positivos pero no alcanzan a compensar.

#### Patrones unicos

139 trades provienen de 111 patrones unicos (ratio 1.3x — menos churning que Exp 3 gracias al lookback corto). 84 patrones generaron 1 solo trade, 27 generaron 2-3 trades.

#### Regimen de volatilidad

El ATR al momento de entry varia significativamente por año:
- 2022: ATR = 1.4x TRAIN (alta volatilidad → stop loss de 1% se ejecuta facilmente → 72% SL rate)
- 2019: ATR = 0.7x TRAIN (baja volatilidad → patron calibrado para otra escala)

El stop_loss fijo de 1% es demasiado tight para 2022 (cuando la volatilidad es 40% mayor que en TRAIN) y produce perdidas seriales.

### Diagnostico

1. **Overfitting clasico:** 21 trades en 1 año de TRAIN no son suficientes para inferir un edge estadistico. Con 21 trades y WR=71%, el IC 95% de la verdadera WR es ~[48%, 89%] — el rango incluye resultados aleatorios.

2. **Stop loss no adaptativo:** el max_stop_loss_pct=0.01 esta calibrado para la volatilidad de 2018. En años con ATR mayor (2022), el stop se ejecuta sistematicamente. Necesitaria ser dinamico (ej: 1.5×ATR actual).

3. **Regimenes cambiantes:** 2020 (COVID, alta volatilidad direccional) y 2025 funcionan; 2021-2024 no. El patron es inconsistente entre regimenes.

4. **Señales target casi inexistentes:** solo 2/139 trades llegan al target de 3R. La combinacion trail=3.0×ATR + target=3.0R es demasiado ambiciosa para movimientos horarios de EURUSD.

---

## Conclusiones

1. **VCP a escala horaria no funciona en EURUSD.** Cuatro experimentos lo confirman: atr_mult bajo con depth_atr (Exp 1), atr_mult alto con depth_atr (Exp 2), atr_mult alto sin depth_atr (Exp 3), atr_mult medio con patrones cortos (Exp 4).

2. **El filtro max_depth_atr era contradictorio con atr_mult alto.** Deshabilitarlo desbloqueo el pipeline (de 0 a 624 configs con senales), pero las senales no son rentables.

3. **El problema es estructural, no de filtros.** Con max_depth_atr deshabilitado, el pipeline encuentra secuencias decrecientes reales y genera breakouts, pero tradearlos produce WR=37-38% con R-multiples negativos. Las contracciones horarias no predicen breakouts rentables.

4. **Exp 4 encontro el primer TRAIN positivo (+4.95% con 21 trades) pero colapsa en TEST (-6.89%).** Esto confirma que el edge aparente en TRAIN es overfitting a una muestra pequena, no una señal real.

5. **Churning reducido pero insuficiente:** el lookback corto (72 barras) redujo el churning de 6x (Exp 3) a 1.3x (Exp 4), pero el problema fundamental persiste.

6. **Microestructura horaria incompatible con VCP:** a escala de horas/dias, EURUSD es ruido con reversion a la media. Los movimientos direccionales que el VCP necesita capturar solo aparecen a escala semanal/mensual — exactamente lo que ya detecta el modelo daily.

7. **Conclusión definitiva:** la hipotesis de VCP hourly en EURUSD esta exhaustivamente testeada. No quedan ejes de parametros razonables por explorar. El esfuerzo futuro debe centrarse en el detector daily con otros activos.
