# META — Optimizacion Profunda v2 (Train 2015-2019)

## Objetivo

Optimizar la deteccion de patrones VCP para META con mejoras respecto a v1:
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
| atr_mult | 2.0 | -1.31% | +0.08% (4.0) | 2.0 domina en coverage (73890 vs 3564 configs con trades) |
| use_close_only | **False (HL)** | -0.53% | -0.62% (True) | **Diferente a GOOGL** — HL es mejor para META |
| comp_thresh | 0.95 | -0.02% | -0.86% (0.85) | 0.95 domina ampliamente, contracciones de ATR sutiles |
| reduction | 0.80 | -0.44% | -0.87% (0.40) | 0.60 y 0.80 similares, 0.40 muy restrictivo |
| vol_filter | w5_t1.5 | +0.34% | -3.31% (no_filter) | Sin filtro produce peor avg_CR por muchos trades malos |

### Parametros con impacto moderado

| Parametro | Observacion |
|---|---|
| lookback_bars | lb=63: avg_CR=-0.31%, lb=126: avg_CR=-0.84%. lb=63 mejor promedio |
| trend_template | False: -0.34%, True: -0.81%. Consistente con otros tickers |
| max_depth_atr | mda=6 mejor (-0.34%), None peor (-0.85%) |
| vol_contraction | Sin VC: -0.64%, con VC: -0.51%. Similar para META |

### Parametros sin impacto (para META)

| Parametro | Observacion |
|---|---|
| tolerance | 0.10, 0.15, 0.20 practicamente iguales |
| max_depth_pct | 0.25, 0.30, 0.35 identicos |
| ascending_lows_tolerance | 0.01 y 0.03 similares, 0.08 ligeramente peor |

### Estabilidad entre exit profiles

Correlacion entre CRs de los 3 perfiles de salida (tight/medium/loose):
- tight-medium: 0.880
- tight-loose: 0.564
- medium-loose: 0.568

Estabilidad buena entre tight-medium, menor entre loose y los demas.

---

## Deteccion base elegida

Las variantes top comparten deteccion similar:

**COMP#1 (ganador composite):**
```
atr_mult=2.0, use_close_only=False (HL)
max_depth_atr=None, min_total_reduction=0.80, lookback_bars=126
compression_threshold=0.95, tolerance=0.10
max_depth_pct=0.25, ascending_lows_tolerance=0.01
trend_template=False, volume_contraction=True (ratio<=0.85)
vol_filter=no_filter
```

**COMP#2-#4 (con vol_filter):**
```
atr_mult=2.0, use_close_only=False (HL)
max_depth_atr=None, min_total_reduction=0.60
lookback_bars=63 (COMP#2) o 126 (COMP#3, COMP#4)
compression_threshold=0.95, tolerance=0.10
max_depth_pct=0.25, ascending_lows_tolerance=0.01
trend_template=False
volume_contraction=True (COMP#3) o False (COMP#2, COMP#4)
vol_filter=w1_t1.2
```

---

## Tabla comparativa — Train (2015-2019)

### Mejores por composite (50% CR + 30% WR + 20% avg_R)

| Variante | Comp | T | W | L | WR | CR | CAGR | MaxDD | Sharpe | avgR | PF |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **Buy & Hold META** | — | — | — | — | — | +161.63% | 21.23% | -42.96% | — | — | — |
| **COMP#1** tr=1.5 tg=2R be=1.0 sl=3% no_filter VC | 0.804 | **14** | 11 | 3 | 79% | **+59.56%** | 9.81% | -2.81% | **1.45** | +1.16 | 8.4 |
| **COMP#2** tr=2.5 tg=2R be=0.5 sl=7% w1_t1.2 lb=63 | 0.776 | 6 | 6 | 0 | **100%** | +45.07% | 7.74% | **0.00%** | 1.30 | +1.14 | **inf** |
| **COMP#3** tr=2.5 tg=2R be=0.5 sl=7% w1_t1.2 VC | 0.655 | 6 | 5 | 1 | 83% | +44.03% | 7.58% | -1.12% | 1.24 | +1.11 | 35.4 |
| **COMP#4** tr=2.5 tg=2R be=0.5 sl=7% w1_t1.2 | 0.638 | 7 | 6 | 1 | 86% | +45.23% | 7.77% | -1.12% | 1.18 | +0.98 | 36.2 |

### Mejores por WR (win rate, min 3 trades)

| Variante | T | W | L | WR | CR | MaxDD | avgR | PF |
|---|---|---|---|---|---|---|---|---|
| **WR#1** w5_t1.5 lb=63 red=0.80 tr=2.5 tg=5R be=2.0 sl=3% | 4 | 4 | 0 | 100% | +14.55% | 0.00% | +1.16 | inf |
| **WR#2** w5_t1.5 lb=63 red=0.80 VC tr=2.5 sl=3% | 3 | 3 | 0 | 100% | +7.25% | 0.00% | — | inf |
| **COMP#2** w1_t1.2 lb=63 tr=2.5 tg=2R sl=7% | 6 | 6 | 0 | 100% | +45.07% | 0.00% | +1.14 | inf |

---

## Configuraciones completas de las variantes

### COMP#1 — La variante ganadora (no_filter, VC)

**Deteccion:**
```
atr_mult=2.0, use_close_only=False
max_depth_atr=None, min_total_reduction=0.80, lookback_bars=126
compression_threshold=0.95, tolerance=0.10
max_depth_pct=0.25, ascending_lows_tolerance=0.01
trend_template=False, volume_contraction=True (ratio<=0.85)
vol_filter=no_filter
```

**Salida:**
```
trailing_atr_multiplier=1.5, target_r_multiple=2.0
early_exit_days=None, breakeven_r_multiple=1.0, max_stop_loss_pct=0.03
max_bars_without_progress=15, min_progress_r=0.5
```

### COMP#2 — Vol filter w1_t1.2, short lookback

**Deteccion:**
```
atr_mult=2.0, use_close_only=False
max_depth_atr=None, min_total_reduction=0.60, lookback_bars=63
compression_threshold=0.95, tolerance=0.10
max_depth_pct=0.25, ascending_lows_tolerance=0.01
trend_template=False, volume_contraction=False
vol_filter=w1_t1.2 (volumen >= 1.2x avg en ventana de 1 dia)
```

**Salida:**
```
trailing_atr_multiplier=2.5, target_r_multiple=2.0
early_exit_days=None, breakeven_r_multiple=0.5, max_stop_loss_pct=0.07
max_bars_without_progress=15, min_progress_r=0.5
```

### COMP#3 — Vol filter w1_t1.2 + VC

**Deteccion:**
```
atr_mult=2.0, use_close_only=False
max_depth_atr=None, min_total_reduction=0.60, lookback_bars=126
compression_threshold=0.95, tolerance=0.10
max_depth_pct=0.25, ascending_lows_tolerance=0.01
trend_template=False, volume_contraction=True (ratio<=0.85)
vol_filter=w1_t1.2
```

**Salida:**
```
trailing_atr_multiplier=2.5, target_r_multiple=2.0
early_exit_days=None, breakeven_r_multiple=0.5, max_stop_loss_pct=0.07
max_bars_without_progress=15, min_progress_r=0.5
```

### COMP#4 — Vol filter w1_t1.2, sin VC

**Deteccion:**
```
atr_mult=2.0, use_close_only=False
max_depth_atr=None, min_total_reduction=0.60, lookback_bars=126
compression_threshold=0.95, tolerance=0.10
max_depth_pct=0.25, ascending_lows_tolerance=0.01
trend_template=False, volume_contraction=False
vol_filter=w1_t1.2
```

**Salida:**
```
trailing_atr_multiplier=2.5, target_r_multiple=2.0
early_exit_days=None, breakeven_r_multiple=0.5, max_stop_loss_pct=0.07
max_bars_without_progress=15, min_progress_r=0.5
```

---

## Detalle de trades — Variantes principales

### COMP#1: tr=1.5 tg=2R sl=3% no_filter VC — 14T, 79% WR, +59.56%

| # | Entry | Exit | Salida | PnL | R | MaxR | Dur |
|---|---|---|---|---|---|---|---|
| 1 | 2015-06-22 | 2015-06-29 | trailing_stop | +1.25% | +0.4R | 1.6R | 7d |
| 2 | 2015-06-30 | 2015-07-17 | target | +10.73% | +3.6R | 3.6R | 17d |
| 3 | 2016-10-21 | 2016-10-27 | stop_loss | -1.80% | -0.6R | 0.3R | 6d |
| 4 | 2017-01-06 | 2017-01-25 | target | +6.54% | +2.2R | 2.2R | 19d |
| 5 | 2017-01-26 | 2017-02-16 | time_exit | +0.80% | +0.3R | 0.4R | 21d |
| 6 | 2017-02-22 | 2017-04-11 | trailing_stop | +2.79% | +0.9R | 1.6R | 48d |
| 7 | 2017-04-20 | 2017-05-01 | target | +6.02% | +2.0R | 2.0R | 11d |
| 8 | 2017-05-02 | 2017-05-16 | stop_loss | -1.96% | -0.7R | 0.0R | 14d |
| 9 | 2017-05-17 | 2017-06-02 | target | +6.05% | +2.0R | 2.0R | 16d |
| 10 | 2018-04-26 | 2018-05-10 | target | +6.53% | +2.2R | 2.2R | 14d |
| 11 | 2018-05-11 | 2018-06-07 | trailing_stop | +0.64% | +0.2R | 1.2R | 27d |
| 12 | 2018-06-08 | 2018-06-20 | target | +6.82% | +2.3R | 2.3R | 12d |
| 13 | 2018-06-21 | 2018-06-27 | stop_loss | -2.81% | -0.9R | 0.0R | 6d |
| 14 | 2018-06-28 | 2018-07-17 | target | +7.01% | +2.3R | 2.3R | 19d |

### COMP#2: tr=2.5 tg=2R sl=7% w1_t1.2 lb=63 — 6T, 100% WR, +45.07%

| # | Entry | Exit | Salida | PnL | R | MaxR | Dur |
|---|---|---|---|---|---|---|---|
| 1 | 2015-06-22 | 2015-07-15 | time_exit | +5.92% | +0.9R | 1.0R | 23d |
| 2 | 2016-04-28 | 2016-05-19 | time_exit | +0.07% | +0.0R | 0.5R | 21d |
| 3 | 2016-07-27 | 2016-08-17 | time_exit | +0.84% | +0.2R | 0.3R | 21d |
| 4 | 2017-02-22 | 2017-04-20 | time_exit | +5.64% | +1.3R | 1.3R | 57d |
| 5 | 2018-04-26 | 2018-06-20 | target | +15.99% | +2.3R | 2.3R | 55d |
| 6 | 2018-06-25 | 2018-07-25 | target | +10.77% | +2.1R | 2.1R | 30d |

---

## Resultados Test (2020-01-02 a 2026-06-09)

### Tabla de resultados — Test

| Variante | T | W | L | WR | CR | MaxDD | Sharpe | avgR | PF |
|---|---|---|---|---|---|---|---|---|---|
| **Buy & Hold META** | — | — | — | — | +178.67% | -76.74% | — | — | — |
| **COMP#1** no_filter VC tr=1.5 tg=2R sl=3% | **27** | **15** | 12 | 56% | **+107.47%** | -15.09% | **0.96** | +0.98 | 3.3 |
| **COMP#2** w1_t1.2 lb=63 tr=2.5 tg=2R sl=7% | 10 | 6 | 4 | 60% | +66.32% | -16.92% | 0.65 | +0.82 | 4.2 |
| **COMP#3** w1_t1.2 VC lb=126 tr=2.5 tg=2R sl=7% | 11 | 7 | 4 | 64% | +78.27% | **-10.53%** | 0.75 | +0.83 | **5.2** |
| **COMP#4** w1_t1.2 lb=126 tr=2.5 tg=2R sl=7% | 12 | 8 | 4 | **67%** | +83.22% | **-10.53%** | 0.78 | +0.79 | 5.4 |

### Detalle de trades — COMP#1 (no_filter VC) — 27T, 56% WR, +107.47%

| # | Entry | Exit | Salida | PnL | R | MaxR | Dur |
|---|---|---|---|---|---|---|---|
| 1 | 2020-10-23 | 2020-10-28 | stop_loss | -6.01% | -2.0R | 0.0R | 5d |
| 2 | 2020-10-29 | 2020-10-30 | stop_loss | -6.31% | -2.1R | 0.0R | 1d |
| 3 | 2021-06-23 | 2021-07-15 | trailing_stop | +1.14% | +0.4R | 1.5R | 22d |
| 4 | 2021-08-25 | 2021-09-17 | trailing_stop | -1.00% | -0.3R | 1.2R | 23d |
| 5 | 2022-07-19 | 2022-07-22 | trailing_stop | -3.70% | -1.2R | 1.4R | 3d |
| 6 | 2023-03-14 | 2023-03-24 | target | +6.18% | +2.1R | 2.1R | 10d |
| 7 | 2023-03-27 | 2023-04-06 | target | +6.54% | +2.2R | 2.2R | 10d |
| 8 | 2023-04-10 | 2023-04-20 | trailing_stop | -0.78% | -0.3R | 1.0R | 10d |
| 9 | 2023-04-21 | 2023-04-27 | target | +12.06% | +4.0R | 4.0R | 6d |
| 10 | 2023-04-28 | 2023-05-05 | stop_loss | -3.14% | -1.0R | 0.4R | 7d |
| 11 | 2023-05-08 | 2023-05-22 | target | +6.45% | +2.2R | 2.2R | 14d |
| 12 | 2023-05-23 | 2023-05-26 | target | +6.20% | +2.1R | 2.1R | 3d |
| 13 | 2023-05-30 | 2023-06-15 | target | +7.36% | +2.5R | 2.5R | 16d |
| 14 | 2023-06-16 | 2023-07-11 | target | +6.15% | +2.1R | 2.1R | 25d |
| 15 | 2023-07-12 | 2023-07-20 | stop_loss | -2.20% | -0.7R | 0.7R | 8d |
| 16 | 2023-07-21 | 2023-07-28 | target | +10.61% | +3.5R | 3.5R | 7d |
| 17 | 2023-12-18 | 2024-01-02 | trailing_stop | +0.48% | +0.2R | 1.3R | 15d |
| 18 | 2024-01-03 | 2024-01-10 | target | +7.55% | +2.5R | 2.5R | 7d |
| 19 | 2024-01-11 | 2024-01-25 | target | +6.36% | +2.1R | 2.1R | 14d |
| 20 | 2024-01-26 | 2024-02-02 | target | +20.51% | +6.8R | 6.8R | 7d |
| 21 | 2024-06-05 | 2024-07-05 | target | +9.06% | +3.0R | 3.0R | 30d |
| 22 | 2024-09-19 | 2024-10-04 | target | +6.59% | +2.2R | 2.2R | 15d |
| 23 | 2024-10-07 | 2024-10-21 | stop_loss | -1.65% | -0.5R | 0.5R | 14d |
| 24 | 2024-10-22 | 2024-10-23 | stop_loss | -3.15% | -1.0R | 0.0R | 1d |
| 25 | 2024-10-24 | 2024-10-31 | trailing_stop | -0.04% | -0.0R | 1.5R | 7d |
| 26 | 2025-07-31 | 2025-08-01 | stop_loss | -3.03% | -1.0R | 0.0R | 1d |
| 27 | 2025-08-04 | 2025-08-19 | stop_loss | -3.21% | -1.1R | 0.6R | 15d |

### Detalle de trades — COMP#4 (w1_t1.2) — 12T, 67% WR, +83.22%

| # | Entry | Exit | Salida | PnL | R | MaxR | Dur |
|---|---|---|---|---|---|---|---|
| 1 | 2020-10-29 | 2020-11-09 | trailing_stop | -0.73% | -0.1R | 0.7R | 11d |
| 2 | 2021-04-29 | 2021-05-10 | stop_loss | -7.14% | -1.0R | 0.0R | 11d |
| 3 | 2021-06-28 | 2021-07-19 | stop_loss | -5.26% | -0.8R | 0.0R | 21d |
| 4 | 2021-09-15 | 2021-09-20 | stop_loss | -4.87% | -0.8R | 0.0R | 5d |
| 5 | 2023-03-14 | 2023-04-14 | target | +14.16% | +2.0R | 2.0R | 31d |
| 6 | 2023-04-26 | 2023-04-28 | target | +14.77% | +2.1R | 2.1R | 2d |
| 7 | 2023-05-03 | 2023-06-01 | target | +15.01% | +2.1R | 2.1R | 29d |
| 8 | 2023-06-16 | 2023-07-21 | trailing_stop | +4.72% | +0.7R | 1.8R | 35d |
| 9 | 2023-07-26 | 2023-08-09 | trailing_stop | +2.22% | +0.3R | 1.3R | 14d |
| 10 | 2024-01-10 | 2024-02-02 | target | +28.21% | +4.0R | 4.0R | 23d |
| 11 | 2024-06-21 | 2024-07-12 | trailing_stop | +0.83% | +0.1R | 1.3R | 21d |
| 12 | 2025-07-31 | 2025-08-21 | stop_loss | -4.44% | -0.6R | 0.3R | 21d |

---

## Comparacion Train vs Test

| Metrica | COMP#1 Train | COMP#1 Test | COMP#3 Train | COMP#3 Test | COMP#4 Train | COMP#4 Test |
|---|---|---|---|---|---|---|
| Trades | 14 | **27** | 6 | 11 | 7 | 12 |
| WR | 79% | 56% | 83% | 64% | 86% | **67%** |
| CR | +59.56% | **+107.47%** | +44.03% | +78.27% | +45.23% | +83.22% |
| MaxDD | -2.81% | -15.09% | -1.12% | **-10.53%** | -1.12% | **-10.53%** |
| Sharpe | 1.45 | **0.96** | 1.24 | 0.75 | 1.18 | 0.78 |
| avgR | +1.16 | +0.98 | +1.11 | +0.83 | +0.98 | +0.79 |
| PF | 8.4 | 3.3 | 35.4 | **5.2** | 36.2 | **5.4** |

---

## Observaciones

1. **META es el mejor ticker del proyecto en v2.** COMP#1 logra +107% CR en test con 27 trades — mas que cualquier otro ticker. Sharpe 0.96 en test con MaxDD -15% vs -77% del B&H.

2. **no_filter con VC=True domina**: el volume contraction filter (ratio<=0.85) descarta senales sin contraccion de volumen real, pero no requiere spike de volumen en breakout. El pipeline VC=True + no_filter es mas selectivo que vol_filter solo.

3. **compression_threshold=0.95 es critico para META** — a diferencia de otros tickers que usan 0.85. Las contracciones de ATR de META son mas sutiles.

4. **use_close_only=False (HL) es mejor** — opuesto a GOOGL (que necesita Close). META tiene mechas informativas que ayudan a definir los swings.

5. **El trailing tight (tr=1.5) genera alta rotacion**: 14T en train, 27T en test. El target=2R corta ganadores temprano pero protege retorno, generando una cadena de trades frecuentes en 2023.

6. **La racha mar-jul 2023 es el motor del test**: 11 trades consecutivos durante el recovery post-crash 2022, incluyendo el trade #20 (+20.51%, gap post-earnings Q4 2023).

7. **COMP#4 (w1_t1.2, sin VC) tiene mejor risk-adjusted en test**: PF 5.4, MaxDD -10.53%, WR 67%. El vol_filter backward elimina los 2 trades toxicos de oct 2020 (-6% cada uno).

8. **COMP#2 (lb=63) degrada mas en test**: 100% WR en train cae a 60% en test. El lookback corto captura patrones menos robustos que lb=126.

---

## Conclusion

META es el ticker ideal para VCP: alta liquidez, breakouts frecuentes con volumen, y tendencias sostenidas post-breakout. La config ganadora **COMP#1 (no_filter, VC=True, tr=1.5, tg=2R, sl=3%)** produce:

- +59.56% CR en train (14T, 79% WR, Sharpe 1.45)
- +107.47% CR en test (27T, 56% WR, Sharpe 0.96) — el mejor resultado absoluto del proyecto
- Supera al B&H en risk-adjusted (MaxDD -15% vs -77%)
- ~4.2 trades/ano en test: alta rotacion con trailing tight + target fijo

**Hallazgo clave**: para META, el volume contraction filter (VC) ya provee suficiente filtrado. Agregar vol_filter de breakout (w1_t1.2 o similar) reduce trade count de 27 a 10-12 sin mejorar calidad por trade. A diferencia de GOOGL/AAPL donde el vol_filter es critico, META genera breakouts con volumen naturalmente alto.

### Alternativa conservadora

**COMP#4 (w1_t1.2, tr=2.5, tg=2R, sl=7%)** ofrece +83.22% CR en test con PF 5.4 y MaxDD -10.53% — mejor risk-adjusted a costa de retorno absoluto.
