# Deep Per-Ticker VCP Optimization v2

## Objetivo

Optimizar la deteccion de patrones VCP (Volatility Contraction Pattern) por activo individual,
con mejoras respecto a v1 en robustez de seleccion y cobertura de parametros.

## Diferencias vs v1 (`stocks_deep_per_ticker/`)

| Aspecto | v1 | v2 |
|---|---|---|
| Script | Uno por ticker (run_deep_aapl.py, run_deep_amzn.py) | Generico (run_deep_generic.py TICKER) |
| Volumen en breakout | Manual post-grilla | Sistematico: 7 variantes como post-filtro |
| Salida fija en Fase 1 | 1 config (trail=1.5, target=3.0) | 3 configs variando trailing (1.5, 2.5, 3.5) |
| Ranking Fase 1 | Solo CR | Promedio de metricas across 3 salidas |
| Seleccion candidatos | Top 1 por CR | Top 10 por CR + Top 10 por WR |
| Fase 2 | Sobre 1 candidato | Sobre ~15-20 candidatos |
| Ranking final | CR | Composite: 50% CR + 30% WR + 20% avg_R |

## Como funciona el experimento

### Datos

- Split temporal: 5 anos train (2015-2019) / resto test (2020-2026)
- Datos diarios OHLCV

### Paso 1: Precomputo

Para cada combinacion de (atr_mult, use_close_only) = 6 combos:
- Detectar swings (zigzag basado en ATR)
- Computar contracciones entre swings
- Computar ATR(14)
- Evaluar Trend Template (Stage 2 de Minervini) sobre todo el periodo de train

Estos caches se reusan en todas las evaluaciones posteriores.

### Paso 2: Fase 1 — Grilla de deteccion

Para cada combinacion de 9 parametros de deteccion (usando caches del paso 1):

1. Correr `run_full_vcp_pipeline()` con `require_volume_confirmation=False` → senales crudas
2. Para cada variante de Trend Template (2: on/off):
   - Filtrar senales por TT si corresponde
3. Para cada variante de volumen en breakout (7: sin filtro + 6 combos):
   - Aplicar `apply_volume_post_filter()` sobre las senales filtradas
4. Para cada config de salida fija (3: tight/medium/loose):
   - Evaluar trades con `evaluate_signals_seq()`
   - Registrar metricas: trades, wins, WR, CR, avg_R

**Pipeline runs:** 17,496 (los costosos)
**Evaluaciones:** 17,496 x 2 TT x 7 vol x 3 exit = 734,832
**Filas unicas de deteccion:** 17,496 x 2 TT x 7 vol = 244,944 (promediando las 3 salidas)

### Paso 3: Promediar metricas

Para cada config de deteccion unica (11 params + vol_filter), promediar CR, WR, avg_R
de las 3 configs de salida. Esto produce un ranking robusto que no depende de una
salida especifica.

### Paso 4: Seleccion multi-criterio

1. Filtrar: minimo 3 trades (promedio across salidas)
2. Top 10 por avg_CR (cumulative return promedio)
3. Top 10 por avg_WR (win rate promedio, desempate por avg_CR)
4. Union y deduplicar → ~15-20 candidatos

### Paso 5: Fase 2 — Grilla de salida

Para cada candidato:
1. Re-ejecutar el pipeline para obtener las senales
2. Aplicar el filtro de volumen correspondiente
3. Evaluar 720 configs de salida completas

### Paso 6: Ranking final

Para cada candidato, tomar su mejor config de salida por CR.
Rankear los candidatos finales con score compuesto:

```
composite = 0.5 * norm(CR) + 0.3 * norm(WR) + 0.2 * norm(avg_R)
```

## Parametros variados

### Fase 1 — Deteccion (11 parametros, 34,992 combos base)

| # | Parametro | Valores | Descripcion |
|---|---|---|---|
| 1 | atr_mult | 2.0, 3.0, 4.0 | Multiplo de ATR para zigzag. Mas alto = menos swings |
| 2 | use_close_only | False, True | High/Low vs solo Close para swings |
| 3 | max_depth_atr | None, 6, 8 | Profundidad maxima por contraccion en ATRs |
| 4 | min_total_reduction | 0.40, 0.60, 0.80 | Ratio ultima/primera contraccion |
| 5 | lookback_bars | 63, 126 | Ventana temporal (~3 o ~6 meses) |
| 6 | compression_threshold | 0.85, 0.90, 0.95 | ATR_end/ATR_start <= umbral |
| 7 | tolerance | 0.10, 0.15, 0.20 | Margen para monotonia decreciente |
| 8 | max_depth_pct | 0.25, 0.30, 0.35 | Profundidad maxima individual (%) |
| 9 | ascending_lows_tolerance | 0.01, 0.03, 0.08 | Margen para lows ascendentes |
| 10 | trend_template | False, True | Filtro Stage 2 de Minervini |
| 11 | volume_contraction | None, ratio<=0.85 | Volumen decrece en formacion |

### Post-filtro de volumen en breakout (7 variantes)

| Variante | Window | Threshold | Descripcion |
|---|---|---|---|
| no_filter | - | - | Sin filtro de volumen |
| w1_t1.2 | 1 dia | 1.2x | Volumen 20% arriba del promedio, dia exacto |
| w1_t1.5 | 1 dia | 1.5x | Volumen 50% arriba, dia exacto |
| w3_t1.2 | 3 dias | 1.2x | Volumen 20% arriba en alguno de ultimos 3 dias |
| w3_t1.5 | 3 dias | 1.5x | Volumen 50% arriba en alguno de ultimos 3 dias |
| w5_t1.2 | 5 dias | 1.2x | Volumen 20% arriba en alguno de ultimos 5 dias |
| w5_t1.5 | 5 dias | 1.5x | Volumen 50% arriba en alguno de ultimos 5 dias |

### Configs de salida fija para evaluacion en Fase 1 (3 perfiles)

| Perfil | trail | target | early | be_R | max_sl |
|---|---|---|---|---|---|
| Tight | 1.5 | None | None | 1.0 | 0.07 |
| Medium | 2.5 | None | None | 1.0 | 0.07 |
| Loose | 3.5 | None | None | 1.0 | 0.07 |

### Fase 2 — Salida (5 parametros, 720 combos)

| # | Parametro | Valores | Descripcion |
|---|---|---|---|
| 1 | trailing_atr_multiplier | 1.0, 1.5, 2.0, 2.5, 3.0 | Trailing stop en multiplos de ATR |
| 2 | target_r_multiple | None, 2.0, 3.0, 5.0 | Take profit en multiplos de riesgo |
| 3 | early_exit_days | None, 3, 5 | Salida temprana si el trade va en contra |
| 4 | breakeven_r_multiple | 0.5, 1.0, 1.5, 2.0 | Ratchet de breakeven |
| 5 | max_stop_loss_pct | 0.03, 0.05, 0.07 | Stop loss maximo (%) |

### Parametros fijos (no se varian)

| Parametro | Valor | Razon |
|---|---|---|
| atr_length | 14 | Estandar |
| min_contractions | 2 | Definicion minima de VCP |
| max_contractions | 6 | Tope razonable |
| volume_lookback_days | 50 | Baseline para promedio de volumen |
| max_bars_without_progress | 15 | Optimizado en estudio AAPL v1 |
| min_progress_r | 0.5 | Optimizado en estudio AAPL v1 |
| trailing_stop_method | "atr" | Mejor metodo encontrado |

## Uso

```bash
# Un ticker
python3 run_deep_generic.py AAPL

# Multiples tickers (secuencial)
python3 run_deep_generic.py AAPL AMZN GOOGL MSFT NVDA

# Con parametros opcionales
python3 run_deep_generic.py AAPL --train-cutoff 2020-01-01 --top-n 10 --min-trades 3
```

## Outputs

Por ticker:
- `results/{ticker}_phase1_detection.csv` — todas las filas de Fase 1 (promedios de 3 salidas)
- `results/{ticker}_phase2_exit.csv` — candidatos x grilla de salida
- Stdout: sensibilidad, top configs, ranking final con detalle de trades
