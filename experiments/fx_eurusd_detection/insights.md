# FX EURUSD Detection — Insights

---

## Config general

- **Modo:** sequential (un trade a la vez, sin overlap)
- **Split temporal:** TRAIN 2015-2019 / TEST 2020-2026, sin re-optimizacion en TEST
- **Optimizacion:** 2 fases — Fase 1 (grilla deteccion expandida, 16,800 configs) + Fase 2 (grilla salida, 240 configs)
- **Comision:** no modelada
- **Stop loss FX:** 2% max
- **Metrica principal:** CR (Cumulative Return) = prod(1 + pnl_i) - 1
- **Activo:** EURUSD unicamente

---

## Objetivo

Ampliar la grilla de deteccion respecto a `fx_sequential`, donde 3 parametros estaban fijos y podrian estar filtrando patrones validos en EURUSD:

| Parametro | Valor en `fx_sequential` (fijo) | Valores en este experimento |
|---|---|---|
| compression_threshold | 0.85 | 0.85, 0.90, 0.95, 1.0 |
| require_ascending_lows | True | True, False |
| tolerance | 0.10 | 0.10, 0.15, 0.20 |

Esto multiplica la grilla de Fase 1: 700 x 4 x 2 x 3 = 16,800 configs.

---

## Resultado principal

### Comparacion vs `fx_sequential` (TEST 2020-2026)

| Metrica | `fx_sequential` | `fx_eurusd_detection` |
|---|---|---|
| Senales | 41 | 71 |
| Trades | 5 | 8 |
| Win Rate | 80.0% | 37.5% |
| CR | +7.93% | +6.23% |
| Avg R | — | +0.51 |
| atr_mult | 2.5 | 1.5 |
| depth_atr | 5 | 4 |
| reduction | 0.6 | 0.7 |
| lookback | 63 | 84 |
| compression_threshold | 0.85 (fijo) | 0.9 |
| require_ascending_lows | True (fijo) | False |
| tolerance | 0.10 (fijo) | 0.15 |

### Resultados por split

| Split | Senales | Trades | WR | CR | Avg R | Salidas |
|-------|---------|--------|----|----|-------|---------|
| TRAIN | 70 | 10 | 70% | +7.27% | +0.44 | trailing_stop=6, stop_loss=2, target=1, time_exit=1 |
| TEST | 71 | 8 | 38% | +6.23% | +0.51 | stop_loss=5, target=1, trailing_stop=2 |
| FULL | 141 | 18 | 56% | +13.95% | +0.47 | trailing_stop=8, stop_loss=7, target=2, time_exit=1 |

### Config final seleccionada

**Deteccion:**
- atr_mult=1.5, depth_atr=4, reduction=0.7, lookback=84
- compression_threshold=0.9, require_ascending_lows=False, tolerance=0.15

**Salida:**
- trail=1.5, target=3.0, early=None, be_R=2.0

### Detalle de trades — TEST

| # | Entrada | Salida | Razon | PnL | R-mult | Dias |
|---|---------|--------|-------|-----|--------|------|
| 1 | 2020-05-18 | 2020-06-04 | target | +3.86% | +3.0R | 17 |
| 2 | 2020-06-05 | 2020-06-17 | stop_loss | -0.42% | -0.2R | 12 |
| 3 | 2020-10-21 | 2021-01-08 | trailing_stop | +3.08% | +2.2R | 79 |
| 4 | 2021-07-28 | 2021-08-06 | stop_loss | -0.70% | -0.9R | 9 |
| 5 | 2023-01-01 | 2023-01-02 | stop_loss | -1.08% | -0.5R | 1 |
| 6 | 2024-03-06 | 2024-03-14 | stop_loss | -0.16% | -0.2R | 8 |
| 7 | 2024-03-15 | 2024-03-21 | stop_loss | -0.25% | -0.3R | 6 |
| 8 | 2025-03-04 | 2025-03-21 | trailing_stop | +1.85% | +0.9R | 17 |

---

## Analisis de sensibilidad — Nuevos parametros

### compression_threshold

| Valor | Avg senales | Avg trades | Avg CR | Best CR | Configs con trades |
|-------|-------------|------------|--------|---------|-------------------|
| 0.85 | 23.4 | 4.2 | -1.19% | +3.44% | 2,946 / 4,200 |
| **0.90** | **34.4** | **6.4** | **-0.45%** | **+7.27%** | **3,018 / 4,200** |
| 0.95 | 46.1 | 8.8 | -1.51% | +6.53% | 3,066 / 4,200 |
| 1.0 (off) | 61.0 | 11.2 | -1.19% | +6.00% | 3,066 / 4,200 |

**Conclusion:** 0.90 es el sweet spot. Genera mas senales que 0.85 (+47%) con el mejor CR promedio y best CR de toda la grilla. Valores >= 0.95 relajan demasiado y degradan.

### require_ascending_lows

| Valor | Avg senales | Avg trades | Avg CR | Best CR | Configs con trades |
|-------|-------------|------------|--------|---------|-------------------|
| True | 41.2 | 7.6 | -1.09% | +7.27% | 6,048 / 8,400 |
| False | 41.2 | 7.6 | -1.09% | +7.27% | 6,048 / 8,400 |

**Conclusion:** no tiene efecto alguno en EURUSD. Los resultados son identicos con True y False. Esto indica que en los patrones detectados en EURUSD, los lows ya son ascendentes naturalmente (o el ascending_lows_tolerance=0.03 los cubre). Este parametro puede mantenerse fijo en cualquier valor sin impacto.

### tolerance

| Valor | Avg senales | Avg trades | Avg CR | Best CR | Configs con trades |
|-------|-------------|------------|--------|---------|-------------------|
| 0.10 | 37.7 | 7.1 | -1.32% | +5.72% | 4,032 / 5,600 |
| **0.15** | **41.7** | **7.7** | **-0.78%** | **+7.27%** | **4,032 / 5,600** |
| 0.20 | 44.4 | 8.1 | -1.16% | +4.82% | 4,032 / 5,600 |

**Conclusion:** 0.15 es el sweet spot. Genera +10% mas senales que 0.10 con mejor avg CR y best CR. 0.20 relaja demasiado — acepta secuencias que no son realmente decrecientes, degradando la calidad.

---

## Estabilidad del top: lookback_bars insensible

Las top 30 configs comparten todas el mismo nucleo (atr=1.5, depth=4, red=0.7, comp=0.9, tol=0.15) y solo varian en lookback_bars y require_ascending_lows, produciendo exactamente el mismo resultado (70 sen, 10T, WR=70%, CR=+7.27%). Esto indica que:

1. La config de deteccion es robusta a variaciones de lookback entre 63-126 barras.
2. require_ascending_lows es inerte.
3. El resultado depende fuertemente de atr_mult, depth_atr, reduction, compression_threshold y tolerance.

---

## Conclusiones

1. **Expandir la grilla mejoro la deteccion en TRAIN** (de 3T/WR=100%/CR=+2.38% original a 10T/WR=70%/CR=+7.27%) con el triple de trades.
2. **En TEST el CR se mantiene positivo (+6.23%)** con mas trades (8 vs 5), pero el WR cayo significativamente (38% vs 80%).
3. **La estrategia depende de asimetria**: los 3 trades ganadores en TEST (+3.86%, +3.08%, +1.85%) compensan 5 losses chicas. Esto es consistente con el diseno (trailing stop + target 3R).
4. **compression_threshold=0.90 y tolerance=0.15** son los dos parametros que hicieron la diferencia. require_ascending_lows no tiene impacto.
5. **El cambio de atr_mult (2.5 -> 1.5)** es notable: la config original usaba swings mas amplios, la nueva usa swings mas finos que detectan contracciones mas sutiles.
6. **Con 8 trades en TEST (6 anios), la significancia estadistica sigue siendo limitada.** Se necesitarian mas activos o timeframes para validar.
7. **No hay overfitting severo:** TRAIN CR (+7.27%) y TEST CR (+6.23%) estan en rangos similares, aunque la degradacion del WR (70% -> 38%) sugiere que la config captura algo de ruido.
