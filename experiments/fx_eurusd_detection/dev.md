# Experimento `fx_eurusd_detection` — Spec

> Fecha: 2026-05-22
> Autor: Gaston de la Rosa
> Relacionados: `experiments/fx_sequential/`, `docs/architecture-detection.md`

---

## Universo y datos
- **Activo**: EURUSD unicamente
- **Fuente**: `data/monedas/EURUSD.csv`
- **Periodo**: 2015 - 2026
- **Split**: TRAIN < 2020-01-01 / TEST >= 2020-01-01

## Objetivo

Ampliar la grilla de deteccion de la Fase 1 para capturar mas senales en EURUSD.
En `fx_sequential`, 3 parametros de deteccion estaban fijos y podrian estar
filtrando patrones validos:

1. **`compression_threshold`** (0.85 fijo) — exige que el ATR se comprima al 85%.
   En FX los movimientos son pequenos y esto puede ser demasiado restrictivo.
2. **`require_ascending_lows`** (True fijo) — descarta patrones donde el ultimo
   low es marginalmente mas bajo que el anterior.
3. **`tolerance`** (0.10 fijo) — tolerancia para que la secuencia sea "decreciente".
   Un valor mayor acepta secuencias aproximadamente decrecientes.

Se evaluan como variables en la grilla manteniendo la misma estructura de 2 fases
y modo sequential.

## Sub-experimento 1: Grilla de deteccion expandida

**Script**: `run_eurusd_detection.py`

### Grilla de parametros — Fase 1: Deteccion

| Parametro | Valores | N |
|---|---|---|
| atr_mult | 0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 2.5 | 7 |
| depth_atr | 2, 3, 4, 5, 6 | 5 |
| min_total_reduction | 0.40, 0.50, 0.60, 0.70, 0.80 | 5 |
| lookback_bars | 63, 84, 105, 126 | 4 |
| compression_threshold | 0.85, 0.90, 0.95, 1.0 (deshabilitado) | 4 |
| require_ascending_lows | True, False | 2 |
| tolerance | 0.10, 0.15, 0.20 | 3 |
| **Total Fase 1** | | **16,800** |

### Grilla de parametros — Fase 2: Salida

Igual que `fx_sequential`:

| Parametro | Valores | N |
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
| max_depth_pct | 0.50 |
| ascending_lows_tolerance | 0.03 |
| require_volume_confirmation | False |

### Parametros fijos — Riesgo (Fase 1)
| Parametro | Valor |
|---|---|
| max_stop_loss_pct | 0.02 |
| trailing_stop_method | atr |
| trailing_atr_period | 14 |
| trailing_atr_multiplier | 1.5 |
| target_r_multiple | 3.0 |
| early_exit_days | None |
| breakeven_r_multiple | 1.0 |
| max_bars_without_progress | 15 |
| min_progress_r | 0.5 |

### Metricas
- CR (Cumulative Return) — metrica principal para seleccion
- N senales, N trades, Win Rate, Avg R-multiple
- Analisis de sensibilidad por cada nuevo parametro (marginal effect)

## Notas de implementacion
- El cache de swings se reutiliza por atr_mult (7 computes totales).
- `compression_threshold=1.0` equivale a deshabilitar el filtro de ATR compression.
- Se agrega analisis de sensibilidad: para cada nuevo parametro, se mide el efecto
  marginal sobre n_senales y CR promedio.
