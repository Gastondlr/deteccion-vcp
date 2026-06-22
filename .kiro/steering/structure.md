# Estructura del Proyecto

## Filosofia de Organizacion

Arquitectura **pipeline-driven y domain-driven**: el codigo se organiza alrededor del pipeline de deteccion de 7 pasos, con separacion clara entre biblioteca core y workbenches de experimentacion.

## Patrones de Directorio

### Biblioteca Core
**Ubicacion**: `vcp_detection/heuristic/`
**Proposito**: Cada modulo implementa un paso del pipeline de deteccion
**Ejemplo**: `swing_detector.py` -> `contractions.py` -> `decreasing_sequence.py` -> `atr_compression.py` -> `volume_contraction.py` -> `pivot_breakout.py`

### Modelos de Dominio
**Ubicacion**: `models/`
**Proposito**: Tipos compartidos (dataclasses), enums y configuraciones
**Ejemplo**: `types.py` (SwingPoint, Contraction, VCPSignal), `configs.py` (ATRZigZagConfig), `enums.py` (SwingType)

### Filtros de Tendencia
**Ubicacion**: `stages/`
**Proposito**: Validacion Stage 2 de Minervini (pre-filtro independiente del pipeline principal)

### Experimentos
**Ubicacion**: `experiments/{asset_class}_{estrategia}/`
**Proposito**: Workbenches de investigacion que consumen la biblioteca core
**Patron de nombre**: `{clase_activo}_{variante}` (ej: `stocks_deep_per_ticker_v2`, `fx_eurusd_detection`)
**Contenido tipico**: `run_optimization.py`, `dev.md` (notas), `insight_*.md` (hallazgos)

### Datos
**Ubicacion**: `data/`
**Proposito**: CSVs OHLCV organizados por clase de activo

### Autoresearch
**Ubicacion**: `autoresearch/`
**Proposito**: Infraestructura de optimizacion (search_space, objective, backtest, integracion MLflow, caching)

## Convenciones de Nombres

- **Clases**: PascalCase (`SwingPoint`, `ATRZigZagDetector`, `VCPSignal`)
- **Funciones**: snake_case (`compute_atr`, `verify_atr_compression`, `run_full_vcp_pipeline`)
- **Archivos**: snake_case, reflejan la funcion/clase principal (`atr_compression.py`, `pivot_breakout.py`)
- **Experimentos**: snake_case descriptivo (`stocks_deep_per_ticker_v2`)

## Patron de Imports

Imports absolutos desde la raiz del proyecto:
```python
from models.types import VCPSignal
from vcp_detection.heuristic import ATRZigZagDetector
from autoresearch.search_space import build_search_space
```
Habilitado por `pythonpath = ["."]` en `pyproject.toml`.

## Principios de Organizacion

- Los experimentos **consumen** la biblioteca core pero nunca la modifican — son workbenches desechables
- Cada paso del pipeline tiene su propio modulo con funcion principal y tests correspondientes en `tests/`
- Los objetos fluyen unidireccionalmente: datos crudos -> SwingPoint -> Contraction -> ... -> VCPSignal
- MLflow tracking (`mlruns/`) registra todas las corridas de optimizacion por experimento

---
_Documentar patrones, no arboles de archivos. Codigo nuevo que siga estos patrones no deberia requerir actualizacion_
