"""Finnhub provider for normalized ARGOS quotes and historical prices."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from urllib.parse import urlencode
from urllib.request import urlopen

from backend.config.settings import get_setting

from .models import PriceHistory, PricePoint, Quote
from .provider_base import MarketProvider


class FinnhubMarketProvider(MarketProvider):
    """Normalize Finnhub market data into ARGOS market models."""

    name = "Finnhub"
    base_url = "https://finnhub.io/api/v1"

    def __init__(self, api_key=None, opener=None) -> None:
        self.api_key = (
            api_key
            if api_key is not None
            else get_setting("FINNHUB_API_KEY")
        )
        self._opener = opener or urlopen

    def _get(self, path: str, **params):
        if not self.api_key:
            raise RuntimeError("FINNHUB_API_KEY não configurada")

        params["token"] = self.api_key
        url = f"{self.base_url}/{path}?{urlencode(params)}"

        with self._opener(url, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))

    def get_quote(self, ticker: str) -> Quote:
        normalized = ticker.upper().strip()

        if not normalized:
            return Quote.unavailable(
                "",
                provider=self.name,
                error="ticker is required",
            )

        if not self.api_key:
            return Quote.unavailable(
                normalized,
                provider=self.name,
                error="FINNHUB_API_KEY não configurada",
            )

        try:
            payload = self._get(
                "quote",
                symbol=normalized,
            )

            price = payload.get("c")
            timestamp = payload.get("t")

            if not isinstance(price, (int, float)) or price <= 0:
                return Quote.unavailable(
                    normalized,
                    provider=self.name,
                    error="quote unavailable",
                )

            if isinstance(timestamp, (int, float)) and timestamp > 0:
                observed_at = datetime.fromtimestamp(
                    timestamp,
                    timezone.utc,
                )
            else:
                observed_at = datetime.now(timezone.utc)

            return Quote(
                ticker=normalized,
                price=float(price),
                currency="USD",
                provider=self.name,
                timestamp=observed_at,
                status="ok",
            )
        except Exception as exc:
            return Quote.unavailable(
                normalized,
                provider=self.name,
                error=str(exc),
            )

    def get_history(
        self,
        ticker: str,
        *,
        days: int,
    ) -> PriceHistory:
        normalized = ticker.upper().strip()

        if not normalized:
            return PriceHistory.unavailable(
                "",
                provider=self.name,
                error="ticker is required",
            )

        if isinstance(days, bool) or not isinstance(days, int) or days <= 0:
            return PriceHistory.unavailable(
                normalized,
                provider=self.name,
                error="days must be a positive integer",
            )

        if not self.api_key:
            return PriceHistory.unavailable(
                normalized,
                provider=self.name,
                error="FINNHUB_API_KEY não configurada",
            )

        now = datetime.now(timezone.utc)
        start = now - timedelta(days=days)

        try:
            payload = self._get(
                "stock/candle",
                symbol=normalized,
                resolution="D",
                **{
                    "from": int(start.timestamp()),
                    "to": int(now.timestamp()),
                },
            )

            if payload.get("s") != "ok":
                return PriceHistory.unavailable(
                    normalized,
                    provider=self.name,
                    error="no historical data",
                )

            closes = payload.get("c")
            timestamps = payload.get("t")

            if (
                not isinstance(closes, list)
                or not isinstance(timestamps, list)
                or not closes
                or len(closes) != len(timestamps)
            ):
                return PriceHistory.unavailable(
                    normalized,
                    provider=self.name,
                    error="invalid historical data",
                )

            points = []

            for timestamp, close in zip(timestamps, closes):
                if (
                    not isinstance(timestamp, (int, float))
                    or not isinstance(close, (int, float))
                    or close <= 0
                ):
                    continue

                reference = datetime.fromtimestamp(
                    timestamp,
                    timezone.utc,
                ).date()

                points.append(
                    PricePoint(
                        date=reference.isoformat(),
                        close=float(close),
                    )
                )

            if not points:
                return PriceHistory.unavailable(
                    normalized,
                    provider=self.name,
                    error="no historical data",
                )

            return PriceHistory(
                ticker=normalized,
                currency="USD",
                provider=self.name,
                points=tuple(points),
                status="ok",
            )
        except Exception as exc:
            return PriceHistory.unavailable(
                normalized,
                provider=self.name,
                error=str(exc),
            )
