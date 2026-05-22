# Sistema de Simulacion de Trades

El modulo `vcp_detection/analysis.py` convierte senales VCP en trades simulados, calculando P&L, R-multiples y metricas de rendimiento. Es el componente central para evaluar la calidad de las senales detectadas.

---

## 1. Agrupacion de senales

Un patron VCP puede generar multiples senales en dias consecutivos (el precio cierra por encima del pivote durante varios dias). Antes de simular, las senales se agrupan para evitar entrar multiples veces al mismo patron.

### Modo "gap" (default)

Agrupa senales cuya distancia temporal es <= `max_gap_days`:

```
Senal 1 (2024-01-08) --[3 dias]--> Senal 2 (2024-01-11) --[2 dias]--> Senal 3 (2024-01-13)
                           |                                   |
                           \___________________________________/
                                    1 grupo (gap <= 30 dias)
```

- Si el gap entre dos senales consecutivas supera `max_gap_days`, se inicia un grupo nuevo.
- Cada grupo produce un unico trade, usando la primera senal del grupo como entry.
- `max_gap_days` tipico: 20-40 dias.

### Modo "sequential"

Un trade a la vez, sin solapamiento:

```
Senal 1 -> trade 1 -> exit -> busca siguiente senal posterior a exit_date -> trade 2 -> ...
```

- Se toma la primera senal, se simula el trade hasta su salida.
- Se descarta cualquier senal que ocurra antes de `exit_date`.
- Se busca la siguiente senal despues de la salida y se repite.
- Refleja una operativa real donde no se mantienen posiciones simultaneas.

### Interfaz

```python
evaluate_signals_to_trades(
    signals: dict[pd.Timestamp, VCPSignal],
    ohlc: pd.DataFrame,
    risk_params: dict,
    grouping: str = "gap",       # "gap" o "sequential"
    max_gap_days: int = 30,      # solo para grouping="gap"
) -> list[tuple[dict, dict]]     # lista de (pattern_dict, trade_dict)
```

---

## 2. Entry (entrada al trade)

La entrada se define a partir de la primera senal del grupo:

| Campo | Valor | Descripcion |
|-------|-------|-------------|
| `entry_price` | `first_signal.entry_price` | Close del dia de breakout |
| `stop_pattern` | `first_signal.suggested_stop` | Low de la ultima contraccion |
| `stop_pct` | `entry * (1 - max_stop_loss_pct)` | Stop calculado como % fijo del entry |
| `effective_stop` | `max(stop_pattern, stop_pct)` | El mas alto (mas conservador) de ambos |
| `stop_method` | "pattern" o "fixed_pct" | Cual de los dos stops se activo |
| `initial_risk` | `entry_price - effective_stop` | Riesgo en unidades de precio (denominador del R-multiple) |

**Logica**: Si el stop del patron esta demasiado lejos (ej: 15% debajo del entry), se usa el stop fijo (ej: 7%) para limitar el riesgo. Esto es controlado por `max_stop_loss_pct` (0.07 para stocks, 0.02 para FX).

---

## 3. Mecanismos de salida

Los mecanismos se evaluan en orden de prioridad dentro de cada barra. La primera condicion que se cumple termina el trade.

| # | Mecanismo | Parametros | Condicion | exit_reason |
|---|-----------|------------|-----------|-------------|
| 1 | **Breakeven escalator** | `breakeven_r_multiple` | `r_mult >= N * step` -> sube stop a `entry + (N-1) * step * initial_risk` | (no genera exit, solo sube stop) |
| 2 | **ATR trailing stop** | `trailing_atr_multiplier`, `trailing_atr_period` | `highest_close - mult * ATR > stop` -> sube stop | (no genera exit, solo sube stop) |
| 3 | **Target R-multiple** | `target_r_multiple` | `r_mult >= target_r_multiple` | `"target"` |
| 4 | **Early exit** | `early_exit_days` | `close < entry_price` y `dias_en_trade <= early_exit_days` | `"early_exit"` |
| 5 | **Stop loss / Trailing** | `effective_stop` | `close <= stop` | `"stop_loss"` o `"trailing_stop"` |
| 6 | **SMA distribution** | `trailing_sma_period`, `trailing_volume_factor` | `close < SMA(period)` y `volume > avg_vol * factor` | `"distribution"` |
| 7 | **Time exit** | `max_bars_without_progress`, `min_progress_r` | Sin progreso de `min_progress_r` R por `max_bars_without_progress` barras | `"time_exit"` |
| 8 | **Max hold** | `max_hold_days=252` | Se agotan las barras de simulacion | `"open"` |

### Orden de evaluacion en el codigo

```python
for loc in range(entry_loc + 1, end_loc + 1):
    # 1. Breakeven escalator -> actualiza stop
    # 2. ATR trailing stop   -> actualiza stop
    # 3. Target R-multiple   -> return si se alcanza
    # 4. Early exit          -> return si close < entry dentro de early_exit_days
    # 5. Stop loss           -> return si close <= stop
    # 6. SMA distribution    -> return si close < SMA y volumen alto
    # 7. Time exit           -> return si sin progreso
```

---

## 4. Trailing Stop ATR

Cuando `trailing_stop_method = "atr"`, se usa un trailing stop basado en ATR:

```
atr_trail = highest_close - trailing_atr_multiplier * ATR(trailing_atr_period)
```

Donde:
- `highest_close` es el close mas alto alcanzado desde la entrada.
- `ATR` se calcula con Wilder's RMA (`compute_atr` de `atr_compression.py`).
- `trailing_atr_multiplier`: tipicamente 1.5 a 4.0 (default 3.0).
- `trailing_atr_period`: tipicamente 10 a 21 (default 14).

El trailing stop solo sube, nunca baja:

```python
if atr_trail > stop:
    stop = atr_trail
```

---

## 5. Breakeven Escalator

Funcion escalonada basada en `breakeven_r_multiple` (default 2.0):

```python
steps_completed = int(r_mult / step)     # step = breakeven_r_multiple
if steps_completed >= 1:
    new_stop = entry_price + (steps_completed - 1) * step * initial_risk
    if new_stop > stop:
        stop = new_stop
```

**Ejemplo con step=2.0 y initial_risk=5.0:**

| R-multiple alcanzado | Steps completados | Stop sube a | Descripcion |
|---------------------|-------------------|-------------|-------------|
| 0.0 - 1.99 | 0 | original | Sin cambio |
| 2.0 - 3.99 | 1 | entry + 0 = entry | Breakeven |
| 4.0 - 5.99 | 2 | entry + 2R | Lock in 2R |
| 6.0 - 7.99 | 3 | entry + 4R | Lock in 4R |

El escalator interactua con el ATR trailing: el stop final es siempre el `max()` entre ambos mecanismos.

---

## 6. SMA Distribution Check

Detecta distribucion institucional (venta masiva con volumen alto):

```python
if close < SMA(trailing_sma_period):
    if volume > avg_volume(trailing_sma_period) * trailing_volume_factor:
        return "distribution"
```

- Solo se activa cuando `trailing_stop_method = "sma"`.
- `trailing_sma_period`: default 20 (1 mes de trading).
- `trailing_volume_factor`: default 1.5 (50% mas que el promedio).

---

## 7. Time Exit

Salida por falta de progreso:

```python
if max_bars_without_progress is not None:
    if r_mult > best_r_at_check + min_progress_r:
        best_r_at_check = r_mult
        last_progress_loc = loc
    if loc - last_progress_loc >= max_bars_without_progress:
        return "time_exit"
```

- `max_bars_without_progress`: None (desactivado), 15, 20, 30 o 40 barras.
- `min_progress_r`: 0.25-1.0 R (default 0.5). El trade debe avanzar al menos este monto para resetear el contador.

---

## 8. Metricas de evaluacion

### Metricas por trade

| Metrica | Calculo | Descripcion |
|---------|---------|-------------|
| `pnl_pct` | `(exit_price - entry_price) / entry_price` | Retorno porcentual |
| `r_multiple` | `(exit_price - entry_price) / initial_risk` | Retorno normalizado por riesgo |
| `max_r` | Maximo `r_multiple` alcanzado durante el trade | Maximo favorable excursion (en R) |
| `duration_days` | `(exit_date - entry_date).days` | Duracion en dias calendario |

### Metricas agregadas (compute_aggregate_metrics)

| Metrica | Calculo | Significado |
|---------|---------|-------------|
| `n_trades` | Cantidad total de trades | Tamano de muestra |
| `expectancy_r` | `mean(r_multiples)` | Ganancia promedio por unidad de riesgo |
| `win_rate` | `n_winners / n_trades` | Proporcion de trades ganadores (R > 0) |
| `profit_factor` | `sum(winners) / abs(sum(losers))` | Ratio beneficio/perdida brutos |
| `avg_winner_r` | `mean(winners)` | R-multiple promedio de ganadores |
| `avg_loser_r` | `mean(losers)` | R-multiple promedio de perdedores |
| `max_r` | `max(r_multiples)` | Mejor trade |
| `min_r` | `min(r_multiples)` | Peor trade |
| `trades_per_ticker` | Dict {ticker: count} | Distribucion de trades por activo |

### Score objetivo (compute_objective_score)

Formula usada por Optuna para maximizar:

```
score = expectancy_r * penalty * sqrt(n_trades)
penalty = sqrt(min(n_trades / N_MIN_TRADES, 1.0))
```

Donde `N_MIN_TRADES = 10`. Esta formula:
- Premia expectancy positiva.
- Penaliza suavemente cuando hay pocos trades (penalty < 1 si n_trades < 10).
- Escala con `sqrt(n_trades)` para preferir estrategias con mas senales (mas robustas estadisticamente).
- Retorna -1.0 si n_trades = 0.

---

## 9. Ubicaciones clave en el codigo

| Componente | Archivo | Funcion/Clase |
|------------|---------|---------------|
| Agrupacion gap | `vcp_detection/analysis.py` | `group_signals_into_patterns()` |
| Agrupacion sequential | `vcp_detection/analysis.py` | `evaluate_signals_to_trades(grouping="sequential")` |
| Simulacion de trade | `vcp_detection/analysis.py` | `simulate_trade()` |
| Entry point | `vcp_detection/analysis.py` | `evaluate_signals_to_trades()` |
| Metricas agregadas | `autoresearch/backtest.py` | `compute_aggregate_metrics()` |
| Score objetivo | `autoresearch/backtest.py` | `compute_objective_score()` |
| Trades a DataFrame | `autoresearch/results.py` | `trades_to_dataframe()` |
| Grafico de patron | `vcp_detection/analysis.py` | `plot_vcp_pattern()` |
| Grafico de trade | `vcp_detection/analysis.py` | `plot_trade_simulation()` |

---

## 10. Parametros de riesgo completos (risk_params)

| Parametro | Tipo | Default | Descripcion |
|-----------|------|---------|-------------|
| `max_stop_loss_pct` | float | 0.07 | Stop loss maximo como % del precio de entrada |
| `breakeven_r_multiple` | float | 2.0 | Escalones de breakeven en multiplos de R |
| `trailing_sma_period` | int | 20 | Periodo SMA para trailing y distribution check |
| `trailing_volume_factor` | float | 1.5 | Factor de volumen para senal de distribucion |
| `trailing_stop_method` | str | "sma" | "sma" o "atr" |
| `trailing_atr_period` | int | 14 | Periodo ATR para trailing stop ATR |
| `trailing_atr_multiplier` | float | 3.0 | Multiplo ATR para trailing stop |
| `max_bars_without_progress` | int/None | None | Barras sin progreso antes de time_exit |
| `min_progress_r` | float | 0.5 | Progreso minimo en R para resetear contador |
| `target_r_multiple` | float/None | None | Target de ganancia en R (exit si se alcanza) |
| `early_exit_days` | int/None | None | Dias iniciales para early exit si close < entry |
