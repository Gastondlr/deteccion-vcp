"""Paso 1: Deteccion de swing points (maximos y minimos locales) en series OHLC.

============================================================================
DESCRIPCION DEL PASO
============================================================================
El primer paso del pipeline VCP es identificar los **swing points** — los
maximos y minimos locales significativos en la serie de precios. Estos puntos
definen la estructura del patron: cada par (HIGH, LOW) consecutivo forma una
"contraccion" que se evalua en los pasos siguientes.

============================================================================
METODOS IMPLEMENTADOS
============================================================================

1. ATRZigZagDetector (recomendado)
   - Algoritmo ZigZag adaptativo con threshold basado en ATR (Average True Range).
   - Recorre la serie hacia adelante (causal) manteniendo un extremo candidato
     y una direccion (UP buscando highs, DOWN buscando lows).
   - Confirma un swing cuando el precio revierte al menos ``atr_mult * ATR``
     desde el extremo actual.
   - Cada swing tiene un ``confirmed_at`` explicito — la fecha del bar donde
     se cruzo el threshold de confirmacion. Esto permite filtrar por fecha en
     backtesting para evitar look-ahead bias.
   - Ventaja: inherentemente causal (procesa barra a barra sin ver el futuro).

2. ScipyPeaksDetector (alternativo)
   - Basado en scipy.signal.find_peaks con filtrado por prominence.
   - Suaviza la serie con SMA, detecta picos/valles, y filtra por prominence
     (fija o autoescalada con ATR).
   - Modo causal (config.causal=True): SMA no centrada + descarte de swings
     inestables al final.
   - Modo no-causal (default): SMA centrada, introduce look-ahead implicito.

============================================================================
LIBRERIAS UTILIZADAS
============================================================================
- numpy: Operaciones vectorizadas sobre arrays de precios (True Range, argmax/argmin).
- pandas: Series temporales con DatetimeIndex, rolling windows para ATR.
- scipy.signal.find_peaks: Deteccion de picos (solo en ScipyPeaksDetector).
- scipy.signal.peak_prominences: Calculo de prominence de picos (solo en ScipyPeaksDetector).
- yaml: Carga de configuracion desde archivos YAML.

============================================================================
CALCULO DEL ATR (Average True Range)
============================================================================
El ATR mide la volatilidad intradia promedio. Se calcula asi:

1. True Range (TR) para cada barra:
   TR_t = max(High_t - Low_t, |High_t - Close_{t-1}|, |Low_t - Close_{t-1}|)

2. ATR = SMA(TR, period) — media movil simple del TR sobre ``period`` barras.
   (Esta implementacion usa SMA; la version de Paso 4 usa Wilder's RMA).

El ATR se usa como threshold adaptativo: en momentos de alta volatilidad se
necesita una reversion mayor para confirmar un swing, evitando falsos positivos.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from scipy.signal import find_peaks, peak_prominences

from models.configs import ATRZigZagConfig, ScipyPeaksConfig
from models.enums import SwingType
from models.types import SwingPoint

logger = logging.getLogger(__name__)

_REQUIRED_COLUMNS = {"open", "high", "low", "close"}


def _compute_atr(
    high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int
) -> np.ndarray:
    """Calcula Average True Range (SMA del True Range).

    Args:
        high: Array de precios high.
        low: Array de precios low.
        close: Array de precios close.
        period: Periodo de la media movil.

    Returns:
        Array de ATR con min_periods=1 (primeros valores son aproximados).
    """
    prev_close = np.empty_like(close)
    prev_close[0] = close[0]
    prev_close[1:] = close[:-1]

    tr = np.maximum(
        high - low,
        np.maximum(np.abs(high - prev_close), np.abs(low - prev_close)),
    )
    return pd.Series(tr).rolling(period, min_periods=1).mean().to_numpy()


class SwingDetector(ABC):
    """ABC para detectores de swing points en series OHLC.

    Implementaciones distintas heredan de esta clase y respetan la misma
    interfaz para poder intercambiarse en el pipeline de VCP detection.
    """

    @abstractmethod
    def detect(self, ohlc: pd.DataFrame) -> list[SwingPoint]:
        """Detecta swings sobre el DataFrame OHLC.

        Args:
            ohlc: DataFrame con indice DatetimeIndex y columnas
                ['open', 'high', 'low', 'close']. Volumen opcional.

        Returns:
            Lista ordenada cronologicamente de SwingPoint, alternando HIGH y LOW.
        """
        ...

    def _validate_ohlc(self, ohlc: pd.DataFrame) -> None:
        """Valida que el DataFrame tenga el schema esperado.

        Args:
            ohlc: DataFrame a validar.

        Raises:
            ValueError: Si faltan columnas, el indice no es DatetimeIndex o esta vacio.
        """
        missing = _REQUIRED_COLUMNS - set(ohlc.columns)
        if missing:
            raise ValueError(f"OHLC DataFrame missing required columns: {missing}")
        if not isinstance(ohlc.index, pd.DatetimeIndex):
            raise ValueError(
                "OHLC DataFrame must have a DatetimeIndex, "
                f"got {type(ohlc.index).__name__}"
            )
        if len(ohlc) == 0:
            raise ValueError("OHLC DataFrame is empty")


class ATRZigZagDetector(SwingDetector):
    """Detector de swings basado en ZigZag con threshold adaptativo por ATR.

    Recorre la serie hacia adelante manteniendo un extremo candidato y una
    direccion (UP buscando highs, DOWN buscando lows). Confirma un swing
    cuando el precio revierte por mas de ``atr_mult * ATR`` desde el extremo.

    El ``confirmed_at`` de cada swing es la fecha del bar donde se cruzo el
    threshold de confirmacion, no la fecha del extremo. Esto permite filtrar
    por ``confirmed_at`` en backtesting para evitar look-ahead bias.

    Args:
        config: Parametros del detector.
    """

    def __init__(self, config: ATRZigZagConfig | None = None) -> None:
        self.config = config or ATRZigZagConfig()

    def detect(self, ohlc: pd.DataFrame) -> list[SwingPoint]:
        """Detecta swings usando ATR ZigZag.

        Args:
            ohlc: DataFrame OHLC con DatetimeIndex.

        Returns:
            Lista de SwingPoint alternando HIGH/LOW. El ultimo swing puede estar
            sin confirmar (metadata["confirmed"] == False).
        """
        self._validate_ohlc(ohlc)

        high = ohlc["high"].to_numpy(dtype=np.float64)
        low = ohlc["low"].to_numpy(dtype=np.float64)
        close = ohlc["close"].to_numpy(dtype=np.float64)
        dates = ohlc.index
        n = len(ohlc)

        atr = _compute_atr(high, low, close, self.config.atr_length)
        start_idx = self.config.atr_length - 1
        if n <= start_idx:
            logger.warning(
                "Series too short for ATR ZigZag (%d bars, need >= %d)", n, start_idx + 1
            )
            return []

        use_close = self.config.use_close_only
        compare_high = close if use_close else high
        compare_low = close if use_close else low

        direction = "UP"
        extreme_price = compare_high[start_idx]
        extreme_idx = start_idx
        extreme_atr = atr[start_idx]

        swings: list[SwingPoint] = []

        for i in range(start_idx + 1, n):
            if direction == "UP":
                if compare_high[i] > extreme_price:
                    extreme_price = compare_high[i]
                    extreme_idx = i
                    extreme_atr = atr[i]
                    continue

                fall = extreme_price - compare_low[i]
                if fall >= self.config.atr_mult * extreme_atr:
                    swings.append(
                        SwingPoint(
                            date=dates[extreme_idx],
                            price=float(high[extreme_idx]),
                            type=SwingType.HIGH,
                            confirmed_at=dates[i],
                            metadata={
                                "atr_at_swing": float(extreme_atr),
                                "confirmed": True,
                            },
                        )
                    )
                    direction = "DOWN"
                    new_idx, new_val = self._find_initial_extreme(
                        compare_low, extreme_idx + 1, i
                    )
                    extreme_price = new_val
                    extreme_idx = new_idx
                    extreme_atr = atr[new_idx]

            else:
                if compare_low[i] < extreme_price:
                    extreme_price = compare_low[i]
                    extreme_idx = i
                    extreme_atr = atr[i]
                    continue

                rise = compare_high[i] - extreme_price
                if rise >= self.config.atr_mult * extreme_atr:
                    swings.append(
                        SwingPoint(
                            date=dates[extreme_idx],
                            price=float(low[extreme_idx]),
                            type=SwingType.LOW,
                            confirmed_at=dates[i],
                            metadata={
                                "atr_at_swing": float(extreme_atr),
                                "confirmed": True,
                            },
                        )
                    )
                    direction = "UP"
                    new_idx, new_val = self._find_initial_extreme(
                        compare_high, extreme_idx + 1, i, find_max=True
                    )
                    extreme_price = new_val
                    extreme_idx = new_idx
                    extreme_atr = atr[new_idx]

        last_type = SwingType.HIGH if direction == "UP" else SwingType.LOW
        last_price = float(high[extreme_idx]) if direction == "UP" else float(low[extreme_idx])
        swings.append(
            SwingPoint(
                date=dates[extreme_idx],
                price=last_price,
                type=last_type,
                confirmed_at=dates[-1],
                metadata={"atr_at_swing": float(extreme_atr), "confirmed": False},
            )
        )

        logger.debug(
            "ATR ZigZag detected %d swings (%d confirmed)",
            len(swings),
            sum(1 for s in swings if s.metadata.get("confirmed")),
        )
        return swings

    @staticmethod
    def _find_initial_extreme(
        values: np.ndarray, start: int, end: int, find_max: bool = False
    ) -> tuple[int, float]:
        """Encuentra el extremo en un rango para inicializar la nueva direccion.

        Args:
            values: Array de precios a buscar.
            start: Indice de inicio (inclusive).
            end: Indice de fin (inclusive).
            find_max: Si True busca maximo; si False busca minimo.

        Returns:
            Tupla (indice, valor) del extremo encontrado.
        """
        segment = values[start : end + 1]
        if find_max:
            offset = int(np.argmax(segment))
        else:
            offset = int(np.argmin(segment))
        idx = start + offset
        return idx, float(values[idx])

    @classmethod
    def from_yaml(cls, yaml_path: str | Path) -> ATRZigZagDetector:
        """Crea una instancia desde un archivo YAML.

        Args:
            yaml_path: Ruta al archivo YAML con la seccion swing_detection.atr_zigzag.

        Returns:
            Instancia configurada de ATRZigZagDetector.
        """
        with open(yaml_path) as f:
            raw = yaml.safe_load(f)
        params = raw["swing_detection"]["atr_zigzag"]
        return cls(config=ATRZigZagConfig(**params))


class ScipyPeaksDetector(SwingDetector):
    """Detector de swings basado en scipy.signal.find_peaks.

    Suaviza la serie de close con SMA, detecta picos y valles via find_peaks,
    y filtra por prominence (fija o autoescalada con ATR). Luego fuerza
    alternancia HIGH/LOW.

    Args:
        config: Parametros del detector.
    """

    def __init__(self, config: ScipyPeaksConfig | None = None) -> None:
        self.config = config or ScipyPeaksConfig()

    def detect(self, ohlc: pd.DataFrame) -> list[SwingPoint]:
        """Detecta swings usando scipy.signal.find_peaks.

        Args:
            ohlc: DataFrame OHLC con DatetimeIndex.

        Returns:
            Lista de SwingPoint alternando HIGH/LOW.
        """
        self._validate_ohlc(ohlc)

        high = ohlc["high"].to_numpy(dtype=np.float64)
        low = ohlc["low"].to_numpy(dtype=np.float64)
        close = ohlc["close"].to_numpy(dtype=np.float64)
        dates = ohlc.index
        n = len(ohlc)

        smoothed = (
            pd.Series(close)
            .rolling(
                self.config.smoothing_window,
                center=not self.config.causal,
                min_periods=1,
            )
            .mean()
            .to_numpy()
        )

        atr: np.ndarray | None = None
        if self.config.prominence is None:
            atr = _compute_atr(high, low, close, 14)

        peak_indices = self._find_filtered_peaks(smoothed, atr, is_high=True)
        valley_indices = self._find_filtered_peaks(smoothed, atr, is_high=False)

        margin = self.config.stability_margin
        if margin is None:
            margin = self.config.min_distance_bars

        if self.config.causal:
            lookforward = margin
            max_allowed = n - 1 - margin
            if max_allowed < 0:
                logger.warning(
                    "Series too short for causal Scipy peaks (%d bars, need > %d)",
                    n,
                    margin,
                )
                return []
            peak_indices = peak_indices[peak_indices <= max_allowed]
            valley_indices = valley_indices[valley_indices <= max_allowed]
        else:
            lookforward = self.config.min_distance_bars // 2 + 1

        raw_swings: list[SwingPoint] = []
        for idx in peak_indices:
            confirmed_idx = min(idx + lookforward, n - 1)
            raw_swings.append(
                SwingPoint(
                    date=dates[idx],
                    price=float(high[idx]),
                    type=SwingType.HIGH,
                    confirmed_at=dates[confirmed_idx],
                    metadata={"detector": "scipy_peaks"},
                )
            )
        for idx in valley_indices:
            confirmed_idx = min(idx + lookforward, n - 1)
            raw_swings.append(
                SwingPoint(
                    date=dates[idx],
                    price=float(low[idx]),
                    type=SwingType.LOW,
                    confirmed_at=dates[confirmed_idx],
                    metadata={"detector": "scipy_peaks"},
                )
            )

        raw_swings.sort(key=lambda s: s.date)
        swings = self._enforce_alternation(raw_swings)

        logger.debug(
            "Scipy peaks detected %d swings (causal=%s)", len(swings), self.config.causal
        )
        return swings

    def _find_filtered_peaks(
        self, smoothed: np.ndarray, atr: np.ndarray | None, *, is_high: bool
    ) -> np.ndarray:
        """Encuentra picos o valles filtrados por prominence.

        Args:
            smoothed: Serie suavizada.
            atr: ATR array para autoescalar prominence (None si prominence es fija).
            is_high: True para buscar picos, False para valles.

        Returns:
            Array de indices de los picos/valles que pasan el filtro.
        """
        signal = smoothed if is_high else -smoothed

        indices, _ = find_peaks(signal, distance=self.config.min_distance_bars)
        if len(indices) == 0:
            return indices

        proms, _, _ = peak_prominences(signal, indices)

        if self.config.prominence is not None:
            mask = proms >= self.config.prominence
        else:
            atr_at_peaks = atr[indices]  # type: ignore[index]
            mask = proms >= self.config.prominence_atr_mult * atr_at_peaks

        return indices[mask]

    @staticmethod
    def _enforce_alternation(swings: list[SwingPoint]) -> list[SwingPoint]:
        """Fuerza alternancia HIGH/LOW quedandose con el extremo mas significativo.

        Args:
            swings: Lista de swings ordenada por fecha, posiblemente con tipos
                consecutivos repetidos.

        Returns:
            Lista filtrada con alternancia estricta HIGH/LOW.
        """
        if len(swings) <= 1:
            return list(swings)

        result: list[SwingPoint] = [swings[0]]
        for sw in swings[1:]:
            if sw.type == result[-1].type:
                if sw.type == SwingType.HIGH and sw.price > result[-1].price:
                    result[-1] = sw
                elif sw.type == SwingType.LOW and sw.price < result[-1].price:
                    result[-1] = sw
            else:
                result.append(sw)
        return result

    @classmethod
    def from_yaml(cls, yaml_path: str | Path) -> ScipyPeaksDetector:
        """Crea una instancia desde un archivo YAML.

        Args:
            yaml_path: Ruta al archivo YAML con la seccion swing_detection.scipy_peaks.

        Returns:
            Instancia configurada de ScipyPeaksDetector.
        """
        with open(yaml_path) as f:
            raw = yaml.safe_load(f)
        params = raw["swing_detection"]["scipy_peaks"]
        return cls(config=ScipyPeaksConfig(**params))
