# Pet Insurance Claims & Portfolio Data Platform

A production-style data-engineering portfolio project demonstrating how mutable operational insurance data is incrementally moved from PostgreSQL into Snowflake and transformed with dbt into tested analytics-ready datasets.

## Locked vertical slice
Pet insurance only. Source entities: customers, pets, policies, claims, claim payments.

## Engineering capabilities targeted
Advanced SQL, PostgreSQL, Snowflake, dbt, Python ingestion, incremental processing/CDC concepts, idempotency, data quality, testing, observability/reconciliation, Docker, CI/CD, documentation, performance/cost awareness, and engineering judgement.

## Current verified state
- GitHub Actions authenticates to Snowflake with secretless OIDC.
- Snowflake project schemas are deployed under `SNOWFLAKE_LEARNING_DB` using the verified `SNOWFLAKE_LEARNING_ROLE`.
- RAW and CONTROL ingestion tables are live.
- Verified PostgreSQL claim history for `CLM-10042` is present in Snowflake as two append-only versions:
  - T1: R8,500, `SUBMITTED`, 2026-09-20 09:00Z.
  - T3: R11,200, approved R9,700, `APPROVED`, 2026-09-22 13:56Z.
- The same bootstrap load is replayed in CI; the replay inserts zero duplicate RAW rows.
- SQL assertions verify exactly two historical versions and reconstruct the T3 state as current.
- The claims watermark is verified at `2026-09-22 13:56:00Z / CLM-10042`.
- The reusable Python ingestion core implements composite watermarks, canonical SHA-256 payload hashing, soft-delete operation mapping, in-batch deduplication and reconciliation.
- Python ingestion/seed tests are green in GitHub Actions.
- The live PostgreSQL→Snowflake workflow is active using the repository `POSTGRES_DSN` secret and Snowflake OIDC.
- Initial live reconciliation repaired a bootstrap watermark gap without duplicating `CLM-10042`: Snowflake RAW now contains all 3 live claim PKs while preserving historical versions.
- T4 is verified end-to-end: `CLM-10042` changed to `PAID`, payment `PAY-10042-T4` for R9,700 was inserted in PostgreSQL, and both changes were incrementally propagated to Snowflake.
- Snowflake now preserves the `CLM-10042` state sequence `SUBMITTED → APPROVED → PAID` with amounts R8,500 → R11,200 and approved/paid amount R9,700.
- The immediate no-change replay produced 0 candidates / 0 inserts for all five source tables, proving idempotent incremental behavior after T4.
- Claims and claim-payment watermarks are both verified at `2026-09-23 19:40:00Z` for `CLM-10042` and `PAY-10042-T4` respectively.

## Repository paths
- `src/insurance_platform/ingestion.py` — reusable CDC/incremental primitives.
- `src/insurance_platform/run_ingestion.py` — live PostgreSQL→Snowflake runner.
- `infra/snowflake/deploy.sql` — RAW/CONTROL platform objects.
- `infra/snowflake/load_verified_claim_history.sql` — deterministic T1/T3 bootstrap replay.
- `infra/snowflake/verify_claim_history.sql` — history/current-state assertions.
- `.github/workflows/snowflake-deploy.yml` — Snowflake OIDC deploy + replay verification.
- `.github/workflows/live-ingestion.yml` — live incremental ingestion.
- `.github/workflows/python-tests.yml` — Python CI.

See `docs/source_contract.md` for the v1 source contract.
