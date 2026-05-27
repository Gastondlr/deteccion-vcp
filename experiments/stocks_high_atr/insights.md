# Stocks High ATR — Insights

---

## Config general

- **Modo:** sequential (un trade a la vez, sin overlap)
- **Activos:** AAPL, AMZN, GOOGL, MSFT, NVDA
- **Comision:** no modelada
- **Stop loss stocks:** 7% max
- **Metrica principal:** CR (Cumulative Return) = prod(1 + pnl_i) - 1

---

## Experimento 1: Split 70/30 (train hasta nov-2022, test nov-2022 a abr-2026)

### Objetivo

Replicar el analisis de fx_eurusd_high_atr en stocks: probar `max_depth_atr=None` y `atr_mult` alto (2.5-5.0) para ver si deshabilitar el filtro desbloquea patrones rentables.

### Grilla

**Fase 1 — Deteccion (432 configs por ticker):**

| Parametro | Valores |
|-----------|---------|
| atr_mult | 2.5, 3.0, 4.0, 5.0 |
| max_depth_atr | None, 4, 6, 8 |
| reduction | 0.40, 0.60, 0.80 |
| lookback_bars | 63, 84, 126 |
| compression_threshold | 0.85, 0.90, 0.95 |
| tolerance | 0.15 (fijo) |
| require_ascending_lows | False (fijo) |
| max_depth_pct | 0.35 (fijo) |

**Fase 2 — Salida (240 configs):**

| Parametro | Valores |
|-----------|---------|
| trailing_atr_multiplier | 1.0, 1.5, 2.0, 2.5, 3.0 |
| target_r_multiple | None, 2.0, 3.0, 5.0 |
| early_exit_days | None, 3, 5 |
| breakeven_r_multiple | 0.5, 1.0, 1.5, 2.0 |

### Resultado

| Ticker | atr | mda | red | lb | trail | tgt | TRAIN T | TRAIN WR | TRAIN CR | TEST T | TEST WR | TEST CR |
|--------|-----|-----|-----|-----|-------|-----|---------|----------|----------|--------|---------|---------|
| AAPL | 2.5 | None | 0.60 | 126 | 2.0 | 5.0 | 16 | 62% | +90.66% | 9 | 56% | -0.74% |
| AMZN | 3.0 | None | 0.80 | 126 | 1.5 | 5.0 | 37 | 41% | +88.95% | 4 | 0% | -3.89% |
| GOOGL | 2.5 | 6 | 0.80 | 84 | 3.0 | 3.0 | 14 | 57% | +85.40% | 4 | 25% | -15.03% |
| MSFT | 2.5 | None | 0.80 | 126 | 1.5 | 2.0 | 31 | 65% | +78.24% | 4 | 50% | +1.17% |
| NVDA | 3.0 | 8 | 0.80 | 126 | 2.5 | 2.0 | 10 | 60% | +46.26% | 1 | 0% | -6.46% |

### Diagnostico

1. **Overfitting masivo:** TRAIN CR entre +46% y +91%, TEST entre -15% y +1%. Ningun ticker es claramente rentable en TEST.
2. **max_depth_atr=None domina TRAIN** (AAPL, AMZN, MSFT lo seleccionan) pero no se traduce a TEST.
3. **AMZN:** la salida optimizada (early_exit=3d) destruye TEST — 4 trades, todos early_exit perdedores.
4. **GOOGL:** 2 stop_loss de ~7.5% eliminan toda ganancia.
5. **NVDA:** solo 1 trade en TEST, muestra insuficiente.
6. **El split importa:** con cutoff 2020, stocks_sequential tenia AAPL +43.5%, MSFT +36.6% en TEST. Con cutoff nov-2022, colapsan. El periodo 2022-2026 es mas dificil para VCP en stocks.

### Interaccion atr_mult x max_depth_atr (patron comun en los 5 tickers)

- **atr_mult >= 4.0 con max_depth_atr numerico:** 0 senales (mismo bloqueo que en FX/hourly)
- **atr_mult=5.0:** solo funciona con max_depth_atr=None
- **atr_mult=2.5 domina** en 4/5 tickers (NVDA prefiere 3.0)
- El patron es identico al de EURUSD daily: atr_mult alto necesita max_depth_atr=None, pero en daily el filtro esta actuando correctamente como filtro de calidad

---

## Comparacion con stocks_sequential (split 2020, cutoff fijo)

El experimento `stocks_sequential` previo (con grilla diferente y split TRAIN 2015-2019 / TEST 2020-2026) tenia:

| Ticker | stocks_sequential TEST CR | stocks_high_atr TEST CR | Nota |
|--------|---------------------------|-------------------------|------|
| AAPL | +43.51% (9T) | -0.74% (9T) | Split diferente + params diferentes |
| AMZN | -10.39% (12T) | -3.89% (4T) | Ambos negativos |
| GOOGL | -0.01% (4T) | -15.03% (4T) | Ambos pobres |
| MSFT | +36.57% (12T) | +1.17% (4T) | Gran diferencia |
| NVDA | +26.56% (2T) | -6.46% (1T) | Muestras minimas |

Las configs de stocks_sequential que funcionaron bien usaban:
- AAPL: atr_mult=1.5, depth_atr=6, reduction=0.8, lookback=63, trail=2.5, target=None
- MSFT: atr_mult=1.5, depth_atr=6, reduction=0.7, lookback=84, trail=2.5, target=3.0

Ambas con **atr_mult=1.5** (mas bajo que nuestro rango 2.5-5.0) y **depth_atr=6** (que funciona como max_depth_atr=6).

---

## Mapa completo de parametros del pipeline VCP

### Parametros que hemos variado en experimentos

| Parametro | Rango probado | Hallazgo |
|-----------|---------------|----------|
| atr_mult | 0.75 - 5.0 | 1.5-2.5 rango util para stocks; 2.5 para FX |
| max_depth_atr | 2-8, None | None desbloquea senales pero agrega ruido; en daily filtra correctamente |
| reduction (min_total_reduction) | 0.40 - 0.80 | Efecto moderado; 0.6-0.8 tipico |
| lookback_bars | 63 - 126 | Efecto moderado; 63-84 suficiente |
| compression_threshold | 0.85 - 1.0 | Efecto moderado; 0.85-0.90 tipico |
| tolerance | 0.10 - 0.20 | Efecto minimo |
| require_ascending_lows | True/False | Inerte en FX; no testeado aislado en stocks |
| trailing_atr_multiplier | 1.0 - 3.0 | Muy sensible; 1.5-2.5 tipico |
| target_r_multiple | None, 2.0, 3.0, 5.0 | Muy sensible; target alto (5R) funciona cuando hay tendencia |
| breakeven_r_multiple | 0.5 - 2.0 | Efecto menor |
| early_exit_days | None, 3, 5 | Destructivo en FX (USDJPY) y AMZN; util en algunos stocks |
| volume_ratio_threshold (breakout) | None, 1.0, 1.5, 2.0 | None gana en 8/8 stocks (no aporta valor) |
| trend_template | True/False | False gana en 8/8 stocks |

### Parametros NUNCA variados (candidatos para explorar)

#### Alta prioridad — probablemente impactan calidad de deteccion

| Parametro | Valor fijo actual | Que controla | Por que explorarlo |
|-----------|-------------------|--------------|-------------------|
| **min_depth_pct** | 0.0 | Profundidad minima de contraccion | Filtrar micro-contracciones (<2-3%) que son ruido; podria mejorar calidad de patrones drasticamente |
| **min_contractions** | 2 | Minimo de contracciones en secuencia | Exigir 3 contracciones = patrones mas formados, tipico VCP de Minervini |
| **max_depth_pct** | 0.35 (stocks) / 0.50 (FX) | Profundidad maxima de contraccion | Nunca variado; interactua con max_depth_atr; podria ser mas o menos restrictivo |
| **volume_contraction** | None (deshabilitado) | Verificar que el volumen decrece entre contracciones | Componente esencial del VCP de Minervini que nunca activamos; el "dry-up" de volumen es clave en la teoria |
| **max_gap_between_contractions_days** | None (sin limite) | Maximo dias entre contracciones | Filtrar patrones "estirados" temporalmente; un VCP real se forma en semanas, no meses |

#### Media prioridad — podrian aportar mejoras incrementales

| Parametro | Valor fijo actual | Que controla | Por que explorarlo |
|-----------|-------------------|--------------|-------------------|
| **atr_length** | 14 | Periodo del ATR para zigzag | 10 = mas reactivo (swings mas frecuentes), 20 = mas suave (solo swings grandes) |
| **method** (sequence) | "tolerance" | Como se verifica la secuencia decreciente | "robust_trend" usa regresion lineal + R²; podria ser mas robusto que comparar pares |
| **compression method** | "ratio" | Como se verifica compresion de ATR | "ratio_normalized" corrige por nivel de precio; relevante en stocks que suben mucho |
| **max_contractions** | 6 | Maximo contracciones consideradas | Reducir a 4 podria filtrar patrones sobre-extendidos |
| **ascending_lows_tolerance** | 0.01 (stocks) / 0.03 (FX) | Tolerancia para lows ascendentes | Relajar (0.05) o endurecer (0.0) podria cambiar que patrones pasan |
| **deduplicate** | False | Evitar re-senales del mismo patron | Podria reducir churning en modo sequential |

#### Baja prioridad — efecto esperado menor

| Parametro | Valor fijo actual | Que controla | Nota |
|-----------|-------------------|--------------|------|
| use_close_only | False | Usar solo close para swings | Cambio sutil en deteccion |
| trailing_stop_method | "atr" | Metodo de trailing stop | "sma" es la alternativa (Minervini original) |
| max_hold_days | 252 | Maximo dias en trade | Reducirlo forzaria trades mas cortos |
| min_progress_r | 0.5 | Progreso minimo para no salir por tiempo | Interactua con max_bars_without_progress |

---

## Plan para siguiente sesion

### Enfoque: mejorar calidad de deteccion en TRAIN, luego validar en TEST

**Split:** 5 anos TRAIN (2015-2019) / ~6 anos TEST (2020-2026), igual que stocks_sequential.

**Estrategia:** empezar con 1 ticker (AAPL, el mejor historicamente), explorar parametros nuevos uno por uno para entender su efecto, luego escalar a los 5 tickers.

### Parametros a probar (en orden de prioridad)

1. **min_depth_pct** = [0.0, 0.02, 0.03, 0.05]
   - Hipotesis: filtrar contracciones menores a 2-5% elimina ruido sin perder patrones reales
   - Impacto esperado: menos senales, mejor calidad

2. **min_contractions** = [2, 3]
   - Hipotesis: exigir 3 contracciones produce patrones mas maduros y predecibles
   - Impacto esperado: muchas menos senales, pero las que quedan son VCP clasicos

3. **volume_contraction** = habilitado con method="ratio", ratio_threshold=[0.80, 0.90, 0.95]
   - Hipotesis: el dry-up de volumen es señal de que la oferta flotante se absorbe (teoria Minervini)
   - Impacto esperado: filtro adicional que descarta patrones sin confirmacion de volumen

4. **max_gap_between_contractions_days** = [None, 30, 60, 90]
   - Hipotesis: patrones estirados (contracciones separadas por meses) no son VCP genuinos
   - Impacto esperado: filtrar patrones temporalmente dispersos

5. **max_depth_pct** = [0.20, 0.25, 0.30, 0.35, 0.40]
   - Hipotesis: el valor fijo de 0.35 podria no ser optimo para todos los activos
   - Impacto esperado: ajustar al regimen de volatilidad de cada stock

6. **compression method** = ["ratio", "ratio_normalized"]
   - Hipotesis: en stocks que suben mucho (NVDA, AAPL), el ATR absoluto sube con el precio; normalizar corrige esto
   - Impacto esperado: mejor deteccion en stocks con tendencia alcista fuerte

### Metodologia propuesta

Para cada parametro nuevo:
1. Fijar todos los demas parametros en la mejor config conocida (de stocks_sequential para AAPL)
2. Variar solo el parametro en cuestion
3. Medir: numero de senales, trades, WR, CR en TRAIN
4. Si mejora TRAIN sin reducir demasiado la muestra, validar en TEST
5. Una vez identificados los parametros que aportan, combinarlos en una grilla final
