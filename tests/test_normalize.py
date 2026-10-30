import unittest

from trialsignal.normalize import normalize_sponsor, normalize_text


class NormalizeTests(unittest.TestCase):
    def test_sponsor_suffix_variants_share_blocking_key(self) -> None:
        self.assertEqual(
            normalize_sponsor("Pfizer, Inc."), normalize_sponsor("PFIZER Incorporated")
        )

    def test_normalize_text_handles_accents_and_punctuation(self) -> None:
        self.assertEqual(normalize_text("Hôpital  Saint-Louis"), "hopital saint louis")


if __name__ == "__main__":
    unittest.main()
