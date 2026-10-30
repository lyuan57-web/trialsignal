import json
import tempfile
import unittest
from pathlib import Path

from trialsignal.analytics import TrialAnalytics, _condition_similarity
from trialsignal.clinicaltrials import parse_study
from trialsignal.data_quality import quality_summary
from trialsignal.store import TrialStore

FIXTURE = Path(__file__).parent / "fixtures" / "studies_response.json"


class QualityAndAnalyticsTests(unittest.TestCase):
    def test_condition_similarity_recovers_nested_registry_labels(self) -> None:
        self.assertEqual(_condition_similarity({"melanoma"}, {"cutaneous melanoma"}), 0.5)
        self.assertEqual(_condition_similarity({"melanoma"}, {"lung cancer"}), 0.0)

    def test_quality_contract_and_overview(self) -> None:
        raw = json.loads(FIXTURE.read_text())["studies"][0]
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "test.db"
            with TrialStore(database) as store:
                store.upsert(parse_study(raw), raw)
            quality = quality_summary(database)
            self.assertEqual(quality["errors"], 0)
            self.assertGreaterEqual(quality["total"], 10)
            overview = TrialAnalytics(database).overview()
            self.assertEqual(overview["totals"]["trials"], 1)
            results = TrialAnalytics(database).search("lung cancer")
            self.assertEqual(results[0]["nct_id"], "NCT00000001")


if __name__ == "__main__":
    unittest.main()
