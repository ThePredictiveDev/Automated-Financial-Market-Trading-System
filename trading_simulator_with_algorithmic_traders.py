"""
Trading Simulator in Python With Algorithmic Traders

Converted from Jupyter Notebook to a standalone Python 3.11+ script.
All functionality from the notebook has been retained and made runnable.

Features included:
- Order book, matching engine, FIX server integration (simplefix)
- Live market data via yfinance with broadcast to subscribers
- Market maker, synthetic liquidity provider
- Algorithmic traders: Momentum, EMA-based, Swing, Sentiment-analysis
- News fetching via NewsAPI for sentiment trader
- Backtesting harness
- CLI to run live or backtest modes

Notes:
- Ensure dependencies are installed: pandas, numpy, yfinance, simplefix, tensorflow, newsapi-python, statistics (stdlib), etc.
- The sentiment model file and NewsAPI key are required to enable the sentiment trader.
"""

from __future__ import annotations

from collections import deque
from bisect import insort  # noqa: F401 (kept for parity with notebook; not used directly)
import argparse
import logging
import os
import random
import socket
import threading
import time
import uuid
import math
from typing import Any, Deque, Dict, List, Optional, Tuple, Callable
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd
import requests

try:
    import simplefix
except Exception as exc:  # pragma: no cover - dependency availability at runtime
    raise RuntimeError(
        "simplefix is required. Install with: pip install simplefix"
    ) from exc

try:
    import yahooquery as yq
except Exception as exc:  # pragma: no cover
    raise RuntimeError(
        "yahooquery is required. Install with: pip install yahooquery"
    ) from exc

try:
    import tensorflow as tf
    from tensorflow.keras.models import load_model #type: ignore
except Exception as exc:  # pragma: no cover
    raise RuntimeError(
        "TensorFlow is required for the sentiment trader. Install with: pip install tensorflow"
    ) from exc

try:
    from newsapi import NewsApiClient
except Exception as exc:  # pragma: no cover
    raise RuntimeError(
        "newsapi-python is required for the sentiment trader. Install with: pip install newsapi-python"
    ) from exc

# Database (SQLAlchemy) for persistence
try:
    from sqlalchemy import Column, String, Float, Integer, DateTime, Text, create_engine
    from sqlalchemy.orm import declarative_base, sessionmaker
    SQLA_AVAILABLE = True
except Exception:
    SQLA_AVAILABLE = False

# Optional experiment tooling
try:
    import optuna  # type: ignore
    OPTUNA_AVAILABLE = True
except Exception:
    OPTUNA_AVAILABLE = False

try:
    import mlflow  # type: ignore
    MLFLOW_AVAILABLE = True
except Exception:
    MLFLOW_AVAILABLE = False


# --------------------------------------------------------------------------------------
# Logging
# --------------------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


# --------------------------------------------------------------------------------------
# FIX tags and mappings (retained from notebook)
# --------------------------------------------------------------------------------------
FIX_TAGS: Dict[int, str] = {
    8: "BeginString",
    35: "MsgType",
    11: "ClOrdID",
    54: "Side",
    55: "Symbol",
    44: "Price",
    38: "OrderQty",
    10: "Checksum",
    41: "OrigClOrdID",
}

SIDE_MAPPING: Dict[str, str] = {
    '1': 'Buy',
    '2': 'Sell',
}

MSG_TYPE_MAPPING: Dict[str, str] = {
    'D': 'NewOrderSingle',
    'F': 'OrderCancelRequest',
}


# --------------------------------------------------------------------------------------
# Yahoo data fetch utilities (yahooquery) with retry + optional on-disk cache
# --------------------------------------------------------------------------------------
TICK_SIZE: Dict[str, float] = {}
LOT_SIZE: Dict[str, int] = {}
DECIMAL_PRECISION: Dict[str, int] = {}
INSTRUMENTS: Dict[str, Dict[str, Any]] = {}

def _tick_size_for_symbol(symbol: str) -> float:
    return float(TICK_SIZE.get(symbol, 0.01))

def _normalize_price_to_tick(price: float, symbol: str) -> float:
    tick = _tick_size_for_symbol(symbol)
    if tick <= 0:
        res = float(price)
    else:
        res = float(round(float(price) / tick) * tick)
    # Apply instrument decimal precision if configured
    prec = int(DECIMAL_PRECISION.get(symbol, 0))
    if prec > 0:
        return round(res, prec)
    return res

def _lot_size_for_symbol(symbol: str) -> int:
    return int(LOT_SIZE.get(symbol, 1))

def _normalize_quantity_to_lot(quantity: int, symbol: str) -> int:
    lot = _lot_size_for_symbol(symbol)
    if lot <= 1:
        return int(quantity)
    return int(quantity // lot * lot)

def _is_market_open(symbol: str, now_utc: Optional[pd.Timestamp] = None) -> bool:
    cfg = INSTRUMENTS.get(symbol)
    if not cfg:
        return True
    try:
        tz = cfg.get('tz') or 'America/New_York'
        open_str = cfg.get('open') or '09:30'
        close_str = cfg.get('close') or '16:00'
        holidays = set(cfg.get('holidays') or [])
        now_utc = now_utc or pd.Timestamp.utcnow().tz_localize('UTC')
        local = now_utc.tz_convert(tz)
        date_key = local.strftime('%Y-%m-%d')
        if date_key in holidays:
            return False
        t_open = pd.to_datetime(f"{date_key} {open_str}").tz_localize(tz)
        t_close = pd.to_datetime(f"{date_key} {close_str}").tz_localize(tz)
        return bool(t_open <= local <= t_close)
    except Exception:
        return True
def _ensure_cache_dir() -> str:
    cache_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".cache")
    try:
        os.makedirs(cache_dir, exist_ok=True)
    except Exception:
        pass
    return cache_dir


def _build_yf_session() -> requests.Session:
    """Create a shared requests session with caching and rate limiting if available."""
    # Default plain session
    session: requests.Session
    try:
        from requests_cache import CachedSession  # type: ignore
        try:
            from requests_ratelimiter import LimiterSession  # type: ignore
            from pyrate_limiter import Duration, RequestRate, Limiter  # type: ignore

            class CachedLimiterSession(CachedSession, LimiterSession):
                pass

            session = CachedLimiterSession(
                limiter=Limiter(RequestRate(2, Duration.SECOND * 5)),
                backend="sqlite",
                cache_name=os.path.join(_ensure_cache_dir(), "yfinance_cache"),
                allowable_codes=(200,),
                stale_if_error=True,
            )
        except Exception:
            # Fallback to cache only
            session = CachedSession(
                cache_name=os.path.join(_ensure_cache_dir(), "yfinance_cache"),
                backend="sqlite",
                allowable_codes=(200,),
                stale_if_error=True,
            )
    except Exception:
        session = requests.Session()

    # Set a UA header to align with yfinance behavior; set timeouts per request in calls
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
    })

    # Optional proxy support via environment variables HTTPS_PROXY/HTTP_PROXY already honored by requests
    return session


_HTTP_SESSION: requests.Session = _build_yf_session()


def _cache_path_for_history(symbol: str, start: Optional[str], end: Optional[str], interval: Optional[str], period: Optional[str]) -> Tuple[str, str]:
    cache_dir = _ensure_cache_dir()
    name_parts = [symbol]
    if start:
        name_parts.append(start)
    if end:
        name_parts.append(end)
    if interval:
        name_parts.append(interval)
    if period:
        name_parts.append(period)
    base = "yq_hist_" + "_".join(name_parts)
    parquet_path = os.path.join(cache_dir, f"{base}.parquet")
    csv_path = os.path.join(cache_dir, f"{base}.csv")
    return parquet_path, csv_path


def _save_cache_df(df: pd.DataFrame, parquet_path: str, csv_path: str) -> None:
    try:
        # Try parquet first for efficiency
        df.to_parquet(parquet_path, index=True)
    except Exception:
        try:
            df.to_csv(csv_path, index=True)
        except Exception:
            pass


def _load_cache_df(parquet_path: str, csv_path: str) -> Optional[pd.DataFrame]:
    if os.path.exists(parquet_path):
        try:
            return pd.read_parquet(parquet_path)
        except Exception:
            pass
    if os.path.exists(csv_path):
        try:
            return pd.read_csv(csv_path, index_col=0, parse_dates=True)
        except Exception:
            pass
    return None


def _normalize_yq_history_df(df: pd.DataFrame, symbol: str) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    # Handle MultiIndex (symbol, date) or symbol column
    if isinstance(df.index, pd.MultiIndex) and 'symbol' in df.index.names:
        try:
            df = df.xs(symbol, level='symbol', drop_level=True)
        except Exception:
            pass
    if 'symbol' in df.columns:
        try:
            df = df[df['symbol'] == symbol].drop(columns=['symbol'])
        except Exception:
            pass
    # Rename columns to expected case
    rename_map = {
        'open': 'Open',
        'high': 'High',
        'low': 'Low',
        'close': 'Close',
        'adjclose': 'Adj Close',
        'adj_close': 'Adj Close',
        'volume': 'Volume',
    }
    actual_rename: Dict[str, str] = {}
    for col in df.columns:
        low = col.lower()
        if low in rename_map:
            actual_rename[col] = rename_map[low]
    if actual_rename:
        df = df.rename(columns=actual_rename)
    return df


def _yq_history_with_retry(symbol: str, *, period: Optional[str] = None, interval: Optional[str] = None,
                            start: Optional[str] = None, end: Optional[str] = None,
                            max_retries: int = 5, base_backoff: float = 1.5) -> pd.DataFrame:
    last_exc: Optional[Exception] = None
    for attempt in range(max_retries):
        try:
            if period is not None and interval is not None:
                data = yq.Ticker(symbol, session=_HTTP_SESSION).history(period=period, interval=interval)
            else:
                # Date range daily
                data = yq.Ticker(symbol, session=_HTTP_SESSION).history(start=start, end=end, interval='1d')
            if data is not None and not data.empty:
                data = _normalize_yq_history_df(data, symbol)
                if data is not None and not data.empty:
                    return data
        except Exception as exc:
            last_exc = exc
            logging.warning("yahooquery fetch failed (attempt %s/%s): %s", attempt + 1, max_retries, exc)
        # Backoff with jitter
        sleep_s = base_backoff ** attempt + random.uniform(0, 0.5)
        time.sleep(sleep_s)

    if last_exc:
        logging.error("yahooquery fetch failed after %s attempts: %s", max_retries, last_exc)
        raise last_exc
    # If simply empty without exception after retries, raise to caller
    raise RuntimeError("yahooquery returned empty data after retries")


# --------------------------------------------------------------------------------------
# Order and OrderBook
# --------------------------------------------------------------------------------------
@dataclass
class Order:
    id: str
    price: float
    quantity: int
    side: str            # 'buy' or 'sell'
    type: str            # 'limit' or 'market'
    symbol: str
    tif: str = 'GTC'     # 'GTC', 'IOC', 'FOK'
    post_only: bool = False
    timestamp: float = field(default_factory=lambda: time.time())
    owner_id: str = "default"
    expires_at: Optional[pd.Timestamp] = None
    auction_only: bool = False
    auction_phase: Optional[str] = None  # 'open' or 'close'


class OrderBook:
    """In-memory limit order book for bids and asks with basic operations."""

    def __init__(self) -> None:
        self.bids: Dict[float, Deque[Order]] = {}
        self.asks: Dict[float, Deque[Order]] = {}
        self.order_map: Dict[str, Order] = {}
        self._bid_prices: List[float] = []   # descending
        self._ask_prices: List[float] = []   # ascending

    def add_order(self, order: Order) -> None:
        # Enforce tick size normalization
        normalized_price = _normalize_price_to_tick(order.price, order.symbol)
        order.price = normalized_price
        if order.side == 'buy':
            if order.price not in self.bids:
                self.bids[order.price] = deque()
                # insert into sorted bid prices (desc)
                import bisect
                pos = bisect.bisect_left([-p for p in self._bid_prices], -order.price)
                self._bid_prices.insert(pos, order.price)
            self.bids[order.price].append(order)
        else:
            if order.price not in self.asks:
                self.asks[order.price] = deque()
                # insert into sorted ask prices (asc)
                import bisect
                pos = bisect.bisect_left(self._ask_prices, order.price)
                self._ask_prices.insert(pos, order.price)
            self.asks[order.price].append(order)
        self.order_map[order.id] = order

    def remove_order(self, order_id: str) -> None:
        if order_id not in self.order_map:
            return
        order = self.order_map[order_id]
        if order.side == 'buy':
            queue = self.bids.get(order.price)
            if queue is not None and order in queue:
                queue.remove(order)
                if not queue:
                    del self.bids[order.price]
                    # remove from price list
                    try:
                        self._bid_prices.remove(order.price)
                    except ValueError:
                        pass
        else:
            queue = self.asks.get(order.price)
            if queue is not None and order in queue:
                queue.remove(order)
                if not queue:
                    del self.asks[order.price]
                    try:
                        self._ask_prices.remove(order.price)
                    except ValueError:
                        pass
        del self.order_map[order_id]

    def cancel_order(self, order_id: str) -> None:
        if order_id in self.order_map:
            self.remove_order(order_id)
            logging.info(f"Order {order_id} has been cancelled.")
        else:
            logging.warning(f"Order {order_id} not found for cancellation.")

    def modify_order(self, order_id: str, new_quantity: Optional[int] = None, new_price: Optional[float] = None) -> None:
        if order_id not in self.order_map:
            logging.warning(f"Order {order_id} not found for modification.")
            return
        order = self.order_map[order_id]
        self.remove_order(order_id)
        if new_quantity is not None:
            order.quantity = int(new_quantity)
        if new_price is not None:
            order.price = float(new_price)
        self.add_order(order)
        logging.info(f"Order {order_id} has been modified.")

    def get_best_bid(self) -> Optional[float]:
        return self._bid_prices[0] if self._bid_prices else None

    def get_best_ask(self) -> Optional[float]:
        return self._ask_prices[0] if self._ask_prices else None

    def bids_to_dataframe(self) -> pd.DataFrame:
        rows: List[Dict[str, Any]] = []
        for price in sorted(self.bids.keys(), reverse=True):
            for order in self.bids[price]:
                rows.append({'Order ID': order.id, 'Price': order.price, 'Quantity': order.quantity})
        return pd.DataFrame(rows)

    def asks_to_dataframe(self) -> pd.DataFrame:
        rows: List[Dict[str, Any]] = []
        for price in sorted(self.asks.keys()):
            for order in self.asks[price]:
                rows.append({'Order ID': order.id, 'Price': order.price, 'Quantity': order.quantity})
        return pd.DataFrame(rows)

    def display_order_book(self) -> None:
        logging.info("Order Book:")
        bids_df = self.bids_to_dataframe()
        asks_df = self.asks_to_dataframe()
        logging.info("Bid Side:\n%s", bids_df.to_string(index=False) if not bids_df.empty else "<empty>")
        logging.info("Ask Side:\n%s", asks_df.to_string(index=False) if not asks_df.empty else "<empty>")


# --------------------------------------------------------------------------------------
# Matching Engine
# --------------------------------------------------------------------------------------
class MatchingEngine:
    """Naive matching engine to cross incoming orders against resting book."""

    def __init__(self, order_book: OrderBook) -> None:
        self.order_book = order_book
        self._lock = threading.RLock()
        self._trade_subscribers: List[Callable[["Execution"], None]] = []
        self.risk_manager: Optional[RiskManager] = None  # type: ignore[name-defined]
        # Latency/slippage modeling (used by backtests)
        self.latency_ms: int = 0
        self.slippage_bps_per_100_shares: float = 0.0
        self._current_time: Optional[pd.Timestamp] = None
        self._delayed_orders: List[Tuple[pd.Timestamp, Order]] = []
        # Price band protection
        self.price_band_bps: float = 0.0
        self.band_reference: str = 'mid'  # 'mid' or 'last'
        self._last_trade_price_by_symbol: Dict[str, float] = {}
        # Auction state
        self.auction_mode: Optional[str] = None  # None/'open'/'close'
        self._auction_orders: List[Order] = []
        # Fees/Rebates (bps)
        self.taker_fee_bps: float = 0.0
        self.maker_rebate_bps: float = 0.0
        # Optional event logger
        self.event_logger: Optional[EventLogger] = None  # type: ignore[name-defined]
        # Halted symbols
        self._halted: set[str] = set()
        # Optional submission queue for concurrency model
        self.use_queue: bool = False
        self.queue_max: int = 10000
        self._order_queue: Deque[Order] = deque()
        self._queue_cond = threading.Condition(self._lock)
        self._loop_running: bool = False
        self._loop_thread: Optional[threading.Thread] = None

    def subscribe_trades(self, callback: Callable[["Execution"], None]) -> None:
        self._trade_subscribers.append(callback)

    def _emit_trade(self, execution: "Execution") -> None:
        # Track last trade price per symbol for banding
        try:
            self._last_trade_price_by_symbol[execution.symbol] = float(execution.price)
        except Exception:
            pass
        # Event log with best bid/ask snapshot for TCA
        try:
            if self.event_logger is not None:
                bb = self.order_book.get_best_bid()
                ba = self.order_book.get_best_ask()
                self.event_logger.log_execution(execution, best_bid=bb, best_ask=ba)
        except Exception:
            pass
        for cb in list(self._trade_subscribers):
            try:
                cb(execution)
            except Exception as exc:
                logging.exception("Trade subscriber error: %s", exc)
        # TCA logging: slippage vs mid and last trade
        try:
            mid = self._mid_price()
            last = self.get_last_trade_price(execution.symbol)
            slip_mid = None if mid is None else ((execution.price - mid) / mid * 10000.0 if execution.side == 'buy' else (mid - execution.price) / mid * 10000.0)
            slip_last = None if last is None or last == 0 else ((execution.price - last) / last * 10000.0 if execution.side == 'buy' else (last - execution.price) / last * 10000.0)
            if hasattr(self, 'tca_logger') and getattr(self, 'tca_logger') is not None:
                self.tca_logger.log_tca(execution.timestamp, execution.symbol, execution.side, float(execution.price), mid, last, slip_mid, slip_last)  # type: ignore[attr-defined]
        except Exception:
            pass

    def _reference_price(self, symbol: str) -> Optional[float]:
        if self.band_reference == 'last':
            return self._last_trade_price_by_symbol.get(symbol)
        # default to mid
        best_bid = self.order_book.get_best_bid()
        best_ask = self.order_book.get_best_ask()
        if best_bid is not None and best_ask is not None:
            return float((best_bid + best_ask) / 2.0)
        return self._last_trade_price_by_symbol.get(symbol)

    def _mid_price(self) -> Optional[float]:
        bb = self.order_book.get_best_bid()
        ba = self.order_book.get_best_ask()
        if bb is None or ba is None:
            return None
        return float((bb + ba) / 2.0)

    def _within_price_band(self, order: Order) -> bool:
        if self.price_band_bps <= 0 or order.type != 'limit':
            return True
        ref = self._reference_price(order.symbol)
        if ref is None or ref <= 0:
            return True
        dev_bps = abs(order.price - ref) / ref * 10000.0
        return dev_bps <= self.price_band_bps

    def get_last_trade_price(self, symbol: str) -> Optional[float]:
        return self._last_trade_price_by_symbol.get(symbol)

    def _available_depth(self, side: str, limit_price: float) -> int:
        # Returns total opposing quantity available up to limit price for sweeping
        total = 0
        if side == 'buy':
            # consume asks up to limit_price
            for px in list(self.order_book._ask_prices):
                if px is None or px > limit_price:
                    break
                q = self.order_book.asks.get(px)
                if not q:
                    continue
                for o in q:
                    total += int(getattr(o, 'quantity', 0))
        else:
            # consume bids down to limit_price
            for px in list(self.order_book._bid_prices):
                if px is None or px < limit_price:
                    break
                q = self.order_book.bids.get(px)
                if not q:
                    continue
                for o in q:
                    total += int(getattr(o, 'quantity', 0))
        return total

    def set_time(self, current_time: pd.Timestamp) -> None:
        self._current_time = current_time

    def process_delayed_orders(self, upto_time: pd.Timestamp) -> None:
        with self._lock:
            if not self._delayed_orders:
                return
            self._delayed_orders.sort(key=lambda x: x[0])
            ready: List[Tuple[pd.Timestamp, Order]] = []
            while self._delayed_orders and self._delayed_orders[0][0] <= upto_time:
                ready.append(self._delayed_orders.pop(0))
        for _, order in ready:
            self._direct_match(order)

    def match_order(self, incoming_order: Order) -> None:
        with self._lock:
            # Halt protection
            if incoming_order.symbol in self._halted and self.auction_mode is None:
                logging.warning("Order %s rejected: trading halted for %s", incoming_order.id, incoming_order.symbol)
                return
            # Pre-trade risk check
            if self.risk_manager is not None and not self.risk_manager.allow_order(incoming_order):
                logging.warning("Order %s rejected by risk manager", incoming_order.id)
                return
            # Session check
            if not _is_market_open(incoming_order.symbol, self._current_time or pd.Timestamp.utcnow().tz_localize('UTC')):
                logging.warning("Order %s rejected: market closed for %s", incoming_order.id, incoming_order.symbol)
                return
            # Auction routing
            if self.auction_mode is not None:
                # Only accept orders allowed for current phase
                if incoming_order.auction_only and (incoming_order.auction_phase in (None, self.auction_mode)):
                    self._auction_orders.append(incoming_order)
                    return
                # During auction, regular orders rest but not execute until uncross, unless they are auction_only which go to pool
                if not incoming_order.auction_only:
                    # Allow resting for limit; hold market orders until uncross
                    if incoming_order.type == 'limit':
                        self.order_book.add_order(incoming_order)
                    else:
                        # buffer market orders into auction pool
                        incoming_order.auction_only = True
                        incoming_order.auction_phase = self.auction_mode
                        self._auction_orders.append(incoming_order)
                    return
            # Log accepted new order event
            try:
                if self.event_logger is not None:
                    self.event_logger.log_new_order(incoming_order)
            except Exception:
                pass
            # Latency: enqueue if configured and current time known
            if self.latency_ms > 0 and self._current_time is not None:
                available_at = self._current_time + pd.Timedelta(milliseconds=int(self.latency_ms))
                self._delayed_orders.append((available_at, incoming_order))
                return
            # Direct matching path
            self._direct_match(incoming_order)

    def submit_order(self, incoming_order: Order) -> None:
        if not self.use_queue:
            self.match_order(incoming_order)
            return
        with self._lock:
            if len(self._order_queue) >= self.queue_max:
                logging.warning("Order queue full; rejecting order %s", incoming_order.id)
                return
            self._order_queue.append(incoming_order)
            self._queue_cond.notify()

    def start_loop(self) -> None:
        if not self.use_queue:
            return
        with self._lock:
            if self._loop_running:
                return
            self._loop_running = True
            self._loop_thread = threading.Thread(target=self._run_loop, daemon=True)
            self._loop_thread.start()

    def stop_loop(self) -> None:
        with self._lock:
            self._loop_running = False
            self._queue_cond.notify_all()
        if self._loop_thread is not None:
            try:
                self._loop_thread.join(timeout=3)
            except Exception:
                pass
            self._loop_thread = None

    def _run_loop(self) -> None:
        while True:
            with self._lock:
                if not self._loop_running:
                    break
                while self._loop_running and not self._order_queue:
                    self._queue_cond.wait(timeout=0.5)
                    if not self._loop_running:
                        return
                if not self._order_queue:
                    continue
                order = self._order_queue.popleft()
            # Process outside of lock to avoid blocking producers
            try:
                self.match_order(order)
            except Exception as exc:
                logging.exception("Engine loop error: %s", exc)

    def halt(self, symbol: str) -> None:
        with self._lock:
            self._halted.add(symbol)

    def resume(self, symbol: str) -> None:
        with self._lock:
            self._halted.discard(symbol)

    def depth_snapshot(self, top_n: int = 5) -> Dict[str, List[Tuple[float, int]]]:
        with self._lock:
            bids: List[Tuple[float, int]] = []
            asks: List[Tuple[float, int]] = []
            for px in list(self.order_book._bid_prices)[:top_n]:
                q = self.order_book.bids.get(px)
                if q:
                    bids.append((px, sum(o.quantity for o in q)))
            for px in list(self.order_book._ask_prices)[:top_n]:
                q = self.order_book.asks.get(px)
                if q:
                    asks.append((px, sum(o.quantity for o in q)))
            return {"bids": bids, "asks": asks}

    def start_auction(self, phase: str) -> None:
        with self._lock:
            self.auction_mode = phase
            self._auction_orders.clear()

    def uncross_auction(self) -> None:
        with self._lock:
            if self.auction_mode is None:
                return
            # Build indicative book from resting regular limits and auction pool
            temp_bids: Dict[float, int] = {}
            temp_asks: Dict[float, int] = {}
            def add_side(dst: Dict[float, int], px: float, qty: int):
                dst[px] = dst.get(px, 0) + qty
            # Include resting limit orders
            for px, q in self.order_book.bids.items():
                size = sum(o.quantity for o in q if o.type == 'limit')
                if size > 0:
                    add_side(temp_bids, px, size)
            for px, q in self.order_book.asks.items():
                size = sum(o.quantity for o in q if o.type == 'limit')
                if size > 0:
                    add_side(temp_asks, px, size)
            # Include auction-only orders as aggressive: market treated as crossing all; limits as normal
            for ao in self._auction_orders:
                if ao.side == 'buy':
                    px = math.inf if ao.type == 'market' else ao.price
                    add_side(temp_bids, px, ao.quantity)
                else:
                    px = 0.0 if ao.type == 'market' else ao.price
                    add_side(temp_asks, px, ao.quantity)
            # Determine single-price cross maximizing matched volume
            prices = sorted(set([p for p in temp_bids.keys() if p != math.inf] + [p for p in temp_asks.keys() if p != 0.0]))
            if not prices and temp_bids and temp_asks:
                # fallback to mid of best levels
                bb = max([p for p in temp_bids.keys() if p != math.inf], default=None)
                ba = min([p for p in temp_asks.keys() if p != 0.0], default=None)
                if bb is not None and ba is not None:
                    prices = [float((bb + ba) / 2.0)]
            best_price = None
            best_volume = -1
            for px in prices:
                buy_qty = sum(q for p, q in temp_bids.items() if p >= px)
                sell_qty = sum(q for p, q in temp_asks.items() if p <= px)
                matched = min(buy_qty, sell_qty)
                if matched > best_volume:
                    best_volume = matched
                    best_price = px
            if best_price is None or best_volume <= 0:
                # No cross; exit auction mode without trades
                self.auction_mode = None
                self._auction_orders.clear()
                return
            # Execute at single price: sweep actual book and pool
            # Convert auction pool to immediate crossing orders at best_price
            pool = list(self._auction_orders)
            self._auction_orders.clear()
            self.auction_mode = None
        # Outside lock: process pool orders at cross price using direct matching repeatedly
        # Force effective_limit around cross price to ensure crossing
        for ao in pool:
            if ao.side == 'buy':
                ao.type = 'limit'
                ao.price = best_price
                self._direct_match(ao)
            else:
                ao.type = 'limit'
                ao.price = best_price
                self._direct_match(ao)

    def _direct_match(self, order: Order) -> None:
        # Enforce lot/precision on order entry (normalize price and quantity)
        if order.type == 'limit':
            order.price = _normalize_price_to_tick(order.price, order.symbol)
        order.quantity = _normalize_quantity_to_lot(order.quantity, order.symbol)
        if order.quantity <= 0:
            logging.warning("Order %s rejected after lot normalization (qty<=0)", order.id)
            return
        # Reject orders outside price bands
        if order.type == 'limit' and not self._within_price_band(order):
            logging.warning("Order %s rejected by price band protection: price=%s symbol=%s", order.id, order.price, order.symbol)
            return
        # FOK pre-check: require full available depth
        if order.tif == 'FOK':
            if order.side == 'buy':
                eff = order.price if order.type == 'limit' else math.inf
                avail = self._available_depth('buy', eff)
            else:
                eff = order.price if order.type == 'limit' else 0.0
                avail = self._available_depth('sell', eff)
            if avail < order.quantity:
                logging.info("FOK order %s cancelled: insufficient depth (need %s, have %s)", order.id, order.quantity, avail)
                return
        if order.side == 'buy':
            self._match_buy_order(order)
        else:
            self._match_sell_order(order)

    def cancel_order(self, order_id: str) -> None:
        with self._lock:
            self.order_book.cancel_order(order_id)
            try:
                if self.event_logger is not None:
                    self.event_logger.log_cancel(order_id)
            except Exception:
                pass

    def _match_buy_order(self, order: Order) -> None:
        # For market orders, treat limit as infinite to cross all available asks
        effective_limit = order.price if order.type == 'limit' else math.inf
        filled_any = False
        while order.quantity > 0 and self.order_book.get_best_ask() is not None:
            best_ask_price = self.order_book.get_best_ask()
            logging.info(f"Best ask price: {best_ask_price}, Incoming buy order price: {order.price}")
            if best_ask_price is not None and effective_limit >= best_ask_price:
                logging.info(f"Executing buy order at price {best_ask_price}")
                order = self._execute_order(order, best_ask_price, 'sell')
                filled_any = True
            else:
                break
        # TIF and POST-ONLY handling
        if order.quantity > 0 and order.type == 'limit':
            if order.tif == 'FOK':
                return
            if order.tif == 'IOC':
                return
            best_ask = self.order_book.get_best_ask()
            if order.post_only and best_ask is not None and order.price >= best_ask:
                return
            self.order_book.add_order(order)

    def _match_sell_order(self, order: Order) -> None:
        # For market orders, treat limit as zero to cross all available bids
        effective_limit = order.price if order.type == 'limit' else 0.0
        filled_any = False
        while order.quantity > 0 and self.order_book.get_best_bid() is not None:
            best_bid_price = self.order_book.get_best_bid()
            logging.info(f"Best bid price: {best_bid_price}, Incoming sell order price: {order.price}")
            if best_bid_price is not None and effective_limit <= best_bid_price:
                logging.info(f"Executing sell order at price {best_bid_price}")
                order = self._execute_order(order, best_bid_price, 'buy')
                filled_any = True
            else:
                break
        # TIF and POST-ONLY handling
        if order.quantity > 0 and order.type == 'limit':
            if order.tif == 'FOK':
                return
            if order.tif == 'IOC':
                return
            best_bid = self.order_book.get_best_bid()
            if order.post_only and best_bid is not None and order.price <= best_bid:
                return
            self.order_book.add_order(order)

    def _apply_slippage(self, side: str, base_price: float, quantity: int) -> float:
        if self.slippage_bps_per_100_shares <= 0:
            return base_price
        # Linear scaling by quantity with 100 shares as unit
        units = max(1.0, quantity / 100.0)
        bps = self.slippage_bps_per_100_shares * units
        sign = 1.0 if side == 'buy' else -1.0
        adj = base_price * (1.0 + sign * (bps / 10000.0))
        return float(adj)

    def _execute_order(self, order: Order, price: float, counter_side: str) -> Order:
        """Execute against the top-of-book at price, returning possibly reduced incoming order.

        This updates the order book queues and order_map consistently and supports partial fills.
        """
        counter_orders = self.order_book.asks if counter_side == 'sell' else self.order_book.bids
        queue = counter_orders.get(price)
        if queue is None:
            return order

        while order.quantity > 0 and queue:
            resting = queue[0]
            # Self-trade prevention: skip resting if same owner
            if hasattr(order, 'owner_id') and hasattr(resting, 'owner_id') and order.owner_id == resting.owner_id:
                # move resting to back to try next
                queue.rotate(-1)
                # If full rotation leads back to same resting, break
                if queue and queue[0] == resting:
                    break
                continue
            # Expiry check for resting order
            if getattr(resting, 'expires_at', None) is not None and pd.Timestamp.utcnow().tz_localize('UTC') >= pd.to_datetime(resting.expires_at):
                # remove expired resting order from book
                queue.popleft()
                try:
                    del self.order_book.order_map[resting.id]
                except KeyError:
                    pass
                continue
            if resting.quantity > order.quantity:
                # Incoming is fully filled; reduce resting and keep it at the front
                remaining_qty = resting.quantity - order.quantity
                updated_resting = resting
                updated_resting.quantity = remaining_qty
                # Replace front of queue
                queue.popleft()
                queue.appendleft(updated_resting)
                # Update map
                self.order_book.order_map[resting.id] = updated_resting
                trade_price = self._apply_slippage(order.side, price, order.quantity)
                logging.info(f"Filled {order.quantity} against {resting.id} at {trade_price}; resting left {remaining_qty}")
                execu = Execution(
                    trade_id=uuid.uuid4().hex,
                    price=trade_price,
                    quantity=order.quantity,
                    taker_order_id=order.id,
                    maker_order_id=resting.id,
                    symbol=resting.symbol,
                    side=order.side,
                    timestamp=pd.Timestamp.utcnow().tz_localize('UTC'),
                    taker_owner_id=getattr(order, 'owner_id', None),
                    maker_owner_id=getattr(resting, 'owner_id', None),
                )
                self._emit_trade(execu)
                order.quantity = 0
            else:
                # Resting fully consumed (or equal)
                consumed = resting.quantity
                queue.popleft()
                if resting.id in self.order_book.order_map:
                    del self.order_book.order_map[resting.id]
                trade_price = self._apply_slippage(order.side, price, consumed)
                execu = Execution(
                    trade_id=uuid.uuid4().hex,
                    price=trade_price,
                    quantity=consumed,
                    taker_order_id=order.id,
                    maker_order_id=resting.id,
                    symbol=resting.symbol,
                    side=order.side,
                    timestamp=pd.Timestamp.utcnow().tz_localize('UTC'),
                    taker_owner_id=getattr(order, 'owner_id', None),
                    maker_owner_id=getattr(resting, 'owner_id', None),
                )
                self._emit_trade(execu)
                order.quantity = order.quantity - consumed
                logging.info(f"Consumed resting {resting.id} qty {consumed} at {price}; incoming left {order.quantity}")

        # Remove empty price level if queue depleted
            if not queue:
                try:
                    del counter_orders[price]
                except KeyError:
                    pass
            # Keep sorted price lists in sync
            try:
                if counter_side == 'sell':
                    self.order_book._ask_prices.remove(price)
                else:
                    self.order_book._bid_prices.remove(price)
            except ValueError:
                pass
        return order


# --------------------------------------------------------------------------------------
# Executions and Portfolio
# --------------------------------------------------------------------------------------

@dataclass
class Execution:
    trade_id: str
    price: float
    quantity: int
    taker_order_id: str
    maker_order_id: str
    symbol: str
    side: str  # side of the taker
    timestamp: pd.Timestamp
    taker_owner_id: Optional[str] = None
    maker_owner_id: Optional[str] = None


class Portfolio:
    """Owner-aware portfolio/PnL tracker with per-symbol positions and fees.

    Applies taker fees when this portfolio is the taker on an execution, and maker
    rebates when this portfolio is the maker on an execution. Positions and cash
    are updated from this owner's perspective only.
    """

    def __init__(self, initial_cash: float = 1_000_000.0, fee_bps: float = 0.0, maker_rebate_bps: float = 0.0,
                 owner_id: str = "default") -> None:
        self.cash: float = float(initial_cash)
        self.fee_bps: float = float(fee_bps)
        self.maker_rebate_bps: float = float(maker_rebate_bps)
        self.owner_id: str = str(owner_id)
        self.positions: Dict[str, int] = {}
        self.avg_price: Dict[str, float] = {}
        self.realized_pnl: float = 0.0
        self._lock = threading.RLock()

    def _apply_fee(self, notional: float) -> float:
        return abs(notional) * (self.fee_bps / 10_000.0)

    def on_execution(self, execu: Execution) -> None:
        with self._lock:
            # Determine the role of this portfolio in the execution
            is_taker = (execu.taker_owner_id == self.owner_id)
            is_maker = (execu.maker_owner_id == self.owner_id)
            if not is_taker and not is_maker:
                return
            # Compute side from this owner's perspective
            if is_taker:
                eff_side = execu.side
            else:
                eff_side = 'sell' if execu.side == 'buy' else 'buy'

            qty = execu.quantity if eff_side == 'buy' else -execu.quantity
            symbol = execu.symbol
            price = execu.price
            # Fees: taker fee applies only if taker; maker rebate only if maker
            fees = 0.0
            if is_taker and self.fee_bps != 0.0:
                fees += self._apply_fee(price * execu.quantity)
            if is_maker and self.maker_rebate_bps != 0.0:
                fees -= abs(price * execu.quantity) * (self.maker_rebate_bps / 10_000.0)

            prev_pos = self.positions.get(symbol, 0)
            new_pos = prev_pos + qty
            # Cash moves opposite to buy quantity
            self.cash -= qty * price
            self.cash -= fees

            # Realized PnL when crossing through zero or reducing position
            if prev_pos == 0 or (prev_pos > 0 and qty > 0) or (prev_pos < 0 and qty < 0):
                # Increasing position in same direction: update average price
                total_qty = abs(prev_pos) + abs(qty)
                if total_qty != 0:
                    prev_avg = self.avg_price.get(symbol, 0.0)
                    if abs(prev_pos) == 0:
                        new_avg = price
                else:
                        new_avg = (prev_avg * abs(prev_pos) + price * abs(qty)) / total_qty
                        self.avg_price[symbol] = new_avg
            else:
                # Closing or flipping: realize PnL on the closed portion
                close_qty = min(abs(prev_pos), abs(qty))
                sign = 1 if prev_pos > 0 else -1
                entry = self.avg_price.get(symbol, price)
                pnl = (price - entry) * (close_qty * sign)
                self.realized_pnl += pnl
                # If flipped, set new avg to current price for the residual
                if abs(qty) > abs(prev_pos):
                    self.avg_price[symbol] = price

            self.positions[symbol] = new_pos

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return {
                'cash': self.cash,
                'positions': dict(self.positions),
                'avg_price': dict(self.avg_price),
                'realized_pnl': self.realized_pnl,
            }


# --------------------------------------------------------------------------------------
# Portfolio Dispatcher (owner -> Portfolio)
# --------------------------------------------------------------------------------------

class PortfolioDispatcher:
    """Thread-safe dispatcher that routes executions to owner-specific portfolios.

    All portfolios use the same fee and rebate configuration unless overridden when created.
    """

    def __init__(self, fee_bps: float = 0.0, maker_rebate_bps: float = 0.0) -> None:
        self._lock = threading.RLock()
        self._portfolios: Dict[str, Portfolio] = {}
        self._default_fee_bps = float(fee_bps)
        self._default_maker_rebate_bps = float(maker_rebate_bps)

    def ensure(self, owner_id: str, initial_cash: float = 0.0, fee_bps: Optional[float] = None,
               maker_rebate_bps: Optional[float] = None) -> Portfolio:
        with self._lock:
            if owner_id in self._portfolios:
                return self._portfolios[owner_id]
            pf = Portfolio(
                initial_cash=float(initial_cash),
                fee_bps=float(self._default_fee_bps if fee_bps is None else fee_bps),
                maker_rebate_bps=float(self._default_maker_rebate_bps if maker_rebate_bps is None else maker_rebate_bps),
                owner_id=owner_id,
            )
            self._portfolios[owner_id] = pf
            return pf

    def get_portfolio(self, owner_id: str) -> Optional[Portfolio]:
        with self._lock:
            return self._portfolios.get(owner_id)

    def on_execution(self, execu: Execution) -> None:
        taker_owner = execu.taker_owner_id or ""
        maker_owner = execu.maker_owner_id or ""
        # Route to taker and maker portfolios if present, creating if needed with default cash 0
        if taker_owner:
            self.ensure(taker_owner).on_execution(execu)
        if maker_owner and maker_owner != taker_owner:
            self.ensure(maker_owner).on_execution(execu)

    def snapshot_all(self) -> Dict[str, Dict[str, Any]]:
        with self._lock:
            return {oid: pf.snapshot() for oid, pf in self._portfolios.items()}

# --------------------------------------------------------------------------------------
# Risk Manager
# --------------------------------------------------------------------------------------

class RiskManager:
    """Basic pre-trade risk checks: max order size, per-symbol exposure, and max gross notional.

    Integrates with Portfolio to check exposures at the time of order entry.
    """

    def __init__(self, portfolio: Portfolio, max_order_qty: int, max_symbol_position: int, max_gross_notional: float,
                 min_order_qty: int = 1, lot_size: int = 1, round_lot_required: bool = False,
                 order_rate_limit_per_sec: Optional[int] = None,
                 owner_drawdown_limit: Optional[float] = None,
                 owner_portfolios: Optional["PortfolioDispatcher"] = None,
                 price_provider: Optional[Callable[[str], Optional[float]]] = None) -> None:
        self.portfolio = portfolio
        self.max_order_qty = int(max_order_qty)
        self.max_symbol_position = int(max_symbol_position)
        self.max_gross_notional = float(max_gross_notional)
        self.min_order_qty = int(max(1, min_order_qty))
        self.lot_size = int(max(1, lot_size))
        self.round_lot_required = bool(round_lot_required)
        # Owner-aware extensions
        self.order_rate_limit_per_sec = int(order_rate_limit_per_sec) if order_rate_limit_per_sec else None
        self._owner_to_timestamps: Dict[str, Deque[float]] = {}
        self.owner_drawdown_limit = float(owner_drawdown_limit) if owner_drawdown_limit is not None else None
        self.owner_portfolios = owner_portfolios
        self.price_provider = price_provider
        self._owner_peak_equity: Dict[str, float] = {}

    def allow_order(self, order: Order) -> bool:
        # Check quantity bounds
        if order.quantity <= 0 or order.quantity > self.max_order_qty:
            return False
        # Min quantity
        if order.quantity < self.min_order_qty:
            return False
        # Round lot checks
        if self.round_lot_required and (order.quantity % self.lot_size != 0):
            return False
        # Estimate notional using order price
        notional = abs(order.quantity * float(order.price))
        if notional > self.max_gross_notional:
            return False
        # Check per-symbol exposure
        pos = self.portfolio.positions.get(order.symbol, 0)
        projected = pos + (order.quantity if order.side == 'buy' else -order.quantity)
        if abs(projected) > self.max_symbol_position:
            return False
        # Rate limit per owner
        if self.order_rate_limit_per_sec is not None:
            owner = getattr(order, 'owner_id', 'default')
            now = time.time()
            dq = self._owner_to_timestamps.get(owner)
            if dq is None:
                dq = deque()
                self._owner_to_timestamps[owner] = dq
            dq.append(now)
            # prune older than 1s
            one_sec_ago = now - 1.0
            while dq and dq[0] < one_sec_ago:
                dq.popleft()
            if len(dq) > self.order_rate_limit_per_sec:
                return False
        # Drawdown kill switch per owner (based on simple equity calc)
        if self.owner_drawdown_limit is not None and self.owner_portfolios is not None and self.price_provider is not None:
            owner = getattr(order, 'owner_id', 'default')
            pf = self.owner_portfolios.get_portfolio(owner)
            if pf is not None:
                # Estimate equity = cash + sum(pos * price)
                equity = float(pf.cash)
                try:
                    for sym, qty in pf.positions.items():
                        px = self.price_provider(sym)
                        if px is not None:
                            equity += float(qty) * float(px)
                except Exception:
                    pass
                peak = self._owner_peak_equity.get(owner, equity)
                if equity > peak:
                    peak = equity
                    self._owner_peak_equity[owner] = peak
                dd = 0.0 if peak <= 0 else (peak - equity) / peak
                if dd > self.owner_drawdown_limit:
                    return False
        return True


# --------------------------------------------------------------------------------------
# CSV Logging
# --------------------------------------------------------------------------------------

class CsvLogger:
    """Append-only CSV logger for executions and equity curve."""

    def __init__(self, base_dir: str) -> None:
        self.base_dir = base_dir
        os.makedirs(self.base_dir, exist_ok=True)
        self.exec_path = os.path.join(self.base_dir, 'executions.csv')
        self.equity_path = os.path.join(self.base_dir, 'equity_curve.csv')
        self.tca_path = os.path.join(self.base_dir, 'tca.csv')
        # Initialize headers if files do not exist
        if not os.path.exists(self.exec_path):
            with open(self.exec_path, 'w', encoding='utf-8') as f:
                f.write('timestamp,symbol,price,quantity,side,taker_order_id,maker_order_id,trade_id\n')
        if not os.path.exists(self.equity_path):
            with open(self.equity_path, 'w', encoding='utf-8') as f:
                f.write('timestamp,net_liquidation,realized_pnl,cash\n')
        if not os.path.exists(self.tca_path):
            with open(self.tca_path, 'w', encoding='utf-8') as f:
                f.write('timestamp,symbol,side,price,mid,last_trade,slippage_mid_bps,slippage_last_bps\n')

    def log_execution(self, execu: Execution) -> None:
        try:
            with open(self.exec_path, 'a', encoding='utf-8') as f:
                f.write(
                    f"{execu.timestamp.isoformat()},{execu.symbol},{execu.price},{execu.quantity},{execu.side},{execu.taker_order_id},{execu.maker_order_id},{execu.trade_id}\n"
                )
        except Exception as exc:
            logging.warning("Failed to write execution log: %s", exc)

    def log_equity(self, timestamp: pd.Timestamp, net_liq: float, realized: float, cash: float) -> None:
        try:
            with open(self.equity_path, 'a', encoding='utf-8') as f:
                f.write(f"{timestamp.isoformat()},{net_liq},{realized},{cash}\n")
        except Exception as exc:
            logging.warning("Failed to write equity log: %s", exc)

    def log_tca(self, timestamp: pd.Timestamp, symbol: str, side: str, price: float, mid: Optional[float], last_trade: Optional[float],
                slip_mid_bps: Optional[float], slip_last_bps: Optional[float]) -> None:
        try:
            with open(self.tca_path, 'a', encoding='utf-8') as f:
                f.write(f"{timestamp.isoformat()},{symbol},{side},{price},{'' if mid is None else mid},{'' if last_trade is None else last_trade},{'' if slip_mid_bps is None else slip_mid_bps},{'' if slip_last_bps is None else slip_last_bps}\n")
        except Exception as exc:
            logging.debug("Failed to write TCA log: %s", exc)


class EventLogger:
    """Append-only CSV event logger for orders/cancels/executions for replay."""

    def __init__(self, base_dir: str) -> None:
        self.base_dir = base_dir
        os.makedirs(self.base_dir, exist_ok=True)
        self.events_path = os.path.join(self.base_dir, 'events.csv')
        if not os.path.exists(self.events_path):
            with open(self.events_path, 'w', encoding='utf-8') as f:
                f.write('timestamp,event,order_id,symbol,side,type,price,quantity,extra\n')

    def log_new_order(self, order: Order) -> None:
        try:
            with open(self.events_path, 'a', encoding='utf-8') as f:
                f.write(f"{pd.Timestamp.utcnow().tz_localize('UTC').isoformat()},NEW,{order.id},{order.symbol},{order.side},{order.type},{order.price},{order.quantity},owner={getattr(order,'owner_id','')}\n")
        except Exception as exc:
            logging.debug("Event log (new) skipped: %s", exc)

    def log_cancel(self, order_id: str) -> None:
        try:
            with open(self.events_path, 'a', encoding='utf-8') as f:
                f.write(f"{pd.Timestamp.utcnow().tz_localize('UTC').isoformat()},CANCEL,{order_id},,,,,,\n")
        except Exception as exc:
            logging.debug("Event log (cancel) skipped: %s", exc)

    def log_execution(self, execu: "Execution", best_bid: Optional[float] = None, best_ask: Optional[float] = None) -> None:
        try:
            with open(self.events_path, 'a', encoding='utf-8') as f:
                extra = []
                if best_bid is not None:
                    extra.append(f"bb={best_bid}")
                if best_ask is not None:
                    extra.append(f"ba={best_ask}")
                extra.append(f"maker={execu.maker_order_id}")
                f.write(f"{execu.timestamp.isoformat()},EXEC,{execu.taker_order_id},{execu.symbol},{execu.side},,{execu.price},{execu.quantity},{' '.join(extra)}\n")
        except Exception as exc:
            logging.debug("Event log (exec) skipped: %s", exc)

    def replay(self) -> List[Dict[str, Any]]:
        events: List[Dict[str, Any]] = []
        try:
            with open(self.events_path, 'r', encoding='utf-8') as f:
                next(f, None)  # skip header
                for line in f:
                    parts = line.strip().split(',')
                    if len(parts) < 3:
                        continue
                    ts, ev, oid = parts[0], parts[1], parts[2]
                    events.append({
                        'timestamp': ts,
                        'event': ev,
                        'order_id': oid,
                        'raw': parts,
                    })
        except Exception:
            pass
        return events

if SQLA_AVAILABLE:
    Base = declarative_base()

    class ExecutionORM(Base):
        __tablename__ = 'executions'
        trade_id = Column(String, primary_key=True)
        timestamp = Column(DateTime(timezone=True), index=True)
        symbol = Column(String, index=True)
        price = Column(Float)
        quantity = Column(Integer)
        side = Column(String)
        taker_order_id = Column(String)
        maker_order_id = Column(String)

    class EquityORM(Base):
        __tablename__ = 'equity_curve'
        id = Column(Integer, primary_key=True, autoincrement=True)
        timestamp = Column(DateTime(timezone=True), index=True)
        net_liquidation = Column(Float)
        realized_pnl = Column(Float)
        cash = Column(Float)

    class ConfigORM(Base):
        __tablename__ = 'configs'
        key = Column(String, primary_key=True)
        value = Column(Text)

    class DbLogger:
        def __init__(self, db_uri: str) -> None:
            self.engine = create_engine(db_uri, future=True)
            Base.metadata.create_all(self.engine)
            self.Session = sessionmaker(bind=self.engine, autoflush=False, autocommit=False)

        def log_execution(self, execu: Execution) -> None:
            try:
                with self.Session() as s:
                    s.add(ExecutionORM(
                        trade_id=execu.trade_id,
                        timestamp=execu.timestamp.to_pydatetime() if hasattr(execu.timestamp, 'to_pydatetime') else execu.timestamp,
                        symbol=execu.symbol,
                        price=float(execu.price),
                        quantity=int(execu.quantity),
                        side=str(execu.side),
                        taker_order_id=execu.taker_order_id,
                        maker_order_id=execu.maker_order_id,
                    ))
                    s.commit()
            except Exception as exc:
                logging.warning("DB execution log failed: %s", exc)

        def log_equity(self, timestamp: pd.Timestamp, net_liq: float, realized: float, cash: float) -> None:
            try:
                with self.Session() as s:
                    s.add(EquityORM(
                        timestamp=timestamp.to_pydatetime() if hasattr(timestamp, 'to_pydatetime') else timestamp,
                        net_liquidation=float(net_liq),
                        realized_pnl=float(realized),
                        cash=float(cash),
                    ))
                    s.commit()
            except Exception as exc:
                logging.warning("DB equity log failed: %s", exc)


# --------------------------------------------------------------------------------------
# Mark-to-Market helper
# --------------------------------------------------------------------------------------

def mark_to_market(portfolio: Portfolio, last_prices: Dict[str, float]) -> float:
    """Compute net liquidation value from cash + mark-to-market of current positions."""
    net = portfolio.cash
    for symbol, qty in portfolio.positions.items():
        if symbol in last_prices:
            net += qty * float(last_prices[symbol])
    return float(net)


# --------------------------------------------------------------------------------------
# Performance analytics and reporting
# --------------------------------------------------------------------------------------

def _load_equity_curve(csv_path: str) -> pd.DataFrame:
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"Equity curve file not found: {csv_path}")
    df = pd.read_csv(csv_path)
    if 'timestamp' not in df.columns or 'net_liquidation' not in df.columns:
        raise RuntimeError("Equity CSV missing required columns")
    df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True, errors='coerce')
    df = df.dropna(subset=['timestamp']).sort_values('timestamp').reset_index(drop=True)
    return df


def compute_performance_metrics(equity_df: pd.DataFrame) -> Dict[str, float]:
    metrics: Dict[str, float] = {}
    if equity_df.empty:
        return metrics
    series = equity_df.set_index('timestamp')['net_liquidation'].astype(float)
    initial = float(series.iloc[0])
    final = float(series.iloc[-1])
    metrics['initial'] = initial
    metrics['final'] = final
    # Resample to daily to avoid intraday noise
    daily = series.resample('1D').last().dropna()
    if len(daily) >= 2:
        returns = daily.pct_change().dropna()
        if not returns.empty:
            # Annualization assuming 252 trading days
            mean = float(returns.mean())
            std = float(returns.std(ddof=0))
            downside = returns[returns < 0]
            downside_std = float(downside.std(ddof=0)) if not downside.empty else 0.0
            metrics['sharpe'] = (mean / std * np.sqrt(252.0)) if std > 0 else 0.0
            metrics['sortino'] = (mean / downside_std * np.sqrt(252.0)) if downside_std > 0 else 0.0
        # CAGR
        num_days = (daily.index[-1] - daily.index[0]).days or 1
        years = num_days / 365.25
        metrics['cagr'] = (final / initial) ** (1.0 / years) - 1.0 if initial > 0 and years > 0 else 0.0
        # Max drawdown
        roll_max = daily.cummax()
        drawdown = (daily / roll_max - 1.0)
        metrics['max_drawdown'] = float(drawdown.min())
    else:
        metrics.update({'sharpe': 0.0, 'sortino': 0.0, 'cagr': 0.0, 'max_drawdown': 0.0})
    return metrics


def export_html_report(equity_df: pd.DataFrame, metrics: Dict[str, float], output_path: str) -> None:
    labels = [ts.isoformat() for ts in equity_df['timestamp']]
    values = [float(v) for v in equity_df['net_liquidation']]
    rows = ''.join(
        f"<tr><td>{k}</td><td>{v:.6f}</td></tr>" for k, v in metrics.items()
    )
    html = f"""
<!doctype html>
<html><head>
  <meta charset='utf-8'/>
  <title>Performance Report</title>
  <script src='https://cdn.jsdelivr.net/npm/chart.js'></script>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 24px; }}
    .row {{ display: flex; gap: 24px; }}
    .col {{ flex: 1; }}
    table {{ border-collapse: collapse; width: 100%; }}
    th, td {{ border: 1px solid #ddd; padding: 6px; }}
    th {{ background: #f2f2f2; }}
  </style>
</head>
<body>
  <h2>Performance Report</h2>
  <div class='row'>
    <div class='col'>
      <h3>Equity Curve</h3>
      <canvas id='eq'></canvas>
    </div>
    <div class='col'>
      <h3>Metrics</h3>
      <table><thead><tr><th>Metric</th><th>Value</th></tr></thead><tbody>
        {rows}
      </tbody></table>
    </div>
  </div>
  <script>
    const labels = {labels};
    const data = {values};
    const ctx = document.getElementById('eq').getContext('2d');
    new Chart(ctx, {{ type: 'line', data: {{ labels, datasets: [{{ label: 'Net Liq', data, borderColor: '#1976d2', fill: false }}] }}, options: {{ responsive: true, scales: {{ x: {{ display: false }} }} }} }});
  </script>
</body></html>
"""
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)


def objective_optuna(trial: "optuna.trial.Trial", symbol: str, start: str, end: str, base_params: Dict[str, Any], log_dir: str) -> float:
    # Sample parameters (example for EMA & momentum)
    short_window = trial.suggest_int('short_window', 3, 20)
    long_window = trial.suggest_int('long_window', max(short_window + 1, 10), 60)
    lookback = trial.suggest_int('lookback', 3, 20)
    slippage = trial.suggest_float('slippage_bps_per_100', 0.0, 5.0)
    latency = trial.suggest_int('latency_ms', 0, 300)

    order_book = OrderBook()
    engine = MatchingEngine(order_book)
    engine.slippage_bps_per_100_shares = slippage
    engine.latency_ms = latency
    portfolio = Portfolio(initial_cash=float(base_params.get('initial_cash', 1_000_000.0)), fee_bps=float(base_params.get('fee_bps', 0.0)))
    logger = CsvLogger(log_dir)
    engine.subscribe_trades(portfolio.on_execution)
    engine.subscribe_trades(logger.log_execution)

    # Risk manager
    engine.risk_manager = RiskManager(
        portfolio=portfolio,
        max_order_qty=int(base_params.get('risk_max_order_qty', 1000)),
        max_symbol_position=int(base_params.get('risk_max_symbol_position', 10_000)),
        max_gross_notional=float(base_params.get('risk_max_gross_notional', 5_000_000.0)),
    )

    data = load_historical_data(symbol, start, end)
    maker = MarketMaker(symbol=symbol, matching_engine=engine)
    traders: List[AlgorithmicTrader] = [
        EMABasedTrader(symbol=symbol, matching_engine=engine, interval=0.0, short_window=short_window, long_window=long_window),
        MomentumTrader(symbol=symbol, matching_engine=engine, interval=0.0, lookback=lookback),
    ]
    run_backtest(data, maker, engine, traders=traders, portfolio=portfolio, csv_logger=logger)
    eq_df = _load_equity_curve(os.path.join(log_dir, 'equity_curve.csv'))
    metrics = compute_performance_metrics(eq_df)
    # MLflow logging (if available)
    if MLFLOW_AVAILABLE:
        try:
            mlflow.log_params({
                'short_window': short_window,
                'long_window': long_window,
                'lookback': lookback,
                'slippage_bps_per_100': slippage,
                'latency_ms': latency,
                'symbol': symbol,
                'start': start,
                'end': end,
            })
            for k, v in metrics.items():
                mlflow.log_metric(k, float(v))
        except Exception:
            pass
    # Optimize for CAGR with drawdown penalty
    score = float(metrics.get('cagr', 0.0)) - 0.1 * abs(float(metrics.get('max_drawdown', 0.0)))
    return score

# --------------------------------------------------------------------------------------
# FIX Application
# --------------------------------------------------------------------------------------
class FixApplication:
    """Simple FIX TCP server using simplefix to receive NewOrder and Cancel messages."""

    def __init__(self, matching_engine: MatchingEngine) -> None:
        self.matching_engine = matching_engine
        self.parser = simplefix.parser.FixParser()
        self.server_socket: Optional[socket.socket] = None
        self.running = False

    def translate_fix_message(self, parsed_msg: List[List[Any]]) -> Dict[str, str]:
        translated_msg: Dict[str, str] = {}
        for field in parsed_msg:
            tag = field[0]
            value = field[1].decode() if isinstance(field[1], (bytes, bytearray)) else str(field[1])
            field_name = FIX_TAGS.get(tag, f"Unknown({tag})")
            if field_name == "Side":
                value = SIDE_MAPPING.get(value, value)
            if field_name == "MsgType":
                value = MSG_TYPE_MAPPING.get(value, value)
            translated_msg[field_name] = value
        return translated_msg

    def handle_new_order(self, translated_msg: Dict[str, str]) -> None:
        order_id = translated_msg["ClOrdID"]
        side_human = translated_msg["Side"]
        side = side_human.lower()
        price = float(translated_msg["Price"])
        quantity = int(translated_msg["OrderQty"])
        symbol = translated_msg.get("Symbol", "UNKNOWN")

        order = Order(id=order_id, price=price, quantity=quantity, side=side, type='limit', symbol=symbol)
        self.matching_engine.match_order(order)
        logging.info(f"New order processed: {order_id} ({side_human} {quantity} {symbol} @ {price})")

    def handle_cancel_order(self, translated_msg: Dict[str, str]) -> None:
        order_id = translated_msg["OrigClOrdID"]
        self.matching_engine.cancel_order(order_id)
        logging.info(f"Cancel order processed for order ID: {order_id}")

    def handle_incoming_message(self, message: bytes) -> None:
        self.parser.append_buffer(message)
        parsed_msg = self.parser.get_message()
        if parsed_msg is None:
            logging.error("Received malformed message.")
            return
        translated_msg = self.translate_fix_message(parsed_msg)
        logging.info(f"Received FIX message: {translated_msg}")
        msg_type = translated_msg.get("MsgType")
        if msg_type == 'NewOrderSingle':
            self.handle_new_order(translated_msg)
        elif msg_type == 'OrderCancelRequest':
            self.handle_cancel_order(translated_msg)
        else:
            logging.warning(f"Unhandled message type: {msg_type}")

    def start(self, host: str = 'localhost', port: int = 5005) -> None:
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((host, port))
        self.server_socket.listen(5)
        self.running = True
        logging.info(f"FIX server started on {host}:{port}. Waiting for connections...")

        while self.running:
            try:
                client_socket, addr = self.server_socket.accept()
                logging.info(f"Connection from {addr}")
                data = client_socket.recv(4096)
                if data:
                    logging.info(f"Received raw data: {data!r}")
                    self.handle_incoming_message(data)
                    client_socket.sendall(b'Ack')
                client_socket.close()
            except OSError:
                if not self.running:
                    logging.info("Server socket closed.")
                else:
                    raise

    def stop(self) -> None:
        self.running = False
        if self.server_socket:
            self.server_socket.close()
            logging.info("FIX server stopped.")

    def create_order_message(self, order: Dict[str, Any]) -> simplefix.FixMessage:
        msg = simplefix.FixMessage()
        msg.append_pair(8, b'FIX.4.2')
        msg.append_pair(35, b'D')  # New Order Single
        msg.append_pair(11, str(order['id']).encode())
        msg.append_pair(54, b'1' if order['side'] == 'buy' else b'2')
        msg.append_pair(55, str(order['symbol']).encode())
        msg.append_pair(44, str(order['price']).encode())
        msg.append_pair(38, str(order['quantity']).encode())
        msg.append_pair(10, b'000')
        return msg

    def send_message(self, msg: simplefix.FixMessage, host: str = 'localhost', port: int = 5005) -> None:
        client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client_socket.connect((host, port))
        client_socket.sendall(msg.encode())
        response = client_socket.recv(1024)
        logging.info(f"Received response: {response.decode(errors='ignore')}")
        client_socket.close()


# --------------------------------------------------------------------------------------
# Market Data Feed
# --------------------------------------------------------------------------------------
class MarketDataFeed:
    """Fetches live market data via yfinance and broadcasts to subscribers every minute."""

    def __init__(self, symbol: str) -> None:
        self.symbol = symbol
        self.subscribers: List[Any] = []
        self.running = False
        self._last_price: Optional[float] = None

    def subscribe(self, client: Any) -> None:
        self.subscribers.append(client)

    def broadcast(self, data: Dict[str, Any]) -> None:
        for client in list(self.subscribers):
            try:
                client.receive(data)
            except Exception as exc:
                logging.exception("Subscriber error: %s", exc)

    def fetch_market_data(self) -> Optional[Dict[str, Any]]:
        try:
            data = _yq_history_with_retry(self.symbol, period="1d", interval="1m", max_retries=4, base_backoff=1.8)
        except Exception as exc:
            logging.warning("MarketDataFeed fetch failed: %s", exc)
            return None
        if data is None or data.empty:
            return None
        latest_data = data.iloc[-1]
        timestamp = latest_data.name
        # Normalize timezone to UTC; if tz-naive, localize to UTC
        try:
            if isinstance(timestamp, pd.Timestamp):
                if timestamp.tzinfo is None:
                    timestamp = timestamp.tz_localize('UTC')
                else:
                    timestamp = timestamp.tz_convert('UTC')
            else:
                timestamp = pd.to_datetime(timestamp, utc=True)
        except Exception:
            timestamp = pd.Timestamp.utcnow().tz_localize('UTC')
        return {
            'symbol': self.symbol,
            'timestamp': timestamp,
            'price': float(latest_data['Close']),
            'volume': int(latest_data.get('Volume', 0)),
        }

    def start(self, interval_seconds: int = 60) -> None:
        self.running = True
        while self.running:
            try:
                market_data = self.fetch_market_data()
                if market_data:
                    self._last_price = float(market_data['price'])
                    self.broadcast(market_data)
            except Exception as exc:
                logging.exception("MarketDataFeed error: %s", exc)
            time.sleep(max(1, int(interval_seconds)))

    def stop(self) -> None:
        self.running = False

    def last_price(self) -> Optional[float]:
        return self._last_price


# --------------------------------------------------------------------------------------
# Market Maker
# --------------------------------------------------------------------------------------
class MarketMaker:
    def __init__(self, symbol: str, matching_engine: MatchingEngine,
                 gamma: float = 0.1, k: float = 1.5, horizon_seconds: float = 60.0,
                 max_inventory: int = 1000, base_order_size: int = 100, min_spread: float = 0.01,
                 num_levels: int = 2, level_spacing_bps: float = 2.0, size_decay: float = 0.7,
                 momentum_window: int = 10, alpha_skew: float = 0.5, vol_widen_z: float = 2.0,
                 drawdown_limit: float = 0.2) -> None:
        self.symbol = symbol
        self.matching_engine = matching_engine
        self.gamma = max(1e-6, float(gamma))
        self.k = max(1e-6, float(k))
        self.horizon_seconds = max(1.0, float(horizon_seconds))
        self.max_inventory = int(max_inventory)
        self.base_order_size = int(max(1, base_order_size))
        self.min_spread = float(max(0.0, min_spread))
        self.num_levels = int(max(1, num_levels))
        self.level_spacing_bps = float(max(0.0, level_spacing_bps))
        self.size_decay = float(min(1.0, max(0.1, size_decay)))
        self.momentum_window = int(max(1, momentum_window))
        self.alpha_skew = float(max(0.0, alpha_skew))
        self.vol_widen_z = float(max(0.0, vol_widen_z))
        self.drawdown_limit = float(max(0.0, drawdown_limit))
        self.price_history: List[float] = []
        self.running = False
        self.inventory: int = 0
        self.current_bid_ids: List[str] = []
        self.current_ask_ids: List[str] = []
        self.order_id_to_side: Dict[str, str] = {}
        # PnL/Equity tracking for kill switch (MM-local, unrealized only)
        self.peak_equity: float = 0.0
        self.last_mid: Optional[float] = None

    def _estimate_sigma(self, window: int = 60) -> float:
        # Simple realized volatility estimate based on recent returns
        if len(self.price_history) < max(3, window):
            return 0.0
        arr = np.array(self.price_history[-window:], dtype=float)
        rets = np.diff(np.log(arr + 1e-12))
        sigma = float(np.std(rets))
        return sigma

    def _compute_quotes(self, mid: float) -> Tuple[float, float, int, int]:
        # Avellaneda-Stoikov inspired quoting
        sigma = self._estimate_sigma()
        T = self.horizon_seconds
        gamma = self.gamma
        k = self.k
        # Reservation price adjusted for inventory
        reservation = mid - self.inventory * gamma * (sigma ** 2) * (T)
        # Momentum skew: use recent price momentum to tilt reservation toward current drift
        if len(self.price_history) >= self.momentum_window:
            recent = self.price_history[-self.momentum_window:]
            mom = recent[-1] - recent[0]
            direction = 1.0 if mom > 0 else (-1.0 if mom < 0 else 0.0)
            reservation += direction * self.alpha_skew * self.min_spread
        # Optimal half-spread
        try:
            half_spread = (gamma * (sigma ** 2) * T) / 2.0 + (1.0 / gamma) * math.log(1.0 + (gamma / k))
        except Exception:
            half_spread = self.min_spread
        half_spread = float(max(self.min_spread, half_spread))
        # Volatility widening under extreme z-score of returns
        if len(self.price_history) >= max(5, self.momentum_window):
            arr = np.array(self.price_history[-self.momentum_window:], dtype=float)
            rets = np.diff(arr)
            if rets.size > 1:
                z = 0.0
                try:
                    z = float((rets[-1] - rets.mean()) / (rets.std(ddof=0) + 1e-12))
                except Exception:
                    z = 0.0
                widen = 1.0 + max(0.0, abs(z) - self.vol_widen_z) * 0.25
                half_spread *= widen
        bid = max(0.0, reservation - half_spread)
        ask = max(bid + self.min_spread, reservation + half_spread)
        # Inventory-aware sizing
        inv_ratio = min(1.0, abs(self.inventory) / float(max(1, self.max_inventory)))
        size_factor = max(0.2, 1.0 - inv_ratio)
        buy_size = int(max(1, round(self.base_order_size * (size_factor if self.inventory > 0 else 1.0))))
        sell_size = int(max(1, round(self.base_order_size * (size_factor if self.inventory < 0 else 1.0))))
        return bid, ask, buy_size, sell_size

    def _cancel_existing_quotes(self) -> None:
        ob = self.matching_engine.order_book
        for oid in self.current_bid_ids:
            ob.cancel_order(oid)
            self.order_id_to_side.pop(oid, None)
        for oid in self.current_ask_ids:
            ob.cancel_order(oid)
            self.order_id_to_side.pop(oid, None)
        self.current_bid_ids = []
        self.current_ask_ids = []

    def _post_quote(self, side: str, price: float, qty: int) -> str:
        order_id = uuid.uuid4().hex
        order = Order(id=order_id, price=float(price), quantity=int(qty), side=side, type='limit', symbol=self.symbol, owner_id='mm')
        # Place as resting order on the book
        self.matching_engine.order_book.add_order(order)
        self.order_id_to_side[order_id] = side
        return order_id

    def on_market_data(self, data: Dict[str, Any]) -> None:
        if data['symbol'] != self.symbol:
            return
        mid = float(data['price'])
        self.price_history.append(mid)
        self.last_mid = mid
        # MM-local equity and kill switch
        equity = self.inventory * mid
        self.peak_equity = max(self.peak_equity, equity)
        if self.peak_equity > 0:
            drawdown = (self.peak_equity - equity) / self.peak_equity
            if drawdown > self.drawdown_limit:
                # Pull quotes and stop quoting until equity recovers (simple behavior)
                self._cancel_existing_quotes()
                logging.warning("MM %s kill-switch active: drawdown=%.2f%%", self.symbol, drawdown * 100.0)
                return
        # Refresh quotes
        self._cancel_existing_quotes()
        bid, ask, buy_size, sell_size = self._compute_quotes(mid)
        # Multi-level laddering
        self.current_bid_ids = []
        self.current_ask_ids = []
        for i in range(self.num_levels):
            decay = self.size_decay ** i
            level_size_bid = max(1, int(round(buy_size * decay)))
            level_size_ask = max(1, int(round(sell_size * decay)))
            step = (self.level_spacing_bps / 10000.0) * (i)
            bid_i = max(0.0, bid - mid * step)
            ask_i = max(bid_i + self.min_spread, ask + mid * step)
            self.current_bid_ids.append(self._post_quote('buy', bid_i, level_size_bid))
            self.current_ask_ids.append(self._post_quote('sell', ask_i, level_size_ask))
        logging.info("MM %s quotes: bid=%.4f... ask=%.4f... levels=%d inv=%d", self.symbol, bid, ask, self.num_levels, self.inventory)

    def on_execution(self, execu: Execution) -> None:
        # Update inventory if our resting order was the maker in this trade
        if execu.symbol != self.symbol:
            return
        if execu.maker_order_id in self.order_id_to_side:
            side = self.order_id_to_side.get(execu.maker_order_id)
            qty = int(execu.quantity)
            if side == 'buy':
                self.inventory += qty
            elif side == 'sell':
                self.inventory -= qty
            # After a fill, rely on next market data tick to refresh quotes

    def start(self, feed: MarketDataFeed) -> None:
        self.running = True
        feed.subscribe(self)

    def stop(self) -> None:
        self.running = False

    def receive(self, data: Dict[str, Any]) -> None:
        self.on_market_data(data)


# --------------------------------------------------------------------------------------
# Synthetic Liquidity Provider
# --------------------------------------------------------------------------------------
class SyntheticLiquidityProvider:
    def __init__(self, symbol: str, matching_engine: MatchingEngine, num_orders: int = 10) -> None:
        self.symbol = symbol
        self.matching_engine = matching_engine
        self.num_orders = num_orders

    def generate_liquidity(self) -> None:
        try:
            data = _yq_history_with_retry(self.symbol, period="1d", interval="1m", max_retries=4, base_backoff=1.8)
        except Exception as exc:
            logging.warning("SyntheticLiquidityProvider fetch failed: %s", exc)
            return
        if data is None or data.empty:
            return
        latest_data = data.iloc[-1]
        price = float(latest_data['Close'])
        for _ in range(self.num_orders):
            side = 'buy' if random.random() < 0.5 else 'sell'
            order = Order(
                id=uuid.uuid4().hex,
                price=price,
                quantity=random.randint(10, 100),
                side=side,
                type='limit',
                symbol=self.symbol,
            )
            self.matching_engine.match_order(order)
            logging.info(f"Synthetic liquidity added: {side} order at {price}")


def auto_inject_liquidity(provider: SyntheticLiquidityProvider, interval_seconds: int) -> None:
    while True:
        try:
            provider.generate_liquidity()
        except Exception as exc:
            logging.exception("Liquidity injection error: %s", exc)
        time.sleep(max(1, int(interval_seconds)))


# --------------------------------------------------------------------------------------
# Algorithmic Traders
# --------------------------------------------------------------------------------------
class AlgorithmicTrader:
    def __init__(self, symbol: str, matching_engine: MatchingEngine, interval: float = 0.1) -> None:
        self.symbol = symbol
        self.matching_engine = matching_engine
        self.interval = interval
        self.running = False
        self.current_price: Optional[float] = None

    def start(self, feed: MarketDataFeed) -> None:
        self.running = True
        feed.subscribe(self)
        while self.running:
            try:
                self.trade()
            except Exception as exc:
                logging.exception("Trader error: %s", exc)
            time.sleep(self.interval)

    def stop(self) -> None:
        self.running = False

    def trade(self) -> None:  # to be overridden
        pass

    def receive(self, data: Dict[str, Any]) -> None:
        if data['symbol'] == self.symbol:
            self.on_market_data(data)

    def on_market_data(self, data: Dict[str, Any]) -> None:
        self.current_price = float(data['price'])
        self.handle_market_data(data)

    def handle_market_data(self, data: Dict[str, Any]) -> None:  # to be overridden
        pass


class MomentumTrader(AlgorithmicTrader):
    def __init__(self, symbol: str, matching_engine: MatchingEngine, interval: float = 0.1, lookback: int = 5) -> None:
        super().__init__(symbol, matching_engine, interval)
        self.lookback = lookback
        self.prices: List[float] = []

    def handle_market_data(self, data: Dict[str, Any]) -> None:
        if self.current_price is not None:
            self.prices.append(self.current_price)
            if len(self.prices) > self.lookback:
                self.prices.pop(0)

    def trade(self) -> None:
        if len(self.prices) < self.lookback or self.current_price is None:
            return
        price_change = self.prices[-1] - self.prices[0]
        if price_change > 0:
            order = Order(id=uuid.uuid4().hex, price=self.current_price, quantity=100, side='buy', type='limit', symbol=self.symbol, owner_id='momentum')
            self.matching_engine.match_order(order)
            logging.info(f"MomentumTrader placed a buy order at {self.current_price}")
        elif price_change < 0:
            order = Order(id=uuid.uuid4().hex, price=self.current_price, quantity=100, side='sell', type='limit', symbol=self.symbol, owner_id='momentum')
            self.matching_engine.match_order(order)
            logging.info(f"MomentumTrader placed a sell order at {self.current_price}")


class EMABasedTrader(AlgorithmicTrader):
    def __init__(self, symbol: str, matching_engine: MatchingEngine, interval: float = 0.1, short_window: int = 5, long_window: int = 20) -> None:
        super().__init__(symbol, matching_engine, interval)
        self.short_window = short_window
        self.long_window = long_window
        self.prices: List[float] = []

    def handle_market_data(self, data: Dict[str, Any]) -> None:
        if self.current_price is not None:
            self.prices.append(self.current_price)
            if len(self.prices) > self.long_window:
                self.prices.pop(0)

    def trade(self) -> None:
        if len(self.prices) < self.long_window or self.current_price is None:
            return
        short_ema = self._calculate_ema(self.short_window)
        long_ema = self._calculate_ema(self.long_window)
        if short_ema > long_ema:
            order = Order(id=uuid.uuid4().hex, price=self.current_price, quantity=100, side='buy', type='limit', symbol=self.symbol, owner_id='ema')
            self.matching_engine.match_order(order)
            logging.info(f"EMABasedTrader placed a buy order at {self.current_price}")
        elif short_ema < long_ema:
            order = Order(id=uuid.uuid4().hex, price=self.current_price, quantity=100, side='sell', type='limit', symbol=self.symbol, owner_id='ema')
            self.matching_engine.match_order(order)
            logging.info(f"EMABasedTrader placed a sell order at {self.current_price}")

    def _calculate_ema(self, window: int) -> float:
        weights = np.exp(np.linspace(-1.0, 0.0, window))
        weights /= weights.sum()
        a = np.convolve(self.prices, weights, mode='valid')
        return float(a[-1])


class SwingTrader(AlgorithmicTrader):
    def __init__(self, symbol: str, matching_engine: MatchingEngine, interval: float = 0.1, support_level: float = 100.0, resistance_level: float = 200.0) -> None:
        super().__init__(symbol, matching_engine, interval)
        self.support_level = support_level
        self.resistance_level = resistance_level

    def trade(self) -> None:
        if self.current_price is None:
            return
        if self.current_price <= self.support_level:
            order = Order(id=uuid.uuid4().hex, price=self.current_price, quantity=100, side='buy', type='limit', symbol=self.symbol, owner_id='swing')
            self.matching_engine.match_order(order)
            logging.info(f"SwingTrader placed a buy order at {self.current_price}")
        elif self.current_price >= self.resistance_level:
            order = Order(id=uuid.uuid4().hex, price=self.current_price, quantity=100, side='sell', type='limit', symbol=self.symbol, owner_id='swing')
            self.matching_engine.match_order(order)
            logging.info(f"SwingTrader placed a sell order at {self.current_price}")

    def handle_market_data(self, data: Dict[str, Any]) -> None:
        self.current_price = float(data['price'])


class NewsFetcher:
    def __init__(self, api_key: str, timeout_seconds: int = 10, max_retries: int = 3) -> None:
        self.newsapi = NewsApiClient(api_key=api_key)
        self.timeout_seconds = max(1, int(timeout_seconds))
        self.max_retries = max(1, int(max_retries))

    def fetch_latest_news(self, query: str = 'stock market') -> List[str]:
        last_exc: Optional[Exception] = None
        for attempt in range(self.max_retries):
            try:
                all_articles = self.newsapi.get_everything(
                    q=query,
                    language='en',
                    sort_by='publishedAt',
                    page_size=5,
                            timeout=self.timeout_seconds,
                )
                headlines = [article['title'] for article in all_articles.get('articles', [])]
                return headlines
            except Exception as exc:
                last_exc = exc
                backoff = 1.5 ** attempt + random.uniform(0, 0.5)
                logging.warning("News fetch failed (attempt %s/%s): %s", attempt + 1, self.max_retries, exc)
                time.sleep(backoff)
        if last_exc:
            logging.error("News fetch failed after %s attempts: %s", self.max_retries, last_exc)
        return []


class SentimentAnalysisTrader(AlgorithmicTrader):
    def __init__(
        self,
        symbol: str,
        matching_engine: MatchingEngine,
        model_file: str,
        news_api_key: str,
        interval: float = 60.0,
        vocab_size: int = 20000,
        max_sequence_length: int = 128,
        vocab_path: Optional[str] = None,
    ) -> None:
        super().__init__(symbol, matching_engine, interval)
        self.model = self._load_model(model_file)
        self.expect_raw_text: bool = False
        self.disabled: bool = False
        # Determine if model expects raw strings
        try:
            model_input = getattr(self.model, 'inputs', [None])[0]
            if model_input is not None and getattr(model_input, 'dtype', None) is not None:
                self.expect_raw_text = str(model_input.dtype).lower().endswith('string')
        except Exception:
            self.expect_raw_text = False

        if self.expect_raw_text:
            self.vectorize_layer = None  # type: ignore[assignment]
        else:
            self.vectorize_layer = self._create_vectorize_layer(vocab_size, max_sequence_length)
            if vocab_path and os.path.exists(vocab_path):
                try:
                    with open(vocab_path, 'r', encoding='utf-8') as f:
                        vocab = [line.strip() for line in f if line.strip()]
                    self.vectorize_layer.set_vocabulary(vocab)
                except Exception as exc:
                    logging.warning("Failed to load vocabulary from %s: %s", vocab_path, exc)
            else:
                logging.warning("No vocabulary provided for sentiment model without preprocessing; disabling trader to avoid garbage predictions.")
                self.disabled = True

        self.news_fetcher = NewsFetcher(api_key=news_api_key)

    def _load_model(self, model_file: str):
        return load_model(model_file)

    def _create_vectorize_layer(self, vocab_size: int, max_sequence_length: int):
        vectorize_layer = tf.keras.layers.TextVectorization(
            max_tokens=vocab_size,
            output_mode='int',
            output_sequence_length=max_sequence_length,
        )
        return vectorize_layer

    def _vectorize_text(self, texts: List[str]):
        tensor = tf.constant(texts)
        if self.vectorize_layer is None:
            return tensor
        return self.vectorize_layer(tensor)

    def _predict_sentiment(self, headlines: List[str]) -> np.ndarray:
        inputs = headlines if self.expect_raw_text else self._vectorize_text(headlines)
        probs = self.model.predict(inputs, verbose=0)
        sentiment_scores = np.argmax(probs, axis=1)
        return sentiment_scores

    @staticmethod
    def _decide_trade_action(sentiment_score: int) -> str:
        if sentiment_score == 2:
            return "buy"
        if sentiment_score == 0:
            return "sell"
        return "hold"

    def trade(self) -> None:
        if self.disabled:
            return
        headlines = self.news_fetcher.fetch_latest_news(query=self.symbol)
        if not headlines:
            return
        for headline in headlines:
            sentiment_score = self._predict_sentiment([headline])
            action = self._decide_trade_action(int(sentiment_score[0]))
            logging.info(f"Headline: {headline} | Sentiment: {int(sentiment_score[0])} -> Action: {action}")
            if self.current_price is None:
                continue
            if action == "buy":
                order = Order(id=uuid.uuid4().hex, price=self.current_price, quantity=100, side='buy', type='market', symbol=self.symbol, owner_id='sentiment')
                self.matching_engine.match_order(order)
            elif action == "sell":
                order = Order(id=uuid.uuid4().hex, price=self.current_price, quantity=100, side='sell', type='market', symbol=self.symbol, owner_id='sentiment')
                self.matching_engine.match_order(order)

    def handle_market_data(self, data: Dict[str, Any]) -> None:
        pass


class CustomTrader(AlgorithmicTrader):
    def __init__(self, symbol: str, matching_engine: MatchingEngine, interval: float = 0.1, threshold: float = 0.0) -> None:
        super().__init__(symbol, matching_engine, interval)
        self.threshold = threshold

    def trade(self) -> None:
        if self.current_price is None:
            return
        if self.current_price < self.threshold:
            order = Order(id=uuid.uuid4().hex, price=self.current_price, quantity=10, side='buy', type='market', symbol=self.symbol, owner_id='custom')
            self.matching_engine.match_order(order)


# --------------------------------------------------------------------------------------
# Strategy Registry (Built-in)
# --------------------------------------------------------------------------------------
@dataclass
class StrategySpec:
    name: str
    description: str
    params: Dict[str, str]


_STRATEGY_REGISTRY: Dict[str, StrategySpec] = {}


def register_strategy(name: str, description: str, params: Dict[str, str]) -> None:
    _STRATEGY_REGISTRY[name] = StrategySpec(name=name, description=description, params=params)


def list_strategies() -> List[StrategySpec]:
    return list(_STRATEGY_REGISTRY.values())


# Register built-in strategies
register_strategy(
    name="MomentumTrader",
    description="Trades in direction of short-term momentum using price delta over lookback",
    params={"lookback": "int (window length)", "interval": "float (seconds)"},
)
register_strategy(
    name="EMABasedTrader",
    description="Crossover of short and long EMAs triggers buy/sell",
    params={"short_window": "int", "long_window": "int", "interval": "float (seconds)"},
)
register_strategy(
    name="SwingTrader",
    description="Buys near support and sells near resistance levels",
    params={"support_level": "float", "resistance_level": "float", "interval": "float (seconds)"},
)
register_strategy(
    name="CustomTrader",
    description="Threshold-based simple mean-reversion or trigger logic",
    params={"threshold": "float", "interval": "float (seconds)"},
)
register_strategy(
    name="SentimentAnalysisTrader",
    description="News sentiment-driven trading using a Keras model pipeline",
    params={
        "model_file": "str (path to keras model)",
        "news_api_key": "str (NewsAPI key)",
        "vocab_path": "Optional[str] (TextVectorization vocabulary)",
        "interval": "float (seconds)",
    },
)


# --------------------------------------------------------------------------------------
# Backtesting
# --------------------------------------------------------------------------------------
def load_historical_data(symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
    # Try cache first
    parquet_path, csv_path = _cache_path_for_history(symbol, start_date, end_date, interval=None, period=None)
    cached = _load_cache_df(parquet_path, csv_path)
    if cached is not None and not cached.empty:
        df = cached.copy()
        # Ensure a 'Date' column exists consistently
        if isinstance(df.index, pd.MultiIndex) and 'date' in df.index.names:
            try:
                df = df.reset_index(level='date').rename(columns={'date': 'Date'})
            except Exception:
                df = df.reset_index()
        else:
            df = df.reset_index()
        # Normalize possible column names
        if 'date' in df.columns and 'Date' not in df.columns:
            df = df.rename(columns={'date': 'Date'})
        if 'Date' not in df.columns:
            # As a fallback, create Date from index if present
            try:
                df['Date'] = pd.to_datetime(df.index)
                df.reset_index(drop=True, inplace=True)
            except Exception:
                pass
        return df

    # Fetch with retry
    data = _yq_history_with_retry(symbol, start=start_date, end=end_date, max_retries=6, base_backoff=1.8)
    if data is None or data.empty:
        raise RuntimeError(f"No historical data returned for {symbol} between {start_date} and {end_date}")
    # Persist to cache for future runs
    try:
        _save_cache_df(data, parquet_path, csv_path)
    except Exception:
        pass
    df = data.copy()
    # Ensure a 'Date' column exists consistently
    if isinstance(df.index, pd.MultiIndex) and 'date' in df.index.names:
        try:
            df = df.reset_index(level='date').rename(columns={'date': 'Date'})
        except Exception:
            df = df.reset_index()
    else:
        # For DatetimeIndex
        df['Date'] = df.index
        df.reset_index(drop=True, inplace=True)
    if 'date' in df.columns and 'Date' not in df.columns:
        df = df.rename(columns={'date': 'Date'})
    # Validate required columns
    required_cols = {"Close"}
    missing = required_cols - set(df.columns)
    if missing:
        raise RuntimeError(f"Historical data missing required columns: {missing}")
    return df


def run_backtest(
    historical_data: pd.DataFrame,
    market_maker: MarketMaker,
    matching_engine: MatchingEngine,
    traders: Optional[List[AlgorithmicTrader]] = None,
    portfolio: Optional[Portfolio] = None,
    csv_logger: Optional[CsvLogger] = None,
) -> None:  # noqa: ARG001
    symbol = market_maker.symbol
    for _, row in historical_data.iterrows():
        # Advance engine time for latency scheduling
        ts = pd.to_datetime(row['Date'], utc=True) if not isinstance(row['Date'], pd.Timestamp) else row['Date']
        if isinstance(ts, pd.Timestamp) and ts.tzinfo is None:
            ts = ts.tz_localize('UTC')
        matching_engine.set_time(ts)
        matching_engine.process_delayed_orders(ts)

        market_data = {
            'symbol': symbol,
            'price': float(row['Close']),
            'timestamp': ts,
        }
        market_maker.on_market_data(market_data)
        if traders:
            for t in traders:
                try:
                    t.on_market_data(market_data)
                    t.trade()
                except Exception as exc:
                    logging.warning("Backtest trader error: %s", exc)
        if csv_logger is not None and portfolio is not None:
            try:
                price = float(row['Close'])
                net_liq = mark_to_market(portfolio, {symbol: price}) + portfolio.realized_pnl
                csv_logger.log_equity(ts, net_liq, portfolio.realized_pnl, portfolio.cash)
            except Exception as exc:
                logging.debug("Equity log skipped: %s", exc)
    logging.info("Backtest completed.")


def load_multi_historical_data(symbols: List[str], start_date: str, end_date: str) -> Dict[str, pd.DataFrame]:
    data_map: Dict[str, pd.DataFrame] = {}
    for sym in symbols:
        df = load_historical_data(sym, start_date, end_date)
        # Normalize timestamp to UTC and set index for fast lookup
        ts = pd.to_datetime(df['Date'], utc=True, errors='coerce')
        df = df.assign(Date=ts).dropna(subset=['Date']).reset_index(drop=True)
        data_map[sym] = df
    return data_map


def run_multi_backtest(
    historical_map: Dict[str, pd.DataFrame],
    engines: Dict[str, MatchingEngine],
    market_makers: Dict[str, MarketMaker],
    traders_map: Optional[Dict[str, List[AlgorithmicTrader]]],
    portfolio: Portfolio,
    csv_logger: CsvLogger,
) -> None:
    # Build a unified sorted time index
    all_ts: List[pd.Timestamp] = []
    per_symbol_ts: Dict[str, pd.Series] = {}
    per_symbol_price: Dict[str, pd.Series] = {}
    for sym, df in historical_map.items():
        s_ts = pd.to_datetime(df['Date'], utc=True, errors='coerce')
        s_ts = s_ts.dropna()
        per_symbol_ts[sym] = s_ts
        per_symbol_price[sym] = pd.Series(df['Close'].values, index=s_ts.values)
        all_ts.extend(list(s_ts.values))
    # Unique sorted timestamps
    unique_ts = sorted(set(all_ts))

    for ts in unique_ts:
        last_prices: Dict[str, float] = {}
        # Advance each engine time and process latency queues
        for sym, engine in engines.items():
            engine.set_time(pd.Timestamp(ts))
            engine.process_delayed_orders(pd.Timestamp(ts))

        # Dispatch market data per symbol if bar exists at ts
        for sym, df in historical_map.items():
            price_series = per_symbol_price[sym]
            if ts in price_series.index:
                price = float(price_series.loc[ts])
                md = {'symbol': sym, 'price': price, 'timestamp': pd.Timestamp(ts)}
                market_makers[sym].on_market_data(md)
                if traders_map and sym in traders_map:
                    for t in traders_map[sym]:
                        try:
                            t.on_market_data(md)
                            t.trade()
                        except Exception as exc:
                            logging.warning("Backtest trader error [%s]: %s", sym, exc)
                last_prices[sym] = price

        # Log equity across all symbols
        try:
            net_liq = mark_to_market(portfolio, last_prices) + portfolio.realized_pnl
            csv_logger.log_equity(pd.Timestamp(ts), net_liq, portfolio.realized_pnl, portfolio.cash)
        except Exception as exc:
            logging.debug("Equity log skipped: %s", exc)

    logging.info("Multi-asset backtest completed.")


# --------------------------------------------------------------------------------------
# Demo controls (retained from notebook): order creation and display
# --------------------------------------------------------------------------------------
def demo_order_controls(order_book: OrderBook) -> None:
    ask_order = Order(id=uuid.uuid4().hex, price=415.0, quantity=100, side='sell', type='limit', symbol='MSFT')
    order_book.add_order(ask_order)
    order_book.display_order_book()


# --------------------------------------------------------------------------------------
# Thread helpers
# --------------------------------------------------------------------------------------
def start_trader_threads(traders: List[AlgorithmicTrader], feed: MarketDataFeed) -> List[threading.Thread]:
    threads: List[threading.Thread] = []
    for trader in traders:
        thread = threading.Thread(target=trader.start, args=(feed,), daemon=True)
        thread.start()
        threads.append(thread)
    return threads


def stop_traders(traders: List[AlgorithmicTrader], threads: List[threading.Thread]) -> None:
    for trader in traders:
        trader.stop()
    for thread in threads:
        thread.join(timeout=5)


# --------------------------------------------------------------------------------------
# Main (CLI)
# --------------------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description="Trading Simulator with Algorithmic Traders")
    parser.add_argument('--mode', choices=['backtest', 'live', 'demo'], default='backtest', help='Run mode')
    parser.add_argument('--symbol', default='AAPL', help='Ticker symbol')
    parser.add_argument('--start-date', default='2023-01-01', help='Backtest start date (YYYY-MM-DD)')
    parser.add_argument('--end-date', default='2023-12-31', help='Backtest end date (YYYY-MM-DD)')
    parser.add_argument('--fix-host', default='localhost', help='FIX server host')
    parser.add_argument('--fix-port', type=int, default=5005, help='FIX server port')
    parser.add_argument('--md-interval', type=int, default=60, help='Market data interval seconds')
    parser.add_argument('--symbols', default=None, help='Comma-separated list of symbols for multi-asset backtest')
    parser.add_argument('--enable-traders', action='store_true', help='Enable algorithmic traders in live mode')
    parser.add_argument('--sentiment-model-path', default='sentiment_classifier_model.keras', help='Sentiment model path')
    parser.add_argument('--news-api-key', default='', help='NewsAPI key for sentiment trader')
    parser.add_argument('--inject-liquidity', type=int, default=0, help='Inject synthetic liquidity every N seconds (0 to disable)')
    parser.add_argument('--seed', type=int, default=None, help='Random seed for reproducibility')
    parser.add_argument('--sentiment-vocab-path', default=None, help='Optional vocabulary file for sentiment TextVectorization')
    parser.add_argument('--initial-cash', type=float, default=1_000_000.0, help='Initial cash for portfolio tracking')
    parser.add_argument('--fee-bps', type=float, default=0.0, help='Execution fee in basis points')
    parser.add_argument('--risk-max-order-qty', type=int, default=1000, help='Risk: maximum order quantity')
    parser.add_argument('--risk-max-symbol-position', type=int, default=10_000, help='Risk: maximum net position per symbol')
    parser.add_argument('--risk-max-gross-notional', type=float, default=5_000_000.0, help='Risk: maximum gross notional per order')
    parser.add_argument('--log-dir', default='.logs', help='Directory for CSV logs (executions, equity curve)')
    parser.add_argument('--slippage-bps-per-100', type=float, default=0.0, help='Slippage in bps per 100 shares for backtests')
    parser.add_argument('--latency-ms', type=int, default=0, help='Order latency in milliseconds for backtests')
    parser.add_argument('--export-report', action='store_true', help='After backtest, export an HTML performance report')
    parser.add_argument('--report-out', default='report.html', help='Path for exported HTML performance report')
    parser.add_argument('--optuna-trials', type=int, default=0, help='Run Optuna parameter search with N trials (0 to disable)')
    parser.add_argument('--mlflow-uri', default=None, help='MLflow tracking URI (set to enable MLflow logging)')
    parser.add_argument('--mlflow-experiment', default='trading-simulator', help='MLflow experiment name')

    args = parser.parse_args()

    # Core components
    if args.seed is not None:
        try:
            random.seed(args.seed)
            np.random.seed(args.seed & 0xFFFFFFFF)
            try:
                tf.random.set_seed(args.seed)
            except Exception:
                pass
        except Exception as exc:
            logging.warning("Failed to set RNG seeds: %s", exc)
    order_book = OrderBook()
    matching_engine = MatchingEngine(order_book)
    # Configure backtest microstructure model
    matching_engine.slippage_bps_per_100_shares = float(max(0.0, args.slippage_bps_per_100))
    matching_engine.latency_ms = max(0, int(args.latency_ms))
    portfolio = Portfolio(initial_cash=args.initial_cash, fee_bps=args.fee_bps)
    matching_engine.subscribe_trades(portfolio.on_execution)
    csv_logger = CsvLogger(args.log_dir)
    matching_engine.subscribe_trades(csv_logger.log_execution)
    # Risk manager
    matching_engine.risk_manager = RiskManager(
        portfolio=portfolio,
        max_order_qty=args.risk_max_order_qty,
        max_symbol_position=args.risk_max_symbol_position,
        max_gross_notional=args.risk_max_gross_notional,
    )

    if args.mode == 'backtest':
        symbol = args.symbol
        if args.symbols:
            # Multi-asset backtest
            symbols = [s.strip() for s in args.symbols.split(',') if s.strip()]
            data_map = load_multi_historical_data(symbols, args.start_date, args.end_date)
            engines = {}
            makers = {}
            traders_map: Dict[str, List[AlgorithmicTrader]] = {}
            for sym in symbols:
                ob = OrderBook()
                eng = MatchingEngine(ob)
                eng.slippage_bps_per_100_shares = matching_engine.slippage_bps_per_100_shares
                eng.latency_ms = matching_engine.latency_ms
                eng.subscribe_trades(portfolio.on_execution)
                eng.subscribe_trades(csv_logger.log_execution)
                eng.risk_manager = matching_engine.risk_manager
                engines[sym] = eng
                makers[sym] = MarketMaker(
                    symbol=sym,
                    matching_engine=eng,
                    gamma=args.mm_gamma,
                    k=args.mm_k,
                    horizon_seconds=args.mm_horizon_seconds,
                    max_inventory=args.mm_max_inventory,
                    base_order_size=args.mm_base_order_size,
                    min_spread=args.mm_min_spread,
                    num_levels=args.mm_num_levels,
                    level_spacing_bps=args.mm_level_spacing_bps,
                    size_decay=args.mm_size_decay,
                    momentum_window=args.mm_momentum_window,
                    alpha_skew=args.mm_alpha_skew,
                    vol_widen_z=args.mm_vol_widen_z,
                    drawdown_limit=args.mm_drawdown_limit,
                )
                eng.subscribe_trades(makers[sym].on_execution)
                if args.enable_traders:
                    traders_map[sym] = [
                        MomentumTrader(symbol=sym, matching_engine=eng, interval=0.0),
                        EMABasedTrader(symbol=sym, matching_engine=eng, interval=0.0),
                        SwingTrader(symbol=sym, matching_engine=eng, interval=0.0),
                    ]
            run_multi_backtest(
                data_map,
                engines,
                makers,
                traders_map if traders_map else None,
                portfolio,
                csv_logger,
            )
        else:
            # Single-asset backtest
            historical_data = load_historical_data(symbol, args.start_date, args.end_date)
            market_maker = MarketMaker(
                symbol=symbol,
                matching_engine=matching_engine,
                gamma=args.mm_gamma,
                k=args.mm_k,
                horizon_seconds=args.mm_horizon_seconds,
                max_inventory=args.mm_max_inventory,
                base_order_size=args.mm_base_order_size,
                min_spread=args.mm_min_spread,
                num_levels=args.mm_num_levels,
                level_spacing_bps=args.mm_level_spacing_bps,
                size_decay=args.mm_size_decay,
                momentum_window=args.mm_momentum_window,
                alpha_skew=args.mm_alpha_skew,
                vol_widen_z=args.mm_vol_widen_z,
                drawdown_limit=args.mm_drawdown_limit,
            )
            backtest_traders: List[AlgorithmicTrader] = []
            if args.enable_traders:
                backtest_traders = [
                    MomentumTrader(symbol=symbol, matching_engine=matching_engine, interval=0.0),
                    EMABasedTrader(symbol=symbol, matching_engine=matching_engine, interval=0.0),
                    SwingTrader(symbol=symbol, matching_engine=matching_engine, interval=0.0),
                ]
            run_backtest(
                historical_data,
                market_maker,
                matching_engine,
                traders=backtest_traders if backtest_traders else None,
                portfolio=portfolio,
                csv_logger=csv_logger,
            )
        if args.export_report:
            try:
                eq_path = os.path.join(args.log_dir, 'equity_curve.csv')
                eq_df = _load_equity_curve(eq_path)
                metrics = compute_performance_metrics(eq_df)
                export_html_report(eq_df, metrics, args.report_out)
                logging.info("Report exported to %s", args.report_out)
            except Exception as exc:
                logging.warning("Report export failed: %s", exc)
        if args.optuna_trials and args.optuna_trials > 0:
            if not OPTUNA_AVAILABLE:
                logging.warning("Optuna not available. Install with: pip install optuna")
            else:
                if MLFLOW_AVAILABLE and args.mlflow_uri:
                    try:
                        mlflow.set_tracking_uri(args.mlflow_uri)
                        mlflow.set_experiment(args.mlflow_experiment)
                    except Exception as exc:
                        logging.warning("Failed to configure MLflow: %s", exc)
                study = optuna.create_study(direction='maximize')
                def _obj(trial):
                    if MLFLOW_AVAILABLE and args.mlflow_uri:
                        with mlflow.start_run(nested=True):
                            return objective_optuna(trial, symbol, args.start_date, args.end_date, {
                                'initial_cash': args.initial_cash,
                                'fee_bps': args.fee_bps,
                                'risk_max_order_qty': args.risk_max_order_qty,
                                'risk_max_symbol_position': args.risk_max_symbol_position,
                                'risk_max_gross_notional': args.risk_max_gross_notional,
                            }, args.log_dir)
                    return objective_optuna(trial, symbol, args.start_date, args.end_date, {
                        'initial_cash': args.initial_cash,
                        'fee_bps': args.fee_bps,
                        'risk_max_order_qty': args.risk_max_order_qty,
                        'risk_max_symbol_position': args.risk_max_symbol_position,
                        'risk_max_gross_notional': args.risk_max_gross_notional,
                    }, args.log_dir)
                study.optimize(_obj, n_trials=int(args.optuna_trials))
                best_value = study.best_value
                best_params = study.best_params
                logging.info("Optuna best value=%.6f params=%s", best_value, best_params)
                if MLFLOW_AVAILABLE and args.mlflow_uri:
                    try:
                        with mlflow.start_run(run_name='optuna-summary'):
                            mlflow.log_params(best_params)
                            mlflow.log_metric('best_value', float(best_value))
                    except Exception as exc:
                        logging.warning("Failed to log MLflow summary: %s", exc)
        snap = portfolio.snapshot()
        logging.info("Portfolio after backtest: cash=%.2f realized_pnl=%.2f positions=%s", snap['cash'], snap['realized_pnl'], snap['positions'])
        return

    if args.mode == 'demo':
        demo_order_controls(order_book)
        return

    # Live mode
    symbol = args.symbol
    fix_app = FixApplication(matching_engine)
    market_data_feed = MarketDataFeed(symbol=symbol)
    market_maker = MarketMaker(
        symbol=symbol,
        matching_engine=matching_engine,
        gamma=args.mm_gamma,
        k=args.mm_k,
        horizon_seconds=args.mm_horizon_seconds,
        max_inventory=args.mm_max_inventory,
        base_order_size=args.mm_base_order_size,
        min_spread=args.mm_min_spread,
        num_levels=args.mm_num_levels,
        level_spacing_bps=args.mm_level_spacing_bps,
        size_decay=args.mm_size_decay,
        momentum_window=args.mm_momentum_window,
        alpha_skew=args.mm_alpha_skew,
        vol_widen_z=args.mm_vol_widen_z,
        drawdown_limit=args.mm_drawdown_limit,
    )
    # Subscribe MM to executions to track inventory
    matching_engine.subscribe_trades(market_maker.on_execution)

    # Start FIX server thread
    fix_thread = threading.Thread(target=fix_app.start, kwargs={'host': args.fix_host, 'port': args.fix_port}, daemon=True)
    fix_thread.start()

    # Start market data feed thread
    feed_thread = threading.Thread(target=market_data_feed.start, kwargs={'interval_seconds': args.md_interval}, daemon=True)
    feed_thread.start()

    # Start market maker (subscriber)
    market_maker.start(market_data_feed)

    # Optional: traders
    traders: List[AlgorithmicTrader] = []
    trader_threads: List[threading.Thread] = []
    if args.enable_traders:
        momentum_trader = MomentumTrader(symbol=symbol, matching_engine=matching_engine, interval=10)
        ema_trader = EMABasedTrader(symbol=symbol, matching_engine=matching_engine, interval=30)
        swing_trader = SwingTrader(symbol=symbol, matching_engine=matching_engine, interval=15)

        traders = [momentum_trader, ema_trader, swing_trader]
        # Sentiment trader only if both model and API key provided
        if args.news_api_key:
            try:
                sentiment_trader = SentimentAnalysisTrader(
                    symbol=symbol,
                    matching_engine=matching_engine,
                    model_file=args.sentiment_model_path,
                    news_api_key=args.news_api_key,
                    interval=60,
                    vocab_path=args.sentiment_vocab_path,
                )
                traders.append(sentiment_trader)
            except Exception as exc:
                logging.warning("Sentiment trader disabled: %s", exc)

        trader_threads = start_trader_threads(traders, market_data_feed)

    # Optional: liquidity injection
    liquidity_thread: Optional[threading.Thread] = None
    if args.inject_liquidity > 0:
        provider = SyntheticLiquidityProvider(symbol=symbol, matching_engine=matching_engine, num_orders=10)
        liquidity_thread = threading.Thread(target=auto_inject_liquidity, args=(provider, args.inject_liquidity), daemon=True)
        liquidity_thread.start()

    try:
        # Keep the main thread alive for live mode
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logging.info("Shutting down...")
    finally:
        # Stop everything gracefully
        market_maker.stop()
        market_data_feed.stop()
        fix_app.stop()
        if traders:
            stop_traders(traders, trader_threads)
        if liquidity_thread:
            # No explicit stop; thread is daemon and will exit on process termination
            pass
        # Final live snapshot and equity log entry if last price is known
        snap = portfolio.snapshot()
        last_price = market_data_feed.last_price()
        if last_price is not None:
            net_liq = mark_to_market(portfolio, {args.symbol: last_price}) + portfolio.realized_pnl
            csv_logger.log_equity(pd.Timestamp.utcnow().tz_localize('UTC'), net_liq, portfolio.realized_pnl, portfolio.cash)
        logging.info("Final portfolio: cash=%.2f realized_pnl=%.2f positions=%s", snap['cash'], snap['realized_pnl'], snap['positions'])


if __name__ == "__main__":
    main()


