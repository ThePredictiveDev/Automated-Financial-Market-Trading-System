"""Backtest execution loops: single-symbol and multi-asset."""
from __future__ import annotations

import logging
from typing import Dict, List, Optional

import pandas as pd

logger = logging.getLogger(__name__)


def run_backtest(historical_data: pd.DataFrame, market_maker, matching_engine, traders: Optional[List] = None,
                  portfolio=None, csv_logger=None) -> None:
    symbol = market_maker.symbol
    if historical_data is None or len(historical_data) == 0:
        logger.warning("run_backtest: empty historical_data for %s", symbol)
        return

    matching_engine.subscribe_trades(market_maker.on_execution)

    for _, row in historical_data.iterrows():
        ts = row["Date"] if isinstance(row["Date"], pd.Timestamp) else pd.to_datetime(row["Date"], utc=True)
        ts = ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")
        matching_engine.set_time(ts)
        matching_engine.process_delayed_orders(ts)

        market_data = {"symbol": symbol, "price": float(row["Close"]), "timestamp": ts}
        market_maker.on_market_data(market_data)
        for t in traders or []:
            try:
                t.on_market_data(market_data)
                t.trade()
            except Exception:
                logger.warning("Backtest trader %s raised", type(t).__name__, exc_info=True)

        if csv_logger is not None and portfolio is not None:
            price = float(row["Close"])
            net_liq = portfolio.equity({symbol: price}) + portfolio.realized_pnl
            csv_logger.log_equity(ts, net_liq, portfolio.realized_pnl, portfolio.cash)

    logger.info("Backtest completed for %s.", symbol)


def run_multi_backtest(historical_map: Dict[str, pd.DataFrame], engines: Dict, market_makers: Dict,
                        traders_map: Optional[Dict[str, List]], portfolio, csv_logger) -> None:
    per_symbol_price: Dict[str, pd.Series] = {}
    all_ts = []
    for sym, df in historical_map.items():
        s_ts = pd.to_datetime(df["Date"], utc=True, errors="coerce").dropna()
        per_symbol_price[sym] = pd.Series(df["Close"].values, index=s_ts.values)
        all_ts.extend(list(s_ts.values))
    unique_ts = sorted(set(all_ts))

    for ts in unique_ts:
        last_prices: Dict[str, float] = {}
        for engine in engines.values():
            engine.set_time(pd.Timestamp(ts))
            engine.process_delayed_orders(pd.Timestamp(ts))

        for sym, price_series in per_symbol_price.items():
            if ts not in price_series.index:
                continue
            price = float(price_series.loc[ts])
            md = {"symbol": sym, "price": price, "timestamp": pd.Timestamp(ts)}
            market_makers[sym].on_market_data(md)
            for t in (traders_map or {}).get(sym, []):
                try:
                    t.on_market_data(md)
                    t.trade()
                except Exception:
                    logger.warning("Backtest trader %s raised for %s", type(t).__name__, sym, exc_info=True)
            last_prices[sym] = price

        net_liq = portfolio.equity(last_prices) + portfolio.realized_pnl
        csv_logger.log_equity(pd.Timestamp(ts), net_liq, portfolio.realized_pnl, portfolio.cash)

    logger.info("Multi-asset backtest completed for %d symbols.", len(historical_map))
