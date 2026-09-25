# Five-minute demo script

This walkthrough is designed for a strict technical reviewer. Every claim below maps to executed code, a workflow, a query result or an explicitly documented limitation.

## 0:00–0:40 — Architecture and the two CDC paths

Open the README.

Explain the custom path:

`PostgreSQL → Python incremental capture/reconciliation → Snowflake RAW/CONTROL → dbt → marts`

Then point out the separately executed managed path:

`Neon PostgreSQL WAL → Estuary Flow → Snowflake PET_INSURANCE_ESTUARY.CLAIMS`

Say:

“The custom path is useful because it exposes the engineering mechanics: watermarks, hashes, batching, transactions, reconciliation and failure recovery. The Estuary path is actual log-based CDC and proves INSERT, UPDATE and physical DELETE capture.”

## 0:40–1:25 — Focal claim and incremental correctness

Open:
- `src/insurance_platform/run_ingestion.py`
- `src/insurance_platform/reconcile_source_state.py`
- `dbt/models/intermediate/int_claim_events.sql`

Use `CLM-10042`:

1. SUBMITTED — R8,500
2. APPROVED — revised claim R11,200; approved R9,700
3. PAID — payment R9,700

Call out:
- composite `(updated_at, primary_key)` watermark;
- deterministic payload hashing;
- set-based Snowflake MERGE;
- RAW + watermark + success audit committed atomically;
- full-state version reconciliation for data behind the high watermark;
- unchanged replay inserts zero rows.

## 1:25–2:15 — Failure handling and transaction proof

Open:
- `Reliability Failure Suite`
- `Transaction Atomicity`

Explain:
- intentionally invalid payment → dbt rule fails → source repaired → rule passes;
- new-key late claim → high-watermark scan misses it → reconciliation recovers it once;
- existing-key late version → high-watermark scan misses it → reconciliation captures the new version;
- soft delete propagates and trusted current-state mart excludes it;
- injected failure after RAW MERGE but before watermark update rolls back RAW and watermark together;
- FAILED batch audit remains durable;
- retry inserts the version once;
- final replay is a no-op.

## 2:15–3:05 — Real Estuary WAL CDC

Open `docs/evidence/estuary_cdc.md`.

Use disposable claim `CLM-EST-36033857733`.

Show:
- Neon `wal_level=logical`;
- isolated publication;
- Estuary capture in History Mode;
- INSERT → `c`;
- UPDATE → `u`;
- physical DELETE → `d`;
- Snowflake materialization contains exactly one create, one update and one delete event.

Say:

“This is the path I call true log-based CDC. I do not describe the Python watermark path as WAL CDC.”

## 3:05–3:45 — dbt, contracts and governance

Open:
- `contracts/`
- `dbt/models/marts/fct_claims.sql`
- `dbt/models/marts/dim_customer_scd2.sql`
- `dbt/tests/`

Current verified state:
- 11 dbt models;
- 67 dbt tests;
- 78/78 dbt build nodes pass;
- direct customer names excluded from analytics marts;
- additive source column accepted/preserved;
- breaking nullability change rejected;
- one intentional SCD2 proves customer-history handling.

## 3:45–4:25 — Scale, security and orchestration

Show:
- `Scale Benchmark`: 82,956 deterministic rows;
- second ingestion: zero candidates / zero inserts;
- `Security Gate`: full-history gitleaks, dependency audit, Ruff, integration-script syntax;
- latest Python suite: 25 passed;
- `Dagster Orchestration Proof`: source ingestion → reconciliation → dbt → health verification.

State clearly that the scale test is controlled evidence, not an enterprise-throughput benchmark.

## 4:25–5:00 — GCP and engineering judgement

Open `docs/evidence/gcp_bigquery_sandbox.md`.

Explain:

“The intended production-style GCP extension is GitHub OIDC/WIF → private GCS → Snowflake external stage/COPY. Both available GCP projects have billing disabled, so bucket creation is provider-blocked. I did not attach billing just to make a demo checkbox green. I used BigQuery Sandbox instead: authenticated Cloud Shell loaded a deterministic claims extract into a typed BigQuery table, then GoogleSQL reconciled it against the source manifest and returned PASS.”

Finish with:

“I would not call this production-ready. It is a bounded, reproducible capability proof with real failures, executed provider integrations, explicit security compromises in the trial identities and documented production extensions.”
