# Data dictionary

## Sources

The current source is ClinicalTrials.gov API v2. AACT is planned for full-registry bulk
loading and relational validation. Raw API payloads are preserved before analytical
transformations.

## Core tables

### `studies`

One current record per NCT identifier.

| Field | Meaning | Analytical caution |
|---|---|---|
| `nct_id` | Registry identifier | Primary key, not a sponsor's internal trial ID |
| `overall_status` | Latest registry status | Outcome field; never use as a model feature |
| `start_date` | Submitted study start | Precision varies between day and month |
| `enrollment_count` | Submitted enrollment | Can be anticipated or actual |
| `sponsor_name_raw` | Submitted lead sponsor | Preserve for audit; do not overwrite |

### `sponsors`

One deterministic normalization key per lead-sponsor name observed in current data. This
is a candidate-entity layer, not a legal corporate hierarchy.

### `conditions` and `study_conditions`

Normalized condition labels and the many-to-many bridge to studies. Public registry terms
are not assumed to be a complete medical ontology.

### `study_snapshots`

Immutable raw payloads keyed by study and SHA-256 content hash. Repeated identical API
responses are not duplicated. New hashes provide evidence for registry changes.

## Modeling contract

Features allowed in the pre-launch benchmark are limited to protocol and planning fields
normally available near registration. Completion dates, final status, why-stopped text,
and actual enrollment are excluded to reduce temporal leakage.

