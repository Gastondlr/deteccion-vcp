# Reporte: VCP adaptado a FX (EURUSD)

## Objetivo

Evaluar si el detector VCP (Volatility Contraction Pattern), originalmente
disenado para acciones, puede adaptarse a mercados de divisas. Se testeo
sobre EURUSD en data diaria (3,581 barras, 2015-2026) y horaria (70,523
barras).

## Diferencias clave FX vs Acciones

| Metrica            | Acciones | FX (EURUSD) | Ratio |
|--------------------|----------|-------------|-------|
| ATR% tipico        | ~2.2%    | ~0.6%       | 3-4x menor |
| Rally tipico       | ~30%     | ~6.5%       | 5x menor |
| Etapa 2 sostenida  | Si       | No          | - |
| Volumen confiable  | Si       | Limitado    | - |

Esto implica que las contracciones en FX son mucho mas chicas en terminos
absolutos, los movimientos post-breakout son menores, y no hay fases de
crecimiento sostenido (no aplica trend template ni volume confirmation).

## Parametros evaluados

### Set base FX (vs Stock de referencia)

| Parametro              | Stock | FX     |
|------------------------|-------|--------|
| max_depth_pct          | 0.35  | 0.10   |
| max_depth_atr          | 7     | 3      |
| min_total_reduction    | 0.80  | 0.60   |
| ascending_lows_tol     | 0.10  | 0.03   |
| max_entry_distance_pct | 0.10  | 0.03   |
| max_stop_loss_pct      | 0.05  | 0.02   |
| breakeven_r_multiple   | 2.0   | 1.0    |
| trailing_atr_mult      | 3.0   | 2.0    |
| target_r_multiple      | None  | 3.0    |
| atr_mult (swing)       | 2.0   | 1.5    |
| trend_template         | Si    | No     |
| volume_confirmation    | Si    | No     |

---

## Fase 1: Exploracion inicial

### Seccion 4: Comparacion Stock vs FX params

| Data    | Params | Senales | Trades | WR  | CR     | Avg R  | Salida principal |
|---------|--------|---------|--------|-----|--------|--------|------------------|
| Diario  | Stock  | 247     | 14     | 21% | +1.13% | +0.04R | early_exit (9/14) |
| Diario  | FX     | 20      | 2      | 50% | +0.85% | +0.20R | early_exit (1/2)  |
| Horario | Stock  | 3173    | 28     | 18% | -1.05% | -0.08R | early_exit (18/28)|
| Horario | FX     | 1119    | 51     | 16% | -0.93% | -0.08R | early_exit (39/51)|

**Observaciones:**
- Diario es rentable con ambos sets de parametros. FX params son mas
  selectivos (20 vs 247 senales) con mejor calidad por trade.
- Horario pierde con ambos sets. El ruido intradiario genera muchos falsos
  patrones.
- `early_exit` domina las salidas en todas las configs — el precio cae
  debajo del entry en los primeros 3 dias/barras con mucha frecuencia.

### Seccion 6: Grilla de salida (target_R x trailing ATR mult)

**Diario** (2 trades base, poco estadisticamente significativo):

| target_R | atr_mult | WR  | CR     |
|----------|----------|-----|--------|
| *        | 1.5      | 50% | +1.59% |
| *        | 2.0      | 50% | +0.85% |
| *        | 2.5      | 50% | +0.85% |

El trailing mas apretado (1.5x ATR) captura mejor la ganancia. El target_R
no tiene efecto (ningun trade alcanzo target).

**Horario** (51 trades base, todo negativo):

| target_R | atr_mult | WR  | CR     |
|----------|----------|-----|--------|
| 2.0      | 2.5      | 18% | -0.36% |
| 3.0      | 2.5      | 18% | -0.62% |
| None     | 2.5      | 18% | -0.95% |

### Seccion 7: Grilla de deteccion (depth x reduction)

**Hallazgo clave:** `depth_pct` no influye en los resultados. Todas las
configs con el mismo `depth_atr` y `reduction` producen resultados
identicos sin importar el `depth_pct` (0.05 a 0.15). En FX, las
contracciones son tan chicas en porcentaje que el filtro de profundidad
porcentual nunca muerde — `depth_atr` es el filtro que realmente importa.

**Diario — mejores configs:**

| depth_atr | reduction | Senales | Trades | WR  | CR     |
|-----------|-----------|---------|--------|-----|--------|
| 5         | 0.60      | 121     | 10     | 20% | +2.41% |
| 5         | 0.70      | 122     | 10     | 20% | +2.13% |
| 5         | 0.50      | 104     | 8      | 12% | +1.42% |
| 3         | 0.60-0.70 | 20-21   | 2      | 50% | +0.85% |

Abrir `depth_atr` a 5 (permitir contracciones mas profundas) detecta 10
trades vs solo 2 del set FX base (depth_atr=3). La reduccion moderada
(0.60) funciona mejor que la estricta (0.50).

**Horario — unica config positiva:**

| depth_atr | reduction | Senales | Trades | WR  | CR     |
|-----------|-----------|---------|--------|-----|--------|
| 2         | 0.70      | 224     | 31     | 23% | +0.68% |
| 2         | 0.60      | 144     | 20     | 20% | +0.27% |

Contracciones chicas (2 ATR) con alta exigencia de reduccion (0.70) es la
unica combinacion rentable en horario.

---

## Fase 2: Configs combinadas (deteccion + salida optimizadas)

Se tomaron las mejores configs de deteccion de la fase 1 y se variaron
los parametros de salida (trailing, target, early_exit, breakeven) para
encontrar la mejor combinacion. **108 combos por config.**

### Config A: Diario (depth_atr=5, reduction=0.60)

**Top 5 configs:**

| Trail | Target | Early exit | BE_R | Trades | WR   | CR      | Salidas |
|-------|--------|------------|------|--------|------|---------|---------|
| 1.5   | 3R     | None       | *    | 10     | 70%  | +8.80%  | 6t/3s/1tgt |
| 1.5   | 2R     | None       | *    | 10     | 70%  | +7.91%  | 5t/3s/2tgt |
| 1.5   | None   | None       | *    | 10     | 70%  | +7.90%  | 7t/3s |
| 1.5   | 5R     | None       | *    | 10     | 70%  | +7.90%  | 7t/3s |
| 2.0   | 3R     | None       | *    | 10     | 70%  | +7.68%  | 5t/3s/1tgt/1time |

**Observaciones:**
- **Desactivar early_exit fue un game changer:** WR sube de 20% a 70%,
  CR de +2.41% a +8.80%.
- Trailing apretado (1.5x ATR) es consistentemente mejor.
- Target a 3R captura un poco mas que sin target (+8.80% vs +7.90%).
- El breakeven_R no impacta (los 3 valores dan lo mismo).
- 7 de 10 trades son ganadores, con un trade de +3.86% (3R) y otro de
  +3.08% (2.2R).

**Desglose de trades (mejor config):**

| Trade | Salida        | PnL    | R mult |
|-------|---------------|--------|--------|
| 1     | trailing_stop | +0.36% | +0.2R  |
| 2     | trailing_stop | +0.82% | +0.6R  |
| 3     | trailing_stop | +0.34% | +0.2R  |
| 4     | stop_loss     | -1.16% | -0.7R  |
| 5     | stop_loss     | -0.13% | -0.2R  |
| 6     | target        | +3.86% | +3.0R  |
| 7     | trailing_stop | +3.08% | +2.2R  |
| 8     | stop_loss     | -0.70% | -0.9R  |
| 9     | trailing_stop | +1.85% | +0.9R  |
| 10    | trailing_stop | +0.25% | +0.1R  |

### Config B: Horario (depth_atr=2, reduction=0.70)

**Top 5 configs:**

| Trail | Target | Early exit | BE_R | Trades | WR   | CR      | Salidas |
|-------|--------|------------|------|--------|------|---------|---------|
| 2.0   | None   | None       | 1.0  | 31     | 42%  | +2.13%  | 12t/12s/7time |
| 2.0   | None   | None       | 1.5  | 31     | 42%  | +2.04%  | 11t/13s/7time |
| 2.0   | None   | None       | 2.0  | 31     | 42%  | +2.04%  | 11t/13s/7time |
| 2.5   | None   | None       | 1.0  | 31     | 42%  | +1.56%  | 10t/12s/9time |
| 3.0   | None   | None       | 1.0  | 31     | 42%  | +1.46%  | 10t/10s/11time |

**Observaciones:**
- Sin early_exit, WR sube de 23% a 42%, CR de +0.68% a +2.13%.
- Sin target (dejar correr con trailing) funciona mejor que con target fijo.
- Trailing a 2x ATR es optimo; mas suelto pierde rendimiento.
- Breakeven rapido (1R) aporta marginalmente.

---

## Hallazgo principal: early_exit es incompatible con FX

| Config  | Con early_exit (3d) | Sin early_exit | Mejora CR |
|---------|-------------------|----------------|-----------|
| Diario  | WR=20%, CR=+1.96% | WR=70%, CR=+8.80% | +6.84pp |
| Horario | WR=23%, CR=+0.54% | WR=42%, CR=+2.13% | +1.59pp |

El `early_exit` cierra un trade si el precio cae debajo del entry en los
primeros N barras. Este mecanismo asume la dinamica de acciones donde una
caida inmediata post-breakout indica fallo del patron. En FX, el ruido es
mayor relativo al movimiento esperado, y el precio naturalmente oscila
cerca del breakout antes de definir direccion.

**Recomendacion: desactivar early_exit para FX.**

---

## Configs finales recomendadas

### FX Diario

```python
sequence_params = {
    "method": "tolerance", "min_contractions": 2, "max_contractions": 6,
    "lookback_bars": 126, "tolerance": 0.10,
    "max_depth_pct": 0.50,    # alto para que no filtre (depth_atr manda)
    "max_depth_atr": 5,
    "min_total_reduction": 0.60,
    "require_ascending_lows": True, "ascending_lows_tolerance": 0.03,
}
risk_params = {
    "max_stop_loss_pct": 0.02,
    "breakeven_r_multiple": 1.0,
    "trailing_stop_method": "atr",
    "trailing_atr_multiplier": 1.5,
    "target_r_multiple": 3.0,
    "early_exit_days": None,       # DESACTIVADO
    "max_bars_without_progress": 15,
}
```

Resultado: 10 trades, 70% WR, +8.80% CR en 11 anios de EURUSD.

### FX Horario

```python
sequence_params = {
    "method": "tolerance", "min_contractions": 2, "max_contractions": 6,
    "lookback_bars": 252, "tolerance": 0.10,
    "max_depth_pct": 0.50,
    "max_depth_atr": 2,
    "min_total_reduction": 0.70,
    "require_ascending_lows": True, "ascending_lows_tolerance": 0.03,
}
risk_params = {
    "max_stop_loss_pct": 0.02,
    "breakeven_r_multiple": 1.0,
    "trailing_stop_method": "atr",
    "trailing_atr_multiplier": 2.0,
    "target_r_multiple": None,     # dejar correr
    "early_exit_days": None,       # DESACTIVADO
    "max_bars_without_progress": 15,
}
```

Resultado: 31 trades, 42% WR, +2.13% CR en 11 anios de EURUSD.

---

## Problemas y limitaciones

1. **Pocos trades en diario:** 10 trades en 11 anios no es estadisticamente
   significativo. Se necesita testear en mas pares (GBPUSD, USDJPY, USDCNH).

2. **`depth_pct` es redundante en FX:** El filtro de profundidad porcentual
   no aporta informacion adicional al filtro ATR. Puede ponerse en un valor
   alto (0.50) para que no filtre.

3. **Riesgo de overfitting:** Con pocos trades, las configs optimas pueden
   estar sobreajustadas a la historia especifica de EURUSD.

4. **Optimizaciones de performance realizadas:**
   - Cache de ATR precalculado (elimino O(n^2) en el pipeline)
   - Busqueda binaria en `_filter_contractions` (searchsorted vs boolean)
   - Cache de swings/contracciones para grillas de parametros
   - Deteccion una vez + simulacion multiple para grillas de riesgo

## Proximos pasos

1. **Expandir a mas pares**: GBPUSD, USDJPY, USDCNH para validar con mas
   trades y verificar que los resultados no son overfitting a EURUSD.
2. **Analizar los trades individualmente** — ver si los patrones detectados
   son visualmente VCPs reales o falsos positivos del detector.
3. **Explorar swing atr_mult** — probar valores distintos a 1.5 para la
   deteccion de swings en FX.
4. **Out-of-sample testing** — dividir la data en train/test para validar
   que las configs no estan sobreajustadas.
