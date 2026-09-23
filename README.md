# Pet Insurance Claims & Portfolio Data Platform

A production-style data-engineering portfolio project demonstrating how mutable operational insurance data is incrementally moved from PostgreSQL into Snowflake and transformed with dbt into tested analytics-ready datasets.

## Locked vertical slice
Pet insurance only. Source entities: customers, pets, policies, claims, claim payments.

## Engineering capabilities demonstrated
Advanced SQL, PostgreSQL, Snowflake, dbt, Python ingestion, incremental processing/CDC concepts, idempotency, data quality, testing, observability/reconciliation, CI/CD, documentation, and engineering judgement.

## Current verified state
- GitHub Actions authenticates to Snowflake with short-lived OIDC workload identity; no Snowflake password is stored.
- Snowflake RAW, STAGING, INTERMEDIATE, MARTS, and CONTROL schemas are live under `SNOWFLAKE_LEARNING_DB`.
- The live PostgreSQL→Snowflake workflow uses a repository `POSTGRES_DSN` secret for the source and OIDC for Snowflake.
- Python ingestion uses composite `updated_at + source_pk` watermarks, canonical SHA-256 payload hashes, append-only RAW history, soft-delete operation mapping, batch audit rows, reconciliation, and idempotent MERGE logic.
- A bootstrap watermark gap was detected by reconciliation and repaired with a one-time missing-primary-key backfill. Snowflake contains all 3 live claim PKs without losing claim history.
- `CLM-10042` is verified end-to-end through three historical versions:
  - T1 — `SUBMITTED`, R8,500.
  - T3 — `APPROVED`, R11,200 with R9,700 approved.
  - T4 — `PAID`, R11,200 with R9,700 approved and R9,700 paid.
- The T4 incremental run detected exactly 1 changed claim and 1 new payment; the immediate replay detected 0 candidates / 0 inserts across all five source tables.
- dbt Core 1.12.5 with `dbt-snowflake 1.12.1` authenticates through the same OIDC identity.
- The dbt project contains 11 models across staging, intermediate, and marts, including one incremental claim-event model and one customer SCD2 history dimension.
- The verified dbt build completed with `PASS=67 WARN=0 ERROR=0 SKIP=0` across 11 models and 56 tests.
- dbt docs artifacts (`manifest.json`, `run_results.json`, `catalog.json`, `index.html`) are generated in CI.
- `FCT_CLAIMS` verifies `CLM-10042` as `PAID` with R11,200 claimed / R9,700 approved / R9,700 paid.
- `INT_CLAIM_EVENTS` verifies the historical sequence `SUBMITTED → APPROVED → PAID` and remains at exactly 3 rows after repeated dbt/incremental runs.
- A real customer attribute change was propagated from PostgreSQL through RAW and dbt:
  - `CUS-00001` historical row: Gauteng, closed at 2026-09-23 20:10Z.
  - `CUS-00001` current row: Western Cape, effective from 2026-09-23 20:10Z.
- The customer change produced exactly 1 source candidate / 1 RAW insert; the immediate replay produced 0 inserts. SCD2 and claim-event idempotency assertions both passed.
- Controlled reliability suite is green: dbt catches an intentionally invalid payment date, the source is repaired and retested, a late-arriving claim is recovered through reconciliation/backfill without duplication, and a source soft delete is propagated into RAW and removed from the trusted claim mart.
- The checked-in PostgreSQL schema now matches the live text-ID contract and is exercised from scratch with PostgreSQL 16 in Docker on GitHub Actions.
- Consolidated Platform CI is green across Python static checks/tests, Docker/PostgreSQL smoke validation, Snowflake OIDC, full dbt build, dbt docs generation, and trusted mart/history assertions.

## Data flow
`PostgreSQL → Python incremental ingestion → Snowflake RAW/CONTROL → dbt STAGING → dbt INTERMEDIATE → dbt MARTS`

## Key repository paths
- `src/insurance_platform/ingestion.py` — reusable CDC/incremental primitives.
- `src/insurance_platform/run_ingestion.py` — live PostgreSQL→Snowflake runner.
- `src/insurance_platform/repair_initial_backfill.py` — reconciliation-driven initial backfill repair.
- `infra/snowflake/deploy.sql` — RAW/CONTROL platform objects.
- `dbt/models/staging/` — current-state typed source models.
- `dbt/models/intermediate/int_claim_events.sql` — incremental historical claim-event model.
- `dbt/models/intermediate/int_policy_claims.sql` — policy-level claim/payment rollup.
- `dbt/models/marts/fct_claims.sql` — trusted current claim fact.
- `dbt/models/marts/dim_policy.sql` — current policy dimension.
- `dbt/models/marts/dim_customer_scd2.sql` — Type-2 customer history.
- `dbt/models/marts/mart_portfolio_performance.sql` — portfolio performance mart.
- `.github/workflows/dbt-build.yml` — dbt debug/build/docs/verification CI.
- `.github/workflows/t4-demo.yml` — paid-claim CDC demonstration.
- `.github/workflows/customer-scd2-demo.yml` — customer-history/SCD2 demonstration.
- `.github/workflows/reliability-suite.yml` — controlled failure, recovery, late-arrival, and soft-delete proof.
- `.github/workflows/platform-ci.yml` — consolidated Python + Docker/PostgreSQL + Snowflake/dbt CI gate.
- `infra/postgres/smoke_test.sql` — clean-container schema, relationship, and constraint smoke test.
- `docs/reliability.md` — verified failure/recovery evidence and CI results.

See `docs/source_contract.md` and `docs/dbt_modeling.md` for implementation detail.
