# Learning guide

The project is taught from the running system backward. Do not memorize the entire codebase.
For each unit, first observe behavior, then trace the code, then make one controlled change.

## Unit 1 — Product decision

Explain who uses TrialSignal, what decision they make, what would be dangerous to overstate,
and why a source-linked comparable is more useful than an unexplained score.

## Unit 2 — API ingestion

Trace one registry record through `fetch_studies`, `parse_study`, and `TrialStore.upsert`.
Then add one field without breaking an existing database.

## Unit 3 — SQL and relational modeling

Draw the relationship among studies, sponsors, conditions, and snapshots. Write SQL for
status distribution, top sponsors, and records with missing completion dates.

## Unit 4 — Entity resolution

Understand normalization, fuzzy candidate scoring, thresholds, margins, and abstention.
Label difficult sponsor pairs and explain one false positive and one false negative. The
portfolio evaluation set must eventually contain at least 300 reviewed pairs.

## Unit 5 — Data contracts

Run `make quality`. Separate blocking errors from review warnings. Explain why a completed
study missing a completion date is a warning rather than grounds for silently deleting it.

## Unit 6 — Comparable-trial retrieval

Trace the weighted similarity calculation. Challenge each weight and identify information
public data cannot capture. This is evidence retrieval, not learned truth.

## Unit 7 — Modeling without leakage

Trace the chronological split, logistic baseline, and model card. Explain why final
enrollment, completion date, and why-stopped text are excluded.

## Unit 8 — API and product surface

Run `make api`, open `/docs`, and follow one request through FastAPI, SQL, and returned JSON.
Add one filtered endpoint with input validation and a test.

## Unit 9 — Deployment and reliability

Build the container, inspect its health check, and run the linting and test commands. Explain
which artifacts remain outside the public repository and how the database is recreated.

## Interview readiness test

You own the project when you can answer these without a script:

- What exact business decision does it support?
- What broke while you built it?
- How did you prevent duplicate ingestion?
- How did you measure entity-resolution quality?
- Where could label or temporal leakage occur?
- Why is the model not causal?
- What would change with proprietary site and patient data?
- How should the system behave when the source API fails?

