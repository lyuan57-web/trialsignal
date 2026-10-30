import unittest

from trialsignal.risk_model import calibration_bins, row_to_features


class RiskModelTests(unittest.TestCase):
    def test_feature_policy_excludes_outcomes(self) -> None:
        row = {
            "overall_status": "TERMINATED",
            "completion_date": "2024-01-01",
            "why_stopped": "Slow enrollment",
            "enrollment_type": "ACTUAL",
            "phases_json": '["PHASE3"]',
            "interventions_json": '["Example Drug"]',
            "intervention_types_json": '["DRUG"]',
            "countries_json": '["United States"]',
            "condition_count": 1,
            "enrollment_count": 100,
            "location_count": 5,
            "start_date": "2020-01-01",
        }
        features = row_to_features(row)
        for prohibited in ("overall_status", "completion_date", "why_stopped", "enrollment_type"):
            self.assertNotIn(prohibited, features)

    def test_calibration_bins_cover_all_rows(self) -> None:
        bins = calibration_bins([0, 0, 1, 1], [0.1, 0.2, 0.8, 0.9], bins=2)
        self.assertEqual(sum(item["n"] for item in bins), 4)
        self.assertEqual(bins[0]["observed_rate"], 0)
        self.assertEqual(bins[1]["observed_rate"], 1)


if __name__ == "__main__":
    unittest.main()
