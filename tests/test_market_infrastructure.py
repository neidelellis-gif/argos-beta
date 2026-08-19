from __future__ import annotations

import unittest
from datetime import datetime, timezone

from backend.market import MarketConnector, MarketProvider, Quote


class DummyProvider(MarketProvider):
    name = "dummy"

    def __init__(self) -> None:
        self.calls = 0

    def get_quote(self, ticker: str) -> Quote:
        self.calls += 1
        return Quote(
            ticker=ticker,
            price=123.45,
            currency="USD",
            provider=self.name,
            timestamp=datetime.now(timezone.utc),
            status="ok",
        )


class FailingProvider(MarketProvider):
    name = "failing"

    def get_quote(self, ticker: str) -> Quote:
        raise RuntimeError("provider offline")


class MarketInfrastructureTests(unittest.TestCase):
    def test_returns_normalized_quote(self) -> None:
        connector = MarketConnector(providers=[DummyProvider()])
        quote = connector.get_quote(" nvda ")
        self.assertEqual(quote.ticker, "NVDA")
        self.assertEqual(quote.price, 123.45)
        self.assertEqual(quote.status, "ok")

    def test_cache_prevents_duplicate_provider_calls(self) -> None:
        provider = DummyProvider()
        connector = MarketConnector(providers=[provider])
        connector.get_quote("NVDA")
        connector.get_quote("NVDA")
        self.assertEqual(provider.calls, 1)

    def test_provider_failure_does_not_break_connector(self) -> None:
        connector = MarketConnector(providers=[FailingProvider()])
        quote = connector.get_quote("NVDA")
        self.assertEqual(quote.status, "unavailable")
        self.assertIn("provider offline", quote.error or "")

    def test_without_provider_returns_unavailable(self) -> None:
        connector = MarketConnector()
        quote = connector.get_quote("NVDA")
        self.assertEqual(quote.status, "unavailable")
        self.assertIsNone(quote.price)


if __name__ == "__main__":
    unittest.main()


class DummyHistoryProvider(DummyProvider):
    def get_history(self, ticker: str, *, days: int):
        from backend.market import PriceHistory, PricePoint

        return PriceHistory(
            ticker=ticker,
            currency="USD",
            provider=self.name,
            points=(
                PricePoint(date="2026-08-17", close=100.0),
                PricePoint(date="2026-08-18", close=102.0),
                PricePoint(date="2026-08-19", close=101.0),
            ),
            status="ok",
        )


class FailingHistoryProvider(DummyProvider):
    def get_history(self, ticker: str, *, days: int):
        raise RuntimeError("history provider offline")


def test_returns_normalized_price_history():
    connector = MarketConnector(
        providers=[DummyHistoryProvider()]
    )

    history = connector.get_history(" nvda ", days=3)

    assert history.ticker == "NVDA"
    assert history.status == "ok"
    assert history.currency == "USD"
    assert [point.close for point in history.points] == [
        100.0,
        102.0,
        101.0,
    ]


def test_history_provider_failure_does_not_break_connector():
    connector = MarketConnector(
        providers=[FailingHistoryProvider()]
    )

    history = connector.get_history("NVDA", days=30)

    assert history.status == "unavailable"
    assert history.points == ()
    assert "history provider offline" in (history.error or "")


def test_history_without_provider_returns_unavailable():
    connector = MarketConnector()

    history = connector.get_history("NVDA", days=30)

    assert history.status == "unavailable"
    assert history.points == ()
