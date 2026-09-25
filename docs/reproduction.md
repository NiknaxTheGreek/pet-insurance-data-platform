# Reproduction and operating guide

## Local verification

If the architecture or terminology is unfamiliar, read [theory_and_architecture.md](theory_and_architecture.md) first. This guide intentionally keeps reproduction separate from theory.

Requirements:

| Tool | What it is | Why it is needed here |
| --- | --- | --- |
| Git | distributed version control | clone and inspect the repository history |
| Python 3.12 | programming/runtime environment | tests, ingestion and utilities |
| Docker + Docker Compose | container runtime and service definition | reproduce a clean PostgreSQL source locally |
| PostgreSQL client knowledge | relational SQL source concepts | understand the operational schema and smoke tests |
| Snowflake access | cloud analytical warehouse | live RAW/CONTROL and dbt execution |
| dbt | SQL transformation framework | build and test staging/intermediate/marts |

Bootstrap and test:

```bash
make bootstrap
make test
make postgres-up
make postgres-smoke
make postgres-down
```

The clean PostgreSQL source reproduces the live-style string-ID schema and enforces the customer → pet → policy → claim → payment relationship plus source constraints.

## Live custom PostgreSQL → Snowflake path

Required:
- repository secret `POSTGRES_DSN`;
- Snowflake service user `PET_INSURANCE_GITHUB`;
- GitHub OIDC workload identity;
- current trial warehouse/database/role access.

Run:
`Live Incremental Ingestion`

The runner:
1. validates source contracts;
2. extracts changes using composite `(updated_at, primary_key)` watermarks;
3. canonicalizes and hashes payloads;
4. stages records in bounded batches;
5. performs one set-based RAW MERGE per table;
6. reconciles staged candidates;
7. commits RAW + watermark + SUCCESS audit atomically;
8. cleans stage rows;
9. exposes state through `INGESTION_HEALTH`.

For versions that fall behind the high watermark:

```bash
python -m insurance_platform.reconcile_source_state
```

This compares `(source_table, source_pk, source_updated_at, payload_hash)` and is idempotent.

## dbt

Core commands:

```bash
dbt debug --project-dir dbt --profiles-dir dbt
dbt build --project-dir dbt --profiles-dir dbt --fail-fast
dbt docs generate --project-dir dbt --profiles-dir dbt
```

Current verified result:
- 11 models
- 67 tests
- 78/78 dbt build nodes pass

## Estuary WAL CDC

See:
`integrations/estuary/README.md`

Executed provider path:

`Neon PostgreSQL → logical replication/WAL → Estuary Flow → Snowflake`

The repository contains:
- source-readiness checker;
- direct-Neon DSN derivation;
- `flowctl` capture publisher;
- C/U/D mutation proof;
- Snowflake JWT materialization workflow;
- final Snowflake C/U/D assertion.

Evidence:
`docs/evidence/estuary_cdc.md`

## GCP no-billing proof

See:
`integrations/gcp/BIGQUERY_SANDBOX.md`

From authenticated Google Cloud Shell:

```bash
python3 -m pip install -e . --no-deps
bash integrations/gcp/run_bigquery_sandbox.sh
```

Success marker:

```text
GCP_BIGQUERY_SANDBOX_ASSERTION=PASS
```

The runner loads a deterministic typed claims dataset into BigQuery Sandbox and reconciles it against its SHA-256/source aggregate manifest.

The production-style GCS → Snowflake implementation remains under `integrations/gcp/`, but provider execution requires a billing-enabled GCP project.

## Main verification workflows

- `Platform CI` — consolidated Python, Docker/PostgreSQL and Snowflake/dbt gate
- `Live Incremental Ingestion` — live custom PostgreSQL → Snowflake path
- `Reliability Failure Suite` — invalid-data, late-arrival/version and delete scenarios
- `Transaction Atomicity` — injected rollback proof
- `Schema Evolution` — additive acceptance + breaking rejection
- `Scale Benchmark` — deterministic 82,956-row ingestion/replay proof
- `Security Gate` — gitleaks, dependency audit, static and shell checks
- `Dagster Orchestration Proof` — dependency-chain execution
- `Estuary CDC Mutation Proof` — managed WAL create/update/physical-delete proof
- `Submission Package` — reproducible review-package checkpoint

Provider-side Estuary setup/materialization runs and the manual BigQuery Sandbox proof are retained in the evidence documentation even though one-off diagnostic workflows were removed from the final review surface.
