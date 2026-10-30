"""Decision-oriented query layer and comparable-trial retrieval."""

from __future__ import annotations

import json
import math
import sqlite3
from collections import Counter
from pathlib import Path

from .normalize import normalize_text

FINAL_STATUSES = {"COMPLETED", "TERMINATED", "WITHDRAWN", "SUSPENDED"}


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _condition_similarity(left: set[str], right: set[str]) -> float:
    """Match both exact registry labels and their normalized disease tokens.

    ClinicalTrials.gov may label the same disease at different granularity (for
    example, ``melanoma`` versus ``cutaneous melanoma``). Exact label overlap is
    retained for precision, while token overlap recovers these nested concepts.
    """

    label_overlap = _jaccard(left, right)
    left_tokens = {token for label in left for token in normalize_text(label).split()}
    right_tokens = {token for label in right for token in normalize_text(label).split()}
    return max(label_overlap, _jaccard(left_tokens, right_tokens))


class TrialAnalytics:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def overview(self) -> dict:
        with sqlite3.connect(self.path) as connection:
            connection.row_factory = sqlite3.Row
            status = {
                row["overall_status"]: row["n"]
                for row in connection.execute(
                    "SELECT overall_status, COUNT(*) n FROM studies GROUP BY overall_status ORDER BY n DESC"
                )
            }
            top_sponsors = [
                dict(row)
                for row in connection.execute(
                    """
                    SELECT sp.canonical_name sponsor, COUNT(*) trial_count
                    FROM studies s JOIN sponsors sp USING(sponsor_id)
                    GROUP BY sp.sponsor_id ORDER BY trial_count DESC, sponsor LIMIT 10
                    """
                )
            ]
            totals = connection.execute(
                """
                SELECT COUNT(*) trials,
                       COUNT(DISTINCT sponsor_id) sponsors,
                       SUM(CASE WHEN overall_status IN ('RECRUITING','NOT_YET_RECRUITING','ACTIVE_NOT_RECRUITING') THEN 1 ELSE 0 END) active_trials,
                       SUM(CASE WHEN overall_status IN ('TERMINATED','WITHDRAWN','SUSPENDED') THEN 1 ELSE 0 END) adverse_outcomes
                FROM studies
                """
            ).fetchone()
        return {"totals": dict(totals), "status_counts": status, "top_sponsors": top_sponsors}

    def search(
        self,
        condition: str = "",
        status: str = "",
        phase: str = "",
        country: str = "",
        sponsor: str = "",
        study_type: str = "",
        limit: int = 50,
    ) -> list[dict]:
        clauses: list[str] = []
        params: list[object] = []
        if condition:
            clauses.append("c.normalized_name LIKE ?")
            params.append(f"%{normalize_text(condition)}%")
        if status:
            clauses.append("s.overall_status = ?")
            params.append(status.upper())
        if phase:
            clauses.append("s.phases_json LIKE ?")
            params.append(f'%"{phase.upper()}"%')
        if country:
            clauses.append("lower(s.countries_json) LIKE ?")
            params.append(f"%{country.lower()}%")
        if sponsor:
            clauses.append("lower(sp.canonical_name) LIKE ?")
            params.append(f"%{sponsor.lower()}%")
        if study_type:
            clauses.append("s.study_type = ?")
            params.append(study_type.upper())
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(min(max(limit, 1), 200))
        with sqlite3.connect(self.path) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                f"""
                SELECT DISTINCT s.nct_id, s.title, sp.canonical_name sponsor,
                       s.sponsor_class, s.study_type, s.overall_status,
                       s.phases_json phases, s.countries_json countries,
                       s.enrollment_count, s.start_date, s.completion_date
                FROM studies s
                JOIN sponsors sp USING(sponsor_id)
                LEFT JOIN study_conditions sc USING(nct_id)
                LEFT JOIN conditions c USING(condition_id)
                {where}
                ORDER BY s.start_date DESC
                LIMIT ?
                """,
                params,
            ).fetchall()
        return [dict(row) for row in rows]

    def comparable_trials(self, nct_id: str, limit: int = 10) -> list[dict]:
        with sqlite3.connect(self.path) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                """
                SELECT s.*, sp.canonical_name sponsor,
                       GROUP_CONCAT(c.normalized_name, '|') conditions
                FROM studies s
                JOIN sponsors sp USING(sponsor_id)
                LEFT JOIN study_conditions sc USING(nct_id)
                LEFT JOIN conditions c USING(condition_id)
                GROUP BY s.nct_id
                """
            ).fetchall()
        records = [dict(row) for row in rows]
        target = next((row for row in records if row["nct_id"] == nct_id), None)
        if target is None:
            raise KeyError(nct_id)

        target_conditions = set((target["conditions"] or "").split("|")) - {""}
        target_phases = set(json.loads(target["phases_json"]))
        target_countries = set(json.loads(target["countries_json"]))
        target_types = set(json.loads(target["intervention_types_json"]))
        candidates: list[dict] = []
        for row in records:
            if row["nct_id"] == nct_id:
                continue
            conditions = set((row["conditions"] or "").split("|")) - {""}
            phases = set(json.loads(row["phases_json"]))
            countries = set(json.loads(row["countries_json"]))
            intervention_types = set(json.loads(row["intervention_types_json"]))
            condition_score = _condition_similarity(target_conditions, conditions)
            phase_score = _jaccard(target_phases, phases)
            geography_score = _jaccard(target_countries, countries)
            intervention_type_score = _jaccard(target_types, intervention_types)
            sponsor_class_score = float(target["sponsor_class"] == row["sponsor_class"])
            purpose_score = float(
                bool(target["primary_purpose"])
                and target["primary_purpose"] == row["primary_purpose"]
            )
            model_score = float(
                bool(target["intervention_model"])
                and target["intervention_model"] == row["intervention_model"]
            )
            allocation_score = float(
                bool(target["allocation"]) and target["allocation"] == row["allocation"]
            )
            masking_score = float(bool(target["masking"]) and target["masking"] == row["masking"])
            if target["enrollment_count"] and row["enrollment_count"]:
                enrollment_score = math.exp(
                    -abs(
                        math.log1p(target["enrollment_count"]) - math.log1p(row["enrollment_count"])
                    )
                )
            else:
                enrollment_score = 0.0
            components = {
                "condition_overlap": (condition_score, 0.30),
                "phase_overlap": (phase_score, 0.12),
                "intervention_type_overlap": (intervention_type_score, 0.12),
                "geography_overlap": (geography_score, 0.10),
                "same_sponsor_class": (sponsor_class_score, 0.04),
                "same_primary_purpose": (purpose_score, 0.06),
                "same_intervention_model": (model_score, 0.06),
                "same_allocation": (allocation_score, 0.04),
                "same_masking": (masking_score, 0.04),
                "enrollment_scale_similarity": (enrollment_score, 0.12),
            }
            score = sum(value * weight for value, weight in components.values())
            candidates.append(
                {
                    "nct_id": row["nct_id"],
                    "title": row["title"],
                    "sponsor": row["sponsor"],
                    "status": row["overall_status"],
                    "similarity": round(score, 4),
                    "evidence": {
                        name: {"value": round(value, 4), "weight": weight}
                        for name, (value, weight) in components.items()
                    },
                }
            )
        return sorted(candidates, key=lambda item: item["similarity"], reverse=True)[:limit]

    def country_competition(self, condition: str) -> list[dict]:
        rows = self.search(condition=condition, limit=200)
        wanted = {row["nct_id"] for row in rows}
        counts: Counter[str] = Counter()
        with sqlite3.connect(self.path) as connection:
            for nct_id, countries_json in connection.execute(
                "SELECT nct_id,countries_json FROM studies"
            ):
                if nct_id in wanted:
                    counts.update(json.loads(countries_json))
        return [
            {"country": country, "trial_count": count} for country, count in counts.most_common()
        ]
