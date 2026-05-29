# AAPL — Optimizacion Profunda v2 (Train 2015-2019)

## Objetivo

Optimizar la deteccion de patrones VCP para AAPL con mejoras respecto a v1:
- Volumen en breakout como post-filtro sistematico (7 variantes)
- 3 perfiles de salida en Fase 1 para ranking robusto (trail 1.5/2.5/3.5)
- Seleccion multi-criterio: top 10 por CR + top 10 por WR
- Fase 2 sobre ~18 candidatos (no solo el top 1)
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

### Fase 2: Salida (720 configs x 18 candidatos = 12,960 evaluaciones)

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
| atr_mult | 2.0 | +8.80% | +1.82% (4.0) | Domina ampliamente, igual que v1 |
| lookback_bars | 126 | +6.62% | +2.46% (63) | 6 meses captura patrones mas completos |
| use_close_only | False (HL) | +6.33% | +2.75% (True) | High/Low detecta extremos mas precisos |
| trend_template | False | +5.93% | +3.15% (True) | TT sobrefiltra en AAPL |

### Parametros con impacto moderado

| Parametro | Observacion |
|---|---|
| reduction | 0.80 mejor (+5.65%), 0.40 peor (+2.82%) |
| max_depth_atr | mda=8 ligeramente mejor (+5.03%), None menos (+4.22%) |
| comp_thresh | 0.95 mejor (+4.92%), 0.85 y 0.90 similares |
| vol_contraction | Sin VC: +5.16%, con VC: +3.92%. VC reduce senales pero mejora WR |
| vol_filter | no_filter: +6.38%, w3_t1.2: +4.16%. Sin filtro mejor avg pero menos robusto |

### Parametros sin impacto (para AAPL)

| Parametro | Observacion |
|---|---|
| tolerance | 0.10, 0.15, 0.20 dan resultados identicos |
| max_depth_pct | 0.25, 0.30, 0.35 practicamente iguales |
| ascending_lows_tolerance | 0.01, 0.03, 0.08 casi sin diferencia |

### Estabilidad entre exit profiles

Correlacion entre CRs de los 3 perfiles de salida (tight/medium/loose):
- tight-medium: 0.776
- tight-loose: 0.740
- medium-loose: 0.892

Las configs de deteccion mantienen su ranking relativo independientemente del trailing.
Esto confirma que usar 1 salida fija en v1 no era un problema grave, pero 3 es mas robusto.

---

## Deteccion base elegida

Todas las variantes top comparten la misma base de deteccion:

```
atr_mult=2.0, use_close_only=False (HL)
max_depth_atr=6, min_total_reduction=0.80, lookback_bars=126
compression_threshold=0.85 o 0.95 (segun variante)
trend_template=False
```

Lo que varia entre ellas es: volume_contraction (on/off), vol_filter, y config de salida.

---

## Tabla comparativa — Train (2015-2019)

### Mejores por CR (retorno acumulado)

| Variante | T | W | L | WR | CR | CAGR | MaxDD | Sharpe | avgR | PF | Exp |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **Buy & Hold AAPL** | — | — | — | — | +168.59% | 21.88% | -38.73% | 0.92 | — | — | 100% |
| **CR#1** tr=2.0 tg=2R sl=5% no_filter | 14 | 10 | 4 | 71% | +57.75% | 11.54% | -3.64% | 2.76 | +0.68 | 7.7 | 14% |
| **CR#2** tr=2.0 tg=2R sl=5% no_filter comp=0.85 | 11 | 8 | 3 | 73% | +56.01% | 11.24% | -2.10% | 3.53 | +0.84 | 14.3 | 12% |
| **CR#3** tr=2.0 tg=2R sl=5% no_filter VC | 8 | 7 | 1 | 88% | +54.28% | 22.04% | -0.95% | 5.10 | +1.13 | 48.7 | 9% |

### Mejores por WR (win rate)

| Variante | T | W | L | WR | CR | CAGR | MaxDD | Sharpe | avgR | PF | Exp |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **Buy & Hold AAPL** | — | — | — | — | +168.59% | 21.88% | -38.73% | 0.92 | — | — | 100% |
| **WR#1** tr=1.0 tg=3R sl=3% w5_t1.2 | 4 | 4 | 0 | 100% | +24.43% | 8.31% | 0.00% | 7.47 | +1.88 | inf | 4% |
| **WR#2** tr=2.0 tg=2R sl=3% w3_t1.2 | 11 | 9 | 2 | 82% | +47.91% | 9.83% | -3.28% | 4.08 | +1.23 | 8.6 | 8% |
| **WR#3** tr=2.0 tg=2R sl=5% no_filter VC | 8 | 7 | 1 | 88% | +54.28% | 22.04% | -0.95% | 5.10 | +1.13 | 48.7 | 9% |

### Mejores por composite (50% CR + 30% WR + 20% avg_R)

| Variante | Comp | T | W | L | WR | CR | CAGR | MaxDD | Sharpe | avgR | PF | Exp |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **Buy & Hold AAPL** | — | — | — | — | — | +168.59% | 21.88% | -38.73% | 0.92 | — | — | 100% |
| **COMP#1** tr=2.0 tg=2R sl=5% no_filter VC | 0.710 | 8 | 7 | 1 | 88% | +54.28% | 22.04% | -0.95% | 5.10 | +1.13 | 48.7 | 9% |
| **COMP#2** tr=2.0 tg=2R sl=3% be=1.5 w3_t1.2 | 0.581 | 11 | 9 | 2 | 82% | +47.91% | 9.83% | -3.28% | 4.08 | +1.23 | 8.6 | 8% |
| **COMP#3** tr=2.0 tg=2R sl=5% no_filter comp=0.85 | 0.555 | 11 | 8 | 3 | 73% | +56.01% | 11.24% | -2.10% | 3.53 | +0.84 | 14.3 | 12% |

---

## Configuraciones completas de las variantes

### COMP#1 / CR#3 / WR#3 — La variante ganadora

**Deteccion:**
```
atr_mult=2.0, use_close_only=False
max_depth_atr=6, min_total_reduction=0.80, lookback_bars=126
compression_threshold=0.85, tolerance=0.10
max_depth_pct=0.25, ascending_lows_tolerance=0.01
trend_template=False, volume_contraction=True (ratio<=0.85)
vol_filter=no_filter
```

**Salida:**
```
trailing_atr_multiplier=2.0, target_r_multiple=2.0
early_exit_days=None, breakeven_r_multiple=1.0, max_stop_loss_pct=0.05
max_bars_without_progress=15, min_progress_r=0.5
```

### COMP#2 / WR#2

**Deteccion:**
```
atr_mult=2.0, use_close_only=False
max_depth_atr=6, min_total_reduction=0.80, lookback_bars=126
compression_threshold=0.85, tolerance=0.10
max_depth_pct=0.25, ascending_lows_tolerance=0.01
trend_template=False, volume_contraction=False
vol_filter=w3_t1.2 (volumen >= 1.2x avg en ventana de 3 dias)
```

**Salida:**
```
trailing_atr_multiplier=2.0, target_r_multiple=2.0
early_exit_days=None, breakeven_r_multiple=1.5, max_stop_loss_pct=0.03
max_bars_without_progress=15, min_progress_r=0.5
```

### CR#1 — Mayor retorno absoluto

**Deteccion:**
```
atr_mult=2.0, use_close_only=False
max_depth_atr=6, min_total_reduction=0.80, lookback_bars=126
compression_threshold=0.95, tolerance=0.10
max_depth_pct=0.25, ascending_lows_tolerance=0.01
trend_template=False, volume_contraction=False
vol_filter=no_filter
```

**Salida:**
```
trailing_atr_multiplier=2.0, target_r_multiple=2.0
early_exit_days=None, breakeven_r_multiple=1.0, max_stop_loss_pct=0.05
max_bars_without_progress=15, min_progress_r=0.5
```

### WR#1 — 100% win rate

**Deteccion:**
```
atr_mult=2.0, use_close_only=False
max_depth_atr=None, min_total_reduction=0.60, lookback_bars=63
compression_threshold=0.85, tolerance=0.10
max_depth_pct=0.25, ascending_lows_tolerance=0.01
trend_template=False, volume_contraction=False
vol_filter=w5_t1.2
```

**Salida:**
```
trailing_atr_multiplier=1.0, target_r_multiple=3.0
early_exit_days=None, breakeven_r_multiple=1.0, max_stop_loss_pct=0.03
max_bars_without_progress=15, min_progress_r=0.5
```

---

## Detalle de trades — Variantes principales

### COMP#1: tr=2.0 tg=2R sl=5% no_filter VC — 8T, 88% WR, +54.28%

| # | Entry | Exit | Salida | PnL | R | MaxR | Dur |
|---|---|---|---|---|---|---|---|
| 1 | 2017-10-27 | 2017-11-15 | trailing_stop | +3.70% | +0.8R | 1.6R | 19d |
| 2 | 2017-11-16 | 2017-11-29 | stop_loss | -0.95% | -0.2R | 0.5R | 13d |
| 3 | 2018-07-25 | 2018-08-17 | target | +11.68% | +2.3R | 2.3R | 23d |
| 4 | 2018-08-20 | 2018-09-07 | trailing_stop | +2.71% | +0.5R | 1.2R | 18d |
| 5 | 2018-09-10 | 2018-10-02 | time_exit | +5.02% | +1.0R | 1.0R | 22d |
| 6 | 2019-03-11 | 2019-03-26 | trailing_stop | +4.41% | +0.9R | 1.8R | 15d |
| 7 | 2019-03-27 | 2019-04-23 | target | +10.09% | +2.0R | 2.0R | 27d |
| 8 | 2019-12-06 | 2019-12-31 | open | +8.47% | +1.7R | 1.7R | 25d |

### COMP#2: tr=2.0 tg=2R sl=3% w3_t1.2 — 11T, 82% WR, +47.91%

| # | Entry | Exit | Salida | PnL | R | MaxR | Dur |
|---|---|---|---|---|---|---|---|
| 1 | 2015-10-28 | 2015-11-10 | stop_loss | -2.10% | -0.7R | 0.9R | 13d |
| 2 | 2016-07-27 | 2016-08-15 | target | +6.34% | +2.1R | 2.1R | 19d |
| 3 | 2017-10-27 | 2017-11-06 | target | +6.87% | +2.3R | 2.3R | 10d |
| 4 | 2017-11-07 | 2017-11-15 | stop_loss | -3.28% | -1.1R | 0.3R | 8d |
| 5 | 2018-08-01 | 2018-08-17 | target | +7.98% | +2.7R | 2.7R | 16d |
| 6 | 2018-08-20 | 2018-09-07 | trailing_stop | +2.71% | +0.9R | 2.0R | 18d |
| 7 | 2018-09-10 | 2018-10-03 | target | +6.29% | +2.1R | 2.1R | 23d |
| 8 | 2019-03-15 | 2019-03-26 | trailing_stop | +0.36% | +0.1R | 1.6R | 11d |
| 9 | 2019-03-27 | 2019-04-08 | target | +6.17% | +2.1R | 2.1R | 12d |
| 10 | 2019-12-10 | 2019-12-26 | target | +7.98% | +2.7R | 2.7R | 16d |
| 11 | 2019-12-27 | 2019-12-31 | open | +1.33% | +0.4R | 0.4R | 4d |

### WR#1: tr=1.0 tg=3R sl=3% w5_t1.2 — 4T, 100% WR, +24.43%

| # | Entry | Exit | Salida | PnL | R | MaxR | Dur |
|---|---|---|---|---|---|---|---|
| 1 | 2016-07-27 | 2016-08-24 | trailing_stop | +4.93% | +1.6R | 2.1R | 28d |
| 2 | 2017-10-27 | 2017-11-14 | trailing_stop | +5.08% | +1.7R | 2.7R | 18d |
| 3 | 2019-03-15 | 2019-03-22 | trailing_stop | +2.65% | +0.9R | 1.6R | 7d |
| 4 | 2019-03-25 | 2019-04-23 | target | +9.93% | +3.3R | 3.3R | 29d |

### CR#1: tr=2.0 tg=2R sl=5% no_filter — 14T, 71% WR, +57.75%

| # | Entry | Exit | Salida | PnL | R | MaxR | Dur |
|---|---|---|---|---|---|---|---|
| 1 | 2015-10-28 | 2015-11-10 | stop_loss | -2.10% | -0.5R | 0.6R | 13d |
| 2 | 2016-07-27 | 2016-08-29 | trailing_stop | +3.76% | +0.8R | 1.3R | 33d |
| 3 | 2016-08-30 | 2016-09-08 | stop_loss | -0.45% | -0.1R | 0.4R | 9d |
| 4 | 2017-10-27 | 2017-11-15 | trailing_stop | +3.70% | +0.8R | 1.6R | 19d |
| 5 | 2017-11-16 | 2017-11-29 | stop_loss | -0.95% | -0.2R | 0.5R | 13d |
| 6 | 2018-07-25 | 2018-08-17 | target | +11.68% | +2.3R | 2.3R | 23d |
| 7 | 2018-08-20 | 2018-09-07 | trailing_stop | +2.71% | +0.5R | 1.2R | 18d |
| 8 | 2018-09-10 | 2018-10-02 | time_exit | +5.02% | +1.0R | 1.0R | 22d |
| 9 | 2019-03-11 | 2019-03-26 | trailing_stop | +4.41% | +0.9R | 1.8R | 15d |
| 10 | 2019-03-27 | 2019-04-23 | target | +10.09% | +2.0R | 2.0R | 27d |
| 11 | 2019-05-01 | 2019-05-07 | stop_loss | -3.64% | -0.7R | 0.1R | 6d |
| 12 | 2019-11-01 | 2019-12-03 | trailing_stop | +1.42% | +0.3R | 0.9R | 32d |
| 13 | 2019-12-04 | 2019-12-26 | target | +10.76% | +2.2R | 2.2R | 22d |
| 14 | 2019-12-27 | 2019-12-31 | open | +1.33% | +0.3R | 0.3R | 4d |

---

## Observaciones

1. **COMP#1 es la variante mas equilibrada**: 88% WR, Sharpe 5.10, MaxDD -0.95%, PF 48.7. Solo 1 loss de -0.95%. El filtro de volume_contraction elimina las senales ruidosas de 2015-2016.

2. **target=2R domina** en todos los top combos. Libera capital rapido y permite re-entradas. En v1 habiamos elegido target=None, pero la grilla completa muestra que 2R es superior para AAPL train (+57.75% vs +51.03% con la misma deteccion).

3. **Volume contraction mejora calidad**: COMP#1 (VC=Y) tiene 8 trades con 88% WR vs CR#1 (VC=N) con 14 trades y 71% WR. VC filtra senales que no tienen volumen decreciente durante la formacion.

4. **Vol filter w3_t1.2 aparece en COMP#2**: la confirmacion de volumen en breakout (1.2x en ventana de 3 dias) mejora WR a 82% y elimina re-entradas falsas.

5. **WR#1 (100% WR) es demasiado conservadora**: solo 4 trades en 5 anos, CR +24%. Usa trail=1.0 (muy ajustado) y sl=3%, lo que descarta cualquier trade que no sea perfecto.

6. **Los 3 parametros sin efecto en AAPL** (tolerance, max_depth_pct, ascending_lows_tolerance) podrian eliminarse de la grilla para este ticker, reduciendo el espacio de busqueda de 34,992 a 1,296.

7. **Exposicion muy baja** (4-14%): el capital esta libre >86% del tiempo en todas las variantes.

---

## Comparacion v1 vs v2

| Metrica | v1 mejor (sin TT) | v2 COMP#1 |
|---|---|---|
| Deteccion | comp=0.95, sin VC, sin vol_filter | comp=0.85, VC=Y, sin vol_filter |
| Salida | trail=2.5, target=None, sl=5% | trail=2.0, target=2R, sl=5% |
| Trades | 7 | 8 |
| WR | 86% | 88% |
| CR | +37.91% | +54.28% |
| Sharpe | 1.06 | 5.10 |
| MaxDD | -5.27% | -0.95% |
| avgR | +1.00 | +1.13 |

v2 encuentra una config significativamente mejor en todas las metricas. La clave es volume_contraction=True (filtra senales ruidosas) y target=2R (libera capital para re-entradas).

---

## Resultados Test (2020-01-02 a 2026-04-08)

Se evaluaron las 3 variantes top por composite en 1,574 barras (6.2 anos) de datos out-of-sample.
AAPL estuvo en Stage 2 solo el 28% del periodo de test (445 de 1574 dias).

### Tabla de resultados — Test

| Variante | T | W | L | WR | CR | CAGR | MaxDD | Sharpe | avgR | PF | Exp |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **Buy & Hold AAPL** | — | — | — | — | +244.80% | 21.85% | -33.43% | 0.79 | — | — | 100% |
| **COMP#1** VC=Y, no_filter, tr=2.0 tg=2R sl=5% | 7 | 5 | 2 | 71% | +33.04% | 6.31% | -5.45% | 2.35 | +0.94 | 6.1 | 8% |
| **COMP#2** VC=N, w3_t1.2, tr=2.0 tg=2R sl=3% be=1.5 | 16 | 10 | 6 | 62% | +49.78% | 8.15% | -4.51% | 2.59 | +0.88 | 4.1 | 11% |
| **COMP#3** VC=N, no_filter, tr=2.0 tg=2R sl=5% | 16 | 10 | 6 | 62% | +55.22% | 8.88% | -6.73% | 1.79 | +0.62 | 3.5 | 14% |

### Detalle de trades — COMP#1 (VC=Y, no_filter) — 7T, 71% WR, +33.04%

| # | Entry | Exit | Salida | PnL | R | MaxR | Dur |
|---|---|---|---|---|---|---|---|
| 1 | 2020-12-01 | 2020-12-28 | target | +11.38% | +2.3R | 2.3R | 27d |
| 2 | 2023-03-20 | 2023-05-05 | target | +10.27% | +2.1R | 2.1R | 46d |
| 3 | 2023-05-08 | 2023-05-30 | time_exit | +2.19% | +0.4R | 0.4R | 22d |
| 4 | 2023-05-31 | 2023-06-30 | target | +9.43% | +2.5R | 2.5R | 30d |
| 5 | 2023-12-05 | 2023-12-29 | stop_loss | -0.46% | -0.1R | 0.8R | 24d |
| 6 | 2025-07-01 | 2025-07-25 | time_exit | +2.92% | +0.6R | 0.6R | 24d |
| 7 | 2025-07-28 | 2025-08-01 | stop_loss | -5.45% | -1.1R | 0.0R | 4d |

### Detalle de trades — COMP#2 (w3_t1.2) — 16T, 62% WR, +49.78%

| # | Entry | Exit | Salida | PnL | R | MaxR | Dur |
|---|---|---|---|---|---|---|---|
| 1 | 2020-06-11 | 2020-06-22 | target | +6.84% | +2.3R | 2.3R | 11d |
| 2 | 2020-06-23 | 2020-06-26 | stop_loss | -3.52% | -1.2R | 0.0R | 3d |
| 3 | 2020-06-29 | 2020-07-10 | target | +6.05% | +2.0R | 2.0R | 11d |
| 4 | 2020-07-13 | 2020-07-23 | stop_loss | -2.76% | -0.9R | 1.0R | 10d |
| 5 | 2020-12-01 | 2020-12-22 | target | +7.46% | +2.5R | 2.5R | 21d |
| 6 | 2020-12-23 | 2021-01-04 | stop_loss | -1.18% | -0.4R | 1.5R | 12d |
| 7 | 2021-01-05 | 2021-01-06 | stop_loss | -3.37% | -1.1R | 0.0R | 1d |
| 8 | 2021-01-07 | 2021-01-22 | target | +6.23% | +2.1R | 2.1R | 15d |
| 9 | 2022-07-29 | 2022-08-15 | target | +6.57% | +2.2R | 2.2R | 17d |
| 10 | 2022-08-31 | 2022-09-13 | stop_loss | -2.15% | -0.7R | 1.3R | 13d |
| 11 | 2023-03-20 | 2023-04-19 | target | +6.50% | +2.2R | 2.2R | 30d |
| 12 | 2023-05-05 | 2023-05-26 | time_exit | +1.07% | +0.4R | 0.4R | 21d |
| 13 | 2023-05-31 | 2023-06-27 | target | +6.10% | +2.0R | 2.0R | 27d |
| 14 | 2023-12-05 | 2023-12-29 | stop_loss | -0.46% | -0.2R | 0.8R | 24d |
| 15 | 2025-07-01 | 2025-07-24 | time_exit | +2.86% | +1.0R | 1.1R | 23d |
| 16 | 2025-07-31 | 2025-08-07 | target | +6.00% | +2.0R | 2.0R | 7d |

### Detalle de trades — COMP#3 (no_filter, sin VC) — 16T, 62% WR, +55.22%

| # | Entry | Exit | Salida | PnL | R | MaxR | Dur |
|---|---|---|---|---|---|---|---|
| 1 | 2020-06-01 | 2020-06-11 | trailing_stop | +4.37% | +0.9R | 1.9R | 10d |
| 2 | 2020-06-12 | 2020-07-06 | target | +10.35% | +2.1R | 2.1R | 24d |
| 3 | 2020-07-07 | 2020-07-23 | trailing_stop | -0.35% | -0.1R | 1.1R | 16d |
| 4 | 2020-12-01 | 2020-12-28 | target | +11.38% | +2.3R | 2.3R | 27d |
| 5 | 2020-12-29 | 2021-01-06 | stop_loss | -6.13% | -1.2R | 0.0R | 8d |
| 6 | 2021-01-07 | 2021-01-29 | trailing_stop | +0.79% | +0.2R | 1.9R | 22d |
| 7 | 2022-07-07 | 2022-07-29 | target | +11.04% | +2.2R | 2.2R | 22d |
| 8 | 2022-08-01 | 2022-08-22 | trailing_stop | +3.75% | +0.8R | 1.6R | 21d |
| 9 | 2022-08-23 | 2022-08-26 | stop_loss | -2.16% | -0.4R | 0.3R | 3d |
| 10 | 2022-08-29 | 2022-09-13 | stop_loss | -4.67% | -0.9R | 0.3R | 15d |
| 11 | 2023-03-20 | 2023-05-05 | target | +10.27% | +2.1R | 2.1R | 46d |
| 12 | 2023-05-08 | 2023-05-30 | time_exit | +2.19% | +0.4R | 0.4R | 22d |
| 13 | 2023-05-31 | 2023-06-30 | target | +9.43% | +2.5R | 2.5R | 30d |
| 14 | 2023-12-05 | 2023-12-29 | stop_loss | -0.46% | -0.1R | 0.8R | 24d |
| 15 | 2025-07-01 | 2025-07-25 | time_exit | +2.92% | +0.6R | 0.6R | 24d |
| 16 | 2025-07-28 | 2025-08-01 | stop_loss | -5.45% | -1.1R | 0.0R | 4d |

---

## Comparacion Train vs Test

| Metrica | COMP#1 Train | COMP#1 Test | COMP#2 Train | COMP#2 Test | COMP#3 Train | COMP#3 Test |
|---|---|---|---|---|---|---|
| Trades | 8 | 7 | 11 | 16 | 11 | 16 |
| WR | 88% | 71% | 82% | 62% | 73% | 62% |
| CR | +54.28% | +33.04% | +47.91% | +49.78% | +56.01% | +55.22% |
| MaxDD | -0.95% | -5.45% | -3.28% | -4.51% | -2.10% | -6.73% |
| Sharpe | 5.10 | 2.35 | 4.08 | 2.59 | 3.53 | 1.79 |
| avg_R | +1.13 | +0.94 | +1.23 | +0.88 | +0.84 | +0.62 |

### Observaciones del test

1. **COMP#2 y COMP#3 generalizan excelente en CR**: COMP#2 +47.91% train -> +49.78% test, COMP#3 +56.01% -> +55.22%. Practicamente sin degradacion en retorno.

2. **COMP#1 (la ganadora en train) fue la peor en test**: VC=Y genera solo 7 trades en 6 anos. La degradacion de WR (88% -> 71%) y el loss de -5.45% en 2025 la perjudican. Senal de que VC sobrefiltra en test.

3. **COMP#2 es la mejor balanceada en test**: mejor Sharpe (2.59), MaxDD controlado (-4.51%), y CR solido (+49.78%). El filtro w3_t1.2 genera suficientes trades (16) sin dejar pasar demasiado ruido.

4. **COMP#3 tiene el mejor CR en test (+55.22%)** pero peor Sharpe (1.79) y MaxDD (-6.73%). Sin filtros de volumen captura mas senales pero tambien mas losses (3 stops de -2% a -6%).

5. **Todas controlan el drawdown** mucho mejor que buy & hold: -4.5% a -6.7% vs -33.4% del activo.

6. **Distribucion temporal razonable**: trades en 2020, 2021, 2022, 2023 y 2025 para COMP#2 y COMP#3. Solo 2024 queda sin trades. COMP#1 tiene un hueco de 2021-2022.

7. **WR baja en test para todas las variantes** (~10-20 puntos). Esperado al pasar a datos no vistos con mayor volatilidad (COVID-2020, caida 2022).

---

## Conclusion

**COMP#2 (w3_t1.2, tr=2.0, tg=2R, sl=3%)** es la variante recomendada:
- Generaliza excelente: CR +47.91% train -> +49.78% test
- Mejor Sharpe en test (2.59)
- Drawdown controlado (-4.51%)
- 16 trades en 6 anos — suficiente muestra
- El filtro de volumen en breakout (1.2x en ventana 3 dias) mejora calidad sin sobrerestringir

Graficos y datos detallados en MLflow (experimento VCP_AAPL_DeepPerTicker_v2).

---

## Proximos pasos

- Repetir el analisis para AMZN, GOOGL, MSFT, NVDA
- Evaluar si los parametros de deteccion son transferibles entre tickers
