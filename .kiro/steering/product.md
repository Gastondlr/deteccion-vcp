# Descripcion del Producto

Sistema de deteccion automatizada de patrones VCP (Volatility Contraction Pattern) basado en la metodologia SEPA de Mark Minervini. Transforma un metodo de trading discretional en un pipeline algoritmico reproducible y optimizable.

## Capacidades Principales

1. **Pipeline de deteccion**: Algoritmo de 7 pasos secuenciales que identifica patrones VCP en datos OHLCV — desde swing points hasta senales de breakout
2. **Simulacion de trades**: Evaluacion de senales con gestion de riesgo (stops, targets, reglas de salida) y analisis de P&L
3. **Optimizacion de hiperparametros**: Busqueda sistematica de configuraciones optimas por activo/universo via Optuna con tracking en MLflow
4. **Filtros de tendencia**: Validacion Stage 2 de Minervini como pre-filtro para calidad de senales

## Casos de Uso

- Screening automatico de acciones y pares FX que presentan contracciones de volatilidad
- Backtesting riguroso de estrategias VCP con proteccion anti look-ahead bias
- Investigacion cuantitativa: optimizacion por activo individual con evaluacion out-of-sample

## Propuesta de Valor

Implementacion sistematica y verificable de una metodologia probada de trading, con capacidad de optimizacion parametrica por activo y tracking completo de experimentos. El enfoque heuristico (no ML) permite interpretabilidad total de cada senal generada.

---
_Enfoque en patrones y proposito, no listas exhaustivas de funcionalidades_
