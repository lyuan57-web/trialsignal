"""Auditable SQLite landing warehouse for the first vertical slice."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Self

from .clinicaltrials import TrialRecord
from .normalize import normalize_sponsor, normalize_text

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS sponsors (
    sponsor_id INTEGER PRIMARY KEY,
    normalized_name TEXT NOT NULL UNIQUE,
    canonical_name TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS studies (
    nct_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    sponsor_id INTEGER NOT NULL REFERENCES sponsors(sponsor_id),
    sponsor_name_raw TEXT NOT NULL,
    sponsor_class TEXT,
    overall_status TEXT NOT NULL,
    study_type TEXT,
    phases_json TEXT NOT NULL,
    interventions_json TEXT NOT NULL,
    intervention_types_json TEXT NOT NULL DEFAULT '[]',
    countries_json TEXT NOT NULL,
    location_count INTEGER NOT NULL DEFAULT 0,
    start_date TEXT,
    primary_completion_date TEXT,
    completion_date TEXT,
    enrollment_count INTEGER,
    enrollment_type TEXT,
    allocation TEXT,
    intervention_model TEXT,
    primary_purpose TEXT,
    masking TEXT,
    sex TEXT,
    minimum_age TEXT,
    maximum_age TEXT,
    healthy_volunteers INTEGER,
    why_stopped TEXT,
    last_update_post_date TEXT,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS conditions (
    condition_id INTEGER PRIMARY KEY,
    normalized_name TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS study_conditions (
    nct_id TEXT NOT NULL REFERENCES studies(nct_id) ON DELETE CASCADE,
    condition_id INTEGER NOT NULL REFERENCES conditions(condition_id),
    PRIMARY KEY (nct_id, condition_id)
);

CREATE TABLE IF NOT EXISTS study_snapshots (
    snapshot_id INTEGER PRIMARY KEY,
    nct_id TEXT NOT NULL REFERENCES studies(nct_id) ON DELETE CASCADE,
    observed_at TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    raw_json TEXT NOT NULL,
    UNIQUE (nct_id, payload_hash)
);

CREATE TABLE IF NOT EXISTS ingestion_runs (
    run_id INTEGER PRIMARY KEY,
    source TEXT NOT NULL,
    query_condition TEXT NOT NULL,
    requested_max INTEGER NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    status TEXT NOT NULL CHECK(status IN ('running', 'completed', 'failed')),
    records_processed INTEGER NOT NULL DEFAULT 0,
    new_snapshots INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS study_ingestion_runs (
    run_id INTEGER NOT NULL REFERENCES ingestion_runs(run_id) ON DELETE CASCADE,
    nct_id TEXT NOT NULL REFERENCES studies(nct_id) ON DELETE CASCADE,
    source_rank INTEGER NOT NULL,
    PRIMARY KEY (run_id, nct_id)
);

CREATE INDEX IF NOT EXISTS idx_studies_status ON studies(overall_status);
CREATE INDEX IF NOT EXISTS idx_studies_sponsor ON studies(sponsor_id);
CREATE INDEX IF NOT EXISTS idx_snapshots_study_time ON study_snapshots(nct_id, observed_at);
CREATE INDEX IF NOT EXISTS idx_run_membership_study ON study_ingestion_runs(nct_id);
"""


class TrialStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.executescript(SCHEMA)
        self._migrate_existing_database()

    def _migrate_existing_database(self) -> None:
        """Apply additive local migrations so earlier demo databases still open."""
        existing = {
            row[1] for row in self.connection.execute("PRAGMA table_info(studies)").fetchall()
        }
        additions = {
            "intervention_types_json": "TEXT NOT NULL DEFAULT '[]'",
            "location_count": "INTEGER NOT NULL DEFAULT 0",
            "allocation": "TEXT",
            "intervention_model": "TEXT",
            "primary_purpose": "TEXT",
            "masking": "TEXT",
            "sex": "TEXT",
            "minimum_age": "TEXT",
            "maximum_age": "TEXT",
            "healthy_volunteers": "INTEGER",
            "why_stopped": "TEXT",
            "last_update_post_date": "TEXT",
        }
        for name, sql_type in additions.items():
            if name not in existing:
                self.connection.execute(f"ALTER TABLE studies ADD COLUMN {name} {sql_type}")
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _upsert_sponsor(self, name: str, observed_at: str) -> int:
        normalized = normalize_sponsor(name) or normalize_text(name) or "unknown"
        self.connection.execute(
            """
            INSERT INTO sponsors(normalized_name, canonical_name, created_at)
            VALUES (?, ?, ?)
            ON CONFLICT(normalized_name) DO UPDATE SET
                canonical_name = CASE
                    WHEN length(excluded.canonical_name) > length(canonical_name)
                    THEN excluded.canonical_name ELSE canonical_name END
            """,
            (normalized, name, observed_at),
        )
        row = self.connection.execute(
            "SELECT sponsor_id FROM sponsors WHERE normalized_name = ?", (normalized,)
        ).fetchone()
        assert row is not None
        return int(row[0])

    def start_ingestion(self, source: str, query_condition: str, requested_max: int) -> int:
        started_at = datetime.now(UTC).isoformat()
        cursor = self.connection.execute(
            """
            INSERT INTO ingestion_runs(source, query_condition, requested_max, started_at, status)
            VALUES (?, ?, ?, ?, 'running')
            """,
            (source, query_condition, requested_max, started_at),
        )
        self.connection.commit()
        return int(cursor.lastrowid)

    def link_ingestion(self, run_id: int, nct_id: str, source_rank: int) -> None:
        self.connection.execute(
            """
            INSERT OR REPLACE INTO study_ingestion_runs(run_id, nct_id, source_rank)
            VALUES (?, ?, ?)
            """,
            (run_id, nct_id, source_rank),
        )
        self.connection.commit()

    def finish_ingestion(
        self,
        run_id: int,
        status: str,
        records_processed: int,
        new_snapshots: int,
    ) -> None:
        self.connection.execute(
            """
            UPDATE ingestion_runs
            SET completed_at = ?, status = ?, records_processed = ?, new_snapshots = ?
            WHERE run_id = ?
            """,
            (
                datetime.now(UTC).isoformat(),
                status,
                records_processed,
                new_snapshots,
                run_id,
            ),
        )
        self.connection.commit()

    def upsert(self, record: TrialRecord, raw: dict[str, Any]) -> bool:
        """Upsert a trial and return True only when a new snapshot was stored."""
        observed_at = datetime.now(UTC).isoformat()
        sponsor_id = self._upsert_sponsor(record.sponsor_name, observed_at)
        self.connection.execute(
            """
            INSERT INTO studies(
                nct_id, title, sponsor_id, sponsor_name_raw, sponsor_class,
                overall_status, study_type, phases_json, interventions_json,
                intervention_types_json, countries_json, location_count,
                start_date, primary_completion_date, completion_date,
                enrollment_count, enrollment_type, allocation, intervention_model,
                primary_purpose, masking, sex, minimum_age, maximum_age,
                healthy_volunteers, why_stopped, last_update_post_date,
                first_seen_at, last_seen_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(nct_id) DO UPDATE SET
                title = excluded.title,
                sponsor_id = excluded.sponsor_id,
                sponsor_name_raw = excluded.sponsor_name_raw,
                sponsor_class = excluded.sponsor_class,
                overall_status = excluded.overall_status,
                study_type = excluded.study_type,
                phases_json = excluded.phases_json,
                interventions_json = excluded.interventions_json,
                intervention_types_json = excluded.intervention_types_json,
                countries_json = excluded.countries_json,
                location_count = excluded.location_count,
                start_date = excluded.start_date,
                primary_completion_date = excluded.primary_completion_date,
                completion_date = excluded.completion_date,
                enrollment_count = excluded.enrollment_count,
                enrollment_type = excluded.enrollment_type,
                allocation = excluded.allocation,
                intervention_model = excluded.intervention_model,
                primary_purpose = excluded.primary_purpose,
                masking = excluded.masking,
                sex = excluded.sex,
                minimum_age = excluded.minimum_age,
                maximum_age = excluded.maximum_age,
                healthy_volunteers = excluded.healthy_volunteers,
                why_stopped = excluded.why_stopped,
                last_update_post_date = excluded.last_update_post_date,
                last_seen_at = excluded.last_seen_at
            """,
            (
                record.nct_id,
                record.title,
                sponsor_id,
                record.sponsor_name,
                record.sponsor_class,
                record.overall_status,
                record.study_type,
                json.dumps(record.phases),
                json.dumps(record.interventions),
                json.dumps(record.intervention_types),
                json.dumps(record.countries),
                record.location_count,
                record.start_date,
                record.primary_completion_date,
                record.completion_date,
                record.enrollment_count,
                record.enrollment_type,
                record.allocation,
                record.intervention_model,
                record.primary_purpose,
                record.masking,
                record.sex,
                record.minimum_age,
                record.maximum_age,
                record.healthy_volunteers,
                record.why_stopped,
                record.last_update_post_date,
                observed_at,
                observed_at,
            ),
        )

        self.connection.execute("DELETE FROM study_conditions WHERE nct_id = ?", (record.nct_id,))
        for condition in record.conditions:
            normalized = normalize_text(condition)
            self.connection.execute(
                """
                INSERT INTO conditions(normalized_name, display_name)
                VALUES (?, ?)
                ON CONFLICT(normalized_name) DO NOTHING
                """,
                (normalized, condition),
            )
            condition_id = self.connection.execute(
                "SELECT condition_id FROM conditions WHERE normalized_name = ?", (normalized,)
            ).fetchone()[0]
            self.connection.execute(
                "INSERT OR IGNORE INTO study_conditions(nct_id, condition_id) VALUES (?, ?)",
                (record.nct_id, condition_id),
            )

        raw_json = json.dumps(raw, sort_keys=True, separators=(",", ":"))
        payload_hash = hashlib.sha256(raw_json.encode()).hexdigest()
        cursor = self.connection.execute(
            """
            INSERT OR IGNORE INTO study_snapshots(nct_id, observed_at, payload_hash, raw_json)
            VALUES (?, ?, ?, ?)
            """,
            (record.nct_id, observed_at, payload_hash, raw_json),
        )
        self.connection.commit()
        return cursor.rowcount == 1

    def summary(self) -> dict[str, int]:
        tables: Iterable[str] = ("studies", "sponsors", "conditions", "study_snapshots")
        return {
            table: int(self.connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in tables
        }
