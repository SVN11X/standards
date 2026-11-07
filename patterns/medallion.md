# Medallion layers

- Status: use
- Profiles: data-ai
- Family: data

## Problem it solves

A pipeline mixes raw ingestion, cleaning and business logic in one step, so errors cannot be traced to a source and reprocessing is risky.

## Use it when

A pipeline runs repeatedly, with several sources or several consumers.

## Do not use it when

The work is a one-off analysis or the data is tiny. Use raw and processed folders instead.

## Signs you do not need it yet

Silver is a copy of bronze, or gold is a copy of silver.

## Simpler alternative

Two layers: raw, as received, and processed, derived by code.

## How it looks when misused

Data copied through three layers with no change. Business rules applied in bronze. Gold tables that read bronze directly.

## Minimal example

```text
data/
  bronze/sensors/2026-11-07.json   as received, never edited
  silver/readings.parquet          typed, deduplicated, timestamps in UTC
  gold/daily_air_quality.parquet   one row per station and day
```

## References

- Original: Databricks, medallion architecture, which describes it as a recommended practice, not a requirement. https://docs.databricks.com/gcp/en/lakehouse/medallion
- Free: Cookiecutter Data Science, for the simpler raw and processed layout. https://github.com/drivendataorg/cookiecutter-data-science
