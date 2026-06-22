# Informe Consolidado v4 — Trend Template Corregido

**Fecha:** 2026-06-22
**Experimento:** `stocks_deep_per_ticker_v4`
**Objetivo:** Evaluar el impacto del Trend Template (TT) de Minervini Stage 2 corregido en la deteccion VCP, optimizado por ticker individual.

---

## Contexto: que corrige v4

En v3 el Trend Template se verificaba en el **dia del breakout** — incorrecto, porque en ese punto el patron ya formo y el precio puede estar en una zona diferente. En v4 se corrige:

1. Se verifican las **7 condiciones** de Minervini en el **primer pico** (inicio de la formacion VCP)
2. Durante la formacion (primer pico → breakout), se exige que las condiciones 2 (SMA150>SMA200), 3 (SMA200 subiendo) y 4 (SMA50>SMA150>SMA200) se mantengan en cada barra

**Train:** pre-2020 | **Test:** 2020-2026 | **Grid:** 122,472 configs deteccion × 720 configs salida

---

## 1. Resultados v4 OOS — Configs optimizadas con TT

Mejor config por ticker evaluada out-of-sample:

| Ticker | B&H Test | Mejor v4 Test CR | T | WR | Sharpe | Resultado |
|--------|----------|------------------|---|-----|--------|-----------|
| **NVDA** | +2935.78% | **+36.93%** | 3 | 100% | 0.99 | Positivo (unica config sobreviviente) |
| **GOOGL** | +363.69% | **+4.32%** | 3 | 67% | 0.36 | Marginal positivo |
| **AAPL** | +244.80% | **-3.45%** | 1 | 0% | 0.00 | Negativo |
| **META** | +178.67% | **-1.07%** | 1 | 0% | 0.00 | Negativo (mejor de 4 configs, todas negativas) |
| **MSFT** | +133.05% | **-3.72%** | 4 | 0% | -1.35 | Negativo |
| **AMZN** | +133.14% | **0 trades** | 0 | — | — | Sin senales |
| **TSLA** | +1282.93% | **0 trades** | 0 | — | — | 0 senales en grid completo |

**Solo NVDA tiene un resultado solido en test.** GOOGL es marginalmente positivo. Los demas son negativos o sin trades.

### Detalle de la unica config exitosa — NVDA v4#4

```
Deteccion: atr=2.0, HL, mda=None, red=0.6, lb=63, comp=0.9, TT=True
Vol filter: w1_t1.2_f3 (backward 1d, threshold 1.2x, forward 3d)
Salida: tr=1.0, tg=3R, be=0.5, sl=5%
```

| # | Entry | Exit | Salida | PnL | R |
|---|-------|------|--------|-----|---|
| 1 | 2024-01-08 | 2024-01-24 | target | +17.43% | +3.5R |
| 2 | 2024-02-05 | 2024-02-20 | trailing_stop | +0.17% | +0.0R |
| 3 | 2024-02-21 | 2024-02-22 | target | +16.40% | +3.3R |

3 trades concentrados en ene-feb 2024 (boom AI/semiconductores). 100% WR, 0% MaxDD.

---

## 2. Experimento v4b — Sin condiciones 2/3/4 durante formacion

**Hipotesis:** la exigencia de cond 2/3/4 en cada barra de la formacion es demasiado estricta y filtra senales validas.

**Resultado: v4b = v4 en test para los 6 tickers.**

| Ticker | v4 Test CR | v4b Test CR | Diferencia |
|--------|-----------|-------------|------------|
| NVDA | +36.93% | +36.93% | Identico |
| GOOGL | +4.32% | +4.32% | Identico |
| AAPL | -3.45% | -3.45% | Identico |
| META | -6.47% | -6.47% | Identico |
| MSFT | -3.72% | -3.72% | Identico |
| AMZN | 0 trades | 0 trades | Identico |

**Conclusion:** la condicion de formacion es **redundante**. Si el primer pico cumple las 7 condiciones TT, las medias moviles de largo plazo (cond 2/3/4) se mantienen naturalmente durante los 10-40 dias de la contraccion. El cuello de botella es el chequeo en el primer pico, no la formacion.

Unica excepcion: MSFT muestra diferencias en **train** (v4b recupera 6 trades extra, CR +12.86% → +25.51%) pero no en test.

---

## 3. Configs v3 + TT como post-filtro (hallazgo principal)

**Hipotesis:** el problema de v4 no es solo el TT — es optimizar configs directamente con TT activado, lo que lleva a overfitting. Las configs v3 (optimizadas sin TT) aplicadas con TT como post-filtro podrian funcionar mejor.

Se tomo la **mejor config v3 recomendada** de cada ticker y se evaluo con y sin TT:

| Ticker | Config v3 usada |
|--------|----------------|
| NVDA | FWD#1 w3_t1.2_f3 tr=2.5 be=1.5 sl=3% |
| GOOGL | COMP#3 w1_t1.2_f3 VC tr=2.5 tg=3R sl=5% |
| META | v2#1 no_filter VC tr=1.5 tg=2R sl=3% |
| TSLA | COMP#1 w3_t1.5 tr=1.5 tg=5R sl=7% |
| AAPL | FWD#1 w3_t1.2_f5 tr=3.0 be=1.0 sl=3% VC |
| MSFT | Baseline no_filter VC tr=1.5 be=0.5 sl=3% |

### 3.1 Funnel de senales — test

| Ticker | Senales sin TT | Sobreviven TT | % eliminadas |
|--------|---------------|---------------|-------------|
| NVDA | 103 | 31 | 70% |
| GOOGL | 54 | 54 | **0%** |
| META | 204 | 84 | 59% |
| AAPL | 98 | 0 | **100%** |
| MSFT | 26 | 0 | **100%** |
| TSLA | 112 | 0 | **100%** |
| AMZN | 0 | 0 | N/A (sin senales base) |

### 3.2 Impacto en performance — test

| Ticker | v3 sin TT | v3 + TT | Delta | Impacto |
|--------|-----------|---------|-------|---------|
| **GOOGL** | +14.34% (2T, 100%WR) | **+14.34%** (2T, 100%WR) | 0 | **TT transparente** — 0% filtrado, senales ya en Stage 2 |
| **NVDA** | +82.15% (5T, 60%WR) | **+72.42%** (2T, 100%WR) | -9.73pp | **TT mejora calidad** — WR 100%, solo 2 trades excepcionales |
| **META** | +107.47% (27T, 56%WR) | **+40.78%** (10T, 60%WR) | -66.69pp | **TT reduce** pero sigue positivo |
| **TSLA** | +79.63% (7T, 71%WR) | **0T** | -79.63pp | **TT destruye** 100% |
| **AAPL** | +37.38% (6T, 83%WR) | **0T** | -37.38pp | **TT destruye** 100% |
| **MSFT** | +4.66% (5T, 60%WR) | **0T** | -4.66pp | **TT destruye** 100% |

### 3.3 Hallazgo critico: META

META v3 + TT = **+40.78%** (10T, 60% WR) en test. Esto es drasticamente superior a cualquier config nativa de v4 para META (todas negativas, mejor: -1.07%).

La razon: v4 optimizo configs CON TT activado y encontro combinaciones que funcionan en train pero no generalizan. La config v3 (optimizada sin TT) genera un pool amplio de senales; el TT como post-filtro selecciona un subconjunto de mayor calidad.

Trades META v3 + TT (test):

| # | Entry | Exit | Salida | PnL | R |
|---|-------|------|--------|-----|---|
| 1 | 2021-06-23 | 2021-07-15 | trailing_stop | +1.14% | +0.4R |
| 2 | 2021-08-25 | 2021-09-17 | trailing_stop | -1.00% | -0.3R |
| 3 | 2023-12-18 | 2024-01-02 | trailing_stop | +0.48% | +0.2R |
| 4 | 2024-01-03 | 2024-01-10 | target | +7.55% | +2.5R |
| 5 | 2024-01-11 | 2024-01-25 | target | +6.36% | +2.1R |
| 6 | 2024-01-26 | 2024-02-02 | target | **+20.51%** | +6.8R |
| 7 | 2024-09-19 | 2024-10-04 | target | +6.59% | +2.2R |
| 8 | 2024-10-07 | 2024-10-21 | stop_loss | -1.65% | -0.5R |
| 9 | 2024-10-22 | 2024-10-23 | stop_loss | -3.15% | -1.0R |
| 10 | 2024-10-24 | 2024-10-31 | trailing_stop | -0.04% | -0.0R |

El TT elimina el rally de mar-jul 2023 (post-crash 2022, precio debajo de medias) pero preserva ene 2024 y sep 2024.

---

## 4. Por que el TT destruye 3 tickers

TSLA, AAPL y MSFT generan **0 senales** con TT en test. La causa raiz:

**Las formaciones VCP de estos tickers ocurren fuera de Minervini Stage 2.** Los mejores VCPs se forman durante:
- Recuperaciones post-crash (precio debajo de SMA150/SMA200)
- Consolidaciones tempranas donde SMA200 aun no sube
- Re-aceleraciones donde SMA50 no ha cruzado sobre SMA150

El TT exige precio > SMA50 > SMA150 > SMA200, todas subiendo. Esto descarta formaciones en fases tempranas de tendencia, que son precisamente las que preceden los movimientos mas grandes.

---

## 5. Comparacion v3 vs v4 — tabla resumen test

| Ticker | v3 mejor sin TT | v4 nativo | v3 mejor + TT | Mejor approach |
|--------|-----------------|-----------|---------------|----------------|
| **NVDA** | +82.15% (5T) | +36.93% (3T) | +72.42% (2T) | v3 sin TT |
| **GOOGL** | +14.34% (2T) | +4.32% (3T) | **+14.34%** (2T) | **v3 (TT transparente)** |
| **META** | **+107.47%** (27T) | -1.07% (1T) | +40.78% (10T) | v3 sin TT |
| **TSLA** | +79.63% (7T) | 0T | 0T | v3 sin TT |
| **AAPL** | +37.38% (6T) | -3.45% (1T) | 0T | v3 sin TT |
| **MSFT** | +4.66% (5T) | -3.72% (4T) | 0T | v3 sin TT |
| **AMZN** | 0T | 0T | 0T | Ninguno |

---

## 6. Observaciones generales

1. **El TT corregido reduce senales entre 59% y 100%.** El filtro es extremadamente restrictivo. De 7 tickers, solo 3 (NVDA, GOOGL, META) sobreviven con senales en test.

2. **Optimizar directamente con TT produce peores resultados OOS que usar TT como post-filtro.** Las configs v4 (optimizadas con TT=True) estan sobre-ajustadas al train. Las configs v3 (optimizadas sin TT) + TT como post-filtro producen un subconjunto de calidad de los trades originales.

3. **La condicion de formacion (cond 2/3/4 durante contraccion) es redundante.** v4b demostro que quitarla no cambia nada en test. El chequeo del primer pico es el filtro real.

4. **GOOGL: TT es transparente con la mejor config v3.** Las senales de GOOGL COMP#3 (VC=True, comp=0.85) ya estan naturalmente en Stage 2 — el TT no filtra ninguna. Con la config suboptima (COMP#1, comp=0.95) parecia que TT ayudaba, pero era un artefacto de usar parametros de deteccion que generaban senales fuera de Stage 2.

5. **El TT tiene un sesgo hacia trades tardios en tendencias maduras.** Los trades sobrevivientes se concentran en 2024 (NVDA, META) — tendencias ya bien establecidas. Esto implica que el TT captura la fase final de una tendencia, no el inicio.

6. **TSLA es incompatible con TT.** 0/115 senales en train y 0/112 en test cumplen Stage 2 en el primer pico. La alta volatilidad de TSLA hace que las medias moviles esten frecuentemente desordenadas.

---

## 7. Conclusiones y recomendaciones

### El Trend Template NO debe usarse como filtro obligatorio universal

El approach optimo depende del ticker:

| Grupo | Tickers | Recomendacion |
|-------|---------|---------------|
| TT transparente | GOOGL | No necesario — la mejor config v3 ya genera senales en Stage 2 |
| TT neutral/leve perdida | NVDA | Opcional — TT mejora WR pero pierde CR total |
| TT reduce pero no destruye | META | No usar TT (v3 sin TT = +107% vs +41% con TT) |
| TT incompatible | TSLA, AAPL, MSFT | No usar TT — elimina 100% de senales |
| Sin senales | AMZN | Revisar deteccion base |

### Si se usa TT, aplicar como post-filtro sobre configs v3

No optimizar configs con TT=True (overfitting). En cambio:
1. Optimizar deteccion y salida SIN TT (como en v3)
2. Aplicar TT como filtro opcional post-hoc
3. Evaluar por ticker si TT mejora o empeora

### Siguiente paso sugerido

Investigar variantes parciales del TT que no destruyan tickers como AAPL/TSLA/MSFT:
- TT "light": solo cond 1 (precio > SMA150) + cond 7 (precio > SMA200)
- TT con umbral de mayoria (cumplir 5/7 condiciones en vez de 7/7)
- TT con lookback flexible (chequear N dias antes del primer pico, no exactamente en el)
