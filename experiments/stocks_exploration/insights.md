# Stocks Exploration — Insights

---

## Config general

- **Activos:** 8 acciones (AAPL, MSFT, NVDA, AVGO, JPM, BRK.B, GOOGL, AMZN)
- **Data:** diaria, 2015-2026
- **Split temporal:** TRAIN 2015-2019 / TEST 2020-2026
- **Comision:** no modelada
- **Stop loss stocks:** 7% max
- **Metrica principal:** CR (Cumulative Return)
- **Optimizacion:** grilla en 2 fases (deteccion + salida)

---

## Sub-experimento 1: Filtros estructurales (Trend Template y Volume Threshold)

### Resultado

En la optimizacion sobre los 8 stocks, se evaluaron los filtros clasicos de Minervini:

- **Trend Template (Stage 2 filter):** `TT=False` gano en 8/8 stocks. El filtro de Stage 2 descarta demasiadas senales buenas.
- **Volume Threshold:** `None` gano en 8/8 stocks. El filtro de volumen no aporta valor para la deteccion via optimizacion.

Estos resultados son unanimes — no hay un solo ticker donde activar estos filtros mejore el rendimiento.

### Conclusiones

- El patron VCP, tal como lo implementa el detector, no se beneficia de los filtros adicionales de Minervini (trend template y volume confirmation). Esto puede deberse a que el detector ya incorpora criterios de calidad suficientes via las contracciones, la reduccion minima y el ascending lows.
- Estos hallazgos motivaron la decision de fijar `TT=False` y `vol_thresh=None` en el experimento stocks_sequential, reduciendo el espacio de busqueda.

---

## Sub-experimento 2: Estabilidad temporal

### Resultado

Se verifico que los parametros optimizados en TRAIN generalizan al periodo TEST. Los resultados confirmaron que la optimizacion en 2 fases produce parametros que no estan sobreajustados a la data de entrenamiento, validando el approach para el experimento sequential posterior.

### Conclusiones

- La confirmacion de estabilidad temporal justifica el diseno del experimento stocks_sequential donde se optimiza en TRAIN y se evalua en TEST sin re-optimizar.

---

## Sintesis final

1. **Los experimentos de exploracion de stocks fueron superados por stocks_sequential**, que aplico las lecciones aprendidas aqui con un framework mas riguroso (modo sequential, un trade a la vez).
2. **Los dos hallazgos clave que informaron el diseno de stocks_sequential fueron:**
   - Trend Template = False gana en 8/8 stocks
   - Volume threshold = None gana en 8/8 stocks
3. **Estos filtros se fijaron en el experimento sequential**, eliminando dimensiones innecesarias de la grilla y permitiendo una busqueda mas eficiente sobre los parametros que si importan (atr_mult, depth_atr, reduction, lookback, trail, target_R, be_R, early_exit).
