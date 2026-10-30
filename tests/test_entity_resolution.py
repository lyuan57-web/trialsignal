import unittest

from trialsignal.entity_resolution import SponsorResolver


class SponsorResolverTests(unittest.TestCase):
    def setUp(self) -> None:
        self.resolver = SponsorResolver(
            ["Pfizer", "AstraZeneca", "Memorial Sloan Kettering Cancer Center"],
            threshold=85,
            margin=3,
        )

    def test_exact_normalized_match(self) -> None:
        result = self.resolver.resolve("Pfizer, Inc.")
        self.assertTrue(result.accepted)
        self.assertEqual(result.canonical_name, "Pfizer")
        self.assertEqual(result.method, "exact_normalized")

    def test_fuzzy_match(self) -> None:
        result = self.resolver.resolve("Memorial Sloan-Kettering Cancer Ctr")
        self.assertTrue(result.accepted)
        self.assertEqual(result.canonical_name, "Memorial Sloan Kettering Cancer Center")

    def test_ambiguous_or_low_score_abstains(self) -> None:
        result = self.resolver.resolve("Completely Different Organization")
        self.assertFalse(result.accepted)
        self.assertIsNone(result.canonical_name)


if __name__ == "__main__":
    unittest.main()
