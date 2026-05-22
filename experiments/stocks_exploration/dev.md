# Experimento `stocks_exploration` — Spec

> Fecha: 2025-04/05
> Autor: Gaston de la Rosa
> Relacionados: `run_stocks_temporal_stability.py`, `run_vcp_with_trend_template.ipynb`, `run_vcp_full_filters.ipynb`

---

## Universo y datos
- **Activos (temporal stability)**: AAPL, AMZN, AVGO, GOOGL, MSFT, NVDA, JPM, BRK.B (8 stocks)
- **Activos (trend template / full filters)**: 23 tickers — AAPL, AMZN, AVGO, BRK.B, COIN, GLD, GOOGL, HOOD, IWM, JPM, META, MSFT, NVDA, PLTR, QLD, QQQ, SLV, SOFI, SPY, SQQQ, TIL, TLT, TQQQ
- **Fuente**: CSVs en `data/csv/`
- **Periodo**: 2015 - 2026
- **Split (temporal stability)**: TRAIN < 2020-01-01 / TEST >= 2020-01-01
- **Split (trend template / full filters)**: Sin split temporal (full period)

## Objetivo
Explorar el detector VCP en acciones estadounidenses con tres enfoques: (1) estabilidad temporal con grilla de 2 fases similar a FX, (2) evaluacion del impacto del Trend Template de Minervini como filtro previo, (3) pipeline completo con todos los filtros configurables (trend template, ascending lows, max entry distance, volume contraction, quality filters). Estos sub-experimentos son exploratorios y anteceden a la version sequential.

## Sub-experimento 1: Estabilidad temporal
**Script/Notebook**: `run_stocks_temporal_stability.py`

### Grilla de parametros

**Fase 1 — Deteccion (sobre TRAIN)**:
Se fijan los parametros de riesgo y se barre la grilla de deteccion. Se selecciona la config con mejor CR.

**Fase 2 — Salida (sobre TRAIN)**:
Se fijan los mejores parametros de deteccion de Fase 1 y se barre la grilla de salida. Se selecciona la config con mejor CR.

### Configs — Fase 1: Deteccion
| Parametro | Valores | Total |
|---|---|---|
| atr_mult | 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0 | 7 |
| depth_atr | 2, 3, 4, 5, 6 | 5 |
| reduction (min_total_reduction) | 0.40, 0.50, 0.60, 0.70, 0.80 | 5 |
| **Total Fase 1** | | **175** |

### Configs — Fase 2: Salida
| Parametro | Valores | Total |
|---|---|---|
| trailing_atr_multiplier | 1.0, 1.5, 2.0, 2.5, 3.0 | 5 |
| target_r_multiple | None, 2.0, 3.0, 5.0 | 4 |
| early_exit_days | None, 3, 5 | 3 |
| breakeven_r_multiple | 0.5, 1.0, 1.5, 2.0 | 4 |
| **Total Fase 2** | | **240** |

### Parametros fijos — Deteccion
| Parametro | Valor |
|---|---|
| atr_length | 14 |
| use_close_only | False |
| method | tolerance |
| min_contractions | 2 |
| max_contractions | 6 |
| lookback_bars | 126 |
| tolerance | 0.10 |
| max_depth_pct | 0.35 (Minervini: 35% max) |
| max_gap_between_contractions_days | None |
| require_ascending_lows | True |
| ascending_lows_tolerance | 0.01 |
| compression method | ratio |
| compression atr_period | 14 |
| compression ratio_threshold | 0.85 |
| breakout volume_method | ratio |
| breakout volume_ratio_threshold | 1.5 |
| breakout volume_lookback_days | 50 |
| breakout require_volume_confirmation | **True** (a diferencia de FX) |

### Parametros fijos — Riesgo (Fase 1)
| Parametro | Valor |
|---|---|
| max_stop_loss_pct | 0.07 (7%, mayor que FX) |
| trailing_sma_period | 20 |
| trailing_volume_factor | 1.5 |
| trailing_stop_method | atr |
| trailing_atr_period | 14 |
| trailing_atr_multiplier | 1.5 (fijo en Fase 1) |
| target_r_multiple | 3.0 (fijo en Fase 1) |
| early_exit_days | None (fijo en Fase 1) |
| breakeven_r_multiple | 1.0 (fijo en Fase 1) |
| max_bars_without_progress | 15 |
| min_progress_r | 0.5 |

### Metricas
- Cumulative Return (CR)
- Win Rate (WR), Avg R-multiple
- N trades, N wins
- Strategy Sharpe, Strategy Max Drawdown
- Buy & Hold Return, Sharpe, Max Drawdown
- Agrupamiento: gap-based

---

## Sub-experimento 2: Trend Template
**Script/Notebook**: `run_vcp_with_trend_template.ipynb`

### Grilla de parametros

Grilla de un solo eje: `volume_ratio_threshold`. Para cada valor se corre el pipeline completo sobre los 23 tickers, filtrando senales que no cumplan las 7 condiciones del Trend Template de Minervini (Etapa 2).

### Configs
| Parametro | Valores | Total |
|---|---|---|
| volume_ratio_threshold | 1.0, 1.5, 2.0 | 3 |
| **Total** | 3 configs x 23 tickers | **69 corridas** |

### Parametros fijos
| Parametro | Valor |
|---|---|
| atr_length | 14 |
| atr_mult | 2.0 |
| use_close_only | False |
| method | tolerance |
| min_contractions | 2 |
| max_contractions | 6 |
| lookback_bars | 126 |
| tolerance | 0.10 |
| max_depth_pct | 0.35 |
| min_total_reduction | 0.80 |
| max_gap_between_contractions_days | None |
| compression method | ratio |
| compression ratio_threshold | 0.85 |
| volume_contraction method | ratio |
| volume_contraction ratio_threshold | 0.85 |
| breakout volume_lookback_days | 50 |
| breakout require_volume_confirmation | True |
| trend_template_filter | True |
| max_stop_loss_pct | 0.07 |
| breakeven_r_multiple | 2.0 |
| trailing_sma_period | 20 |
| trailing_volume_factor | 1.5 |

### Metricas
- Cumulative Return (CR)
- Win Rate, Avg R-multiple
- N signals raw vs filtered (por template)
- Worst/Avg trade drawdown
- Asset max drawdown
- In-trade Sharpe ratio
- Agrupamiento: gap-based

---

## Sub-experimento 3: Full Filters
**Script/Notebook**: `run_vcp_full_filters.ipynb`

### Grilla de parametros

Grilla de 2 ejes: `volume_ratio_threshold` x `template_mode`. Se evalua el impacto de cada filtro (trend template, ascending lows, max entry distance, volume contraction, quality filters) de forma combinada.

### Configs
| Parametro | Valores | Total |
|---|---|---|
| volume_ratio_threshold | 0, 1.0, 1.5, 2.0 | 4 |
| template_mode | False, True | 2 |
| **Total** | 8 configs x 23 tickers | **184 corridas** |

### Parametros fijos
| Parametro | Valor |
|---|---|
| atr_length | 14 |
| atr_mult | 2.0 |
| use_close_only | False |
| method | tolerance |
| min_contractions | 2 |
| max_contractions | 6 |
| lookback_bars | 126 |
| tolerance | 0.10 |
| max_depth_pct | 0.35 |
| max_depth_atr | 7 |
| min_total_reduction | 0.80 |
| max_gap_between_contractions_days | None |
| require_ascending_lows | True |
| ascending_lows_tolerance | 0.10 |
| compression method | ratio |
| compression ratio_threshold | 0.85 |
| volume_contraction (USE_VOLUME_CONTRACTION) | True |
| volume_contraction ratio_threshold | 0.85 |
| breakout volume_lookback_days | 50 |
| breakout max_entry_distance_pct | 0.10 |
| max_stop_loss_pct | 0.05 |
| breakeven_r_multiple | 2.0 |
| trailing_stop_method | atr |
| trailing_atr_period | 14 |
| trailing_atr_multiplier | 3.0 |
| trailing_sma_period | 20 |
| trailing_volume_factor | 1.5 |
| max_bars_without_progress | 20 |
| min_progress_r | 0.5 |
| early_exit_days | 3 |

### Metricas
- Cumulative Return (CR)
- Win Rate, Avg R-multiple
- N signals raw vs filtered
- Worst/Avg trade drawdown
- Asset max drawdown
- In-trade Sharpe ratio
- Avg entry distance (pct)
- Agrupamiento: gap-based

## Notas de implementacion
- Sub-exp 1 adapta parametros de FX a stocks: atr_mult mas altos (1.0-4.0), stop loss mas grande (7%), max_depth_pct=0.35 (Minervini), ascending_lows_tolerance=0.01 (mas estricto), volume confirmation habilitada.
- Sub-exp 2 introduce el Trend Template de Minervini (7 condiciones de Etapa 2) como filtro pre-agrupamiento. Senales fuera de etapa alcista se descartan. Resultado: ~41% retencion de senales.
- Sub-exp 3 agrega filtros adicionales: max_entry_distance_pct (rechaza breakouts lejanos del pivot), volume_contraction, max_depth_atr (profundidad relativa a volatilidad), early_exit_days=3. Stop loss mas bajo (5%).
- Resultados trackeados en MLflow: `VCP_Stocks_TemporalStability`, `VCP_TrendTemplate_Drawdown`, `VCP_FullFilters` / `VCP_FullFilters_TrendTemplate`.
- Sub-exps 2 y 3 pre-computan el Trend Template una sola vez por ticker (no depende del threshold).
