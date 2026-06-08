# Insight v3: Confirmacion de Volumen Forward

**Fecha:** 2026-06-06 (actualizado 2026-06-07 con NVDA y AMZN)
**Experimento:** `stocks_deep_per_ticker_v3`
**Objetivo:** Evaluar si permitir confirmacion de volumen en los N dias posteriores al breakout de precio mejora la robustez de las señales VCP en test (2020-2026).

## Metodologia

- **Train:** 2015-01-01 a 2019-12-31 | **Test:** 2020-01-01 a 2026-04-08
- Grid search completo (17,496 pipeline runs × 7 variantes de volumen por ticker)
- Variantes forward: `w{1,3}_t{1.2,1.5}_f{3,5}` (backward window × threshold × forward days)
- Post-filter: pipeline corre sin volume confirmation, filtro aplicado post-hoc
- Forward: si volumen no confirma backward, busca en N dias siguientes. Si precio se mantiene sobre pivot Y volumen confirma, entra a precio de cierre del dia de confirmacion (sin look-ahead bias)
- Ranking compuesto: 50% CR + 30% WR + 20% avg_R

---

## Resultados por Ticker

### AAPL — Forward es claramente beneficioso

| Config | Train T | Train WR | Train CR | Test T | Test WR | Test CR | Test MaxDD | Test PF |
|--------|---------|----------|----------|--------|---------|---------|------------|---------|
| **FWD#1 w3_t1.2_f5** | 4 | 100% | +36.14% | **6** | **83%** | **+37.38%** | -4.02% | **9.3** |
| FWD#2 w3_t1.2_f3 | 4 | 100% | +36.14% | 6 | 83% | +37.38% | -4.02% | 9.3 |
| FWD#3 w1_t1.2_f5 | 4 | 100% | +34.65% | 6 | 83% | +19.56% | -4.02% | 5.7 |
| Baseline no_filter be=2.0 | 4 | 100% | +41.22% | 6 | 67% | +16.76% | -6.59% | 2.8 |
| Baseline no_filter be=1.0 | 5 | 100% | +46.80% | 6 | 67% | +19.36% | -6.59% | 3.0 |

**Deteccion:** atr=2.0, close=False, mda=6.0, red=0.80, lb=126, comp=0.85, VC=True
**Exit (forward):** tr=3.0, tg=None, be=1.0, sl=3%

**Hallazgos:**
- FWD#1/2 (+37.38%) **duplican** el retorno del mejor baseline (+19.36%) en test
- WR sube de 67% → 83% con forward
- El forward evito el trade toxico del 2025-07-25 (baseline: stop_loss -5.38%) y en cambio entro el 2025-07-31 con confirmacion, capturando +8.88%
- FWD#1 y FWD#2 producen señales identicas — el forward 3 vs 5 dias no importa para AAPL
- FWD#3 (w1) captura las mismas señales pero con entries ligeramente diferentes, menor CR
- **Mejor transicion train→test de todo el proyecto:** CR mejora de train a test (+36%→+37%)

### GOOGL — Forward evita trades toxicos

| Config | Train T | Train WR | Train CR | Test T | Test WR | Test CR | Test MaxDD | Test PF |
|--------|---------|----------|----------|--------|---------|---------|------------|---------|
| FWD COMP#1 w3_t1.2_f3 | 12 | 75% | +77.52% | 4 | 50% | +3.55% | -7.77% | 1.4 |
| FWD COMP#2 w1_t1.2_f3 | 12 | 75% | +73.67% | 3 | 67% | +4.84% | -7.77% | 1.7 |
| **FWD COMP#3 w1_t1.2_f3 VC** | 4 | **100%** | +28.74% | **2** | **100%** | **+14.34%** | **0.00%** | **inf** |
| Baseline no_filter | 16 | 69% | +78.84% | 5 | 40% | **-4.02%** | -14.51% | 0.8 |

**Deteccion:** atr=2.0, close=True, mda=8, red=0.80, lb=126, comp=0.95, VC=N (excepto COMP#3: comp=0.85, VC=ratio 0.85)
**Exit:** tr=2.5, tg=None (COMP#3: tg=3R, sl=5%), be=1.0, sl=7%

**Hallazgos:**
- Baseline es **negativo** en test (-4.02%), todos los forward son positivos
- Forward evito el trade 2026-02-02 (baseline: stop_loss -7.31%) — el volumen no confirmo
- COMP#3 (VC + forward + target=3R) es el mas robusto: 100% WR en train Y test, 0% drawdown
- Trade count bajo en test (2-5) limita significancia estadistica

### NVDA — Forward funciona pero baseline sin filtro tambien es fuerte

| Config | Train T | Train WR | Train CR | Test T | Test WR | Test CR | Test MaxDD | Test PF |
|--------|---------|----------|----------|--------|---------|---------|------------|---------|
| FWD#1 w3_t1.2_f3 | 5 | 60% | +67.96% | 5 | 60% | +82.15% | -6.84% | 10.9 |
| **FWD#2 w1_t1.2_f3** | 5 | 60% | +67.96% | **6** | **67%** | **+142.36%** | -6.84% | **15.7** |
| FWD#3 w3_t1.2_f3 tg=5R | 5 | 60% | +61.55% | 4 | 75% | +89.00% | -2.68% | 27.9 |
| Baseline NF (best NF det) | 3 | 100% | +33.67% | **0** | — | — | — | — |
| **Baseline NF (same det)** | 8 | 38% | +46.60% | **9** | **67%** | **+182.30%** | -5.79% | **14.7** |

**Deteccion (forward):** atr=2.0, close=False, mda=None, red=0.60, lb=63, comp=0.95, VC=False
**Exit (forward):** tr=2.5, tg=None, be=1.5, sl=3%

**Hallazgos:**
- FWD#2 (w1_t1.2_f3) captura un trade extra en test via forward (+33.05% el 2023-05-24 [fwd+2d])
- Pero el **baseline sin filtro con mismos params de deteccion supera a todos** (+182% vs +142%)
- NVDA es tan explosivo (B&H test +2935%) que filtrar trades buenos cuesta mas que evitar malos
- FWD#3 con target=5R tiene el mejor PF (27.9) y menor MaxDD (-2.68%) — mas controlado
- El baseline best NF (atr=3.0, red=0.8) produce 0 trades en test — sobre-ajustado a train

### AMZN — Problema de deteccion, no de forward

| Config | Train T | Train WR | Train CR | Test T | Test WR | Test CR | Test MaxDD | Test PF |
|--------|---------|----------|----------|--------|---------|---------|------------|---------|
| FWD#1 w3_t1.2_f3 VC | 12 | 75% | +111.12% | **0** | — | — | — | — |
| FWD#2 w3_t1.2_f3 tg=3R VC | 14 | 64% | +84.27% | **0** | — | — | — | — |
| Baseline NF (best NF det) | 19 | 63% | +113.58% | 14 | 36% | **-0.12%** | -13.17% | 1.1 |
| Baseline NF (same det as fwd) | 14 | 64% | +93.22% | **0** | — | — | — | — |

**Deteccion (forward):** atr=3.0, close=False, mda=None, red=0.60, lb=126, comp=0.90, VC=True
**Exit (forward):** tr=2.0, tg=None, be=1.5, sl=3%

**Hallazgos:**
- **0 trades en test** para TODA configuracion con los params de deteccion que ganan en train (atr=3.0, VC=True)
- El problema no es el forward sino la deteccion: estos params no producen VCPs en AMZN post-2020
- Unico baseline con trades en test usa params distintos (atr=2.0, close=True, VC=False) y es negativo (-0.12%, 36% WR)
- AMZN cambio de regimen despues de 2020 (COVID crash → recovery → diferente estructura de mercado)
- **Ticker no viable para VCP** con los params actuales del grid

### MSFT — Forward no mejora vs baseline

| Config | Train T | Train WR | Train CR | Test T | Test WR | Test CR | Test MaxDD | Test PF |
|--------|---------|----------|----------|--------|---------|---------|------------|---------|
| FWD#1 w3_t1.2_f3 | 5 | 80% | +19.19% | 4 | 50% | +1.88% | -7.87% | 1.3 |
| FWD#2 w1_t1.2_f3 | 5 | 80% | +17.57% | 3 | 33% | -6.20% | -7.87% | 0.2 |
| **Baseline VC=True tr=1.5** | 8 | 75% | +39.42% | **5** | **60%** | **+4.66%** | -4.67% | **2.0** |
| Baseline VC=False tr=3.0 | 7 | 71% | +29.15% | 6 | 50% | +3.70% | -7.87% | 1.5 |

**Deteccion:** atr=2.0, close=False, mda=None, red=0.60, lb=126, comp=0.85
**Exit (forward):** tr=3.0, tg=None, be=1.5, sl=3%

**Hallazgos:**
- Baseline VC=True con trailing tight (tr=1.5) es el mejor en test
- Forward configs degradan mas que baselines: muy pocos trades en train (5T), aun menos en test (3-4T)
- FWD#2 es negativo en test (-6.20%)
- MSFT requiere mas señales activas para funcionar; el forward sobre-filtra

---

## Conclusiones Cross-Ticker (5 tickers)

### 1. Forward volume es ticker-dependiente
- **AAPL:** Mejora dramatica (+37% vs +19% baseline en test) — forward duplica retorno
- **GOOGL:** Mejora moderada (positivo vs negativo baseline) — forward evita trades toxicos
- **NVDA:** Resultado mixto — forward +142% pero baseline sin filtro +182% (NVDA es tan explosivo que filtrar cuesta mas que no filtrar)
- **MSFT:** No mejora (baseline VC=True sigue siendo mejor)
- **AMZN:** No evaluable — 0 trades en test con params ganadores de train (cambio de regimen post-2020)

### 2. El forward actua como filtro de calidad
Reduce trade count pero mejora calidad promedio. Funciona mejor en tickers donde:
- Las señales base ya son decentes (AAPL, GOOGL)
- No sobre-filtra donde hay pocas señales (MSFT)
- No descarta winners en tickers ultra-explosivos (NVDA)

### 3. Patron robusto: VC + forward + exits conservadores
Las configs mas robustas combinan:
- Volume contraction (VC=True, ratio 0.85)
- Forward volume confirmation (w3_t1.2_f3 o f5)
- Trailing amplio (tr=2.5-3.0) + stop_loss ajustado (sl=3%)

Ejemplos: AAPL FWD#1 (83%WR, +37% test), GOOGL COMP#3 (100%WR, +14% test).

### 4. Consistencia del umbral 1.2x
En todos los tickers donde forward funciona, threshold=1.2 es suficiente. No se necesita 1.5x — el forward ya filtra naturalmente porque requiere que el precio se mantenga sobre pivot.

### 5. Forward window 3 vs 5 dias
Minima diferencia. Para AAPL, f3 y f5 producen resultados identicos. Recomendacion: usar f3 (menos exposicion temporal).

### 6. Problema de generalizacion temporal
AMZN demuestra un riesgo critico: params de deteccion optimizados en 2015-2019 pueden no producir NINGUNA señal en 2020-2026. El mercado post-COVID cambio la estructura de volatilidad/volumen de algunos tickers. Esto no es un problema del forward filter sino de la deteccion base.

### 7. Limitacion: trade count bajo
La mayoria de configs tienen 2-9 trades en test (6.25 años). Insuficiente para significancia estadistica rigurosa. Los resultados son indicativos, no concluyentes.

---

## Mejor Config por Ticker (Test)

| Ticker | Config | Test T | WR | CR | MaxDD | Sharpe | Veredicto |
|--------|--------|--------|-----|------|-------|--------|-----------|
| **AAPL** | FWD w3_t1.2_f5, tr=3.0, be=1.0, sl=3% | 6 | 83% | +37.38% | -4.02% | 1.07 | Forward gana |
| **GOOGL** | FWD w1_t1.2_f3 VC, tr=2.5, tg=3R, be=1.0, sl=5% | 2 | 100% | +14.34% | 0.00% | 1.47 | Forward gana |
| **NVDA** | Baseline NF, tr=2.5, be=1.5, sl=3% | 9 | 67% | +182.30% | -5.79% | 1.08 | Baseline gana |
| **MSFT** | Baseline VC=True, tr=1.5, be=0.5, sl=3% | 5 | 60% | +4.66% | -4.67% | 0.28 | Baseline gana |
| **AMZN** | — | 0 | — | — | — | — | No viable |

### Scoreboard: Forward 2 — Baseline 2 — No viable 1

## Siguiente Paso

- El forward no es un filtro universal; funciona en tickers con señales de calidad media (AAPL, GOOGL) pero no agrega valor en tickers explosivos (NVDA) ni en los que sobre-filtra (MSFT)
- Considerar usar forward condicionalmente: activar solo cuando VC=True y el ticker tiene >= 8 señales en train
- Problema mas urgente: robustez de la deteccion base (AMZN 0 trades en test)
- Explorar tickers mid-cap donde VCPs pueden ser mas frecuentes y el forward podria tener mas impacto estadistico
