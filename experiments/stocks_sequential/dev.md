# Experimento `stocks_sequential` — Spec

> Fecha: 2025-05
> Autor: Gaston de la Rosa
> Relacionados: `run_stocks_sequential.py`, `experiments/stocks_exploration/`, `experiments/fx_sequential/`

---

## Universo y datos
- **Activos**: AAPL, AMZN, AVGO, GOOGL, MSFT, NVDA, JPM, BRK.B (8 stocks)
- **Fuente**: CSVs en `data/csv/`
- **Periodo**: 2015 - 2026
- **Split**: TRAIN < 2020-01-01 / TEST >= 2020-01-01
- **Evaluacion**: TRAIN, TEST, FULL

## Objetivo
Evaluar el detector VCP en stocks con agrupamiento secuencial (un trade a la vez, sin solapamiento). Extiende `stocks_exploration` incorporando `lookback_bars`, `volume_threshold` y `trend_template` como variables de la grilla en Fase 1, ademas del modo secuencial de `fx_sequential`. Es el experimento mas completo para stocks: grilla de 6 dimensiones en deteccion.

## Sub-experimento 1: Sequential stocks
**Script/Notebook**: `run_stocks_sequential.py`

### Grilla de parametros

**Fase 1 — Deteccion (sobre TRAIN)**:
Se fijan los parametros de riesgo y se barre la grilla de deteccion con 6 dimensiones. Se evalua el Trend Template como variable (True/False) y el volume_threshold como variable (None/disabled, 1.0, 1.5, 2.0). Se selecciona la config con mejor CR.

**Fase 2 — Salida (sobre TRAIN)**:
Se fijan los mejores parametros de deteccion de Fase 1 y se barre la grilla de salida. Se selecciona la config con mejor CR.

### Configs — Fase 1: Deteccion
| Parametro | Valores | Total |
|---|---|---|
| atr_mult | 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0 | 7 |
| depth_atr | 2, 3, 4, 5, 6 | 5 |
| reduction (min_total_reduction) | 0.40, 0.50, 0.60, 0.70, 0.80 | 5 |
| lookback_bars | 63, 84, 105, 126 | 4 |
| volume_threshold | None, 1.0, 1.5, 2.0 | 4 |
| trend_template | False, True | 2 |
| **Total Fase 1** | | **5600** |

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
| tolerance | 0.10 |
| max_depth_pct | 0.35 (Minervini: 35% max) |
| max_gap_between_contractions_days | None |
| require_ascending_lows | True |
| ascending_lows_tolerance | 0.01 |
| compression method | ratio |
| compression atr_period | 14 |
| compression ratio_threshold | 0.85 |
| breakout volume_method | ratio |
| breakout volume_lookback_days | 50 |

### Parametros fijos — Riesgo (Fase 1)
| Parametro | Valor |
|---|---|
| max_stop_loss_pct | 0.07 |
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
- Cumulative Return (CR) — metrica principal para seleccion
- Win Rate (WR)
- Avg R-multiple
- N trades, N wins, N losses
- Strategy Sharpe, Strategy Max Drawdown
- Buy & Hold Return, Buy & Hold Sharpe, Buy & Hold Max Drawdown
- Agrupamiento: **sequential** (`evaluate_signals_to_trades` con `grouping="sequential"`)

## Notas de implementacion
- Grilla de deteccion de 6 dimensiones = 5600 configs por stock. Es el experimento con mayor espacio de busqueda por activo.
- `volume_threshold=None` desactiva la confirmacion de volumen en breakout (`require_volume_confirmation=False`). Cuando se especifica (1.0, 1.5, 2.0), activa confirmacion con ese threshold.
- `trend_template=True` filtra senales que no cumplan las 7 condiciones de Etapa 2 de Minervini. Se pre-computa una sola vez por ticker usando `evaluate_trend_template`.
- Usa `evaluate_signals_to_trades(..., grouping="sequential")` para agrupamiento secuencial.
- El script reporta impacto marginal de `trend_template` y `volume_threshold` sobre el pool de configs.
- Resultados trackeados en MLflow experiment `VCP_Stocks_TemporalStability` bajo run `sequential_stocks`.
- Parametros adaptados a stocks vs FX: atr_mult mas altos (1.0-4.0), stop loss 7%, max_depth_pct=0.35, ascending_lows_tolerance=0.01.
