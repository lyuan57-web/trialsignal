"""Command-line entry point for the first TrialSignal ingestion slice."""

from __future__ import annotations

import argparse
import json
from collections.abc import Iterable
from pathlib import Path

from .clinicaltrials import API_URL, fetch_studies, parse_study
from .store import TrialStore


def load_fixture(path: Path) -> Iterable[dict]:
    payload = json.loads(path.read_text())
    return payload.get("studies", [])


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest ClinicalTrials.gov records")
    parser.add_argument("--condition", default="non-small cell lung cancer")
    parser.add_argument("--max-studies", type=int, default=100)
    parser.add_argument("--database", type=Path, default=Path("data/trialsignal.db"))
    parser.add_argument("--fixture", type=Path)
    args = parser.parse_args()

    studies = (
        load_fixture(args.fixture)
        if args.fixture
        else fetch_studies(args.condition, max_studies=args.max_studies)
    )
    processed = 0
    changed = 0
    with TrialStore(args.database) as store:
        run_id = store.start_ingestion(
            source=str(args.fixture) if args.fixture else API_URL,
            query_condition=args.condition,
            requested_max=1 if args.fixture else args.max_studies,
        )
        try:
            for raw_study in studies:
                processed += 1
                record = parse_study(raw_study)
                changed += int(store.upsert(record, raw_study))
                store.link_ingestion(run_id, record.nct_id, processed)
        except Exception:
            store.finish_ingestion(run_id, "failed", processed, changed)
            raise
        store.finish_ingestion(run_id, "completed", processed, changed)
        summary = store.summary()

    print(
        json.dumps(
            {"run_id": run_id, "processed": processed, "new_snapshots": changed, **summary},
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
