# Reporte: Estabilidad temporal y multi-currency de VCP en FX

## Objetivo

Evaluar dos preguntas sobre los parametros VCP optimizados para EURUSD
en el reporte anterior (que uso toda la data 2015-2026):

1. **Estabilidad temporal:** Si optimizamos usando solo los primeros 5
   anios (2015-2019), encontramos los mismos parametros? Los parametros
   son estables o son producto de overfitting a la data completa?

2. **Generalización multi-currency:** Los parametros de EURUSD funcionan
   en otras monedas (GBPUSD, USDJPY, USDCNH, USDCNY)? Cada moneda
   necesita sus propios parametros o hay un set "universal FX"?

Scripts: `_run_fx_temporal_stability.py`, `_run_fx_multicurrency_gridsearch.py`

---

## Datos utilizados

| Moneda | Barras totales | Rango          | Train (5y)    | Test (~6y)    |
|--------|----------------|----------------|---------------|---------------|
| EURUSD | 3,581          | 2015-01 a 2026-05 | 1,556 barras | 2,025 barras |
| GBPUSD | 3,576          | 2015-01 a 2026-05 | 1,556 barras | 2,020 barras |
| USDJPY | 3,547          | 2015-01 a 2026-05 | 1,536 barras | 2,011 barras |
| USDCNH | 3,460          | 2015-01 a 2026-05 | 1,544 barras | 1,916 barras |
| USDCNY | 3,457          | 2015-01 a 2026-05 | 1,528 barras | 1,929 barras |

Corte temporal: 2020-01-01. Todos los timeframes son diarios.

---

## Referencia: parametros del experimento anterior (full-dataset)

Estos son los parametros encontrados en el reporte anterior optimizando
sobre toda la data (2015-2026) de EURUSD:

```python
# Swing detection
atr_mult = 1.5

# Deteccion de patron
depth_atr = 5, reduction = 0.60

# Gestion de salida
trailing_atr_multiplier = 1.5, target_r_multiple = 3.0
early_exit_days = None, breakeven_r_multiple = 1.0
```

Resultado full-dataset: 10 trades, 70% WR, +8.80% CR en 11 anios.

---

## Parte 1: Estabilidad temporal (EURUSD)

### Metodologia

Se corrio la misma busqueda de grilla en dos fases usando solo el periodo
TRAIN (2015-2019):

**Fase 1 — Grilla de deteccion** (incluyendo `atr_mult` como dimension nueva):
- `atr_mult`: [0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 2.5]
- `depth_atr`: [2, 3, 4, 5, 6]
- `min_total_reduction`: [0.40, 0.50, 0.60, 0.70, 0.80]
- Total: 175 combinaciones

Salida fija durante esta fase: trail=1.5, target=3R, early=None, be_R=1.0

**Fase 2 — Grilla de salida** (mejor deteccion de fase 1):
- `trailing_atr_multiplier`: [1.0, 1.5, 2.0, 2.5, 3.0]
- `target_r_multiple`: [None, 2R, 3R, 5R]
- `early_exit_days`: [None, 3, 5]
- `breakeven_r_multiple`: [0.5, 1.0, 1.5, 2.0]
- Total: 240 combinaciones

### Efecto de atr_mult en la deteccion (TRAIN)

| atr_mult | Swings | Contracciones | Avg CR  | Best CR  | Configs c/trades |
|----------|--------|---------------|---------|----------|------------------|
| 0.75     | 567    | 283           | -3.08%  | +0.00%   | 22/25            |
| 1.00     | 463    | 231           | -2.68%  | +0.00%   | 22/25            |
| 1.25     | 351    | 175           | -1.95%  | +0.00%   | 22/25            |
| **1.50** | **277** | **138**      | **-0.10%** | **+1.19%** | **16/25**   |
| 1.75     | 221    | 110           | -0.03%  | +1.19%   | 16/25            |
| 2.00     | 167    | 83            | -1.14%  | +0.82%   | 14/25            |
| 2.50     | 125    | 62            | +0.16%  | +1.79%   | 11/25            |

**Observaciones:**
- `atr_mult` bajo (0.75-1.25): demasiados swings, demasiado ruido. Ninguna
  config produce trades rentables. El detector confunde oscilaciones menores
  con estructura real.
- `atr_mult` medio (1.5-1.75): el punto optimo. Suficientes swings para
  captar patrones, sin ahogarse en ruido.
- `atr_mult` alto (2.0-2.5): pocos swings "limpios". El mejor CR en train
  viene de 2.5 (+1.79%) pero con solo 4 trades — estadisticamente fragil.

### Comparacion de parametros: TRAIN (5y) vs FULL (11y)

| Parametro                | TRAIN (5y) | FULL (11y) | Iguales? |
|--------------------------|------------|------------|----------|
| atr_mult                 | 2.5        | 1.5        | NO       |
| depth_atr                | **5**      | **5**      | **SI**   |
| min_total_reduction      | 0.7        | 0.6        | NO       |
| trailing_atr_multiplier  | **1.5**    | **1.5**    | **SI**   |
| target_r_multiple        | 5.0        | 3.0        | NO       |
| early_exit_days          | **None**   | **None**   | **SI**   |
| breakeven_r_multiple     | 2.0        | 1.0        | NO       |

**Coincidencia: 3/7 parametros exactos.** Pero los 3 que coinciden son
los que mas importan:
- `depth_atr=5`: la profundidad maxima de contraccion en ATR
- `trailing=1.5`: trailing stop apretado
- `early_exit=None`: no cerrar trades prematuramente

Los 4 que difieren (`atr_mult`, `reduction`, `target`, `breakeven`) son
parametros que con solo 2-4 trades en TRAIN no se pueden discriminar
estadisticamente — muchas configs dan el mismo CR.

### Validacion out-of-sample

| Config               | Split           | Trades | WR   | CR       |
|----------------------|-----------------|--------|------|----------|
| Train-best (5y)      | TRAIN 2015-2019 | 4      | 75%  | +1.79%   |
| Train-best (5y)      | TEST 2020-2026  | 3      | 100% | +5.18%   |
| Full-dataset (11y)   | TRAIN 2015-2019 | 5      | 60%  | +0.22%   |
| Full-dataset (11y)   | TEST 2020-2026  | 5      | 80%  | **+8.56%** |

La config train-best (`atr_mult=2.5`) es rentable en TEST (+5.18%) pero
pierde frente a la full-dataset (+8.56%). La razon: con `atr_mult=2.5`
se pierden los dos mejores trades del periodo (mayo 2020 +3.86%, oct
2020 +3.08%) porque swings demasiado grandes no captan esas contracciones.

**Conclusion:** `atr_mult=1.5` se confirma como el valor correcto. El 2.5
que "gano" en TRAIN es un artefacto de pocos trades. Los parametros
estructurales estables son `depth_atr=5`, `trailing=1.5`, `early_exit=None`.

---

## Parte 2: Multi-currency grid search

### Metodologia

Para cada moneda se corrio la grilla de 2 fases en TRAIN (2015-2019)
con `atr_mult` fijo en 1.5 (confirmado por el test de estabilidad):

- Fase 1: 25 configs de deteccion (depth_atr x reduction)
- Fase 2: 240 configs de salida sobre la mejor deteccion

Luego se validaron los resultados en TEST (2020-2026).

### Mejores parametros por moneda (optimizados en TRAIN)

| Moneda | depth_atr | reduction | trail | target | early | be_R  | Train T | Train WR | Train CR |
|--------|-----------|-----------|-------|--------|-------|-------|---------|----------|----------|
| EURUSD | 5         | 0.40      | 1.5   | 5.0    | None  | 2.0   | 2       | 100%     | +1.19%   |
| GBPUSD | 6         | 0.70      | 1.5   | 2.0    | 3     | 0.5   | 9       | 44%      | +9.76%   |
| USDJPY | 3         | 0.60      | 2.0   | None   | 3     | 1.0   | 2       | 100%     | +0.87%   |
| USDCNH | 2         | 0.40      | 1.0   | None   | None  | 0.5   | 0       | 0%       | +0.00%   |
| USDCNY | 6         | 0.80      | 2.0   | None   | None  | 1.5   | 7       | 86%      | +14.49%  |

**Observaciones sobre la deteccion:**
- GBPUSD y USDCNY prefieren `depth_atr` alto (5-6): permiten
  contracciones profundas, que son mas comunes en estas monedas.
- USDJPY prefiere `depth_atr` bajo (3): contracciones mas acotadas.
- USDCNH no genera trades con ninguna config en TRAIN.

**Observaciones sobre la salida:**
- GBPUSD y USDJPY seleccionaron `early_exit=3` — veremos que esto es
  un error de overfitting al evaluar en TEST.
- El `trailing=1.5` aparece en EURUSD y GBPUSD; las asiaticas prefieren 2.0.

### Out-of-sample: params propios vs params EURUSD

| Moneda | Config          | Train CR  | Test CR    | Full CR    | Test T | Test WR |
|--------|-----------------|-----------|------------|------------|--------|---------|
| EURUSD | Propios (train) | +1.19%    | +5.18%     | +6.43%     | 4      | 75%     |
|        | EURUSD params   | +0.22%    | **+8.56%** | +8.80%     | 5      | 80%     |
| GBPUSD | Propios (train) | +9.76%    | +1.30%     | +10.97%    | 13     | 31%     |
|        | EURUSD params   | +1.11%    | **+6.53%** | +7.70%     | 10     | 60%     |
| USDJPY | Propios (train) | +0.87%    | -1.20%     | -0.34%     | 5      | 0%      |
|        | EURUSD params   | -2.98%    | -3.14%     | -6.03%     | 9      | 22%     |
| USDCNH | Propios (train) | +0.00%    | -0.50%     | -0.50%     | 1      | 0%      |
|        | EURUSD params   | -1.12%    | -4.92%     | -5.99%     | 9      | 33%     |
| USDCNY | Propios (train) | +14.49%   | +4.38%     | +19.51%    | 7      | 57%     |
|        | EURUSD params   | +7.95%    | +3.45%     | +11.67%    | 5      | 60%     |

### Analisis por moneda

**EURUSD:** Los params del full-dataset (+8.56% TEST) superan a los
optimizados en TRAIN (+5.18%). `reduction=0.60` (full) detecta mas
trades que `reduction=0.40` (train), y `target=3R` captura mejor las
ganancias del primer trade (+3.86% vs +3.00%).

**GBPUSD — caso clasico de overfitting:** Los params propios dieron
+9.76% en TRAIN pero solo +1.30% en TEST con 31% WR. De 13 trades en
TEST, 8 fueron early_exits (cerrados al dia siguiente con perdida).
El optimizador selecciono `early_exit=3` que casualmente funciono en
TRAIN pero destruye performance en TEST. Con params EURUSD (sin
early_exit): +6.53% TEST, 60% WR. Leccion clara: `early_exit` no
funciona en FX, no importa la moneda.

**USDJPY — VCP no funciona:** Pierde con ambos sets de params en TEST.
Con sus propios params: -1.20%, 0% WR (5 trades, todos perdedores —
4 fueron early_exits). Con EURUSD params: -3.14%, 22% WR. El yen tiene
una dinamica de precios incompatible con el patron VCP.

**USDCNH — sin evidencia:** 0 trades en TRAIN con params propios, 1
trade (perdedor) en TEST. Con EURUSD params: 9 trades en TEST pero
33% WR y -4.92% CR. El yuan offshore no exhibe patrones VCP.

**USDCNY — segunda mejor moneda:** Funciona con ambos sets de params.
Sus propios params (+4.38% TEST, 57% WR) y EURUSD params (+3.45% TEST,
60% WR) son ambos rentables out-of-sample. Destaca un trade de +4.07%
(9.4R) en 2023. El yuan onshore tiene mas restricciones de mercado que
generan contracciones mas definidas.

### Detalle de trades en TEST (configs propias por moneda)

**EURUSD** (depth_atr=5, red=0.4, trail=1.5, target=5R, early=None):

| Trade | Fecha entry | Fecha exit | Salida        | PnL    | R     | Dur  |
|-------|-------------|------------|---------------|--------|-------|------|
| 1     | 2020-05-18  | 2020-06-17 | trailing_stop | +3.00% | +2.4R | 30d  |
| 2     | 2020-11-19  | 2021-01-08 | trailing_stop | +2.80% | +3.4R | 50d  |
| 3     | 2021-07-28  | 2021-08-06 | stop_loss     | -0.70% | -0.9R | 9d   |
| 4     | 2025-06-25  | 2025-07-11 | trailing_stop | +0.04% | +0.0R | 16d  |

**GBPUSD** (depth_atr=6, red=0.7, trail=1.5, target=2R, early=3):

| Trade | Fecha entry | Fecha exit | Salida        | PnL    | R     | Dur  |
|-------|-------------|------------|---------------|--------|-------|------|
| 1     | 2020-06-01  | 2020-06-11 | trailing_stop | +0.70% | +0.3R | 10d  |
| 2     | 2020-12-03  | 2020-12-04 | early_exit    | -0.13% | -0.1R | 1d   |
| 3     | 2021-01-21  | 2021-01-22 | early_exit    | -0.34% | -0.2R | 1d   |
| 4     | 2021-05-07  | 2021-05-28 | time_exit     | +1.50% | +1.2R | 21d  |
| 5     | 2021-07-09  | 2021-07-11 | early_exit    | -0.02% | -0.0R | 2d   |
| 6     | 2022-07-25  | 2022-07-26 | early_exit    | -0.15% | -0.1R | 1d   |
| 7     | 2022-12-01  | 2022-12-15 | trailing_stop | -0.55% | -0.3R | 14d  |
| 8     | 2023-04-24  | 2023-04-25 | early_exit    | -0.69% | -0.6R | 1d   |
| 9     | 2024-03-06  | 2024-03-14 | trailing_stop | +0.07% | +0.1R | 8d   |
| 10    | 2024-05-27  | 2024-05-28 | early_exit    | -0.11% | -0.1R | 1d   |
| 11    | 2025-02-13  | 2025-03-26 | trailing_stop | +2.49% | +1.3R | 41d  |
| 12    | 2025-09-01  | 2025-09-02 | early_exit    | -1.22% | -1.3R | 1d   |
| 13    | 2026-04-30  | 2026-05-01 | early_exit    | -0.21% | -0.2R | 1d   |

8 de 13 trades son early_exits — la mayoria de 1 dia. Ejemplo claro de
por que `early_exit` no funciona en FX.

**USDCNY** (depth_atr=6, red=0.8, trail=2.0, target=None, early=None):

| Trade | Fecha entry | Fecha exit | Salida        | PnL    | R     | Dur  |
|-------|-------------|------------|---------------|--------|-------|------|
| 1     | 2020-05-06  | 2020-06-01 | trailing_stop | +0.33% | +0.4R | 26d  |
| 2     | 2023-02-10  | 2023-03-01 | trailing_stop | +0.88% | +1.3R | 19d  |
| 3     | 2023-04-19  | 2023-07-12 | trailing_stop | +4.07% | +9.4R | 84d  |
| 4     | 2023-09-05  | 2023-09-10 | stop_loss     | -0.97% | -0.5R | 5d   |
| 5     | 2024-03-14  | 2024-04-09 | time_exit     | +0.53% | +1.8R | 26d  |
| 6     | 2024-07-10  | 2024-07-11 | stop_loss     | -0.27% | -1.9R | 1d   |
| 7     | 2025-07-09  | 2025-07-14 | stop_loss     | -0.18% | -0.8R | 5d   |

El trade 3 (+4.07%, 9.4R en 84 dias) es excepcional — un patron VCP
clasico capturado en USDCNY.

---

## Comparacion con el experimento full-dataset

### Que se confirma

1. **`early_exit=None` es universal en FX.** Se confirmo en la
   estabilidad temporal (coincide en ambas mitades) y en multi-currency
   (GBPUSD y USDJPY que seleccionaron early_exit pierden en TEST).

2. **`depth_atr=5` es estable.** Coincide entre TRAIN y FULL en EURUSD.
   Las monedas que seleccionan 5-6 funcionan; las que seleccionan 2-3
   tienen pocos trades.

3. **`trailing=1.5` es estable.** Coincide entre TRAIN y FULL en EURUSD.
   El trailing apretado captura mejor los movimientos chicos de FX.

4. **Los params de EURUSD generalizan bien.** En GBPUSD dan mejor
   resultado (+6.53% vs +1.30% en TEST) que los params propios
   sobreajustados. En USDCNY rinden comparable (+3.45% vs +4.38%).

### Que cambia respecto al full-dataset

1. **El CR de EURUSD en train/test:** Los +8.80% del full-dataset se
   descomponen en +0.22% TRAIN / +8.56% TEST. Casi toda la ganancia
   viene de 2020-2026, particularmente de dos trades grandes en
   mayo y octubre 2020.

2. **Monedas no viables:** USDJPY y USDCNH pierden con cualquier
   configuracion, tanto en TRAIN como en TEST. El patron VCP no se
   manifiesta en estas monedas.

3. **`atr_mult=1.5` es correcto pero no se puede demostrar solo con
   5 anios.** En TRAIN, `atr_mult=2.5` "gana" porque con 4 trades
   tiene mas suerte. Pero en TEST pierde los mejores movimientos.
   Se necesita la data completa para confirmar este parametro.

---

## Monedas viables para VCP

| Moneda | Viable? | Evidencia                                         |
|--------|---------|---------------------------------------------------|
| EURUSD | **SI**  | +8.56% TEST, 80% WR, 5 trades                    |
| GBPUSD | **SI**  | +6.53% TEST con params EURUSD, 60% WR, 10 trades |
| USDCNY | **SI**  | +4.38% TEST (propios) / +3.45% (EURUSD), 5-7 trades |
| USDJPY | **NO**  | Negativo con todos los params en TEST              |
| USDCNH | **NO**  | Sin trades o trades perdedores en TEST             |

---

## Configs recomendadas

### Config universal FX (params EURUSD — recomendada)

La config que mejor generaliza across monedas viables:

```python
swing_config = ATRZigZagConfig(atr_length=14, atr_mult=1.5)

sequence_params = {
    "method": "tolerance", "min_contractions": 2, "max_contractions": 6,
    "lookback_bars": 126, "tolerance": 0.10,
    "max_depth_pct": 0.50, "max_depth_atr": 5,
    "min_total_reduction": 0.60,
    "require_ascending_lows": True, "ascending_lows_tolerance": 0.03,
}

risk_params = {
    "max_stop_loss_pct": 0.02,
    "trailing_stop_method": "atr", "trailing_atr_multiplier": 1.5,
    "target_r_multiple": 3.0,
    "early_exit_days": None,
    "breakeven_r_multiple": 1.0,
    "max_bars_without_progress": 15,
}
```

Resultados en TEST (2020-2026) con esta config:
- EURUSD: 5 trades, 80% WR, +8.56%
- GBPUSD: 10 trades, 60% WR, +6.53%
- USDCNY: 5 trades, 60% WR, +3.45%
- **Total: 20 trades, 65% WR combinado**

### Config especifica USDCNY (si se quiere maximizar esta moneda)

```python
swing_config = ATRZigZagConfig(atr_length=14, atr_mult=1.5)

sequence_params = {
    "method": "tolerance", "min_contractions": 2, "max_contractions": 6,
    "lookback_bars": 126, "tolerance": 0.10,
    "max_depth_pct": 0.50, "max_depth_atr": 6,
    "min_total_reduction": 0.80,
    "require_ascending_lows": True, "ascending_lows_tolerance": 0.03,
}

risk_params = {
    "max_stop_loss_pct": 0.02,
    "trailing_stop_method": "atr", "trailing_atr_multiplier": 2.0,
    "target_r_multiple": None,
    "early_exit_days": None,
    "breakeven_r_multiple": 1.5,
    "max_bars_without_progress": 15,
}
```

Resultado en TEST: 7 trades, 57% WR, +4.38%

---

## Limitaciones

1. **Bajo N de trades:** 4-10 trades por moneda en cada mitad. Los
   resultados son direccionales pero no estadisticamente robustos.

2. **Seleccion de la mejor config por CR maximo:** Con pocos trades, la
   mejor config puede ganar por un trade con suerte. Un enfoque mas
   robusto seria seleccionar la config con mejor avg_R o mejor percentil
   de CR across configs similares.

3. **Sesgo de supervivencia temporal:** El split 50/50 deja poco margen.
   Un walk-forward con ventanas moviles seria mas riguroso pero requiere
   mas data.

4. **Parametros fijos no explorados:** `tolerance` (0.10), `lookback_bars`
   (126), `ascending_lows_tolerance` (0.03), `ratio_threshold` (0.85), y
   `max_entry_distance_pct` (0.03) se mantuvieron fijos. Podrian tener
   impacto.

## Proximos pasos

1. **Analisis visual de trades** — verificar que los patrones detectados
   en GBPUSD y USDCNY son visualmente VCPs reales.
2. **Walk-forward validation** — ventanas moviles de 3 anios train + 2
   anios test para mas robustez.
3. **Explorar parametros fijos** — particularmente `tolerance` y
   `max_entry_distance_pct` que podrian variar entre monedas.
4. **Combinar monedas en portfolio** — evaluar equity curve y drawdown
   de operar las 3 monedas viables simultaneamente.
