"""News-sentiment-driven trader.

Fix vs. the original: the original re-fetched the same ~5 latest headlines
every `interval` seconds and re-traded every one of them every single time
with no memory of what it had already acted on -- so as long as NewsAPI kept
returning the same top headlines (which it does between fast polls), the
trader would keep re-buying/re-selling on stale news indefinitely. This
version remembers headlines it has already acted on (bounded LRU cache) and
skips them on subsequent polls.
"""
from __future__ import annotations

import logging
import os
import uuid
from collections import OrderedDict
from typing import Optional

import numpy as np

from ..core.order import Order
from .base import AlgorithmicTrader
from .news import NewsFetcher

logger = logging.getLogger(__name__)

try:
    import tensorflow as tf  # type: ignore
    from tensorflow.keras.models import load_model  # type: ignore
    TF_AVAILABLE = True
except ImportError:
    tf = None  # type: ignore
    TF_AVAILABLE = False

    def load_model(*args, **kwargs):  # type: ignore
        raise RuntimeError("TensorFlow is not installed; `pip install tensorflow` to use SentimentAnalysisTrader")


class SentimentAnalysisTrader(AlgorithmicTrader):
    def __init__(self, symbol: str, matching_engine, model_file: str, news_api_key: str,
                 interval: float = 60.0, vocab_size: int = 20000, max_sequence_length: int = 128,
                 vocab_path: Optional[str] = None, quantity: int = 100, seen_cache_size: int = 500,
                 owner_id: str = "sentiment") -> None:
        super().__init__(symbol, matching_engine, interval)
        self.model = load_model(model_file)
        self.quantity = int(quantity)
        self.owner_id = owner_id
        self.disabled = False
        self.expect_raw_text = False
        self._seen_headlines: "OrderedDict[str, None]" = OrderedDict()
        self._seen_cache_size = max(1, int(seen_cache_size))

        try:
            model_input = getattr(self.model, "inputs", [None])[0]
            if model_input is not None and getattr(model_input, "dtype", None) is not None:
                self.expect_raw_text = str(model_input.dtype).lower().endswith("string")
        except Exception:
            self.expect_raw_text = False

        self.vectorize_layer = None
        if not self.expect_raw_text:
            self.vectorize_layer = tf.keras.layers.TextVectorization(
                max_tokens=vocab_size, output_mode="int", output_sequence_length=max_sequence_length)
            if vocab_path and os.path.exists(vocab_path):
                with open(vocab_path, "r", encoding="utf-8") as f:
                    vocab = [line.strip() for line in f if line.strip()]
                self.vectorize_layer.set_vocabulary(vocab)
            else:
                logger.warning("No vocabulary provided for a model expecting pre-tokenized input; "
                                "disabling %s to avoid trading on garbage predictions.", type(self).__name__)
                self.disabled = True

        self.news_fetcher = NewsFetcher(api_key=news_api_key)

    def _remember(self, headline: str) -> bool:
        """Return True if this headline is new (and record it), False if
        we've already acted on it."""
        if headline in self._seen_headlines:
            self._seen_headlines.move_to_end(headline)
            return False
        self._seen_headlines[headline] = None
        if len(self._seen_headlines) > self._seen_cache_size:
            self._seen_headlines.popitem(last=False)
        return True

    def _vectorize_text(self, texts):
        tensor = tf.constant(texts)
        return tensor if self.vectorize_layer is None else self.vectorize_layer(tensor)

    def _predict_sentiment(self, headlines) -> np.ndarray:
        inputs = headlines if self.expect_raw_text else self._vectorize_text(headlines)
        probs = self.model.predict(inputs, verbose=0)
        return np.argmax(probs, axis=1)

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
        for headline in headlines:
            if not self._remember(headline):
                continue  # already acted on this headline in a prior poll
            sentiment_score = self._predict_sentiment([headline])
            action = self._decide_trade_action(int(sentiment_score[0]))
            logger.info("Headline: %s | sentiment=%s -> %s", headline, int(sentiment_score[0]), action)
            if action == "hold" or self.current_price is None:
                continue
            order = Order(id=uuid.uuid4().hex, price=self.current_price, quantity=self.quantity,
                          side=action, type="market", symbol=self.symbol, owner_id=self.owner_id)
            self.matching_engine.match_order(order)

    def handle_market_data(self, data) -> None:
        pass
