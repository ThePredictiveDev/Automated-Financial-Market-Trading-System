"""Historical/live market data fetch via yahooquery (primary) with yfinance
fallback, on-disk parquet/CSV caching, and retry with backoff."""
from __future__ import annotations

import logging
import os
import random
import time
from typing import Optional, Tuple

import pandas as pd
import requests

logger = logging.getLogger(__name__)

try:
    import yahooquery as yq  # type: ignore
    YQ_AVAILABLE = True
except ImportError:
    yq = None  # type: ignore
    YQ_AVAILABLE = False

try:
    import yfinance as yf  # type: ignore
    YF_AVAILABLE = True
except ImportError:
    yf = None  # type: ignore
    YF_AVAILABLE = False


def _ensure_cache_dir() -> str:
    cache_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".cache")
    cache_dir = os.path.abspath(cache_dir)
    os.makedirs(cache_dir, exist_ok=True)
    return cache_dir


def _build_session() -> requests.Session:
    try:
        from requests_cache import CachedSession  # type: ignore
        try:
            from pyrate_limiter import Duration, Limiter, RequestRate  # type: ignore
            from requests_ratelimiter import LimiterSession  # type: ignore

            class CachedLimiterSession(CachedSession, LimiterSession):
                pass

            session = CachedLimiterSession(
                limiter=Limiter(RequestRate(2, Duration.SECOND * 5)), backend="sqlite",
                cache_name=os.path.join(_ensure_cache_dir(), "yfinance_cache"),
                allowable_codes=(200,), stale_if_error=True,
            )
        except ImportError:
            session = CachedSession(cache_name=os.path.join(_ensure_cache_dir(), "yfinance_cache"),
                                     backend="sqlite", allowable_codes=(200,), stale_if_error=True)
    except ImportError:
        session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 (compatible; trading-simulator/2.0)"})
    return session


_HTTP_SESSION = _build_session()


def _cache_paths(symbol: str, start, end, interval, period) -> Tuple[str, str]:
    cache_dir = _ensure_cache_dir()
    parts = [symbol] + [p for p in (start, end, interval, period) if p]
    base = "yq_hist_" + "_".join(parts)
    return os.path.join(cache_dir, f"{base}.parquet"), os.path.join(cache_dir, f"{base}.csv")


def _save_cache(df: pd.DataFrame, parquet_path: str, csv_path: str) -> None:
    try:
        df.to_parquet(parquet_path, index=True)
    except Exception:
        try:
            df.to_csv(csv_path, index=True)
        except OSError:
            logger.warning("Failed to persist history cache for %s", csv_path, exc_info=True)


def _load_cache(parquet_path: str, csv_path: str) -> Optional[pd.DataFrame]:
    if os.path.exists(parquet_path):
        try:
            return pd.read_parquet(parquet_path)
        except Exception:
            logger.warning("Failed reading parquet cache %s, falling back", parquet_path, exc_info=True)
    if os.path.exists(csv_path):
        try:
            return pd.read_csv(csv_path, index_col=0, parse_dates=True)
        except Exception:
            logger.warning("Failed reading csv cache %s", csv_path, exc_info=True)
    return None


def _normalize_columns(df: pd.DataFrame, symbol: str) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    if isinstance(df.index, pd.MultiIndex) and "symbol" in df.index.names:
        try:
            df = df.xs(symbol, level="symbol", drop_level=True)
        except KeyError:
            pass
    if "symbol" in df.columns:
        df = df[df["symbol"] == symbol].drop(columns=["symbol"])
    rename_map = {"open": "Open", "high": "High", "low": "Low", "close": "Close",
                  "adjclose": "Adj Close", "adj_close": "Adj Close", "volume": "Volume"}
    actual = {c: rename_map[c.lower()] for c in df.columns if c.lower() in rename_map}
    return df.rename(columns=actual) if actual else df


def fetch_history_with_retry(symbol: str, *, period: Optional[str] = None, interval: Optional[str] = None,
                              start: Optional[str] = None, end: Optional[str] = None,
                              max_retries: int = 5, base_backoff: float = 1.5) -> pd.DataFrame:
    last_exc: Optional[Exception] = None
    if YQ_AVAILABLE:
        for attempt in range(max_retries):
            try:
                ticker = yq.Ticker(symbol, session=_HTTP_SESSION)
                data = ticker.history(period=period, interval=interval) if (period and interval) else \
                    ticker.history(start=start, end=end, interval="1d")
                if data is not None and not data.empty:
                    data = _normalize_columns(data, symbol)
                    if data is not None and not data.empty:
                        return data
            except Exception as exc:
                last_exc = exc
                logger.warning("yahooquery fetch failed (attempt %s/%s): %s", attempt + 1, max_retries, exc)
            time.sleep(base_backoff ** attempt + random.uniform(0, 0.5))
        logger.error("yahooquery exhausted retries for %s; falling back to yfinance if available", symbol)

    if YF_AVAILABLE:
        try:
            df = yf.Ticker(symbol).history(period=period, interval=interval) if (period and interval) else \
                yf.download(symbol, start=start, end=end, interval="1d", progress=False)
            if df is not None and not df.empty:
                return df
        except Exception as exc:
            last_exc = exc
            logger.error("yfinance fallback failed for %s: %s", symbol, exc)

    if last_exc:
        raise last_exc
    if not YQ_AVAILABLE and not YF_AVAILABLE:
        raise RuntimeError(
            f"Could not fetch market data for {symbol!r}: neither yahooquery nor yfinance is installed. "
            "Run `pip install -r requirements.txt` (or `pip install yahooquery yfinance`) to enable live/backtest "
            "data fetching, or use --mode demo, which needs no market data provider."
        )
    raise RuntimeError(
        f"Market data fetch for {symbol!r} returned no data after retries. This usually means the symbol is "
        "wrong/delisted, the date range has no trading days, or there's no network access from this machine."
    )


def load_historical_data(symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
    parquet_path, csv_path = _cache_paths(symbol, start_date, end_date, None, None)
    cached = _load_cache(parquet_path, csv_path)
    if cached is not None and not cached.empty:
        df = cached.copy().reset_index()
        if "date" in df.columns and "Date" not in df.columns:
            df = df.rename(columns={"date": "Date"})
        return df

    data = fetch_history_with_retry(symbol, start=start_date, end=end_date, max_retries=6, base_backoff=1.8)
    if data is None or data.empty:
        raise RuntimeError(f"No historical data returned for {symbol} between {start_date} and {end_date}")
    _save_cache(data, parquet_path, csv_path)
    df = data.copy()
    if isinstance(df.index, pd.MultiIndex) and "date" in df.index.names:
        df = df.reset_index(level="date").rename(columns={"date": "Date"})
    else:
        df["Date"] = df.index
        df.reset_index(drop=True, inplace=True)
    if "date" in df.columns and "Date" not in df.columns:
        df = df.rename(columns={"date": "Date"})
    if "Close" not in df.columns:
        raise RuntimeError(f"Historical data for {symbol} missing required 'Close' column")
    return df


def load_multi_historical_data(symbols, start_date: str, end_date: str):
    data_map = {}
    for sym in symbols:
        df = load_historical_data(sym, start_date, end_date)
        ts = pd.to_datetime(df["Date"], utc=True, errors="coerce")
        data_map[sym] = df.assign(Date=ts).dropna(subset=["Date"]).reset_index(drop=True)
    return data_map
