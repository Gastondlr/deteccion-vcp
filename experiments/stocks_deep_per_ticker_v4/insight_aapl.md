# AAPL — Deep Per-Ticker v4 (Trend Template corregido)

## Objetivo

Evaluar el impacto de activar Trend Template (TT=True) corregido en la deteccion VCP para AAPL, con grid search de parametros de deteccion y salida optimizados por ticker individual.

**Train:** 2015-01-02 a 2019-12-31 (1,258 barras) | **Test:** 2020-01-02 a 2026-04-08 (1,574 barras)
**B&H Train:** CR=+168.59%, MaxDD=-38.73% | **B&H Test:** CR=+244.80%, MaxDD=-33.43%

---

## Metodologia

- Grid search por ticker con Trend Template corregido (TT=True)
- Dos bases de deteccion evaluadas: best_CR y alternativa (distinto red)
- Variantes de salida: trailing, target, breakeven, stop loss
- Forward volume filter aplicado como post-filtro en configs seleccionadas
- Evaluacion out-of-sample estricta: train 2015-2019, test 2020-2026

---

## Deteccion base

**best_CR:**
```
atr_mult=2.0, use_close_only=True (C)
max_depth_atr=8, min_total_reduction=0.40, lookback_bars=126
compression_threshold=0.95, tolerance=0.10
max_depth_pct=0.25, ascending_lows_tolerance=0.03
trend_template=True
```

**Alternativa (alt):**
```
Mismos parametros pero min_total_reduction=0.80
```

---

## Tabla comparativa — Train (2015-2019)

| Variante | T | W | L | WR | CR | MaxDD | Sharpe | avgR | PF |
|---|---|---|---|---|---|---|---|---|---|
| **Buy & Hold AAPL** | — | — | — | — | +168.59% | -38.73% | — | — | — |
| **v4#1** w1_t1.2_f3 | 5 | 5 | 0 | **100%** | **+26.79%** | **0.00%** | — | — | **inf** |
| **v4#2** alt no_filter | 5 | 4 | 1 | 80% | +24.08% | — | — | — | — |
| **v4#3** baseline | 5 | 2 | 3 | 40% | +11.74% | — | — | — | — |
| **v4#4** agresivo | 4 | 3 | 1 | 75% | +14.92% | — | — | — | — |

---

## Tabla comparativa — Test (2020-2026)

| Variante | T | W | L | WR | CR | MaxDD | Sharpe | avgR | PF |
|---|---|---|---|---|---|---|---|---|---|
| **Buy & Hold AAPL** | — | — | — | — | +244.80% | -33.43% | — | — | — |
| **v4#1** w1_t1.2_f3 | **0** | — | — | — | — | — | — | — | — |
| **v4#2** alt no_filter | 1 | 0 | 1 | 0% | -3.45% | — | — | — | — |
| **v4#3** baseline | 1 | 0 | 1 | 0% | -3.45% | — | — | — | — |
| **v4#4** agresivo | **0** | — | — | — | — | — | — | — | — |

---

## Configuracion destacada — v4#2 alt (unica con trade en test)

**Deteccion:**
```
atr_mult=2.0, use_close_only=True (C)
max_depth_atr=8, min_total_reduction=0.80, lookback_bars=126
compression_threshold=0.95, tolerance=0.10
max_depth_pct=0.25, ascending_lows_tolerance=0.03
trend_template=True
vol_filter=no_filter
```

**Salida:**
```
(parametros de salida de la config alternativa)
```

---

## Detalle de trades — v4#2 alt Test (1T, 0% WR, -3.45%)

| # | Entry | Exit | Salida | PnL | R | MaxR | Dur |
|---|---|---|---|---|---|---|---|
| 1 | 2021-09-03 | 2021-09-10 | stop_loss | -3.45% | — | — | 7d |

## Detalle de trades — v4#3 baseline Test (1T, 0% WR, -3.45%)

| # | Entry | Exit | Salida | PnL | R | MaxR | Dur |
|---|---|---|---|---|---|---|---|
| 1 | 2021-09-03 | 2021-09-10 | stop_loss | -3.45% | — | — | 7d |

Ambas configs que generan trades en test producen exactamente el mismo trade perdedor.

---

## Comparacion Train vs Test

| Metrica | v4#1 Train | v4#1 Test | v4#2 Train | v4#2 Test | v4#3 Train | v4#3 Test |
|---|---|---|---|---|---|---|
| Trades | 5 | **0** | 5 | 1 | 5 | 1 |
| WR | 100% | — | 80% | **0%** | 40% | **0%** |
| CR | +26.79% | — | +24.08% | **-3.45%** | +11.74% | **-3.45%** |
| MaxDD | 0.00% | — | — | — | — | — |

---

## Observaciones

1. **La mejor config de train (v4#1, 100% WR, forward filter) produce 0 trades en test.** El forward volume filter elimina la unica senal disponible.

2. **Las unicas configs con trades en test (v4#2 y v4#3) producen el mismo trade perdedor**: entrada 2021-09-03, stop_loss el 2021-09-10, -3.45%. Es una senal de baja calidad en la parte alta del mercado pre-correccion 2021-2022.

3. **v4 vs v3**: en v3 sin TT, FWD#1 (w3_t1.2_f5) logro +37.38% con 6 trades en test y 83% WR. Con TT corregido, AAPL pasa de ser un ticker prometedor a uno inviable. El Trend Template destruye la capacidad de deteccion.

4. **El Trend Template es demasiado restrictivo para AAPL**: requiere que el precio este sobre medias moviles clave durante la formacion del VCP. AAPL forma VCPs validos durante correcciones intermedias donde el precio esta temporalmente bajo las medias, y TT los descarta.

5. **use_close_only=True persiste de v3**: consistente con el hallazgo de que AAPL tiene mechas ruidosas que contaminan la deteccion con High/Low.

6. **Degradacion dramatica**: de +26.79% / +24.08% CR en train a 0 trades o -3.45% en test. El sobreajuste es total.

---

## Conclusion

**El Trend Template corregido destruye la viabilidad de VCP para AAPL.** Donde v3 sin TT mostraba resultados solidos (+37.38% CR, 83% WR, 6 trades en test), v4 con TT produce:

- v4#1 (mejor train): 0 trades en test
- v4#2/v4#3: 1 unico trade perdedor (-3.45%)
- v4#4 (agresivo): 0 trades en test

El Trend Template filtra las formaciones VCP de AAPL que ocurren durante correcciones intermedias — precisamente los puntos de entrada de mayor calidad. La recomendacion es no usar TT para AAPL y mantener la config v3 (FWD#1 w3_t1.2_f5, tr=3.0, be=1.0, sl=3%) como referencia.
