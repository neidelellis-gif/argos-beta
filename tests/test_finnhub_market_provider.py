from __future__ import annotations

import json
from io import BytesIO

import pytest

from backend.market.finnhub_provider import FinnhubMarketProvider


class FakeResponse:
    def __init__(self, payload):
        self._buffer = BytesIO(json.dumps(payload).encode("utf-8"))

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return self._buffer.read()


def opener_for(payload):
    def opener(url, timeout=10):
        return FakeResponse(payload)

    return opener


def test_finnhub_provider_normalizes_quote():
    provider = FinnhubMarketProvider(
        api_key="test-key",
        opener=opener_for({
            "c": 182.50,
            "t": 1787144400,
        }),
    )

    quote = provider.get_quote(" nvda ")

    assert quote.ticker == "NVDA"
    assert quote.price == 182.50
    assert quote.currency == "USD"
    assert quote.provider == "Finnhub"
    assert quote.status == "ok"


def test_finnhub_provider_normalizes_daily_history():
    provider = FinnhubMarketProvider(
        api_key="test-key",
        opener=opener_for({
            "c": [100.0, 102.0, 101.0],
            "t": [
                1786924800,
                1787011200,
                1787097600,
            ],
            "s": "ok",
        }),
    )

    history = provider.get_history(" nvda ", days=3)

    assert history.ticker == "NVDA"
    assert history.currency == "USD"
    assert history.provider == "Finnhub"
    assert history.status == "ok"
    assert [point.close for point in history.points] == [
        100.0,
        102.0,
        101.0,
    ]
    assert len(history.points) == 3


def test_finnhub_history_no_data_returns_unavailable():
    provider = FinnhubMarketProvider(
        api_key="test-key",
        opener=opener_for({
            "s": "no_data",
        }),
    )

    history = provider.get_history("NVDA", days=30)

    assert history.status == "unavailable"
    assert history.points == ()
    assert "no historical data" in (history.error or "")


def test_finnhub_provider_requires_api_key():
    provider = FinnhubMarketProvider(
        api_key="",
        opener=opener_for({}),
    )

    quote = provider.get_quote("NVDA")
    history = provider.get_history("NVDA", days=30)

    assert quote.status == "unavailable"
    assert history.status == "unavailable"
    assert "FINNHUB_API_KEY" in (quote.error or "")
    assert "FINNHUB_API_KEY" in (history.error or "")


def test_finnhub_history_uses_daily_resolution_and_requested_period():
    seen = {}

    def opener(url, timeout=10):
        seen["url"] = url
        return FakeResponse({
            "c": [100.0, 101.0],
            "t": [1786924800, 1787011200],
            "s": "ok",
        })

    provider = FinnhubMarketProvider(
        api_key="test-key",
        opener=opener,
    )

    history = provider.get_history("NVDA", days=30)

    assert history.status == "ok"
    assert "stock/candle" in seen["url"]
    assert "symbol=NVDA" in seen["url"]
    assert "resolution=D" in seen["url"]
    assert "from=" in seen["url"]
    assert "to=" in seen["url"]
    assert "token=test-key" in seen["url"]


def test_finnhub_rejects_malformed_history_payload():
    provider = FinnhubMarketProvider(
        api_key="test-key",
        opener=opener_for({
            "c": [100.0, 101.0],
            "t": [1786924800],
            "s": "ok",
        }),
    )

    history = provider.get_history("NVDA", days=30)

    assert history.status == "unavailable"
    assert history.points == ()
    assert "invalid historical data" in (history.error or "")


def test_finnhub_skips_invalid_history_points_but_keeps_valid_ones():
    provider = FinnhubMarketProvider(
        api_key="test-key",
        opener=opener_for({
            "c": [100.0, -1.0, 102.0],
            "t": [
                1786924800,
                1787011200,
                1787097600,
            ],
            "s": "ok",
        }),
    )

    history = provider.get_history("NVDA", days=30)

    assert history.status == "ok"
    assert [point.close for point in history.points] == [
        100.0,
        102.0,
    ]


def test_finnhub_provider_integrates_with_market_connector():
    from backend.market import MarketConnector

    payloads = [
        {
            "c": 182.50,
            "t": 1787144400,
        },
        {
            "c": [180.0, 181.5, 182.5],
            "t": [
                1786924800,
                1787011200,
                1787097600,
            ],
            "s": "ok",
        },
    ]

    def opener(url, timeout=10):
        return FakeResponse(payloads.pop(0))

    connector = MarketConnector(
        providers=[
            FinnhubMarketProvider(
                api_key="test-key",
                opener=opener,
            )
        ]
    )

    quote = connector.get_quote("NVDA")
    history = connector.get_history("NVDA", days=30)

    assert quote.status == "ok"
    assert quote.price == 182.50

    assert history.status == "ok"
    assert [point.close for point in history.points] == [
        180.0,
        181.5,
        182.5,
    ]
