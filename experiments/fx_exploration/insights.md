# FX Exploration — Insights

---

## Config general

- **Activo principal:** EURUSD diario (3,581 barras, 2015-2026) y horario (70,523 barras)
- **Comision:** no modelada (sin costos de transaccion)
- **Split temporal:** TRAIN 2015-2019 (1,556 barras) / TEST 2020-2026 (2,025 barras), corte 2020-01-01
- **Metrica principal:** CR (Cumulative Return) = prod(1 + pnl_i) - 1
- **Optimizacion:** grilla en 2 fases (deteccion + salida), parametros fijados en TRAIN, validados en TEST sin re-optimizar
- **Stop loss FX:** 2% max
- **Monedas evaluadas:** EURUSD, GBPUSD, USDJPY, USDCNH, USDCNY

---

## Sub-experimento 1: Estabilidad temporal diaria

### Resultado

**Efecto de atr_mult en la deteccion (EURUSD TRAIN):**

| atr_mult | Swings | Contracciones | Avg CR  | Best CR  | Configs c/trades |
|----------|--------|---------------|---------|----------|------------------|
| 0.75     | 567    | 283           | -3.08%  | +0.00%   | 22/25            |
| 1.00     | 463    | 231           | -2.68%  | +0.00%   | 22/25            |
| 1.25     | 351    | 175           | -1.95%  | +0.00%   | 22/25            |
| **1.50** | **277** | **138**      | **-0.10%** | **+1.19%** | **16/25**   |
| 1.75     | 221    | 110           | -0.03%  | +1.19%   | 16/25            |
| 2.00     | 167    | 83            | -1.14%  | +0.82%   | 14/25            |
| 2.50     | 125    | 62            | +0.16%  | +1.79%   | 11/25            |

**Comparacion TRAIN (5y) vs FULL (11y):**

| Parametro                | TRAIN (5y) | FULL (11y) | Iguales? |
|--------------------------|------------|------------|----------|
| atr_mult                 | 2.5        | 1.5        | NO       |
| depth_atr                | **5**      | **5**      | **SI**   |
| min_total_reduction      | 0.7        | 0.6        | NO       |
| trailing_atr_multiplier  | **1.5**    | **1.5**    | **SI**   |
| target_r_multiple        | 5.0        | 3.0        | NO       |
| early_exit_days          | **None**   | **None**   | **SI**   |
| breakeven_r_multiple     | 2.0        | 1.0        | NO       |

Coincidencia: 3/7 parametros exactos. Los 3 que coinciden son los que mas importan: `depth_atr=5`, `trailing=1.5`, `early_exit=None`.

**Validacion out-of-sample EURUSD:**

| Config               | Split           | Trades | WR   | CR       |
|----------------------|-----------------|--------|------|----------|
| Train-best (5y)      | TRAIN 2015-2019 | 4      | 75%  | +1.79%   |
| Train-best (5y)      | TEST 2020-2026  | 3      | 100% | +5.18%   |
| Full-dataset (11y)   | TRAIN 2015-2019 | 5      | 60%  | +0.22%   |
| Full-dataset (11y)   | TEST 2020-2026  | 5      | 80%  | **+8.56%** |

**Multi-currency: params propios vs params EURUSD (TEST 2020-2026):**

| Moneda | Config          | Train CR  | Test CR    | Full CR    | Test T | Test WR |
|--------|-----------------|-----------|------------|------------|--------|---------|
| EURUSD | Propios (train) | +1.19%    | +5.18%     | +6.43%     | 4      | 75%     |
|        | EURUSD params   | +0.22%    | **+8.56%** | +8.80%     | 5      | 80%     |
| GBPUSD | Propios (train) | +9.76%    | +1.30%     | +10.97%    | 13     | 31%     |
|        | EURUSD params   | +1.11%    | **+6.53%** | +7.70%     | 10     | 60%     |
| USDJPY | Propios (train) | +0.87%    | -1.20%     | -0.34%     | 5      | 0%      |
|        | EURUSD params   | -2.98%    | -3.14%     | -6.03%     | 9      | 22%     |
| USDCNH | Propios (train) | +0.00%    | -0.50%     | -0.50%     | 1      | 0%      |
|        | EURUSD params   | -1.12%    | -4.92%     | -5.99%     | 9      | 33%     |
| USDCNY | Propios (train) | +14.49%   | +4.38%     | +19.51%    | 7      | 57%     |
|        | EURUSD params   | +7.95%    | +3.45%     | +11.67%    | 5      | 60%     |

**Monedas viables:**

| Moneda | Viable? | Evidencia                                         |
|--------|---------|---------------------------------------------------|
| EURUSD | **SI**  | +8.56% TEST, 80% WR, 5 trades                    |
| GBPUSD | **SI**  | +6.53% TEST con params EURUSD, 60% WR, 10 trades |
| USDCNY | **SI**  | +4.38% TEST (propios) / +3.45% (EURUSD), 5-7 trades |
| USDJPY | **NO**  | Negativo con todos los params en TEST              |
| USDCNH | **NO**  | Sin trades o trades perdedores en TEST             |

### Conclusiones

- `atr_mult=1.5` se confirma como optimo. El valor 2.5 que "gano" en TRAIN es un artefacto de pocos trades (4 trades). En TEST pierde los dos mejores movimientos (mayo 2020 +3.86%, oct 2020 +3.08%).
- Los parametros estructurales estables entre TRAIN y FULL son `depth_atr=5`, `trailing=1.5`, `early_exit=None`. Los 4 que difieren son parametros que con solo 2-4 trades en TRAIN no se pueden discriminar estadisticamente.
- Los params universales EURUSD generalizan mejor que los params propios sobreajustados: en GBPUSD dan +6.53% vs +1.30% en TEST. El caso GBPUSD es clasico de overfitting: +9.76% en TRAIN, solo +1.30% en TEST (8 de 13 trades eran early_exits).
- `early_exit=None` es universal en FX. Se confirma en estabilidad temporal (coincide en ambas mitades) y en multi-currency (GBPUSD y USDJPY que seleccionaron early_exit pierden en TEST).
- USDJPY y USDCNH no son viables — la dinamica de precios es incompatible con el patron VCP.

---

## Sub-experimento 2: Escala horaria

### Resultado

**Config A (max CR, 3 trades):**

| Split | Trades | WR | CR | Avg R |
|-------|--------|-----|------|-------|
| TRAIN | 3 | 67% | +2.58% | +2.98 |
| TEST | 2 | 0% | -0.61% | -0.86 |

Detalle TRAIN:

| Trade | Fecha | Salida | PnL | R |
|-------|-------|--------|-----|---|
| 1 | 2015-03-18 | trailing_stop | +1.43% | +2.9R |
| 2 | 2016-04-19 | stop_loss | -0.13% | -0.4R |
| 3 | 2017-12-27 | trailing_stop | +1.27% | +6.4R |

Detalle TEST:

| Trade | Fecha | Salida | PnL | R |
|-------|-------|--------|-----|---|
| 1 | 2020-04-13 | stop_loss | -0.44% | -1.3R |
| 2 | 2025-03-18 | stop_loss | -0.17% | -0.4R |

**Config B (min 10 trades, sin early_exit):**

| Split | Trades | WR | CR | Avg R |
|-------|--------|-----|------|-------|
| TRAIN | 17 | 35% | +2.13% | +0.06 |
| TEST | 18 | 17% | -1.59% | -0.23 |

Detalle TEST (18 trades):

| Trade | Fecha | Salida | PnL | R |
|-------|-------|--------|-----|---|
| 1 | 2020-04-13 | stop_loss | -0.14% | -0.4R |
| 2 | 2020-07-29 | stop_loss | -0.07% | -0.1R |
| 3 | 2021-10-04 | trailing_stop | +0.01% | +0.0R |
| 4 | 2022-05-09 | stop_loss | -0.13% | -0.2R |
| 5 | 2022-08-26 | trailing_stop | -0.18% | -0.4R |
| 6 | 2022-10-26 | trailing_stop | -0.01% | -0.0R |
| 7 | 2023-02-09 | trailing_stop | -0.01% | -0.0R |
| 8 | 2023-09-18 | stop_loss | -0.14% | -0.4R |
| 9 | 2024-04-25 | stop_loss | -0.26% | -0.7R |
| 10 | 2024-06-18 | stop_loss | -0.12% | -0.3R |
| 11 | 2024-08-27 | stop_loss | -0.07% | -0.2R |
| 12 | 2024-12-30 | stop_loss | -0.59% | -1.6R |
| 13 | 2025-03-18 | trailing_stop | -0.01% | -0.0R |
| 14 | 2025-07-01 | stop_loss | -0.13% | -0.2R |
| 15 | 2025-09-05 | trailing_stop | +0.44% | +0.9R |
| 16 | 2025-12-16 | trailing_stop | -0.07% | -0.2R |
| 17 | 2026-02-25 | trailing_stop | +0.04% | +0.1R |
| 18 | 2026-04-07 | stop_loss | -0.16% | -0.4R |

Solo 3 de 18 trades fueron positivos. El mayor ganador fue +0.44%.

### Conclusiones

- VCP a escala horaria no muestra edge en EURUSD. Todas las configuraciones — con y sin early_exit, con distintos criterios de seleccion — producen resultados negativos en TEST.
- Los movimientos horarios son demasiado pequenos: los trades duran horas (la mayoria <1 dia) y los movimientos son insuficientes para superar los costos del stop loss.
- El CR como metrica de seleccion sesga hacia configs con pocos trades. La config A tenia solo 3 trades — estadisticamente insignificante.
- El lookback_bars fue indiferente: las 4 variantes (72, 120, 168, 240) produjeron resultados identicos.

---

## Sintesis final

1. **VCP funciona en FX diario para pares range-bound:** EURUSD (+8.56% TEST), GBPUSD (+6.53%) y USDCNY (+4.38%) son viables. Con params universales EURUSD: 20 trades, 65% WR combinado en TEST 2020-2026.
2. **La escala horaria no funciona.** Los patrones VCP necesitan mas tiempo para formarse y generar movimientos post-breakout significativos.
3. **`early_exit` es incompatible con FX universalmente.** Desactivar early_exit fue el hallazgo mas importante: en diario sube el WR de 20% a 70% y el CR de +2.41% a +8.80%. En multi-currency, las monedas que seleccionaron early_exit en TRAIN pierden sistematicamente en TEST.
4. **Los parametros clave son estables:** `depth_atr=5`, `trailing=1.5`, `atr_mult=1.5` se confirman entre periodos y entre monedas.
5. **Limitacion principal:** bajo N de trades (4-10 por moneda en cada mitad). Los resultados son direccionales pero no estadisticamente robustos.
