# TSLA — Optimizacion Profunda v2 (Train 2015-2019)

## Objetivo

Optimizar la deteccion de patrones VCP para TSLA con mejoras respecto a v1:
- Volumen en breakout como post-filtro sistematico (7 variantes)
- 3 perfiles de salida en Fase 1 para ranking robusto (trail 1.5/2.5/3.5)
- Seleccion multi-criterio: top 10 por CR + top 10 por WR
- Fase 2 sobre 16 candidatos (no solo el top 1)
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

### Fase 2: Salida (720 configs x 16 candidatos = 11,520 evaluaciones)

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
| atr_mult | 2.0 | -0.36% | -0.05% (4.0) | 2.0 domina en cobertura (28960 vs 432 configs con trades) |
| use_close_only | **True (Close)** | +0.09% | -0.43% (False) | **Diferente a META/AAPL** — Close es mejor para TSLA |
| max_depth_pct | **0.35** | +1.38% | -0.88% (0.25) | 0.35 domina ampliamente, TSLA necesita profundidad flexible |
| lookback_bars | 126 | +0.37% | -0.71% (63) | lb=126 claramente superior |
| reduction | 0.80 | +0.18% | -0.11% (0.40) | 0.80 domina, 0.60 aceptable |
| trend_template | **False** | +0.15% | -0.49% (True) | TT=True produce 0 trades — Stage 2 muy corto para TSLA |

### Parametros con impacto moderado

| Parametro | Observacion |
|---|---|
| vol_filter | w3_t1.5/w5_t1.5 mejores (+0.70%), no_filter peor (-2.34%). Filtro de volumen muy critico |
| max_depth_atr | mda=8 mejor (+0.30%), mda=6 peor (-0.36%) |
| ascending_lows_tol | 0.08 mejor (+0.17%), 0.03 peor (-0.49%) |
| vol_contraction | Sin VC: -0.10%, con VC: -0.24%. Similar |

### Parametros sin impacto (para TSLA)

| Parametro | Observacion |
|---|---|
| tolerance | 0.10, 0.15, 0.20 practicamente iguales |
| comp_thresh | 0.85, 0.90, 0.95 — diferencia minima, 0.95 ligeramente mejor |

### Estabilidad entre exit profiles

Correlacion entre CRs de los 3 perfiles de salida (tight/medium/loose):
- tight-medium: 0.964
- tight-loose: 0.943
- medium-loose: 0.960

Estabilidad excepcionalmente alta — las mismas configs producen buenos resultados con cualquier perfil de salida.

---

## Deteccion base elegida

Las variantes top comparten deteccion similar con dos variaciones:

**COMP#1/COMP#2 (mda=None):**
```
atr_mult=2.0, use_close_only=True (Close)
max_depth_atr=None, min_total_reduction=0.80, lookback_bars=126
compression_threshold=0.95, tolerance=0.10
max_depth_pct=0.35, ascending_lows_tolerance=0.08
trend_template=False, volume_contraction=False
```

**COMP#3/Baseline (mda=8):**
```
atr_mult=2.0, use_close_only=True (Close)
max_depth_atr=8, min_total_reduction=0.80, lookback_bars=126
compression_threshold=0.95, tolerance=0.10
max_depth_pct=0.35, ascending_lows_tolerance=0.08
trend_template=False, volume_contraction=False
```

---

## Tabla comparativa — Train (2015-2019)

### Mejores por composite (50% CR + 30% WR + 20% avg_R)

| Variante | Comp | T | W | L | WR | CR | CAGR | MaxDD | Sharpe | avgR | PF |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **Buy & Hold TSLA** | — | — | — | — | — | +90.75% | 13.82% | -53.51% | — | — | — |
| **COMP#1** w3_t1.5 tr=1.5 tg=5R be=0.5 sl=7% | 0.980 | 4 | 4 | 0 | **100%** | **+130.87%** | **18.25%** | **0.00%** | **1.82** | **+3.41** | **inf** |
| **COMP#3** w1_t1.2 tr=1.5 tg=5R be=0.5 sl=7% | 0.804 | 5 | 5 | 0 | **100%** | +115.03% | 16.58% | **0.00%** | 1.37 | +2.46 | **inf** |
| **Baseline** no_filter tr=1.5 tg=5R be=0.5 sl=5% | 0.634 | **9** | 7 | 2 | 78% | +99.53% | 14.84% | -11.18% | 0.90 | +1.75 | 7.8 |

---

## Configuraciones completas de las variantes

### COMP#1 — La variante ganadora (w3_t1.5)

**Deteccion:**
```
atr_mult=2.0, use_close_only=True (Close)
max_depth_atr=None, min_total_reduction=0.80, lookback_bars=126
compression_threshold=0.95, tolerance=0.10
max_depth_pct=0.35, ascending_lows_tolerance=0.08
trend_template=False, volume_contraction=False
vol_filter=w3_t1.5 (volumen >= 1.5x avg en ventana de 3 dias)
```

**Salida:**
```
trailing_atr_multiplier=1.5, target_r_multiple=5.0
early_exit_days=None, breakeven_r_multiple=0.5, max_stop_loss_pct=0.07
max_bars_without_progress=15, min_progress_r=0.5
```

### COMP#3 — Vol filter w1_t1.2

**Deteccion:**
```
atr_mult=2.0, use_close_only=True (Close)
max_depth_atr=8, min_total_reduction=0.80, lookback_bars=126
compression_threshold=0.95, tolerance=0.10
max_depth_pct=0.35, ascending_lows_tolerance=0.08
trend_template=False, volume_contraction=False
vol_filter=w1_t1.2 (volumen >= 1.2x avg en ventana de 1 dia)
```

**Salida:**
```
trailing_atr_multiplier=1.5, target_r_multiple=5.0
early_exit_days=None, breakeven_r_multiple=0.5, max_stop_loss_pct=0.07
max_bars_without_progress=15, min_progress_r=0.5
```

### Baseline — Sin filtro de volumen

**Deteccion:**
```
atr_mult=2.0, use_close_only=True (Close)
max_depth_atr=8, min_total_reduction=0.80, lookback_bars=126
compression_threshold=0.95, tolerance=0.10
max_depth_pct=0.35, ascending_lows_tolerance=0.08
trend_template=False, volume_contraction=False
vol_filter=no_filter
```

**Salida:**
```
trailing_atr_multiplier=1.5, target_r_multiple=5.0
early_exit_days=None, breakeven_r_multiple=0.5, max_stop_loss_pct=0.05
```

---

## Detalle de trades — Variantes principales

### COMP#1: w3_t1.5 tr=1.5 tg=5R sl=7% — 4T, 100% WR, +130.87%

| # | Entry | Exit | Salida | PnL | R | MaxR | Dur |
|---|---|---|---|---|---|---|---|
| 1 | 2015-04-08 | 2015-07-07 | trailing_stop | +28.99% | +4.1R | 5.0R | 90d |
| 2 | 2015-07-08 | 2015-07-21 | trailing_stop | +4.63% | +0.7R | 1.5R | 13d |
| 3 | 2019-10-14 | 2019-11-12 | target | +36.18% | +5.2R | 5.2R | 29d |
| 4 | 2019-11-22 | 2019-12-31 | open | +25.61% | +3.7R | 4.2R | 39d |

### Baseline: no_filter tr=1.5 tg=5R sl=5% — 9T, 78% WR, +99.53%

| # | Entry | Exit | Salida | PnL | R | MaxR | Dur |
|---|---|---|---|---|---|---|---|
| 1 | 2015-04-08 | 2015-06-17 | target | +25.40% | +5.1R | 5.1R | 70d |
| 2 | 2015-06-18 | 2015-07-07 | trailing_stop | +2.29% | +0.5R | 1.4R | 19d |
| 3 | 2015-07-08 | 2015-07-21 | trailing_stop | +4.63% | +0.9R | 2.1R | 13d |
| 4 | 2015-12-01 | 2015-12-09 | stop_loss | -5.34% | -1.1R | 0.0R | 8d |
| 5 | 2015-12-30 | 2016-01-04 | stop_loss | -6.17% | -1.2R | 0.2R | 5d |
| 6 | 2018-12-03 | 2018-12-14 | trailing_stop | +2.01% | +0.4R | 1.0R | 11d |
| 7 | 2019-10-14 | 2019-10-25 | target | +27.70% | +5.5R | 5.5R | 11d |
| 8 | 2019-10-28 | 2019-11-22 | trailing_stop | +1.63% | +0.3R | 1.9R | 25d |
| 9 | 2019-11-25 | 2019-12-24 | target | +26.43% | +5.3R | 5.3R | 29d |

---

## Resultados Test (2020-01-02 a 2026-06-09)

### Tabla de resultados — Test

| Variante | T | W | L | WR | CR | MaxDD | Sharpe | avgR | PF |
|---|---|---|---|---|---|---|---|---|---|
| **Buy & Hold TSLA** | — | — | — | — | +1282.93% | -73.63% | — | — | — |
| **COMP#1** w3_t1.5 tr=1.5 tg=5R sl=7% | 7 | 5 | 2 | **71%** | **+79.63%** | **-7.18%** | **0.70** | **+1.37** | **9.6** |
| **COMP#3** w1_t1.2 tr=1.5 tg=5R sl=7% | 8 | 4 | 4 | 50% | +35.87% | -17.28% | 0.44 | +0.64 | 2.9 |
| **Baseline** no_filter tr=1.5 tg=5R sl=5% | **19** | 9 | 10 | 47% | +47.82% | -20.91% | 0.44 | +0.50 | 2.3 |

### Detalle de trades — COMP#1 (w3_t1.5) — 7T, 71% WR, +79.63%

| # | Entry | Exit | Salida | PnL | R | MaxR | Dur |
|---|---|---|---|---|---|---|---|
| 1 | 2020-11-18 | 2020-12-09 | trailing_stop | +24.22% | +3.5R | 4.8R | 21d |
| 2 | 2020-12-10 | 2020-12-21 | trailing_stop | +3.63% | +0.5R | 1.5R | 11d |
| 3 | 2020-12-22 | 2021-01-08 | target | +37.43% | +5.3R | 5.3R | 17d |
| 4 | 2021-01-11 | 2021-01-28 | trailing_stop | +2.99% | +0.4R | 1.3R | 17d |
| 5 | 2024-10-25 | 2024-10-31 | stop_loss | -7.18% | -1.0R | 0.0R | 6d |
| 6 | 2025-09-12 | 2025-09-25 | trailing_stop | +6.93% | +1.0R | 1.7R | 13d |
| 7 | 2025-10-02 | 2025-10-07 | trailing_stop | -0.67% | -0.1R | 0.6R | 5d |

### Detalle de trades — Baseline (no_filter) — 19T, 47% WR, +47.82%

| # | Entry | Exit | Salida | PnL | R | MaxR | Dur |
|---|---|---|---|---|---|---|---|
| 1 | 2020-11-18 | 2020-11-30 | trailing_stop | +16.64% | +3.3R | 4.1R | 12d |
| 2 | 2020-12-01 | 2020-12-09 | trailing_stop | +3.37% | +0.7R | 2.2R | 8d |
| 3 | 2020-12-10 | 2020-12-21 | trailing_stop | +3.63% | +0.7R | 2.2R | 11d |
| 4 | 2020-12-22 | 2021-01-07 | target | +27.44% | +5.5R | 5.5R | 16d |
| 5 | 2021-01-08 | 2021-01-11 | stop_loss | -7.82% | -1.6R | 0.0R | 3d |
| 6 | 2021-01-12 | 2021-01-28 | trailing_stop | -1.65% | -0.3R | 0.8R | 16d |
| 7 | 2021-01-29 | 2021-02-10 | trailing_stop | +1.42% | +0.3R | 2.0R | 12d |
| 8 | 2021-08-02 | 2021-08-16 | stop_loss | -3.31% | -0.7R | 0.4R | 14d |
| 9 | 2021-08-23 | 2021-09-20 | trailing_stop | +3.38% | +0.7R | 1.5R | 28d |
| 10 | 2024-10-25 | 2024-10-31 | stop_loss | -7.18% | -1.4R | 0.0R | 6d |
| 11 | 2025-08-11 | 2025-08-21 | stop_loss | -5.58% | -1.1R | 0.1R | 10d |
| 12 | 2025-08-22 | 2025-08-29 | trailing_stop | -1.81% | -0.4R | 0.7R | 7d |
| 13 | 2025-09-04 | 2025-09-17 | target | +25.80% | +5.2R | 5.2R | 13d |
| 14 | 2025-09-18 | 2025-09-25 | trailing_stop | +1.57% | +0.3R | 1.2R | 7d |
| 15 | 2025-09-26 | 2025-10-02 | trailing_stop | -1.00% | -0.2R | 0.9R | 6d |
| 16 | 2025-10-03 | 2025-10-07 | trailing_stop | +0.76% | +0.2R | 1.1R | 4d |
| 17 | 2025-10-08 | 2025-10-10 | stop_loss | -5.74% | -1.1R | 0.0R | 2d |
| 18 | 2025-10-13 | 2025-10-24 | trailing_stop | -0.50% | -0.1R | 0.6R | 11d |
| 19 | 2025-10-27 | 2025-11-04 | trailing_stop | -1.80% | -0.4R | 0.7R | 8d |

---

## Comparacion Train vs Test

| Metrica | COMP#1 Train | COMP#1 Test | Baseline Train | Baseline Test |
|---|---|---|---|---|
| Trades | 4 | 7 | 9 | **19** |
| WR | **100%** | **71%** | 78% | 47% |
| CR | **+130.87%** | **+79.63%** | +99.53% | +47.82% |
| MaxDD | 0.00% | **-7.18%** | -11.18% | -20.91% |
| Sharpe | **1.82** | **0.70** | 0.90 | 0.44 |
| avgR | **+3.41** | **+1.37** | +1.75 | +0.50 |
| PF | **inf** | **9.6** | 7.8 | 2.3 |

---

## Observaciones

1. **TSLA es un ticker de baja frecuencia VCP**: solo 4-9 trades en train (5 anos) y 7-19 en test (6.4 anos). Los patrones se concentran en 2015 y late 2019 (train), y en el rally de nov 2020 - ene 2021 (test). Gran brecha 2022-2024 sin trades.

2. **use_close_only=True (Close) es critico para TSLA** — opuesto a META/AAPL que prefieren HL. Las mechas de TSLA son extremas y generan falsos swings con HL.

3. **max_depth_pct=0.35 es inusual**: la mayoria de tickers usa 0.25. TSLA necesita tolerancia a drawdowns mas profundos porque sus contracciones son mas violentas.

4. **trend_template=True elimina TODOS los trades** — el Stage 2 de Minervini es muy restrictivo para TSLA, que tiene periodos largos de consolidacion lateral.

5. **Vol filter w3_t1.5 es el optimo**: filtra los 2 stop losses de dic 2015 (-5.34%, -6.17%) y el trade de dic 2018 (+2.01%), dejando solo los 4 trades explosivos. El trade #3 de oct 2019 (+36.18%) es el de mayor R del proyecto.

6. **El B&H en test es +1282.93%** — imposible de superar en retorno absoluto. Pero el B&H sufre MaxDD -73.63%. COMP#1 logra +79.63% con MaxDD -7.18% — superior en risk-adjusted.

7. **Los 4 primeros trades de COMP#1 en test (nov 2020 - ene 2021) son todos ganadores**: +24%/+4%/+37%/+3%. Captura el rally historico de TSLA pre/post S&P inclusion. El trade #3 (+37.43%, target 5R) es excepcional.

8. **Solo 1 loss en test para COMP#1**: oct 2024, -7.18% (stop_loss). Es un breakout fallido post-earnings Q3 2024.

9. **El Baseline (no_filter) produce demasiado ruido en test**: 19 trades, 47% WR, muchos trailing stops con perdidas menores. La rafaga de 9 trades en sep-nov 2025 (7 trailing stops + 1 target + 1 stop_loss) diluye el retorno.

10. **La estabilidad entre exit profiles es la mas alta del proyecto** (0.94-0.96). TSLA tiene tan pocos trades que las configs ganadoras son robustas a la eleccion de salida.

---

## Conclusion

TSLA es un ticker de baja frecuencia pero alta calidad VCP. La config ganadora **COMP#1 (w3_t1.5, tr=1.5, tg=5R, sl=7%)** produce:

- +130.87% CR en train (4T, 100% WR, Sharpe 1.82) — zero losses, zero drawdown
- +79.63% CR en test (7T, 71% WR, Sharpe 0.70) — PF 9.6, MaxDD solo -7.18%
- No supera al B&H (+1283%) en retorno absoluto, pero MaxDD -7% vs -74% B&H

**Hallazgo clave**: el vol_filter es extremadamente selectivo para TSLA — w3_t1.5 reduce de 9 a 4 trades en train, eliminando todas las perdidas. Los trades que pasan el filtro son explosivos (avgR +3.41R). La configuracion use_close_only=True y max_depth_pct=0.35 son especificas de TSLA y no se comparten con otros tickers.

### Alternativa conservadora

El **Baseline (no_filter)** ofrece mas trades (19 en test) pero menor calidad: WR 47%, CR +47.82%, MaxDD -20.91%. Para TSLA, menos es mas — el filtro estricto produce mejores resultados.
