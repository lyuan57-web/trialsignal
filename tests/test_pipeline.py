import json
import tempfile
import unittest
from pathlib import Path

from trialsignal.clinicaltrials import parse_study
from trialsignal.store import TrialStore

FIXTURE = Path(__file__).parent / "fixtures" / "studies_response.json"


class PipelineTests(unittest.TestCase):
    def test_parse_and_idempotent_snapshot(self) -> None:
        raw = json.loads(FIXTURE.read_text())["studies"][0]
        record = parse_study(raw)
        self.assertEqual(record.nct_id, "NCT00000001")
        self.assertEqual(record.enrollment_count, 480)
        self.assertEqual(record.countries, ("Canada", "United States"))

        with (
            tempfile.TemporaryDirectory() as directory,
            TrialStore(Path(directory) / "test.db") as store,
        ):
            self.assertTrue(store.upsert(record, raw))
            self.assertFalse(store.upsert(record, raw))
            self.assertEqual(
                store.summary(),
                {"studies": 1, "sponsors": 1, "conditions": 1, "study_snapshots": 1},
            )


if __name__ == "__main__":
    unittest.main()
