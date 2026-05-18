# Informe: Experimento VCP en Data Horaria (FX)

## 1. Objetivo

Evaluar si el patron VCP puede detectarse y explotarse a escala horaria en pares de
divisas, donde los patrones se forman en dias (no meses) y los trades duran horas
(no semanas).

## 2. Data

- **Par:** EURUSD (horario)
- **Fuente:** `data/monedas_hora/EURUSD.csv`
- **TRAIN:** 2015-01-02 a 2019-12-31 (31,052 barras)
- **TEST:** 2020-01-01 a 2026-05-14 (39,471 barras)
- **Cutoff:** 2020-01-01

---

## 3. Filosofia de Parametros

### Primer intento (descartado)

Se escalaron los parametros diarios a horario multiplicando por 24 (ej. ATR=24 horas
para equivaler a ATR=1 dia, lookback=3024 para equivaler a 126 dias). Esto produjo
resultados pobres (EURUSD TEST: -0.07% CR, 28 trades, 32% WR) porque detectaba los
mismos patrones diarios con mas granularidad, sin agregar valor.

### Segundo intento (escala horaria real)

Se rediseñaron los parametros para detectar patrones VCP genuinamente mas pequeños:
patrones que se forman en dias y se operan en horas. Se redujo el ATR, el lookback,
los stops y los tiempos de salida.

---

## 4. Configuracion del Experimento

### 4.1 Parametros fijos

| Parametro | Valor | Justificacion |
|-----------|-------|---------------|
| `atr_length` | 14 (horas) | Ventana de volatilidad corta |
| `max_stop_loss_pct` | 1% | Riesgo maximo por trade |
| `max_entry_distance_pct` | 0.5% | Distancia maxima al pivot para entrar |
| `max_bars_without_progress` | 48 (2 dias) | Corta trades estancados |
| `max_hold_bars` | 360 (15 dias) | Limite maximo de holding |
| `min_contractions` | 2 | Minimo de contracciones para VCP |
| `max_contractions` | 6 | Maximo de contracciones |
| `require_ascending_lows` | True | Lows deben ser ascendentes |
| `compression ratio_threshold` | 0.85 | Umbral de compresion ATR |
| `volume_confirmation` | False | No se requiere confirmacion por volumen |

### 4.2 Grilla de deteccion (Phase 1) — 560 configs

| Parametro | Valores | Cantidad |
|-----------|---------|----------|
| `atr_mult` (swing) | 0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 2.5 | 7 |
| `max_depth_atr` | 1, 2, 3, 4 | 4 |
| `min_total_reduction` | 0.40, 0.50, 0.60, 0.70, 0.80 | 5 |
| `lookback_bars` | 72, 120, 168, 240 (3-10 dias) | 4 |

Evaluadas con parametros de salida fijos: trail=1.5, target=2R, early=None, be_R=1.0

### 4.3 Grilla de salida (Phase 2) — 240 configs

| Parametro | Valores | Cantidad |
|-----------|---------|----------|
| `trailing_atr_multiplier` | 1.0, 1.5, 2.0, 2.5, 3.0 | 5 |
| `target_r_multiple` | None, 1.5, 2.0, 3.0 | 4 |
| `early_exit_days` (horas) | None, 6, 12 | 3 |
| `breakeven_r_multiple` | 0.5, 1.0, 1.5, 2.0 | 4 |

Evaluadas sobre la mejor config de deteccion de Phase 1.

---

## 5. Resultados Phase 1: Grilla de Deteccion

### 5.1 Mejor config por atr_mult (TRAIN, salida fija)

| atr_mult | Swings | Contr | Mejor config | Trades | WR | CR |
|----------|--------|-------|--------------|--------|-----|------|
| 0.75 | 10,706 | 5,352 | d=4, r=0.40, lb=72 | 12 | 33% | +0.16% |
| 1.00 | 8,737 | 4,368 | d=2, r=0.60, lb=240 | 20 | 35% | +1.01% |
| 1.25 | 6,927 | 3,463 | d=2, r=0.50, lb=72 | 7 | 43% | +0.93% |
| 1.50 | 5,466 | 2,732 | d=4, r=0.80, lb=240 | 15 | 33% | +0.41% |
| 1.75 | 4,268 | 2,133 | d=4, r=0.50, lb=240 | 28 | 36% | +1.20% |
| 2.00 | 3,418 | 1,708 | d=4, r=0.50, lb=240 | 22 | 36% | +0.16% |
| 2.50 | 2,210 | 1,104 | d=3, r=0.70, lb=240 | 3 | 67% | +1.85% |

### 5.2 Efecto de atr_mult (promedios sobre todas las configs)

| atr_mult | Avg Trades | Avg CR | Best CR | Configs c/trades |
|----------|-----------|--------|---------|-----------------|
| 0.75 | 7.2 | -0.66% | +0.16% | 72/80 |
| 1.00 | 10.8 | -0.93% | +1.01% | 60/80 |
| 1.25 | 10.8 | -0.41% | +0.93% | 60/80 |
| 1.50 | 11.8 | -0.77% | +0.41% | 56/80 |
| 1.75 | 10.9 | -0.14% | +1.20% | 52/80 |
| 2.00 | 8.1 | -0.34% | +0.16% | 44/80 |
| 2.50 | 3.0 | +0.23% | +1.85% | 32/80 |

**Observacion:** El avg CR es negativo para todos los atr_mult excepto 2.5, lo cual
indica que la mayoria de las configuraciones pierden dinero. Solo atr_mult=2.5 tiene
un promedio positivo, pero con muy pocos trades (avg=3).

### 5.3 Mejor config global (TRAIN)

```
atr_mult=2.5, depth_atr=3, reduction=0.7, lookback_bars=168
-> 93 señales, 3 trades, WR=67%, CR=+1.85%
```

**Nota:** El lookback_bars fue indiferente — la misma config produjo identicos
resultados con lb=72, 120, 168 y 240.

---

## 6. Resultados Phase 2: Grilla de Salida

Usando la mejor config de deteccion (atr_mult=2.5, d=3, r=0.7, lb=168):

| trail | target | early | be_R | Trades | WR | CR |
|-------|--------|-------|------|--------|-----|------|
| 2.5 | None | None | 1.0 | 3 | 67% | +2.58% |
| 2.5 | None | 6 | 1.0 | 3 | 67% | +2.58% |
| 3.0 | None | None | 1.0 | 3 | 67% | +2.40% |
| 2.5 | 3.0 | 6 | 1.5 | 3 | 67% | +2.39% |

**Mejor config completa (TRAIN):**
```
Deteccion: atr_mult=2.5, depth_atr=3, reduction=0.7, lookback=168
Salida:    trail=2.5, target=None, early=None, be_R=1.0
-> 3 trades, 67% WR, CR=+2.58%, avg R=+2.98
```

---

## 7. Evaluacion de Robustez

### 7.1 Problema: metrica de seleccion

La seleccion por maximo CR favorece configs con pocos trades que tuvieron suerte.
Se evaluo el impacto comparando dos configs:

- **Config A (max CR):** atr_mult=2.5, d=3, r=0.7, lb=168 — 3 trades
- **Config B (min 10 trades):** atr_mult=2.5, d=4, r=0.8, lb=72 — 17 trades

### 7.2 Comparacion TRAIN vs TEST

#### Config A — max CR (3 trades)

| Split | Trades | WR | CR | Avg R |
|-------|--------|-----|------|-------|
| TRAIN | 3 | 67% | +2.58% | +2.98 |
| TEST | 2 | 0% | -0.61% | -0.86 |

Detalle TRAIN:
| Trade | Fecha | Salida | PnL | R |
|-------|-------|--------|-----|---|
| 1 | 2015-03-18 | trailing_stop | +1.43% | +2.9R |
| 2 | 2016-04-19 | stop_loss | -0.13% | -0.4R |
| 3 | 2017-12-27 | trailing_stop | +1.27% | +6.4R |

Detalle TEST:
| Trade | Fecha | Salida | PnL | R |
|-------|-------|--------|-----|---|
| 1 | 2020-04-13 | stop_loss | -0.44% | -1.3R |
| 2 | 2025-03-18 | stop_loss | -0.17% | -0.4R |

#### Config B — min 10 trades (17 trades), con early_exit=6h

| Split | Trades | WR | CR | Avg R |
|-------|--------|-----|------|-------|
| TRAIN | 17 | 18% | +3.35% | +0.41 |
| TEST | 18 | 0% | -1.77% | -0.23 |

En TEST, 0% win rate: los 18 trades fueron perdedores.
14 de 17 trades TRAIN salieron por early_exit con perdidas chicas; el resultado
positivo depende de solo 3 trades ganadores grandes.

#### Config B — min 10 trades, sin early_exit

| Split | Trades | WR | CR | Avg R |
|-------|--------|-----|------|-------|
| TRAIN | 17 | 35% | +2.13% | +0.06 |
| TEST | 18 | 17% | -1.59% | -0.23 |

Mejor config de salida sin early: trail=1.0, target=2R, be_R=2.0

Detalle TEST (18 trades):
| Trade | Fecha | Salida | PnL | R |
|-------|-------|--------|-----|---|
| 1 | 2020-04-13 | stop_loss | -0.14% | -0.4R |
| 2 | 2020-07-29 | stop_loss | -0.07% | -0.1R |
| 3 | 2021-10-04 | trailing_stop | +0.01% | +0.0R |
| 4 | 2022-05-09 | stop_loss | -0.13% | -0.2R |
| 5 | 2022-08-26 | trailing_stop | -0.18% | -0.4R |
| 6 | 2022-10-26 | trailing_stop | -0.01% | -0.0R |
| 7 | 2023-02-09 | trailing_stop | -0.01% | -0.0R |
| 8 | 2023-09-18 | stop_loss | -0.14% | -0.4R |
| 9 | 2024-04-25 | stop_loss | -0.26% | -0.7R |
| 10 | 2024-06-18 | stop_loss | -0.12% | -0.3R |
| 11 | 2024-08-27 | stop_loss | -0.07% | -0.2R |
| 12 | 2024-12-30 | stop_loss | -0.59% | -1.6R |
| 13 | 2025-03-18 | trailing_stop | -0.01% | -0.0R |
| 14 | 2025-07-01 | stop_loss | -0.13% | -0.2R |
| 15 | 2025-09-05 | trailing_stop | +0.44% | +0.9R |
| 16 | 2025-12-16 | trailing_stop | -0.07% | -0.2R |
| 17 | 2026-02-25 | trailing_stop | +0.04% | +0.1R |
| 18 | 2026-04-07 | stop_loss | -0.16% | -0.4R |

Solo 3 de 18 trades fueron positivos, y el mayor ganador fue +0.44%.

---

## 8. Conclusiones

1. **VCP a escala horaria no muestra edge en EURUSD.** Todas las configuraciones
   evaluadas — con y sin early_exit, con distintos criterios de seleccion — producen
   resultados negativos en TEST.

2. **El CR como metrica de seleccion sesga hacia configs con pocos trades.** La config
   ganadora por CR tenia solo 3 trades, estadisticamente insignificante. Al requerir
   minimo 10 trades, el CR sigue positivo en TRAIN pero colapsa en TEST.

3. **Los movimientos horarios son demasiado pequeños.** Los trades duran horas
   (la mayoria <1 dia) y los movimientos son insuficientes para superar los costos
   del stop loss. El mejor trade en TEST fue +0.44%.

4. **El lookback_bars fue indiferente.** Las 4 variantes (72, 120, 168, 240)
   produjeron resultados identicos para las mejores configs, indicando que este
   parametro no es un discriminador relevante a escala horaria.

5. **Contraste con escala diaria.** En el experimento diario, EURUSD con
   atr_mult=1.75 produjo 12 trades en TRAIN con CR=+7.23% y resultados positivos
   en TEST. Los patrones VCP necesitan mas tiempo para formarse y generar movimientos
   post-breakout significativos.

---

## 9. Scripts Utilizados

| Script | Descripcion |
|--------|-------------|
| `run_fx_temporal_stability_hourly.py` | Experimento principal: Phase 1 (560 configs deteccion) + Phase 2 (240 configs salida) sobre TRAIN |
| `compare_hourly_configs.py` | Comparacion Config A (max CR) vs Config B (min 10T) en TRAIN y TEST |
| `compare_hourly_no_early.py` | Config B sin early_exit, 80 configs de salida en TRAIN y TEST |

## 10. Tiempo de Ejecucion

- Phase 1 (560 configs deteccion): ~3 horas
- Phase 2 (240 configs salida): ~77 segundos
- Comparacion 2 configs con TEST: ~20 minutos
- Comparacion sin early_exit: ~6 minutos

El cuello de botella es `run_full_vcp_pipeline` con 31K barras horarias: cada config
tarda 13-23 segundos dependiendo del atr_mult (mas swings = mas lento).
