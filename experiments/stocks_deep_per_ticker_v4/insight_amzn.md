# AMZN — Deep Per-Ticker v4 (Trend Template corregido)

## Objetivo

Evaluar el impacto de activar Trend Template (TT=True) corregido en la deteccion VCP para AMZN, con grid search de parametros de deteccion y salida optimizados por ticker individual.

**Train:** 2015-01-02 a 2019-12-31 (1,258 barras) | **Test:** 2020-01-02 a 2026-04-08 (1,574 barras)
**B&H Train:** CR=+498.94%, MaxDD=-34.10% | **B&H Test:** CR=+133.14%, MaxDD=-56.15%

---

## Metodologia

- Grid search por ticker con Trend Template corregido (TT=True)
- Deteccion unica evaluada: atr=3.0, Close, lb=126
- Variantes de salida: trailing, target, breakeven, stop loss
- Forward volume filter aplicado como post-filtro en configs seleccionadas
- Evaluacion out-of-sample estricta: train 2015-2019, test 2020-2026

---

## Deteccion base

```
atr_mult=3.0, use_close_only=True (C)
max_depth_atr=None, min_total_reduction=0.60, lookback_bars=126
compression_threshold=0.95, tolerance=0.10
max_depth_pct=0.25, ascending_lows_tolerance=0.03
trend_template=True, volume_contraction=False
```

---

## Tabla comparativa — Train (2015-2019)

| Variante | T | W | L | WR | CR | MaxDD | Sharpe | avgR | PF |
|---|---|---|---|---|---|---|---|---|---|
| **Buy & Hold AMZN** | — | — | — | — | +498.94% | -34.10% | — | — | — |
| **v4#1** no_filter | 7 | 4 | 3 | 57% | +42.66% | -1.52% | 0.73 | +1.11 | 16.6 |
| **v4#3** best_WR w3_t1.2_f5 | 4 | 4 | 0 | **100%** | +37.52% | **0.00%** | — | — | **inf** |
| **v4#4** conservador | 5 | 4 | 1 | 80% | +38.18% | -0.97% | — | — | — |

---

## Tabla comparativa — Test (2020-2026)

| Variante | T | W | L | WR | CR | MaxDD | Sharpe | avgR | PF |
|---|---|---|---|---|---|---|---|---|---|
| **Buy & Hold AMZN** | — | — | — | — | +133.14% | -56.15% | — | — | — |
| **v4#1** no_filter | **0** | — | — | — | — | — | — | — | — |
| **v4#3** best_WR w3_t1.2_f5 | **0** | — | — | — | — | — | — | — | — |
| **v4#4** conservador | **0** | — | — | — | — | — | — | — | — |

---

## Configuracion destacada — v4#1 (mejor CR en train)

**Deteccion:**
```
atr_mult=3.0, use_close_only=True (C)
max_depth_atr=None, min_total_reduction=0.60, lookback_bars=126
compression_threshold=0.95, tolerance=0.10
max_depth_pct=0.25, ascending_lows_tolerance=0.03
trend_template=True, volume_contraction=False
vol_filter=no_filter
```

**Salida:**
```
(mejor config de train — irrelevante dado 0 trades en test)
```

---

## Detalle de trades

**Todas las configs producen 0 trades en test.** No hay detalle de trades OOS que reportar.

El mejor resultado en train es v4#1 con 7 trades (4W/3L, 57% WR, +42.66% CR), pero la config no genera ninguna senal en el periodo 2020-2026 con Trend Template activado.

---

## Comparacion Train vs Test

| Metrica | v4#1 Train | v4#1 Test | v4#3 Train | v4#3 Test | v4#4 Train | v4#4 Test |
|---|---|---|---|---|---|---|
| Trades | 7 | **0** | 4 | **0** | 5 | **0** |
| WR | 57% | — | 100% | — | 80% | — |
| CR | +42.66% | — | +37.52% | — | +38.18% | — |
| MaxDD | -1.52% | — | 0.00% | — | -0.97% | — |

---

## Observaciones

1. **TODAS las configuraciones producen 0 trades en test.** Sobreajuste completo — los parametros de deteccion que funcionan en train (2015-2019) no generan ninguna senal en el periodo 2020-2026.

2. **El problema persiste desde v3**: en v3 sin TT, las configs ganadoras (atr=3.0, VC=True) tambien producian 0 trades en test. Activar TT no mejora ni empeora — el problema es de deteccion base, no de filtro de tendencia.

3. **AMZN cambio de regimen post-2020**: COVID crash, caida -55% en 2022, y tariffs 2025 generan consolidaciones donde volatilidad y volumen no se comprimen simultaneamente. Las consolidaciones de AMZN ya no se comportan como VCPs clasicos.

4. **El Trend Template agrega restriccion sobre un activo que ya no genera VCPs detectables.** TT requiere que el precio este sobre las medias moviles clave — combinado con los parametros de deteccion restrictivos (atr=3.0, comp=0.95), el filtro es insuperable para AMZN post-2020.

5. **Train muestra buenos resultados enganiosos**: v4#1 con +42.66% CR y PF=16.6, v4#3 con 100% WR. Son metricas que no tienen ninguna relevancia predictiva dado 0 senales OOS.

---

## Conclusion

**AMZN no es viable para la estrategia VCP** ni con TT corregido ni sin el. El resultado es identico a v3: 0 trades en test para todas las configuraciones con los parametros de deteccion optimizados en train.

El problema es estructural:
- Los params de deteccion que funcionan en 2015-2019 no producen NINGUNA senal en 2020-2026
- El Trend Template no resuelve ni agrava el problema — la causa raiz es la incompatibilidad de los parametros de deteccion con el regimen post-2020 de AMZN
- Las consolidaciones post-2020 de AMZN no exhiben la compresion simultanea de ATR y volumen que define un VCP clasico

Recomendacion: excluir AMZN del universo VCP o explorar un grid radicalmente diferente (atr_mult mas bajo, lookback mas corto, sin comp/VC).
