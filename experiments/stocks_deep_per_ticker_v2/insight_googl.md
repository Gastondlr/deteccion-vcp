# GOOGL — Optimizacion Profunda v2 (Train 2015-2019)

## Objetivo

Optimizar la deteccion de patrones VCP para GOOGL con mejoras respecto a v1:
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
| atr_mult | 2.0 | +3.99% | +0.17% (4.0) | Domina ampliamente. 4.0 casi inutil |
| use_close_only | **True (Close)** | +3.92% | -0.72% (HL) | **Diferente a AAPL** — HL da CR negativo |
| max_depth_atr | 8 | +2.16% | +1.00% (None) | mda=8 mejor, consistente con AAPL |
| reduction | 0.80 | +2.73% | +0.32% (0.40) | Consistente con AAPL/AMZN |
| lookback_bars | 126 | +2.38% | +0.82% (63) | Consistente con AAPL/AMZN |
| trend_template | False | +2.11% | +1.09% (True) | Consistente con AAPL/AMZN |

### Parametros con impacto moderado

| Parametro | Observacion |
|---|---|
| comp_thresh | 0.95 mejor (+2.35%), 0.85 peor (+0.84%) |
| vol_contraction | Sin VC: +2.19%, con VC: +1.01%. VC restringe demasiado |
| vol_filter | no_filter: +2.65%, w3_t1.2: +1.68%, w1_t1.5: +1.07% |

### Parametros sin impacto (para GOOGL)

| Parametro | Observacion |
|---|---|
| tolerance | 0.10 ligeramente mejor, 0.15 y 0.20 identicos |
| max_depth_pct | 0.25, 0.30, 0.35 practicamente iguales |
| ascending_lows_tolerance | 0.01, 0.03, 0.08 sin diferencia apreciable |

### Estabilidad entre exit profiles

Correlacion entre CRs de los 3 perfiles de salida (tight/medium/loose):
- tight-medium: 0.922 (la mas alta de los 3 tickers)
- tight-loose: 0.763
- medium-loose: 0.768

Las configs de deteccion son muy estables entre exits en GOOGL.

---

## Deteccion base elegida

Todas las variantes top comparten la misma base de deteccion:

```
atr_mult=2.0, use_close_only=True (Close)
max_depth_atr=8, min_total_reduction=0.80, lookback_bars=126
compression_threshold=0.95, tolerance=0.10
max_depth_pct=0.25
trend_template=False, volume_contraction=False
```

Lo que varia entre ellas es: ascending_lows_tolerance (0.08/0.01), vol_filter, y config de salida.

---

## Tabla comparativa — Train (2015-2019)

### Mejores por CR (retorno acumulado)

| Variante | T | W | L | WR | CR | CAGR | MaxDD | avgR | PF | Exp |
|---|---|---|---|---|---|---|---|---|---|---|
| **Buy & Hold GOOGL** | — | — | — | — | +113.52% | 16.40% | -24.40% | — | — | 100% |
| **CR#1** tr=2.5 tg=2R early=3 be=1.5 sl=3% no_filter | 32 | 13 | 19 | 41% | +103.84% | 15.34% | -5.31% | +0.79 | — | — |
| **CR#2** tr=2.5 tg=2R early=3 be=0.5 sl=3% no_filter comp=0.90 | 29 | 13 | 16 | 45% | +99.03% | 14.78% | -5.31% | +0.84 | — | — |
| **CR#3** tr=2.5 tg=2R early=3 be=0.5 sl=3% no_filter w5_t1.2 | 24 | 11 | 13 | 46% | +85.27% | 13.14% | -3.90% | +0.78 | — | — |

### Mejores por WR (win rate, min 3 trades)

| Variante | T | W | L | WR | CR | CAGR | MaxDD | avgR | PF | Exp |
|---|---|---|---|---|---|---|---|---|---|---|
| **Buy & Hold GOOGL** | — | — | — | — | +113.52% | 16.40% | -24.40% | — | — | 100% |
| **WR#1** tr=2.5 tg=3R be=1.0 sl=5% w5_t1.2 VC=Y | 4 | 4 | 0 | 100% | +28.74% | — | 0.00% | +1.55 | inf | — |
| **WR#2** tr=2.5 tg=3R be=1.0 sl=5% w3_t1.2 VC=Y | 4 | 4 | 0 | 100% | +28.74% | — | 0.00% | +1.55 | inf | — |
| **WR#3** tr=2.5 tg=2R be=0.5 sl=7% w1_t1.2 atr=3.0 HL | 4 | 4 | 0 | 100% | +26.03% | — | 0.00% | +1.72 | inf | — |

### Mejores por Sharpe ratio

| Variante | T | W | L | WR | CR | CAGR | MaxDD | Sharpe | avgR | PF | Exp |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **Buy & Hold GOOGL** | — | — | — | — | +152.93% | 20.43% | -23.40% | 0.90 | — | — | 100% |
| **COMP#1** tr=2.5 tg=None sl=7% w3_t1.2 | 12 | 9 | 3 | 75% | +77.52% | 12.18% | -2.55% | **1.52** | +0.96 | 10.5 | 30% |
| **COMP#2** tr=2.5 tg=None sl=7% w1_t1.2 | 12 | 9 | 3 | 75% | +73.67% | 11.69% | -2.55% | **1.45** | +0.93 | 10.2 | 27% |
| **COMP#3** tr=2.5 tg=None sl=7% w3_t1.2 alt=0.01 | 11 | 8 | 3 | 73% | +70.59% | 11.29% | -2.55% | **1.42** | +0.99 | 9.9 | 28% |

### Mejores por composite (50% CR + 30% WR + 20% avg_R)

| Variante | Comp | T | W | L | WR | CR | CAGR | MaxDD | avgR | PF | Exp |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **Buy & Hold GOOGL** | — | — | — | — | — | +113.52% | 16.40% | -24.40% | — | — | 100% |
| **COMP#1** tr=2.5 tg=None sl=7% w3_t1.2 VC=N | 0.600 | 12 | 9 | 3 | 75% | +77.52% | 12.13% | -2.55% | +0.96 | — | — |
| **COMP#2** tr=2.5 tg=None sl=7% w1_t1.2 VC=N | 0.574 | 12 | 9 | 3 | 75% | +73.67% | 11.68% | -2.55% | +0.93 | — | — |
| **COMP#3** tr=2.5 tg=None sl=7% w3_t1.2 VC=N comp=0.95 alt=0.01 | 0.555 | 11 | 8 | 3 | 73% | +70.59% | 11.32% | -2.55% | +0.99 | — | — |

---

## Configuraciones completas de las variantes

### COMP#1 — La variante ganadora (w3_t1.2)

**Deteccion:**
```
atr_mult=2.0, use_close_only=True
max_depth_atr=8, min_total_reduction=0.80, lookback_bars=126
compression_threshold=0.95, tolerance=0.10
max_depth_pct=0.25, ascending_lows_tolerance=0.08
trend_template=False, volume_contraction=False
vol_filter=w3_t1.2 (volumen >= 1.2x avg en ventana de 3 dias)
```

**Salida:**
```
trailing_atr_multiplier=2.5, target_r_multiple=None
early_exit_days=None, breakeven_r_multiple=1.0, max_stop_loss_pct=0.07
max_bars_without_progress=15, min_progress_r=0.5
```

### COMP#2 — Misma deteccion, vol_filter w1_t1.2

**Deteccion:**
```
atr_mult=2.0, use_close_only=True
max_depth_atr=8, min_total_reduction=0.80, lookback_bars=126
compression_threshold=0.95, tolerance=0.10
max_depth_pct=0.25, ascending_lows_tolerance=0.08
trend_template=False, volume_contraction=False
vol_filter=w1_t1.2 (volumen >= 1.2x avg en ventana de 1 dia)
```

**Salida:**
```
trailing_atr_multiplier=2.5, target_r_multiple=None
early_exit_days=None, breakeven_r_multiple=1.0, max_stop_loss_pct=0.07
max_bars_without_progress=15, min_progress_r=0.5
```

### COMP#3 — Deteccion con ascending_lows_tolerance=0.01

**Deteccion:**
```
atr_mult=2.0, use_close_only=True
max_depth_atr=8, min_total_reduction=0.80, lookback_bars=126
compression_threshold=0.95, tolerance=0.10
max_depth_pct=0.25, ascending_lows_tolerance=0.01
trend_template=False, volume_contraction=False
vol_filter=w3_t1.2
```

**Salida:**
```
trailing_atr_multiplier=2.5, target_r_multiple=None
early_exit_days=None, breakeven_r_multiple=1.0, max_stop_loss_pct=0.07
max_bars_without_progress=15, min_progress_r=0.5
```

### CR#1 — Mayor retorno absoluto

**Deteccion:**
```
atr_mult=2.0, use_close_only=True
max_depth_atr=8, min_total_reduction=0.80, lookback_bars=126
compression_threshold=0.95, tolerance=0.10
max_depth_pct=0.25, ascending_lows_tolerance=0.08
trend_template=False, volume_contraction=False
vol_filter=no_filter
```

**Salida:**
```
trailing_atr_multiplier=2.5, target_r_multiple=2.0
early_exit_days=3, breakeven_r_multiple=1.5, max_stop_loss_pct=0.03
max_bars_without_progress=15, min_progress_r=0.5
```

---

## Detalle de trades — Variantes principales

### COMP#1: tr=2.5 tg=None sl=7% w3_t1.2 — 12T, 75% WR, +77.52%

| # | Entry | Exit | Salida | PnL | R | MaxR | Dur |
|---|---|---|---|---|---|---|---|
| 1 | 2015-07-13 | 2015-07-24 | trailing_stop | +14.52% | +2.6R | 4.0R | 11d |
| 2 | 2015-07-27 | 2015-08-21 | stop_loss | -2.16% | -0.3R | 0.8R | 25d |
| 3 | 2015-08-24 | 2015-09-17 | time_exit | +8.67% | +1.2R | 1.2R | 24d |
| 4 | 2016-07-28 | 2016-08-22 | time_exit | +4.06% | +0.6R | 0.8R | 25d |
| 5 | 2017-03-17 | 2017-03-21 | stop_loss | -2.55% | -0.4R | 0.0R | 4d |
| 6 | 2017-04-24 | 2017-06-09 | trailing_stop | +10.38% | +1.8R | 2.5R | 46d |
| 7 | 2017-09-27 | 2017-11-30 | trailing_stop | +7.95% | +2.2R | 3.2R | 64d |
| 8 | 2017-12-01 | 2018-02-02 | trailing_stop | +9.18% | +2.2R | 3.9R | 63d |
| 9 | 2018-07-13 | 2018-08-14 | time_exit | +4.46% | +0.6R | 1.0R | 32d |
| 10 | 2019-03-12 | 2019-03-27 | stop_loss | -1.61% | -0.2R | 0.5R | 15d |
| 11 | 2019-10-17 | 2019-11-29 | time_exit | +4.09% | +0.6R | 1.0R | 43d |
| 12 | 2019-12-04 | 2019-12-26 | time_exit | +3.30% | +0.5R | 0.5R | 22d |

### COMP#2: tr=2.5 tg=None sl=7% w1_t1.2 — 12T, 75% WR, +73.67%

Mismos trades que COMP#1 excepto:
- Trade #9: entry 2018-07-23 (vs 07-13), +3.89% (vs +4.46%), Dur=22d (vs 32d)
- Trade #11: entry 2019-10-28 (vs 10-17), +2.39% (vs +4.09%), Dur=21d (vs 43d)

El filtro w1_t1.2 (ventana de 1 dia) retrasa algunas entradas respecto a w3_t1.2.

### CR#1: tr=2.5 tg=2R early=3 sl=3% no_filter — 32T, 41% WR, +103.84%

| # | Entry | Exit | Salida | PnL | R | MaxR | Dur |
|---|---|---|---|---|---|---|---|
| 1 | 2015-07-13 | 2015-07-17 | target | **+22.37%** | **+7.5R** | 7.5R | 4d |
| 2 | 2015-07-20 | 2015-07-23 | early_exit | -2.61% | -0.9R | 0.1R | 3d |
| 3 | 2015-07-24 | 2015-08-17 | target | +6.01% | +2.0R | 2.0R | 24d |
| 4 | 2015-08-18 | 2015-08-20 | early_exit | -1.34% | -0.4R | 0.3R | 2d |
| 5 | 2015-08-21 | 2015-08-24 | early_exit | -4.02% | -1.3R | 0.0R | 3d |
| 6 | 2015-08-25 | 2015-08-26 | target | +7.72% | +2.6R | 2.6R | 1d |
| 7 | 2015-12-29 | 2015-12-30 | early_exit | -0.46% | -0.2R | 0.0R | 1d |
| 8 | 2016-07-20 | 2016-07-21 | early_exit | -0.35% | -0.1R | 0.0R | 1d |
| 9 | 2016-07-22 | 2016-07-25 | early_exit | -0.23% | -0.1R | 0.0R | 3d |
| 10 | 2016-07-26 | 2016-08-05 | target | +6.50% | +2.2R | 2.2R | 10d |
| 11 | 2016-08-08 | 2016-08-29 | time_exit | -1.17% | -0.4R | 0.1R | 21d |
| 12 | 2017-03-10 | 2017-03-21 | stop_loss | -1.31% | -0.4R | 0.4R | 11d |
| 13 | 2017-04-24 | 2017-05-01 | target | +6.13% | +2.0R | 2.0R | 7d |
| 14 | 2017-05-02 | 2017-05-30 | target | +6.30% | +2.1R | 2.1R | 28d |
| 15 | 2017-09-27 | 2017-10-27 | target | +7.69% | +2.6R | 2.6R | 30d |
| 16 | 2017-10-30 | 2017-10-31 | early_exit | -0.01% | -0.0R | 0.0R | 1d |
| 17 | 2017-11-01 | 2017-11-30 | stop_loss | -0.62% | -0.2R | 0.9R | 29d |
| 18 | 2017-12-01 | 2017-12-04 | early_exit | -1.29% | -0.4R | 0.0R | 3d |
| 19 | 2017-12-05 | 2017-12-18 | target | +6.42% | +2.1R | 2.1R | 13d |
| 20 | 2018-07-13 | 2018-07-16 | early_exit | -0.66% | -0.2R | 0.0R | 3d |
| 21 | 2018-07-17 | 2018-07-18 | early_exit | -0.01% | -0.0R | 0.0R | 1d |
| 22 | 2018-07-23 | 2018-07-26 | target | +6.15% | +2.1R | 2.1R | 3d |
| 23 | 2018-07-27 | 2018-07-30 | early_exit | -1.82% | -0.6R | 0.0R | 3d |
| 24 | 2018-07-31 | 2018-08-28 | time_exit | +1.52% | +0.5R | 1.0R | 28d |
| 25 | 2019-03-04 | 2019-03-07 | early_exit | -0.22% | -0.1R | 0.5R | 3d |
| 26 | 2019-03-11 | 2019-03-27 | trailing_stop | -0.11% | -0.0R | 1.6R | 16d |
| 27 | 2019-03-28 | 2019-04-22 | target | +6.95% | +2.3R | 2.3R | 25d |
| 28 | 2019-10-17 | 2019-10-18 | early_exit | -0.67% | -0.2R | 0.0R | 1d |
| 29 | 2019-10-23 | 2019-11-15 | target | +6.04% | +2.0R | 2.0R | 23d |
| 30 | 2019-11-18 | 2019-11-19 | early_exit | -0.55% | -0.2R | 0.0R | 1d |
| 31 | 2019-11-20 | 2019-11-21 | early_exit | -0.13% | -0.0R | 0.0R | 1d |
| 32 | 2019-11-22 | 2019-12-31 | open | +3.53% | +1.2R | 1.8R | 39d |

---

## Observaciones

1. **use_close_only=True es critico para GOOGL**: HL da CR promedio negativo (-0.72%). Las mechas de GOOGL generan swings ruidosos que contaminan la deteccion de VCPs. Esto es **unico de GOOGL** — AAPL favorece HL.

2. **target=None domina en composite** (como AMZN), pero target=2R domina en CR absoluto. La diferencia es que target=None produce menos trades pero con mayor WR (75% vs 41%).

3. **trail=2.5 en vez de 2.0**: GOOGL necesita un trailing mas holgado que AAPL (2.0) y AMZN (2.0). Probablemente por mayor volatilidad intraday.

4. **VC=N en todos los top por CR y composite**: volume_contraction restringe demasiado en GOOGL (+2.19% sin VC vs +1.01% con VC).

5. **sl=0.07 en composite vs sl=0.03 en CR**: las variantes composite usan un stop loss mas amplio, lo que evita ser sacado prematuramente en swings normales de GOOGL.

6. **El trade estrella de CR#1**: 2015-07-13 a 2015-07-17, +22.37% (+7.5R) en solo 4 dias. Un earnings beat masivo de Alphabet.

---

## Resultados Test (2020-01-02 a 2026-04-08)

Stage 2 en test: dato no disponible en log (estimado ~25% basado en el regimen de mercado).

### Tabla de resultados — Test

| Variante | T | W | L | WR | CR | MaxDD | avgR | PF | Exp |
|---|---|---|---|---|---|---|---|---|---|
| **Buy & Hold GOOGL** | — | — | — | — | +363.69% | -44.32% | — | — | 100% |
| **COMP#1** w3_t1.2, tr=2.5 tg=None sl=7% | 4 | 2 | 2 | 50% | +3.55% | -7.77% | +0.16 | — | — |
| **COMP#2** w1_t1.2, tr=2.5 tg=None sl=7% | 3 | 2 | 1 | 67% | +4.84% | -7.77% | +0.26 | — | — |
| **CR#1** no_filter, tr=2.5 tg=2R early=3 sl=3% | 14 | 2 | 12 | 14% | -4.86% | -10.03% | -0.10 | — | — |

### Detalle de trades — COMP#1 (w3_t1.2) — 4T, 50% WR, +3.55%

| # | Entry | Exit | Salida | PnL | R | MaxR | Dur |
|---|---|---|---|---|---|---|---|
| 1 | 2021-07-23 | 2021-09-20 | trailing_stop | +4.29% | +0.6R | 1.3R | 59d |
| 2 | 2021-09-21 | 2021-09-28 | stop_loss | -2.30% | -0.3R | 0.3R | 7d |
| 3 | 2021-09-29 | 2021-11-17 | time_exit | +10.19% | +1.5R | 1.6R | 49d |
| 4 | 2023-02-02 | 2023-02-08 | stop_loss | -7.77% | -1.1R | 0.0R | 6d |

### Detalle de trades — COMP#2 (w1_t1.2) — 3T, 67% WR, +4.84%

| # | Entry | Exit | Salida | PnL | R | MaxR | Dur |
|---|---|---|---|---|---|---|---|
| 1 | 2021-07-23 | 2021-09-20 | trailing_stop | +4.29% | +0.6R | 1.3R | 59d |
| 2 | 2021-09-28 | 2021-11-17 | time_exit | +8.99% | +1.3R | 1.4R | 50d |
| 3 | 2023-02-02 | 2023-02-08 | stop_loss | -7.77% | -1.1R | 0.0R | 6d |

COMP#2 (w1_t1.2) evita el trade #2 perdedor de COMP#1 porque el filtro de 1 dia no confirma volumen en 2021-09-21.

### Detalle de trades — CR#1 en test: 14T, 14% WR, -4.86%

| # | Entry | Exit | Salida | PnL | R | MaxR | Dur |
|---|---|---|---|---|---|---|---|
| 1 | 2021-07-23 | 2021-07-27 | early_exit | -0.84% | -0.3R | 0.3R | 4d |
| 2 | 2021-07-28 | 2021-07-29 | early_exit | -0.23% | -0.1R | 0.0R | 1d |
| 3 | 2021-07-30 | 2021-08-27 | target | +6.89% | +2.3R | 2.3R | 28d |
| 4 | 2021-08-30 | 2021-09-02 | early_exit | -0.90% | -0.3R | 0.1R | 3d |
| 5 | 2021-09-03 | 2021-09-08 | early_exit | -0.03% | -0.0R | 0.1R | 5d |
| 6 | 2021-09-09 | 2021-09-10 | early_exit | -1.86% | -0.6R | 0.0R | 1d |
| 7 | 2021-09-13 | 2021-09-20 | stop_loss | -2.54% | -0.8R | 0.5R | 7d |
| 8 | 2021-09-21 | 2021-09-28 | stop_loss | -2.30% | -0.8R | 0.8R | 7d |
| 9 | 2021-09-29 | 2021-09-30 | early_exit | -0.50% | -0.2R | 0.0R | 1d |
| 10 | 2021-10-01 | 2021-10-04 | early_exit | -2.11% | -0.7R | 0.0R | 3d |
| 11 | 2021-10-05 | 2021-10-27 | target | +7.49% | +2.5R | 2.5R | 22d |
| 12 | 2023-02-02 | 2023-02-03 | early_exit | -2.75% | -0.9R | 0.0R | 1d |
| 13 | 2023-02-06 | 2023-02-08 | early_exit | -3.43% | -1.1R | 1.5R | 2d |
| 14 | 2026-02-02 | 2026-02-03 | early_exit | -1.16% | -0.4R | 0.0R | 1d |

---

## Comparacion Train vs Test

| Metrica | COMP#1 Train | COMP#1 Test | COMP#2 Train | COMP#2 Test | CR#1 Train | CR#1 Test |
|---|---|---|---|---|---|---|
| Trades | 12 | 4 | 12 | 3 | 32 | 14 |
| WR | 75% | 50% | 75% | 67% | 41% | 14% |
| CR | +77.52% | +3.55% | +73.67% | +4.84% | +103.84% | -4.86% |
| MaxDD | -2.55% | -7.77% | -2.55% | -7.77% | -5.31% | -10.03% |
| avg_R | +0.96 | +0.16 | +0.93 | +0.26 | +0.79 | -0.10 |

---

## Conclusion

GOOGL produce resultados levemente positivos en test (+3.55% a +4.84%) pero con muy pocos trades (3-4 en 6 anos), lo que hace los resultados estadisticamente insignificantes. La estrategia VCP es demasiado selectiva para GOOGL en el periodo 2020-2026.

**Hallazgo clave**: `use_close_only=True` es critico para GOOGL — un parametro que no seria seleccionado si se usaran los resultados de AAPL. Esto refuerza que los parametros de deteccion no son transferibles entre tickers.

El loss de -7.77% en feb 2023 (earnings miss de Alphabet) pesa sobre todas las variantes. Sin ese trade, COMP#2 tendria +13.8% CR en test, un resultado mas razonable.

---

## Proximos pasos

- Evaluar MSFT y NVDA para completar el universo de 5 tickers
- Analizar si existe un conjunto de parametros "universales" que funcione razonablemente en multiples tickers
- Considerar filtro de earnings: excluir entradas en las 2 semanas previas a earnings para evitar gap downs
- Evaluar si un stop loss mas amplio (7% vs 3%) mejora la generalizacion cross-ticker
