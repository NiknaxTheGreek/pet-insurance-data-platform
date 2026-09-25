# Badger Submission Guide

## What to send

Primary link:

https://github.com/NiknaxTheGreek/pet-insurance-data-platform

Frozen review branch:

https://github.com/NiknaxTheGreek/pet-insurance-data-platform/tree/submission-final-2026-09-25

Guided technical documentation:
- concepts and technology definitions: `docs/concepts.md`
- analyst → analytics engineer → data engineer walkthrough: `docs/engineering_walkthrough.md`
- function-by-function ingestion explanation: `docs/ingestion_deep_dive.md`
- exact reproduction commands: `docs/reproduction.md`

Do not lead with the ZIP unless they specifically ask for an offline copy. The GitHub repository is the strongest presentation because the reviewer can see the code, documentation, commit history, Actions evidence and architecture in one place.

If an attachment is useful, use the frozen Drive checkpoint:

`06_submission_candidate.zip`

## Recommended message

Subject:

`Pet Insurance Data Platform — Snowflake, dbt, PostgreSQL and CDC`

Message:

Hi Jo,

Following our conversation, I built a small production-style insurance data platform to demonstrate the engineering capabilities we discussed in a concrete way.

The project models a mutable pet-insurance workload in PostgreSQL, incrementally propagates changes into Snowflake, transforms them through dbt and exposes tested analytical marts. I focused specifically on CDC/incremental processing, historical correctness, idempotency, reconciliation, data quality, observability, CI/CD and engineering trade-offs rather than adding technologies for their own sake.

Repository:
https://github.com/NiknaxTheGreek/pet-insurance-data-platform

A few of the verified scenarios include:
- a claim progressing from SUBMITTED → APPROVED → PAID while preserving all three historical versions;
- a no-change replay producing zero duplicate inserts;
- an intentionally invalid payment being caught by dbt, repaired and retested;
- recovery of deliberately late-arriving data that a normal high-watermark scan misses;
- soft-delete propagation from PostgreSQL through Snowflake into the trusted mart;
- a real customer attribute change producing SCD2 history;
- a real Estuary WAL/logical-replication path that captured INSERT → UPDATE → physical DELETE and materialized all three events into Snowflake;
- transaction rollback after RAW MERGE but before watermark advancement;
- additive schema evolution plus explicit breaking-change rejection;
- a controlled 82,956-row benchmark;
- consolidated GitHub Actions gates for Python, Docker/PostgreSQL, Snowflake, dbt, security and Dagster orchestration.

The README contains the architecture and evidence, and `docs/demo_script.md` gives a five-minute technical walkthrough.

Regards,
Nicholas

## 30-second explanation

“I built a production-style pet-insurance data platform around a mutable PostgreSQL source. The custom Python path uses batched incremental capture, append-only Snowflake RAW, payload hashing, transactional watermark updates and full-state reconciliation. dbt reconstructs current state and exposes tested marts. I also implemented a second, real CDC path using Neon logical replication and Estuary Flow: a disposable claim was inserted, updated, physically deleted and all three WAL events were materialized into Snowflake. The project therefore proves both the mechanics of incremental engineering and a managed log-based CDC approach.”

## Two-minute explanation

“The project starts with a PostgreSQL operational model containing customers, pets, policies, claims and claim payments.

Because those records are mutable, I did not use simple overwrite extracts. The Python ingestion layer reads incrementally using a composite `updated_at + primary key` watermark. Each source version is serialized deterministically, SHA-256 hashed and merged into an append-only Snowflake RAW table. Snowflake CONTROL tables track watermarks and batch-level row counts.

I then use dbt to move through staging, intermediate and mart layers. Staging reconstructs current source state from RAW and types the VARIANT payload. The intermediate layer contains reusable claim/policy logic and a historical incremental claim-event model. The marts expose a current claims fact, policy dimension, one deliberately chosen customer SCD2 and a portfolio-performance mart.

I also built failure scenarios because I wanted the project to demonstrate reliability rather than just successful queries. An invalid payment date is ingested, the dbt rule fails, the source is repaired and the test then passes. I insert a deliberately late claim with a timestamp older than the current watermark; normal ingestion misses it, then reconciliation recovers it exactly once. I also soft-delete a claim and verify that RAW preserves the delete while the trusted mart excludes it.

The whole project is exercised through GitHub Actions. Snowflake uses OIDC rather than a stored Snowflake password, PostgreSQL is reproducible in Docker, the current Python suite is 25/25 passing, and dbt passes all 78 build nodes. I also executed a no-billing GCP proof in authenticated Cloud Shell using BigQuery Sandbox: a deterministic claims extract was loaded into a typed BigQuery table and reconciled with GoogleSQL against its source manifest.”

## Five-minute technical walkthrough

### 0:00–0:45 — Start with the architecture

Open the README and show the Mermaid diagram.

Say:

“The source is PostgreSQL. Python handles change capture and reconciliation. Snowflake RAW preserves versions, CONTROL tracks ingestion state, and dbt creates staging, intermediate and trusted marts. GitHub Actions is the CI/CD and execution surface.”

### 0:45–1:30 — Show the ingestion code

Open:

`src/insurance_platform/run_ingestion.py`

Call out:

- composite watermark
- deterministic hashing
- idempotent MERGE
- batch IDs
- source/candidate/insert reconciliation

Then briefly show:

`src/insurance_platform/repair_initial_backfill.py`

Say:

“The high-watermark is the fast path, but it is not treated as infallible. Reconciliation is the correctness path for late/backfilled rows.”

### 1:30–2:15 — Show the focal claim

Use `CLM-10042`.

Narrative:

- T1 — SUBMITTED, R8,500
- T3 — APPROVED, amount revised to R11,200, approved R9,700
- T4 — PAID, payment R9,700

Open the successful T4 workflow and show that the immediate replay inserted zero rows.

### 2:15–3:00 — Show failure handling

Open the Reliability Failure Suite.

Explain:

- deliberately invalid payment date
- dbt test fails
- repair and retest
- deliberately late claim
- watermark scan misses it
- reconciliation restores it once
- soft delete propagates
- final no-change run inserts nothing

This is the strongest proof that the platform handles mutable data rather than only a happy-path batch load.

### 3:00–3:45 — Show dbt modeling

Open:

`dbt/models/staging/stg_claims.sql`

`dbt/models/intermediate/int_claim_events.sql`

`dbt/models/marts/fct_claims.sql`

`dbt/models/marts/dim_customer_scd2.sql`

Say:

“I kept the model deliberately small. One SCD2 is enough to show the pattern. I avoided creating dimensions and technology layers that the use case did not require.”

Mention:

- 11 models
- 67 dbt tests
- 78/78 dbt build nodes passing
- 25 Python tests passing

### 3:45–4:30 — Show CI/reproducibility

Open Platform CI.

Show:

- Python quality
- PostgreSQL Docker smoke
- Snowflake/dbt build

Say:

“The source can be recreated from the repository in a clean PostgreSQL 16 container. Snowflake uses OIDC, so there is no Snowflake password in GitHub.”

### 4:30–5:00 — Finish with engineering judgement

Open the ADR folder and `docs/performance_cost.md`.

Say:

“The project changed while I tested it. For example, the original dbt incremental model used a max RAW-record-ID predicate. Live backfill testing exposed two older rows that it could never recover, so I changed it to an anti-join against already-modeled event IDs. That moved the design toward correctness instead of preserving a simpler implementation just because it was already written.”

Close with:

“I would not call this a full production insurance platform. It is a bounded capability proof with explicit compromises and a reproducible evidence trail.”

## Likely technical questions

### “Is this real CDC?”

Answer:

“There are two separate paths. The custom Python implementation is not WAL-based CDC; it uses a composite `updated_at + primary key` watermark plus payload hashing, version preservation and full-state reconciliation. I keep that distinction explicit because it demonstrates the mechanics and failure modes directly.

Separately, I implemented and executed a real managed CDC path with Neon logical replication and Estuary Flow. Neon is running with `wal_level=logical`; Estuary captures the PostgreSQL WAL stream in History Mode; a disposable claim produced create, update and physical-delete events; and Snowflake contains exactly one `c`, one `u` and one `d` event for that claim. So I would call the Estuary path true log-based CDC, but not the custom watermark path.”

### “Why not Airflow?”

Answer:

“The workflow does not currently need a persistent scheduler or complex dependency graph. GitHub Actions is enough to demonstrate execution, CI and controlled end-to-end scenarios. If this became an operational platform with scheduled SLAs, retries across many independent DAGs, backfills and operational ownership, I would introduce an orchestrator when that complexity is justified.”

### “Why not Kafka?”

Answer:

“The workload does not require streaming latency or a durable event bus to demonstrate the stated problem. Adding Kafka would increase operational surface without improving this bounded use case. If the business needed near-real-time event propagation or multiple downstream consumers, that decision would change.”

### “How do you handle duplicates?”

Answer:

“Each source version has a deterministic payload hash and the Snowflake merge condition includes source table, source primary key, source update timestamp and payload hash. Replaying the same version does not create another RAW record. I also explicitly rerun ingestion unchanged and assert zero inserts.”

### “How do you handle late-arriving data?”

Answer:

“The normal fast path uses the composite watermark. I deliberately proved that a sufficiently old late record can fall behind that watermark. Reconciliation compares source keys with RAW and recovers missing records idempotently. That failure scenario is automated in CI.”

### “Why VARIANT in RAW?”

Answer:

“It is used only in the append-only landing layer. It preserves the complete source payload while keeping the ingestion contract simple and auditable. dbt staging is responsible for explicit typing. I would not expose VARIANT directly to analytical consumers.”

### “Why only one SCD2?”

Answer:

“Because there is only one demonstrated need to prove the history pattern. Replicating SCD2 logic across every table just to increase model count would add complexity without adding a new engineering signal.”

### “What is the loss ratio?”

Answer:

“The mart uses a paid-loss-ratio proxy based on current monthly premium annualized by twelve. It is explicitly named a proxy because the source does not contain actuarial earned-premium exposure. I would not present it as a production actuarial loss ratio.”

### “What would you change for production?”

Answer:

“I would separate the trial identities first. The Estuary proof currently reuses the Neon owner role and the existing Snowflake GitHub service user / learning role because this is a bounded trial. In production I would create dedicated least-privilege source and destination identities, environment-specific workload identities, formal promotion between environments and explicit credential rotation.

The project already proves both watermark/reconciliation and WAL-based Estuary CDC, plus Dagster orchestration, schema contracts and controlled scale testing. What I would add next would depend on real SLAs and volume: stronger environment isolation, production monitoring/on-call ownership, representative load testing and any additional orchestration or streaming infrastructure only where justified.”

### “What did you actually do in GCP?”

Answer:

“The available GCP projects have billing disabled, so the production-style GCS path cannot create a bucket. I did not attach billing just to make the demo green. Instead, I executed a BigQuery Sandbox proof from authenticated Cloud Shell, which Google supports without a billing account. The committed runner generates a deterministic claims extract and manifest, creates a typed BigQuery table, loads the data, queries it with GoogleSQL and reconciles row count, claim-amount sum and ID bounds back to the manifest. It returned `GCP_BIGQUERY_SANDBOX_ASSERTION=PASS`.

The repository still contains the production-style GitHub OIDC/WIF → private GCS → Snowflake external-stage/COPY implementation, but I explicitly label that path unexecuted because of the billing constraint.”

### “What was the most important bug you found?”

Answer:

“The dbt incremental claim-event model originally used `raw_record_id > max(raw_record_id)`. Backfill testing showed that older RAW IDs could be absent from the target even though the target already had a higher max ID. That meant a max-only predicate could never recover them. I changed the model to a `NOT EXISTS` anti-join on its unique event key and verified RAW and modeled claim history both contain all eight versions.”

## What not to say

Avoid saying:

- “This is production-ready.”
- “This is true PostgreSQL CDC” without the watermark/reconciliation qualification.
- “The loss ratio is actuarially correct.”
- “The performance test proves production scale.”
- “The Snowflake least-privilege role is implemented.” It is proposed; the verified trial uses the learning role.
- “I used Kafka/Airflow because production systems should use them.” They are intentionally absent.

Prefer:

- “production-style”
- “verified capability proof”
- “CDC semantics using watermark + reconciliation”
- “bounded implementation with explicit trade-offs”
- “tested against controlled failure scenarios”

## Best review order for Badger

1. README
2. Platform CI
3. Reliability Failure Suite
4. Estuary WAL CDC evidence
5. GCP BigQuery Sandbox evidence
6. Transaction Atomicity
7. Scale Benchmark
8. dbt models
9. ADRs
10. Performance/cost evidence

The reviewer should not need the ZIP unless they want an offline copy.
