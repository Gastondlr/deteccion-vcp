# Informe: VCP en EURUSD a escala horaria

## Contexto

El detector VCP fue desarrollado y validado originalmente sobre data diaria, donde
produce resultados positivos en EURUSD (5 trades, 80% WR, +7.93% CR en TEST
2020-2026). Este informe documenta la investigacion exhaustiva sobre si el patron
VCP puede adaptarse a escala horaria en EURUSD.

**Data:** 70,523 barras horarias de EURUSD (2015-2026).
**Split:** TRAIN 2018 (6,206 barras, 1 ano) / TEST 2019-2026 (45,668 barras, 8 anos).
**Modo:** Sequential (un trade a la vez, sin overlap).

La eleccion de TRAIN 2018 se debe a que es un ano representativo sin eventos
extremos (no incluye COVID 2020, crisis energetica 2022, etc.), lo que permite
evaluar si el patron funciona en condiciones "normales" de mercado.

---

## Diferencias FX horario vs diario

Antes de describir los experimentos, es importante entender por que la escala
horaria es un desafio diferente al diario:

| Metrica | Diario | Horario | Ratio |
|---|---|---|---|
| Barras por ano | ~252 | ~6,200 | 25x mas datos |
| ATR tipico (14 periodos) | ~0.6% del precio | ~0.05% del precio | 12x menor |
| Movimiento tipico 1 periodo | ~0.4% | ~0.04% | 10x menor |
| Ruido vs senal | Bajo | Alto | Mucho mas ruido |
| Duracion de tendencias | Semanas-meses | Horas-dias | Mucho mas cortas |

Las contracciones en horario son del orden de 0.5-3% (vs 5-25% en diario), y los
movimientos post-breakout son proporcionalmente menores. El stop loss se adapto a
1-2% (vs 7% en stocks, 2% en FX diario).

---

## Experimento 1: atr_mult bajo (1.0 - 2.0)

### Hipotesis

Usar los mismos rangos de atr_mult que funcionan en FX diario (1.0-2.0), adaptando
el lookback a barras horarias (3 a 20 dias de trading = 72 a 480 barras).

### Parametros variados — Fase 1 deteccion (1,944 configs)

| Parametro | Valores | Por que se varia |
|---|---|---|
| atr_mult | 1.0, 1.5, 2.0 | Rango que funciona en FX diario. Define la escala minima de movimiento para registrar un swing. Con ATR horario ~0.05%, atr_mult=1.0 requiere movimientos de ~0.05% (muy chico), atr_mult=2.0 requiere ~0.10%. |
| depth_atr | 2, 3, 4 | Profundidad maxima de contraccion en multiplos de ATR. Valores mas bajos que diario (donde se usa 5-6) porque las contracciones horarias son mas chicas. |
| reduction | 0.4, 0.6, 0.8 | Reduccion total exigida entre primera y ultima contraccion. Mismos valores que diario — es un ratio, no depende de la escala. |
| lookback_bars | 72, 120, 240, 480 | Ventana temporal: 72 barras = 3 dias, 120 = 5 dias, 240 = 10 dias, 480 = 20 dias. Se varia para encontrar la duracion de patron optima a escala horaria. |
| compression_threshold | 0.85, 0.90, 0.95 | Ratio ATR_fin/ATR_inicio. Mismos valores que diario. |
| tolerance | 0.10, 0.15, 0.20 | Margen para secuencia "casi" decreciente. Mismos valores que diario. |
| require_ascending_lows | True, False | Si exigir lows ascendentes. Se varia porque en contracciones tan chicas podria ser demasiado restrictivo. |

### Parametros fijos

| Parametro | Valor | Razon |
|---|---|---|
| max_stop_loss_pct | 0.02 | Adaptado a FX (2%, mismo que FX diario) |
| early_exit_days | None | Descartado en FX diario — se mantiene deshabilitado |
| min_contractions | 2 | Minimo para VCP |
| max_contractions | 6 | Estandar |

### Resultados TRAIN 2018

Ninguna de las 1,944 configuraciones fue rentable.

| atr_mult | Swings detectados | Contracciones | Avg CR | Best CR |
|---|---|---|---|---|
| 1.0 | 1,728 | 863 | -2.11% | -0.21% |
| 1.5 | 1,077 | 538 | -1.30% | +0.00% |
| 2.0 | 669 | 334 | -0.48% | +0.00% |

Las configs con best CR = +0.00% son las que no generaron ninguna senal (0 trades
= 0 perdida). No hay una sola config que genere retorno positivo.

**lookback_bars resulto completamente inerte:**

| lookback_bars | Avg senales | Avg trades | Avg CR |
|---|---|---|---|
| 72 (3 dias) | 80.8 | 17.9 | -1.30% |
| 120 (5 dias) | 82.0 | 18.0 | -1.30% |
| 240 (10 dias) | 82.0 | 18.0 | -1.30% |
| 480 (20 dias) | 82.0 | 18.0 | -1.30% |

De 120 a 480 barras los resultados son identicos. Los patrones detectados ya estan
dentro de las 72 barras mas recientes — ventanas mas largas no agregan nada.

**require_ascending_lows tambien inerte:** resultados identicos con True y False.

### Diagnostico

Con atr_mult=1.0, el ZigZag detecta 1,728 swings en 6,206 barras — un swing cada
3.6 barras (menos de 4 horas). Esos "swings" son oscilaciones aleatorias del precio
dentro del spread bid-ask. Las contracciones que se forman entre ellos no tienen
poder predictivo — son ruido puro.

Con atr_mult=2.0 se reduce a 669 swings (1 cada 9 barras), pero sigue siendo
demasiado frecuente para capturar estructura real de mercado.

---

## Experimento 2: atr_mult alto (5.0 - 7.0)

### Hipotesis

Si atr_mult bajo detecta ruido, atr_mult alto (5-7x ATR horario) deberia capturar
movimientos reales de 0.25-0.35% — equivalentes a medio dia o un dia completo de
movimiento. Esto filtraria el ruido y detectaria solo las correcciones significativas.

Se amplio el lookback a 10-40 dias (240-960 barras) porque con swings mas espaciados
los patrones tardan mas en formarse.

### Parametros variados — Fase 1 (1,944 configs)

| Parametro | Valores | Por que |
|---|---|---|
| atr_mult | 5, 6, 7 | Escala alta: solo movimientos de ~0.25-0.35%. Deberia filtrar ruido completamente. |
| depth_atr | 2, 3, 4 | Mismos que exp 1 |
| reduction | 0.4, 0.6, 0.8 | Mismos que exp 1 |
| lookback_bars | 240, 480, 720, 960 | Ventanas mas largas (10d a 40d) para patrones de mayor duracion |
| compression_threshold | 0.85, 0.90, 0.95 | Mismos |
| tolerance | 0.10, 0.15, 0.20 | Mismos |
| require_ascending_lows | True, False | Mismos |

### Resultados TRAIN 2018

**0 senales VCP en todas las 1,944 configuraciones.**

| atr_mult | Swings | Contracciones | Senales | Trades |
|---|---|---|---|---|
| 5 | ~95 | 61 | 0 | 0 |
| 6 | ~70 | ~40 | 0 | 0 |
| 7 | ~50 | ~25 | 0 | 0 |

Con atr_mult=5 se detectan 95 swings con contracciones de mediana 1.12% y duracion
51 horas — movimientos reales. Pero el pipeline VCP completo (secuencia decreciente
+ compresion ATR + breakout) rechaza todas las secuencias.

### Diagnostico

Investigacion detallada del pipeline revelo que el filtro `max_depth_atr` (con
valores 2, 3, 4) bloqueaba el 100% de las contracciones. La contradiccion es
matematica: si atr_mult=5, los swings requieren un movimiento de >= 5×ATR para
confirmarse. Por construccion, la contraccion entre ese swing y el siguiente tiene
depth_atr >= 4.75. Pero el filtro mas permisivo (max_depth_atr=4) rechaza toda
contraccion con depth_atr > 4. Resultado: 100% rechazado.

Se confirmo manualmente que existen secuencias de contracciones decrecientes reales
en la data (ej: 4 contracciones de 1.39% → 1.25% → 0.96% → 0.83% en marzo 2018),
pero el filtro max_depth_atr las bloquea.

Este descubrimiento motivo el experimento 3.

---

## Experimento 3: atr_mult alto con max_depth_atr deshabilitado

### Hipotesis

Desactivar max_depth_atr (poner None) deberia desbloquear el pipeline para atr_mult
alto, permitiendo evaluar las contracciones reales que se detectaron en exp 2.

### Parametros variados — Fase 1 (648 configs)

| Parametro | Valores | Cambio vs exp 2 |
|---|---|---|
| atr_mult | 5, 6, 7 | Igual |
| max_depth_atr | **None** | **Deshabilitado** (antes: 2, 3, 4) |
| reduction | 0.4, 0.6, 0.8 | Igual |
| lookback_bars | 240, 480, 720, 960 | Igual |
| compression_threshold | 0.85, 0.90, 0.95 | Igual |
| tolerance | 0.10, 0.15, 0.20 | Igual |
| require_ascending_lows | True, False | Igual |

### Parametros de salida — Fase 2 (960 configs)

| Parametro | Valores | Por que |
|---|---|---|
| trailing_atr_multiplier | 1.0, 1.5, 2.0, 2.5, 3.0 | Rango estandar |
| target_r_multiple | None, 2.0, 3.0, 5.0 | Evaluar si un target fijo ayuda |
| breakeven_r_multiple | 0.5, 1.0, 1.5, 2.0 | Rango estandar |
| max_stop_loss_pct | 0.01, 0.015, 0.02 | Adaptado a horario (1-2%) |
| max_bars_without_progress | 10, 15, 20, None | Time exit en barras horarias |
| early_exit_days | None (fijo) | Descartado universalmente en FX |

### Resultados TRAIN 2018

**624 de 648 configs generan senales, pero ninguna es rentable.**

| atr_mult | Avg senales | Avg trades | Avg CR | Best CR |
|---|---|---|---|---|
| 5 | 148.9 | 18.1 | -2.12% | +0.00% |
| 6 | 160.1 | 19.2 | -2.06% | +0.00% |
| 7 | 118.3 | 14.7 | -1.72% | -0.43% |

Las configs con best CR = +0.00% son las que generaron 0 senales (comp=0.85 +
lookback=240 + reduction exigente).

### Evaluacion en TEST 2019-2026

Con la "mejor" config de TRAIN (0 senales):

| Split | Senales | Trades | WR | CR |
|---|---|---|---|---|
| TRAIN | 0 | 0 | — | +0.00% |
| TEST | 435 | 66 | 38% | -1.38% |

### Analisis de patrones en TEST

Los 66 trades provienen de solo **11 patrones unicos**. El modo sequential re-entra
inmediatamente despues de cada salida si el precio sigue arriba del pivot, generando
churning (re-entrada compulsiva):

| Patron | Fecha | Contracciones | Trades | WR | PnL total |
|---|---|---|---|---|---|
| 1 | 2019-01 | 3 (2.0%→0.9%→0.4%) | 5 | 2/5 | -0.27% |
| 2 | 2019-04 | 2 (2.3%→0.4%) | 9 | 3/9 | +0.02% |
| 3 | 2019-05 | 2 (1.2%→0.5%) | 7 | 2/7 | -0.24% |
| 7 | 2021-04 | 2 (2.4%→0.4%) | 20 | 9/20 | +1.23% |
| 8 | 2021-10 | 2 (1.9%→0.6%) | 12 | 4/12 | -0.16% |
| 11 | 2025-01 | 3 (3.1%→2.2%→1.0%) | 3 | 2/3 | -1.20% |

El patron 7 es el caso extremo: 1 patron genera 20 trades en 8 dias porque el
precio oscila alrededor del pivot y el sistema entra y sale hora a hora.

### Problemas identificados

1. **Re-entrada compulsiva:** un patron genera multiples trades que se cancelan
   entre si. El ratio trades/patrones es 6x (66 trades / 11 patrones).

2. **Patrones en contexto bajista:** la mayoria de los patrones detectados se forman
   durante tendencias bajistas, no alcistas. Un VCP genuino requiere Etapa 2
   (uptrend). Sin filtro de tendencia en FX, se detectan "VCPs" en consolidaciones
   dentro de caidas.

3. **Trades de duracion 0 dias:** la mayoria duran pocas horas. Stop loss es la
   salida dominante (38/66 trades = 58%).

---

## Experimento 4: atr_mult medio (2-4), lookback corto (3-5 dias)

### Hipotesis

Los experimentos 1-3 exploraron los extremos: atr_mult bajo (1-2, ruido) y alto
(5-7, muy pocos patrones). El rango intermedio atr_mult 2-4 con lookback corto
(3-5 dias = 72-120 barras) podria capturar micro-patrones intra-semana que no son
ni ruido ni movimientos demasiado grandes.

Se simplificaron parametros que resultaron inertes en exp 1-3: tolerance fijo en
0.15, ascending_lows=False, max_depth_atr=None, max_contractions=4 (patrones mas
cortos).

### Parametros variados — Fase 1 (54 configs)

| Parametro | Valores | Por que |
|---|---|---|
| atr_mult | 2, 3, 4 | Rango intermedio no explorado. 2×ATR horario ≈ 0.10%, 4×ATR ≈ 0.20%. |
| max_depth_atr | None | Deshabilitado (aprendido de exp 2-3: bloquea con atr_mult alto) |
| reduction | 0.40, 0.60, 0.80 | Mismos |
| lookback_bars | 72, 120 | Solo 3 y 5 dias — patrones intra-semana |
| compression_threshold | 0.90, 0.95, 1.00 | 1.00 = deshabilitar filtro de compresion (probar sin el) |

### Parametros fijos (aprendidos de exp 1-3)

| Parametro | Valor | Razon |
|---|---|---|
| tolerance | 0.15 | Efecto minimo en exp 1, se fija en valor intermedio |
| require_ascending_lows | False | Inerte en todos los experimentos previos |
| max_contractions | 4 | Patrones cortos (intra-semana, no mas de 4 contracciones) |

### Parametros de salida — Fase 2 (216 configs)

| Parametro | Valores | Por que |
|---|---|---|
| trailing_atr_multiplier | 1.0, 1.5, 2.0, 3.0 | Trailing adaptado a escala horaria |
| target_r_multiple | None, 2.0, 3.0 | Sin 5R (inalcanzable en horario segun exp 3) |
| breakeven_r_multiple | 0.5, 1.0, 1.5 | Rango estandar |
| max_stop_loss_pct | 0.01, 0.015 | Mas apretado que exp 1-3 porque los patrones son mas cortos |
| max_bars_without_progress | 10, 24, None | 10 barras ≈ medio dia, 24 barras = 1 dia |

### Resultados TRAIN 2018

**Primer resultado positivo en TRAIN de todos los experimentos hourly.**

| atr_mult | Swings | Contracciones | Avg CR | Best CR |
|---|---|---|---|---|
| 2 | 669 | 334 | -0.78% | +0.00% |
| **3** | **350** | **175** | **-0.46%** | **+4.95%** |
| 4 | 194 | 97 | -0.14% | +0.00% |

Mejor config deteccion: atr_mult=3, reduction=0.80, lookback=72, compression=0.95.
Mejor config salida: trail=3.0, target=3.0R, be_R=1.0, sl=0.01, bars=24.

Con esta config en TRAIN: 21 trades, 71% WR, +4.95% CR, avg_R=+0.44R.

### Resultados TEST 2019-2026

**Colapso total.**

| Split | Senales | Trades | WR | CR | Avg R |
|---|---|---|---|---|---|
| TRAIN | 313 | 21 | 71% | +4.95% | +0.44R |
| TEST | 1,677 | 139 | 37% | -6.89% | -0.04R |

### Desglose por ano (TEST)

| Ano | Trades | WR | CR | SL rate | Nota |
|---|---|---|---|---|---|
| 2019 | 29 | 34% | -0.14% | 55% | ATR 0.7x TRAIN (baja volatilidad) |
| **2020** | **22** | **55%** | **+1.56%** | **36%** | **Unico ano claramente rentable** (COVID, alta volatilidad direccional) |
| 2021 | 10 | 20% | -0.82% | 60% | Pocos trades, todos malos |
| **2022** | **18** | **17%** | **-5.21%** | **72%** | **Peor ano** — ATR 1.4x TRAIN |
| 2023 | 17 | 41% | -1.46% | 53% | |
| 2024 | 18 | 33% | -1.86% | 44% | |
| 2025 | 17 | 59% | +1.39% | 35% | Segundo ano rentable |
| 2026 | 8 | 25% | -0.40% | 38% | Parcial (hasta abril) |

Solo 2 de 8 anos rentables (2020 y 2025). 2022 concentra el 75% de la perdida.

### Metricas comparativas TRAIN vs TEST

| Metrica | TRAIN | TEST | Delta |
|---|---|---|---|
| Trades | 21 | 139 | +118 |
| Win Rate | 71% | 37% | -34pp |
| Cumulative Return | +4.95% | -6.89% | -11.84pp |
| Stop Loss Rate | 19% | 50% | +31pp |
| Target Rate | 10% | 1% | -8pp |
| Avg Duration | 0.8 dias | 0.9 dias | ~igual |
| Avg PnL | +0.23% | -0.05% | -0.28pp |
| Best trade | +1.49% | +1.09% | |
| Worst trade | -0.32% | -0.93% | |

### Razones de salida (TEST)

| Razon | N | % | WR | Avg PnL |
|---|---|---|---|---|
| stop_loss | 69 | 50% | 0% | -0.34% |
| time_exit | 48 | 35% | 71% | +0.20% |
| trailing_stop | 20 | 14% | 80% | +0.23% |
| target | 2 | 1% | 100% | +0.94% |

Los stop losses dominan TEST (50% vs 19% en TRAIN). Solo 2 de 139 trades alcanzan
el target de 3R — el target es inalcanzable a escala horaria.

### Diagnostico del colapso

1. **Overfitting clasico:** 21 trades en 1 ano de TRAIN no son suficientes para
   inferir un edge estadistico. Con n=21 y WR observado=71%, el intervalo de
   confianza 95% de la verdadera WR es [48%, 89%]. El rango incluye 50% (aleatorio).

2. **Stop loss no adaptativo:** max_stop_loss_pct=0.01 (1%) esta calibrado para la
   volatilidad de 2018. En 2022, el ATR horario es 1.4x mayor que en 2018. Un stop
   de 1% en un mercado donde la volatilidad horaria subio 40% se ejecuta
   sistematicamente (72% SL rate en 2022 vs 19% en TRAIN).

3. **Regimenes cambiantes:** 2020 (COVID, alta volatilidad direccional) y 2025
   funcionan porque tienen caracteristicas similares a 2018 — movimientos
   direccionales cortos. 2021-2024 no funcionan porque el mercado esta en regimenes
   diferentes (lateralizacion, tendencias largas, etc.).

4. **Target inalcanzable:** solo 2/139 trades llegan a 3R. La combinacion
   trail=3.0×ATR + target=3.0R es demasiado ambiciosa para movimientos horarios
   de EURUSD que tipicamente son de 0.3-0.5% en un dia.

---

## Conclusiones

### 1. VCP a escala horaria no funciona en EURUSD

Cuatro experimentos cubriendo todo el espacio de parametros razonables lo confirman:

| Exp | atr_mult | max_depth_atr | Resultado |
|---|---|---|---|
| 1 | 1-2 (bajo) | 2-4 | 0 configs rentables — micro-swings = ruido |
| 2 | 5-7 (alto) | 2-4 | 0 senales — filtro bloquea todo |
| 3 | 5-7 (alto) | None | 624 configs con senales, 0 rentables — churning |
| 4 | 2-4 (medio) | None | 1 config positiva en TRAIN, colapsa en TEST |

No queda un rango de atr_mult sin explorar. No hay combinacion de parametros que
produzca resultados positivos consistentes.

### 2. El problema es estructural, no de parametros

Con max_depth_atr deshabilitado (exp 3-4), el pipeline encuentra secuencias de
contracciones decrecientes reales y genera breakouts. Las contracciones existen y
son geometricamente validas. Pero tradearlas produce WR=37-38% con R-multiples
negativos. Las contracciones horarias no predicen breakouts rentables.

### 3. Microestructura horaria incompatible con VCP

La visualizacion de la dinamica de precio a distintas escalas revela por que:

- **1 hora:** retornos con media ~0%, desviacion ~0.05%. Puro ruido.
- **1 dia:** rango de ~0.3%. Movimientos de ida y vuelta sin direccion.
- **1 semana:** rango de ~0.7%. Algo mas de estructura, pero lateralizacion dominante.
- **1 mes:** movimientos de ~1%. Empiezan a verse tendencias.
- **3 meses:** tendencia visible (~2.5%). Esta es la escala que captura el detector
  daily.

El patron VCP asume que una secuencia de contracciones decrecientes indica que la
oferta flotante se esta agotando — los tenedores debiles salen en cada correccion
y las instituciones absorben la oferta. Esto funciona a escala de semanas/meses
porque refleja el ciclo real de acumulacion institucional. A escala de horas, las
"contracciones" son fluctuaciones aleatorias del precio sin relacion con flujos
institucionales reales.

### 4. El unico resultado positivo (exp 4) es overfitting

21 trades en 1 ano no permiten inferencia estadistica. El colapso de +4.95% en
TRAIN a -6.89% en TEST es evidencia clara de sobreajuste. Ademas, el stop loss
fijo de 1% falla cuando la volatilidad cambia — un modelo que depende de que la
volatilidad futura sea identica a la del periodo de calibracion no es operable.

### 5. Recomendacion

No invertir mas esfuerzo en VCP horario para EURUSD. Los ejes de exploracion estan
agotados:

- atr_mult: cubierto de 1 a 7
- max_depth_atr: cubierto con valores numericos y deshabilitado
- lookback_bars: cubierto de 72 a 960 barras (3 a 40 dias)
- compression_threshold: cubierto de 0.85 a 1.00
- stop loss: cubierto de 1% a 2%

El esfuerzo futuro debe centrarse en el detector daily, que ya produce resultados
positivos y validados en TEST para EURUSD, GBPUSD y USDCNY.
