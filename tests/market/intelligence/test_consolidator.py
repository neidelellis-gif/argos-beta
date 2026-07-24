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

    def test_raises_error_when_no_valid_quotes_exist(self):
        consolidator = MarketConsolidator()

        quotes = [
            Quote(
                ticker="NVDA",
                price=None,
                currency=None,
                provider="provider_a",
                timestamp=datetime.now(timezone.utc),
                status="unavailable",
            ),
            Quote(
                ticker="NVDA",
                price=None,
                currency=None,
                provider="provider_b",
                timestamp=datetime.now(timezone.utc),
                status="unavailable",
            ),
        ]

        with self.assertRaises(ValueError):
            consolidator.consolidate(quotes)

    def test_returns_most_recent_valid_quote(self):
        consolidator = MarketConsolidator()

        older_quote = Quote(
            ticker="NVDA",
            price=100.0,
            currency="USD",
            provider="provider_a",
            timestamp=datetime(2026, 7, 24, 10, 0, tzinfo=timezone.utc),
            status="ok",
        )

        newer_quote = Quote(
            ticker="NVDA",
            price=101.0,
            currency="USD",
            provider="provider_b",
            timestamp=datetime(2026, 7, 24, 11, 0, tzinfo=timezone.utc),
            status="ok",
        )

        result = consolidator.consolidate([older_quote, newer_quote])

        self.assertEqual(result, newer_quote)

    def test_tie_uses_provider_name(self):
        consolidator = MarketConsolidator()

        quote_b = Quote(
            ticker="NVDA",
            price=101.0,
            currency="USD",
            provider="z_provider",
            timestamp=datetime(2026, 7, 24, 11, 0, tzinfo=timezone.utc),
            status="ok",
        )

        quote_a = Quote(
            ticker="NVDA",
            price=100.0,
            currency="USD",
            provider="a_provider",
            timestamp=datetime(2026, 7, 24, 11, 0, tzinfo=timezone.utc),
            status="ok",
        )

        result = consolidator.consolidate([quote_b, quote_a])

        self.assertEqual(result, quote_a)


if __name__ == "__main__":
    unittest.main()