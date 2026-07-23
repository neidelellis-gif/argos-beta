from __future__ import annotations

from pathlib import Path
from time import perf_counter
from typing import Iterable, List, Optional

from .cache import TTLCache
from .logger import build_market_logger
from .models import Quote
from .provider_base import MarketProvider


class MarketConnector:
    """Provider-agnostic access point for all ARGOS market quotes."""

    def __init__(
        self,
        providers: Optional[Iterable[MarketProvider]] = None,
        cache_ttl_seconds: int = 300,
        log_path: Optional[Path] = None,
    ) -> None:
        self._providers: List[MarketProvider] = list(providers or [])
        self._cache: TTLCache[Quote] = TTLCache(ttl_seconds=cache_ttl_seconds)
        self._logger = build_market_logger(log_path)

    def register_provider(self, provider: MarketProvider) -> None:
        self._providers.append(provider)

    def get_quote(self, ticker: str) -> Quote:
        normalized_ticker = ticker.upper().strip()
        if not normalized_ticker:
            return Quote.unavailable("", error="ticker is required")

        cached = self._cache.get(normalized_ticker)
        if cached is not None:
            return cached

        if not self._providers:
            quote = Quote.unavailable(
                normalized_ticker,
                error="no market provider registered",
            )
            self._cache.set(normalized_ticker, quote)
            return quote

        last_error: Optional[str] = None
        for provider in self._providers:
            started = perf_counter()
            try:
                quote = provider.get_quote(normalized_ticker)
            except Exception as exc:  # provider failure must never break ARGOS
                last_error = str(exc)
                quote = Quote.unavailable(
                    normalized_ticker,
                    provider=getattr(provider, "name", provider.__class__.__name__),
                    error=last_error,
                )

            elapsed_ms = round((perf_counter() - started) * 1000, 2)
            self._logger.info(
                "market quote request",
                extra={
                    "provider": quote.provider,
                    "ticker": normalized_ticker,
                    "elapsed_ms": elapsed_ms,
                    "status": quote.status,
                },
            )

            if quote.status == "ok" and quote.price is not None:
                self._cache.set(normalized_ticker, quote)
                return quote
            last_error = quote.error or last_error

        quote = Quote.unavailable(
            normalized_ticker,
            provider=self._providers[-1].name,
            error=last_error or "all providers unavailable",
        )
        self._cache.set(normalized_ticker, quote)
        return quote

    def clear_cache(self) -> None:
        self._cache.clear()
