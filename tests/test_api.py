import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from trialsignal import api
from trialsignal.clinicaltrials import parse_study
from trialsignal.store import TrialStore

FIXTURE = Path(__file__).parent / "fixtures" / "studies_response.json"


class ApiTests(unittest.TestCase):
    def test_health_search_quality_and_comparables(self) -> None:
        raw = json.loads(FIXTURE.read_text())["studies"][0]
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "test.db"
            with TrialStore(database) as store:
                store.upsert(parse_study(raw), raw)
            with patch.object(api, "DEFAULT_DATABASE", database):
                client = TestClient(api.app)
                self.assertEqual(client.get("/health").status_code, 200)
                search = client.get("/trials/search", params={"condition": "lung cancer"})
                self.assertEqual(search.status_code, 200)
                self.assertEqual(search.json()[0]["nct_id"], "NCT00000001")
                filtered = client.get(
                    "/trials/search",
                    params={
                        "phase": "PHASE3",
                        "country": "Canada",
                        "sponsor": "Example Therapeutics",
                        "study_type": "INTERVENTIONAL",
                    },
                )
                self.assertEqual(filtered.status_code, 200)
                self.assertEqual(filtered.json()[0]["nct_id"], "NCT00000001")
                self.assertEqual(client.get("/quality").json()["errors"], 0)
                comparable = client.get("/trials/NCT00000001/comparables")
                self.assertEqual(comparable.status_code, 200)
                self.assertEqual(comparable.json(), [])


if __name__ == "__main__":
    unittest.main()
