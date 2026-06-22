# NVDA — Deep Per-Ticker v4 (Trend Template corregido)

## Objetivo

Evaluar el impacto de activar Trend Template (TT=True) corregido en la deteccion VCP para NVDA, con grid search de parametros de deteccion y salida optimizados por ticker individual.

**Train:** 2015-01-02 a 2019-12-31 (1,258 barras) | **Test:** 2020-01-02 a 2026-04-08 (1,574 barras)
**B&H Train:** CR=+1068.79%, MaxDD=-56.08% | **B&H Test:** CR=+2935.78%, MaxDD=-66.36%

---

## Metodologia

- Grid search por ticker con Trend Template corregido (TT=True)
- Dos bases de deteccion evaluadas: best_CR y best_WR (parametros de deteccion distintos)
- Variantes de salida: trailing, target, early exit, breakeven, stop loss
- Forward volume filter aplicado como post-filtro en configs seleccionadas
- Evaluacion out-of-sample estricta: train 2015-2019, test 2020-2026

---

## Deteccion base

Dos bases de deteccion evaluadas:

**best_CR:**
```
atr_mult=3.0, use_close_only=False (HL)
max_depth_atr=None, min_total_reduction=0.80, lookback_bars=126
compression_threshold=0.95, tolerance=0.10
max_depth_pct=0.25, ascending_lows_tolerance=0.03
trend_template=True, volume_contraction=False
```

**best_WR:**
```
atr_mult=2.0, use_close_only=False (HL)
max_depth_atr=None, min_total_reduction=0.60, lookback_bars=63
compression_threshold=0.90, tolerance=0.10
max_depth_pct=0.25, ascending_lows_tolerance=0.01
trend_template=True, volume_contraction=False
```

---

## Tabla comparativa — Train (2015-2019)

| Variante | T | W | L | WR | CR | MaxDD | Sharpe | avgR | PF |
|---|---|---|---|---|---|---|---|---|---|
| **Buy & Hold NVDA** | — | — | — | — | +1068.79% | -56.08% | — | — | — |
| **v4#1** best_CR no_filter tr=2.5 tg=5R early=5d be=1.0 sl=5% | 11 | 4 | 7 | 36% | +74.87% | -3.69% | 0.74 | +1.16 | 10.6 |
| **v4#4** best_WR w1_t1.2_f3 tr=1.0 tg=3R be=0.5 sl=5% | **5** | **5** | **0** | **100%** | +49.52% | **0.00%** | **1.13** | **+1.73** | **inf** |
| **v4#5** best_CR no_filter tr=2.5 be=1.0 sl=3% (sin target/early) | 11 | 7 | 4 | 64% | +49.17% | -9.82% | 0.74 | +1.33 | 4.2 |

---

## Tabla comparativa — Test (2020-2026)

| Variante | T | W | L | WR | CR | MaxDD | Sharpe | avgR | PF |
|---|---|---|---|---|---|---|---|---|---|
| **Buy & Hold NVDA** | — | — | — | — | +2935.78% | -66.36% | — | — | — |
| **v4#1** best_CR no_filter tr=2.5 tg=5R early=5d be=1.0 sl=5% | **0** | — | — | — | — | — | — | — | — |
| **v4#4** best_WR w1_t1.2_f3 tr=1.0 tg=3R be=0.5 sl=5% | **3** | **3** | **0** | **100%** | **+36.93%** | **0.00%** | **0.99** | **+2.27** | **inf** |
| **v4#5** best_CR no_filter tr=2.5 be=1.0 sl=3% (sin target/early) | **0** | — | — | — | — | — | — | — | — |

---

## Configuracion destacada — v4#4 best_WR w1_t1.2_f3

**Deteccion:**
```
atr_mult=2.0, use_close_only=False (HL)
max_depth_atr=None, min_total_reduction=0.60, lookback_bars=63
compression_threshold=0.90, tolerance=0.10
max_depth_pct=0.25, ascending_lows_tolerance=0.01
trend_template=True, volume_contraction=False
vol_filter=w1_t1.2_f3 (backward 1 dia, threshold 1.2x, forward 3 dias)
```

**Salida:**
```
trailing_atr_multiplier=1.0, target_r_multiple=3.0
early_exit_days=None, breakeven_r_multiple=0.5, max_stop_loss_pct=0.05
```

---

## Detalle de trades — v4#4 Train (5T, 100% WR, +49.52%)

| # | Entry | Exit | Salida | PnL | R | MaxR | Dur |
|---|---|---|---|---|---|---|---|
| 1 | 2017-05-10 | 2017-05-17 | trailing_stop | +5.30% | +1.1R | — | 7d |
| 2 | 2017-05-18 | 2017-06-08 | target | +20.19% | +4.0R | — | 21d |
| 3 | 2017-09-15 | 2017-09-21 | trailing_stop | +0.36% | +0.1R | — | 6d |
| 4 | 2017-09-26 | 2017-10-16 | target | +15.10% | +3.0R | — | 20d |
| 5 | 2017-11-09 | 2017-11-15 | trailing_stop | +2.27% | +0.5R | — | 6d |

## Detalle de trades — v4#4 Test (3T, 100% WR, +36.93%)

| # | Entry | Exit | Salida | PnL | R | MaxR | Dur |
|---|---|---|---|---|---|---|---|
| 1 | 2024-01-08 | 2024-01-24 | target | +17.43% | +3.5R | — | 16d |
| 2 | 2024-02-05 | 2024-02-20 | trailing_stop | +0.17% | +0.0R | — | 15d |
| 3 | 2024-02-21 | 2024-02-22 | target | +16.40% | +3.3R | — | 1d |

---

## Comparacion Train vs Test

| Metrica | v4#4 Train | v4#4 Test | v4#1 Train | v4#1 Test | v4#5 Train | v4#5 Test |
|---|---|---|---|---|---|---|
| Trades | 5 | 3 | 11 | **0** | 11 | **0** |
| WR | 100% | **100%** | 36% | — | 64% | — |
| CR | +49.52% | **+36.93%** | +74.87% | — | +49.17% | — |
| MaxDD | 0.00% | **0.00%** | -3.69% | — | -9.82% | — |
| Sharpe | 1.13 | **0.99** | 0.74 | — | 0.74 | — |
| avgR | +1.73 | **+2.27** | +1.16 | — | +1.33 | — |
| PF | inf | **inf** | 10.6 | — | 4.2 | — |

---

## Observaciones

1. **La config best_CR (atr=3.0, lb=126) produce 11 trades en train y 0 en test** — completamente sobre-ajustada. El Trend Template corregido con parametros restrictivos elimina todas las senales post-2020.

2. **Solo la config best_WR con forward volume filter (w1_t1.2_f3) sobrevive al test** con 3 trades, todos ganadores. La base de deteccion es DIFERENTE (atr=2.0, lb=63 vs atr=3.0, lb=126).

3. **Los parametros de deteccion v3-style (atr bajo, lookback corto) capturan mejor los VCPs de NVDA** incluso con TT corregido. Esto sugiere que el lookback=63 es critico para NVDA — consistente con v2 y v3.

4. **3 trades en test concentrados en ene-feb 2024** — la explosion AI/semiconductores genera VCPs de alta calidad. Trade #1 (+17.43%, target) y trade #3 (+16.40%, target en 1 dia) son excepcionales.

5. **El trailing tight (tr=1.0) combinado con target=3R es clave**: captura ganancias rapido con breakeven temprano (be=0.5). Compara con v4#1 que usa tr=2.5 y no sobrevive al test.

6. **avgR mejora de train (+1.73) a test (+2.27)** — los trades de test son de mayor calidad promedio que los de train, aunque hay menos.

7. **v4 vs v3**: en v3 sin TT, FWD#2 (w1_t1.2_f3) logro +142.36% con 6 trades en test. Con TT corregido, la misma variante de filtro produce solo 3 trades y +36.93%. El Trend Template reduce significativamente el trade count.

---

## Conclusion

**El Trend Template corregido reduce drasticamente las senales para NVDA.** Solo la config best_WR con forward volume filter (w1_t1.2_f3, atr=2.0, lb=63) produce trades en test:

- 3 trades, 100% WR, +36.93% CR, MaxDD 0.00%
- Sharpe 0.99 en test, PF infinito
- Todos los trades en ene-feb 2024 (cluster temporal)

Las configs best_CR (atr=3.0, lb=126) estan completamente sobre-ajustadas: 11 trades en train, 0 en test. El TT agrega un filtro de tendencia que, combinado con parametros restrictivos, elimina todas las senales del periodo post-2020.

La recomendacion es usar la config v4#4 (best_WR + forward filter) como referencia conservadora, pero reconocer que v3 sin TT produce resultados superiores para NVDA (+142% vs +37% en test). El Trend Template no aporta valor para este ticker.
