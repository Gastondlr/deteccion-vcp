# AMZN — Optimizacion Profunda v2 (Train 2015-2019)

## Objetivo

Optimizar la deteccion de patrones VCP para AMZN con mejoras respecto a v1:
- Volumen en breakout como post-filtro sistematico (7 variantes)
- 3 perfiles de salida en Fase 1 para ranking robusto (trail 1.5/2.5/3.5)
- Seleccion multi-criterio: top 10 por CR + top 10 por WR
- Fase 2 sobre 20 candidatos (no solo el top 1)
- Ranking final compuesto: 50% CR + 30% WR + 20% avg_R

Train: 2015-01-02 a 2019-12-31 (1,258 barras). Test reservado: 2020-2026.

---

## Parametros variados

### Fase 1: Deteccion (17,496 pipeline runs -> 244,944 rows evaluadas)

| Parametro | Valores |
|---|---|
| atr_mult | 2.0, 3.0, 4.0 |
| use_close_only | False, True |
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

Cada config se evaluo con 3 salidas fijas (tight/medium/loose) y se rankeo por el promedio.

### Fase 2: Salida (720 configs x 20 candidatos = 14,400 evaluaciones)

| Parametro | Valores |
|---|---|
| trailing_atr_multiplier | 1.0, 1.5, 2.0, 2.5, 3.0 |
| target_r_multiple | None, 2.0, 3.0, 5.0 |
| early_exit_days | None, 3, 5 |
| breakeven_r_multiple | 0.5, 1.0, 1.5, 2.0 |
| max_stop_loss_pct | 0.03, 0.05, 0.07 |

---

## Resultados de sensibilidad (Fase 1)

### Parametros con alto impacto

| Parametro | Mejor valor | avg_CR mejor | avg_CR peor | Observacion |
|---|---|---|---|---|
| atr_mult | 2.0 | +8.09% | +2.50% (4.0) | Domina, consistente con AAPL |
| max_depth_atr | None | +9.08% | +2.46% (6) | **Diferente a AAPL** (donde mda=6 era mejor) |
| reduction | 0.80 | +8.93% | +0.96% (0.40) | Consistente con AAPL, brecha mas grande |
| lookback_bars | 126 | +8.18% | +3.20% (63) | Consistente con AAPL |
| trend_template | False | +7.97% | +3.41% (True) | Consistente con AAPL |

### Parametros con impacto moderado

| Parametro | Observacion |
|---|---|
| comp_thresh | 0.95 mejor (+6.59%), 0.85 peor (+4.77%) |
| vol_contraction | Sin VC: +6.07%, con VC: +5.31%. Menor gap que AAPL |
| vol_filter | no_filter: +7.56%, w1_t1.5: +3.28%. no_filter y w5_t1.2 similares |
| use_close_only | HL: +6.07%, Close: +5.31%. Mucho menor gap que AAPL |

### Parametros sin impacto (para AMZN)

| Parametro | Observacion |
|---|---|
| tolerance | 0.10, 0.15, 0.20 practicamente identicos |
| max_depth_pct | 0.30 y 0.35 iguales, 0.25 ligeramente peor |
| ascending_lows_tolerance | 0.01, 0.03, 0.08 sin diferencia apreciable |

### Estabilidad entre exit profiles

Correlacion entre CRs de los 3 perfiles de salida (tight/medium/loose):
- tight-medium: 0.862
- tight-loose: 0.781
- medium-loose: 0.811

Ligeramente mas alta que AAPL. Las configs de deteccion son estables entre exits.

---

## Deteccion base elegida

Las variantes top por composite comparten base de deteccion:

```
atr_mult=3.0, use_close_only=False (HL)
max_depth_atr=None, lookback_bars=126
compression_threshold=0.90, tolerance=0.15
max_depth_pct=0.30, ascending_lows_tolerance=0.01
trend_template=False, volume_contraction=True (ratio<=0.85)
```

Lo que varia entre ellas es: min_total_reduction (0.60/0.80), vol_filter, y config de salida.

La variante con mayor CR (CR#1) usa una base diferente: atr=2.0, Close, mda=8, VC=N.

---

## Tabla comparativa — Train (2015-2019)

### Mejores por CR (retorno acumulado)

| Variante | T | W | L | WR | CR | CAGR | MaxDD | avgR | PF | Exp |
|---|---|---|---|---|---|---|---|---|---|---|
| **Buy & Hold AMZN** | — | — | — | — | +498.94% | 43.13% | -34.10% | — | — | 100% |
| **CR#1** tr=2.0 tg=3R early=5 sl=5% no_filter VC=N | 33 | 15 | 18 | 45% | +121.77% | 17.30% | -5.38% | +0.53 | 5.4 | 40% |
| **CR#2** tr=2.0 tg=5R early=3 sl=5% no_filter VC=Y red=0.60 | 19 | 10 | 9 | 53% | +103.38% | 15.32% | -2.88% | +0.80 | 7.9 | 38% |
| **CR#3** tr=2.0 tg=5R early=5 sl=5% no_filter VC=Y red=0.80 | 25 | 11 | 14 | 44% | +98.09% | 14.66% | -2.88% | +0.54 | 7.9 | 38% |

### Mejores por WR (win rate, min 3 trades)

| Variante | T | W | L | WR | CR | CAGR | MaxDD | avgR | PF | Exp |
|---|---|---|---|---|---|---|---|---|---|---|
| **Buy & Hold AMZN** | — | — | — | — | +498.94% | 43.13% | -34.10% | — | — | 100% |
| **WR#1** tr=2.5 tg=2R sl=3% w5_t1.2 VC=N | 6 | 6 | 0 | 100% | +37.58% | — | 0.00% | +1.83 | inf | — |
| **WR#2** tr=2.5 tg=3R be=1.5 sl=3% w3_t1.2 VC=Y | 4 | 4 | 0 | 100% | +37.95% | — | 0.00% | +2.80 | inf | — |
| **WR#3** tr=2.0 tg=None be=1.5 sl=3% w3_t1.2 VC=Y | 12 | 9 | 3 | 75% | +111.12% | 16.15% | -1.80% | +2.21 | 26.1 | 36% |

### Mejores por Sharpe ratio

| Variante | T | W | L | WR | CR | CAGR | MaxDD | Sharpe | avgR | PF | Exp |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **Buy & Hold AMZN** | — | — | — | — | +498.94% | 43.13% | -34.10% | 1.37 | — | — | 100% |
| **WR#2** tr=2.5 tg=3R be=1.5 sl=3% w3_t1.2 VC | 4 | 4 | 0 | 100% | +37.95% | 6.66% | 0.00% | **2.93** | +2.80 | inf | 10% |
| **COMP#1** tr=2.0 tg=None be=1.5 sl=3% w3_t1.2 VC | 12 | 9 | 3 | 75% | +111.12% | 16.15% | -1.80% | **1.57** | +2.21 | 26.1 | 36% |
| **COMP#3** tr=2.0 tg=None be=1.5 sl=3% w5_t1.2 VC red=0.80 | 14 | 10 | 4 | 71% | +106.18% | 15.60% | -4.51% | **1.37** | +1.84 | 11.1 | 39% |

### Mejores por composite (50% CR + 30% WR + 20% avg_R)

| Variante | Comp | T | W | L | WR | CR | CAGR | MaxDD | avgR | PF | Exp |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **Buy & Hold AMZN** | — | — | — | — | — | +498.94% | 43.13% | -34.10% | — | — | 100% |
| **COMP#1** tr=2.0 tg=None be=1.5 sl=3% w3_t1.2 VC=Y | 0.771 | 12 | 9 | 3 | 75% | +111.12% | 16.15% | -1.80% | +2.21 | 26.1 | 36% |
| **COMP#2** tr=2.0 tg=None be=1.5 sl=3% w5_t1.2 VC=Y | 0.771 | 12 | 9 | 3 | 75% | +111.12% | 16.15% | -1.80% | +2.21 | 26.1 | 36% |
| **COMP#3** tr=2.0 tg=None be=1.5 sl=3% w5_t1.2 VC=Y red=0.80 | 0.696 | 14 | 10 | 4 | 71% | +106.18% | 15.60% | -4.51% | +1.84 | 11.1 | 39% |

---

## Configuraciones completas de las variantes

### COMP#1 / WR#3 — La variante ganadora (w3_t1.2)

**Deteccion:**
```
atr_mult=3.0, use_close_only=False
max_depth_atr=None, min_total_reduction=0.60, lookback_bars=126
compression_threshold=0.90, tolerance=0.15
max_depth_pct=0.30, ascending_lows_tolerance=0.01
trend_template=False, volume_contraction=True (ratio<=0.85)
vol_filter=w3_t1.2 (volumen >= 1.2x avg en ventana de 3 dias)
```

**Salida:**
```
trailing_atr_multiplier=2.0, target_r_multiple=None
early_exit_days=None, breakeven_r_multiple=1.5, max_stop_loss_pct=0.03
max_bars_without_progress=15, min_progress_r=0.5
```

### COMP#2 — Misma deteccion, vol_filter w5_t1.2

**Deteccion:**
```
atr_mult=3.0, use_close_only=False
max_depth_atr=None, min_total_reduction=0.60, lookback_bars=126
compression_threshold=0.90, tolerance=0.15
max_depth_pct=0.30, ascending_lows_tolerance=0.01
trend_template=False, volume_contraction=True (ratio<=0.85)
vol_filter=w5_t1.2 (volumen >= 1.2x avg en ventana de 5 dias)
```

**Salida:**
```
trailing_atr_multiplier=2.0, target_r_multiple=None
early_exit_days=None, breakeven_r_multiple=1.5, max_stop_loss_pct=0.03
max_bars_without_progress=15, min_progress_r=0.5
```

### COMP#3 — Deteccion con red=0.80 (mas restrictiva)

**Deteccion:**
```
atr_mult=3.0, use_close_only=False
max_depth_atr=None, min_total_reduction=0.80, lookback_bars=126
compression_threshold=0.90, tolerance=0.15
max_depth_pct=0.30, ascending_lows_tolerance=0.01
trend_template=False, volume_contraction=True (ratio<=0.85)
vol_filter=w5_t1.2
```

**Salida:**
```
trailing_atr_multiplier=2.0, target_r_multiple=None
early_exit_days=None, breakeven_r_multiple=1.5, max_stop_loss_pct=0.03
max_bars_without_progress=15, min_progress_r=0.5
```

### CR#1 — Mayor retorno absoluto

**Deteccion:**
```
atr_mult=2.0, use_close_only=True
max_depth_atr=8, min_total_reduction=0.80, lookback_bars=126
compression_threshold=0.95, tolerance=0.10
max_depth_pct=0.30, ascending_lows_tolerance=0.03
trend_template=False, volume_contraction=False
vol_filter=no_filter
```

**Salida:**
```
trailing_atr_multiplier=2.0, target_r_multiple=3.0
early_exit_days=5, breakeven_r_multiple=1.0, max_stop_loss_pct=0.05
max_bars_without_progress=15, min_progress_r=0.5
```

---

## Detalle de trades — Variantes principales

### COMP#1 / COMP#2: tr=2.0 tg=None be=1.5 sl=3% VC=Y — 12T, 75% WR, +111.12%

Trades identicos para ambas variantes (w3_t1.2 y w5_t1.2 pasan las mismas senales).

| # | Entry | Exit | Salida | PnL | R | MaxR | Dur |
|---|---|---|---|---|---|---|---|
| 1 | 2016-04-29 | 2016-06-23 | time_exit | +9.47% | +3.2R | 3.5R | 55d |
| 2 | 2016-06-24 | 2016-09-01 | time_exit | +10.25% | +3.4R | 3.5R | 69d |
| 3 | 2017-03-29 | 2017-04-13 | trailing_stop | +1.18% | +0.4R | 1.3R | 15d |
| 4 | 2017-04-27 | 2017-06-09 | trailing_stop | +6.53% | +2.2R | 3.4R | 43d |
| 5 | 2017-10-12 | 2017-10-20 | stop_loss | -1.80% | -0.6R | 0.3R | 8d |
| 6 | 2017-10-27 | 2017-12-04 | trailing_stop | +3.00% | +1.0R | 2.9R | 38d |
| 7 | 2017-12-05 | 2018-02-01 | trailing_stop | **+21.76%** | **+7.3R** | 9.0R | 58d |
| 8 | 2018-07-12 | 2018-07-30 | trailing_stop | -0.97% | -0.3R | 1.2R | 18d |
| 9 | 2018-07-31 | 2018-09-06 | trailing_stop | +10.18% | +3.4R | 4.9R | 37d |
| 10 | 2019-03-18 | 2019-05-10 | trailing_stop | +8.49% | +2.8R | 4.2R | 53d |
| 11 | 2019-05-13 | 2019-05-23 | trailing_stop | -0.40% | -0.1R | 1.6R | 10d |
| 12 | 2019-06-05 | 2019-07-26 | trailing_stop | +11.77% | +3.9R | 5.4R | 51d |

### COMP#3: tr=2.0 tg=None be=1.5 sl=3% VC=Y red=0.80 — 14T, 71% WR, +106.18%

Mismos 12 trades de COMP#1/2 + 2 trades adicionales en sep-oct 2016.

| # | Entry | Exit | Salida | PnL | R | MaxR | Dur |
|---|---|---|---|---|---|---|---|
| 1 | 2016-04-29 | 2016-06-23 | time_exit | +9.47% | +3.2R | 3.5R | 55d |
| 2 | 2016-06-24 | 2016-09-01 | time_exit | +10.25% | +3.4R | 3.5R | 69d |
| 3 | 2016-09-22 | 2016-10-14 | trailing_stop | +2.27% | +0.8R | 1.6R | 22d |
| 4 | 2016-10-17 | 2016-10-28 | trailing_stop | -4.51% | -1.5R | 1.0R | 11d |
| 5 | 2017-03-29 | 2017-04-13 | trailing_stop | +1.18% | +0.4R | 1.3R | 15d |
| 6 | 2017-04-27 | 2017-06-09 | trailing_stop | +6.53% | +2.2R | 3.4R | 43d |
| 7 | 2017-10-12 | 2017-10-20 | stop_loss | -1.80% | -0.6R | 0.3R | 8d |
| 8 | 2017-10-27 | 2017-12-04 | trailing_stop | +3.00% | +1.0R | 2.9R | 38d |
| 9 | 2017-12-05 | 2018-02-01 | trailing_stop | +21.76% | +7.3R | 9.0R | 58d |
| 10 | 2018-07-12 | 2018-07-30 | trailing_stop | -0.97% | -0.3R | 1.2R | 18d |
| 11 | 2018-07-31 | 2018-09-06 | trailing_stop | +10.18% | +3.4R | 4.9R | 37d |
| 12 | 2019-03-18 | 2019-05-10 | trailing_stop | +8.49% | +2.8R | 4.2R | 53d |
| 13 | 2019-05-13 | 2019-05-23 | trailing_stop | -0.40% | -0.1R | 1.6R | 10d |
| 14 | 2019-06-05 | 2019-07-26 | trailing_stop | +11.77% | +3.9R | 5.4R | 51d |

---

## Observaciones

1. **target=None domina** en AMZN (los mejores dejan correr profits con trailing), mientras que en AAPL ganaba target=2R. Esto refleja que AMZN tuvo movimientos mas amplios 2016-2019.

2. **VC=Y aparece en los top por composite**: volume_contraction filtra senales ruidosas y mejora WR (75% vs 45% sin VC).

3. **atr_mult=3.0 en el composite vs 2.0 en sensibilidad**: la sensibilidad global muestra atr=2.0 mejor en promedio, pero las mejores configs puntuales usan atr=3.0 con VC=Y. Esto es un patron de overfitting: atr=3.0 produce menos senales y las pocas que da son mas limpias en train.

4. **CR#1 (atr=2.0, no_filter, early=5) tiene el mayor CR (+121.77%)** pero con 45% WR — gana por volumen de trades (33) y early_exit que captura recuperaciones rapidas.

5. **El trade estrella**: 2017-12-05 a 2018-02-01, +21.76% (+7.3R) en 58 dias, presente en todas las variantes. Un VCP clasico de AMZN pre-earnings Q4 2017.

6. **Exposicion baja** (36-40%): el capital esta libre >60% del tiempo en todas las variantes.

---

## Resultados Test (2020-01-02 a 2026-04-08)

Stage 2 en test: 389/1574 dias (25%).

### Tabla de resultados — Test

| Variante | T | W | L | WR | CR | MaxDD | avgR | PF | Exp |
|---|---|---|---|---|---|---|---|---|---|
| **Buy & Hold AMZN** | — | — | — | — | +133.14% | -56.15% | — | — | 100% |
| **COMP#1** VC=Y, w3_t1.2, tr=2.0 tg=None sl=3% | **0** | — | — | — | 0.00% | — | — | — | 0% |
| **COMP#2** VC=Y, w5_t1.2, tr=2.0 tg=None sl=3% | **0** | — | — | — | 0.00% | — | — | — | 0% |
| **COMP#3** VC=Y, w5_t1.2, tr=2.0 tg=None sl=3% | **0** | — | — | — | 0.00% | — | — | — | 0% |
| **CR#1** VC=N, no_filter, tr=2.0 tg=3R early=5 sl=5% | 31 | 4 | 27 | 13% | -8.93% | -15.26% | -0.05 | 0.8 | 14% |

### Diagnostico: Por que 0 trades en test para las variantes top

Senales brutas en test por configuracion de zigzag:

| Config | Senales sin filtro | Senales con VC |
|---|---|---|
| atr=2.0, HL | 121 | 102 |
| atr=2.0, Close | 76 | 73 |
| atr=3.0, HL | **9** | **0** |
| atr=3.0, Close | 0 | 0 |

**Causa raiz**: `atr_mult=3.0` con los filtros de contraccion aplicados produce solo 9 senales brutas en test (sin VC) y 0 con VC. AMZN tuvo movimientos muy amplios en 2020-2022 (COVID rally +100%, caida -55%) que generan swings demasiado grandes — el zigzag detecta pocos swings (79 vs 191 con atr=2.0) y las contracciones resultantes no cumplen los criterios de VCP.

### Variantes alternativas evaluadas en test

Se evaluaron configs con atr=2.0 para entender si el problema es solo atr_mult:

| Variante | T | W | L | WR | CR | MaxDD | avgR | PF | Exp |
|---|---|---|---|---|---|---|---|---|---|
| ALT#1 atr=3.0 HL VC=N no_filter tr=2.0 tg=5R early=5 | 4 | 0 | 4 | 0% | -3.89% | -3.89% | -0.20 | 0.0 | 1% |
| ALT#2 atr=3.0 HL VC=Y no_filter tr=2.0 tg=None | **0** | — | — | — | 0.00% | — | — | — | 0% |
| ALT#3 atr=3.0 HL VC=N no_filter tr=2.0 tg=None | 2 | 0 | 2 | 0% | -3.49% | -3.49% | -0.58 | 0.0 | 2% |
| **ALT#4** atr=2.0 C VC=N no_filter tr=2.0 tg=None | **14** | **5** | **9** | **36%** | **-0.12%** | **-13.17%** | **+0.06** | **1.1** | **20%** |

### Detalle de trades — ALT#4 (mejor en test): 14T, 36% WR, -0.12%

| # | Entry | Exit | Salida | PnL | R | MaxR | Dur |
|---|---|---|---|---|---|---|---|
| 1 | 2021-02-02 | 2021-02-11 | stop_loss | -3.49% | -1.2R | 0.0R | 9d |
| 2 | 2022-07-29 | 2022-08-22 | trailing_stop | -1.28% | -0.4R | 2.4R | 24d |
| 3 | 2022-08-23 | 2022-08-30 | stop_loss | -3.66% | -1.2R | 0.9R | 7d |
| 4 | 2022-08-31 | 2022-09-13 | trailing_stop | +0.04% | +0.0R | 2.5R | 13d |
| 5 | 2023-04-19 | 2023-05-01 | trailing_stop | -2.16% | -0.7R | 1.8R | 12d |
| 6 | 2023-05-05 | 2023-07-24 | trailing_stop | **+21.91%** | **+7.3R** | 9.4R | 80d |
| 7 | 2024-02-02 | 2024-03-22 | time_exit | +4.11% | +1.4R | 1.4R | 49d |
| 8 | 2024-03-25 | 2024-04-17 | trailing_stop | +0.87% | +0.3R | 1.7R | 23d |
| 9 | 2024-04-18 | 2024-04-25 | stop_loss | -3.10% | -1.0R | 0.1R | 7d |
| 10 | 2024-04-26 | 2024-05-23 | trailing_stop | +0.80% | +0.3R | 1.8R | 27d |
| 11 | 2025-06-27 | 2025-08-01 | trailing_stop | -3.83% | -1.3R | 1.6R | 35d |
| 12 | 2026-01-06 | 2026-01-14 | stop_loss | -1.78% | -0.6R | 0.9R | 8d |
| 13 | 2026-01-16 | 2026-01-20 | stop_loss | -3.40% | -1.1R | 0.0R | 4d |
| 14 | 2026-01-23 | 2026-02-04 | stop_loss | -2.58% | -0.9R | 0.8R | 12d |

### Detalle de trades — CR#1 en test: 31T, 13% WR, -8.93%

| # | Entry | Exit | Salida | PnL | R | MaxR | Dur |
|---|---|---|---|---|---|---|---|
| 1 | 2021-02-02 | 2021-02-03 | early_exit | -2.00% | -0.4R | 0.0R | 1d |
| 2 | 2021-02-05 | 2021-02-08 | early_exit | -0.87% | -0.2R | 0.0R | 3d |
| 3 | 2022-07-29 | 2022-08-02 | early_exit | -0.59% | -0.1R | 0.1R | 4d |
| 4 | 2022-08-03 | 2022-08-08 | early_exit | -0.08% | -0.0R | 0.4R | 5d |
| 5 | 2022-08-09 | 2022-08-22 | trailing_stop | -3.34% | -0.7R | 1.0R | 13d |
| 6 | 2022-08-23 | 2022-08-26 | early_exit | -2.15% | -0.4R | 0.5R | 3d |
| 7 | 2022-08-29 | 2022-08-30 | early_exit | -0.82% | -0.2R | 0.0R | 1d |
| 8 | 2022-08-31 | 2022-09-06 | early_exit | -0.52% | -0.1R | 0.2R | 6d |
| 9 | 2022-09-07 | 2022-09-13 | early_exit | -2.05% | -0.4R | 1.1R | 6d |
| 10 | 2023-04-19 | 2023-04-20 | early_exit | -0.47% | -0.1R | 0.0R | 1d |
| 11 | 2023-04-21 | 2023-04-24 | early_exit | -0.70% | -0.1R | 0.0R | 3d |
| 12 | 2023-04-26 | 2023-05-01 | early_exit | -2.79% | -0.6R | 0.9R | 5d |
| 13 | 2023-05-05 | 2023-05-30 | target | +15.15% | +3.0R | 3.0R | 25d |
| 14 | 2024-02-02 | 2024-02-05 | early_exit | -0.87% | -0.2R | 0.0R | 3d |
| 15 | 2024-02-06 | 2024-02-13 | early_exit | -0.30% | -0.1R | 0.6R | 7d |
| 16 | 2024-02-14 | 2024-02-15 | early_exit | -0.69% | -0.1R | 0.0R | 1d |
| 17 | 2024-02-16 | 2024-02-20 | early_exit | -1.43% | -0.3R | 0.0R | 4d |
| 18 | 2024-02-21 | 2024-03-14 | time_exit | +6.03% | +1.2R | 1.2R | 22d |
| 19 | 2024-03-15 | 2024-04-17 | trailing_stop | +3.93% | +0.8R | 1.7R | 33d |
| 20 | 2024-04-18 | 2024-04-19 | early_exit | -2.56% | -0.5R | 0.0R | 1d |
| 21 | 2024-04-22 | 2024-04-24 | early_exit | -0.36% | -0.1R | 0.3R | 2d |
| 22 | 2024-04-25 | 2024-05-23 | trailing_stop | +4.25% | +0.8R | 1.8R | 28d |
| 23 | 2025-06-27 | 2025-06-30 | early_exit | -1.75% | -0.4R | 0.0R | 3d |
| 24 | 2025-07-01 | 2025-07-02 | early_exit | -0.24% | -0.0R | 0.0R | 1d |
| 25 | 2025-07-03 | 2025-07-08 | early_exit | -1.81% | -0.4R | 0.0R | 5d |
| 26 | 2025-07-09 | 2025-07-10 | early_exit | -0.13% | -0.0R | 0.0R | 1d |
| 27 | 2025-07-11 | 2025-07-16 | early_exit | -0.81% | -0.2R | 0.1R | 5d |
| 28 | 2025-07-17 | 2025-08-01 | trailing_stop | -4.08% | -0.8R | 0.9R | 15d |
| 29 | 2026-01-06 | 2026-01-14 | stop_loss | -1.78% | -0.4R | 0.5R | 8d |
| 30 | 2026-01-16 | 2026-01-20 | early_exit | -3.40% | -0.7R | 0.0R | 4d |
| 31 | 2026-01-23 | 2026-01-26 | early_exit | -0.31% | -0.1R | 0.0R | 3d |

---

## Comparacion Train vs Test

| Metrica | COMP#1 Train | COMP#1 Test | CR#1 Train | CR#1 Test | ALT#4 Train | ALT#4 Test |
|---|---|---|---|---|---|---|
| Trades | 12 | **0** | 33 | 31 | 19 | 14 |
| WR | 75% | — | 45% | 13% | 63% | 36% |
| CR | +111.12% | 0.00% | +121.77% | -8.93% | +113.58% | -0.12% |
| MaxDD | -1.80% | — | -5.38% | -15.26% | -6.29% | -13.17% |
| avg_R | +2.21 | — | +0.53 | -0.05 | +1.44 | +0.06 |

---

## Diagnostico detallado: Por que no se detectan patrones en test

Se realizo un analisis progresivo del pipeline para identificar en que etapa se pierden las senales.

### Capa 1: ATR absoluto 3.7x mayor en test

| Metrica | Train | Test | Ratio |
|---|---|---|---|
| ATR(14) medio | 1.22 | 4.48 | 3.68x |
| ATR(14) mediana | 0.89 | 4.27 | 4.80x |
| ATR como % del precio | 2.17% | 2.89% | 1.33x |
| Precio medio | ~$50 | ~$160 | 3.2x |

El ATR absoluto es 3.7x mayor en test, pero como porcentaje del precio la diferencia es menor (2.17% vs 2.89%).
El atr_mult=3.0 usa el ATR absoluto para definir swings, por lo que en test necesita movimientos de precio
mucho mayores para registrar un swing. Aun asi, el numero de swings y contracciones es similar
(79 swings / 39 contracciones en test vs 76/37 en train). **El problema no esta en la deteccion de swings.**

### Capa 2: Las contracciones en test son mucho mas profundas

| Metrica | Train | Test |
|---|---|---|
| Depth % medio | 11.0% | **15.7%** |
| Depth % mediana | 8.4% | **15.6%** |
| Contracciones con depth <10% | 24/37 (65%) | **12/39 (31%)** |
| Contracciones con depth <20% | 31/37 (84%) | 29/39 (74%) |
| Depth maximo | 27.4% | **40.7%** |

En train, la mayoria de las contracciones son "suaves" (<10%) — tipicas de un VCP clasico donde el precio
se consolida gradualmente. En test, las contracciones son violentas: COVID (-18%, -19%), caida 2022 (-28%,
-40%, -29%), tariffs 2025 (-33%). Esto dificulta que se formen secuencias de contracciones decrecientes,
ya que una contraccion violenta resetea el patron.

Pares consecutivos con depth decreciente: 50% en train vs 42% en test.

### Capa 3: La ATR NO se comprime entre contracciones (el filtro fatal)

El pipeline requiere compresion de ATR: `ATR_end / ATR_start <= compression_threshold` (0.90).
Esto verifica que la volatilidad se contrae durante la formacion — el principio fundamental del VCP.

Analisis de las primeras 15 contracciones en test:

| Contraccion | Fechas | ATR inicio | ATR fin | Ratio | Comprime? |
|---|---|---|---|---|---|
| 2 | feb 2020 | 2.18 | 2.74 | 1.26 | NO |
| 3 | mar 2020 | 3.03 | 4.19 | 1.38 | NO |
| 4 | may 2020 | 3.37 | 3.31 | 0.98 | NO |
| 5 | jun 2020 | 3.19 | 3.62 | 1.13 | NO |
| 6 | jul 2020 | 4.83 | 5.77 | 1.19 | NO |
| 7 | sep 2020 | 4.19 | 5.66 | 1.35 | NO |
| 8 | oct 2020 | 5.38 | 5.64 | 1.05 | NO |
| 9 | nov 2020 | 5.91 | 6.11 | 1.03 | NO |
| 10 | feb 2021 | 4.19 | 4.26 | 1.02 | NO |
| 11 | abr 2021 | 3.57 | 3.96 | 1.11 | NO |
| **12** | **jul 2021** | **3.50** | **3.09** | **0.88** | **SI** |
| 13 | sep 2021 | 2.95 | 3.30 | 1.12 | NO |
| 14 | oct 2021 | 3.26 | 3.65 | 1.12 | NO |
| 15 | nov 2021 | 4.25 | 4.93 | 1.16 | NO |

**13 de 15 contracciones NO comprimen.** La ATR se mantiene igual o AUMENTA durante las contracciones.
Solo 1 contraccion (jul-ago 2021) muestra compresion genuina (ratio 0.88).

Incluso con filtros ultra-relajados (compression_threshold=1.0, min_reduction=0.10, sin ascending_lows,
lookback=252, max_depth=100%), el pipeline produce **0 senales** con atr=3.0 en test. El filtro de
compresion de ATR es el cuello de botella absoluto.

### Causa raiz

En un VCP clasico (como los que AMZN formaba en 2016-2019), la volatilidad se contrae progresivamente:
cada swing es menor, el ATR baja, y el precio se consolida antes del breakout. Este patron funciona
en mercados con tendencias ordenadas y volatilidad moderada.

AMZN en 2020-2026 tiene un regimen radicalmente diferente:
- **COVID 2020**: volatilidad extrema que nunca baja completamente
- **Rally 2020-2021**: swings amplios incluso en uptrend
- **Caida 2022**: -55% con contracciones de 28-40%
- **Recuperacion 2023-2025**: volatilidad persistente por incertidumbre macro

En este regimen, las "consolidaciones" de AMZN NO vienen con ATR decreciente — el mercado oscila
con la misma energia, solo cambia la direccion. El supuesto fundamental del VCP
(Volatility **Contraction** Pattern) no se cumple.

### Posible solucion: compresion por rango de barras

El ATR(14) es un promedio suavizado que reacciona lento a cambios de volatilidad. Si AMZN tiene un
spike de volatilidad (earnings, macro), el ATR se queda alto por semanas aunque las barras individuales
ya se hayan calmado.

Una alternativa seria medir la compresion con el **rango de las barras** (high - low de cada vela):

```
Compresion = promedio(rango ultimas N barras) / promedio(rango N barras previas)
```

Por ejemplo, con N=10:
- Tomar el rango promedio de las ultimas 10 barras antes del breakout
- Dividir por el rango promedio de las 10 barras anteriores a esas
- Si el ratio es <= 0.85, hay compresion

Ventajas:
- **Responde mas rapido** al cambio real de volatilidad — si AMZN pasa de barras de $10 de rango a
  barras de $4, eso se detecta en 10 barras. Con ATR(14), el cambio tarda mas en reflejarse.
- **No se contamina** con volatilidad historica — solo mira las barras recientes.
- **Captura compresion local** que el ATR suavizado no puede ver.

Esta mejora no esta implementada aun.

---

## Conclusion

**AMZN no es un buen candidato para la estrategia VCP con los parametros actuales.** Las variantes
optimizadas estan sobreajustadas al regimen de baja volatilidad 2015-2019 y no producen trades en test.

El diagnostico revela que el problema no es la deteccion de swings o contracciones (hay cantidades
similares en train y test), sino que **el filtro de compresion de ATR rechaza todas las formaciones
en test** porque la volatilidad de AMZN no se contrae durante las consolidaciones post-2020. Este es
un cambio estructural en el comportamiento del activo, no un simple problema de parametros.

La unica variante que genera trades significativos en test (ALT#4: atr=2.0, Close, no_filter,
trail=2.0, sl=3%) apenas empata con cero, con un solo trade excepcional (+21.91%) salvando el resultado.

---

## Proximos pasos

- **Implementar compresion por rango de barras** como alternativa al ATR compression — medir
  `promedio(rango ultimas N barras) / promedio(rango N barras previas)` para capturar compresion
  local que el ATR(14) suavizado no detecta
- Evaluar si un atr_mult adaptativo basado en volatilidad del mercado mejora la generalizacion
- Considerar periodos de train mas recientes (incluyendo 2020-2022) para capturar ambos regimenes
- Evaluar si un modelo cross-ticker entrenado en AAPL+otros funciona mejor que per-ticker para AMZN
