# Autoresearch Phase 1 — Insights

---

## Config general

- **Metodo de optimizacion:** Optuna con TPE (Tree-structured Parzen Estimator), multivariate=True, 20 startup trials random, seed=42
- **Trials:** 50 (1 job secuencial)
- **Universo:** 18 tickers con data desde antes de 2016 (AAPL, AMZN, AVGO, BRK.B, GLD, GOOGL, IWM, JPM, MSFT, NVDA, QLD, QQQ, SLV, SPY, SQQQ, TIL, TLT, TQQQ)
- **Out-of-sample (no usado):** 4 tickers recientes (COIN, HOOD, PLTR, SOFI)
- **Periodo comun:** 2015-05-27 a 2026-04-08
- **Comision:** no modelada
- **Stop loss:** 7% max (fixed_pct) o pattern-based (el menor)
- **Metrica de optimizacion:** score = expectancy_r * sqrt(n_trades) (Opt C)
- **12 parametros optimizados:** atr_length, atr_mult, min_contractions, max_contractions, lookback_bars, tolerance, max_depth_pct, min_total_reduction, compression_threshold, vol_contraction_threshold, volume_ratio_threshold, max_gap_days

---

## Sub-experimento 1: Baseline vs Best Optuna

### Resultado

**Metricas comparativas:**

| Metrica | Baseline (original) | Best Optuna (trial #25) |
|---------|---------------------|-------------------------|
| score (Opt C) | +2.7004 | +4.1320 |
| n_trades | 78 | 26 |
| expectancy_r | +0.3058 | +0.8104 |
| win_rate | 46.2% | 50.0% |
| profit_factor | 1.62 | 3.40 |
| avg_winner_r | 1.7247 | 2.2958 |
| avg_loser_r | -0.9105 | -0.6751 |

**Comparacion de parametros:**

| Parametro | Baseline | Optuna |
|-----------|----------|--------|
| atr_length | 14 | 12 |
| atr_mult | 2.0000 | 3.5000 |
| min_contractions | 2 | 3 |
| max_contractions | 6 | 7 |
| lookback_bars | 126 | 120 |
| tolerance | 0.1000 | 0.0500 |
| max_depth_pct | 0.3500 | 0.3285 |
| min_total_reduction | 0.8000 | 0.8603 |
| compression_threshold | 0.8500 | 0.8875 |
| vol_contraction_threshold | 0.8500 | 0.9263 |
| volume_ratio_threshold | 1.5000 | 1.5183 |
| max_gap_days | 30 | 37 |

**Distribucion de trades por ticker:**

| Ticker | Baseline | Optuna | Diff |
|--------|----------|--------|------|
| AAPL | 6 | 3 | -3 |
| AMZN | 14 | 2 | -12 |
| AVGO | 6 | 3 | -3 |
| BRK.B | 3 | 1 | -2 |
| GLD | 4 | 1 | -3 |
| GOOGL | 10 | 1 | -9 |
| IWM | 2 | 1 | -1 |
| JPM | 6 | 2 | -4 |
| MSFT | 5 | 0 | -5 |
| NVDA | 2 | 1 | -1 |
| QLD | 2 | 1 | -1 |
| QQQ | 2 | 1 | -1 |
| SLV | 4 | 2 | -2 |
| SPY | 4 | 0 | -4 |
| SQQQ | 2 | 0 | -2 |
| TIL | 1 | 1 | 0 |
| TLT | 3 | 5 | +2 |
| TQQQ | 2 | 1 | -1 |
| **Total** | **78** | **26** | **-52** |

### Conclusiones

- Optuna mejora el score de +2.70 a +4.13 (+53%), triplicando el profit factor (1.62 a 3.40) y mejorando la expectancy (0.31 a 0.81).
- El tradeoff es una reduccion dramatica en trades: 78 a 26 (-67%). Optuna produce un detector mucho mas selectivo.
- Los parametros clave que cambian: `atr_mult` sube de 2.0 a 3.5 (filtra mas ruido), `tolerance` baja de 0.10 a 0.05 (mas estricto), `min_contractions` sube de 2 a 3, `vol_contraction_threshold` sube de 0.85 a 0.93.
- La eliminacion de trades se concentra en AMZN (-12), GOOGL (-9), MSFT (-5), SPY (-4) — tickers donde el baseline generaba muchos trades de baja calidad.
- TLT es el unico ticker donde Optuna genera MAS trades (+2), sugiriendo que los patrones VCP en bonos son mas limpios con parametros mas estrictos.

---

## Sub-experimento 2: Top 10 trials

### Resultado

| trial | score | n_trades | expectancy_r | win_rate | profit_factor |
|-------|-------|----------|--------------|----------|---------------|
| 25 | +4.1320 | 26 | +0.8104 | 50.0% | 3.40 |
| 27 | +3.4382 | 29 | +0.6385 | 44.8% | 2.69 |
| 39 | +3.3559 | 12 | +0.9688 | 58.3% | 4.49 |
| 6 | +3.3287 | 43 | +0.5076 | 44.2% | 2.56 |
| 43 | +3.3096 | 8 | +1.3082 | 62.5% | 9.22 |
| 21 | +3.2885 | 17 | +0.7976 | 52.9% | 5.31 |
| 38 | +3.2109 | 41 | +0.5015 | 51.2% | 2.27 |
| 20 | +3.1527 | 16 | +0.7882 | 56.2% | 4.50 |
| 31 | +3.0658 | 30 | +0.5597 | 46.7% | 2.44 |
| 0 | +3.0531 | 16 | +0.7633 | 43.8% | 3.87 |

### Conclusiones

- Los top 10 trials tienen scores entre +3.05 y +4.13, todos superiores al baseline (+2.70).
- Hay una tension visible entre n_trades y expectancy: trial #43 tiene la mejor expectancy (+1.31) pero solo 8 trades; trial #6 tiene 43 trades pero expectancy moderada (+0.51).
- Los trials con mas de 30 trades (6 y 38) mantienen profit factor >2.2, sugiriendo que el edge es real incluso con mas trades.
- 48 de 50 trials tienen score > 0, y todos los trials generaron al menos 1 trade.

---

## Sub-experimento 3: Importancia de parametros (fANOVA)

### Resultado

| Parametro | Importancia |
|-----------|-------------|
| vol_contraction_threshold | 0.2082 |
| max_gap_days | 0.1732 |
| volume_ratio_threshold | 0.1576 |
| min_total_reduction | 0.1442 |
| max_depth_pct | 0.1333 |
| atr_mult | 0.0527 |
| compression_threshold | 0.0484 |
| lookback_bars | 0.0240 |
| min_contractions | 0.0202 |
| atr_length | 0.0146 |
| max_contractions | 0.0120 |
| tolerance | 0.0118 |

### Conclusiones

- **Los 5 parametros mas importantes (sumando 81.6% de la varianza):** vol_contraction_threshold (0.21), max_gap_days (0.17), volume_ratio_threshold (0.16), min_total_reduction (0.14), max_depth_pct (0.13).
- **Los parametros de swing detection (atr_mult, atr_length) son poco importantes** (5.3% y 1.5%). Esto puede ser contraintuitivo pero indica que una vez que el swing detection produce estructura razonable, son los filtros de patron los que determinan la calidad.
- **Los parametros de contraccion (min/max_contractions) y tolerance son los menos importantes** (<2% cada uno), sugiriendo que su rango actual ya cubre bien los valores utiles.
- **El gap grouping (max_gap_days) es sorprendentemente importante** (17.3%), indicando que como se agrupan patrones cercanos impacta significativamente la calidad de las senales.

---

## Sub-experimento 4: Detalle de trades del best trial (#25)

### Resultado

26 trades sobre 18 tickers (periodo completo 2015-2026):

| # | Ticker | Entry | Exit | Razon | Dur (dias) | PnL% | R-mult |
|---|--------|-------|------|-------|------------|------|--------|
| 1 | AAPL | 2016-07-27 | 2016-09-08 | distribution | 43 | +2.50% | +0.39 |
| 2 | AAPL | 2016-09-08 | 2016-09-09 | distribution | 1 | -2.26% | -0.32 |
| 3 | AAPL | 2024-12-20 | 2025-01-13 | stop_loss | 24 | -7.89% | -1.13 |
| 4 | AMZN | 2017-04-04 | 2017-06-09 | distribution | 66 | +7.88% | +1.13 |
| 5 | AMZN | 2017-10-27 | 2017-12-04 | distribution | 38 | +3.00% | +0.43 |
| 6 | AVGO | 2016-06-03 | 2016-06-24 | stop_loss | 21 | -8.51% | -1.22 |
| 7 | AVGO | 2024-12-13 | 2025-01-27 | stop_loss | 45 | -10.08% | -1.44 |
| 8 | AVGO | 2025-01-27 | 2025-01-28 | distribution | 1 | +2.59% | +0.37 |
| 9 | BRK.B | 2017-09-05 | 2018-02-05 | distribution | 153 | +11.20% | +1.92 |
| 10 | GLD | 2025-08-29 | 2026-01-30 | trailing_stop | 154 | +39.89% | +7.41 |
| 11 | GOOGL | 2019-04-29 | 2019-04-30 | stop_loss | 1 | -7.50% | -1.07 |
| 12 | IWM | 2020-10-08 | 2021-02-25 | distribution | 140 | +35.06% | +5.01 |
| 13 | JPM | 2020-11-09 | 2020-12-18 | distribution | 39 | +1.86% | +0.27 |
| 14 | JPM | 2020-12-18 | 2021-06-14 | distribution | 178 | +32.32% | +4.62 |
| 15 | NVDA | 2024-01-08 | 2024-04-19 | trailing_stop | 102 | +45.83% | +6.55 |
| 16 | QLD | 2017-10-27 | 2017-11-29 | distribution | 33 | +3.37% | +0.54 |
| 17 | QQQ | 2017-10-27 | 2017-11-29 | distribution | 33 | +1.73% | +0.53 |
| 18 | SLV | 2023-07-26 | 2023-08-07 | stop_loss | 12 | -7.42% | -1.06 |
| 19 | SLV | 2025-03-13 | 2025-04-03 | distribution | 21 | -6.02% | -0.86 |
| 20 | TIL | 2016-11-15 | 2017-01-23 | distribution | 69 | -3.77% | -0.54 |
| 21 | TLT | 2016-06-27 | 2016-08-26 | distribution | 60 | -0.58% | -0.11 |
| 22 | TLT | 2016-08-26 | 2016-09-08 | distribution | 13 | -0.41% | -0.09 |
| 23 | TLT | 2017-06-02 | 2017-10-20 | distribution | 140 | -1.31% | -0.29 |
| 24 | TLT | 2020-01-30 | 2020-03-18 | trailing_stop | 48 | -0.16% | -0.02 |
| 25 | TLT | 2025-09-05 | 2026-01-20 | distribution | 137 | -2.16% | -0.62 |
| 26 | TQQQ | 2017-10-27 | 2017-11-29 | distribution | 33 | +4.78% | +0.68 |

### Conclusiones

- Los trades ganadores grandes dominan el resultado: GLD +39.89% (7.41R), NVDA +45.83% (6.55R), IWM +35.06% (5.01R), JPM +32.32% (4.62R).
- Los perdedores estan acotados: el peor es AVGO -10.08% (-1.44R). El stop loss de 7% limita efectivamente las perdidas (algunos exceden el 7% por gap).
- TLT genera 5 trades pero todos negativos o flat — los bonos no se prestan bien al patron VCP.
- La "distribution" como razon de salida domina (16/26 trades), indicando que la mayoria de las posiciones se cierran cuando el patron se distribuye, no por stop o trailing.
- Duracion media: trades ganadores tienden a ser mas largos (33-178 dias) que perdedores (1-45 dias).

---

## Sintesis final

1. **Optuna mejora significativamente el detector VCP:** score +53%, profit factor 2.1x, expectancy 2.7x vs baseline. El tradeoff es -67% trades (78 a 26).
2. **Los parametros mas influyentes son los filtros de patron** (vol_contraction_threshold, max_gap_days, volume_ratio_threshold, min_total_reduction, max_depth_pct), no los parametros de swing detection.
3. **La config Optuna es mucho mas selectiva:** descarta la mayoria de trades de AMZN, GOOGL y MSFT que en el baseline tenian baja calidad, y preserva los trades de alta calidad en IWM, JPM, NVDA, GLD.
4. **Limitaciones importantes:**
   - **In-sample only:** se optimiza y evalua sobre el mismo periodo. No hay validacion out-of-sample.
   - **50 trials insuficientes:** con 12 parametros, TPE necesita ~200-500 trials para convergir bien.
   - **Solo method=tolerance:** no se exploraron `robust_trend` ni otros metodos de compresion.
   - **Gap grouping no explorado:** el max_gap_days es importante (17.3% fANOVA) pero solo se exploro un rango.
5. **Proximos pasos recomendados:**
   - Walk-forward validation para verificar si los parametros generalizan a periodos futuros.
   - Out-of-sample test sobre los 4 tickers excluidos (COIN, HOOD, PLTR, SOFI).
   - Escalar a 200+ trials para explorar mejor el espacio.
   - Multi-objective: optimizar expectancy y n_trades como objetivos separados (Pareto front).
