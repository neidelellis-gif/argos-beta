from __future__ import annotations

from pathlib import Path
from time import perf_counter
from typing import Iterable, List, Optional

from .cache import TTLCache
from .logger import build_market_logger
from .models import PriceHistory, Quote
from .persistent_history_cache import PersistentHistoryCache
from .provider_base import MarketProvider


class MarketConnector:
    """Provider-agnostic access point for all ARGOS market quotes."""

    def __init__(
        self,
        providers: Optional[Iterable[MarketProvider]] = None,
        cache_ttl_seconds: int = 300,
        log_path: Optional[Path] = None,
        *,
        history_cache_ttl_seconds: Optional[int] = None,
        persistent_history_cache_dir: Optional[Path] = None,
    ) -> None:
        self._providers: List[MarketProvider] = list(providers or [])
        self._cache: TTLCache[Quote] = TTLCache(ttl_seconds=cache_ttl_seconds)
        history_ttl = (
            cache_ttl_seconds
            if history_cache_ttl_seconds is None
            else history_cache_ttl_seconds
        )
        self._history_cache: TTLCache[PriceHistory] = TTLCache(
            ttl_seconds=history_ttl
        )
        self._persistent_history_cache = (
            PersistentHistoryCache(
                persistent_history_cache_dir,
                ttl_seconds=history_ttl,
            )
            if persistent_history_cache_dir is not None
            else None
        )
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
            quote = Quote.unavailable(normalized_ticker, error="no market provider registered")
            self._cache.set(normalized_ticker, quote)
            return quote

        last_error: Optional[str] = None
        for provider in self._providers:
            started = perf_counter()
            try:
                quote = provider.get_quote(normalized_ticker)
            except Exception as exc:
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
            provider=getattr(self._providers[-1], "name", self._providers[-1].__class__.__name__),
            error=last_error or "all providers unavailable",
        )
        self._cache.set(normalized_ticker, quote)
        return quote

    def get_history(self, ticker: str, *, days: int) -> PriceHistory:
        normalized_ticker = ticker.upper().strip()
        if not normalized_ticker:
            return PriceHistory.unavailable("", error="ticker is required")
        if isinstance(days, bool) or not isinstance(days, int) or days <= 0:
            return PriceHistory.unavailable(
                normalized_ticker,
                error="days must be a positive integer",
            )

        cache_key = f"{normalized_ticker}:{days}"
        cached = self._history_cache.get(cache_key)
        if cached is not None:
            return cached

        if self._persistent_history_cache is not None:
            try:
                persisted = self._persistent_history_cache.get(cache_key)
            except Exception:
                persisted = None
            if persisted is not None:
                self._history_cache.set(cache_key, persisted)
                return persisted

        if not self._providers:
            if self._persistent_history_cache is not None:
                try:
                    stale = self._persistent_history_cache.get_stale(cache_key)
                except Exception:
                    stale = None
                if stale is not None:
                    return PriceHistory(
                        ticker=stale.ticker,
                        currency=stale.currency,
                        provider=f"{stale.provider}:stale",
                        points=stale.points,
                        status="ok",
                        error="using stale last-good history; no market provider registered",
                    )
            return PriceHistory.unavailable(
                normalized_ticker,
                error="no market provider registered",
            )

        last_error: Optional[str] = None
        for provider in self._providers:
            provider_name = getattr(provider, "name", provider.__class__.__name__)
            get_history = getattr(provider, "get_history", None)
            if not callable(get_history):
                last_error = f"provider {provider_name} does not support history"
                continue

            started = perf_counter()
            try:
                history = get_history(normalized_ticker, days=days)
            except Exception as exc:
                last_error = str(exc)
                history = PriceHistory.unavailable(
                    normalized_ticker,
                    provider=provider_name,
                    error=last_error,
                )

            elapsed_ms = round((perf_counter() - started) * 1000, 2)
            self._logger.info(
                "market history request",
                extra={
                    "provider": history.provider,
                    "ticker": normalized_ticker,
                    "days": days,
                    "elapsed_ms": elapsed_ms,
                    "status": history.status,
                },
            )

            if history.status == "ok" and history.points:
                self._history_cache.set(cache_key, history)
                if self._persistent_history_cache is not None:
                    try:
                        self._persistent_history_cache.set(cache_key, history)
                    except Exception:
                        pass
                return history
            last_error = history.error or last_error

        if self._persistent_history_cache is not None:
            try:
                stale = self._persistent_history_cache.get_stale(cache_key)
            except Exception:
                stale = None
            if stale is not None:
                return PriceHistory(
                    ticker=stale.ticker,
                    currency=stale.currency,
                    provider=f"{stale.provider}:stale",
                    points=stale.points,
                    status="ok",
                    error="using stale last-good history after provider failure",
                )

        return PriceHistory.unavailable(
            normalized_ticker,
            provider=getattr(self._providers[-1], "name", self._providers[-1].__class__.__name__),
            error=last_error or "all providers unavailable",
        )

    def clear_cache(self, *, persistent: bool = False) -> None:
        self._cache.clear()
        self._history_cache.clear()
        if persistent and self._persistent_history_cache is not None:
            try:
                self._persistent_history_cache.clear()
            except Exception:
                pass
