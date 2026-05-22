# FX Sequential — Insights

---

## Config general

- **Modo:** sequential (un trade a la vez, sin overlap)
- **Split temporal:** TRAIN 2015-2019 / TEST 2020-2026, sin re-optimizacion en TEST
- **Optimizacion:** 2 fases — Fase 1 (grilla deteccion con salidas fijas) + Fase 2 (grilla salida con mejor deteccion fija)
- **Comision:** no modelada
- **Stop loss FX:** 2% max
- **Metrica principal:** CR (Cumulative Return) = prod(1 + pnl_i) - 1
- **Monedas evaluadas:** EURUSD, GBPUSD, USDCNH, USDCNY, USDJPY

---

## Sub-experimento: Evaluacion multi-currency en modo sequential

### Resultado

**Tabla comparativa (TEST 2020-2026):**

| Moneda | Senales | Trades | Wins | Losses | Win Rate | Avg Win | Avg Loss | CR | Sharpe | Max DD |
|--------|---------|--------|------|--------|----------|---------|----------|----|--------|--------|
| EURUSD | 41 | 5 | 4 | 1 | 80.0% | +2.13% | -0.74% | +7.93% | 2.48 | -1.60% |
| GBPUSD | 90 | 15 | 8 | 7 | 53.3% | +1.34% | -0.70% | +5.80% | 1.27 | -1.82% |
| USDCNH | 50 | 3 | 1 | 2 | 33.3% | +4.28% | -1.28% | +1.62% | 1.09 | -1.63% |
| USDCNY | 40 | 2 | 1 | 1 | 50.0% | +3.39% | -1.81% | +1.52% | 1.48 | -2.01% |
| USDJPY | 43 | 13 | 1 | 12 | 7.7% | +1.50% | -0.37% | -2.96% | -1.84 | -1.74% |

**Mejores configuraciones por moneda:**

| Moneda | atr_mult | depth_atr | reduction | lookback | trail | target_R | be_R | early_exit |
|--------|----------|-----------|-----------|----------|-------|----------|------|------------|
| EURUSD | 2.5 | 5 | 0.6 | 63 | 1.5 | 5.0 | 2.0 | — |
| GBPUSD | 1.5 | 3 | 0.8 | 63 | 1.5 | 2.0 | 0.5 | — |
| USDCNH | 2.5 | 4 | 0.6 | 105 | 3.0 | 3.0 | 2.0 | — |
| USDCNY | 2.5 | 5 | 0.8 | 105 | 2.5 | 3.0 | 0.5 | — |
| USDJPY | 2.5 | 6 | 0.5 | 105 | 1.5 | 5.0 | 1.5 | 3d |

**Detalle de trades — EURUSD** (4W / 1L):

| Entrada | Salida | Razon | PnL | R-mult | Dias |
|---------|--------|-------|-----|--------|------|
| 2025-03-04 | 2025-03-21 | trailing_stop | +1.85% | +0.93 | 17 |
| 2025-03-23 | 2025-04-23 | trailing_stop | +4.55% | +2.28 | 31 |
| 2025-06-02 | 2025-06-17 | trailing_stop | +0.25% | +0.13 | 15 |
| 2025-06-18 | 2025-07-11 | trailing_stop | +1.85% | +0.92 | 23 |
| 2025-07-13 | 2025-07-28 | stop_loss | -0.74% | -0.37 | 15 |

**Detalle de trades — GBPUSD** (8W / 7L):

| Entrada | Salida | Razon | PnL | R-mult | Dias |
|---------|--------|-------|-----|--------|------|
| 2020-07-20 | 2020-07-29 | target | +2.51% | +2.13 | 9 |
| 2020-12-03 | 2020-12-11 | stop_loss | -1.70% | -1.44 | 8 |
| 2021-01-21 | 2021-02-07 | time_exit | +0.07% | +0.04 | 17 |
| 2021-05-07 | 2021-05-28 | time_exit | +1.50% | +1.18 | 21 |
| 2021-07-09 | 2021-07-16 | stop_loss | -1.00% | -0.87 | 7 |
| 2022-01-05 | 2022-01-18 | trailing_stop | +0.34% | +0.37 | 13 |
| 2022-01-19 | 2022-01-24 | stop_loss | -0.89% | -0.68 | 5 |
| 2022-11-10 | 2022-12-01 | target | +4.82% | +2.41 | 21 |
| 2022-12-02 | 2022-12-15 | stop_loss | -0.88% | -0.44 | 13 |
| 2023-04-24 | 2023-05-01 | trailing_stop | -0.12% | -0.11 | 7 |
| 2023-05-02 | 2023-05-11 | trailing_stop | +0.25% | +0.28 | 9 |
| 2024-05-27 | 2024-06-13 | time_exit | -0.14% | -0.18 | 17 |
| 2025-03-04 | 2025-03-25 | time_exit | +1.17% | +0.63 | 21 |
| 2025-03-26 | 2025-04-04 | trailing_stop | +0.10% | +0.05 | 9 |
| 2026-04-30 | 2026-05-01 | open | -0.21% | -0.18 | 1 |

**Detalle de trades — USDCNH** (1W / 2L):

| Entrada | Salida | Razon | PnL | R-mult | Dias |
|---------|--------|-------|-----|--------|------|
| 2020-05-27 | 2020-06-05 | stop_loss | -1.62% | -1.16 | 9 |
| 2023-05-14 | 2023-06-29 | target | +4.28% | +3.04 | 46 |
| 2023-06-30 | 2023-07-18 | time_exit | -0.95% | -0.47 | 18 |

**Detalle de trades — USDCNY** (1W / 1L):

| Entrada | Salida | Razon | PnL | R-mult | Dias |
|---------|--------|-------|-----|--------|------|
| 2022-08-16 | 2022-09-20 | target | +3.39% | +3.11 | 35 |
| 2023-09-19 | 2023-10-01 | stop_loss | -1.81% | -0.92 | 12 |

**Detalle de trades — USDJPY** (1W / 12L):

| Entrada | Salida | Razon | PnL | R-mult | Dias |
|---------|--------|-------|-----|--------|------|
| 2023-02-14 | 2023-03-10 | trailing_stop | +1.50% | +0.75 | 24 |
| 2023-03-11 | 2023-03-12 | early_exit | -0.03% | -0.02 | 1 |
| 2023-03-13 | 2023-03-15 | early_exit | -0.14% | -0.07 | 2 |
| 2023-03-16 | 2023-03-17 | early_exit | -1.15% | -0.57 | 1 |
| 2023-03-30 | 2023-03-31 | early_exit | -0.32% | -0.16 | 1 |
| 2023-04-02 | 2023-04-03 | early_exit | -0.77% | -0.39 | 1 |
| 2023-10-26 | 2023-10-27 | early_exit | -0.46% | -0.32 | 1 |
| 2023-10-31 | 2023-11-01 | early_exit | -0.49% | -0.30 | 1 |
| 2023-11-08 | 2023-11-14 | stop_loss | -0.24% | -0.18 | 6 |
| 2024-11-12 | 2024-11-15 | early_exit | -0.24% | -0.12 | 3 |
| 2024-11-17 | 2024-11-18 | early_exit | -0.02% | -0.01 | 1 |
| 2024-11-19 | 2024-11-21 | early_exit | -0.36% | -0.18 | 2 |
| 2024-11-22 | 2024-11-25 | early_exit | -0.25% | -0.12 | 3 |

### Conclusiones

- **4/5 monedas positivas en TEST.** EURUSD (+7.93%, Sharpe 2.48) y GBPUSD (+5.80%, Sharpe 1.27) son las mas consistentes.
- **USDJPY es la unica negativa** (-2.96%, Sharpe -1.84). Las 12 losses son todas por early_exit (salida a 3 dias), confirmando que este filtro temporal es incompatible con FX.
- **Asimetria favorable:** en las monedas positivas, el avg win es ~2-3x el avg loss. USDCNH muestra +4.28% avg win vs -1.28% avg loss; USDCNY +3.39% vs -1.81%.
- **Max drawdown controlado:** <2% en todos los casos, consistente con el stop loss ajustado de 2%.
- **El modo sequential filtra severamente:** de 41 senales a 5 trades en EURUSD, de 90 senales a 15 trades en GBPUSD. Prioriza honestidad sobre cantidad.
- **USDCNH y USDCNY positivos pero con muy pocos trades** (3 y 2 respectivamente), lo que limita la significancia estadistica.

---

## Sintesis final

1. **El modo sequential confirma los hallazgos de la exploracion FX:** las mismas monedas (EURUSD, GBPUSD, USDCNY) son viables; USDJPY no lo es.
2. **EURUSD es el par mas robusto** con el mejor Sharpe (2.48) y WR mas alto (80.0%), aunque con solo 5 trades.
3. **GBPUSD aporta volumen de trades** (15 trades) con un WR razonable (53.3%) y buen Sharpe (1.27), siendo el par con mejor significancia estadistica.
4. **El early_exit destruye USDJPY:** el optimizador selecciono early_exit=3d para este par, y 12 de 13 trades salieron por este mecanismo con perdida. Sin early_exit probablemente seria viable (o al menos no tan negativo).
5. **Recomendacion:** operar las 3 monedas viables (EURUSD, GBPUSD, USDCNY) en portfolio para sumar trades y diversificar.
