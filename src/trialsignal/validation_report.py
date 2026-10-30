"""Build a versionable evidence report without exposing raw registry payloads."""

from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import joblib

from .analytics import TrialAnalytics
from .data_quality import quality_summary
from .entity_resolution import SponsorResolver, evaluate_labels
from .survival import duration_benchmark


def build_report(
    database: str | Path,
    model_path: str | Path,
    labels_path: str | Path,
) -> dict:
    with sqlite3.connect(database) as connection:
        lineage = {
            "completed_runs": connection.execute(
                "SELECT COUNT(*) FROM ingestion_runs WHERE status='completed'"
            ).fetchone()[0],
            "query_memberships": connection.execute(
                "SELECT COUNT(*) FROM study_ingestion_runs"
            ).fetchone()[0],
        }
    resolver = SponsorResolver.from_database(database, threshold=85, margin=3)
    artifact = joblib.load(model_path)
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "overview": TrialAnalytics(database).overview(),
        "lineage": lineage,
        "data_quality": quality_summary(database),
        "entity_resolution_seed_evaluation": evaluate_labels(labels_path, resolver),
        "risk_model": artifact["metrics"],
        "phase3_duration_benchmark": duration_benchmark(database, phase="PHASE3"),
        "release_status": "development; not approved for clinical or automated decisions",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build TrialSignal validation evidence")
    parser.add_argument("--database", type=Path, default=Path("data/trialsignal.db"))
    parser.add_argument("--model", type=Path, default=Path("models/adverse_outcome.joblib"))
    parser.add_argument("--labels", type=Path, default=Path("data/sponsor_resolution_labels.csv"))
    parser.add_argument("--output", type=Path, default=Path("reports/validation.json"))
    args = parser.parse_args()
    report = build_report(args.database, args.model, args.labels)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
