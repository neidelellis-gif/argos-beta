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
