"""Twelve Data provider for normalized ARGOS historical prices."""

from __future__ import annotations

import json
import time
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import urlopen

from backend.config.settings import get_setting

from .models import PriceHistory, PricePoint, Quote
from .provider_base import MarketProvider


class TwelveDataMarketProvider(MarketProvider):
    """Provide historical market data through Twelve Data."""

    name = "TwelveData"
    base_url = "https://api.twelvedata.com"

    def __init__(
        self,
        api_key=None,
        opener=None,
        *,
        sleep_fn=None,
        rate_limit_retries: int = 3,
        rate_limit_base_wait_seconds: float = 10.0,
    ) -> None:
        self.api_key = (
            api_key
            if api_key is not None
            else get_setting("TWELVE_DATA_API_KEY")
        )
        self._opener = opener or urlopen
        self._sleep = sleep_fn or time.sleep

        if (
            isinstance(rate_limit_retries, bool)
            or not isinstance(rate_limit_retries, int)
            or rate_limit_retries < 0
        ):
            raise ValueError(
                "rate_limit_retries must be a non-negative integer"
            )

        if (
            isinstance(rate_limit_base_wait_seconds, bool)
            or not isinstance(
                rate_limit_base_wait_seconds,
                (int, float),
            )
            or rate_limit_base_wait_seconds < 0
        ):
            raise ValueError(
                "rate_limit_base_wait_seconds must be non-negative"
            )

        self._rate_limit_retries = rate_limit_retries
        self._rate_limit_base_wait_seconds = float(
            rate_limit_base_wait_seconds
        )

    @staticmethod
    def _payload_is_rate_limited(payload) -> bool:
        if not isinstance(payload, dict):
            return False

        code = payload.get("code")

        try:
            numeric_code = int(code)
        except (TypeError, ValueError):
            numeric_code = None

        if numeric_code == 429:
            return True

        message = str(payload.get("message") or "").lower()

        return (
            "too many requests" in message
            or "rate limit" in message
            or "api credits" in message
        )

    def _rate_limit_wait(self, retry_number: int) -> float:
        return (
            self._rate_limit_base_wait_seconds
            * (2 ** retry_number)
        )

    def _get_once(self, path: str, **params):
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

    def _get(self, path: str, **params):
        last_rate_limit_error = None

        for attempt in range(
            self._rate_limit_retries + 1
        ):
            try:
                payload = self._get_once(
                    path,
                    **params,
                )
            except HTTPError as exc:
                if exc.code != 429:
                    raise

                last_rate_limit_error = exc

                if attempt >= self._rate_limit_retries:
                    raise

                self._sleep(
                    self._rate_limit_wait(attempt)
                )
                continue

            if not self._payload_is_rate_limited(payload):
                return payload

            last_rate_limit_error = RuntimeError(
                payload.get("message")
                or "Twelve Data rate limit exceeded"
            )

            if attempt >= self._rate_limit_retries:
                raise last_rate_limit_error

            self._sleep(
                self._rate_limit_wait(attempt)
            )

        if last_rate_limit_error is not None:
            raise last_rate_limit_error

        raise RuntimeError(
            "Twelve Data request failed"
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

        except HTTPError as exc:
            if exc.code == 429:
                error = (
                    "Twelve Data rate limit exceeded "
                    "after retries"
                )
            else:
                error = str(exc)

            return PriceHistory.unavailable(
                normalized,
                provider=self.name,
                error=error,
            )

        except Exception as exc:
            return PriceHistory.unavailable(
                normalized,
                provider=self.name,
                error=str(exc),
            )
