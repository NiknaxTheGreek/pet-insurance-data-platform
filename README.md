# Pet Insurance Claims & Portfolio Data Platform

A production-style data-engineering portfolio project demonstrating how mutable operational insurance data is incrementally moved from PostgreSQL into Snowflake and transformed with dbt into tested analytics-ready datasets.

## Locked vertical slice
Pet insurance only. Source entities: customers, pets, policies, claims, claim payments.

## Engineering capabilities targeted
Advanced SQL, PostgreSQL, Snowflake, dbt, Python ingestion, incremental processing/CDC concepts, idempotency, data quality, testing, observability/reconciliation, Docker, CI/CD, documentation, performance/cost awareness, and engineering judgement.

## Current verified state
The PostgreSQL source contract and deterministic seed generator are implemented and tested. A live PostgreSQL proof has also demonstrated watermark-based incremental capture and append-only change history. Snowflake GitHub Actions/OIDC integration is being bootstrapped; it is not considered verified until an actual workflow authenticates successfully.

See `docs/source_contract.md` for the v1 source contract.
