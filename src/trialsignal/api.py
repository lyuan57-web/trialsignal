"""FastAPI application exposing traceable TrialSignal decisions."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .analytics import TrialAnalytics
from .data_quality import quality_summary
from .entity_resolution import SponsorResolver
from .risk_model import predict_artifact
from .survival import duration_benchmark

PACKAGE_ROOT = Path(__file__).parent
DEFAULT_DATABASE = Path(os.getenv("TRIALSIGNAL_DB", "data/trialsignal.db"))
DEFAULT_MODEL = Path(os.getenv("TRIALSIGNAL_MODEL", "models/adverse_outcome.joblib"))

app = FastAPI(
    title="TrialSignal API",
    version="0.2.0",
    description="Traceable clinical-trial competitive intelligence and risk benchmarks.",
)


class SponsorQuery(BaseModel):
    name: str = Field(min_length=2, max_length=300)


def _require_database() -> Path:
    if not DEFAULT_DATABASE.exists():
        raise HTTPException(503, f"Database not found: {DEFAULT_DATABASE}")
    return DEFAULT_DATABASE


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(PACKAGE_ROOT / "web" / "index.html")


@app.get("/health")
def health() -> dict:
    database = _require_database()
    return {"status": "ok", "database": str(database), "model_available": DEFAULT_MODEL.exists()}


@app.get("/metrics/overview")
def overview() -> dict:
    return TrialAnalytics(_require_database()).overview()


@app.get("/trials/search")
def search_trials(
    condition: str = "",
    status: str = "",
    phase: str = "",
    country: str = "",
    sponsor: str = "",
    study_type: str = "",
    limit: int = Query(default=50, ge=1, le=200),
) -> list[dict]:
    return TrialAnalytics(_require_database()).search(
        condition=condition,
        status=status,
        phase=phase,
        country=country,
        sponsor=sponsor,
        study_type=study_type,
        limit=limit,
    )


@app.get("/trials/{nct_id}/comparables")
def comparables(nct_id: str, limit: int = Query(default=10, ge=1, le=50)) -> list[dict]:
    try:
        return TrialAnalytics(_require_database()).comparable_trials(nct_id.upper(), limit)
    except KeyError as error:
        raise HTTPException(404, f"Unknown trial: {nct_id}") from error


@app.get("/landscape/countries")
def country_landscape(condition: str) -> list[dict]:
    return TrialAnalytics(_require_database()).country_competition(condition)


@app.get("/benchmarks/duration")
def trial_duration(phase: str = "", sponsor_class: str = "") -> dict:
    return duration_benchmark(_require_database(), phase, sponsor_class)


@app.post("/sponsors/resolve")
def resolve_sponsor(query: SponsorQuery) -> dict:
    resolver = SponsorResolver.from_database(_require_database())
    return resolver.resolve(query.name).to_dict()


@app.get("/quality")
def data_quality() -> dict:
    return quality_summary(_require_database())


@app.get("/trials/{nct_id}/risk")
def trial_risk(nct_id: str) -> dict:
    database = _require_database()
    if not DEFAULT_MODEL.exists():
        raise HTTPException(503, "Risk model has not been trained")
    with sqlite3.connect(database) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            """
            SELECT s.*, COUNT(sc.condition_id) condition_count
            FROM studies s LEFT JOIN study_conditions sc USING(nct_id)
            WHERE s.nct_id = ? GROUP BY s.nct_id
            """,
            (nct_id.upper(),),
        ).fetchone()
    if row is None:
        raise HTTPException(404, f"Unknown trial: {nct_id}")
    return {"nct_id": nct_id.upper(), **predict_artifact(DEFAULT_MODEL, row)}
