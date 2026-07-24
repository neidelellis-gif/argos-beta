import unittest
from datetime import datetime, timezone

from backend.market.intelligence.rules.source_consensus import SourceConsensusRule
from backend.market.models import Quote


class SourceConsensusRuleTest(unittest.TestCase):
    def test_returns_false_with_one_quote(self):
        rule = SourceConsensusRule()

        result = rule.evaluate([
            Quote(
                ticker="NVDA",
                price=100.0,
                currency="USD",
                provider="test",
                timestamp=datetime.now(timezone.utc),
                status="ok",
            )
        ])

        self.assertFalse(result)

    def test_returns_true_with_two_quotes(self):
        rule = SourceConsensusRule()

        result = rule.evaluate([
            Quote(
                ticker="NVDA",
                price=100.0,
                currency="USD",
                provider="a",
                timestamp=datetime.now(timezone.utc),
                status="ok",
            ),
            Quote(
                ticker="NVDA",
                price=100.0,
                currency="USD",
                provider="b",
                timestamp=datetime.now(timezone.utc),
                status="ok",
            ),
        ])

        self.assertTrue(result)


if __name__ == "__main__":
    unittest.main()
