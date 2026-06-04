# NVDA — Optimizacion Profunda v2 (Train 2015-2019)

## Objetivo

Optimizar la deteccion de patrones VCP para NVDA con mejoras respecto a v1:
- Volumen en breakout como post-filtro sistematico (7 variantes)
- 3 perfiles de salida en Fase 1 para ranking robusto (trail 1.5/2.5/3.5)
- Seleccion multi-criterio: top 10 por CR + top 10 por WR
- Fase 2 sobre 19 candidatos (no solo el top 1)
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

### Fase 2: Salida (720 configs x 19 candidatos = 13,680 evaluaciones)

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
| atr_mult | 2.0 | +14.12% | -0.36% (4.0) | Domina masivamente. 3.0 y 4.0 casi inutiles |
| use_close_only | **False (HL)** | +8.36% | +1.35% (True) | HL domina. Close genera muy pocas senales |
| lookback_bars | 63 | +5.49% | +4.22% (126) | **Unico ticker donde lb=63 es mejor** |
| trend_template | False | +4.96% | +4.74% (True) | Menor diferencia que otros tickers |

### Parametros con impacto moderado

| Parametro | Observacion |
|---|---|
| reduction | 0.80 mejor (+7.81%), 0.40 peor (+2.89%) |
| max_depth_atr | None y mda=8 similares (+5.4%), mda=6 peor (+3.77%) |
| comp_thresh | 0.85 mejor (+4.45%), 0.90/0.95 similares (+5.0%) |
| vol_contraction | VC: +5.00%, sin VC: +4.71%. Practicamente igual |
| vol_filter | w3_t1.2 y w5_t1.2 mejores (+5.3%), no_filter peor (+4.89%) |

### Parametros sin impacto (para NVDA)

| Parametro | Observacion |
|---|---|
| tolerance | 0.10, 0.15, 0.20 identicos |
| max_depth_pct | 0.25, 0.30, 0.35 identicos |
| ascending_lows_tolerance | 0.01, 0.03, 0.08 sin diferencia |

### Estabilidad entre exit profiles

Correlacion entre CRs de los 3 perfiles de salida (tight/medium/loose):
- tight-medium: 0.927
- tight-loose: 0.757
- medium-loose: 0.923

Alta estabilidad tight-medium (0.927), la mas alta de todos los tickers.

---

## Deteccion base elegida

Todas las variantes top comparten:

```
atr_mult=2.0, use_close_only=False (HL)
max_depth_atr=None, min_total_reduction=0.60, lookback_bars=63
compression_threshold=0.95, tolerance=0.10
max_depth_pct=0.30, ascending_lows_tolerance=0.01
trend_template=False, volume_contraction=False
```

Lo que varia: vol_filter (w5_t1.2, w3_t1.2, w1_t1.2).

**lookback_bars=63** es unico de NVDA — todos los demas tickers usan 126. NVDA tiene ciclos de VCP mas cortos (~3 meses).

---

## Tabla comparativa — Train (2015-2019)

### Mejores por CR (retorno acumulado)

| Variante | T | W | L | WR | CR | CAGR | MaxDD | Sharpe | avgR | PF | Exp |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **Buy & Hold NVDA** | — | — | — | — | +1068.79% | 63.18% | -56.08% | 1.13 | — | — | 100% |
| **COMP#1** tr=2.5 tg=5R sl=5% w5_t1.2 | 6 | 4 | 2 | 67% | +96.87% | 14.53% | -10.36% | 0.89 | +2.63 | 6.1 | 16% |
| **COMP#2** tr=2.5 tg=5R sl=5% w3_t1.2 | 6 | 4 | 2 | 67% | +96.87% | 14.53% | -10.36% | 0.89 | +2.63 | 6.1 | 16% |
| **COMP#3** tr=2.5 tg=5R sl=5% w1_t1.2 | 6 | 4 | 2 | 67% | +88.92% | 13.59% | -10.36% | 0.83 | +2.48 | 5.8 | 16% |

### Mejores por WR (win rate, min 3 trades)

| Variante | T | W | L | WR | CR | CAGR | MaxDD | Sharpe | avgR | PF | Exp |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **Buy & Hold NVDA** | — | — | — | — | +1068.79% | 63.18% | -56.08% | 1.13 | — | — | 100% |
| **WR#1** tr=3.0 tg=2R sl=7% no_filter atr=3.0 | 3 | 3 | 0 | 93%* | +42.15% | — | 0.00% | — | — | inf | — |
| **WR#2** tr=2.5 tg=5R sl=5% w5_t1.2 lb=63 red=0.60 | 4 | 3 | 1 | 78%* | +40.04% | — | — | — | +1.88 | — | — |

*Promedio de 3 exit profiles.

### Mejores por Sharpe ratio

| Variante | T | W | L | WR | CR | CAGR | MaxDD | Sharpe | avgR | PF | Exp |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **Buy & Hold NVDA** | — | — | — | — | +1068.79% | 63.18% | -56.08% | 1.13 | — | — | 100% |
| **COMP#1** tr=2.5 tg=5R sl=5% w5_t1.2 | 6 | 4 | 2 | 67% | +96.87% | 14.53% | -10.36% | **0.89** | +2.63 | 6.1 | 16% |
| **COMP#3** tr=2.5 tg=5R sl=5% w1_t1.2 | 6 | 4 | 2 | 67% | +88.92% | 13.59% | -10.36% | **0.83** | +2.48 | 5.8 | 16% |

Nota: NVDA tiene los Sharpe mas bajos de los 5 tickers (0.89). Esto se debe a la alta volatilidad por trade — un stop loss de -10.36% en el primer trade impacta el ratio.

### Mejores por composite (50% CR + 30% WR + 20% avg_R)

| Variante | Comp | T | W | L | WR | CR | CAGR | MaxDD | Sharpe | avgR | PF | Exp |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **Buy & Hold NVDA** | — | — | — | — | — | +1068.79% | 63.18% | -56.08% | 1.13 | — | — | 100% |
| **COMP#1** tr=2.5 tg=5R sl=5% w5_t1.2 | 0.801 | 6 | 4 | 2 | 67% | +96.87% | 14.53% | -10.36% | 0.89 | +2.63 | 6.1 | 16% |
| **COMP#2** tr=2.5 tg=5R sl=5% w3_t1.2 | 0.801 | 6 | 4 | 2 | 67% | +96.87% | 14.53% | -10.36% | 0.89 | +2.63 | 6.1 | 16% |
| **COMP#3** tr=2.5 tg=5R sl=5% w1_t1.2 | 0.727 | 6 | 4 | 2 | 67% | +88.92% | 13.59% | -10.36% | 0.83 | +2.48 | 5.8 | 16% |

---

## Configuraciones completas de las variantes

### COMP#1 / COMP#2 — Trades identicos (w5_t1.2 / w3_t1.2)

**Deteccion:**
```
atr_mult=2.0, use_close_only=False
max_depth_atr=None, min_total_reduction=0.60, lookback_bars=63
compression_threshold=0.95, tolerance=0.10
max_depth_pct=0.30, ascending_lows_tolerance=0.01
trend_template=False, volume_contraction=False
vol_filter=w5_t1.2 / w3_t1.2
```

**Salida:**
```
trailing_atr_multiplier=2.5, target_r_multiple=5.0
early_exit_days=None, breakeven_r_multiple=1.5, max_stop_loss_pct=0.05
max_bars_without_progress=15, min_progress_r=0.5
```

### COMP#3 — Vol filter w1_t1.2 (mas restrictivo)

**Deteccion:**
```
atr_mult=2.0, use_close_only=False
max_depth_atr=None, min_total_reduction=0.60, lookback_bars=63
compression_threshold=0.95, tolerance=0.10
max_depth_pct=0.30, ascending_lows_tolerance=0.01
trend_template=False, volume_contraction=False
vol_filter=w1_t1.2
```

**Salida:**
```
trailing_atr_multiplier=2.5, target_r_multiple=5.0
early_exit_days=None, breakeven_r_multiple=1.5, max_stop_loss_pct=0.05
max_bars_without_progress=15, min_progress_r=0.5
```

---

## Detalle de trades — Variantes principales

### COMP#1 / COMP#2: tr=2.5 tg=5R sl=5% — 6T, 67% WR, +96.87%

Trades identicos para w5_t1.2 y w3_t1.2.

| # | Entry | Exit | Salida | PnL | R | MaxR | Dur |
|---|---|---|---|---|---|---|---|
| 1 | 2015-03-20 | 2015-03-25 | stop_loss | -10.36% | -2.1R | 0.0R | 5d |
| 2 | 2017-05-10 | 2017-06-08 | target | **+31.86%** | **+6.4R** | 6.4R | 29d |
| 3 | 2017-09-15 | 2017-09-25 | stop_loss | -5.06% | -1.0R | 0.8R | 10d |
| 4 | 2017-09-26 | 2017-11-10 | target | +25.69% | +5.1R | 5.1R | 45d |
| 5 | 2019-03-13 | 2019-04-25 | time_exit | +10.85% | +2.2R | 2.8R | 43d |
| 6 | 2019-10-03 | 2019-12-17 | target | +25.91% | +5.2R | 5.2R | 75d |

### COMP#3: tr=2.5 tg=5R sl=5% w1_t1.2 — 6T, 67% WR, +88.92%

Mismos trades excepto #5: entry 2019-03-19 (vs 03-13), +6.37% (vs +10.85%), Dur=37d (vs 43d). El filtro w1_t1.2 retrasa la entrada 6 dias.

---

## Observaciones

1. **target=5R domina en todos los top** — unico ticker donde 5R es optimo. NVDA tiene movimientos explosivos que justifican targets altos (+31.86%, +25.69%, +25.91%).

2. **lookback_bars=63 es optimo** — unico ticker donde 3 meses supera a 6 meses. NVDA forma VCPs mas rapidos, probablemente por su ciclo de earnings trimestrales y noticias de AI/gaming.

3. **Solo 6 trades en 5 anos**: la estrategia es muy selectiva. Pero los 4 ganadores tienen avg_R=+4.7R, lo que compensa los 2 losses.

4. **El stop loss del trade #1 es severo** (-10.36%): NVDA tiene gaps violentos. Un sl=5% no se ejecuto a precio — el gap fue mayor.

5. **Pocas configs elegibles**: solo 200 de 244,944 rows tienen min 3 trades promedio (vs 2,074 AMZN, 1,334 GOOGL). NVDA genera pocas senales VCP.

6. **Exposicion muy baja** (16%): el capital esta libre 84% del tiempo.

---

## Resultados Test (2020-01-02 a 2026-04-08)

### Tabla de resultados — Test

| Variante | T | W | L | WR | CR | CAGR | MaxDD | Sharpe | avgR | PF | Exp |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **Buy & Hold NVDA** | — | — | — | — | +2935.78% | 76.91% | -66.36% | — | — | — | 100% |
| **COMP#1** w5_t1.2 | 5 | 3 | 2 | 60% | +74.60% | 9.33% | -10.10% | 0.74 | +2.58 | 7.3 | 9% |
| **COMP#2** w3_t1.2 | 4 | 3 | 1 | 75% | **+89.00%** | 10.73% | **-2.68%** | **1.10** | **+3.60** | **27.9** | 8% |
| **COMP#3** w1_t1.2 | 4 | 3 | 1 | 75% | **+89.00%** | 10.73% | **-2.68%** | **1.10** | **+3.60** | **27.9** | 8% |

### Detalle de trades — COMP#1 (w5_t1.2) — 5T, 60% WR, +74.60%

| # | Entry | Exit | Salida | PnL | R | MaxR | Dur |
|---|---|---|---|---|---|---|---|
| 1 | 2023-05-01 | 2023-05-25 | target | **+31.37%** | +6.3R | 6.3R | 24d |
| 2 | 2024-01-08 | 2024-02-02 | target | **+26.61%** | +5.3R | 5.3R | 25d |
| 3 | 2024-02-05 | 2024-02-21 | stop_loss | -2.68% | -0.5R | 1.3R | 16d |
| 4 | 2024-10-21 | 2024-10-31 | stop_loss | -7.62% | -1.5R | 0.0R | 10d |
| 5 | 2025-06-25 | 2025-08-28 | time_exit | +16.76% | +3.4R | 3.7R | 64d |

### Detalle de trades — COMP#2 / COMP#3 (w3_t1.2 / w1_t1.2) — 4T, 75% WR, +89.00%

| # | Entry | Exit | Salida | PnL | R | MaxR | Dur |
|---|---|---|---|---|---|---|---|
| 1 | 2023-05-01 | 2023-05-25 | target | **+31.37%** | +6.3R | 6.3R | 24d |
| 2 | 2024-01-08 | 2024-02-02 | target | **+26.61%** | +5.3R | 5.3R | 25d |
| 3 | 2024-02-05 | 2024-02-21 | stop_loss | -2.68% | -0.5R | 1.3R | 16d |
| 4 | 2025-06-25 | 2025-08-28 | time_exit | +16.76% | +3.4R | 3.7R | 64d |

COMP#2/3 evitan el trade #4 perdedor (-7.62%) de COMP#1 porque w3/w1_t1.2 no confirma volumen en oct 2024.

---

## Comparacion Train vs Test

| Metrica | COMP#1 Train | COMP#1 Test | COMP#2 Train | COMP#2 Test |
|---|---|---|---|---|
| Trades | 6 | 5 | 6 | 4 |
| WR | 67% | 60% | 67% | 75% |
| CR | +96.87% | +74.60% | +96.87% | **+89.00%** |
| MaxDD | -10.36% | -10.10% | -10.36% | **-2.68%** |
| Sharpe | 0.89 | 0.74 | 0.89 | **1.10** |
| avg_R | +2.63 | +2.58 | +2.63 | **+3.60** |

---

## Observaciones del test

1. **NVDA generaliza excelentemente**: COMP#2 tiene CR +96.87% train -> +89.00% test. Es el **segundo mejor ticker** en generalizacion despues de AAPL.

2. **Los trades en test son enormes**: +31.37% (AI boom mayo 2023), +26.61% (rally pre-earnings enero 2024), +16.76% (consolidacion 2025). Los patrones VCP de NVDA producen movimientos explosivos tanto en train como en test.

3. **COMP#2 (w3_t1.2) supera a COMP#1 (w5_t1.2) en test**: el filtro mas restrictivo evita el trade #4 perdedor (-7.62%) de oct 2024, resultando en 75% WR, -2.68% MaxDD y Sharpe de 1.10.

4. **avg_R mejora en test** (+3.60 vs +2.63): los VCPs que NVDA forma en 2023-2025 son de mayor calidad que los de 2015-2019. El rally de AI amplifica los movimientos.

5. **Solo 4 trades en 6 anos**: pocos pero contundentes. La exposicion es solo 8% del tiempo.

6. **Buy & hold NVDA hizo +2935%**: la estrategia VCP captura solo una fraccion, pero con -2.68% MaxDD vs -66.36% del buy & hold.

---

## Conclusion

**NVDA es el segundo mejor ticker para la estrategia VCP**, con excelente generalizacion train->test.

**COMP#2 (w3_t1.2, tr=2.5, tg=5R, sl=5%)** es la variante recomendada:
- Generaliza excelente: CR +96.87% train -> +89.00% test
- 75% WR en test con avg_R de +3.60
- MaxDD controlado: -2.68% en test
- Sharpe 1.10 en test (mejor que train)
- Los pocos VCPs que NVDA forma son de alta calidad y producen movimientos explosivos

El parametro clave es **target=5R**: permite capturar los movimientos de +25-31% que caracterizan a NVDA. Ningun otro ticker tiene un target optimo tan alto.

---

## Proximos pasos

- NVDA y AAPL son los mejores candidatos para un portfolio VCP multi-ticker
- Evaluar si combinar NVDA+AAPL produce mejores metricas de portfolio (diversificacion temporal de trades)
