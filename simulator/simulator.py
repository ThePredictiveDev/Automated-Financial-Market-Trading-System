from __future__ import annotations

import bisect
import heapq
import logging
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Deque, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# ENUMS & DATA TYPES
# ---------------------------------------------------------------------------


class Side(str, Enum):
    BUY = "buy"
    SELL = "sell"

    @property
    def opp(self) -> "Side":
        return Side.SELL if self == Side.BUY else Side.BUY


class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"


@dataclass
class Order:
    id: str
    symbol: str
    side: Side
    quantity: int
    type: OrderType = OrderType.LIMIT
    price: Optional[float] = None  # price is optional for market orders
    timestamp: float = field(default_factory=time.time)


@dataclass
class Trade:
    id: str
    symbol: str
    price: float
    quantity: int
    buy_order_id: str
    sell_order_id: str
    timestamp: float = field(default_factory=time.time)


# ---------------------------------------------------------------------------
# ORDER BOOK 
# ---------------------------------------------------------------------------


class OrderBook:
    """A price-level aggregated order book with O(log n) inserts."""

    def __init__(self):
        # Using dict(price -> deque[Order]) for fast order retrieval
        self.bids: Dict[float, Deque[Order]] = defaultdict(deque)
        self.asks: Dict[float, Deque[Order]] = defaultdict(deque)
        # Sorted price levels for quick best bid / best ask lookup
        self._bid_prices: List[float] = []  # descending sorted
        self._ask_prices: List[float] = []  # ascending sorted
        # Map for fast order cancellation / modification
        self._order_map: Dict[str, Tuple[Order, Deque[Order]]] = {}

    # ---------------------------- helpers ----------------------------------
    @staticmethod
    def _insert_price(levels: List[float], price: float, reverse: bool = False):
        """Insert price maintaining sorted order. reverse=True => descending."""
        if price in levels:
            return
        if reverse:
            # bisect in descending means invert sign or use custom key; easier: store negative
            bisect.insort(levels, -price)
        else:
            bisect.insort(levels, price)

    @staticmethod
    def _remove_price(levels: List[float], price: float, reverse: bool = False):
        try:
            idx = levels.index(-price if reverse else price)
            levels.pop(idx)
        except ValueError:
            pass  # already gone

    # ---------------------------- properties --------------------------------

    @property
    def best_bid(self) -> Optional[float]:
        return -self._bid_prices[0] if self._bid_prices else None

    @property
    def best_ask(self) -> Optional[float]:
        return self._ask_prices[0] if self._ask_prices else None

    # ---------------------------- core api ----------------------------------

    def add_order(self, order: Order):
        book_side = self.bids if order.side == Side.BUY else self.asks
        price_levels = self._bid_prices if order.side == Side.BUY else self._ask_prices
        reverse = order.side == Side.BUY

        dq = book_side[order.price]
        dq.append(order)
        # maintain price level list
        self._insert_price(price_levels, order.price, reverse)
        # map for cancellation / modification
        self._order_map[order.id] = (order, dq)

    def cancel_order(self, order_id: str):
        if order_id not in self._order_map:
            return
        order, dq = self._order_map.pop(order_id)
        dq.remove(order)
        if not dq:  # remove empty price level
            book_side = self.bids if order.side == Side.BUY else self.asks
            price_levels = self._bid_prices if order.side == Side.BUY else self._ask_prices
            del book_side[order.price]
            self._remove_price(price_levels, order.price, order.side == Side.BUY)

    def modify_order(self, order_id: str, *, new_qty: Optional[int] = None, new_price: Optional[float] = None):
        if order_id not in self._order_map:
            return
        order, _ = self._order_map[order_id]
        # Remove existing order first
        self.cancel_order(order_id)
        # Create modified copy
        order = Order(
            id=order.id,
            symbol=order.symbol,
            side=order.side,
            quantity=new_qty if new_qty is not None else order.quantity,
            type=order.type,
            price=new_price if new_price is not None else order.price,
            timestamp=time.time(),
        )
        self.add_order(order)

    def depth(self, side: Side, levels: int = 5) -> List[Tuple[float, int]]:
        """Return (price, total_qty) for top *levels* on given side."""
        book_side = self.bids if side == Side.BUY else self.asks
        prices_sorted = (
            sorted(book_side.keys(), reverse=True) if side == Side.BUY else sorted(book_side.keys())
        )
        snapshot = []
        for price in prices_sorted[:levels]:
            total_qty = sum(o.quantity for o in book_side[price])
            snapshot.append((price, total_qty))
        return snapshot


# ---------------------------------------------------------------------------
# MATCHING ENGINE
# ---------------------------------------------------------------------------


class MatchingEngine:
    """Price-time priority limit‐order matching engine."""

    def __init__(self, order_book: OrderBook):
        self.order_book = order_book
        self.trade_log: List[Trade] = []
        self._trade_counter = 0

    # ---------------------------- utility ----------------------------------
    def _log_trade(self, symbol: str, price: float, qty: int, buy_id: str, sell_id: str):
        self._trade_counter += 1
        trade = Trade(
            id=str(self._trade_counter),
            symbol=symbol,
            price=price,
            quantity=qty,
            buy_order_id=buy_id,
            sell_order_id=sell_id,
        )
        self.trade_log.append(trade)
        logging.debug("TRADE %s@%s qty=%s", price, symbol, qty)
        return trade

    # ----------------------------- public ----------------------------------
    def submit_order(self, incoming: Order) -> List[Trade]:
        """Match *incoming* order against book then add remaining if limit."""
        trades: List[Trade] = []
        opposite_book = self.order_book.asks if incoming.side == Side.BUY else self.order_book.bids

        def match_condition(best_price: float) -> bool:
            if incoming.side == Side.BUY:
                return incoming.price is None or incoming.price >= best_price
            return incoming.price is None or incoming.price <= best_price

        best_price_func = min if incoming.side == Side.BUY else max

        while incoming.quantity > 0 and opposite_book:
            best_price = best_price_func(opposite_book.keys())
            if not match_condition(best_price):
                break  # best price not favourable

            queue = opposite_book[best_price]
            while queue and incoming.quantity > 0:
                resting = queue[0]
                trade_qty = min(incoming.quantity, resting.quantity)
                # Log trade
                trade = self._log_trade(
                    symbol=incoming.symbol,
                    price=best_price,
                    qty=trade_qty,
                    buy_id=incoming.id if incoming.side == Side.BUY else resting.id,
                    sell_id=resting.id if incoming.side == Side.BUY else incoming.id,
                )
                trades.append(trade)
                # Update quantities
                incoming.quantity -= trade_qty
                resting = Order(
                    **{**resting.__dict__, "quantity": resting.quantity - trade_qty}
                )
                # Replace or remove
                queue[0] = resting  # even if 0, will pop below
                if resting.quantity == 0:
                    queue.popleft()
                if not queue:
                    # Remove empty price level
                    del opposite_book[best_price]
                    if incoming.side == Side.BUY:
                        OrderBook._remove_price(self.order_book._ask_prices, best_price, False)
                    else:
                        OrderBook._remove_price(self.order_book._bid_prices, best_price, True)
        # If unfilled quantity remains and order is limit or stop_limit, enqueue
        if incoming.quantity > 0 and incoming.type in (OrderType.LIMIT, OrderType.STOP_LIMIT):
            self.order_book.add_order(incoming)
        return trades


# ---------------------------------------------------------------------------
# PORTFOLIO & PNL TRACKING
# ---------------------------------------------------------------------------


@dataclass
class Position:
    symbol: str
    qty: int = 0
    avg_price: float = 0.0
    realized_pnl: float = 0.0

    def update(self, side: Side, trade_price: float, trade_qty: int):
        if side == Side.BUY:
            new_total_cost = self.avg_price * self.qty + trade_price * trade_qty
            self.qty += trade_qty
            self.avg_price = new_total_cost / self.qty
        else:
            # selling
            if trade_qty > self.qty:
                raise ValueError("Cannot sell more than current position")
            self.realized_pnl += (trade_price - self.avg_price) * trade_qty
            self.qty -= trade_qty
            if self.qty == 0:
                self.avg_price = 0.0


class PortfolioManager:
    """Tracks positions and PnL for one or many strategies."""

    def __init__(self):
        self.positions: Dict[str, Position] = {}
        self.cash: float = 0.0

    # -------------------------------- operations ---------------------------
    def process_trade(self, trade: Trade):
        pos = self.positions.setdefault(trade.symbol, Position(symbol=trade.symbol))
        # Determine side for this portfolio. Assume we are the buyer if we generated buy_order_id
        # We cannot infer this directly, so expose explicit API for strategies to call.
        pass  # left for strategy specific implementation

    # More advanced portfolio analytics can be added here.


# ---------------------------------------------------------------------------
# EVENT DRIVEN SIMULATION ENGINE
# ---------------------------------------------------------------------------


class EventType(Enum):
    MARKET = auto()
    ORDER = auto()
    CUSTOM = auto()


@dataclass(order=True)
class ScheduledEvent:
    execute_at: float
    priority: int
    event_type: EventType = field(compare=False)
    payload: dict = field(compare=False)


class Simulation:
    """A simple discrete-event simulator for backtests or synthetic market scenarios."""

    def __init__(self):
        self.order_book = OrderBook()
        self.engine = MatchingEngine(self.order_book)
        self.now: float = 0.0  # simulation time (secs)
        self._queue: List[ScheduledEvent] = []
        self.logger = logging.getLogger("Simulation")
        self.logger.setLevel(logging.INFO)

    # ----------------------- scheduling helpers ----------------------------
    def schedule_event(self, delay: float, event_type: EventType, payload: dict, priority: int = 0):
        evt = ScheduledEvent(self.now + delay, priority, event_type, payload)
        heapq.heappush(self._queue, evt)

    # ----------------------- simulation loop ------------------------------
    def run(self, until: float = float("inf")):
        while self._queue and self.now < until:
            evt = heapq.heappop(self._queue)
            self.now = evt.execute_at
            if evt.event_type == EventType.ORDER:
                order: Order = evt.payload["order"]
                self.logger.debug("Processing order %s at t=%.3f", order.id, self.now)
                trades = self.engine.submit_order(order)
                for t in trades:
                    self.logger.info("TRADE %s %s@%.2f qty=%s", t.symbol, t.id, t.price, t.quantity)
            elif evt.event_type == EventType.MARKET:
                # For future extensions such as price shocks
                pass
            else:
                # custom extension
                pass

    # ----------------------- utilities ------------------------------------
    def snapshot_depth(self, levels: int = 5):
        return {
            "bids": self.order_book.depth(Side.BUY, levels),
            "asks": self.order_book.depth(Side.SELL, levels),
        }

    # ----------------------- convenience -----------------------------------
    def submit_limit_order(self, delay: float, **order_kwargs):
        order_kwargs.setdefault("type", OrderType.LIMIT)
        order = Order(**order_kwargs)
        self.schedule_event(delay, EventType.ORDER, {"order": order})


# ---------------------------------------------------------------------------
# IF EXECUTED AS SCRIPT
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    sim = Simulation()
    # simple test scenario: two crossing orders
    sim.submit_limit_order(0, id="1", symbol="TEST", side=Side.BUY, price=100.0, quantity=10)
    sim.submit_limit_order(0, id="2", symbol="TEST", side=Side.SELL, price=99.5, quantity=10)
    sim.run()
    print("Trade log:")
    for t in sim.engine.trade_log:
        print(t)