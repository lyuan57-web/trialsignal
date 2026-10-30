"""Leakage-aware baseline model for adverse trial outcomes.

The model intentionally uses only protocol and planning fields that are normally known
near study registration. Outcome status, completion dates, why-stopped text, and actual
enrollment type are excluded from features.
"""

from __future__ import annotations

import argparse
import json
import math
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import joblib
from sklearn.feature_extraction import DictVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from sklearn.pipeline import Pipeline

ADVERSE_STATUSES = {"TERMINATED", "WITHDRAWN", "SUSPENDED"}
ELIGIBLE_STATUSES = ADVERSE_STATUSES | {"COMPLETED"}


def _year(value: str | None) -> int | None:
    if not value or len(value) < 4:
        return None
    try:
        return int(value[:4])
    except ValueError:
        return None


def row_to_features(row: sqlite3.Row | dict) -> dict[str, str | float]:
    data = dict(row)
    phases = json.loads(data.get("phases_json") or "[]")
    interventions = json.loads(data.get("interventions_json") or "[]")
    countries = json.loads(data.get("countries_json") or "[]")
    intervention_types = json.loads(data.get("intervention_types_json") or "[]")
    enrollment = data.get("enrollment_count")
    start_year = _year(data.get("start_date"))
    return {
        "sponsor_class": data.get("sponsor_class") or "MISSING",
        "study_type": data.get("study_type") or "MISSING",
        "phase": phases[0] if phases else "MISSING",
        "allocation": data.get("allocation") or "MISSING",
        "intervention_model": data.get("intervention_model") or "MISSING",
        "primary_purpose": data.get("primary_purpose") or "MISSING",
        "masking": data.get("masking") or "MISSING",
        "sex": data.get("sex") or "MISSING",
        "enrollment_log1p": math.log1p(enrollment)
        if enrollment is not None and enrollment >= 0
        else 0.0,
        "location_count_log1p": math.log1p(max(data.get("location_count") or 0, 0)),
        "condition_count": float(data.get("condition_count") or 0),
        "intervention_count": float(len(interventions)),
        "country_count": float(len(countries)),
        "intervention_type_count": float(len(intervention_types)),
        "start_year_offset": float(start_year - 2000) if start_year else 0.0,
    }


def load_training_rows(database: str | Path) -> list[sqlite3.Row]:
    with sqlite3.connect(database) as connection:
        connection.row_factory = sqlite3.Row
        placeholders = ",".join("?" for _ in ELIGIBLE_STATUSES)
        rows = connection.execute(
            f"""
            SELECT s.*, COUNT(sc.condition_id) condition_count
            FROM studies s
            LEFT JOIN study_conditions sc USING(nct_id)
            WHERE s.overall_status IN ({placeholders})
              AND s.start_date IS NOT NULL
            GROUP BY s.nct_id
            ORDER BY s.start_date, s.nct_id
            """,
            tuple(sorted(ELIGIBLE_STATUSES)),
        ).fetchall()
    return rows


def load_cohort_membership(database: str | Path) -> dict[str, set[str]]:
    with sqlite3.connect(database) as connection:
        rows = connection.execute(
            """
            SELECT r.query_condition, x.nct_id
            FROM ingestion_runs r
            JOIN study_ingestion_runs x USING(run_id)
            WHERE r.status = 'completed'
            """
        ).fetchall()
    cohorts: dict[str, set[str]] = {}
    for condition, nct_id in rows:
        cohorts.setdefault(condition, set()).add(nct_id)
    return cohorts


def calibration_bins(y_true: list[int], probabilities: list[float], bins: int = 5) -> list[dict]:
    ordered = sorted(zip(probabilities, y_true, strict=True))
    results: list[dict] = []
    for index in range(bins):
        start = index * len(ordered) // bins
        end = (index + 1) * len(ordered) // bins
        group = ordered[start:end]
        if not group:
            continue
        results.append(
            {
                "bin": index + 1,
                "n": len(group),
                "mean_predicted": sum(item[0] for item in group) / len(group),
                "observed_rate": sum(item[1] for item in group) / len(group),
            }
        )
    return results


def train_model(database: str | Path, output: str | Path) -> dict:
    rows = load_training_rows(database)
    if len(rows) < 100:
        raise ValueError(f"Need at least 100 eligible historical trials; found {len(rows)}")

    split = int(len(rows) * 0.8)
    train_rows, test_rows = rows[:split], rows[split:]
    y_train = [int(row["overall_status"] in ADVERSE_STATUSES) for row in train_rows]
    y_test = [int(row["overall_status"] in ADVERSE_STATUSES) for row in test_rows]
    if len(set(y_train)) < 2 or len(set(y_test)) < 2:
        raise ValueError("Temporal split must contain both outcome classes in train and test sets")

    model = Pipeline(
        [
            ("vectorizer", DictVectorizer(sparse=True)),
            (
                "classifier",
                LogisticRegression(max_iter=2000, class_weight="balanced", random_state=42),
            ),
        ]
    )
    model.fit([row_to_features(row) for row in train_rows], y_train)
    probabilities = model.predict_proba([row_to_features(row) for row in test_rows])[:, 1]
    probability_list = [float(value) for value in probabilities]
    train_prevalence = sum(y_train) / len(y_train)
    baseline_probabilities = [train_prevalence] * len(y_test)
    cohorts = load_cohort_membership(database)
    cohort_metrics: dict[str, dict] = {}
    for condition, member_ids in sorted(cohorts.items()):
        indices = [index for index, row in enumerate(test_rows) if row["nct_id"] in member_ids]
        cohort_y = [y_test[index] for index in indices]
        cohort_probabilities = [probability_list[index] for index in indices]
        if len(indices) < 30 or len(set(cohort_y)) < 2:
            continue
        cohort_metrics[condition] = {
            "n": len(indices),
            "adverse_rate": sum(cohort_y) / len(cohort_y),
            "roc_auc": roc_auc_score(cohort_y, cohort_probabilities),
            "average_precision": average_precision_score(cohort_y, cohort_probabilities),
            "brier_score": brier_score_loss(cohort_y, cohort_probabilities),
        }
    metrics = {
        "eligible_trials": len(rows),
        "train_trials": len(train_rows),
        "test_trials": len(test_rows),
        "train_adverse_rate": train_prevalence,
        "test_adverse_rate": sum(y_test) / len(y_test),
        "roc_auc": roc_auc_score(y_test, probabilities),
        "average_precision": average_precision_score(y_test, probabilities),
        "brier_score": brier_score_loss(y_test, probabilities),
        "prevalence_baseline_brier": brier_score_loss(y_test, baseline_probabilities),
        "train_through": train_rows[-1]["start_date"],
        "test_from": test_rows[0]["start_date"],
        "calibration_bins": calibration_bins(y_test, probability_list),
        "cohort_metrics": cohort_metrics,
    }
    artifact = {
        "model": model,
        "metrics": metrics,
        "trained_at": datetime.now(UTC).isoformat(),
        "feature_policy": "registration-time protocol and planning fields only",
        "excluded_for_leakage": [
            "overall_status",
            "completion_date",
            "primary_completion_date",
            "why_stopped",
            "enrollment_type",
        ],
    }
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(artifact, output)
    return metrics


def predict_artifact(artifact_path: str | Path, row: sqlite3.Row | dict) -> dict:
    artifact = joblib.load(artifact_path)
    probability = float(artifact["model"].predict_proba([row_to_features(row)])[0, 1])
    return {
        "adverse_outcome_probability": probability,
        "model_metrics": artifact["metrics"],
        "feature_policy": artifact["feature_policy"],
        "interpretation": "Benchmark probability, not a causal estimate or clinical recommendation.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Train temporal adverse-outcome benchmark")
    parser.add_argument("--database", type=Path, default=Path("data/trialsignal.db"))
    parser.add_argument("--output", type=Path, default=Path("models/adverse_outcome.joblib"))
    args = parser.parse_args()
    print(json.dumps(train_model(args.database, args.output), indent=2))


if __name__ == "__main__":
    main()
