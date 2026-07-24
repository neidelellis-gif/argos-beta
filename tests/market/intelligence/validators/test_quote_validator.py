import unittest
from datetime import datetime, timezone

from backend.market.intelligence.validators.quote_validator import QuoteValidator
from backend.market.models import Quote


class QuoteValidatorTest(unittest.TestCase):
    def test_valid_quote(self):
        validator = QuoteValidator()

        quote = Quote(
            ticker="NVDA",
            price=100.0,
            currency="USD",
            provider="test",
            timestamp=datetime.now(timezone.utc),
            status="ok",
        )

        self.assertTrue(validator.is_valid(quote))

    def test_invalid_quote_without_price(self):
        validator = QuoteValidator()

        quote = Quote(
            ticker="NVDA",
            price=None,
            currency="USD",
            provider="test",
            timestamp=datetime.now(timezone.utc),
            status="ok",
        )

        self.assertFalse(validator.is_valid(quote))


if __name__ == "__main__":
    unittest.main()
