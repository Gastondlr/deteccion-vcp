# FX EURUSD High ATR — Insights

---

## Config general

- **Modo:** sequential (un trade a la vez, sin overlap)
- **Split temporal:** TRAIN 2015-2019 / TEST 2020-2026, sin re-optimizacion en TEST
- **Optimizacion:** 2 fases — Fase 1 (grilla deteccion, 432 configs) + Fase 2 (grilla salida, 240 configs)
- **Comision:** no modelada
- **Stop loss FX:** 2% max
- **Metrica principal:** CR (Cumulative Return) = prod(1 + pnl_i) - 1
- **Activo:** EURUSD daily

---

## Objetivo

En los experimentos hourly, se descubrio que `max_depth_atr` bloqueaba el 100% de las contracciones cuando `atr_mult` era alto (>=5), porque los swings son >= atr_mult × ATR por construccion. Deshabilitarlo (`max_depth_atr=None`) desbloqueo el pipeline.

En los experimentos daily previos (`fx_sequential`, `fx_eurusd_detection`), `max_depth_atr` siempre se seteo igual a `depth_atr` (valores 2-6) y `atr_mult` solo llego a 2.5. Este experimento prueba:

1. **atr_mult mas alto** (2.5, 3.0, 4.0, 5.0) — extender mas alla del rango previo
2. **max_depth_atr deshabilitado** (None) vs valores permisivos (4, 6, 8)

---

## Grilla de parametros

### Fase 1 — Deteccion (432 configs)

| Parametro | Valores |
|-----------|---------|
| atr_mult | 2.5, 3.0, 4.0, 5.0 |
| max_depth_atr | None, 4, 6, 8 |
| reduction | 0.40, 0.60, 0.80 |
| lookback_bars | 63, 84, 126 |
| compression_threshold | 0.85, 0.90, 0.95 |
| tolerance | 0.15 (fijo) |
| require_ascending_lows | False (fijo) |

Tolerance y ascending_lows fijados por sensibilidad previa (efecto minimo/inerte).

### Fase 2 — Salida (240 configs)

| Parametro | Valores |
|-----------|---------|
| trailing_atr_multiplier | 1.0, 1.5, 2.0, 2.5, 3.0 |
| target_r_multiple | None, 2.0, 3.0, 5.0 |
| early_exit_days | None, 3, 5 |
| breakeven_r_multiple | 0.5, 1.0, 1.5, 2.0 |

---

## Resultado principal

### Mejor config del experimento

| Parametro | Valor |
|-----------|-------|
| atr_mult | 2.5 |
| max_depth_atr | None |
| reduction | 0.80 |
| lookback_bars | 126 |
| compression_threshold | 0.90 |
| trail | 2.0 |
| target_r_multiple | 2.0 |
| breakeven_r_multiple | 2.0 |

| Split | Senales | Trades | WR | CR |
|-------|---------|--------|----|----|
| TRAIN | 104 | 15 | 40% | +4.58% |
| TEST | 104 | 10 | 50% | +2.08% |
| FULL | 208 | 25 | 44% | +5.72% |

### Comparacion con fx_sequential (CR=+7.93%)

| Metrica | fx_sequential | high_atr (mejor) |
|---------|---------------|------------------|
| TEST CR | **+7.93%** | +2.08% |
| TEST trades | 5 | 10 |
| TEST WR | 80% | 50% |
| Senales TEST | 57 | 104 |

---

## Interaccion atr_mult x max_depth_atr

| atr_mult | max_depth_atr | avg_signals | avg_trades | avg_CR | best_CR | con_senales |
|----------|---------------|-------------|------------|--------|---------|-------------|
| 2.5 | 4 | 23.3 | 3.3 | +0.0141 | +0.0259 | 18/27 |
| 2.5 | 6 | 57.9 | 9.6 | -0.0142 | +0.0174 | 27/27 |
| 2.5 | 8 | 59.1 | 10.0 | -0.0132 | +0.0174 | 27/27 |
| 3.0 | 4 | 0.0 | 0.0 | +0.0000 | +0.0000 | 0/27 |
| 3.0 | 6 | 6.0 | 1.6 | -0.0064 | +0.0000 | 18/27 |
| 3.0 | 8 | 42.3 | 6.4 | -0.0083 | +0.0013 | 18/27 |
| 4.0 | 4 | 0.0 | 0.0 | +0.0000 | +0.0000 | 0/27 |
| 4.0 | 6 | 3.0 | 0.4 | -0.0002 | +0.0061 | 6/27 |
| 4.0 | 8 | 5.0 | 1.6 | -0.0026 | +0.0036 | 18/27 |
| 5.0 | 4 | 0.0 | 0.0 | +0.0000 | +0.0000 | 0/27 |
| 5.0 | 6 | 0.0 | 0.0 | +0.0000 | +0.0000 | 0/27 |
| 5.0 | 8 | 0.0 | 0.0 | +0.0000 | +0.0000 | 0/27 |

**Nota:** `max_depth_atr=None` no aparece correctamente en el DataFrame (se convierte en NaN). La mejor config global usa None y corresponde al primer lugar del Top 30 (atr=2.5, mda=nan, red=0.80, lb=126, comp=0.9, CR=+2.65% en Fase 1).

Hallazgos:
- **atr_mult >= 3.0 con max_depth_atr=4:** 0 senales (mismo bloqueo que en hourly)
- **atr_mult=5.0:** solo funciona con max_depth_atr=None; valores 4/6/8 bloquean todo
- **atr_mult=2.5 domina:** es el unico con senales consistentes en la mayoria de configs

---

## Analisis de senales: high_atr es superset de fx_sequential

Las senales de fx_sequential son un **subconjunto estricto** de las de high_atr (ambas usan atr_mult=2.5):

| Split | fx_sequential | high_atr | En comun | Solo high_atr |
|-------|---------------|----------|----------|---------------|
| TRAIN | 21 | 104 | 21 | 83 |
| TEST | 57 | 104 | 57 | 47 |

Las 47 senales extra en TEST provienen de 2 clusters: julio 2023 (19 senales) y dic 2025 - ene 2026 (28 senales). Corresponden a patrones con contracciones de depth > 5×ATR que max_depth_atr=5 filtra.

---

## Test de aislamiento: max_depth_atr=None en fx_sequential

Para aislar el efecto de max_depth_atr, se corrio la config exacta de fx_sequential cambiando unicamente max_depth_atr de 5 a None:

| Split | max_depth_atr=5 | max_depth_atr=None |
|-------|-----------------|---------------------|
| TRAIN | 21 sen, 3T, WR=100%, **CR=+2.38%** | 39 sen, 6T, WR=50%, CR=-0.29% |
| TEST | 57 sen, 5T, WR=80%, **CR=+7.93%** | 87 sen, 10T, WR=60%, CR=+6.24% |

**max_depth_atr=None empeora ambos splits.**

Trades extra en TRAIN (3): todos stop_loss (-1.07%, -0.74%, -0.82%).

Trades extra en TEST (5): 1W/4L, cluster julio 2023 (1W/3L, -1.93% neto) + 1 marginalmente positivo en dic 2025.

---

## Cruces deteccion x salida (TEST)

| Senales | Salida | Trades | CR |
|---------|--------|--------|----|
| fx_seq | fx_seq (trail=1.5, target=5R) | 5 | **+7.93%** |
| fx_seq | high_atr (trail=2.0, target=2R) | 3 | +2.89% |
| high_atr | fx_seq (trail=1.5, target=5R) | 13 | +4.78% |
| high_atr | high_atr (trail=2.0, target=2R) | 10 | +2.08% |

La salida de fx_sequential (trail=1.5, target=5R) es superior en ambos conjuntos de senales. El trailing tight corta perdidas rapido y el target=5R deja correr el trade de +4.55% (mar-abr 2025).

Los trades extra de high_atr suman -2.92% en TEST con la salida fx_seq (8 trades extra: 2W/6L).

---

## Sensibilidad de otros parametros

| Parametro | Mejor valor | avg_CR | best_CR |
|-----------|-------------|--------|---------|
| reduction | 0.40 | -0.0039 | +0.0142 |
| lookback_bars | 63 | -0.0023 | +0.0259 |
| compression_threshold | 0.90 | -0.0029 | +0.0265 |

Efectos moderados, consistentes con experimentos previos.

---

## Detalle de trades en TEST (config ganadora)

| # | Entrada | Salida | Razon | PnL | R | Dur |
|---|---------|--------|-------|-----|---|-----|
| 1 | 2023-07-11 | 2023-07-21 | trailing_stop | +1.08% | +0.7R | 10d |
| 2 | 2023-07-22 | 2023-07-27 | stop_loss | -1.34% | -0.7R | 5d |
| 3 | 2023-07-28 | 2023-08-14 | stop_loss | -1.17% | -0.6R | 17d |
| 4 | 2025-03-04 | 2025-03-26 | trailing_stop | +1.11% | +0.6R | 22d |
| 5 | 2025-06-02 | 2025-07-14 | trailing_stop | +1.85% | +0.9R | 42d |
| 6 | 2025-07-15 | 2025-07-28 | trailing_stop | -0.09% | -0.0R | 13d |
| 7 | 2025-12-03 | 2025-12-21 | time_exit | +0.38% | +0.2R | 18d |
| 8 | 2025-12-22 | 2026-01-04 | stop_loss | -0.49% | -0.2R | 13d |
| 9 | 2026-01-05 | 2026-01-11 | stop_loss | -0.78% | -0.4R | 6d |
| 10 | 2026-01-12 | 2026-01-30 | trailing_stop | +1.58% | +1.0R | 18d |

Desglose por ano:
- 2023: 3T, WR=33%, CR=-1.44%
- 2025: 5T, WR=60%, CR=+2.76%
- 2026: 2T, WR=50%, CR=+0.79%

---

## Conclusiones

1. **max_depth_atr=None no mejora la deteccion daily.** A diferencia de hourly donde era contradictorio con atr_mult alto, en daily el filtro max_depth_atr=5 descarta correctamente contracciones demasiado profundas que no son VCP genuinos.

2. **atr_mult > 2.5 no aporta en daily.** Con atr_mult=3+ y max_depth_atr numerico, 0 senales. Con max_depth_atr=None, atr_mult=5 produce solo 2 trades en TRAIN (+1.42%). El rango util sigue siendo atr_mult <= 2.5.

3. **Las senales extra de high_atr son ruido.** Las 47 senales adicionales en TEST generan 8 trades extra con CR=-2.92% usando la salida fx_seq. Son patrones con contracciones profundas (>5×ATR) que aparentan VCP pero no producen breakouts rentables.

4. **La config fx_sequential sigue siendo la mejor para EURUSD.** Con atr_mult=2.5, max_depth_atr=5, reduction=0.6, lookback=63, trail=1.5, target=5R: 5T en TEST, WR=80%, CR=+7.93%. Muestras chicas pero resultados consistentes.

5. **La salida importa tanto como la deteccion.** Los cruces muestran que la combinacion trail=1.5 + target=5R es superior a trail=2.0 + target=2R independientemente del set de senales. El trailing tight minimiza perdidas y el target ambicioso captura los movimientos grandes.

6. **El problema de muestra persiste.** 5 trades en TEST (todos en 2025) no son suficientes para validacion estadistica. El siguiente paso deberia ser probar la config fx_sequential en otras monedas (GBPUSD, USDCNH) para sumar trades y diversificar.
