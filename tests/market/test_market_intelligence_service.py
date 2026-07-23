import unittest

from backend.market import (
    MarketConnector,
    MarketIntelligence,
    MarketIntelligenceService,
)


class DummyProvider:
    name = "dummy"

    def get_quote(self, ticker):
        from backend.market.models import Quote

        return Quote(
            ticker=ticker,
            price=100.0,
            currency="USD",
            provider=self.name,
        )


class MarketIntelligenceServiceTest(unittest.TestCase):
    def test_returns_market_intelligence(self):
        connector = MarketConnector([DummyProvider()])
        service = MarketIntelligenceService(connector)

        result = service.get_market_intelligence("NVDA")

        self.assertIsInstance(result, MarketIntelligence)
        self.assertEqual(result.quote.ticker, "NVDA")
        self.assertEqual(result.confidence, 1.0)
        self.assertEqual(result.sources_consulted, 1)
        self.assertEqual(result.sources_confirmed, 1)
        self.assertEqual(result.quality_status, "validated")


if __name__ == "__main__":
    unittest.main()
