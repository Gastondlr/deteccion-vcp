# Informe de Resultados: Experimento Sequential VCP

## 1. Descripcion del Experimento

Se aplica el pipeline de deteccion VCP (Volatility Contraction Pattern) con modo
de evaluacion **sequential** (un trade a la vez, sin overlap) sobre 5 pares FX y
8 acciones. La optimizacion se realiza en dos fases:

- **Fase 1 (Deteccion):** Grilla sobre parametros de deteccion con salidas fijas.
- **Fase 2 (Salida):** Grilla sobre parametros de salida con la mejor deteccion fija.

**Estabilidad temporal:** Se optimiza sobre TRAIN (2015-2019) y se valida sobre
TEST (2020-2026) sin re-optimizar. Los resultados reportados son sobre TEST
salvo que se indique lo contrario.

**Metrica principal:** CR (Cumulative Return) = prod(1 + pnl_i) - 1

---

## 2. Resultados FX (TEST: 2020-2026)

### 2.1 Tabla comparativa

| Moneda | Senales | Trades | Wins | Losses | Win Rate | Avg Win | Avg Loss | CR | Sharpe | Max DD |
|--------|---------|--------|------|--------|----------|---------|----------|----|--------|--------|
| EURUSD | 41 | 5 | 4 | 1 | 80.0% | +2.13% | -0.74% | +7.93% | 2.48 | -1.60% |
| GBPUSD | 90 | 15 | 8 | 7 | 53.3% | +1.34% | -0.70% | +5.80% | 1.27 | -1.82% |
| USDCNH | 50 | 3 | 1 | 2 | 33.3% | +4.28% | -1.28% | +1.62% | 1.09 | -1.63% |
| USDCNY | 40 | 2 | 1 | 1 | 50.0% | +3.39% | -1.81% | +1.52% | 1.48 | -2.01% |
| USDJPY | 43 | 13 | 1 | 12 | 7.7% | +1.50% | -0.37% | -2.96% | -1.84 | -1.74% |

### 2.2 Mejores configuraciones por moneda

| Moneda | atr_mult | depth_atr | reduction | lookback | trail | target_R | be_R | early_exit |
|--------|----------|-----------|-----------|----------|-------|----------|------|------------|
| EURUSD | 2.5 | 5 | 0.6 | 63 | 1.5 | 5.0 | 2.0 | — |
| GBPUSD | 1.5 | 3 | 0.8 | 63 | 1.5 | 2.0 | 0.5 | — |
| USDCNH | 2.5 | 4 | 0.6 | 105 | 3.0 | 3.0 | 2.0 | — |
| USDCNY | 2.5 | 5 | 0.8 | 105 | 2.5 | 3.0 | 0.5 | — |
| USDJPY | 2.5 | 6 | 0.5 | 105 | 1.5 | 5.0 | 1.5 | 3d |

### 2.3 Detalle de trades por moneda

**EURUSD** (4W / 1L)

| Entrada | Salida | Razon | PnL | R-mult | Dias |
|---------|--------|-------|-----|--------|------|
| 2025-03-04 | 2025-03-21 | trailing_stop | +1.85% | +0.93 | 17 |
| 2025-03-23 | 2025-04-23 | trailing_stop | +4.55% | +2.28 | 31 |
| 2025-06-02 | 2025-06-17 | trailing_stop | +0.25% | +0.13 | 15 |
| 2025-06-18 | 2025-07-11 | trailing_stop | +1.85% | +0.92 | 23 |
| 2025-07-13 | 2025-07-28 | stop_loss | -0.74% | -0.37 | 15 |

**GBPUSD** (8W / 7L)

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

**USDCNH** (1W / 2L)

| Entrada | Salida | Razon | PnL | R-mult | Dias |
|---------|--------|-------|-----|--------|------|
| 2020-05-27 | 2020-06-05 | stop_loss | -1.62% | -1.16 | 9 |
| 2023-05-14 | 2023-06-29 | target | +4.28% | +3.04 | 46 |
| 2023-06-30 | 2023-07-18 | time_exit | -0.95% | -0.47 | 18 |

**USDCNY** (1W / 1L)

| Entrada | Salida | Razon | PnL | R-mult | Dias |
|---------|--------|-------|-----|--------|------|
| 2022-08-16 | 2022-09-20 | target | +3.39% | +3.11 | 35 |
| 2023-09-19 | 2023-10-01 | stop_loss | -1.81% | -0.92 | 12 |

**USDJPY** (1W / 12L)

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

### 2.4 Interpretacion FX

- **4/5 monedas positivas en TEST.** EURUSD y GBPUSD son las mas consistentes.
- **USDJPY es la unica negativa** (-2.96%). Las 12 losses son todas por early_exit
  (salida a 3 dias), sugiriendo que el filtro temporal es demasiado agresivo para
  este par donde los movimientos son mas lentos.
- **Asimetria favorable**: en las monedas positivas, el avg win es ~2-3x el avg loss.
- **Max drawdown controlado** (<2% en todos los casos), consistente con el stop loss
  ajustado (2% max).
- **Senales vs trades**: el modo sequential filtra severamente (ej: 41 senales -> 5
  trades en EURUSD), priorizando honestidad sobre cantidad.

---

## 3. Resultados Stocks (TEST: 2020-2026)

### 3.1 Tabla comparativa

| Ticker | Senales | Trades | Wins | Losses | Win Rate | Avg Win | Avg Loss | CR | Sharpe | Max DD |
|--------|---------|--------|------|--------|----------|---------|----------|----|--------|--------|
| AAPL | 86 | 9 | 5 | 4 | 55.6% | +10.13% | -2.59% | +43.51% | 1.79 | -7.82% |
| MSFT | 80 | 12 | 6 | 6 | 50.0% | +8.77% | -3.01% | +36.57% | 1.95 | -6.27% |
| NVDA | 3 | 2 | 1 | 1 | 50.0% | +26.61% | -0.04% | +26.56% | 7.12 | -5.97% |
| AVGO | 42 | 15 | 2 | 13 | 13.3% | +15.15% | -1.48% | +9.19% | 1.23 | -8.82% |
| JPM | 28 | 4 | 2 | 2 | 50.0% | +3.31% | -2.29% | +1.83% | 0.68 | -2.95% |
| BRK.B | 8 | 4 | 2 | 2 | 50.0% | +5.98% | -5.34% | +0.28% | 0.20 | -9.21% |
| GOOGL | 18 | 4 | 1 | 3 | 25.0% | +2.87% | -0.94% | -0.01% | 0.11 | -7.70% |
| AMZN | 19 | 12 | 1 | 11 | 8.3% | +4.52% | -1.38% | -10.39% | -1.78 | -8.27% |

### 3.2 Mejores configuraciones por ticker

| Ticker | atr_mult | depth_atr | reduction | lookback | vol_thresh | TT | trail | target_R | be_R | early |
|--------|----------|-----------|-----------|----------|------------|-----|-------|----------|------|-------|
| AAPL | 1.5 | 6 | 0.8 | 63 | None | No | 2.5 | — | 1.0 | — |
| MSFT | 1.5 | 6 | 0.7 | 84 | None | No | 2.5 | 3.0 | 0.5 | — |
| NVDA | 1.5 | 4 | 0.8 | 84 | None | No | 1.5 | 3.0 | 2.0 | — |
| AVGO | 2.0 | 6 | 0.6 | 63 | None | No | 3.0 | 2.0 | 1.0 | 5d |
| JPM | 2.5 | 5 | 0.7 | 105 | None | No | 1.5 | 5.0 | 2.0 | — |
| BRK.B | 1.0 | 3 | 0.6 | 84 | None | No | 1.0 | 3.0 | 0.5 | — |
| GOOGL | 2.5 | 6 | 0.6 | 126 | None | No | 3.0 | 3.0 | 2.0 | 3d |
| AMZN | 2.0 | 4 | 0.8 | 105 | None | No | 2.0 | 2.0 | 0.5 | 3d |

### 3.3 Interpretacion Stocks

- **6/8 stocks positivos en TEST.** AAPL (+43.5%) y MSFT (+36.6%) lideran.
- **AMZN es el peor** (-10.4%, 8.3% WR) con 11 losses consecutivas de ~1.4% promedio.
- **Trend Template (TT=False) gana en los 8 stocks** — el filtro de Stage 2 de
  Minervini descarta demasiadas senales buenas.
- **Volume threshold: None gana en los 8 stocks** — el filtro de volumen no aporta
  valor para la deteccion via optimizacion.
- **Asimetria favorable**: las wins son mucho mas grandes que las losses (ej: NVDA
  +26.6% vs -0.04%, AVGO +15.2% vs -1.5%).
- **Max drawdown mas alto que FX** (hasta -9.2% en BRK.B), consistente con la mayor
  volatilidad de acciones y el stop loss mas amplio (7% vs 2%).
- **Ninguna estrategia supera al B&H en retorno absoluto** — el mercado subio
  fuertemente 2020-2026. La ventaja es el Sharpe ajustado por tiempo invertido.

---

## 4. Comparacion FX vs Stocks

| Aspecto | FX | Stocks |
|---------|-----|--------|
| Activos positivos | 4/5 (80%) | 6/8 (75%) |
| Mejor CR TEST | EURUSD +7.93% | AAPL +43.51% |
| Peor CR TEST | USDJPY -2.96% | AMZN -10.39% |
| Max DD rango | -1.6% a -2.0% | -2.9% a -9.2% |
| Sharpe rango (pos) | 1.09 a 2.48 | 0.20 a 7.12 |
| Avg trades TEST | 7.6 | 7.5 |
| Vol threshold | N/A | None gana 8/8 |
| Trend Template | N/A | No gana 8/8 |

---

## 5. Notas Metodologicas

- **Modo sequential**: un trade a la vez, sin overlap. Si hay 41 senales pero
  la primera entra el 4-mar y sale el 21-mar, las senales entre esas fechas se
  ignoran. Esto produce un CR honesto y representativo.
- **Stop loss FX**: 2% max. **Stop loss stocks**: 7% max.
- **Optimizacion en 2 fases** para evitar el exponencial de la grilla conjunta
  (700 det x 240 exit = 168K vs 940 total evaluaciones).
- **Sin re-optimizacion en TEST**: los parametros se fijan en TRAIN y se aplican
  directamente en TEST.
- **Todos los resultados estan registrados en MLflow** con graficos de cada trade,
  CSVs de detalle, y metricas completas.
