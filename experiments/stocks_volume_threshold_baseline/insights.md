# Experimento: Baseline exploratorio — Volume Threshold en breakout (todos los stocks)

**Fecha:** 5 de mayo de 2026

**Estado:** Eliminado del repo el 18 de mayo de 2026 (commit `e42bba0`). Este documento preserva la configuracion y resultados.

**MLflow experiment:** `VCP_Breakout_Volume_Threshold`

## Objetivo

Primer experimento formal del proyecto. Evaluar el efecto de variar
`volume_ratio_threshold` en el breakout sobre los 23 tickers disponibles,
con todos los demas parametros fijos en valores por defecto.

## Configuracion

### Parametro variado

| Parametro | Valores |
|---|---|
| `volume_ratio_threshold` | 1.0, 1.5, 2.0 |

### Parametros fijos

**Swing detection:**

| Parametro | Valor |
|---|---|
| atr_length | 14 |
| atr_mult | 2.0 |
| use_close_only | False |

**Sequence (contracciones):**

| Parametro | Valor |
|---|---|
| method | tolerance |
| min_contractions | 2 |
| max_contractions | 6 |
| lookback_bars | 126 |
| tolerance | 0.10 |
| max_depth_pct | 0.35 |
| min_total_reduction | 0.80 |
| max_gap_between_contractions_days | None |

**ATR compression:**

| Parametro | Valor |
|---|---|
| method | ratio |
| atr_period | 14 |
| ratio_threshold | 0.85 |

**Volume contraction:**

| Parametro | Valor |
|---|---|
| method | ratio |
| volume_column | volume |
| ratio_threshold | 0.85 |

**Breakout (fijos):**

| Parametro | Valor |
|---|---|
| volume_method | ratio |
| volume_lookback_days | 50 |
| require_volume_confirmation | True |

**Risk / trade simulation:**

| Parametro | Valor |
|---|---|
| max_stop_loss_pct | 0.07 (7%) |
| breakeven_r_multiple | 2.0 |
| trailing_sma_period | 20 |
| trailing_volume_factor | 1.5 |

### Tickers (23)

AAPL, AMZN, AVGO, BRK.B, COIN, GLD, GOOGL, HOOD, IWM, JPM, META, MSFT,
NVDA, PLTR, QLD, QQQ, SLV, SOFI, SPY, SQQQ, TIL, TLT, TQQQ

### Periodo

Todos los datos disponibles por ticker (sin split train/test).

### Agrupacion

Gap grouping (mode por defecto en ese momento). No existia sequential grouping aun.

## Resultados agregados

| Threshold | Patrones | Trades | Avg WR | Avg CR |
|---|---|---|---|---|
| 1.0 (sin filtro) | 127 | 127 | 46% | +20.9% |
| 1.5 | 86 | 86 | 41% | +5.6% |
| 2.0 (estricto) | 38 | 38 | 42% | +2.8% |

## Resultados por ticker

### threshold = 1.0

| Ticker | Patrones | Trades | WR | CR |
|---|---|---|---|---|
| NVDA | 7 | 7 | 86% | +223.6% |
| GOOGL | 11 | 11 | 64% | +82.7% |
| TQQQ | 5 | 5 | 60% | +75.1% |
| AAPL | 7 | 7 | 86% | +71.6% |
| AVGO | 7 | 7 | 71% | +35.6% |
| SOFI | 1 | 1 | 100% | +27.1% |
| MSFT | 6 | 6 | 83% | +26.3% |
| QLD | 6 | 6 | 67% | +20.0% |
| META | 4 | 4 | 75% | +17.0% |
| SPY | 10 | 10 | 50% | +15.9% |
| GLD | 4 | 4 | 50% | +11.8% |
| QQQ | 3 | 3 | 100% | +8.1% |
| PLTR | 0 | 0 | - | - |
| SQQQ | 3 | 3 | 33% | -5.5% |
| SLV | 4 | 4 | 25% | -6.2% |
| TIL | 2 | 2 | 0% | -7.3% |
| TLT | 4 | 4 | 0% | -8.9% |
| AMZN | 17 | 17 | 29% | -12.0% |
| BRK.B | 6 | 6 | 17% | -14.5% |
| HOOD | 2 | 2 | 0% | -18.4% |
| IWM | 7 | 7 | 14% | -19.0% |
| JPM | 8 | 8 | 12% | -30.2% |
| COIN | 3 | 3 | 0% | -34.1% |

### threshold = 1.5

| Ticker | Patrones | Trades | WR | CR |
|---|---|---|---|---|
| NVDA | 2 | 2 | 100% | +98.1% |
| GOOGL | 10 | 10 | 60% | +47.3% |
| AAPL | 6 | 6 | 83% | +26.5% |
| SPY | 4 | 4 | 75% | +18.6% |
| META | 4 | 4 | 75% | +16.6% |
| TQQQ | 2 | 2 | 50% | +11.6% |
| GLD | 4 | 4 | 50% | +8.1% |
| QQQ | 2 | 2 | 100% | +7.1% |
| MSFT | 5 | 5 | 60% | +5.4% |
| SQQQ | 2 | 2 | 50% | +3.7% |
| QLD | 2 | 2 | 50% | +0.2% |
| PLTR | 0 | 0 | - | - |
| SOFI | 1 | 1 | 0% | -0.9% |
| AVGO | 6 | 6 | 67% | -2.5% |
| TIL | 1 | 1 | 0% | -3.8% |
| BRK.B | 3 | 3 | 33% | -4.2% |
| TLT | 3 | 3 | 0% | -8.4% |
| IWM | 2 | 2 | 0% | -8.9% |
| HOOD | 1 | 1 | 0% | -10.2% |
| COIN | 2 | 2 | 0% | -18.2% |
| JPM | 6 | 6 | 17% | -21.3% |
| AMZN | 14 | 14 | 29% | -28.7% |

### threshold = 2.0

| Ticker | Patrones | Trades | WR | CR |
|---|---|---|---|---|
| GOOGL | 3 | 3 | 100% | +49.6% |
| GLD | 2 | 2 | 100% | +37.6% |
| NVDA | 1 | 1 | 100% | +35.8% |
| META | 2 | 2 | 50% | +14.4% |
| AAPL | 3 | 3 | 100% | +10.6% |
| QQQ | 1 | 1 | 100% | +4.3% |
| SQQQ | 2 | 2 | 50% | +3.7% |
| SPY | 1 | 1 | 100% | +0.3% |
| PLTR | 0 | 0 | - | - |
| BRK.B | 0 | 0 | - | - |
| QLD | 0 | 0 | - | - |
| TQQQ | 0 | 0 | - | - |
| SOFI | 1 | 1 | 0% | -0.9% |
| MSFT | 3 | 3 | 33% | -3.0% |
| TLT | 1 | 1 | 0% | -3.0% |
| TIL | 1 | 1 | 0% | -3.8% |
| SLV | 1 | 1 | 0% | -6.0% |
| IWM | 1 | 1 | 0% | -6.9% |
| HOOD | 1 | 1 | 0% | -10.2% |
| COIN | 1 | 1 | 0% | -10.9% |
| AVGO | 3 | 3 | 33% | -12.8% |
| JPM | 3 | 3 | 0% | -18.1% |
| AMZN | 7 | 7 | 29% | -26.8% |

## Conclusiones

1. **threshold=1.0 domina en retorno agregado** (+20.9% avg CR vs +5.6% y +2.8%).
   Filtrar volumen en breakout descarta mas senales buenas que malas.

2. **Tickers consistentemente buenos** (positivos en las 3 configs): AAPL, GOOGL,
   NVDA, META, QQQ, SPY, GLD.

3. **Tickers consistentemente malos** (negativos en las 3 configs): AMZN, JPM,
   COIN, HOOD, TIL, IWM, TLT.

4. **AMZN es problematico** desde el primer experimento: 29% WR constante
   independiente del threshold, muchos trades (17 → 14 → 7), siempre negativo.

5. **Sin split train/test:** todos los resultados son in-sample. No hay forma de
   saber cuanto de esto generaliza.

## Limitaciones

- Solo se vario 1 parametro de 20+ disponibles.
- Sin split temporal (in-sample completo).
- Gap grouping sobreestima n_trades (senales cercanas cuentan como trades separados).
- Sin metricas de riesgo (drawdown, Sharpe, profit factor).
- Algunos tickers con muy pocos trades (SOFI: 1, PLTR: 0) no son estadisticamente significativos.

## Impacto en experimentos posteriores

Este experimento establecio la intuicion inicial de que `volume_threshold=None`
es superior, lo cual fue confirmado sistematicamente en:
- **stocks_exploration** (8 tickers, train/test split): vol_thresh=None gano en 8/8
- **stocks_sequential** (8 tickers, sequential grouping): vol_thresh=None gano en 8/8
