"""NewsAPI headline fetcher used by SentimentAnalysisTrader."""
from __future__ import annotations

import logging
import random
import time
from typing import List

logger = logging.getLogger(__name__)

try:
    from newsapi import NewsApiClient  # type: ignore
    NEWSAPI_AVAILABLE = True
except ImportError:
    NEWSAPI_AVAILABLE = False


class NewsFetcher:
    def __init__(self, api_key: str, timeout_seconds: int = 10, max_retries: int = 3) -> None:
        if not NEWSAPI_AVAILABLE:
            raise RuntimeError("newsapi-python is not installed; `pip install newsapi-python` to use SentimentAnalysisTrader")
        self.newsapi = NewsApiClient(api_key=api_key)
        self.timeout_seconds = max(1, int(timeout_seconds))
        self.max_retries = max(1, int(max_retries))

    def fetch_latest_news(self, query: str = "stock market") -> List[str]:
        last_exc = None
        for attempt in range(self.max_retries):
            try:
                articles = self.newsapi.get_everything(q=query, language="en", sort_by="publishedAt", page_size=5)
                return [a["title"] for a in articles.get("articles", [])]
            except Exception as exc:
                last_exc = exc
                backoff = 1.5 ** attempt + random.uniform(0, 0.5)
                logger.warning("News fetch failed (attempt %s/%s): %s", attempt + 1, self.max_retries, exc)
                time.sleep(backoff)
        if last_exc:
            logger.error("News fetch failed after %s attempts: %s", self.max_retries, last_exc)
        return []
