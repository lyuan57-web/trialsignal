"""ClinicalTrials.gov API v2 client and response parser."""

from __future__ import annotations

import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

import httpx

API_URL = "https://clinicaltrials.gov/api/v2/studies"


@dataclass(frozen=True)
class TrialRecord:
    nct_id: str
    title: str
    sponsor_name: str
    sponsor_class: str | None
    overall_status: str
    study_type: str | None
    phases: tuple[str, ...] = field(default_factory=tuple)
    conditions: tuple[str, ...] = field(default_factory=tuple)
    interventions: tuple[str, ...] = field(default_factory=tuple)
    intervention_types: tuple[str, ...] = field(default_factory=tuple)
    countries: tuple[str, ...] = field(default_factory=tuple)
    location_count: int = 0
    start_date: str | None = None
    primary_completion_date: str | None = None
    completion_date: str | None = None
    enrollment_count: int | None = None
    enrollment_type: str | None = None
    allocation: str | None = None
    intervention_model: str | None = None
    primary_purpose: str | None = None
    masking: str | None = None
    sex: str | None = None
    minimum_age: str | None = None
    maximum_age: str | None = None
    healthy_volunteers: bool | None = None
    why_stopped: str | None = None
    last_update_post_date: str | None = None


def _get(mapping: dict[str, Any], *path: str, default: Any = None) -> Any:
    current: Any = mapping
    for key in path:
        if not isinstance(current, dict) or key not in current:
            return default
        current = current[key]
    return current


def parse_study(study: dict[str, Any]) -> TrialRecord:
    protocol = study.get("protocolSection", {})
    identification = protocol.get("identificationModule", {})
    status = protocol.get("statusModule", {})
    design = protocol.get("designModule", {})
    conditions_module = protocol.get("conditionsModule", {})
    arms = protocol.get("armsInterventionsModule", {})
    locations = protocol.get("contactsLocationsModule", {})
    sponsor = _get(protocol, "sponsorCollaboratorsModule", "leadSponsor", default={})
    enrollment = design.get("enrollmentInfo", {})
    design_info = design.get("designInfo", {})
    eligibility = protocol.get("eligibilityModule", {})

    interventions = tuple(
        item.get("name", "").strip()
        for item in arms.get("interventions", [])
        if item.get("name", "").strip()
    )
    intervention_types = tuple(
        sorted(
            {
                item.get("type", "").strip()
                for item in arms.get("interventions", [])
                if item.get("type", "").strip()
            }
        )
    )
    raw_locations = locations.get("locations", [])
    countries = tuple(
        sorted(
            {
                item.get("country", "").strip()
                for item in raw_locations
                if item.get("country", "").strip()
            }
        )
    )

    return TrialRecord(
        nct_id=identification["nctId"],
        title=identification.get("briefTitle", ""),
        sponsor_name=sponsor.get("name", "Unknown"),
        sponsor_class=sponsor.get("class"),
        overall_status=status.get("overallStatus", "UNKNOWN"),
        study_type=design.get("studyType"),
        phases=tuple(design.get("phases", [])),
        conditions=tuple(conditions_module.get("conditions", [])),
        interventions=interventions,
        intervention_types=intervention_types,
        countries=countries,
        location_count=len(raw_locations),
        start_date=_get(status, "startDateStruct", "date"),
        primary_completion_date=_get(status, "primaryCompletionDateStruct", "date"),
        completion_date=_get(status, "completionDateStruct", "date"),
        enrollment_count=enrollment.get("count"),
        enrollment_type=enrollment.get("type"),
        allocation=design_info.get("allocation"),
        intervention_model=design_info.get("interventionModel"),
        primary_purpose=design_info.get("primaryPurpose"),
        masking=_get(design_info, "maskingInfo", "masking"),
        sex=eligibility.get("sex"),
        minimum_age=eligibility.get("minimumAge"),
        maximum_age=eligibility.get("maximumAge"),
        healthy_volunteers=eligibility.get("healthyVolunteers"),
        why_stopped=status.get("whyStopped"),
        last_update_post_date=_get(status, "lastUpdatePostDateStruct", "date"),
    )


def fetch_studies(
    condition: str,
    max_studies: int = 100,
    page_size: int = 100,
    timeout_seconds: int = 30,
) -> Iterator[dict[str, Any]]:
    """Yield current study records from the public API with token pagination."""
    yielded = 0
    page_token: str | None = None
    transport = httpx.HTTPTransport(retries=2)
    with httpx.Client(
        transport=transport,
        timeout=timeout_seconds,
        follow_redirects=True,
        headers={"User-Agent": "TrialSignal/0.1 (portfolio data project)"},
    ) as client:
        while yielded < max_studies:
            params = {
                "format": "json",
                "query.cond": condition,
                "pageSize": min(page_size, max_studies - yielded),
                "countTotal": "true",
            }
            if page_token:
                params["pageToken"] = page_token
            response: httpx.Response | None = None
            for attempt in range(4):
                response = client.get(API_URL, params=params)
                if response.status_code not in {429, 500, 502, 503, 504}:
                    break
                retry_after = response.headers.get("Retry-After")
                delay = min(float(retry_after), 10.0) if retry_after else 0.5 * (2**attempt)
                time.sleep(delay)
            assert response is not None
            response.raise_for_status()
            payload = response.json()
            for study in payload.get("studies", []):
                yield study
                yielded += 1
                if yielded >= max_studies:
                    return
            page_token = payload.get("nextPageToken")
            if not page_token:
                return
