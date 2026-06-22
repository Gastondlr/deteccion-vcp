# Stack Tecnologico

## Arquitectura

Pipeline heuristico de 7 pasos secuenciales. Cada paso es un modulo independiente que recibe la salida del anterior y produce objetos de dominio tipados (dataclasses). No hay capa web ni API — es una biblioteca analitica pura con experimentos como consumidores.

## Tecnologias Principales

- **Lenguaje**: Python 3.11+
- **Datos**: pandas (>=2.0), numpy (>=1.24), scipy (>=1.10)
- **Optimizacion**: Optuna para busqueda de hiperparametros
- **Tracking**: MLflow (>=2.10) para registro de experimentos
- **Configuracion**: PyYAML, frozen dataclasses

## Bibliotecas Clave

- **pandas/numpy**: Procesamiento de series temporales OHLCV y calculo de indicadores (ATR, medias moviles)
- **Optuna**: Optimizacion bayesiana de ~20 parametros del pipeline de deteccion
- **MLflow**: Persistencia y comparacion de corridas de optimizacion
- **matplotlib**: Visualizacion de patrones y resultados de backtesting

## Estandares de Desarrollo

### Tipado
Uso consistente de type hints con `from __future__ import annotations`. Objetos de dominio como frozen dataclasses inmutables.

### Calidad de Codigo
- **Formatter**: black (line-length=100)
- **Linter**: ruff (line-length=100)

### Testing
- **Framework**: pytest con pytest-cov
- **Cobertura**: Tests unitarios por modulo del pipeline + tests de integracion con patrones sinteticos
- **Ejecucion**: `pytest` desde la raiz del proyecto

## Entorno de Desarrollo

### Comandos Comunes
```bash
# Tests: pytest
# Formato: black .
# Lint: ruff check .
# Experimento: python experiments/{nombre}/run_optimization.py
```

## Decisiones Tecnicas Clave

- **Heuristico sobre ML**: Interpretabilidad total de cada senal; cada paso del pipeline tiene significado financiero directo
- **Frozen dataclasses**: Inmutabilidad de objetos de dominio para evitar efectos laterales en el pipeline
- **Pythonpath raiz**: Imports absolutos desde la raiz del proyecto (`pythonpath = ["."]` en pyproject.toml)
- **Sin CI/CD**: Proyecto de investigacion; validacion manual via pytest y notebooks

---
_Documentar estandares y patrones, no cada dependencia_
