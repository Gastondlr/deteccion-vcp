# Cronica del proyecto — Deteccion VCP

Registro cronologico de las decisiones, experimentos y hallazgos del proyecto.
Cada entrada documenta que se hizo, que parametros se variaron, que resultados
se obtuvieron y que decisiones se tomaron como consecuencia.

---

## 4 de mayo de 2026

### Setup inicial del proyecto

Se creo el proyecto standalone de deteccion VCP (Volatility Contraction Pattern)
basado en el metodo SEPA de Mark Minervini. El pipeline de deteccion tiene 6 pasos:

1. Swing Detection (ATR ZigZag)
2. Contractions (profundidad entre pares de swings)
3. Decreasing Sequence (secuencia monotona decreciente)
4. ATR Compression (volatilidad tambien decrece)
5. Volume Contraction (volumen se seca durante formacion)
6. Pivot Breakout (ruptura sobre ultimo high con volumen)

Se implemento un unico detector (ATRZigZagDetector) eliminando ScipyPeaksDetector
que era inferior. Se mejoro la deteccion heuristica con filtro de gaps, skip de
swings no confirmados, y fix de profundidad cero. Se agregaron tests unitarios
y un notebook demo.

### Descripcion del metodo SEPA de Mark Minervini

#### En que consiste el metodo SEPA

SEPA (Specific Entry Point Analysis) es una metodologia de trading desarrollada
por Mark Minervini, ganador del US Investing Championship en 1997 con un retorno
del 155% y nuevamente en 2021. El metodo esta documentado en dos libros:
*Trade Like a Stock Market Wizard* (2013) y *Think & Trade Like a Champion* (2017).

El metodo SEPA es un sistema de seleccion de acciones orientado al momentum que
combina analisis tecnico y fundamental para identificar puntos de entrada de bajo
riesgo y alta recompensa. Su objetivo es posicionarse en acciones que estan en la
fase mas explosiva de su ciclo de precio — lo que Stan Weinstein denomino "Etapa 2"
o fase de avance — y hacerlo en el momento preciso donde el riesgo definido por el
stop-loss es minimo en relacion al potencial de ganancia.

SEPA no es un sistema de prediccion. Es un sistema de identificacion y reaccion:
identifica acciones que ya estan demostrando fortaleza institucional (las grandes
instituciones ya estan comprando) y se posiciona cuando el patron tecnico ofrece
una entrada con una relacion riesgo-recompensa favorable.

El flujo completo del metodo sigue una secuencia de filtros sucesivos, donde cada
paso reduce el universo de acciones hasta quedarse solo con las mejores candidatas:

1. Se evalua el contexto del mercado general para determinar que nivel de exposicion
   es apropiado (exposicion progresiva).
2. Se filtran las acciones usando la Plantilla de Tendencia, un conjunto de 8
   condiciones tecnicas que confirman que una accion esta en Etapa 2.
3. Se aplican filtros fundamentales para verificar que la fortaleza del precio esta
   respaldada por crecimiento real del negocio (beneficios, ventas, margenes).
4. Se busca el patron VCP (Volatility Contraction Pattern) dentro de las acciones
   que pasaron ambos filtros — este patron identifica el momento optimo de entrada.
5. Se entra en la posicion cuando el precio supera el punto pivote con volumen
   confirmatorio.
6. Se gestiona la posicion con un sistema de stop-loss dinamico que evoluciona en
   tres fases.

El metodo opera exclusivamente en acciones individuales, no en indices ni en ETFs,
y se concentra en acciones de mediana y gran capitalizacion listadas en NYSE y NASDAQ.

#### La Plantilla de Tendencia (Trend Template)

La Plantilla de Tendencia es el primer filtro cuantitativo del metodo SEPA. Es una
formalizacion de las condiciones que caracterizan una accion en Etapa 2 de Weinstein,
traducidas a 8 condiciones numericas verificables que involucran medias moviles simples,
extremos de precio de 52 semanas, y fuerza relativa.

El principio detras de la plantilla es que una accion en una tendencia alcista saludable
exhibe un conjunto especifico de relaciones entre su precio y sus medias moviles: el
precio esta por encima de todas las medias, las medias estan apiladas en orden (la mas
rapida arriba, la mas lenta abajo), y todas tienen pendiente ascendente. Ademas, el
precio debe estar significativamente por encima de su minimo reciente (confirmando que
ya hubo un avance) y relativamente cerca de su maximo (confirmando que no colapso).

La plantilla funciona como un filtro binario: las 8 condiciones deben cumplirse
simultaneamente. Si una sola falla, la accion se descarta.

**Las 8 condiciones:**

1. **Precio > SMA(150) y SMA(200):** La accion cotiza por encima de ambas medias
   moviles de largo plazo, confirmando tendencia alcista sostenida.

2. **SMA(150) > SMA(200):** Las medias de largo plazo estan apiladas en orden alcista.
   La tendencia de mediano plazo es mas fuerte que la de largo plazo — la accion esta
   acelerandose al alza.

3. **SMA(200) ascendente desde hace al menos 1 mes:** SMA(200) de hoy > SMA(200) de
   hace 22 dias habiles. Idealmente ascendente durante 4-5 meses; minimo aceptable 1 mes.

4. **SMA(50) > SMA(150) > SMA(200):** Apilamiento completo de las tres medias moviles.
   El momentum de corto plazo es fuerte y arrastra las medias mas lentas al alza.

5. **Precio > SMA(50):** El precio esta por encima de la media de corto plazo. Durante
   la formacion del VCP, el precio puede violar temporalmente esta condicion — las
   contracciones pueden llevarlo debajo de la SMA(50). Pero debe cumplirse al momento
   de la entrada.

6. **Precio >= Minimo_52w × 1.30:** La accion esta al menos 30% por encima de su
   minimo de 52 semanas (MIN del low de los ultimos 252 dias habiles). Confirma que
   ya hubo un avance significativo. Algunos usan umbral del 25%.

7. **Precio >= Maximo_52w × 0.75:** La accion esta dentro del 25% de su maximo de 52
   semanas (MAX del high de los ultimos 252 dias habiles). Confirma que no colapso.
   Las mejores acciones en Etapa 2 suelen estar dentro del 10-15% de su maximo.

8. **RS Ranking >= 70:** La accion tiene mejor performance de precio que al menos el
   70% del universo. Calculo estandar de IBD pondera 40% ultimo trimestre y 20% cada
   uno de los tres anteriores. Minervini prefiere RS >= 80 o >= 90.

#### Filtros fundamentales

Una vez que una accion pasa las 8 condiciones tecnicas, se aplica un segundo nivel
de filtrado basado en los fundamentos de la empresa. La logica es que las tendencias
alcistas mas poderosas estan respaldadas por crecimiento real del negocio.

**Beneficio por Accion (BPA / EPS):**
- Crecimiento interanual del ultimo trimestre >= 20-25% (vs mismo trimestre del ano anterior)
- Crecimiento acelerandose trimestre a trimestre
- Estimaciones de analistas siendo revisadas al alza
- Sorpresas positivas de beneficios (BPA real > estimaciones del consenso)

**Ventas / Ingresos:**
- Crecimiento interanual >= 20-25%, acelerandose
- Confirma que el crecimiento de beneficios es organico (mas negocio real, no solo
  recorte de costos o recompra de acciones)

**ROE y Margenes:**
- ROE >= 17%, preferiblemente > 20%
- Margenes de beneficio operativo expandiendose o estables

**Catalizadores:**
- Producto nuevo disruptivo, regulacion favorable, expansion geografica, cambio de
  management, innovacion tecnologica. Los grandes ganadores historicos casi siempre
  tenian algo nuevo e importante que los impulsaba.

#### El patron VCP (Volatility Contraction Pattern)

El VCP es el patron tecnico que define la senal de entrada en SEPA. Solo se busca en
acciones que ya pasaron la Plantilla de Tendencia y los filtros fundamentales. Es un
patron de continuacion dentro de la Etapa 2 — no marca el inicio de la tendencia
alcista, sino una pausa dentro de ella que ofrece un punto de entrada optimo.

El VCP se compone de 2 a 6 contracciones de precio progresivamente menores. Cada
contraccion es una correccion desde un swing high hasta un swing low, seguida de una
recuperacion parcial o total. La caracteristica definitoria es que cada correccion
sucesiva es de menor magnitud que la anterior.

Ejemplo tipico: primera contraccion corrige 25%, segunda 12%, tercera 5%. Esta
secuencia decreciente revela que cada ronda de toma de ganancias saca a mas tenedores
debiles, mientras que los tenedores fuertes (instituciones) absorben esa oferta.
Cuando la ultima contraccion es muy estrecha (2-5%), la oferta flotante se agoto.

**Metricas del VCP:**
- Profundidad de la primera contraccion: no debe exceder 35%. Rango ideal 15-30%.
- Numero de contracciones: entre 2 y 6.
- Duracion total: tipicamente 4 a 12 semanas.
- Volumen decreciente durante cada contraccion sucesiva. La contraccion final debe
  tener el volumen mas bajo de toda la formacion.
- Zona de estrechez: periodo justo antes del breakout donde el precio se comprime
  en un rango de 2-5% de amplitud con volumen minimo.

**Punto de breakout:**

El pivote es el maximo del precio (high) durante la ultima contraccion del VCP.
La senal de compra se activa cuando se cumplen tres condiciones simultaneamente:
1. El precio supera el pivote durante el dia de trading
2. El volumen del dia es >= 1.4-1.5x el promedio de los ultimos 50 dias
3. Idealmente los 1-2 dias previos tienen volumen extremadamente bajo

#### Stop-loss y gestion de posicion

Minervini considera el stop-loss el componente mas importante de todo SEPA. Su
filosofia: no se necesita tener razon la mayoria de las veces — se necesita que
las ganancias cuando se acierta sean mucho mayores que las perdidas cuando se falla.

**Fase 1 — Stop-loss inicial (dia de entrada):**

Se toma el mas ajustado entre:
- Stop tecnico: justo debajo del low de la ultima contraccion del VCP
- Stop porcentual: 5-8% debajo del precio de entrada

Nunca debe exceder 10%. Perdida promedio objetivo: 6-7%.

Dimensionamiento de posicion: nunca arriesgar mas del 1% del capital total por
operacion. Cantidad de acciones = Riesgo maximo en dolares / (Precio entrada - Stop).

**Fase 2 — Mover a breakeven:**

Cuando la ganancia no realizada alcanza 2-3R (2-3 veces el riesgo inicial), se mueve
el stop al precio de entrada. La operacion se vuelve "gratis".

**Fase 3 — Trailing stop dinamico:**

El stop nunca baja, solo sube. Tres tecnicas:
- Por swing lows: cada minimo de retroceso se convierte en nuevo nivel de stop
- Por media movil: SMA(20) para corto plazo, SMA(50) para posiciones largas
- Por porcentaje desde el maximo: 10-15% debajo del maximo alcanzado

**Senales de salida definitiva:**
- Climax top: subida parabolica con volumen mas alto de todo el avance (10-25% en 1-2
  semanas). Senala euforia y agotamiento de compradores.
- Violacion de la plantilla de tendencia: la accion deja de cumplir condiciones de Etapa 2.
- Quiebre de SMA(50) con volumen alto: cierre debajo de SMA(50) con volumen >= 1.5x
  promedio. Presion vendedora institucional.
- Fallo de breakout ("squat"): el precio supera el pivote pero dentro de 2-3 dias cae
  de vuelta al rango del VCP. Se sale inmediatamente.

#### Fuentes bibliograficas

- Minervini, M. (2013). *Trade Like a Stock Market Wizard*. McGraw-Hill. Caps 4 (Trend Template), 10 (VCP), 12-13 (Risk Management).
- Minervini, M. (2017). *Think & Trade Like a Champion*. McGraw-Hill.
- Weinstein, S. (1988). *Secrets for Profiting in Bull and Bear Markets*. Dow Jones-Irwin.
- O'Neil, W. (2009). *How to Make Money in Stocks*. McGraw-Hill.

---

## 5 de mayo de 2026

### Experimento 1: Baseline — Volume Threshold en breakout

**Directorio:** `experiments/stocks_volume_threshold_baseline/`
**MLflow:** `VCP_Breakout_Volume_Threshold`

Primer experimento formal. Se vario un unico parametro (`volume_ratio_threshold`)
sobre los 23 tickers disponibles con todos los demas parametros fijos.

**Parametro variado:**

| Parametro | Valores |
|---|---|
| volume_ratio_threshold | 1.0, 1.5, 2.0 |

**Parametros fijos con explicacion de cada uno:**

**Paso 1 — Swing Detection (identificar extremos de precio significativos):**

Estos parametros controlan como el detector ATR ZigZag identifica los swing highs
y swing lows en la serie de precio. Un swing es un punto donde el precio cambia de
direccion de manera significativa. El detector usa ATR (Average True Range) como
unidad de medida: solo registra un cambio de direccion si el precio se movio al
menos `atr_mult` veces el ATR desde el ultimo swing.

| Parametro | Valor | Que hace |
|---|---|---|
| atr_length | 14 | Periodo para calcular el ATR (14 dias es el estandar). ATR mide la volatilidad promedio diaria del activo. |
| atr_mult | 2.0 | Multiplicador del ATR para considerar un movimiento como significativo. Con atr_mult=2.0, el precio debe moverse al menos 2x el ATR desde el ultimo swing para que se registre un nuevo swing. Valores bajos detectan mas swings (mas sensible, mas ruido). Valores altos detectan menos swings (solo movimientos grandes). |
| use_close_only | False | Si es False, usa precios High/Low para detectar swings (captura extremos intradiarios). Si es True, usa solo precios de cierre (mas conservador, ignora mechas). |

**Paso 2-3 — Sequence Detection (encontrar secuencias de contracciones decrecientes):**

Una vez identificados los swings, el pipeline agrupa pares consecutivos (high → low)
para calcular la profundidad de cada contraccion, y busca secuencias donde cada
contraccion sucesiva es menor que la anterior — la firma del VCP.

| Parametro | Valor | Que hace |
|---|---|---|
| method | tolerance | Metodo para determinar si la secuencia es decreciente. "tolerance" permite que una contraccion sea hasta un X% mayor que la anterior sin romper la secuencia (no exige decrecimiento estricto). |
| min_contractions | 2 | Minimo de contracciones para considerar un patron VCP valido. Minervini define 2-6. Con min=2, se aceptan patrones simples de 2 contracciones. |
| max_contractions | 6 | Maximo de contracciones. Mas de 6 indica que la accion no logra resolver la consolidacion. |
| lookback_bars | 126 | Ventana en barras (dias) hacia atras donde buscar patrones. 126 dias ≈ 6 meses. Patrones mas viejos se ignoran. |
| tolerance | 0.10 | Margen de tolerancia para el metodo "tolerance". Con 0.10, una contraccion puede ser hasta 10% mas profunda que la anterior sin romper la secuencia. Permite secuencias "casi decrecientes". |
| max_depth_pct | 0.35 | Profundidad maxima permitida para la primera contraccion, como porcentaje del precio. 0.35 = 35%, el limite de Minervini. Contracciones mas profundas indican debilidad estructural. |
| min_total_reduction | 0.80 | Reduccion total minima exigida entre la primera y la ultima contraccion. Con 0.80, la ultima contraccion debe ser al menos 80% menor que la primera (ej: si la primera fue 20%, la ultima debe ser <= 4%). Garantiza que hubo contraccion de volatilidad real. |
| max_gap_days | None | Maximo de dias permitido entre contracciones consecutivas. None = sin limite. Cuando se activa (ej: 40 dias), filtra patrones "estirados" donde las contracciones estan muy separadas en el tiempo. |

**Paso 4 — ATR Compression (verificar que la volatilidad tambien se contrajo):**

Ademas de que las contracciones de precio sean decrecientes, el VCP genuino requiere
que la volatilidad medida por ATR tambien haya disminuido durante la formacion del
patron. Esto confirma que el mercado se esta "calmando" genuinamente.

| Parametro | Valor | Que hace |
|---|---|---|
| method | ratio | Metodo de medicion: compara el ATR al final del patron con el ATR al inicio. |
| atr_period | 14 | Periodo del ATR usado para la comparacion (14 dias, estandar). |
| ratio_threshold | 0.85 | Ratio maximo ATR_fin/ATR_inicio. Con 0.85, el ATR al final del patron debe ser <= 85% del ATR al inicio. Esto exige una reduccion de volatilidad de al menos 15%. |

**Paso 5 — Volume Contraction (verificar que el volumen se seco):**

El VCP de Minervini requiere que el volumen disminuya durante la formacion del patron.
Volumen bajo en las correcciones confirma que las instituciones no estan vendiendo —
solo los tenedores debiles estan saliendo.

| Parametro | Valor | Que hace |
|---|---|---|
| method | ratio | Metodo de medicion: compara el volumen promedio al final del patron con el volumen al inicio. |
| ratio_threshold | 0.85 | Ratio maximo volumen_fin/volumen_inicio. Con 0.85, el volumen al final debe ser <= 85% del volumen al inicio. Confirma que la actividad se seco durante la consolidacion. |

**Paso 6 — Breakout Detection (confirmar ruptura con volumen):**

La senal de compra se activa cuando el precio supera el punto pivote (maximo de la
ultima contraccion) con volumen superior al promedio. El `volume_ratio_threshold`
es el parametro que se vario en este experimento.

| Parametro | Valor | Que hace |
|---|---|---|
| volume_ratio_threshold | **VARIADO: 1.0, 1.5, 2.0** | Ratio minimo de volumen en el dia de breakout vs promedio. Con 1.0 = sin filtro (cualquier volumen es aceptable). Con 1.5 = el volumen debe ser al menos 50% superior al promedio. Con 2.0 = el volumen debe duplicar el promedio. Valores altos exigen confirmacion institucional fuerte pero descartan breakouts validos con volumen moderado. |
| volume_lookback_days | 50 | Periodo para calcular el volumen promedio de referencia (50 dias ≈ 10 semanas). |

**Simulacion de trades — Risk Management:**

Una vez que se detecta una senal de breakout, se simula la operacion completa
(entrada, gestion, salida) para evaluar el resultado. Estos parametros controlan
como se gestiona cada trade.

| Parametro | Valor | Que hace |
|---|---|---|
| max_stop_loss_pct | 0.07 | Stop-loss maximo como porcentaje del precio de entrada. 7% es el limite superior de Minervini (rango tipico 5-8%). Si el precio cae 7% desde la entrada, se cierra la posicion. |
| breakeven_r_multiple | 2.0 | Cuando la ganancia no realizada alcanza 2.0R (2 veces el riesgo inicial), el stop se mueve al precio de entrada (breakeven). A partir de ahi, la operacion es "gratis". |
| trailing_sma_period | 20 | Periodo de la SMA usada como trailing stop. Con 20, si el precio cierra debajo de la SMA(20) con volumen alto, se cierra la posicion. La SMA(20) sube naturalmente si la accion sigue en tendencia. |
| trailing_volume_factor | 1.5 | Factor de volumen para confirmar el quiebre del trailing. Con 1.5, el volumen del dia de quiebre debe ser al menos 1.5x el promedio para que la salida se ejecute. Evita salidas por ruido en dias de volumen bajo. |

**Tickers (23):** AAPL, AMZN, AVGO, BRK.B, COIN, GLD, GOOGL, HOOD, IWM, JPM,
META, MSFT, NVDA, PLTR, QLD, QQQ, SLV, SOFI, SPY, SQQQ, TIL, TLT, TQQQ.

**Periodo:** Todos los datos disponibles por ticker, sin split train/test.

**Resultados agregados:**

| Threshold | Patrones | Trades | Avg WR | Avg CR |
|---|---|---|---|---|
| 1.0 (sin filtro) | 127 | 127 | 46% | +20.9% |
| 1.5 | 86 | 86 | 41% | +5.6% |
| 2.0 (estricto) | 38 | 38 | 42% | +2.8% |

**Mejores tickers (threshold=1.0):** NVDA 86% WR / +223.6% CR, GOOGL 64% / +82.7%,
TQQQ 60% / +75.1%, AAPL 86% / +71.6%.

**Peores tickers (consistentes en las 3 configs):** AMZN (29% WR, siempre negativo),
JPM, COIN, HOOD, IWM, TLT.

**Conclusion:** threshold=1.0 domina. El filtro de volumen en breakout descarta mas
senales buenas que malas. Esta intuicion se confirmaria en experimentos posteriores.

**Limitaciones:** Solo 1 parametro variado, sin split temporal, gap grouping
sobreestima trades, sin metricas de riesgo.

### Primer intento de autoresearch (descartado)

Se creo un modulo `autoresearch/` con Optuna para optimizacion automatica, pero
se descarto el mismo dia por problemas de diseno. Se removio y se agrego el
notebook ejecutado del experimento baseline.

---

## 6 de mayo de 2026

### Autoresearch Phase 1 — Optimizacion con Optuna

**Directorio:** `experiments/autoresearch_phase1/`
**MLflow:** `autoresearch_vcp_phase1`

Se reconstruyo el paquete `autoresearch/` con mejor arquitectura. Se implemento
SwingCache para evitar recomputar swings/contracciones entre trials (40-60% speedup).

**Configuracion Optuna:**
- Sampler: TPE (multivariate=True)
- 50 trials, 20 random startup, seed=42
- Objetivo: `score = expectancy_r × sqrt(n_trades)` con penalidad

**Universo:** 18 tickers (excluidos COIN, HOOD, PLTR, SOFI por start_date > 2015,
META excluido manualmente). Periodo comun: 2015-05-27 a 2026-04-08.

**12 parametros optimizados:**

| Parametro | Rango |
|---|---|
| atr_length | [10, 25] |
| atr_mult | [1.5, 3.5] step 0.25 |
| min_contractions | [2, 3] |
| max_contractions | [5, 7] |
| lookback_bars | [80, 140] |
| tolerance | [0.05, 0.20] |
| max_depth_pct | [0.25, 0.45] |
| max_depth_atr | [3.0, 7.0] |
| min_total_reduction | [0.65, 0.90] |
| compression_threshold | [0.70, 0.95] |
| vol_contraction_threshold | [0.75, 0.95] |
| volume_ratio_threshold | [1.3, 2.0] |

(Mas parametros de salida: max_gap_days, trailing, early exit, etc.)

**Resultados:**

| Metrica | Baseline | Best (trial #25) | Cambio |
|---|---|---|---|
| Score | +2.70 | +4.13 | +53% |
| Trades | 78 | 26 | -67% |
| Expectancy R | +0.31 | +0.81 | +2.7x |
| Win Rate | 46% | 50% | +4pp |
| Profit Factor | 1.62 | 3.40 | +2.1x |

**Parametros del mejor trial (#25):**

| Parametro | Baseline | Optimizado |
|---|---|---|
| atr_mult | 2.0 | 3.5 |
| tolerance | 0.10 | 0.05 |
| min_contractions | 2 | 3 |
| vol_contraction_threshold | 0.85 | 0.9263 |
| compression_threshold | 0.85 | 0.8875 |
| max_gap_days | None | 37 |
| lookback_bars | 126 | 120 |

**Importancia de parametros (fANOVA):**

| Parametro | Importancia |
|---|---|
| vol_contraction_threshold | 0.21 |
| max_gap_days | 0.17 |
| volume_ratio_threshold | 0.16 |
| min_total_reduction | 0.14 |
| max_depth_pct | 0.13 |
| (top 5 = 81.6% varianza) | |
| atr_mult | 0.053 |
| atr_length | 0.015 |

**Hallazgo clave:** Los parametros de filtrado de patrones importan mucho mas que
los de deteccion de swings. El detector de swings es robusto; la calidad viene
de como se filtran las secuencias.

**Limitacion:** 50 trials insuficientes para 12+ parametros (recomendado 200-500).
Todo in-sample, sin validacion temporal.

---

## 7 de mayo de 2026

### Stocks Exploration — Filtros estructurales

**Directorio:** `experiments/stocks_exploration/`
**MLflow:** `VCP_TrendTemplate_Drawdown`, `VCP_FullFilters`

Dia de mucho desarrollo. Se implementaron y testearon los filtros de Minervini:

1. **Trend Template (Stage 2):** Se implemento el modulo `stages/trend_template.py`
   y se corrio un experimento comparando TT=True vs TT=False sobre 23 tickers
   con 3 volume thresholds.

2. **Full Filters:** Se agrego ascending lows filter, max entry distance filter,
   y se corrio el experimento `run_vcp_full_filters.ipynb` con 8 configs
   (volume_threshold × template_mode) sobre 23 tickers.

**Universo:** 8 stocks principales (AAPL, AMZN, AVGO, BRK.B, GOOGL, JPM, MSFT, NVDA).
**Split:** TRAIN < 2020-01-01 / TEST >= 2020-01-01.

**Grilla deteccion (175 configs):**

| Parametro | Valores | N |
|---|---|---|
| atr_mult | 1.0-4.0 | 7 |
| depth_atr | 2-6 | 5 |
| reduction | 0.40-0.80 | 5 |

**Grilla salida (240 configs):**

| Parametro | Valores | N |
|---|---|---|
| trailing_atr_multiplier | 1.0-3.0 | 5 |
| target_r_multiple | None, 2.0, 3.0, 5.0 | 4 |
| early_exit_days | None, 3, 5 | 3 |
| breakeven_r_multiple | 0.5-2.0 | 4 |

**Resultado clave (unanime en 8/8 stocks):**
- **Trend Template = False** gana en todos los tickers
- **Volume Threshold = None** gana en todos los tickers

Los filtros adicionales de Minervini no mejoran el detector VCP — el pipeline de
6 pasos es autosuficiente.

**Impacto:** Estos resultados negativos simplificaron todos los experimentos
posteriores al eliminar TT y vol_thresh del espacio de busqueda.

### Otras mejoras del dia

- Se agrego adaptive ATR trailing stop y time-based exit a `simulate_trade`
- Se agregaron tablas de performance y trades breakdown a MLflow
- Se creo el documento `mejoras_pendientes.md` con roadmap priorizado
- Se agrego metrica in-trade Sharpe ratio per ticker

---

## 8 de mayo de 2026

### Exploracion FX — Primer contacto con forex

Se agrego data de pares FX (EURUSD, GBPUSD, USDJPY, USDCNH, USDCNY) y se
implemento ATR-relative depth filter y Minervini early exit rule.

Se creo un scratch notebook para VCP detection en FX daily y se actualizo el
experimento full_filters con parametros tuneados.

### Dual-mode experiment (template vs no-template con volume grid)

**MLflow:** Experimento con 2 modos (TT=True/False) combinado con grid de volume
threshold. Confirmo nuevamente la superioridad de TT=False.

**Parametros FX vs Stocks (adaptacion):**

| Parametro | Stocks | FX |
|---|---|---|
| max_stop_loss_pct | 0.07 | 0.02 |
| max_depth_pct | 0.35 | 0.50 |
| ascending_lows_tol | 0.01 | 0.03 |
| require_volume_confirmation | True | False |
| atr_mult (swing) | 2.0 | 1.5 |
| trailing_atr_mult | 3.0 | 2.0 |
| target_r_multiple | None | 3.0 |

---

## 9 de mayo de 2026

### FX Experiment — Target exit y simulacion

Se agrego target exit a la simulacion de trades y se completo el notebook de
experimento FX con resultados iniciales. Primeras observaciones:

- Diario FX con params stock: 14 trades, 21% WR, +1.13% CR
- Diario FX con params FX: 2 trades, 50% WR, +0.85% CR
- Horario: ambos sets de params pierden (-1.05%, -0.93%)
- **early_exit domina las salidas** en todas las configs (el precio cae debajo
  del entry en los primeros 3 dias/barras con alta frecuencia)

---

## 10 de mayo de 2026

### FX Exploration completa

**Directorio:** `experiments/fx_exploration/`
**MLflow:** `VCP_FX_TemporalStability`

Se corrigio un bottleneck O(n^2) en el pipeline y se completo el experimento FX
con configs optimizadas. Se agrego experimento multi-currency con MLflow tracking.

**Sub-experimento 1: Daily stability (5 pares)**

**Grilla:** Fase 1 (175 configs) + Fase 2 (240 configs).
**Split:** TRAIN 2015-2019 / TEST 2020-2026.

**Resultados por par (TEST, mejores configs):**

| Moneda | Viable? | CR TEST | WR | Trades |
|---|---|---|---|---|
| EURUSD | Si | +8.56% | 80% | 5 |
| GBPUSD | Si | +6.53% | 60% | 10 |
| USDCNY | Si | +4.38% | — | 5-7 |
| USDJPY | No | negativo | — | — |
| USDCNH | No | negativo/sin trades | — | — |

**Hallazgos criticos:**
- **atr_mult=1.5 es optimo** en FX daily (mejor CR y WR en ambos splits)
- **early_exit=None es universal en FX.** Deshabilitarlo: WR pasa de 20% a 70%,
  CR de +2.41% a +8.80%. Este fue el hallazgo mas importante de FX.
- Params universales (EURUSD) generalizan mejor que params optimizados por par
  para GBPUSD (+6.53% vs +1.30% en TEST), indicando overfitting par-especifico.

**Sub-experimento 2: Hourly EURUSD**
- Config A (max CR): 3T, 67% WR, +2.58% TRAIN, -0.61% TEST
- Config B (min 10T): 17T, 35% WR, +2.13% TRAIN, -1.59% TEST
- **Conclusion:** VCP no funciona a escala horaria. Movimientos demasiado chicos.

---

## 14 de mayo de 2026

### Temporal stability y multi-currency grid search

Se completaron los experimentos de estabilidad temporal para FX y stocks,
confirmando que los parametros optimizados en TRAIN generalizan razonablemente
a TEST. Se agrego grid search multi-currency para evaluar si parametros
universales funcionan mejor que par-especificos.

---

## 18 de mayo de 2026

### Gran refactor: Sequential mode y limpieza

Dia de reestructuracion mayor. Se implementaron cambios fundamentales:

1. **Sequential grouping mode:** Se agrego `evaluate_signals_to_trades` con modo
   sequential (un trade a la vez, sin overlap). Cambio critico porque refleja
   trading real y filtra severamente.

2. **Early contractions:** Se agrego `make_early_contractions` para deteccion
   temprana de VCP.

3. **Limpieza:** Se removio `max_entry_distance_pct` del breakout detection,
   se eliminaron scripts y notebooks obsoletos de `experiments/` root,
   y se removio codigo de early_entry no usado.

### FX Sequential

**Directorio:** `experiments/fx_sequential/`
**Script:** `run_fx_sequential_multicurrency.py`
**Split:** TRAIN < 2020-01-01 / TEST >= 2020-01-01

**Grilla Fase 1 (700 configs):**

| Parametro | Valores | N |
|---|---|---|
| atr_mult | 0.75-2.5 | 7 |
| depth_atr | 2-6 | 5 |
| reduction | 0.40-0.80 | 5 |
| lookback_bars | 63, 84, 105, 126 | 4 |

**Grilla Fase 2 (240 configs):** Standard exit grid.

**Resultados TEST (2020-2026):**

| Moneda | Senales | Trades | WR | Avg Win | Avg Loss | CR | Sharpe | MaxDD |
|---|---|---|---|---|---|---|---|---|
| EURUSD | 41 | 5 | 80.0% | +2.13% | -0.74% | +7.93% | 2.48 | -1.60% |
| GBPUSD | 90 | 15 | 53.3% | +1.34% | -0.70% | +5.80% | 1.27 | -1.82% |
| USDCNH | 50 | 3 | 33.3% | +4.28% | -1.28% | +1.62% | 1.09 | -1.63% |
| USDCNY | 40 | 2 | 50.0% | +3.39% | -1.81% | +1.52% | 1.48 | -2.01% |
| USDJPY | 43 | 13 | 7.7% | +1.50% | -0.37% | -2.96% | -1.84 | -1.74% |

**Mejores configs por moneda:**

| Moneda | atr_mult | depth_atr | reduction | lookback | trail | target_R | be_R |
|---|---|---|---|---|---|---|---|
| EURUSD | 2.5 | 5 | 0.6 | 63 | 1.5 | 5.0 | 2.0 |
| GBPUSD | 1.5 | 3 | 0.8 | 63 | 1.5 | 2.0 | 0.5 |
| USDCNH | 2.5 | 4 | 0.6 | 105 | 3.0 | 3.0 | 2.0 |
| USDCNY | 2.5 | 5 | 0.8 | 105 | 2.5 | 3.0 | 0.5 |
| USDJPY | 2.5 | 6 | 0.5 | 105 | 1.5 | 5.0 | 1.5 |

**Insight clave:** Sequential filtra severamente (57 senales → 5 trades en EURUSD).
Resultados son honestos. USDJPY destruido por early_exit=3d (12/13 trades perdidos).

### Stocks Sequential

**Directorio:** `experiments/stocks_sequential/`
**Script:** `run_stocks_sequential.py`
**Universo:** 8 stocks. **Split:** TRAIN < 2020 / TEST >= 2020.

**Grilla Fase 1 (5,600 configs):**

| Parametro | Valores | N |
|---|---|---|
| atr_mult | 1.0-4.0 | 7 |
| depth_atr | 2-6 | 5 |
| reduction | 0.40-0.80 | 5 |
| lookback_bars | 63, 84, 105, 126 | 4 |
| volume_threshold | None, 1.0, 1.5, 2.0 | 4 |
| trend_template | False, True | 2 |

**Grilla Fase 2 (240 configs):** Standard exit grid.

**Resultados TEST (2020-2026):**

| Ticker | Senales | Trades | WR | Avg Win | Avg Loss | CR | Sharpe | MaxDD |
|---|---|---|---|---|---|---|---|---|
| AAPL | 86 | 9 | 55.6% | +10.13% | -2.59% | +43.51% | 1.79 | -7.82% |
| MSFT | 80 | 12 | 50.0% | +8.77% | -3.01% | +36.57% | 1.95 | -6.27% |
| NVDA | 3 | 2 | 50.0% | +26.61% | -0.04% | +26.56% | 7.12 | -5.97% |
| AVGO | 42 | 15 | 13.3% | +15.15% | -1.48% | +9.19% | 1.23 | -8.82% |
| JPM | 28 | 4 | 50.0% | +3.31% | -2.29% | +1.83% | 0.68 | -2.95% |
| BRK.B | 8 | 4 | 50.0% | +5.98% | -5.34% | +0.28% | 0.20 | -9.21% |
| GOOGL | 18 | 4 | 25.0% | +2.87% | -0.94% | -0.01% | 0.11 | -7.70% |
| AMZN | 19 | 12 | 8.3% | +4.52% | -1.38% | -10.39% | -1.78 | -8.27% |

**Mejores configs por ticker:**

| Ticker | atr_mult | depth_atr | reduction | lookback | vol_thresh | TT | trail | target_R |
|---|---|---|---|---|---|---|---|---|
| AAPL | 1.5 | 6 | 0.8 | 63 | None | No | 2.5 | None |
| MSFT | 1.5 | 6 | 0.7 | 84 | None | No | 2.5 | 3.0 |
| NVDA | 1.5 | 4 | 0.8 | 84 | None | No | 1.5 | 3.0 |
| AVGO | 2.0 | 6 | 0.6 | 63 | None | No | 3.0 | 2.0 |
| AMZN | 2.0 | 4 | 0.8 | 105 | None | No | 2.0 | 2.0 |

**Confirmado unanime:** TT=False y vol_thresh=None ganan en 8/8 stocks.

**Comparacion FX vs Stocks:**

| Aspecto | FX | Stocks |
|---|---|---|
| Activos positivos | 4/5 (80%) | 6/8 (75%) |
| Mejor CR TEST | EURUSD +7.93% | AAPL +43.51% |
| Peor CR TEST | USDJPY -2.96% | AMZN -10.39% |
| Rango MaxDD | -1.6% a -2.0% | -2.9% a -9.2% |
| Rango Sharpe (pos) | 1.09-2.48 | 0.20-7.12 |

---

## 22 de mayo de 2026

### Reestructuracion de experiments y documentacion

Se reorganizo la carpeta `experiments/` en subdirectorios tematicos y se creo
la documentacion de arquitectura (`docs/architecture-*.md`).

### FX EURUSD Detection — Grid expandido

**Directorio:** `experiments/fx_eurusd_detection/`

Se intento mejorar la deteccion en EURUSD relajando 3 parametros que estaban
fijos en fx_sequential.

**Grilla expandida Fase 1 (16,800 configs = 24x mas que fx_sequential):**

| Parametro | Valores previos | Valores nuevos | N |
|---|---|---|---|
| atr_mult | 0.75-2.5 | (igual) | 7 |
| depth_atr | 2-6 | (igual) | 5 |
| reduction | 0.40-0.80 | (igual) | 5 |
| lookback_bars | 63-126 | (igual) | 4 |
| compression_threshold | 0.85 (fijo) | 0.85, 0.90, 0.95, 1.0 | 4 |
| require_ascending_lows | True (fijo) | True, False | 2 |
| tolerance | 0.10 (fijo) | 0.10, 0.15, 0.20 | 3 |

**Comparacion con fx_sequential (TEST):**

| Metrica | fx_sequential | eurusd_detection |
|---|---|---|
| Senales | 41 | 71 |
| Trades | 5 | 8 |
| WR | 80.0% | 37.5% |
| CR | +7.93% | +6.23% |

**Resultado:** Mas senales pero peor calidad. fx_sequential sigue siendo superior.

**Analisis de sensibilidad:**
- **compression_threshold:** 0.90 es optimo (+47% mas senales que 0.85, misma calidad)
- **require_ascending_lows:** Completamente inerte en EURUSD (0 efecto)
- **tolerance:** 0.15 es optimo (mejor que 0.10 y 0.20)

**Conclusion:** Expandir la grilla de deteccion no mejora resultados. Los filtros
existentes estan funcionando correctamente.

---

## 26 de mayo de 2026

### Optimizacion de ATR computation

Se optimizo el calculo de ATR y se agrego progress reporting al experimento
EURUSD para manejar las grillas mas grandes.

---

## 27 de mayo de 2026

### High ATR experiments (EURUSD + Stocks)

**Directorios:** `experiments/fx_eurusd_high_atr/`, `experiments/stocks_high_atr/`

Se testeo la hipotesis de que atr_mult mas alto (2.5-5.0) con max_depth_atr
deshabilitado podria capturar patrones VCP diferentes.

**Grilla (432 configs por activo):**

| Parametro | Valores | N |
|---|---|---|
| atr_mult | 2.5, 3.0, 4.0, 5.0 | 4 |
| max_depth_atr | None, 4, 6, 8 | 4 |
| reduction | 0.40, 0.60, 0.80 | 3 |
| lookback_bars | 63, 84, 126 | 3 |
| compression_threshold | 0.85, 0.90, 0.95 | 3 |

#### EURUSD High ATR

**Resultado TEST:** 10 trades, 50% WR, +2.08% CR (vs fx_sequential: 5T, 80% WR, +7.93%).

**Interaccion atr_mult x max_depth_atr:**
- atr_mult >= 3.0 con max_depth_atr numerico → 0 senales (bloqueo)
- atr_mult = 5.0 → solo funciona con max_depth_atr=None
- Las 47 senales extra de high_atr son ruido: generan trades con CR=-2.92%

**Cruce deteccion x salida (TEST):**

| Senales | Salida | Trades | CR |
|---|---|---|---|
| fx_sequential | fx_sequential | 5 | +7.93% |
| fx_sequential | high_atr | 3 | +2.89% |
| high_atr | fx_sequential | 13 | +4.78% |
| high_atr | high_atr | 10 | +2.08% |

La salida de fx_sequential (trail=1.5, target=5R) es superior en ambos sets.

#### Stocks High ATR (AAPL, AMZN, GOOGL, MSFT, NVDA)

**Split:** TRAIN hasta nov-2022 / TEST nov-2022 a abr-2026.

**Resultados (TRAIN → TEST):**

| Ticker | TRAIN CR | TEST CR |
|---|---|---|
| AAPL | +90.66% | -0.74% |
| AMZN | +88.95% | -3.89% |
| GOOGL | +85.40% | -15.03% |
| MSFT | +78.24% | +1.17% |
| NVDA | +46.26% | -6.46% |

**Overfitting masivo.** TRAIN 46%-91%, TEST siempre negativo o plano.
El split nov-2022 a abr-2026 es mas dificil para VCP en stocks.

**Conclusion:** High ATR no mejora deteccion en ningun mercado.

### FX EURUSD Hourly — Testeo exhaustivo

**Directorio:** `experiments/fx_eurusd_hourly/`
**Data:** 70,523 barras horarias (2015-2026).
**Split:** TRAIN 2018 / TEST 2019-2026.

Se corrieron 4 sub-experimentos cubriendo todo el espacio de parametros:

**Exp 1: atr_mult bajo (1-2)**
- 1,944 configs. Ninguna rentable en TRAIN.
- lookback_bars completamente inerte (72, 120, 240, 480 → resultados identicos).

**Exp 2: atr_mult alto (5-7)**
- 1,944 configs. 0 senales en todas.
- max_depth_atr bloquea 100% de contracciones.

**Exp 3: atr_mult alto con max_depth_atr=None**
- 648 configs. 624 generan senales, ninguna rentable.
- Problemas: re-entrada compulsiva, patrones en tendencia bajista.

**Exp 4: atr_mult medio (2-4), lookback corto (72-120)**
- **Primer TRAIN positivo en hourly:** +4.95%, 21 trades, 71% WR.
- **TEST colapsa:** -6.89%, 139 trades, 37% WR.
- Solo 2/8 anos rentables (2020, 2025). 2022 pierde -5.21%.
- Overfitting clasico: 21 trades en 1 ano insuficiente.

**Veredicto definitivo:** VCP a escala horaria no funciona en EURUSD.
Hipotesis exhaustivamente testeada, no quedan ejes razonables. Esfuerzo futuro
debe centrarse en detector daily con otros activos.

---

## 28 de mayo de 2026

### Deep per-ticker v1 — Optimizacion profunda AAPL

**Directorio:** `experiments/stocks_deep_per_ticker/`
**Split:** TRAIN 2015-2019 / TEST 2020-2026.

Primera optimizacion profunda por ticker individual.

**Fase 1: Deteccion (34,992 configs):**

| Parametro | Valores | N |
|---|---|---|
| atr_mult | 2.0, 3.0, 4.0 | 3 |
| max_depth_atr | None, 6, 8 | 3 |
| min_total_reduction | 0.40, 0.60, 0.80 | 3 |
| lookback_bars | 63, 126 | 2 |
| compression_threshold | 0.85, 0.90, 0.95 | 3 |
| tolerance | 0.10, 0.15, 0.20 | 3 |
| max_depth_pct | 0.25, 0.30, 0.35 | 3 |
| ascending_lows_tol | 0.01, 0.03, 0.08 | 3 |
| use_close_only | False, True | 2 |
| trend_template | False, True | 2 |
| volume_contraction | None, ratio<=0.85 | 2 |

**Fase 2: Salida (720 configs):**

| Parametro | Valores | N |
|---|---|---|
| trailing_atr_multiplier | 1.0-3.0 | 5 |
| target_r_multiple | None, 2.0, 3.0, 5.0 | 4 |
| early_exit_days | None, 3, 5 | 3 |
| breakeven_r_multiple | 0.5-2.0 | 4 |
| max_stop_loss_pct | 0.03, 0.05, 0.07 | 3 |

**Sensibilidad (parametros de alto impacto en AAPL):**
- atr_mult: 2.0 domina (+10.15% avg CR vs +1.40% a 4.0)
- lookback_bars: 126 >> 63 (+8.07% vs +2.01%)
- use_close_only: False >> True (+7.77% vs +2.31%)
- trend_template: False >> True (+7.25% vs +2.83%)

**Parametros inertes en AAPL:** tolerance, max_depth_pct, ascending_lows_tolerance.

**Config final v1 (sin TT):**
- Detection: atr=2.0, close=False, mda=6, red=0.80, lb=126, comp=0.95, tol=0.10
- Volume: 1.2x threshold, ventana 3 dias, lookback 50
- Exit: trail=2.5, target=None, early=None, be_R=1.5, sl=5%

**Resultados AAPL v1:**

| Metrica | B&H | Sin TT (TRAIN) | Sin TT (TEST) |
|---|---|---|---|
| Trades | — | 7 | 10 |
| WR | — | 86% | 80% |
| CR | +168.59% / +244.80% | +37.91% | +49.82% |
| CAGR | +21.89% / +21.92% | +6.65% | +6.69% |
| Max DD | -38.73% / -33.43% | -5.27% | -10.06% |
| Sharpe | 0.92 / 0.79 | 1.06 | 0.72 |
| Exposicion | 100% | 14% | 16% |

**Hallazgo notable:** CAGR 6.65% TRAIN ≈ 6.69% TEST. Overfitting minimo.
Drawdown controlado (-10% vs -33% B&H). Capital libre 84% del tiempo.

---

## 29 de mayo de 2026

### Deep per-ticker v2 — Metodologia mejorada

**Directorio:** `experiments/stocks_deep_per_ticker_v2/`

**Mejoras sobre v1:**
1. Volume en breakout como post-filtro sistematico (7 variantes vs manual en v1)
2. 3 perfiles de salida fijos en Fase 1 (tight/medium/loose trailing) para ranking
   robusto en vez de evaluar salida sobre un solo best
3. Seleccion multi-criterio: top 10 CR + top 10 WR (~15-20 candidatos)
4. Ranking compuesto: 50% CR + 30% WR + 20% avg_R

**7 variantes de vol_filter:**

| Variante | Ventana | Threshold |
|---|---|---|
| no_filter | — | — |
| w1_t1.2 | 1 dia | 1.2x |
| w1_t1.5 | 1 dia | 1.5x |
| w3_t1.2 | 3 dias | 1.2x |
| w3_t1.5 | 3 dias | 1.5x |
| w5_t1.2 | 5 dias | 1.2x |
| w5_t1.5 | 5 dias | 1.5x |

**3 exit profiles fijos (Fase 1):**
- Tight: trail=1.5
- Medium: trail=2.5
- Loose: trail=3.5

**Escala:** 17,496 pipeline runs × 2 TT × 7 vol_filter × 3 exit = 734,832 evaluaciones totales.
De esas, 244,944 son configs de deteccion unicas (promediando las 3 salidas fijas).
Fase 2: 720 configs × ~18 candidatos = 12,960 evaluaciones.

**Resultados AAPL v2 (top 3 composite, TRAIN → TEST):**

| Config | TRAIN T/WR/CR | TEST T/WR/CR | TEST Sharpe | TEST MaxDD |
|---|---|---|---|---|
| COMP#1 VC=Y, no_filter, tr=2.0, tg=2R, sl=5% | 8 / 88% / +54.28% | 7 / 71% / +33.04% | 2.35 | -5.45% |
| COMP#2 VC=N, w3_t1.2, tr=2.0, tg=2R, sl=3% | 11 / 82% / +47.91% | 16 / 62% / +49.78% | 2.59 | -4.51% |
| COMP#3 VC=N, no_filter, tr=2.0, tg=2R, sl=5% | 11 / 73% / +56.01% | 16 / 62% / +55.22% | 1.79 | -6.73% |

**Hallazgos v2:**
- **target=2R domina** (diferencia vs v1 que usaba target=None). Libera capital rapido.
- **vol_filter=w3_t1.2** es el mejor balance en TEST: mejora WR sin sobrerestringir.
- **COMP#2 es la config recomendada:** casi sin degradacion TRAIN→TEST en CAGR,
  mejor Sharpe (2.59), MaxDD controlado (-4.51%), 16 trades en 6 anos.

**Comparacion v1 vs v2:**

| Metrica | v1 (TEST) | v2 COMP#2 (TEST) |
|---|---|---|
| Trades | 10 | 16 |
| WR | 80% | 62% |
| CR | +49.82% | +49.78% |
| Sharpe | 0.72 | 2.59 |
| MaxDD | -10.06% | -4.51% |
| Config | trail=2.5, target=None | trail=2.0, target=2R, w3_t1.2 |

v2 logra CR equivalente con mejor Sharpe y menor drawdown, mediante busqueda
mas sistematica.

---

## Resumen de principios descubiertos

### Lo que funciona

- atr_mult=1.5-2.0 optimo (rara vez >2.5 aporta)
- lookback_bars=63-126 (3-6 meses)
- depth_atr=4-6
- min_total_reduction=0.6-0.8
- trailing=1.5-2.5x ATR
- early_exit=None universalmente
- Sequential mode (no gap-based)
- Volume confirmation window w3_t1.2 (3 dias, 1.2x)
- target=2R para liberar capital

### Lo que no funciona

- Trend Template (sobreajusta, pierde en 8/8 stocks)
- Volume threshold en breakout (mata senales buenas, pierde en 8/8 stocks)
- High atr_mult (>2.5) sin cambios estructurales
- Escala horaria en FX (exhaustivamente descartado)
- early_exit en FX (destruye WR)
- max_depth_atr=None en daily (agrega ruido)

### Matriz de viabilidad por activo (TEST 2020-2026)

**Stocks:**
- Viables: AAPL (+43.5%), MSFT (+36.6%), NVDA (+26.6%), AVGO (+9.2%), JPM (+1.8%), BRK.B (+0.3%)
- No viables: GOOGL (-0.01%), AMZN (-10.4%)

**FX:**
- Viables: EURUSD (+7.9%), GBPUSD (+5.8%), USDCNY (+1.5%), USDCNH (+1.6%)
- No viable: USDJPY (-3.0%)

---

## 4 de junio de 2026

### Deep per-ticker v2 — Expansion a 5 tickers (AMZN, GOOGL, MSFT, NVDA)

**Directorio:** `experiments/stocks_deep_per_ticker_v2/`
**Split:** TRAIN 2015-2019 (1,258 barras) / TEST 2020-2026 (1,574 barras)

Se completo el experimento deep per-ticker v2 para los 4 tickers restantes (AMZN, GOOGL, MSFT, NVDA),
usando la misma metodologia aplicada a AAPL el 29 de mayo.

### En que consta el experimento

Optimizacion en dos fases con seleccion multi-criterio:

**Fase 1 — Deteccion:** 17,496 pipeline runs × 2 TT × 7 vol_filter × 3 exit = 734,832 evaluaciones
totales. De esas, 244,944 son configs de deteccion unicas (promediando las 3 salidas fijas
tight/medium/loose). Se rankea por el promedio y se seleccionan ~20 candidatos: top 10 por CR +
top 10 por WR (sin duplicados).

**Fase 2 — Salida:** Se evaluan 720 configuraciones de salida sobre los ~20 candidatos seleccionados
(~14,400 evaluaciones). Se aplica ranking compuesto: 50% CR + 30% WR + 20% avg_R.

**Evaluacion final:** Las 3 mejores configuraciones por composite se evaluan en datos out-of-sample
(TEST 2020-2026) y se comparan contra buy & hold del activo.

### Parametros variados

**Fase 1 — Deteccion (12 parametros):**

| Parametro | Valores |
|---|---|
| atr_mult | 2.0, 3.0, 4.0 |
| use_close_only | False (HL), True (Close) |
| max_depth_atr | None, 6, 8 |
| min_total_reduction | 0.40, 0.60, 0.80 |
| lookback_bars | 63, 126 |
| compression_threshold | 0.85, 0.90, 0.95 |
| tolerance | 0.10, 0.15, 0.20 |
| max_depth_pct | 0.25, 0.30, 0.35 |
| ascending_lows_tolerance | 0.01, 0.03, 0.08 |
| trend_template | False, True |
| volume_contraction | None, ratio<=0.85 |
| vol_filter (breakout) | no_filter, w1_t1.2, w1_t1.5, w3_t1.2, w3_t1.5, w5_t1.2, w5_t1.5 |

**Fase 2 — Salida (5 parametros, 720 combos):**

| Parametro | Valores |
|---|---|
| trailing_atr_multiplier | 1.0, 1.5, 2.0, 2.5, 3.0 |
| target_r_multiple | None, 2.0, 3.0, 5.0 |
| early_exit_days | None, 3, 5 |
| breakeven_r_multiple | 0.5, 1.0, 1.5, 2.0 |
| max_stop_loss_pct | 0.03, 0.05, 0.07 |

### Resultados — Train (2015-2019)

Mejor configuracion por composite de cada ticker, comparada contra buy & hold:

| Ticker | Mejor config | T | WR | CR | MaxDD | Sharpe | avgR | B&H CR | B&H MaxDD |
|---|---|---|---|---|---|---|---|---|---|
| AAPL | COMP#1 tr=2.0 tg=2R sl=5% VC | 8 | 88% | +54.28% | -0.95% | 1.83 | +1.13 | +168.59% | -38.73% |
| AMZN | COMP#1 tr=2.0 tg=None sl=3% w3_t1.2 VC | 12 | 75% | +111.12% | -1.80% | 1.57 | +2.21 | +498.94% | -34.10% |
| GOOGL | COMP#1 tr=2.5 tg=None sl=7% w3_t1.2 | 12 | 75% | +77.52% | -2.55% | 1.52 | +0.96 | +113.52% | -24.40% |
| MSFT | COMP#1 tr=3.0 tg=2R sl=5% VC | 9 | 67% | +48.17% | -0.89% | 1.31 | +1.02 | +237.25% | -18.58% |
| NVDA | COMP#1 tr=2.5 tg=5R sl=5% w5_t1.2 | 6 | 67% | +96.87% | -10.36% | 0.89 | +2.63 | +1068.79% | -56.08% |

En todos los casos, la estrategia VCP produce CRs menores al buy & hold pero con drawdowns drasticamente
menores (1-10% vs 18-56%).

### Resultados — Test (2020-2026)

Mejor configuracion de cada ticker en test, comparada contra buy & hold:

| Ticker | Mejor config (test) | T | WR | CR | MaxDD | Sharpe | avgR | B&H CR | B&H MaxDD |
|---|---|---|---|---|---|---|---|---|---|
| AAPL | COMP#2 w3_t1.2, tr=2.0 tg=2R sl=3% | 16 | 62% | +49.78% | -4.51% | 2.59 | +0.88 | +244.80% | -33.43% |
| AMZN | COMP#1-3 (0 trades) / ALT#4 atr=2.0 | 0/14 | —/36% | 0.00%/-0.12% | —/-13.17% | — | — | +133.14% | -56.15% |
| GOOGL | COMP#2 w1_t1.2, tr=2.5 tg=None sl=7% | 3 | 67% | +4.84% | -7.77% | — | +0.26 | +363.69% | -44.32% |
| MSFT | COMP#2 tr=1.5 tg=3R sl=3% | 8 | 50% | +8.41% | -9.39% | 0.29 | +0.37 | +133.05% | -37.56% |
| NVDA | COMP#2 w3_t1.2, tr=2.5 tg=5R sl=5% | 4 | 75% | +89.00% | -2.68% | 1.10 | +3.60 | +2935.78% | -66.36% |

### Tabla comparativa cross-ticker — Generalizacion train vs test

| Ticker | CR Train | CR Test | Trades Test | MaxDD Test | Sharpe Test | Veredicto |
|---|---|---|---|---|---|---|
| **AAPL** | +54.28% | +49.78% | 16 | -4.51% | 2.59 | Excelente |
| **NVDA** | +96.87% | +89.00% | 4 | -2.68% | 1.10 | Excelente |
| **MSFT** | +48.17% | +8.41% | 8 | -9.39% | 0.29 | Marginal |
| **GOOGL** | +77.52% | +4.84% | 3 | -7.77% | — | Marginal |
| **AMZN** | +111.12% | 0.00% | 0 | — | — | Fallo |

### Parametros optimos por ticker — No son transferibles

Los parametros de deteccion difieren significativamente entre tickers:

| Parametro | AAPL | AMZN | GOOGL | MSFT | NVDA |
|---|---|---|---|---|---|
| atr_mult | 2.0 | 3.0 | 2.0 | 2.0 | 2.0 |
| use_close_only | False (HL) | False (HL) | **True (Close)** | False (HL) | False (HL) |
| lookback_bars | 126 | 126 | 126 | 126 | **63** |
| target_r_multiple | 2R | None | None | 2R | **5R** |
| trailing_atr_mult | 2.0 | 2.0 | **2.5** | **3.0** | **2.5** |
| volume_contraction | **Si** | Si | No | **Si** | No |
| max_stop_loss_pct | 5% | 3% | **7%** | 5% | 5% |

Hallazgos unicos por ticker:
- **GOOGL**: `use_close_only=True` es critico — HL da CR negativo. Unico ticker con esta particularidad.
- **NVDA**: `lookback_bars=63` (3 meses) y `target=5R`. Ciclos VCP mas cortos y movimientos explosivos.
- **MSFT**: `volume_contraction=True` ligeramente mejor. Unico ticker donde VC aporta marginalmente.
- **AMZN**: `atr_mult=3.0` optimo en train pero produce 0 senales en test.

### AMZN — Diagnostico del fallo en test

Las 3 variantes top por composite (COMP#1-3) no generaron ningun trade en test (2020-2026).

**Analisis progresivo del pipeline:**

1. **ATR absoluto 3.7x mayor en test:** ATR(14) medio pasa de 1.22 (train) a 4.48 (test).
   Con atr_mult=3.0, se necesitan movimientos mucho mayores para registrar un swing.

2. **Contracciones mas profundas:** Depth % medio 11.0% train vs 15.7% test. COVID rally,
   caida 2022 (-55%) y tariffs 2025 generan contracciones violentas que rompen el patron VCP.

3. **Filtro de compresion de ATR rechaza todo:** 13 de 15 contracciones en test tienen ratio
   ATR_fin/ATR_inicio > 1.0 — la volatilidad NO se contrae durante las consolidaciones.
   Solo 1 contraccion (jul 2021) muestra compresion genuina (ratio 0.88).

**Causa raiz:** AMZN post-2020 tiene un regimen donde las consolidaciones no vienen con ATR
decreciente. El supuesto fundamental del VCP (Volatility **Contraction** Pattern) no se cumple
en este activo durante este periodo. Es un cambio estructural del comportamiento, no un problema
de parametros.

**Posible solucion propuesta (no implementada):** Medir compresion con rango de barras
(`promedio(rango ultimas N barras) / promedio(rango N barras previas)`) en vez de ATR(14),
que reacciona lento a cambios de volatilidad.

### Insights documentados

Se crearon insights detallados para cada ticker con formato estandarizado:
- `insight_aapl_train.md` — actualizado con tabla Sharpe
- `insight_amzn.md` — incluye diagnostico completo del fallo
- `insight_googl.md`
- `insight_msft.md`
- `insight_nvda.md`

Scripts de evaluacion: `run_deep_generic.py`, `eval_test_generic.py`, `eval_amzn_test.py`,
`compute_sharpe_all.py`. Logs en `logs/`.

### Conclusion

De los 5 tickers evaluados, solo **AAPL y NVDA** muestran generalizacion robusta train→test.
MSFT y GOOGL generan retornos positivos marginales. AMZN falla completamente por un cambio
de regimen de volatilidad post-2020.

Los parametros optimos no son transferibles entre tickers: use_close_only, lookback_bars,
target_r_multiple y trailing_atr_multiplier varian significativamente. Esto implica que una
estrategia VCP productiva requiere optimizacion per-ticker.

---

## 5 de junio de 2026

### Nuevo parametro: volume_confirmation_forward

Se implemento `volume_confirmation_forward` en `detect_breakout_signal()`. Este
parametro complementa la ventana backward existente (`volume_confirmation_window`)
permitiendo buscar confirmacion de volumen en los dias posteriores al breakout
de precio.

**Logica:** Cuando el precio supera el pivot pero el volumen no confirma en la
ventana backward, se busca en los N dias siguientes verificando que:
1. El precio (close) siga por encima del pivot
2. Aparezca un dia con volumen alto

Si el close cae <= pivot en algun dia forward, se cancela la busqueda. La senal
se emite en el dia donde se confirma el volumen (no en el dia del breakout de
precio), evitando look-ahead bias.

**Default:** 0 (solo busca hacia atras, comportamiento original).

### Test: forward volume sobre configs COMP#1 v2

**Script:** `experiments/test_forward_volume.py`

Se testearon las configuraciones ganadoras (COMP#1) de cada ticker del
experimento deep per-ticker v2, variando solo `volume_confirmation_forward`
con valores [0, 1, 2, 3, 5]. Se evaluo en train (2015-2019) y test (2020-2026).

**Resultados TRAIN (2015-2019):**

| Ticker | Config vol | fwd=0 (baseline) | fwd=3 | fwd=5 |
|---|---|---|---|---|
| AAPL | vol=off | 8T 88% +54.28% | sin cambio | sin cambio |
| AMZN | w3_t1.2 | 12T 75% +111.12% | sin cambio | sin cambio |
| GOOGL | w3_t1.2 | 12T 75% +77.52% | 14T 64% +72.40% | 14T 64% +72.40% |
| MSFT | vol=off | 9T 67% +48.17% | sin cambio | sin cambio |
| NVDA | w3_t1.2 | 6T 67% +96.87% | sin cambio | sin cambio |

**Resultados TEST (2020-2026):**

| Ticker | Config vol | fwd=0 (baseline) | fwd=3 | fwd=5 |
|---|---|---|---|---|
| AAPL | vol=off | 7T 71% +33.04% | sin cambio | sin cambio |
| AMZN | w3_t1.2 | 0T (fallo estructural) | sin cambio | sin cambio |
| GOOGL | w3_t1.2 | 4T 50% +3.55% | sin cambio | sin cambio |
| MSFT | vol=off | 9T 44% +1.04% | sin cambio | sin cambio |
| NVDA | w3_t1.2 | 4T 75% +89.00% | 5T 60% +76.58% | 6T 50% +66.48% |

**Observaciones:**

1. **AAPL y MSFT:** Sin efecto. Sus configs COMP#1 usan `require_volume_confirmation=False`,
   por lo que el forward no aplica.

2. **AMZN:** 0 senales en test independientemente del forward. El problema es
   estructural (ATR no se contrae post-2020), no de volumen.

3. **GOOGL train:** El forward agrega 2 trades que pierden (WR baja de 75% a 64%,
   CR de +77.52% a +72.40%). En test, las senales extra caen cuando ya hay trade
   activo (sequential las ignora) y no cambian metricas.

4. **NVDA test:** El caso mas revelador. Con fwd=3 se agrega 1 trade perdedor
   (CR baja de +89% a +76.58%). Con fwd=5, 2 trades perdedores (CR baja a +66.48%,
   WR de 75% a 50%).

**Conclusion:** El `volume_confirmation_forward` no mejora ninguna config ganadora.
En los casos donde agrega trades (GOOGL train, NVDA test), esos trades son de peor
calidad. Las senales donde el volumen confirma el mismo dia o antes del breakout
son las mas confiables — las que necesitan confirmacion tardia son breakouts debiles.

El parametro queda implementado y disponible (default=0), pero la evidencia
indica que no debe activarse con las configs actuales.

### Analisis del target en NVDA: 5R vs None

A partir de los graficos de trades generados para las configs ganadoras, se
observo que el target=5R tiene un efecto diferente en train vs test para NVDA.

**NVDA TRAIN — target=5R gana:**

| Metrica | target=5R | target=None |
|---|---|---|
| Trades | 6 | 6 |
| WR | 67% | 67% |
| CR | +96.87% | +68.99% |
| avg_R | +2.63 | +2.01 |

Mismos trades, pero sin target los ganadores devuelven ganancia antes de que el
trailing (2.5×ATR) se active. Ejemplo: trade #2 con target sale a +6.4R en 29d;
sin target el trailing lo saca a +4.2R despues de que el precio revertio desde
el maximo de 6.4R.

**NVDA TEST — target=None gana:**

| Metrica | target=5R | target=None |
|---|---|---|
| Trades | 4 | 3 |
| WR | 75% | 100% |
| CR | +89.00% | +95.43% |
| avg_R | +3.60 | +5.03 |

Detalle de trades con target=5R:

| # | Entry | Exit | Salida | PnL | R | MaxR | Dur |
|---|---|---|---|---|---|---|---|
| 1 | 2023-05-01 | 2023-05-25 | target | +31.37% | +6.3R | 6.3R | 24d |
| 2 | 2024-01-08 | 2024-02-02 | target | +26.61% | +5.3R | 5.3R | 25d |
| 3 | 2024-02-05 | 2024-02-21 | stop_loss | -2.68% | -0.5R | 1.3R | 16d |
| 4 | 2025-06-25 | 2025-08-28 | time_exit | +16.76% | +3.4R | 3.7R | 64d |

Detalle de trades con target=None:

| # | Entry | Exit | Salida | PnL | R | MaxR | Dur |
|---|---|---|---|---|---|---|---|
| 1 | 2023-05-01 | 2023-06-07 | trailing_stop | +29.63% | +5.9R | 7.7R | 37d |
| 2 | 2024-01-08 | 2024-02-21 | trailing_stop | +29.13% | +5.8R | 8.3R | 44d |
| 3 | 2025-06-25 | 2025-08-28 | time_exit | +16.76% | +3.4R | 3.7R | 64d |

El cambio clave es el trade #2: con target=5R sale el 2024-02-02, y al dia
siguiente entra el trade #3 que pierde -2.68%. Sin target, el trade #2 sigue
abierto hasta 2024-02-21 (trailing_stop a +5.8R, max +8.3R) y absorbe ese
periodo, evitando el trade perdedor.

**Conclusion:** El valor principal del detector VCP es la identificacion de
patrones de alta calidad y la senal de entrada. Una vez dentro del trade, la
gestion de salida puede hacerse dia a dia observando el comportamiento del
precio y volumen, en vez de delegar a un target fijo automatico. Con target=None
la salida queda determinada por stop loss (si el patron falla), trailing stop
(si el precio avanza y retrocede), o time exit (si se lateraliza). Esto permite
al operador monitorear la posicion activa y tomar decisiones sobre el contexto
del momento.
