"""Carga y filtrado de universo de tickers para optimización."""

from __future__ import annotations

from pathlib import Path

import pandas as pd


def get_ticker_info(data_dir: str | Path) -> pd.DataFrame:
    """Resume los CSVs disponibles: ticker, start_date, end_date, n_bars.

    Args:
        data_dir: Directorio con CSVs OHLCV (un archivo por ticker).

    Returns:
        DataFrame indexado por ticker con columnas start_date, end_date, n_bars.
    """
    data_dir = Path(data_dir)
    rows = []
    for path in sorted(data_dir.glob("*.csv")):
        df = pd.read_csv(path, parse_dates=["date"], usecols=["date"])
        rows.append({
            "ticker": path.stem,
            "start_date": df["date"].min(),
            "end_date": df["date"].max(),
            "n_bars": len(df),
        })
    return pd.DataFrame(rows).set_index("ticker")


def filter_tickers_by_start_date(
    data_dir: str | Path,
    max_start_date: str,
    exclude_tickers: list[str] | None = None,
) -> tuple[list[str], list[str]]:
    """Separa tickers en optimization set y out-of-sample set.

    Args:
        data_dir: Directorio con CSVs.
        max_start_date: Tickers cuyo start_date <= esta fecha van al
            optimization set. Formato "YYYY-MM-DD".
        exclude_tickers: Tickers a excluir completamente de ambos sets.

    Returns:
        Tupla (optimization_tickers, out_of_sample_tickers), ambas sorted.
    """
    exclude = set(exclude_tickers or [])
    cutoff = pd.Timestamp(max_start_date)
    info = get_ticker_info(data_dir)

    optimization = []
    out_of_sample = []

    for ticker, row in info.iterrows():
        if ticker in exclude:
            continue
        if row["start_date"] <= cutoff:
            optimization.append(ticker)
        else:
            out_of_sample.append(ticker)

    return sorted(optimization), sorted(out_of_sample)


def load_universe(
    tickers: list[str],
    data_dir: str | Path,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, pd.DataFrame]:
    """Carga DataFrames OHLCV para los tickers indicados.

    Args:
        tickers: Lista de tickers a cargar.
        data_dir: Directorio con CSVs.
        start_date: Fecha inicio opcional para filtrar (inclusive).
        end_date: Fecha fin opcional para filtrar (inclusive).

    Returns:
        Dict {ticker: DataFrame} con DatetimeIndex.
    """
    data_dir = Path(data_dir)
    universe = {}
    for ticker in tickers:
        path = data_dir / f"{ticker}.csv"
        df = pd.read_csv(path, parse_dates=["date"], index_col="date")
        if start_date is not None:
            df = df.loc[start_date:]
        if end_date is not None:
            df = df.loc[:end_date]
        universe[ticker] = df
    return universe


def find_common_period(universe: dict[str, pd.DataFrame]) -> tuple[pd.Timestamp, pd.Timestamp]:
    """Encuentra el periodo temporal común a todos los tickers del universo.

    Args:
        universe: Dict {ticker: DataFrame} con DatetimeIndex.

    Returns:
        Tupla (common_start, common_end).

    Raises:
        ValueError: Si el universo está vacío o no hay overlap.
    """
    if not universe:
        raise ValueError("Universe is empty")

    common_start = max(df.index.min() for df in universe.values())
    common_end = min(df.index.max() for df in universe.values())

    if common_start > common_end:
        raise ValueError(
            f"No common period: latest start {common_start.date()} > "
            f"earliest end {common_end.date()}"
        )

    return common_start, common_end
