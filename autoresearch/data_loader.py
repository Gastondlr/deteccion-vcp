from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)


def load_ohlc(ticker: str, data_dir: Path) -> pd.DataFrame:
    path = data_dir / f"{ticker}.csv"
    return pd.read_csv(path, parse_dates=["date"], index_col="date")


def get_ticker_info(data_dir: Path) -> pd.DataFrame:
    rows = []
    for path in sorted(data_dir.glob("*.csv")):
        df = pd.read_csv(path, parse_dates=["date"], usecols=["date"])
        rows.append(
            {
                "ticker": path.stem,
                "start_date": df["date"].min(),
                "end_date": df["date"].max(),
                "n_bars": len(df),
            }
        )
    return pd.DataFrame(rows)


def filter_tickers_by_start_date(
    data_dir: Path,
    max_start_date: str | pd.Timestamp = "2015-12-31",
    exclude_tickers: list[str] | None = None,
) -> tuple[list[str], list[str]]:
    """Separa tickers en (optimization_set, out_of_sample_set) segun fecha de inicio.

    Args:
        data_dir: Directorio con los CSVs.
        max_start_date: Fecha limite. Tickers con start <= esta fecha son elegibles
            para optimizacion.
        exclude_tickers: Lista de tickers a EXCLUIR completamente de ambos sets.
            Util para tickers con datos corruptos o irrelevantes (ej: META que
            perdio su historia pre-rebrand).

    Returns:
        Tupla (optimization_tickers, out_of_sample_tickers).
    """
    cutoff = pd.Timestamp(max_start_date)
    excluded = set(exclude_tickers or [])
    optimization = []
    out_of_sample = []

    for csv_path in sorted(data_dir.glob("*.csv")):
        ticker = csv_path.stem
        if ticker in excluded:
            continue
        df = pd.read_csv(csv_path, parse_dates=["date"], index_col="date")
        if df.index[0] <= cutoff:
            optimization.append(ticker)
        else:
            out_of_sample.append(ticker)

    logger.info(
        "Filtered tickers: %d for optimization, %d out-of-sample, %d excluded",
        len(optimization),
        len(out_of_sample),
        len(excluded),
    )
    return optimization, out_of_sample


def find_common_period(
    data_dir: Path,
    tickers: list[str],
) -> tuple[pd.Timestamp, pd.Timestamp]:
    latest_start = pd.Timestamp.min
    earliest_end = pd.Timestamp.max
    for ticker in tickers:
        df = pd.read_csv(
            data_dir / f"{ticker}.csv", parse_dates=["date"], usecols=["date"]
        )
        start, end = df["date"].min(), df["date"].max()
        if start > latest_start:
            latest_start = start
        if end < earliest_end:
            earliest_end = end
    return latest_start, earliest_end


def load_universe(
    data_dir: Path,
    tickers: list[str],
    common_period: bool = False,
) -> dict[str, pd.DataFrame]:
    frames = {}
    if common_period:
        start, end = find_common_period(data_dir, tickers)
        for ticker in tickers:
            df = load_ohlc(ticker, data_dir)
            frames[ticker] = df.loc[start:end]
    else:
        for ticker in tickers:
            frames[ticker] = load_ohlc(ticker, data_dir)
    return frames
