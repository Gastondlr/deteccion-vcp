# Stocks Sequential — Insights

---

## Config general

- **Modo:** sequential (un trade a la vez, sin overlap)
- **Split temporal:** TRAIN 2015-2019 / TEST 2020-2026, sin re-optimizacion en TEST
- **Optimizacion:** 2 fases — Fase 1 (grilla deteccion con salidas fijas, ~700 configs) + Fase 2 (grilla salida con mejor deteccion fija, 240 configs). Total ~940 evaluaciones por ticker vs 168K si fuera grilla conjunta.
- **Comision:** no modelada
- **Stop loss stocks:** 7% max
- **Metrica principal:** CR (Cumulative Return) = prod(1 + pnl_i) - 1
- **Filtros fijos:** Trend Template = No, Volume threshold = None (determinados en stocks_exploration)

---

## Sub-experimento 1: Resultados por ticker

### Resultado

**Tabla comparativa (TEST 2020-2026):**

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

**Mejores configuraciones por ticker:**

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

### Conclusiones

- **6/8 stocks positivos en TEST.** AAPL (+43.51%) y MSFT (+36.57%) lideran con Sharpe alto (1.79 y 1.95 respectivamente).
- **NVDA destaca con Sharpe 7.12** pero solo tiene 2 trades, lo que limita la significancia.
- **AVGO tiene asimetria extrema:** 13.3% WR pero avg win de +15.15% vs avg loss de -1.48%. Solo 2 wins compensan 13 losses.
- **AMZN es el peor** (-10.39%, 8.3% WR) con 11 losses consecutivas de ~1.4% promedio. Es el unico ticker con CR claramente negativo.
- **Trend Template (TT=False) gana en los 8 stocks** — confirma el hallazgo de la exploracion.
- **Volume threshold: None gana en los 8 stocks** — confirma que el filtro de volumen no aporta valor.
- **Max drawdown mas alto que FX** (hasta -9.21% en BRK.B), consistente con la mayor volatilidad de acciones y el stop loss mas amplio (7% vs 2%).
- **Ninguna estrategia supera al B&H en retorno absoluto** — el mercado subio fuertemente 2020-2026. La ventaja es el Sharpe ajustado por tiempo invertido.

---

## Sub-experimento 2: Comparacion FX vs Stocks

### Resultado

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

### Conclusiones

- **Stocks tienen mayor potencial de retorno** (AAPL +43.5% vs EURUSD +7.9%) pero tambien mayor riesgo (max DD hasta -9.2% vs -2.0%).
- **El ratio de activos positivos es similar** (~75-80%) entre FX y stocks.
- **Los Sharpe son comparables** cuando se excluyen outliers (NVDA con 2 trades).
- **El numero de trades promedio es casi identico** (7.6 FX vs 7.5 stocks), lo cual sugiere que VCP es un patron infrecuente en ambos mercados.

---

## Sub-experimento 3: Notas metodologicas

### Resultado

- **Modo sequential:** un trade a la vez, sin overlap. Si hay 86 senales (AAPL) pero la primera entra el dia X y sale el dia Y, las senales entre X e Y se ignoran. Esto produce un CR honesto y representativo.
- **Optimizacion en 2 fases** para evitar el exponencial de la grilla conjunta (700 det x 240 exit = 168K vs 940 total evaluaciones).
- **Sin re-optimizacion en TEST:** los parametros se fijan en TRAIN y se aplican directamente en TEST.
- **Todos los resultados estan registrados en MLflow** con graficos de cada trade, CSVs de detalle, y metricas completas.

### Conclusiones

- El framework de 2 fases reduce dramaticamente el costo computacional (940 vs 168K evaluaciones) con perdida minima de calidad, ya que los parametros de deteccion y salida son relativamente independientes.
- El modo sequential es mas conservador que el modo con overlap, pero produce resultados mas realistas y operables.

---

## Sintesis final

1. **VCP funciona en acciones con modo sequential:** 6/8 stocks positivos en TEST, con AAPL (+43.51%) y MSFT (+36.57%) como lideres.
2. **La asimetria wins/losses es la clave del edge:** avg win >> avg loss en la mayoria de los tickers, especialmente en AVGO (+15.15% vs -1.48%) y NVDA (+26.61% vs -0.04%).
3. **Los filtros de Minervini no aportan:** Trend Template y Volume threshold pierden en los 8 stocks, confirmando que el detector VCP es autosuficiente.
4. **Stocks ofrecen mayor retorno que FX pero con mayor drawdown.** Ambos mercados muestran tasas similares de activos viables (~75-80%).
5. **AMZN y GOOGL son los unicos no viables** en este universo — posiblemente por la naturaleza de sus movimientos de precio o por overfitting del optimizador a patrones de TRAIN que no se repiten en TEST.
6. **Limitacion:** la estrategia no supera al B&H en retorno absoluto en un mercado alcista. El valor esta en el Sharpe ajustado y en la baja exposicion temporal.
