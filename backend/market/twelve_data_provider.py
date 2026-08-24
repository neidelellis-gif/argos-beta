"""Twelve Data provider for normalized ARGOS historical prices."""

from __future__ import annotations

import json
from urllib.parse import urlencode
from urllib.request import urlopen

from backend.config.settings import get_setting

from .models import PriceHistory, PricePoint, Quote
from .provider_base import MarketProvider


class TwelveDataMarketProvider(MarketProvider):
    """Provide historical market data through Twelve Data."""

    name = "TwelveData"
    base_url = "https://api.twelvedata.com"

    def __init__(self, api_key=None, opener=None) -> None:
        self.api_key = (
            api_key
            if api_key is not None
            else get_setting("TWELVE_DATA_API_KEY")
        )
        self._opener = opener or urlopen

    def _get(self, path: str, **params):
        if not self.api_key:
            raise RuntimeError(
                "TWELVE_DATA_API_KEY não configurada"
            )

        params["apikey"] = self.api_key
        url = f"{self.base_url}/{path}?{urlencode(params)}"

        with self._opener(url, timeout=20) as response:
            return json.loads(
                response.read().decode("utf-8")
            )

    def get_quote(self, ticker: str) -> Quote:
        normalized = ticker.upper().strip()

        return Quote.unavailable(
            normalized,
            provider=self.name,
            error="quote not provided by TwelveData fallback",
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

        if (
            isinstance(days, bool)
            or not isinstance(days, int)
            or days <= 0
        ):
            return PriceHistory.unavailable(
                normalized,
                provider=self.name,
                error="days must be a positive integer",
            )

        if not self.api_key:
            return PriceHistory.unavailable(
                normalized,
                provider=self.name,
                error="TWELVE_DATA_API_KEY não configurada",
            )

        try:
            payload = self._get(
                "time_series",
                symbol=normalized,
                interval="1day",
                outputsize=days,
                order="ASC",
            )

            if payload.get("status") == "error":
                return PriceHistory.unavailable(
                    normalized,
                    provider=self.name,
                    error=payload.get("message")
                    or "historical data unavailable",
                )

            values = payload.get("values")

            if not isinstance(values, list) or not values:
                return PriceHistory.unavailable(
                    normalized,
                    provider=self.name,
                    error="no historical data",
                )

            points = []

            for value in values:
                if not isinstance(value, dict):
                    continue

                date = value.get("datetime")
                close = value.get("close")

                if not isinstance(date, str):
                    continue

                try:
                    close_value = float(close)
                except (TypeError, ValueError):
                    continue

                if close_value <= 0:
                    continue

                points.append(
                    PricePoint(
                        date=date,
                        close=close_value,
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
