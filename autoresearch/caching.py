"""Cache de swings y contracciones para evitar recomputar pasos 1-2."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from models.configs import ATRZigZagConfig
from vcp_detection.heuristic.swing_detector import ATRZigZagDetector
from vcp_detection.heuristic.contractions import compute_contractions


@dataclass
class _CacheEntry:
    swings: list
    contractions: list


class SwingCache:
    """Cache de resultados de pasos 1 (swings) y 2 (contracciones).

    La clave de cache es ``(ticker, atr_length, atr_mult)``. Mientras esos
    parámetros no cambien, devuelve el resultado cacheado.
    """

    def __init__(self) -> None:
        self._store: dict[tuple, _CacheEntry] = {}
        self._hits = 0
        self._misses = 0

    def _key(self, ticker: str, config: dict) -> tuple:
        return (ticker, config["atr_length"], config["atr_mult"])

    def get_or_compute(
        self,
        ticker: str,
        ohlc: pd.DataFrame,
        config: dict,
        min_depth_pct: float = 0.0,
    ) -> dict[str, Any]:
        key = self._key(ticker, config)
        if key in self._store:
            self._hits += 1
            entry = self._store[key]
            return {"swings": entry.swings, "contractions": entry.contractions}

        self._misses += 1
        cfg = ATRZigZagConfig(**config)
        detector = ATRZigZagDetector(cfg)
        swings = detector.detect(ohlc)
        contractions = compute_contractions(swings, ohlc=ohlc, min_depth_pct=min_depth_pct)

        self._store[key] = _CacheEntry(swings=swings, contractions=contractions)
        return {"swings": swings, "contractions": contractions}

    def stats(self) -> dict[str, int]:
        return {"hits": self._hits, "misses": self._misses, "size": len(self._store)}

    def clear(self) -> None:
        self._store.clear()
        self._hits = 0
        self._misses = 0
