# Experimento `fx_exploration` — Spec

> Fecha: 2025-05
> Autor: Gaston de la Rosa
> Relacionados: `run_fx_temporal_stability.py`, `run_fx_temporal_stability_hourly.py`, `compare_hourly_configs.py`, `compare_hourly_no_early.py`

---

## Universo y datos
- **Activos (diario)**: EURUSD, GBPUSD, USDJPY, USDCNH, USDCNY (5 pares FX)
- **Activos (horario)**: EURUSD, GBPUSD, USDJPY, USDCNH, USDCNY (5 pares FX)
- **Fuente**: CSVs en `data/monedas/` (diario) y `data/monedas_hora/` (horario)
- **Periodo**: 2015 - 2026
- **Split**: TRAIN < 2020-01-01 / TEST >= 2020-01-01
- **Evaluacion**: TRAIN, TEST, FULL

## Objetivo
Evaluar la estabilidad temporal del detector VCP en pares FX. Se optimizan parametros de deteccion y salida en TRAIN (2015-2019) y se valida out-of-sample en TEST (2020-2026). Un segundo sub-experimento explora si el patron VCP es detectable a escala horaria (micro-VCP que se forman en dias y tradean en horas).

## Sub-experimento 1: Estabilidad temporal diaria
**Script/Notebook**: `run_fx_temporal_stability.py`

### Grilla de parametros

**Fase 1 — Deteccion (sobre TRAIN)**:
Se fijan los parametros de riesgo y se barre la grilla de deteccion. Se selecciona la config con mejor CR.

**Fase 2 — Salida (sobre TRAIN)**:
Se fijan los mejores parametros de deteccion de Fase 1 y se barre la grilla de salida. Se selecciona la config con mejor CR.

### Configs — Fase 1: Deteccion
| Parametro | Valores | Total |
|---|---|---|
| atr_mult | 0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 2.5 | 7 |
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
- Cumulative Return (CR) — metrica principal para seleccion de mejor config
- Win Rate (WR)
- Avg R-multiple
- N trades, N wins
- Strategy Sharpe, Strategy Max Drawdown
- Buy & Hold Return, Buy & Hold Sharpe, Buy & Hold Max Drawdown
- Agrupamiento: gap-based (`group_signals_into_patterns`)

---

## Sub-experimento 2: Escala horaria
**Script/Notebook**: `run_fx_temporal_stability_hourly.py` + `compare_hourly_configs.py` + `compare_hourly_no_early.py`

### Grilla de parametros

**Fase 1 — Deteccion (sobre TRAIN)**:
Misma metodologia que Sub-exp 1 pero con parametros adaptados a escala horaria. Agrega `lookback_bars` como variable adicional.

**Fase 2 — Salida (sobre TRAIN)**:
Se fijan los mejores parametros de deteccion de Fase 1 y se barre la grilla de salida con early_exit en barras horarias.

### Configs — Fase 1: Deteccion
| Parametro | Valores | Total |
|---|---|---|
| atr_mult | 0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 2.5 | 7 |
| depth_atr | 1, 2, 3, 4 | 4 |
| reduction (min_total_reduction) | 0.40, 0.50, 0.60, 0.70, 0.80 | 5 |
| lookback_bars | 72, 120, 168, 240 | 4 |
| **Total Fase 1** | | **560** |

### Configs — Fase 2: Salida
| Parametro | Valores | Total |
|---|---|---|
| trailing_atr_multiplier | 1.0, 1.5, 2.0, 2.5, 3.0 | 5 |
| target_r_multiple | None, 1.5, 2.0, 3.0 | 4 |
| early_exit_days (barras) | None, 6, 12 | 3 |
| breakeven_r_multiple | 0.5, 1.0, 1.5, 2.0 | 4 |
| **Total Fase 2** | | **240** |

### Parametros fijos — Deteccion (horario)
| Parametro | Valor |
|---|---|
| atr_length | 14 (14 horas) |
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

### Parametros fijos — Riesgo (horario)
| Parametro | Valor |
|---|---|
| max_stop_loss_pct | 0.01 (1%, menor que diario) |
| trailing_sma_period | 20 |
| trailing_volume_factor | 1.5 |
| trailing_stop_method | atr |
| trailing_atr_period | 14 |
| trailing_atr_multiplier | 1.5 (fijo en Fase 1) |
| target_r_multiple | 2.0 (fijo en Fase 1) |
| early_exit_days | None (fijo en Fase 1) |
| breakeven_r_multiple | 1.0 (fijo en Fase 1) |
| max_bars_without_progress | 48 (2 dias en barras horarias) |
| min_progress_r | 0.5 |
| max_hold_bars | 360 (15 dias) |
| bars_per_day | 24 |
| annualization_factor | sqrt(252 * 24) |

### Metricas
- Cumulative Return (CR)
- Win Rate (WR)
- Avg R-multiple
- N trades
- Strategy Sharpe (annualized con factor horario)
- Strategy Max Drawdown
- Buy & Hold Return, Sharpe, Max Drawdown
- Agrupamiento: gap-based

## Notas de implementacion
- Cada moneda se procesa independientemente; se busca la mejor config por moneda.
- Sub-exp 1 usa `group_signals_into_patterns` (gap grouping). La deteccion tiene `lookback_bars=126` fijo.
- Sub-exp 2 agrega `lookback_bars` como variable en la grilla (72-240 barras = 3-10 dias).
- Sub-exp 2 usa `max_hold_bars=360` (15 dias max por trade) y `early_exit_days` en barras (no dias).
- Los depth_atr del sub-exp 2 son mas pequenos (1-4 vs 2-6) para capturar micro-patrones.
- Los target_r del sub-exp 2 son mas pequenos (1.5-3.0 vs 2.0-5.0) para salidas mas rapidas.
- Resultados trackeados en MLflow experiment `VCP_FX_TemporalStability`.
- Pre-compute de swings y contracciones por `atr_mult` para evitar recalculo.
- Fases 3-5 del script diario: evaluacion comparativa TRAIN/TEST/FULL, detalle de trades TEST, efecto de atr_mult.
