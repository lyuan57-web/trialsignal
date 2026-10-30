# Adverse-outcome benchmark model card

## Intended use

Prioritize historical comparables for analyst review. The probability is a statistical
benchmark, not a causal estimate, medical recommendation, or automated trial decision.

## Outcome

- Positive: `TERMINATED`, `WITHDRAWN`, or `SUSPENDED`
- Negative: `COMPLETED`
- Ongoing and unknown-status trials are excluded from model training.

## Features

Only registration-time design and planning fields are used: sponsor class, phase, study
type, allocation, intervention model, purpose, masking, sex eligibility, planned
enrollment, location/condition/intervention/country counts, and start year.

Explicitly excluded for leakage:

- final status;
- primary and final completion dates;
- `why_stopped` text;
- actual-versus-estimated enrollment type.

## Validation design

Trials are ordered by start date. The earliest 80% form the training period and the latest
20% form the holdout period. Random cross-validation would overstate performance when
registry practices and trial portfolios change over time.

## Current development validation

The multi-indication development extraction contains 11,509 distinct records. After outcome
and date eligibility rules, it yielded 6,642 resolved trials: 5,313 training and 1,329 holdout
records. The temporal holdout begins May 29, 2019.

| Metric | Development result |
|---|---:|
| ROC-AUC | 0.871 |
| Average precision | 0.835 |
| Brier score | 0.181 |
| Prevalence-only baseline Brier score | 0.255 |
| Holdout adverse-outcome prevalence | 0.370 |

Subgroup ROC-AUC ranged from 0.779 for melanoma to 0.918 for leukemia in the
development holdout. This variation is retained as evidence of domain sensitivity rather
than hidden behind the aggregate score. Calibration bins also show systematic
overprediction in several risk ranges, so the score is not ready for a decision threshold.

These values are development evidence, not final claims. They must be regenerated after
expanding the data and freezing the cohort definition.

## Known limitations

- Registry data are self-reported and retrospectively updated.
- Important operational variables are unavailable in public data.
- Each development query is capped at 1,000 relevance-ranked records, so the current cohort
  is not a prevalence-representative sample of the registry.
- A multi-indication extraction does not by itself establish out-of-domain validity.
- The baseline is not yet calibrated for operational decision thresholds.
- Sponsor normalization does not represent acquisitions or parent-subsidiary history.

