"""Non-parametric trial-duration benchmarks with right censoring."""

from __future__ import annotations

import json
import sqlite3
from collections import Counter
from datetime import date
from pathlib import Path

FINAL_STATUSES = {"COMPLETED", "TERMINATED", "WITHDRAWN", "SUSPENDED"}


def parse_partial_date(value: str | None) -> date | None:
    """Parse registry dates at year, month, or day precision conservatively."""
    if not value:
        return None
    parts = value.split("-")
    try:
        year = int(parts[0])
        month = int(parts[1]) if len(parts) > 1 else 7
        day = int(parts[2]) if len(parts) > 2 else 15
        return date(year, month, day)
    except (ValueError, IndexError):
        return None


def kaplan_meier(observations: list[tuple[float, bool]]) -> list[dict]:
    """Return the Kaplan-Meier curve for (duration_months, event_observed)."""
    if not observations:
        return []
    grouped: dict[float, Counter] = {}
    for duration, observed in observations:
        bucket = grouped.setdefault(float(duration), Counter())
        bucket["events" if observed else "censored"] += 1

    at_risk = len(observations)
    survival = 1.0
    curve = [{"month": 0.0, "survival": 1.0, "at_risk": at_risk, "events": 0, "censored": 0}]
    for duration in sorted(grouped):
        events = grouped[duration]["events"]
        censored = grouped[duration]["censored"]
        if events and at_risk:
            survival *= 1 - events / at_risk
        curve.append(
            {
                "month": round(duration, 2),
                "survival": round(survival, 6),
                "at_risk": at_risk,
                "events": events,
                "censored": censored,
            }
        )
        at_risk -= events + censored
    return curve


def _survival_at(curve: list[dict], month: float) -> float:
    value = 1.0
    for point in curve:
        if point["month"] > month:
            break
        value = point["survival"]
    return value


def duration_benchmark(
    database: str | Path,
    phase: str = "",
    sponsor_class: str = "",
    as_of: date | None = None,
) -> dict:
    as_of = as_of or date.today()
    with sqlite3.connect(database) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT nct_id, overall_status, phases_json, sponsor_class,
                   start_date, completion_date
            FROM studies WHERE start_date IS NOT NULL
            """
        ).fetchall()

    observations: list[tuple[float, bool]] = []
    excluded = Counter()
    requested_phase = phase.upper()
    requested_class = sponsor_class.upper()
    for row in rows:
        phases = {item.upper() for item in json.loads(row["phases_json"] or "[]")}
        if requested_phase and requested_phase not in phases:
            continue
        if requested_class and (row["sponsor_class"] or "").upper() != requested_class:
            continue
        start = parse_partial_date(row["start_date"])
        if start is None or start > as_of:
            excluded["invalid_or_future_start"] += 1
            continue
        is_final = row["overall_status"] in FINAL_STATUSES
        end = parse_partial_date(row["completion_date"]) if is_final else as_of
        if end is None:
            excluded["final_without_completion_date"] += 1
            continue
        days = (end - start).days
        if days < 0:
            excluded["negative_duration"] += 1
            continue
        observations.append((days / 30.4375, is_final))

    curve = kaplan_meier(observations)
    median = next((point["month"] for point in curve if point["survival"] <= 0.5), None)
    return {
        "cohort": {"phase": requested_phase or "ALL", "sponsor_class": requested_class or "ALL"},
        "as_of": as_of.isoformat(),
        "trials": len(observations),
        "events": sum(int(event) for _, event in observations),
        "censored": sum(int(not event) for _, event in observations),
        "median_months_to_study_end": median,
        "probability_still_ongoing": {
            "12_months": round(_survival_at(curve, 12), 4),
            "24_months": round(_survival_at(curve, 24), 4),
            "36_months": round(_survival_at(curve, 36), 4),
            "60_months": round(_survival_at(curve, 60), 4),
        },
        "excluded": dict(excluded),
        "curve": curve,
        "interpretation": "Descriptive duration benchmark with right censoring; not a causal forecast.",
    }
