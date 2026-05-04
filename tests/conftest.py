"""Fixtures compartidos para tests del detector VCP.

Genera datos sinteticos con propiedades conocidas para verificar que cada
paso del pipeline produce los resultados esperados.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


@pytest.fixture
def synthetic_vcp_ohlc() -> pd.DataFrame:
    """Genera un DataFrame OHLC sintetico con un patron VCP conocido.

    Estructura del precio sintetico:
    - Dias 0-49: tendencia alcista (de $10 a ~$15).
    - Dias 50-69: contraccion 1 (caida ~12%, de $15 a ~$13.2).
    - Dias 70-89: recuperacion parcial a ~$14.8.
    - Dias 90-104: contraccion 2 (caida ~7%, de $14.8 a ~$13.8).
    - Dias 105-119: recuperacion a ~$14.7.
    - Dias 120-129: contraccion 3 (caida ~3%, de $14.7 a ~$14.3).
    - Dias 130-139: recuperacion y breakout por encima de $15.
    - Dias 140-159: continuacion post-breakout.

    Returns:
        DataFrame con columnas [open, high, low, close, volume] y DatetimeIndex.
    """
    np.random.seed(42)
    n_bars = 160
    dates = pd.bdate_range(start="2023-01-02", periods=n_bars)

    close = np.zeros(n_bars)

    # Fase 1: tendencia alcista
    close[0:50] = np.linspace(10.0, 15.0, 50) + np.random.normal(0, 0.05, 50)

    # Contraccion 1: ~12% de caida
    close[50:70] = np.concatenate([
        np.linspace(15.0, 13.2, 15),
        np.linspace(13.2, 14.8, 5),
    ]) + np.random.normal(0, 0.03, 20)

    # Contraccion 2: ~7% de caida
    close[70:90] = np.concatenate([
        np.linspace(14.8, 14.8, 5),
        np.linspace(14.8, 13.8, 10),
        np.linspace(13.8, 14.7, 5),
    ]) + np.random.normal(0, 0.03, 20)

    # Contraccion 3: ~3% de caida
    close[90:110] = np.concatenate([
        np.linspace(14.7, 14.7, 5),
        np.linspace(14.7, 14.3, 8),
        np.linspace(14.3, 14.6, 7),
    ]) + np.random.normal(0, 0.02, 20)

    # Tight range antes del breakout
    close[110:130] = np.linspace(14.6, 14.9, 20) + np.random.normal(0, 0.02, 20)

    # Breakout y continuacion
    close[130:140] = np.linspace(15.2, 16.5, 10) + np.random.normal(0, 0.05, 10)
    close[140:160] = np.linspace(16.5, 18.0, 20) + np.random.normal(0, 0.08, 20)

    high = close + np.abs(np.random.normal(0.1, 0.05, n_bars))
    low = close - np.abs(np.random.normal(0.1, 0.05, n_bars))
    open_ = close + np.random.normal(0, 0.05, n_bars)

    # Volumen decreciente durante la base
    volume = np.ones(n_bars) * 1_000_000
    volume[50:70] = 1_200_000  # Alto en contraccion 1
    volume[70:90] = 900_000    # Menor en contraccion 2
    volume[90:110] = 600_000   # Menor aun en contraccion 3
    volume[110:130] = 400_000  # Muy bajo en tight range
    volume[130:140] = 2_000_000  # Explosion en breakout
    volume += np.random.normal(0, 50_000, n_bars)
    volume = np.maximum(volume, 100_000)

    return pd.DataFrame(
        {
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        },
        index=dates,
    )


@pytest.fixture
def flat_ohlc() -> pd.DataFrame:
    """Genera un DataFrame OHLC plano (sin patron VCP).

    Precio lateral con ruido aleatorio — no deberia generar senales VCP.
    """
    np.random.seed(123)
    n_bars = 200
    dates = pd.bdate_range(start="2023-01-02", periods=n_bars)

    close = 50.0 + np.random.normal(0, 0.3, n_bars).cumsum() * 0.01
    close = np.maximum(close, 45.0)
    close = np.minimum(close, 55.0)

    high = close + np.abs(np.random.normal(0.2, 0.1, n_bars))
    low = close - np.abs(np.random.normal(0.2, 0.1, n_bars))
    open_ = close + np.random.normal(0, 0.1, n_bars)
    volume = np.random.uniform(500_000, 1_500_000, n_bars)

    return pd.DataFrame(
        {
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        },
        index=dates,
    )


@pytest.fixture
def downtrend_ohlc() -> pd.DataFrame:
    """Genera un DataFrame OHLC en tendencia bajista.

    No deberia producir patrones VCP validos — las contracciones
    seran profundas y no mostraran compresion.
    """
    np.random.seed(456)
    n_bars = 200
    dates = pd.bdate_range(start="2023-01-02", periods=n_bars)

    close = np.linspace(100.0, 50.0, n_bars) + np.random.normal(0, 1.0, n_bars)
    close = np.maximum(close, 30.0)

    high = close + np.abs(np.random.normal(1.0, 0.5, n_bars))
    low = close - np.abs(np.random.normal(1.0, 0.5, n_bars))
    open_ = close + np.random.normal(0, 0.5, n_bars)
    volume = np.random.uniform(1_000_000, 3_000_000, n_bars)

    return pd.DataFrame(
        {
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        },
        index=dates,
    )
