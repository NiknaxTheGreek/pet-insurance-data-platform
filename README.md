# Pet Insurance Claims & Portfolio Data Platform

[![Platform CI](https://github.com/NiknaxTheGreek/pet-insurance-data-platform/actions/workflows/platform-ci.yml/badge.svg)](https://github.com/NiknaxTheGreek/pet-insurance-data-platform/actions/workflows/platform-ci.yml)
[![Reliability](https://github.com/NiknaxTheGreek/pet-insurance-data-platform/actions/workflows/reliability-suite.yml/badge.svg)](https://github.com/NiknaxTheGreek/pet-insurance-data-platform/actions/workflows/reliability-suite.yml)
[![Security](https://github.com/NiknaxTheGreek/pet-insurance-data-platform/actions/workflows/security.yml/badge.svg)](https://github.com/NiknaxTheGreek/pet-insurance-data-platform/actions/workflows/security.yml)

Production-style ELT / CDC capability proof for a mutable pet-insurance workload.

## Problem

Operational PostgreSQL records change after creation: claims progress through states, approved amounts change, payments arrive later, customer attributes change, and rows can be soft-deleted. A simple overwrite or timestamp-only batch can lose history or miss late data.

~~~text
PostgreSQL
  → Python incremental capture + full-state reconciliation
  → Snowflake RAW / CONTROL
  → dbt STAGING
  → dbt INTERMEDIATE
  → dbt MARTS
~~~

GitHub Actions provides CI/CD and Snowflake OIDC. Docker provides a reproducible PostgreSQL source. Dagster proves the same dependency chain can be expressed as an orchestrated workload.

A second executed path proves managed log-based CDC:

~~~text
Neon PostgreSQL
  → logical replication / WAL
  → Estuary Flow
  → Snowflake PET_INSURANCE_ESTUARY.CLAIMS
~~~

## Current verified evidence

- Live PostgreSQL → Snowflake set-based ingestion: PASS
- Transaction rollback after RAW MERGE / before watermark: PASS
- New-key late arrival recovery: PASS
- Existing-key late-version recovery: PASS
- Duplicate / no-change replay: PASS
- Soft-delete propagation: PASS
- Additive schema evolution: PASS
- Breaking schema change rejection: PASS
- Customer SCD2 history: PASS
- Security gate (gitleaks + dependency audit + Ruff): PASS
- Dagster orchestration proof: PASS
- Controlled scale benchmark: PASS
- Estuary WAL capture: INSERT / UPDATE / physical DELETE PASS
- Estuary → Snowflake materialization: PASS
- Snowflake Estuary history: 1 create + 1 update + 1 delete for the disposable CDC claim
- Python tests: 24 passed
- dbt: 11 models + 67 tests; 78/78 build nodes passed

Executed evidence is indexed in [docs/evidence/](docs/evidence/).

## Focal claim history

| State | Claim amount | Approved | Paid |
| --- | ---: | ---: | ---: |
| SUBMITTED | R8,500 | — | — |
| APPROVED | R11,200 | R9,700 | — |
| PAID | R11,200 | R9,700 | R9,700 |

CLM-10042 preserves all three states. An unchanged replay inserts zero new versions.

## Ingestion design

Normal fast path:

- validate the PostgreSQL source contract;
- read a composite (updated_at, primary_key) watermark;
- canonicalize and SHA-256 hash source payloads;
- stage rows in batches;
- execute one set-based Snowflake MERGE per table;
- commit RAW + watermark + SUCCESS audit atomically;
- clean stage rows;
- expose operational state through INGESTION_HEALTH.

Correctness path:

- compare the full current source-version identity (table, primary key, source_updated_at, payload_hash);
- recover new or changed versions that arrived behind the high watermark;
- replay reconciliation without duplication.

See [run_ingestion.py](src/insurance_platform/run_ingestion.py) and [reconcile_source_state.py](src/insurance_platform/reconcile_source_state.py).

## Transaction failure proof

The atomicity workflow deliberately raises an exception after the claims RAW MERGE and before watermark update.

Verified result: RAW rolled back; the watermark did not advance; the FAILED batch audit remained; stage rows were cleaned; normal retry loaded the source version once; a final unchanged replay inserted zero rows.

Evidence: [transaction_atomicity.md](docs/evidence/transaction_atomicity.md).

## Data contracts and governance

Versioned source contracts live in [contracts/](contracts/). They enforce required columns, types, nullability and primary keys while allowing logged additive fields.

Schema-evolution CI proves an additive submission_channel field is accepted and preserved while an incompatible nullability change is rejected.

Direct customer names are kept out of analytics marts. dbt also tests cross-entity insurance integrity, accepted values, payment limits, claim/policy dates and the PII boundary.

## Scale proof

A clean benchmark generated and loaded 82,956 rows:

- 10,000 customers
- 14,916 pets
- 14,916 policies
- 29,828 claims
- 13,296 claim payments

First set-based ingestion reconciled every row. The immediate second run produced zero candidates and zero inserts across all five tables.

This is a controlled scale test, not an enterprise-throughput claim.

Evidence: [scale_benchmark.md](docs/evidence/scale_benchmark.md).

## dbt

Layering: RAW → STAGING → INTERMEDIATE → MARTS.

Key models include typed staging models, backfill-safe int_claim_events, int_policy_claims, fct_claims, dim_policy, one intentional customer SCD2 and mart_portfolio_performance.

The loss-ratio field is explicitly a proxy, not an actuarial earned-premium loss ratio.

## Security and reproducibility

- Snowflake uses GitHub OIDC; no Snowflake password is stored.
- PostgreSQL DSN is an Actions secret.
- Python toolchain has a committed tested dependency lock.
- gitleaks scans full history.
- pip-audit reported no known vulnerabilities in the verified run.
- Docker boots and validates a clean source schema.
- Makefile provides zero-to-green local commands.
- [docs/runbook.md](docs/runbook.md) contains diagnosis and recovery procedures.

Verified Snowflake trial compute: Standard X-Small, auto-resume enabled, auto-suspend 300 seconds.

The live trial uses SNOWFLAKE_LEARNING_ROLE. A least-privilege production role bootstrap is documented as PROPOSED, not falsely presented as deployed.

## External integrations

- **Estuary Flow — VERIFIED.** Live Neon runs with `wal_level=logical`; Estuary captures PostgreSQL WAL events in History Mode; a controlled claim produced create, update and physical-delete events; the Estuary collection was materialized into Snowflake; Snowflake contains exactly one `c`, one `u` and one `d` event for the disposable claim. See [docs/evidence/estuary_cdc.md](docs/evidence/estuary_cdc.md).
- **Google Cloud / GCS — NOT YET PROVIDER-VERIFIED.** Deterministic export, GitHub WIF workflow, private GCS upload, Snowflake external stage/COPY and reconciliation are implemented and CI-tested on the repo side. GCP authentication/project/WIF setup is still required.

See [docs/external_integrations.md](docs/external_integrations.md) for the exact verification boundary.

## What broke while I built this

1. The intended custom Snowflake CI role did not exist in the trial account; the verified learning role was used and the production role stayed proposed.
2. PostgreSQL Decimal values broke canonical JSON serialization; deterministic Decimal handling was added and regression-tested.
3. Bootstrapping one claim advanced a table watermark past older claims; reconciliation exposed and repaired the gap.
4. A max(raw_record_id) incremental predicate could not recover older missing events; it was replaced with a unique-key anti-join.
5. Snowflake connector executemany could not rewrite an INSERT containing PARSE_JSON; JSON is staged as text and parsed in the set-based MERGE.
6. A Snowflake ALTER with a default was not idempotent against the migrated table; the migration was corrected.
7. Executable contracts exposed live-source differences from initial assumptions (VARCHAR vs TEXT, nullable breed and additional customer fields); the checked-in contract was aligned to reality.
8. Transaction testing proved failure handling must cover staging errors as well as MERGE errors.

These failures are retained as engineering evidence rather than hidden behind the final architecture.

## Quick start

~~~bash
make bootstrap
make test
make postgres-up
make postgres-smoke
make postgres-down
~~~

See [docs/reproduction.md](docs/reproduction.md) for live Snowflake execution.

## Review path

1. README
2. docs/evidence/
3. docs/runbook.md
4. src/insurance_platform/run_ingestion.py
5. src/insurance_platform/reconcile_source_state.py
6. dbt/models/
7. docs/adr/
8. GitHub Actions: Platform CI, Reliability, Transaction Atomicity, Scale Benchmark, Security Gate, Dagster proof and Estuary CDC proof

## Deliberate non-goals

Kafka, Spark, Kubernetes and a permanent orchestration service are not added merely to increase technology count. They should be introduced only when latency, scale, topology or operational requirements justify them.
