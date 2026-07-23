"""Built-in strategy registry plus a validated loader for custom
`module:ClassName` strategies (used by the `--custom-trader` CLI flag and the
guided CLI).

Fix vs. the original: the original dynamically imported whatever
`module:ClassName` the user typed and instantiated it with no interface
check -- a typo'd or wrong class would fail deep inside the trading loop with
a confusing AttributeError instead of a clear error at load time. `load_custom_trader`
now verifies the class subclasses AlgorithmicTrader before instantiating it.
"""
from __future__ import annotations

import importlib
import json
from dataclasses import dataclass
from typing import Any, Dict, List, Type

from .base import AlgorithmicTrader


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


class StrategyLoadError(RuntimeError):
    pass


def resolve_trader_class(spec: str) -> Type[AlgorithmicTrader]:
    """Resolve a 'module.path:ClassName' spec to a class, verifying it's a
    proper AlgorithmicTrader subclass before handing it back."""
    if ":" not in spec:
        raise StrategyLoadError(f"trader spec must be 'module.path:ClassName', got {spec!r}")
    module_path, class_name = spec.split(":", 1)
    try:
        module = importlib.import_module(module_path)
    except ImportError as exc:
        raise StrategyLoadError(f"could not import module {module_path!r}: {exc}") from exc
    cls = getattr(module, class_name, None)
    if cls is None:
        raise StrategyLoadError(f"module {module_path!r} has no attribute {class_name!r}")
    if not (isinstance(cls, type) and issubclass(cls, AlgorithmicTrader)):
        raise StrategyLoadError(
            f"{spec} is not a subclass of trading_simulator.strategies.AlgorithmicTrader "
            "(custom traders must subclass it and implement trade())"
        )
    return cls


def load_custom_trader(spec: str, params_json: str, symbol: str, matching_engine) -> AlgorithmicTrader:
    cls = resolve_trader_class(spec)
    try:
        params = json.loads(params_json) if params_json else {}
    except json.JSONDecodeError as exc:
        raise StrategyLoadError(f"invalid JSON params for {spec}: {exc}") from exc
    return cls(symbol=symbol, matching_engine=matching_engine, **params)


register_strategy("MomentumTrader", "Trades in direction of short-term momentum using price delta over lookback",
                   {"lookback": "int (window length)", "interval": "float (seconds)"})
register_strategy("EMABasedTrader", "Crossover of short and long EMAs triggers buy/sell",
                   {"short_window": "int", "long_window": "int", "interval": "float (seconds)"})
register_strategy("SwingTrader", "Buys near support and sells near resistance levels",
                   {"support_level": "float", "resistance_level": "float", "interval": "float (seconds)"})
register_strategy("CustomTrader", "Threshold-based simple mean-reversion or trigger logic",
                   {"threshold": "float", "interval": "float (seconds)"})
register_strategy("SentimentAnalysisTrader", "News sentiment-driven trading using a Keras model pipeline",
                   {"model_file": "str (path to keras model)", "news_api_key": "str (NewsAPI key)",
                    "vocab_path": "Optional[str] (TextVectorization vocabulary)", "interval": "float (seconds)"})
