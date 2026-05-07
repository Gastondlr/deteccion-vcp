"""Plantilla de Tendencia (Trend Template) de Mark Minervini — 7 condiciones de Etapa 2.

Filtro binario que determina si una acción está en Stage 2 (advancing phase).
Las 7 condiciones deben cumplirse simultáneamente. Una acción que pasa este
filtro es candidata para buscar patrones VCP con el pipeline heurístico.

Referencia: *Trade Like a Stock Market Wizard* (Minervini, 2013), Capítulo 4.
"""

from __future__ import annotations

import pandas as pd


def compute_smas(df: pd.DataFrame) -> pd.DataFrame:
    """Calcula SMAs de 50, 150 y 200 días sobre el precio de cierre.

    Args:
        df: DataFrame con columna ``close``.

    Returns:
        Copia del DataFrame con columnas ``sma_50``, ``sma_150``, ``sma_200``.
    """
    out = df.copy()
    close = out["close"]
    out["sma_50"] = close.rolling(window=50, min_periods=50).mean()
    out["sma_150"] = close.rolling(window=150, min_periods=150).mean()
    out["sma_200"] = close.rolling(window=200, min_periods=200).mean()
    return out


def compute_52w_extremes(df: pd.DataFrame) -> pd.DataFrame:
    """Calcula mínimo y máximo rolling de 52 semanas (252 días hábiles).

    Args:
        df: DataFrame con columnas ``low`` y ``high``.

    Returns:
        Copia del DataFrame con columnas ``low_52w`` y ``high_52w``.
    """
    out = df.copy()
    out["low_52w"] = out["low"].rolling(window=252, min_periods=252).min()
    out["high_52w"] = out["high"].rolling(window=252, min_periods=252).max()
    return out


def evaluate_trend_template(df: pd.DataFrame) -> pd.DataFrame:
    """Evalúa las 7 condiciones de la Plantilla de Tendencia de Minervini.

    Args:
        df: DataFrame con columnas mínimas ``close``, ``high``, ``low``.

    Returns:
        DataFrame con columnas originales más: ``sma_50``, ``sma_150``,
        ``sma_200``, ``low_52w``, ``high_52w``, ``cond_1``..``cond_7``,
        ``trend_template``, ``conditions_met``.
    """
    out = compute_smas(df)
    out = compute_52w_extremes(out)

    close = out["close"]
    sma_50 = out["sma_50"]
    sma_150 = out["sma_150"]
    sma_200 = out["sma_200"]

    # Cond 1: Precio por encima de SMA 150 y SMA 200
    out["cond_1"] = (close > sma_150) & (close > sma_200)

    # Cond 2: SMA 150 por encima de SMA 200
    out["cond_2"] = sma_150 > sma_200

    # Cond 3: SMA 200 en tendencia alcista (al menos 1 mes / 22 días hábiles)
    out["cond_3"] = sma_200 > sma_200.shift(22)

    # Cond 4: SMA 50 por encima de SMA 150 y SMA 200
    out["cond_4"] = (sma_50 > sma_150) & (sma_50 > sma_200)

    # Cond 5: Precio por encima de SMA 50
    out["cond_5"] = close > sma_50

    # Cond 6: Precio al menos 30% por encima del mínimo de 52 semanas
    out["cond_6"] = close >= out["low_52w"] * 1.30

    # Cond 7: Precio dentro del 25% del máximo de 52 semanas
    out["cond_7"] = close >= out["high_52w"] * 0.75

    cond_cols = [f"cond_{i}" for i in range(1, 8)]

    # NaN en cualquier indicador → False
    for col in cond_cols:
        out[col] = out[col].fillna(False).astype(bool)

    out["trend_template"] = out[cond_cols].all(axis=1)
    out["conditions_met"] = out[cond_cols].sum(axis=1).astype(int)

    return out


def screen_universe(
    dfs: dict[str, pd.DataFrame],
    date: str,
) -> pd.DataFrame:
    """Filtra un universo de acciones por la Plantilla de Tendencia en una fecha dada.

    Args:
        dfs: Dict ``{ticker: DataFrame_ohlcv}``.
        date: Fecha de evaluación en formato ``YYYY-MM-DD``.

    Returns:
        DataFrame resumen con una fila por ticker, ordenado por
        ``conditions_met`` descendente.
    """
    rows: list[dict] = []

    for ticker, df in sorted(dfs.items()):
        evaluated = evaluate_trend_template(df)

        if "date" in evaluated.columns:
            date_col = evaluated["date"]
            if pd.api.types.is_datetime64_any_dtype(date_col):
                mask = date_col == pd.Timestamp(date)
            else:
                mask = date_col == date
            if not mask.any():
                continue
            row_data = evaluated.loc[mask].iloc[-1]
        elif isinstance(evaluated.index, pd.DatetimeIndex):
            target = pd.Timestamp(date)
            if target not in evaluated.index:
                continue
            row_data = evaluated.loc[target]
            if isinstance(row_data, pd.DataFrame):
                row_data = row_data.iloc[-1]
        else:
            continue

        row = {"ticker": ticker, "close": row_data["close"]}
        for col in ["sma_50", "sma_150", "sma_200"]:
            row[col] = row_data[col]
        for i in range(1, 8):
            row[f"cond_{i}"] = row_data[f"cond_{i}"]
        row["trend_template"] = row_data["trend_template"]
        row["conditions_met"] = row_data["conditions_met"]
        rows.append(row)

    if not rows:
        cols = (
            ["ticker", "close", "sma_50", "sma_150", "sma_200"]
            + [f"cond_{i}" for i in range(1, 8)]
            + ["trend_template", "conditions_met"]
        )
        return pd.DataFrame(columns=cols)

    result = pd.DataFrame(rows)
    return result.sort_values("conditions_met", ascending=False).reset_index(drop=True)
