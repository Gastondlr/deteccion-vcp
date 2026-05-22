# Experimento `fx_sequential` — Spec

> Fecha: 2025-05
> Autor: Gaston de la Rosa
> Relacionados: `run_fx_sequential_multicurrency.py`, `experiments/fx_exploration/`

---

## Universo y datos
- **Activos**: EURUSD, GBPUSD, USDJPY, USDCNH, USDCNY (5 pares FX). El script default corre 4 pares (sin EURUSD, que fue evaluado previamente en `fx_exploration`). Para la corrida final se incluyeron los 5 via CLI.
- **Fuente**: CSVs en `data/monedas/`
- **Periodo**: 2015 - 2026
- **Split**: TRAIN < 2020-01-01 / TEST >= 2020-01-01
- **Evaluacion**: TRAIN, TEST, FULL

## Objetivo
Evaluar el detector VCP en FX con agrupamiento secuencial (un trade a la vez, sin solapamiento) en lugar de gap-based. Agrega `lookback_bars` como variable de la grilla respecto a `fx_exploration`. La hipotesis es que el modo secuencial refleja mejor una operativa real donde solo se tiene una posicion abierta por activo a la vez, y que un lookback variable puede capturar patrones de distintas duraciones.

## Sub-experimento 1: Sequential multicurrency
**Script/Notebook**: `run_fx_sequential_multicurrency.py`

### Grilla de parametros

**Fase 1 — Deteccion (sobre TRAIN)**:
Se fijan los parametros de riesgo y se barre la grilla de deteccion con `lookback_bars` variable. Se selecciona la config con mejor CR.

**Fase 2 — Salida (sobre TRAIN)**:
Se fijan los mejores parametros de deteccion de Fase 1 y se barre la grilla de salida. Se selecciona la config con mejor CR.

### Configs — Fase 1: Deteccion
| Parametro | Valores | Total |
|---|---|---|
| atr_mult | 0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 2.5 | 7 |
| depth_atr | 2, 3, 4, 5, 6 | 5 |
| reduction (min_total_reduction) | 0.40, 0.50, 0.60, 0.70, 0.80 | 5 |
| lookback_bars | 63, 84, 105, 126 | 4 |
| **Total Fase 1** | | **700** |

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
| max_depth_pct | 0.50 |
| max_gap_between_contractions_days | None |
| require_ascending_lows | True |
| ascending_lows_tolerance | 0.03 |
| compression method | ratio |
| compression atr_period | 14 |
| compression ratio_threshold | 0.85 |
| breakout volume_method | ratio |
| breakout volume_ratio_threshold | 1.5 |
| breakout volume_lookback_days | 50 |
| breakout require_volume_confirmation | False |

### Parametros fijos — Riesgo (Fase 1)
| Parametro | Valor |
|---|---|
| max_stop_loss_pct | 0.02 |
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
- Diferencia clave vs `fx_exploration`: agrupamiento secuencial en vez de gap-based. Usa `evaluate_signals_to_trades(..., grouping="sequential")` en lugar de `group_signals_into_patterns`.
- `lookback_bars` es variable en la grilla: [63, 84, 105, 126] (3-6 meses aprox).
- Cada moneda se optimiza independientemente; se reportan parametros optimos por moneda y moda entre monedas.
- Se genera histograma de PnL por senal en TEST para cada moneda.
- Resultados trackeados en MLflow experiment `VCP_FX_TemporalStability` bajo run `sequential_multicurrency`.
- Fases 3-4: evaluacion comparativa TRAIN/TEST/FULL con MLflow logging, detalle de trades en TEST.
- Se generan tablas de parametros optimos por moneda y comparativa strategy vs buy & hold.
