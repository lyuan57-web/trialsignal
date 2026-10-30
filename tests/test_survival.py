import unittest
from datetime import date

from trialsignal.survival import kaplan_meier, parse_partial_date


class SurvivalTests(unittest.TestCase):
    def test_partial_date_defaults(self) -> None:
        self.assertEqual(parse_partial_date("2024"), date(2024, 7, 15))
        self.assertEqual(parse_partial_date("2024-02"), date(2024, 2, 15))
        self.assertEqual(parse_partial_date("2024-02-03"), date(2024, 2, 3))

    def test_kaplan_meier_handles_censoring(self) -> None:
        curve = kaplan_meier([(10, True), (10, False), (20, True), (30, False)])
        self.assertEqual(curve[1]["at_risk"], 4)
        self.assertAlmostEqual(curve[1]["survival"], 0.75)
        self.assertEqual(curve[1]["events"], 1)
        self.assertEqual(curve[1]["censored"], 1)
        self.assertAlmostEqual(curve[2]["survival"], 0.375)


if __name__ == "__main__":
    unittest.main()
