# Product specification

## Decision and user

TrialSignal helps a clinical-strategy or business-development analyst answer:

> For a proposed trial in a target indication, which comparable studies and sponsors
> create enrollment competition, and which design choices are associated with schedule
> or non-completion risk?

The first target user is an analyst planning an industry-sponsored Phase 2 or Phase 3
oncology trial. The product is decision support, not medical advice.

## What makes this more than a dashboard

1. **Auditable ingestion:** daily snapshots preserve source records and detect revisions.
2. **Entity resolution:** sponsor and condition variants are resolved with measurable
   precision, recall, and coverage rather than silently grouped by string equality.
3. **Leakage-safe benchmarking:** risk features are restricted to information plausibly
   available at trial planning time; validation is split by calendar time.
4. **Decision output:** the system returns comparable trials, competitive intensity,
   uncertainty, and the evidence behind each recommendation.
5. **Production behavior:** tested transformations, data-quality alerts, an API, a
   deployed interface, monitoring, and reproducible builds.

## MVP acceptance criteria

- Ingest at least 10,000 interventional oncology studies from an official source. **Met in development: 11,509 distinct studies.**
- Preserve raw payloads and repeated observations without duplicate snapshots.
- Resolve sponsor aliases against a hand-labeled evaluation set of at least 300 pairs.
- Build a star schema and pass at least 25 automated data tests.
- Produce comparable-trial cohorts without using post-outcome information.
- Expose evidence and metrics through an API and deployed web interface.
- Run the complete public demo from one documented command.

## Honest product boundary

Public registry data does not include every operational variable used by commercial
trial-planning products. TrialSignal will report data gaps and uncertainty explicitly and
will not claim to replace proprietary patient, site, or enrollment-performance data.

