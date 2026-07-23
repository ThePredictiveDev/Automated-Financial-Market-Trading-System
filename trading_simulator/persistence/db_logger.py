"""Optional PostgreSQL/SQLAlchemy persistence for executions, equity, and config.

Import guarded: if SQLAlchemy isn't installed, `DbLogger` becomes a stub that
raises a clear RuntimeError on construction (callers can also check
`SQLA_AVAILABLE` up front; the CLI does neither today since DbLogger isn't
yet wired into it -- this is a standalone persistence option).
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from ..core.execution import Execution

logger = logging.getLogger(__name__)

try:
    from sqlalchemy import Column, DateTime, Float, Integer, String, Text, create_engine
    from sqlalchemy.orm import declarative_base, sessionmaker

    SQLA_AVAILABLE = True

    Base = declarative_base()

    class ExecutionORM(Base):
        __tablename__ = "executions"
        trade_id = Column(String, primary_key=True)
        timestamp = Column(DateTime(timezone=True), index=True)
        symbol = Column(String, index=True)
        price = Column(Float)
        quantity = Column(Integer)
        side = Column(String)
        taker_order_id = Column(String)
        maker_order_id = Column(String)

    class EquityORM(Base):
        __tablename__ = "equity_curve"
        id = Column(Integer, primary_key=True, autoincrement=True)
        timestamp = Column(DateTime(timezone=True), index=True)
        net_liquidation = Column(Float)
        realized_pnl = Column(Float)
        cash = Column(Float)

    class ConfigORM(Base):
        __tablename__ = "configs"
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
                        timestamp=execu.timestamp.to_pydatetime() if hasattr(execu.timestamp, "to_pydatetime") else execu.timestamp,
                        symbol=execu.symbol, price=float(execu.price), quantity=int(execu.quantity),
                        side=str(execu.side), taker_order_id=execu.taker_order_id, maker_order_id=execu.maker_order_id,
                    ))
                    s.commit()
            except Exception:
                logger.warning("DB execution log failed", exc_info=True)

        def log_equity(self, timestamp, net_liq: float, realized: float, cash: float) -> None:
            try:
                with self.Session() as s:
                    s.add(EquityORM(
                        timestamp=timestamp.to_pydatetime() if hasattr(timestamp, "to_pydatetime") else timestamp,
                        net_liquidation=float(net_liq), realized_pnl=float(realized), cash=float(cash),
                    ))
                    s.commit()
            except Exception:
                logger.warning("DB equity log failed", exc_info=True)

        def save_config(self, key: str, value: Dict[str, Any]) -> None:
            try:
                with self.Session() as s:
                    payload = json.dumps(value)
                    existing = s.get(ConfigORM, key)
                    if existing is None:
                        s.add(ConfigORM(key=key, value=payload))
                    else:
                        existing.value = payload
                    s.commit()
            except Exception:
                logger.warning("DB save_config failed", exc_info=True)

        def load_config(self, key: str) -> Optional[Dict[str, Any]]:
            try:
                with self.Session() as s:
                    row = s.get(ConfigORM, key)
                    return json.loads(row.value) if row is not None else None
            except Exception:
                logger.warning("DB load_config failed", exc_info=True)
                return None

        def list_configs(self) -> List[str]:
            try:
                with self.Session() as s:
                    return [r[0] for r in s.query(ConfigORM.key).all()]
            except Exception:
                logger.warning("DB list_configs failed", exc_info=True)
                return []

except ImportError:
    SQLA_AVAILABLE = False

    class DbLogger:  # type: ignore[no-redef]
        """Stub used when SQLAlchemy isn't installed. Raises a clear,
        actionable error on construction instead of leaving `DbLogger` as a
        bare `None` (which would fail with a confusing
        `TypeError: 'NoneType' object is not callable` for any caller that
        forgot to check `SQLA_AVAILABLE` first)."""

        def __init__(self, *args, **kwargs) -> None:
            raise RuntimeError(
                "SQLAlchemy is not installed; `pip install sqlalchemy` to use DbLogger "
                "(or check SQLA_AVAILABLE before constructing one)."
            )
