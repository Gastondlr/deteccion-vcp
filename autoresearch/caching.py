"""Cache de swings y contracciones para evitar recomputar pasos 1-2 entre trials."""

from __future__ import annotations

import pandas as pd

from models.configs import ATRZigZagConfig
from models.types import Contraction, SwingPoint
from vcp_detection.heuristic.contractions import compute_contractions
from vcp_detection.heuristic.swing_detector import ATRZigZagDetector


class SwingCache:
    """Cache de swings + contracciones indexado por (ticker, atr_length, atr_mult, use_close_only).

    Los pasos 1 (swing detection) y 2 (contraction computation) dependen
    solo de swing_config. Si dos trials comparten el mismo swing_config,
    reusar el resultado ahorra ~40-60% del tiempo por trial.
    """

    def __init__(self) -> None:
        self._cache: dict[tuple, dict] = {}
        self.hits: int = 0
        self.misses: int = 0

    def get_or_compute(
        self,
        ticker: str,
        ohlc: pd.DataFrame,
        swing_config: ATRZigZagConfig,
    ) -> dict[str, list[SwingPoint] | list[Contraction]]:
        """Retorna swings y contracciones, desde cache si es posible.

        Args:
            ticker: Nombre del ticker.
            ohlc: DataFrame OHLCV con DatetimeIndex.
            swing_config: Configuración del detector de swings.

        Returns:
            Dict con keys "swings" y "contractions".
        """
        key = (ticker, swing_config.atr_length, swing_config.atr_mult, swing_config.use_close_only)

        if key in self._cache:
            self.hits += 1
            return self._cache[key]

        self.misses += 1
        detector = ATRZigZagDetector(swing_config)
        swings = detector.detect(ohlc)
        contractions = compute_contractions(swings, ohlc)

        result = {"swings": swings, "contractions": contractions}
        self._cache[key] = result
        return result

    def stats(self) -> dict:
        """Retorna estadísticas del cache."""
        total = self.hits + self.misses
        return {
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate": self.hits / total if total > 0 else 0.0,
            "size": len(self._cache),
        }

    def clear(self) -> None:
        """Limpia el cache y resetea contadores."""
        self._cache.clear()
        self.hits = 0
        self.misses = 0
