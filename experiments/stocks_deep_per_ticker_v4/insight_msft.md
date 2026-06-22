# MSFT — Deep Per-Ticker v4 (Trend Template corregido)

## Objetivo

Evaluar el impacto de activar Trend Template (TT=True) corregido en la deteccion VCP para MSFT, con grid search de parametros de deteccion y salida optimizados por ticker individual.

**Train:** 2015-01-02 a 2019-12-31 (1,258 barras) | **Test:** 2020-01-02 a 2026-04-08 (1,574 barras)
**B&H Train:** CR=+237.25%, MaxDD=-18.58% | **B&H Test:** CR=+133.05%, MaxDD=-37.56%

---

## Metodologia

- Grid search por ticker con Trend Template corregido (TT=True)
- Dos bases de deteccion evaluadas: best_CR y best_WR (parametros distintos)
- Variantes de salida: trailing, target, sin target, agresivo
- Evaluacion out-of-sample estricta: train 2015-2019, test 2020-2026

---

## Deteccion base

Dos bases de deteccion evaluadas:

**best_CR:**
```
atr_mult=2.0, use_close_only=False (HL)
max_depth_atr=None, min_total_reduction=0.80, lookback_bars=126
compression_threshold=0.90, tolerance=0.10
max_depth_pct=0.25, ascending_lows_tolerance=0.03
trend_template=True, volume_contraction=True
```

**best_WR:**
```
atr_mult=3.0, use_close_only=False (HL)
max_depth_atr=6, min_total_reduction=0.60, lookback_bars=126
compression_threshold=0.95, tolerance=0.10
max_depth_pct=0.25, ascending_lows_tolerance=0.01
trend_template=True
```

---

## Tabla comparativa — Train (2015-2019)

| Variante | T | W | L | WR | CR | MaxDD | Sharpe | avgR | PF |
|---|---|---|---|---|---|---|---|---|---|
| **Buy & Hold MSFT** | — | — | — | — | +237.25% | -18.58% | — | — | — |
| **v4#1** best_CR | 6 | 4 | 2 | 67% | **+12.86%** | — | — | — | — |
| **v4#2** best_WR | 3 | 3 | 0 | **100%** | +12.20% | — | — | — | — |
| **v4#3** sin target | 4 | 2 | 2 | 50% | +3.92% | — | — | — | — |
| **v4#4** agresivo | 4 | 3 | 1 | 75% | +7.71% | — | — | — | — |

---

## Tabla comparativa — Test (2020-2026)

| Variante | T | W | L | WR | CR | MaxDD | Sharpe | avgR | PF |
|---|---|---|---|---|---|---|---|---|---|
| **Buy & Hold MSFT** | — | — | — | — | +133.05% | -37.56% | — | — | — |
| **v4#1** best_CR | 4 | 0 | 4 | 0% | -3.72% | — | — | — | — |
| **v4#2** best_WR | **0** | — | — | — | — | — | — | — | — |
| **v4#3** sin target | 2 | 0 | 2 | 0% | -6.31% | — | — | — | — |
| **v4#4** agresivo | 4 | 0 | 4 | 0% | -3.72% | — | — | — | — |

---

## Configuracion destacada

No hay configuracion ganadora. Todas las configs producen 0 trades o resultados negativos en test. Se reporta v4#1 como referencia.

**Deteccion v4#1 (best_CR):**
```
atr_mult=2.0, use_close_only=False (HL)
max_depth_atr=None, min_total_reduction=0.80, lookback_bars=126
compression_threshold=0.90, tolerance=0.10
max_depth_pct=0.25, ascending_lows_tolerance=0.03
trend_template=True, volume_contraction=True
```

---

## Detalle de trades

**v4#1 Test (4T, 0% WR, -3.72%):** 4 trades, todos perdedores.

**v4#2 Test:** 0 trades. La config best_WR (atr=3.0, mda=6, comp=0.95) es demasiado restrictiva con TT para generar senales post-2020.

**v4#3 Test (2T, 0% WR, -6.31%):** 2 trades, ambos perdedores. La peor perdida promedio por trade.

**v4#4 Test (4T, 0% WR, -3.72%):** Mismos 4 trades perdedores que v4#1. Parametros de salida agresivos no cambian el resultado.

---

## Comparacion Train vs Test

| Metrica | v4#1 Train | v4#1 Test | v4#2 Train | v4#2 Test | v4#3 Train | v4#3 Test | v4#4 Train | v4#4 Test |
|---|---|---|---|---|---|---|---|---|
| Trades | 6 | 4 | 3 | **0** | 4 | 2 | 4 | 4 |
| WR | 67% | **0%** | 100% | — | 50% | **0%** | 75% | **0%** |
| CR | +12.86% | **-3.72%** | +12.20% | — | +3.92% | **-6.31%** | +7.71% | **-3.72%** |

---

## Observaciones

1. **TODAS las configs producen 0 trades o resultados negativos en test.** VCP con Trend Template corregido no funciona para MSFT.

2. **0% WR en test para todas las configs con trades**: v4#1 (4T, 0W), v4#3 (2T, 0W), v4#4 (4T, 0W). No hay un solo trade ganador en 6.25 anos de test.

3. **v4#2 (best_WR, 100% WR en train) produce 0 trades en test**: la combinacion atr=3.0 + mda=6 + comp=0.95 + TT es insuperablemente restrictiva.

4. **v3 vs v4 — consistente degradacion**: en v3 sin TT, el Baseline VC logro +4.66% con 5 trades (60% WR). Ya era marginal, pero al menos positivo. Con TT, MSFT pasa a ser completamente negativo.

5. **v4#1 y v4#4 producen los mismos 4 trades perdedores en test**: cambiar parametros de salida (agresivo vs conservador) no rescata senales fundamentalmente malas. El problema es la deteccion, no la salida.

6. **MSFT ya era el peor ticker en v3** (+4.66% CR en test, marginal). TT solo empeora la situacion.

7. **VC=True en best_CR agrega restriccion innecesaria**: volume contraction combinado con TT genera un doble filtro que no tiene sentido para un activo con breakouts de bajo volumen como MSFT.

---

## Conclusion

**VCP no funciona para MSFT con Trend Template corregido.** Todas las configs producen 0 trades o resultados negativos en test:

- v4#1: -3.72% (4T, 0% WR)
- v4#2: 0 trades
- v4#3: -6.31% (2T, 0% WR)
- v4#4: -3.72% (4T, 0% WR)

MSFT ya era marginal en v3 (+4.66% CR en test). El Trend Template no solo no mejora, sino que invierte el signo. Las senales VCP de MSFT son de baja calidad y el TT no filtra las malas — simplemente reduce el pool de trades eliminando potenciales ganadores.

Recomendacion: no usar TT para MSFT. Si se opera VCP en MSFT, usar la config v3 Baseline (VC=True, tr=1.5, be=0.5, sl=3%) como referencia, reconociendo que el retorno es marginal (+4.66% en 6 anos).
