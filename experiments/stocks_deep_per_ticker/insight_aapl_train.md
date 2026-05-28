# AAPL — Optimizacion Profunda (Train 2015-2019)

## Objetivo

Optimizar la deteccion de patrones VCP para AAPL de forma individual, usando 5 anos de datos para train (2015-01-02 a 2019-12-31, 1258 barras) y reservando 2020-2026 como test out-of-sample.

Se exploraron 34,992 configuraciones de deteccion y 720 configuraciones de salida, seguidas de estudios manuales sobre volumen en breakout, trailing stop y time exit.

---

## Parametros variados

### Fase 1: Deteccion (34,992 configs)

| Parametro | Valores | Descripcion |
|---|---|---|
| `atr_mult` | 2.0, 3.0, 4.0 | Multiplo de ATR para confirmar swings. Mas alto = menos swings, patrones mas grandes |
| `max_depth_atr` | None, 6, 8 | Profundidad maxima por contraccion en ATRs. Filtra caidas excesivas |
| `min_total_reduction` | 0.40, 0.60, 0.80 | Ratio ultima/primera contraccion. 0.60 = la ultima debe ser <=60% de la primera |
| `lookback_bars` | 63, 126 | Ventana temporal para buscar contracciones (~3 o ~6 meses) |
| `compression_threshold` | 0.85, 0.90, 0.95 | ATR_end/ATR_start debe ser <= umbral. 0.85 = al menos 15% de compresion |
| `tolerance` | 0.10, 0.15, 0.20 | Margen para monotonia decreciente de contracciones |
| `max_depth_pct` | 0.25, 0.30, 0.35 | Profundidad maxima por contraccion individual (absoluta) |
| `ascending_lows_tolerance` | 0.01, 0.03, 0.08 | Margen para lows ascendentes entre contracciones |
| `use_close_only` | False, True | Si usa high/low o solo close para detectar swings |
| `trend_template` | False, True | Filtro Stage 2 de Minervini (7 condiciones de medias moviles) |
| `volume_contraction` | None, ratio<=0.85 | Verifica que el volumen decrece durante la formacion del patron |

### Fase 2: Salida (720 configs)

| Parametro | Valores | Descripcion |
|---|---|---|
| `trailing_atr_multiplier` | 1.0, 1.5, 2.0, 2.5, 3.0 | Trailing stop = highest_close - mult * ATR |
| `target_r_multiple` | None, 2.0, 3.0, 5.0 | Take profit en N multiplos del riesgo inicial |
| `early_exit_days` | None, 3, 5 | Sale si el precio esta debajo de entry en los primeros N dias |
| `breakeven_r_multiple` | 0.5, 1.0, 1.5, 2.0 | Step del ratchet de breakeven |
| `max_stop_loss_pct` | 0.03, 0.05, 0.07 | Stop loss maximo como porcentaje del precio |

### Fase 3: Estudios manuales post-grilla

- Volumen en breakout: ventana de confirmacion (1-5 dias), threshold (1.2x-1.5x), lookback dinamico
- Trailing stop: multiplicadores de 1.5 a 4.0 y su interaccion con re-entradas al mismo patron
- Time exit: max_bars_without_progress (10, 15, 20, 30, None) x min_progress_r (0.3, 0.5, 1.0)

---

## Resultados de sensibilidad (Fase 1)

### Parametros con alto impacto

| Parametro | Mejor valor | avg_CR mejor | avg_CR peor | Observacion |
|---|---|---|---|---|
| `atr_mult` | 2.0 | +10.15% | +1.40% (4.0) | Domina ampliamente. Mas swings = mas oportunidades |
| `lookback_bars` | 126 | +8.07% | +2.01% (63) | 6 meses captura patrones mas completos |
| `use_close_only` | False (HL) | +7.77% | +2.31% (True) | High/Low detecta extremos mas precisos |
| `trend_template` | False | +7.25% | +2.83% (True) | Sin TT captura mas senales. TT mejora calidad (ver abajo) |

### Parametros con impacto moderado

| Parametro | Observacion |
|---|---|
| `vol_contraction` | Sin VC: avg_CR=+5.77%, con VC: +4.30%. VC reduce senales pero mejora calidad |
| `max_depth_atr` | mda=6 tiene mejor mediana. None tiene mas senales |
| `reduction` | 0.60 es el sweet spot (avg_CR=+6.58%) |
| `compression_threshold` | 0.95 ligeramente mejor (menos filtrado) |

### Parametros sin impacto (para AAPL)

| Parametro | Observacion |
|---|---|
| `tolerance` | 0.10, 0.15, 0.20 dan resultados **identicos** |
| `max_depth_pct` | 0.25, 0.30, 0.35 practicamente iguales. AAPL no tiene contracciones tan profundas |
| `ascending_lows_tolerance` | 0.01, 0.03, 0.08 casi sin diferencia |

---

## Estudio de target_r_multiple

Se probaron 4 valores de target: None (sin target), 2R, 3R y 5R.

| Target | avg Trades | WR | best CR | avg CR | avg R |
|---|---|---|---|---|---|
| 2.0R | 18.9 | 48% | **+57.75%** | +43.62% | +0.48 |
| 3.0R | 15.4 | 53% | +49.30% | +43.07% | +0.58 |
| 5.0R | 14.2 | 55% | +51.03% | +42.18% | +0.63 |
| **None** | 14.1 | **56%** | +51.03% | +42.23% | **+0.64** |

Target 2R gano en best_CR porque libera capital rapido y permite mas rotacion. Pero es una ventaja fragil.

Sin target los trades respiran mas y el trailing stop maneja la salida. Ejemplo: el trade de jul-2018 pasa de +11.68% (cortado a 2R) a +13.59% (trailing stop a 2.7R). Target=5R y target=None dan resultados casi identicos porque el trailing stop corta antes.

**Se elige target=None.**

---

## Estudio de volumen en breakout

### Problema original

Minervini describe dos condiciones de volumen: (1) volumen se seca durante la formacion del patron, (2) volumen sube en el breakout. En la implementacion original ambos filtros estaban desactivados porque exigir volumen alto el mismo dia del breakout era demasiado restrictivo (143 senales → 14, CR caia de +57% a +19%).

### Mejora implementada: ventana de confirmacion

Se implemento una ventana de N dias para la confirmacion de volumen en el breakout. En vez de exigir el spike el dia exacto, se busca si hubo volumen alto en alguno de los ultimos N dias (incluyendo hoy).

Tambien se agrego un lookback dinamico que compara el volumen contra el promedio durante la duracion del patron VCP.

### Resultados

| Variante | Sen | Trades | WR | CR |
|---|---|---|---|---|
| Vol 1.5x, ventana=1 dia (original) | 14 | 8 | 62% | +19.22% |
| Vol 1.5x, ventana=3 dias | 31 | 9 | 67% | +31.24% |
| **Vol 1.2x, ventana=3 dias** | **58** | **11** | **73%** | **+42.17%** |
| Vol 1.2x, ventana=5 dias | 76 | 11 | 73% | +42.17% |

El threshold 1.2x con ventana de 3 dias es el mejor balance. Se fija como filtro para todas las variantes.

---

## Estudio de trailing stop y time exit

### Trailing stop multiplier

Con Vol 1.2x + TT activos:

| Trail | T | WR | CR | Avg R | Salida principal |
|---|---|---|---|---|---|
| 1.5 | 5 | 80% | +27.07% | +1.04 | trailing(3), stop_loss(1) |
| 2.0 | 5 | 100% | +32.67% | +1.21 | trailing(3), time_exit(1) |
| **2.5** | **4** | **100%** | **+27.58%** | **+1.31** | **trailing(2), time_exit(1)** |
| 3.0 | 4 | 100% | +30.59% | +1.44 | time_exit(2), trailing(1) |
| 3.5+ | 4 | 100% | +30.19% | +1.42 | time_exit(3) |

### Re-entradas al mismo patron

Con trail=2.0, el trailing stop genera re-entradas: sale un trade, pero al dia siguiente el close sigue arriba del pivot y se genera una nueva senal al mismo patron. Esto produce trades "artificiales" que inflan el conteo.

Con trail=2.5 las re-entradas desaparecen. Comparacion detallada:

**Trade jul-2018 (pivot $48.99):**
- trail=2.0: sale 09-07 (+9.83%), re-entra 09-10 (+5.02%). Dos trades, total +14.85%.
- trail=2.5: un solo trade, sale 09-10 (+8.35%). Sin re-entrada.

**Trade nov-2019 (pivot $62.44):**
- trail=2.0: sale 12-03 (+1.42%), re-entra 12-10 con nuevo pivot $67.06 (+9.37%). Dos trades.
- trail=2.5: un solo trade, sale 12-05 (+3.82%) por time_exit. El siguiente trade (pivot $67.06) es un patron nuevo.

**Se elige trail=2.5** para evitar re-entradas y tener trades que corresponden a patrones independientes.

### Time exit

El parametro `max_bars_without_progress` actua como red de seguridad para trades que se estancan. Se probo variando de 10 a None:

| bars | minR | T | WR | CR | Observacion |
|---|---|---|---|---|---|
| 10 | 0.5 | 4 | 100% | +28.67% | Saca trades un poco antes, similar |
| **15** | **0.5** | **4** | **100%** | **+27.58%** | **Balance — 1 time_exit productivo** |
| 20 | 0.5 | 3 | 100% | +28.97% | Fusiona 2 trades en 1 (pierde granularidad) |
| None | — | 3 | 100% | +28.97% | Solo trailing — pocos trades |

Con bars=15, el time_exit interviene 1 vez de forma productiva (saca un trade lateral a +3.82% antes de que pierda). Con bars=20 o None, los trades 3+4 se fusionan en uno solo largo, pero se pierde un trade de +9.37%.

**Se mantiene bars=15, minR=0.5.**

---

## Configuracion final elegida

### Deteccion

```
atr_mult=2.0, use_close_only=False
max_depth_atr=6, min_total_reduction=0.80, lookback_bars=126, tolerance=0.10
max_depth_pct=0.25, ascending_lows_tolerance=0.01, compression_threshold=0.95
```

### Volumen en breakout (fijo)

```
volume_ratio_threshold=1.2, volume_confirmation_window=3, volume_lookback_days=50
require_volume_confirmation=True
```

### Salida

```
trailing_atr_multiplier=2.5, target_r_multiple=None, early_exit_days=None
breakeven_r_multiple=1.5, max_stop_loss_pct=0.05
max_bars_without_progress=15, min_progress_r=0.5
```

---

## Tabla de resultados — Train (2015-2019)

| Variante | Trades | Wins | Losses | WR | CR | CAGR | Max DD | Sharpe | Avg R | PF | Exp |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **Buy & Hold AAPL** | — | — | — | — | **+168.59%** | **+21.89%** | -38.73% | 0.92 | — | — | 100% |
| Vol 1.2x win=3d | 7 | 6 | 1 | 86% | +37.91% | +6.65% | -5.27% | 1.06 | +1.00 | 14.0 | 14% |
| **Vol 1.2x win=3d + TT** | **4** | **4** | **0** | **100%** | +27.58% | +5.00% | **-4.39%** | **1.20** | **+1.31** | **inf** | 7% |

### Detalle de trades — Vol 1.2x win=3d (sin TT)

| # | Entry | Exit | Salida | PnL | R | Max R | Dur | Pivot |
|---|---|---|---|---|---|---|---|---|
| 1 | 2015-10-28 | 2015-11-11 | stop_loss | -2.65% | -0.6R | 0.6R | 14d | $39.30 |
| 2 | 2016-07-27 | 2016-08-30 | trailing_stop | +2.96% | +0.6R | 1.3R | 34d | $25.40 |
| 3 | 2017-10-27 | 2017-11-15 | trailing_stop | +3.70% | +0.8R | 1.6R | 19d | $40.22 |
| 4 | 2018-08-01 | 2018-09-10 | trailing_stop | +8.35% | +1.7R | 2.7R | 40d | $48.99 |
| 5 | 2019-03-15 | 2019-05-09 | trailing_stop | +7.84% | +1.6R | 2.8R | 55d | $45.00 |
| 6 | 2019-11-01 | 2019-12-05 | time_exit | +3.82% | +0.8R | 0.9R | 34d | $62.44 |
| 7 | 2019-12-10 | 2019-12-31 | open | +9.37% | +2.1R | 2.1R | 21d | $67.06 |

### Detalle de trades — Vol 1.2x win=3d + TT (0 losses)

| # | Entry | Exit | Salida | PnL | R | Max R | Dur | Pivot |
|---|---|---|---|---|---|---|---|---|
| 1 | 2017-10-27 | 2017-11-15 | trailing_stop | +3.70% | +0.8R | 1.6R | 19d | $40.22 |
| 2 | 2018-08-01 | 2018-09-10 | trailing_stop | +8.35% | +1.7R | 2.7R | 40d | $48.99 |
| 3 | 2019-11-01 | 2019-12-05 | time_exit | +3.82% | +0.8R | 0.9R | 34d | $62.44 |
| 4 | 2019-12-10 | 2019-12-31 | open | +9.37% | +2.1R | 2.1R | 21d | $67.06 |

Cada trade corresponde a un patron VCP independiente (pivots distintos, sin re-entradas).

### Observaciones clave

1. **Buy & Hold gana en retorno total** (+168.59%) pero con drawdown de -38.73% y 100% de exposicion.

2. **Sin TT** (7 trades): solo 1 loss (-2.65% en oct-2015), el resto ganadores. PF=14.0.

3. **Con TT** (4 trades): el filtro elimina los trades de 2015-2016 (AAPL no estaba en Stage 2 claro). 100% WR, PF infinito, Sharpe 1.20.

4. **Exposicion muy baja** (7-14%). El capital esta libre el 86-93% del tiempo.

5. **Trailing 2.5x elimina re-entradas** — cada trade es un patron independiente con pivot distinto.

6. **Graficos y datos** guardados en MLflow (experimento VCP_AAPL_DeepPerTicker).

---

## Resultados Test (2020-01-02 a 2026-04-08)

Se evaluaron las 2 variantes con la configuracion optimizada en train, sobre 1,574 barras (6.2 anos) de datos out-of-sample.

AAPL estuvo en Stage 2 solo el 28% del periodo de test (445 de 1574 dias).

### Tabla de resultados — Test

| Variante | Trades | Wins | Losses | WR | CR | CAGR | Max DD | Sharpe | Avg R | PF | Exp |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **Buy & Hold AAPL** | — | — | — | — | **+244.80%** | **+21.92%** | -33.43% | 0.79 | — | — | 100% |
| **Vol 1.2x win=3d** | **10** | **8** | **2** | **80%** | **+49.82%** | **+6.69%** | **-10.06%** | 0.72 | +0.86 | 7.0 | 16% |
| Vol 1.2x win=3d + TT | 3 | 2 | 1 | 67% | +1.38% | +0.22% | -8.73% | 0.07 | +0.12 | 1.3 | 4% |

### Detalle de trades — Vol 1.2x win=3d (sin TT)

| # | Entry | Exit | Salida | PnL | R | Max R | Dur | Pivot |
|---|---|---|---|---|---|---|---|---|
| 1 | 2020-06-11 | 2020-07-24 | trailing_stop | +10.29% | +2.1R | 3.4R | 43d | $79.92 |
| 2 | 2020-12-01 | 2021-01-06 | trailing_stop | +3.16% | +0.6R | 2.3R | 36d | $121.99 |
| 3 | 2021-01-07 | 2021-01-29 | trailing_stop | +0.79% | +0.2R | 1.9R | 22d | $129.58 |
| 4 | 2022-07-29 | 2022-08-26 | trailing_stop | +0.68% | +0.1R | 1.5R | 28d | $143.49 |
| 5 | 2022-08-31 | 2022-09-15 | stop_loss | -3.08% | -0.6R | 0.8R | 15d | $143.49 |
| 6 | 2023-03-20 | 2023-05-26 | time_exit | +11.45% | +2.3R | 2.3R | 67d | $156.30 |
| 7 | 2023-05-31 | 2023-07-24 | time_exit | +8.74% | +2.3R | 2.7R | 54d | $176.39 |
| 8 | 2023-12-05 | 2024-01-02 | stop_loss | -4.02% | -1.3R | 0.8R | 28d | $192.93 |
| 9 | 2025-07-01 | 2025-07-25 | time_exit | +2.92% | +0.6R | 0.6R | 24d | $206.24 |
| 10 | 2025-07-31 | 2025-08-29 | time_exit | +11.84% | +2.4R | 2.5R | 29d | $206.24 |

### Detalle de trades — Vol 1.2x win=3d + TT

| # | Entry | Exit | Salida | PnL | R | Max R | Dur | Pivot |
|---|---|---|---|---|---|---|---|---|
| 1 | 2021-01-05 | 2021-01-29 | trailing_stop | +0.73% | +0.1R | 1.9R | 24d | $129.58 |
| 2 | 2023-06-05 | 2023-07-24 | time_exit | +7.33% | +1.5R | 1.7R | 49d | $176.39 |
| 3 | 2023-12-13 | 2024-01-02 | stop_loss | -6.22% | -1.2R | 0.0R | 20d | $192.93 |

### Desglose por ano — Vol 1.2x win=3d (sin TT)

| Ano | Trades | WR | CR |
|---|---|---|---|
| 2020 | 2 | 100% | +13.78% |
| 2021 | 1 | 100% | +0.79% |
| 2022 | 2 | 50% | -2.42% |
| 2023 | 3 | 67% | +16.33% |
| 2024 | 0 | — | — |
| 2025 | 2 | 100% | +15.10% |

### Observaciones del test

1. **La variante sin TT generaliza bien**: WR se mantiene (86% train → 80% test), CR comparable (+37.91% en 5y → +49.82% en 6.2y). Los patrones VCP con confirmacion de volumen funcionan out-of-sample.

2. **El Trend Template NO generaliza**: de 100% WR en train cae a 67% en test. Solo genera 3 trades en 6 anos — demasiado restrictivo. Elimina los mejores trades de 2020 (+10.29%) y 2025 (+11.84%). El loss de dic-2023 (-6.22%) borra casi todo.

3. **El drawdown se controla**: -10.06% de la estrategia vs -33.43% del buy & hold (3.3x menor). Las 2 losses son del -3% a -4%, manejables.

4. **Distribucion temporal razonable**: trades en 2020, 2021, 2022, 2023 y 2025. Solo 2024 queda sin trades. No hay concentracion en un solo periodo.

5. **Re-entradas en test**: trades 4+5 (pivot $143.49) y 9+10 (pivot $206.24) son re-entradas al mismo patron. Con trail=2.5 se reduce pero no elimina completamente. En el caso 9+10, la re-entrada fue muy exitosa (+11.84%).

6. **Time exit sigue siendo util**: 4 de 10 trades salen por time_exit, todos positivos (de +2.92% a +11.84%). El mecanismo funciona como proteccion de ganancias en trades que se estancan.

---

## Comparacion Train vs Test

| Metrica | Train (2015-2019) | Test (2020-2026) |
|---|---|---|
| **Estrategia (sin TT)** | | |
| Trades | 7 | 10 |
| Win Rate | 86% | 80% |
| CR | +37.91% | +49.82% |
| CAGR | +6.65% | +6.69% |
| Max Drawdown | -5.27% | -10.06% |
| Sharpe | 1.06 | 0.72 |
| Avg R | +1.00 | +0.86 |
| PF | 14.0 | 7.0 |
| Exposicion | 14% | 16% |
| **Buy & Hold** | | |
| CR | +168.59% | +244.80% |
| Max Drawdown | -38.73% | -33.43% |
| Sharpe | 0.92 | 0.79 |

El CAGR de la estrategia es practicamente identico entre train y test (+6.65% vs +6.69%), lo que sugiere que no hay overfitting significativo en los parametros de deteccion y salida. La degradacion esta en Sharpe (1.06 → 0.72) y drawdown (-5.27% → -10.06%), esperado al pasar a datos no vistos con mayor volatilidad (COVID-2020, caida 2022).

---

## Conclusion

La estrategia VCP con confirmacion de volumen (1.2x, ventana 3 dias) y sin Trend Template es la variante ganadora:

- **Generaliza en test** con metricas consistentes vs train.
- **80% WR** y **PF 7.0** out-of-sample.
- **Drawdown controlado** (-10% vs -33% del activo).
- **Exposicion baja** (16%) — capital libre el 84% del tiempo.
- **El Trend Template sobreajusta** al periodo de train y debe descartarse para AAPL.

Graficos y datos detallados en MLflow (experimento VCP_AAPL_DeepPerTicker, runs AAPL_deep_test).

---

## Proximos pasos

- Repetir el analisis completo para AMZN, GOOGL, MSFT y NVDA.
- Evaluar si los parametros de deteccion son transferibles entre tickers o requieren optimizacion individual.
