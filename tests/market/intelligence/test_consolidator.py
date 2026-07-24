import unittest
from datetime import datetime, timezone

from backend.market.intelligence.consolidator import MarketConsolidator
from backend.market.models import Quote


class MarketConsolidatorTest(unittest.TestCase):
    def test_returns_first_valid_quote(self):
        consolidator = MarketConsolidator()

        invalid_quote = Quote(
            ticker="NVDA",
            price=None,
            currency=None,
            provider="provider_a",
            timestamp=datetime.now(timezone.utc),
            status="unavailable",
        )

        valid_quote = Quote(
            ticker="NVDA",
            price=100.0,
            currency="USD",
            provider="provider_b",
            timestamp=datetime.now(timezone.utc),
            status="ok",
        )

        result = consolidator.consolidate([invalid_quote, valid_quote])

        self.assertEqual(result, valid_quote)


if __name__ == "__main__":
    unittest.main()