"""Executable data contracts for the landing warehouse."""

from __future__ import annotations

import argparse
import json
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class CheckResult:
    name: str
    severity: str
    failed_rows: int
    passed: bool
    description: str

    def to_dict(self) -> dict:
        return asdict(self)


CHECKS = (
    (
        "missing_title",
        "error",
        "SELECT COUNT(*) FROM studies WHERE trim(title) = ''",
        "Every study needs a title.",
    ),
    (
        "unknown_sponsor",
        "warning",
        "SELECT COUNT(*) FROM studies WHERE sponsor_name_raw = 'Unknown'",
        "Lead sponsor should be present.",
    ),
    (
        "missing_status",
        "error",
        "SELECT COUNT(*) FROM studies WHERE trim(overall_status) = ''",
        "Status is required.",
    ),
    (
        "negative_enrollment",
        "error",
        "SELECT COUNT(*) FROM studies WHERE enrollment_count < 0",
        "Enrollment cannot be negative.",
    ),
    (
        "missing_condition",
        "error",
        "SELECT COUNT(*) FROM studies s LEFT JOIN study_conditions sc USING(nct_id) WHERE sc.nct_id IS NULL",
        "Every analytical trial needs a condition.",
    ),
    (
        "missing_snapshot",
        "error",
        "SELECT COUNT(*) FROM studies s LEFT JOIN study_snapshots x USING(nct_id) WHERE x.nct_id IS NULL",
        "Every current row must be traceable to raw data.",
    ),
    (
        "orphan_condition_link",
        "error",
        "SELECT COUNT(*) FROM study_conditions sc LEFT JOIN conditions c USING(condition_id) WHERE c.condition_id IS NULL",
        "Condition links must satisfy referential integrity.",
    ),
    (
        "completed_without_completion_date",
        "warning",
        "SELECT COUNT(*) FROM studies WHERE overall_status = 'COMPLETED' AND completion_date IS NULL",
        "Completed studies should generally report completion date.",
    ),
    (
        "start_after_completion",
        "error",
        "SELECT COUNT(*) FROM studies WHERE length(start_date) >= 7 AND length(completion_date) >= 7 AND substr(start_date,1,7) > substr(completion_date,1,7)",
        "Start must not follow completion.",
    ),
    (
        "interventional_without_intervention",
        "warning",
        "SELECT COUNT(*) FROM studies WHERE study_type = 'INTERVENTIONAL' AND interventions_json = '[]'",
        "Interventional studies generally identify an intervention.",
    ),
    (
        "terminated_without_reason",
        "warning",
        "SELECT COUNT(*) FROM studies WHERE overall_status = 'TERMINATED' AND (why_stopped IS NULL OR trim(why_stopped) = '')",
        "Terminated studies should be reviewed for a reason.",
    ),
    (
        "duplicate_snapshot_hash",
        "error",
        "SELECT COUNT(*) FROM (SELECT nct_id,payload_hash,COUNT(*) n FROM study_snapshots GROUP BY 1,2 HAVING n>1)",
        "Identical snapshots must be deduplicated.",
    ),
    (
        "unfinished_ingestion_run",
        "warning",
        "SELECT COUNT(*) FROM ingestion_runs WHERE status = 'running'",
        "A run left in progress may indicate an interrupted pipeline.",
    ),
    (
        "completed_run_count_mismatch",
        "error",
        "SELECT COUNT(*) FROM ingestion_runs r WHERE r.status='completed' AND r.records_processed != (SELECT COUNT(*) FROM study_ingestion_runs x WHERE x.run_id=r.run_id)",
        "Completed-run counts must reconcile to lineage membership.",
    ),
    (
        "study_without_ingestion_lineage",
        "warning",
        "SELECT COUNT(*) FROM studies s LEFT JOIN study_ingestion_runs r USING(nct_id) WHERE r.nct_id IS NULL",
        "Every production study should be attributable to at least one ingestion run.",
    ),
)


def run_checks(path: str | Path) -> list[CheckResult]:
    results: list[CheckResult] = []
    with sqlite3.connect(path) as connection:
        for name, severity, query, description in CHECKS:
            failed = int(connection.execute(query).fetchone()[0])
            results.append(CheckResult(name, severity, failed, failed == 0, description))
        fk_failures = len(connection.execute("PRAGMA foreign_key_check").fetchall())
        results.append(
            CheckResult(
                "foreign_key_integrity",
                "error",
                fk_failures,
                fk_failures == 0,
                "All foreign keys must resolve.",
            )
        )
    return results


def quality_summary(path: str | Path) -> dict:
    results = run_checks(path)
    return {
        "checks": [result.to_dict() for result in results],
        "total": len(results),
        "passed": sum(result.passed for result in results),
        "errors": sum(not result.passed and result.severity == "error" for result in results),
        "warnings": sum(not result.passed and result.severity == "warning" for result in results),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Execute TrialSignal data contracts")
    parser.add_argument("--database", type=Path, default=Path("data/trialsignal.db"))
    args = parser.parse_args()
    summary = quality_summary(args.database)
    print(json.dumps(summary, indent=2))
    if summary["errors"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
