# MSFT — Optimizacion Profunda v2 (Train 2015-2019)

## Objetivo

Optimizar la deteccion de patrones VCP para MSFT con mejoras respecto a v1:
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
| atr_mult | 2.0 | +1.07% | +0.38% (4.0) | Domina pero con brecha menor que otros tickers |
| use_close_only | False (HL) | +0.93% | +0.72% (True) | HL mejor, consistente con AAPL |
| lookback_bars | 126 | +1.35% | +0.30% (63) | Consistente con todos los tickers |
| trend_template | False | +1.39% | +0.26% (True) | Consistente con todos los tickers |

### Parametros con impacto moderado

| Parametro | Observacion |
|---|---|
| max_depth_atr | mda=8 y None similares (+1.2%), mda=6 peor (+0.03%) |
| reduction | 0.60 y 0.80 similares (~+1.3%), 0.40 negativo (-0.15%) |
| comp_thresh | 0.95 mejor (+0.93%), 0.85 peor (+0.66%) |
| vol_contraction | VC: +0.95%, sin VC: +0.70%. **VC ligeramente mejor** (unico ticker) |
| vol_filter | no_filter: +2.13%, w1_t1.5: +0.07%. Brecha grande |

### Parametros sin impacto (para MSFT)

| Parametro | Observacion |
|---|---|
| tolerance | 0.10 ligeramente mejor, 0.15 y 0.20 identicos |
| max_depth_pct | 0.25, 0.30, 0.35 identicos |
| ascending_lows_tolerance | 0.03 ligeramente mejor, 0.01 peor |

### Estabilidad entre exit profiles

Correlacion entre CRs de los 3 perfiles de salida (tight/medium/loose):
- tight-medium: 0.822
- tight-loose: 0.752
- medium-loose: 0.876

---

## Deteccion base elegida

Todas las variantes top comparten:

```
atr_mult=2.0, use_close_only=False (HL)
max_depth_atr=None, lookback_bars=126
tolerance=0.10, max_depth_pct=0.25, ascending_lows_tolerance=0.03
trend_template=False
```

Lo que varia: min_total_reduction (0.60/0.80), compression_threshold (0.85/0.90), volume_contraction (on/off), y config de salida.

---

## Tabla comparativa — Train (2015-2019)

### Mejores por CR (retorno acumulado)

| Variante | T | W | L | WR | CR | CAGR | MaxDD | Sharpe | avgR | PF | Exp |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **Buy & Hold MSFT** | — | — | — | — | +237.25% | 27.55% | -18.58% | 1.21 | — | — | 100% |
| **COMP#1** tr=3.0 tg=2R sl=5% no_filter VC | 9 | 6 | 3 | 67% | +48.17% | 8.19% | -0.89% | 1.31 | +1.02 | 32.2 | 16% |
| **COMP#3** tr=3.0 tg=2R sl=5% no_filter VC red=0.60 | 8 | 5 | 3 | 62% | +45.70% | 7.83% | -0.89% | 1.28 | +1.10 | 30.9 | 13% |
| **COMP#4** tr=1.5 tg=3R sl=3% no_filter VC | 10 | 6 | 4 | 60% | +42.65% | 7.37% | -3.16% | 0.88 | +1.24 | 4.5 | 14% |

### Mejores por WR (win rate, min 3 trades)

| Variante | T | W | L | WR | CR | CAGR | MaxDD | Sharpe | avgR | PF | Exp |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **Buy & Hold MSFT** | — | — | — | — | +237.25% | 27.55% | -18.58% | 1.21 | — | — | 100% |
| **WR#1** tr=3.0 tg=None sl=7% w1_t1.2 | 4 | 4 | 0 | 100% | +20.54% | — | 0.00% | — | +0.98 | inf | — |
| **WR#2** tr=1.0 tg=None sl=3% w1_t1.2 | 7 | 6 | 1 | 86% | +20.27% | — | — | — | +0.95 | — | — |

### Mejores por Sharpe ratio

| Variante | T | W | L | WR | CR | CAGR | MaxDD | Sharpe | avgR | PF | Exp |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **Buy & Hold MSFT** | — | — | — | — | +237.25% | 27.55% | -18.58% | 1.21 | — | — | 100% |
| **COMP#1** tr=3.0 tg=2R sl=5% no_filter VC | 9 | 6 | 3 | 67% | +48.17% | 8.19% | -0.89% | **1.31** | +1.02 | 32.2 | 16% |
| **COMP#3** tr=3.0 tg=2R sl=5% no_filter VC red=0.60 | 8 | 5 | 3 | 62% | +45.70% | 7.83% | -0.89% | **1.28** | +1.10 | 30.9 | 13% |
| **COMP#2** tr=1.5 tg=3R sl=3% no_filter | 9 | 6 | 3 | 67% | +41.08% | 7.14% | -3.16% | **1.07** | +1.34 | 9.1 | 13% |

### Mejores por composite (50% CR + 30% WR + 20% avg_R)

| Variante | Comp | T | W | L | WR | CR | CAGR | MaxDD | Sharpe | avgR | PF | Exp |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **Buy & Hold MSFT** | — | — | — | — | — | +237.25% | 27.55% | -18.58% | 1.21 | — | — | 100% |
| **COMP#1** tr=3.0 tg=2R sl=5% no_filter VC | 0.737 | 9 | 6 | 3 | 67% | +48.17% | 8.19% | -0.89% | 1.31 | +1.02 | 32.2 | 16% |
| **COMP#2** tr=1.5 tg=3R sl=3% no_filter | 0.713 | 9 | 6 | 3 | 67% | +41.08% | 7.14% | -3.16% | 1.07 | +1.34 | 9.1 | 13% |
| **COMP#3** tr=3.0 tg=2R sl=5% no_filter VC red=0.60 | 0.697 | 8 | 5 | 3 | 62% | +45.70% | 7.83% | -0.89% | 1.28 | +1.10 | 30.9 | 13% |

---

## Configuraciones completas de las variantes

### COMP#1 — La variante ganadora

**Deteccion:**
```
atr_mult=2.0, use_close_only=False
max_depth_atr=None, min_total_reduction=0.80, lookback_bars=126
compression_threshold=0.90, tolerance=0.10
max_depth_pct=0.25, ascending_lows_tolerance=0.03
trend_template=False, volume_contraction=True (ratio<=0.85)
vol_filter=no_filter
```

**Salida:**
```
trailing_atr_multiplier=3.0, target_r_multiple=2.0
early_exit_days=None, breakeven_r_multiple=0.5, max_stop_loss_pct=0.05
max_bars_without_progress=15, min_progress_r=0.5
```

### COMP#2

**Deteccion:**
```
atr_mult=2.0, use_close_only=False
max_depth_atr=None, min_total_reduction=0.60, lookback_bars=126
compression_threshold=0.85, tolerance=0.10
max_depth_pct=0.25, ascending_lows_tolerance=0.03
trend_template=False, volume_contraction=False
vol_filter=no_filter
```

**Salida:**
```
trailing_atr_multiplier=1.5, target_r_multiple=3.0
early_exit_days=None, breakeven_r_multiple=0.5, max_stop_loss_pct=0.03
max_bars_without_progress=15, min_progress_r=0.5
```

### COMP#3

**Deteccion:**
```
atr_mult=2.0, use_close_only=False
max_depth_atr=None, min_total_reduction=0.60, lookback_bars=126
compression_threshold=0.85, tolerance=0.10
max_depth_pct=0.25, ascending_lows_tolerance=0.03
trend_template=False, volume_contraction=True (ratio<=0.85)
vol_filter=no_filter
```

**Salida:**
```
trailing_atr_multiplier=3.0, target_r_multiple=2.0
early_exit_days=None, breakeven_r_multiple=0.5, max_stop_loss_pct=0.05
max_bars_without_progress=15, min_progress_r=0.5
```

---

## Detalle de trades — Variantes principales

### COMP#1: tr=3.0 tg=2R sl=5% no_filter VC — 9T, 67% WR, +48.17%

| # | Entry | Exit | Salida | PnL | R | MaxR | Dur |
|---|---|---|---|---|---|---|---|
| 1 | 2015-04-23 | 2015-04-24 | target | +10.45% | +2.1R | 2.1R | 1d |
| 2 | 2015-04-27 | 2015-05-18 | time_exit | -0.04% | -0.0R | 0.5R | 21d |
| 3 | 2017-03-28 | 2017-04-19 | time_exit | -0.38% | -0.1R | 0.3R | 22d |
| 4 | 2017-04-20 | 2017-05-01 | target | +5.97% | +2.1R | 2.1R | 11d |
| 5 | 2017-05-02 | 2017-05-23 | time_exit | -0.89% | -0.2R | 0.0R | 21d |
| 6 | 2018-08-28 | 2018-10-05 | trailing_stop | +1.70% | +0.4R | 1.2R | 38d |
| 7 | 2019-02-15 | 2019-03-21 | target | +11.09% | +2.2R | 2.2R | 34d |
| 8 | 2019-03-22 | 2019-04-25 | target | +10.34% | +2.1R | 2.1R | 34d |
| 9 | 2019-12-12 | 2019-12-31 | open | +2.91% | +0.7R | 0.9R | 19d |

### COMP#2: tr=1.5 tg=3R sl=3% no_filter — 9T, 67% WR, +41.08%

| # | Entry | Exit | Salida | PnL | R | MaxR | Dur |
|---|---|---|---|---|---|---|---|
| 1 | 2015-04-23 | 2015-04-24 | target | +10.45% | +3.5R | 3.5R | 1d |
| 2 | 2015-04-27 | 2015-05-05 | trailing_stop | -0.90% | -0.3R | 0.8R | 8d |
| 3 | 2015-05-06 | 2015-05-19 | trailing_stop | +2.81% | +0.9R | 1.8R | 13d |
| 4 | 2017-03-28 | 2017-04-19 | time_exit | -0.38% | -0.1R | 0.3R | 22d |
| 5 | 2017-04-20 | 2017-05-17 | trailing_stop | +3.02% | +1.1R | 2.1R | 27d |
| 6 | 2019-02-15 | 2019-03-21 | target | +11.09% | +3.7R | 3.7R | 34d |
| 7 | 2019-03-22 | 2019-04-25 | target | +10.34% | +3.4R | 3.4R | 34d |
| 8 | 2019-07-24 | 2019-07-31 | stop_loss | -3.16% | -1.1R | 0.1R | 7d |
| 9 | 2019-12-12 | 2019-12-31 | open | +2.91% | +1.0R | 1.2R | 19d |

---

## Observaciones

1. **MSFT tiene los CRs mas modestos** de los 5 tickers (+48.17% mejor composite). MSFT fue un activo estable 2015-2019 con menos movimientos explosivos.

2. **VC mejora ligeramente en MSFT**: unico ticker donde vol_contraction da mejor CR promedio que sin VC. MSFT tiene un patron de volumen mas predecible.

3. **no_filter domina** en vol_filter: +2.13% vs +1.02% para w1_t1.2. Los filtros de volumen reducen demasiado las senales.

4. **Dos trades clave**: feb-abr 2019 con +11.09% y +10.34% back-to-back. Sin estos dos trades, el CR seria modesto.

5. **breakeven_r_multiple=0.5**: MSFT favorece un breakeven muy rapido, diferente a otros tickers. Protege capital temprano.

---

## Resultados Test (2020-01-02 a 2026-04-08)

### Tabla de resultados — Test

| Variante | T | W | L | WR | CR | CAGR | MaxDD | Sharpe | avgR | PF | Exp |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **Buy & Hold MSFT** | — | — | — | — | +133.05% | 14.51% | -37.56% | — | — | — | 100% |
| **COMP#1** tr=3.0 tg=2R sl=5% no_filter VC | 9 | 4 | 5 | 44% | +1.04% | 0.17% | -11.79% | 0.06 | +0.03 | 1.1 | 9% |
| **COMP#2** tr=1.5 tg=3R sl=3% no_filter | 8 | 4 | 4 | 50% | +8.41% | 1.30% | -9.39% | 0.29 | +0.37 | 1.8 | 6% |
| **COMP#3** tr=3.0 tg=2R sl=5% no_filter VC red=0.60 | 4 | 2 | 2 | 50% | +1.71% | 0.27% | -5.21% | 0.10 | +0.10 | 1.3 | 4% |

### Detalle de trades — COMP#1 en test: 9T, 44% WR, +1.04%

| # | Entry | Exit | Salida | PnL | R | MaxR | Dur |
|---|---|---|---|---|---|---|---|
| 1 | 2020-05-05 | 2020-05-13 | trailing_stop | -0.56% | -0.1R | 0.7R | 8d |
| 2 | 2020-05-14 | 2020-06-11 | trailing_stop | +3.18% | +0.6R | 1.8R | 28d |
| 3 | 2020-06-12 | 2020-06-26 | trailing_stop | +4.58% | +0.9R | 1.5R | 14d |
| 4 | 2021-01-25 | 2021-02-22 | trailing_stop | +2.17% | +0.4R | 1.3R | 28d |
| 5 | 2022-07-07 | 2022-07-12 | stop_loss | -5.49% | -1.1R | 0.0R | 5d |
| 6 | 2023-03-14 | 2023-03-31 | target | +10.55% | +2.1R | 2.1R | 17d |
| 7 | 2023-09-05 | 2023-09-20 | stop_loss | -3.83% | -0.9R | 0.3R | 15d |
| 8 | 2025-07-31 | 2025-08-20 | stop_loss | -5.21% | -1.0R | 0.1R | 20d |
| 9 | 2025-10-27 | 2025-11-04 | stop_loss | -3.23% | -0.7R | 0.4R | 8d |

### Detalle de trades — COMP#2 en test: 8T, 50% WR, +8.41%

| # | Entry | Exit | Salida | PnL | R | MaxR | Dur |
|---|---|---|---|---|---|---|---|
| 1 | 2020-05-05 | 2020-05-12 | trailing_stop | +0.97% | +0.3R | 1.1R | 7d |
| 2 | 2020-05-14 | 2020-06-10 | target | +9.03% | +3.0R | 3.0R | 27d |
| 3 | 2020-06-12 | 2020-06-24 | trailing_stop | +5.38% | +1.8R | 2.5R | 12d |
| 4 | 2023-05-25 | 2023-06-07 | trailing_stop | -0.78% | -0.3R | 1.0R | 13d |
| 5 | 2023-06-08 | 2023-06-20 | trailing_stop | +3.93% | +1.3R | 2.3R | 12d |
| 6 | 2024-10-22 | 2024-10-31 | stop_loss | -4.95% | -1.6R | 0.4R | 9d |
| 7 | 2025-07-31 | 2025-08-07 | stop_loss | -2.37% | -0.8R | 0.1R | 7d |
| 8 | 2025-08-08 | 2025-08-19 | stop_loss | -2.35% | -0.8R | 0.5R | 11d |

---

## Comparacion Train vs Test

| Metrica | COMP#1 Train | COMP#1 Test | COMP#2 Train | COMP#2 Test | COMP#3 Train | COMP#3 Test |
|---|---|---|---|---|---|---|
| Trades | 9 | 9 | 9 | 8 | 8 | 4 |
| WR | 67% | 44% | 67% | 50% | 62% | 50% |
| CR | +48.17% | +1.04% | +41.08% | +8.41% | +45.70% | +1.71% |
| MaxDD | -0.89% | -11.79% | -3.16% | -9.39% | -0.89% | -5.21% |
| Sharpe | 1.31 | 0.06 | 1.07 | 0.29 | 1.28 | 0.10 |
| avg_R | +1.02 | +0.03 | +1.34 | +0.37 | +1.10 | +0.10 |

---

## Conclusion

MSFT produce resultados levemente positivos en test (+1.04% a +8.41%) con trades razonables distribuidos en 2020, 2021, 2023, 2024 y 2025. Es el segundo mejor ticker despues de AAPL en terms de generalizacion, pero el CR en test es muy modesto.

**COMP#2** (tr=1.5, tg=3R) es la mejor variante en test: +8.41% con 50% WR y 8 trades. El trailing mas ajustado (1.5 vs 3.0) captura profits mas rapido y el target=3R produce un trade excepcional (+9.03% en mayo 2020).

El principal problema es que los stop losses en 2022, 2025 erosionan las ganancias. MSFT tuvo drawdowns significativos en esos periodos que las variantes no evitan completamente.

---

## Proximos pasos

- Evaluar si un filtro de earnings mejora los resultados (evitar entradas previas a reportes)
- Considerar MSFT como parte de un portfolio multi-ticker con AAPL
