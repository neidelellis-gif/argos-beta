import unittest

from backend.market.intelligence import ConfidenceEvaluator


class ConfidenceEvaluatorTest(unittest.TestCase):
    def test_validated_when_all_sources_confirm(self):
        result = ConfidenceEvaluator().evaluate(
            sources_consulted=3,
            sources_confirmed=3,
        )

        self.assertEqual(result.status, "validated")
        self.assertEqual(result.score, 1.0)

    def test_partial_when_half_confirm(self):
        result = ConfidenceEvaluator().evaluate(
            sources_consulted=4,
            sources_confirmed=2,
        )

        self.assertEqual(result.status, "partial")

    def test_low_when_few_confirm(self):
        result = ConfidenceEvaluator().evaluate(
            sources_consulted=4,
            sources_confirmed=1,
        )

        self.assertEqual(result.status, "low")

    def test_invalid_when_no_sources(self):
        result = ConfidenceEvaluator().evaluate(
            sources_consulted=0,
            sources_confirmed=0,
        )

        self.assertEqual(result.status, "invalid")


if __name__ == "__main__":
    unittest.main()
