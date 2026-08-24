from __future__ import annotations

import json
from io import BytesIO

from backend.market.market_connector import MarketConnector
from backend.market.finnhub_provider import FinnhubMarketProvider
from backend.market.twelve_data_provider import (
    TwelveDataMarketProvider,
)


class FakeResponse:
    def __init__(self, payload):
        self._buffer = BytesIO(
            json.dumps(payload).encode("utf-8")
        )

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return self._buffer.read()


def opener_for(payload):
    def opener(url, timeout=20):
        return FakeResponse(payload)

    return opener


def test_twelve_data_normalizes_daily_history():
    provider = TwelveDataMarketProvider(
        api_key="test-key",
        opener=opener_for({
            "values": [
                {
                    "datetime": "2026-08-20",
                    "close": "420.10",
                },
                {
                    "datetime": "2026-08-21",
                    "close": "422.25",
                },
                {
                    "datetime": "2026-08-24",
                    "close": "425.27",
                },
            ]
        }),
    )

    history = provider.get_history(
        " gld ",
        days=252,
    )

    assert history.ticker == "GLD"
    assert history.currency == "USD"
    assert history.provider == "TwelveData"
    assert history.status == "ok"

    assert [point.close for point in history.points] == [
        420.10,
        422.25,
        425.27,
    ]


def test_twelve_data_requires_api_key():
    provider = TwelveDataMarketProvider(
        api_key="",
        opener=opener_for({}),
    )

    history = provider.get_history(
        "GLD",
        days=252,
    )

    assert history.status == "unavailable"
    assert "TWELVE_DATA_API_KEY" in (
        history.error or ""
    )


def test_twelve_data_rejects_invalid_days():
    provider = TwelveDataMarketProvider(
        api_key="test-key",
        opener=opener_for({}),
    )

    history = provider.get_history(
        "GLD",
        days=0,
    )

    assert history.status == "unavailable"
    assert "positive integer" in (
        history.error or ""
    )


def test_twelve_data_handles_api_error():
    provider = TwelveDataMarketProvider(
        api_key="test-key",
        opener=opener_for({
            "status": "error",
            "message": "symbol not found",
        }),
    )

    history = provider.get_history(
        "UNKNOWN",
        days=252,
    )

    assert history.status == "unavailable"
    assert history.error == "symbol not found"


def test_twelve_data_builds_expected_request():
    seen = {}

    def opener(url, timeout=20):
        seen["url"] = url
        return FakeResponse({
            "values": [
                {
                    "datetime": "2026-08-24",
                    "close": "425.27",
                }
            ]
        })

    provider = TwelveDataMarketProvider(
        api_key="test-key",
        opener=opener,
    )

    history = provider.get_history(
        "GLD",
        days=252,
    )

    assert history.status == "ok"
    assert "time_series" in seen["url"]
    assert "symbol=GLD" in seen["url"]
    assert "interval=1day" in seen["url"]
    assert "outputsize=252" in seen["url"]
    assert "order=ASC" in seen["url"]
    assert "apikey=test-key" in seen["url"]


def test_market_connector_falls_back_to_twelve_data_history():
    finnhub = FinnhubMarketProvider(
        api_key="test-key",
        opener=opener_for({}),
    )

    twelve = TwelveDataMarketProvider(
        api_key="test-key",
        opener=opener_for({
            "values": [
                {
                    "datetime": "2026-08-22",
                    "close": "423.00",
                },
                {
                    "datetime": "2026-08-24",
                    "close": "425.27",
                },
            ]
        }),
    )

    connector = MarketConnector(
        providers=[
            finnhub,
            twelve,
        ]
    )

    history = connector.get_history(
        "GLD",
        days=252,
    )

    assert history.status == "ok"
    assert history.provider == "TwelveData"
    assert [point.close for point in history.points] == [
        423.00,
        425.27,
    ]
