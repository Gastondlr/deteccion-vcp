# GOOGL — Deep Per-Ticker v4 (Trend Template corregido)

## Objetivo

Evaluar el impacto de activar Trend Template (TT=True) corregido en la deteccion VCP para GOOGL, con grid search de parametros de deteccion y salida optimizados por ticker individual.

**Train:** 2015-01-02 a 2019-12-31 (1,258 barras) | **Test:** 2020-01-02 a 2026-04-08 (1,574 barras)
**B&H Train:** CR=+152.93%, MaxDD=-23.40% | **B&H Test:** CR=+363.69%, MaxDD=-44.32%

---

## Metodologia

- Grid search por ticker con Trend Template corregido (TT=True)
- Deteccion unica evaluada: atr=3.0, HL, lb=126
- Variantes de salida: trailing, target, sin target
- Evaluacion out-of-sample estricta: train 2015-2019, test 2020-2026

---

## Deteccion base

```
atr_mult=3.0, use_close_only=False (HL)
max_depth_atr=None, min_total_reduction=0.60, lookback_bars=126
compression_threshold=0.85, tolerance=0.10
max_depth_pct=0.25, ascending_lows_tolerance=0.01
trend_template=True
```

---

## Tabla comparativa — Train (2015-2019)

| Variante | T | W | L | WR | CR | MaxDD | Sharpe | avgR | PF |
|---|---|---|---|---|---|---|---|---|---|
| **Buy & Hold GOOGL** | — | — | — | — | +152.93% | -23.40% | — | — | — |
| **v4#1** tg=5R | 2 | 2 | 0 | 100% | +15.60% | 0.00% | — | — | inf |
| **v4#2** tg=3R | 3 | — | — | — | +15.15% | — | — | — | — |
| **v4#3** sin target | 2 | — | — | — | +9.45% | — | — | — | — |

---

## Tabla comparativa — Test (2020-2026)

| Variante | T | W | L | WR | CR | MaxDD | Sharpe | avgR | PF |
|---|---|---|---|---|---|---|---|---|---|
| **Buy & Hold GOOGL** | — | — | — | — | +363.69% | -44.32% | — | — | — |
| **v4#1** tg=5R | 4 | 2 | 2 | 50% | +3.26% | -4.78% | 0.20 | — | — |
| **v4#2** tg=3R | 3 | 2 | 1 | **67%** | **+4.32%** | **-2.30%** | — | — | — |
| **v4#3** sin target | 4 | 2 | 2 | 50% | +3.26% | -4.78% | — | — | — |

---

## Configuracion destacada — v4#2 tg=3R

**Deteccion:**
```
atr_mult=3.0, use_close_only=False (HL)
max_depth_atr=None, min_total_reduction=0.60, lookback_bars=126
compression_threshold=0.85, tolerance=0.10
max_depth_pct=0.25, ascending_lows_tolerance=0.01
trend_template=True
```

**Salida:**
```
target_r_multiple=3.0
(demas parametros de salida de la config v4#2)
```

---

## Detalle de trades — v4#1 Test (4T, 50% WR, +3.26%)

| # | Entry | Exit | Salida | PnL | R | MaxR | Dur |
|---|---|---|---|---|---|---|---|
| 1 | 2021-07-23 | 2021-09-10 | — | +5.91% | — | — | 49d |
| 2 | 2021-09-13 | 2021-09-20 | stop | -2.54% | — | — | 7d |
| 3 | 2021-09-21 | 2021-09-28 | stop | -2.30% | — | — | 7d |
| 4 | 2021-09-29 | 2021-10-22 | — | +2.39% | — | — | 23d |

## Detalle de trades — v4#2 Test (3T, 67% WR, +4.32%)

| # | Entry | Exit | Salida | PnL | R | MaxR | Dur |
|---|---|---|---|---|---|---|---|
| 1 | 2021-07-23 | 2021-09-20 | — | +4.29% | — | — | 59d |
| 2 | 2021-09-21 | 2021-09-28 | stop | -2.30% | — | — | 7d |
| 3 | 2021-09-29 | 2021-10-22 | — | +2.39% | — | — | 23d |

---

## Comparacion Train vs Test

| Metrica | v4#1 Train | v4#1 Test | v4#2 Train | v4#2 Test | v4#3 Train | v4#3 Test |
|---|---|---|---|---|---|---|
| Trades | 2 | 4 | 3 | 3 | 2 | 4 |
| WR | 100% | 50% | — | **67%** | — | 50% |
| CR | +15.60% | +3.26% | +15.15% | **+4.32%** | +9.45% | +3.26% |
| MaxDD | 0.00% | -4.78% | — | **-2.30%** | — | -4.78% |
| Sharpe | — | 0.20 | — | — | — | — |

---

## Observaciones

1. **Todos los trades de test estan concentrados en un unico cluster: jul-oct 2021.** En 6.25 anos de test, GOOGL solo genera senales VCP (con TT) durante un periodo de 3 meses. Esto hace los resultados estadisticamente no significativos.

2. **v4#2 (tg=3R) es la mejor config por CR y WR en test** (+4.32%, 67% WR), pero el margen sobre v4#1 (+3.26%, 50% WR) es minimo. La diferencia es que v4#2 combina los trades 1 y 2 de v4#1 en un solo trade mas largo.

3. **CR marginal en test**: +3.26% a +4.32% en 6.25 anos no es tradeable. Comparar con B&H GOOGL +363.69% en el mismo periodo.

4. **v4 vs v3**: en v3, COMP#3 (VC + forward + target=3R) logro +14.34% con 2 trades y 100% WR en test. Con TT, GOOGL genera mas trades (3-4) pero de menor calidad (50-67% WR). El TT no filtra mejor que la combinacion VC + forward de v3.

5. **Los 2 losses son consecutivos (sep 2021)**: trades #2 y #3 de v4#1 entran inmediatamente despues de un stop, sugiriendo re-entradas en una correccion activa. Un filtro de cooldown post-loss podria eliminarlos.

6. **El trade ganador principal es el mismo en todas las configs**: entrada 2021-07-23 durante el breakout post-earnings Q2 2021. Es el unico VCP de GOOGL que pasa el filtro TT en 6 anos de test.

---

## Conclusion

**GOOGL con Trend Template produce resultados marginales y no tradeables.** La mejor config (v4#2, tg=3R) logra:

- +4.32% CR en test con 3 trades, 67% WR
- MaxDD -2.30%
- Todos los trades concentrados en jul-oct 2021

Comparado con v3 sin TT (COMP#3: +14.34%, 100% WR, 0% MaxDD), el TT no aporta mejora. Los resultados de v3 ya eran marginales con solo 2 trades; v4 genera mas trades pero introduce losses.

GOOGL no es un candidato viable para VCP con TT. El B&H (+363.69%) supera cualquier config VCP por un factor de 80x. La recomendacion es mantener la config v3 COMP#3 como referencia de minimo riesgo (100% WR, 0% MaxDD) si se insiste en operar VCP en GOOGL.
