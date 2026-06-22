# META — Deep Per-Ticker v4 (Trend Template corregido)

## Objetivo

Evaluar el impacto de activar Trend Template (TT=True) corregido en la deteccion VCP para META, con grid search de parametros de deteccion y salida optimizados por ticker individual.

**Train:** 2015-01-02 a 2019-12-31 (1,258 barras) | **Test:** 2020-01-02 a 2026-04-08 (1,574 barras)
**B&H Train:** CR=+161.63%, MaxDD=-42.96% | **B&H Test:** CR=+178.67%, MaxDD=-76.74%

---

## Metodologia

- Grid search por ticker con Trend Template corregido (TT=True)
- Dos bases de deteccion evaluadas: best_CR y best_WR (parametros de deteccion distintos)
- Variantes de salida: trailing, target, breakeven, stop loss
- Evaluacion out-of-sample estricta: train 2015-2019, test 2020-2026

---

## Deteccion base

Dos bases de deteccion evaluadas:

**best_CR:**
```
atr_mult=2.0, use_close_only=False (HL)
max_depth_atr=None, min_total_reduction=0.80, lookback_bars=63
compression_threshold=0.85, tolerance=0.20
max_depth_pct=0.25, ascending_lows_tolerance=0.03
trend_template=True
```

**best_WR:**
```
atr_mult=2.0, use_close_only=False (HL)
max_depth_atr=None, min_total_reduction=0.40, lookback_bars=63
compression_threshold=0.85, tolerance=0.10
max_depth_pct=0.25, ascending_lows_tolerance=0.01
trend_template=True
```

---

## Tabla comparativa — Train (2015-2019)

| Variante | T | W | L | WR | CR | MaxDD | Sharpe | avgR | PF |
|---|---|---|---|---|---|---|---|---|---|
| **Buy & Hold META** | — | — | — | — | +161.63% | -42.96% | — | — | — |
| **v4#1** best_CR | 6 | 4 | 2 | 67% | +7.35% | — | — | — | — |
| **v4#2** best_CR tg=2R | 6 | — | — | — | +7.35% | — | — | — | — |
| **v4#3** best_WR | 3 | 3 | 0 | **100%** | +6.76% | — | — | — | — |
| **v4#4** agresivo | 6 | — | — | — | +0.55% | — | — | — | — |

---

## Tabla comparativa — Test (2020-2026)

| Variante | T | W | L | WR | CR | MaxDD | Sharpe | avgR | PF |
|---|---|---|---|---|---|---|---|---|---|
| **Buy & Hold META** | — | — | — | — | +178.67% | -76.74% | — | — | — |
| **v4#1** best_CR | 4 | 1 | 3 | 25% | -6.47% | — | — | — | — |
| **v4#2** best_CR tg=2R | 8 | 1 | 7 | 12% | -3.90% | — | — | — | — |
| **v4#3** best_WR | 1 | 0 | 1 | 0% | -1.07% | — | — | — | — |
| **v4#4** agresivo | 5 | 2 | 3 | 40% | -9.29% | — | — | — | — |

---

## Configuracion destacada

No hay configuracion ganadora. Todas las configs son negativas en test. Se destaca v4#3 (best_WR) como la de menor perdida (-1.07%) pero con solo 1 trade perdedor.

**Deteccion v4#3 (best_WR):**
```
atr_mult=2.0, use_close_only=False (HL)
max_depth_atr=None, min_total_reduction=0.40, lookback_bars=63
compression_threshold=0.85, tolerance=0.10
max_depth_pct=0.25, ascending_lows_tolerance=0.01
trend_template=True
```

---

## Detalle de trades

**v4#1 Test (4T, 25% WR, -6.47%):** 1 ganador, 3 perdedores. CR negativo.

**v4#2 Test (8T, 12% WR, -3.90%):** 1 ganador, 7 perdedores. El target=2R genera mas entradas pero la tasa de exito es pesima (12%).

**v4#3 Test (1T, 0% WR, -1.07%):** Un unico trade perdedor.

**v4#4 Test (5T, 40% WR, -9.29%):** 2 ganadores, 3 perdedores. La peor perdida acumulada.

---

## Comparacion Train vs Test

| Metrica | v4#1 Train | v4#1 Test | v4#2 Train | v4#2 Test | v4#3 Train | v4#3 Test | v4#4 Train | v4#4 Test |
|---|---|---|---|---|---|---|---|---|
| Trades | 6 | 4 | 6 | 8 | 3 | 1 | 6 | 5 |
| WR | 67% | **25%** | — | **12%** | 100% | **0%** | — | **40%** |
| CR | +7.35% | **-6.47%** | +7.35% | **-3.90%** | +6.76% | **-1.07%** | +0.55% | **-9.29%** |

---

## Observaciones

1. **TODAS las configuraciones son negativas en test.** VCP con Trend Template corregido no funciona para META. Es una degradacion total respecto a v3.

2. **v3 vs v4 — degradacion dramatica**: en v3 sin TT, el Baseline logro +107.47% CR con 27 trades en test (Sharpe 0.96). Con TT corregido, la mejor config pierde -1.07% con 1 trade. El Trend Template destruye completamente la capacidad de META para generar VCPs.

3. **META genera VCPs durante recuperaciones post-crash** (2020, 2023) — momentos donde el precio esta por debajo de las medias moviles. El TT requiere que el precio este SOBRE las medias, descartando precisamente las mejores formaciones.

4. **v4#2 con target=2R genera 8 trades pero solo 1 ganador (12% WR)**: el target fijo genera re-entradas repetidas en senales de baja calidad. Mas trades = mas perdidas en este caso.

5. **lookback_bars=63 es consistente**: tanto best_CR como best_WR usan lb=63, heredado de v3. META necesita lookback corto para capturar contracciones rapidas.

6. **El CR en train ya es bajo** (+0.55% a +7.35%): incluso en el periodo de optimizacion, el TT limita severamente el retorno. Comparar con v3 Baseline train de +59.56%.

7. **v4#4 (agresivo) es la peor config** con -9.29% CR en test. Parametros mas permisivos no ayudan — generan mas trades de baja calidad.

---

## Conclusion

**VCP no funciona para META con Trend Template corregido.** Todas las configuraciones son negativas en test:

- v4#1: -6.47% (4T, 25% WR)
- v4#2: -3.90% (8T, 12% WR)
- v4#3: -1.07% (1T, 0% WR)
- v4#4: -9.29% (5T, 40% WR)

La causa raiz es que el Trend Template exige precio sobre medias moviles, pero META genera sus mejores VCPs durante recuperaciones donde el precio esta temporalmente debajo de las medias (post-crash 2020, post-crash 2022-2023).

Recomendacion: no usar TT para META. La config v3 Baseline (no_filter, VC=True, tr=1.5, tg=2R, sl=3%) con +107.47% CR y 27 trades en test sigue siendo la referencia. META es el ticker con mejor performance del proyecto, pero SOLO sin Trend Template.
