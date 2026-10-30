# Architecture roadmap

```text
ClinicalTrials.gov API v2 / AACT daily snapshot
                    |
             raw immutable layer
                    |
       normalization + entity resolution
                    |
          PostgreSQL analytical model
                    |
              dbt marts + tests
              /              \
 competitive benchmark   risk benchmark
              \              /
                  FastAPI
                     |
             analyst web interface
```

The initial vertical slice uses SQLite so it runs without credentials or infrastructure.
The warehouse moves to PostgreSQL after the ingestion contract and keys are stable. The
SQLite implementation is not presented as the final production architecture.

## Planned data model

- `dim_sponsor`
- `dim_condition`
- `dim_intervention`
- `dim_location`
- `fct_trial`
- `fct_trial_site`
- `fct_trial_snapshot`
- `mart_competitive_landscape`
- `mart_trial_duration_benchmark`
- `mart_sponsor_performance`
- `mart_data_quality`

