# Reproduction and operating guide

## Local verification

Requirements:
- Python 3.12 recommended
- Docker with Docker Compose

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

The production-style GCS → Snowflake implementation remains under `integrations/gcp/` and `.github/workflows/gcp-backfill.yml`, but provider execution requires a billing-enabled GCP project.

## Main verification workflows

- `Platform CI` — consolidated Python, Docker/PostgreSQL and Snowflake/dbt gate
- `Live Incremental Ingestion` — live custom source path
- `Reliability Failure Suite` — invalid-data, late-arrival/version and delete scenarios
- `Transaction Atomicity` — injected rollback proof
- `Schema Evolution` — additive acceptance + breaking rejection
- `Scale Benchmark` — deterministic 82,956-row ingestion/replay proof
- `Security Gate` — gitleaks, dependency audit, static/shell checks
- `Dagster Orchestration Proof` — dependency-chain execution
- `Estuary Neon Capture` — WAL capture publish
- `Estuary CDC Mutation Proof` — create/update/physical-delete proof
- `Estuary Snowflake Materialization` — managed CDC destination
- `Estuary Snowflake CDC Evidence` — final Snowflake history assertion

## Secrets and identities

Never commit:
- PostgreSQL DSN;
- Estuary refresh token;
- Snowflake OIDC token;
- private RSA keys.

Persistent secrets used by provider workflows are held in repository secret storage. Snowflake CI uses short-lived GitHub OIDC. Estuary's Snowflake JWT private key is generated ephemerally by CI for the trial proof.

See `docs/runbook.md` for operational recovery procedures.
