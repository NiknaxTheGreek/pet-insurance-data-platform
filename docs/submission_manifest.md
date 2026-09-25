# Submission candidate manifest

Date: 2026-09-25

Repository: `NiknaxTheGreek/pet-insurance-data-platform`

## Verified evidence

| Capability | Evidence |
| --- | --- |
| Consolidated Python + Docker + Snowflake/dbt gate | Platform CI run 36113302708 — PASS |
| Python suite | Platform CI run 36113302708, Python quality job — 25 passed |
| Security gate | run 36113322776 — PASS |
| Live hardened incremental ingestion | run 35988189813 — PASS |
| Reliability / late-data / soft-delete suite | run 35989125299 — PASS |
| Transaction rollback atomicity | run 35989925581 — PASS |
| Additive + breaking schema evolution | run 35988832514 — PASS |
| 82,956-row controlled scale benchmark | run 35990122190 — PASS |
| Dagster orchestration proof | run 35990181134 — PASS |
| Estuary Neon capture | run 36033392711 — PASS |
| Estuary INSERT/UPDATE/physical DELETE | run 36033857733 — PASS |
| Estuary → Snowflake materialization | run 36040696100 — PASS |
| Estuary C/U/D history in Snowflake | run 36041150766 — PASS |
| GCP BigQuery Sandbox | authenticated Cloud Shell manual execution — PASS |

## Verified outcomes

- Custom PostgreSQL → Snowflake incremental pipeline is live.
- Ingestion stages rows and performs one set-based Snowflake MERGE per table.
- RAW + watermark + success audit are one transaction.
- Failure after RAW MERGE/before watermark advancement rolls back correctly.
- Failure batches remain auditable.
- Payload hashes and merge identity make unchanged replays idempotent.
- Full-state reconciliation recovers both new late keys and late changed versions of existing keys.
- `CLM-10042` preserves `SUBMITTED → APPROVED → PAID`.
- Customer SCD2 history is verified with a real attribute change.
- Invalid payment data is detected, repaired and retested.
- Soft-delete propagation is verified.
- Source contracts allow logged additive fields and reject breaking changes.
- Analytics marts exclude direct customer-name PII.
- dbt: 11 models + 67 tests; 78/78 build nodes pass.
- Python: 25 tests pass.
- Controlled scale benchmark loads 82,956 rows and then proves a zero-change replay.
- Estuary Flow uses Neon logical replication/WAL and captured one create, one update and one physical delete for the disposable claim.
- Snowflake materialized all three Estuary history events.
- BigQuery Sandbox provider execution loaded a deterministic typed claims dataset and reconciled it against a manifest in GoogleSQL.
- Security gates include full-history secret scanning, dependency audit and static checks.
- Dagster expresses the execution dependency chain.
- Snowflake trial warehouse: Standard X-Small, auto-resume true, auto-suspend 300 seconds.

## Deliberate limitations

- The project is **production-style**, not production-ready.
- The trial uses `SNOWFLAKE_LEARNING_ROLE`, not the proposed production least-privilege Snowflake role.
- Estuary's live trial reuses the Neon owner role and Snowflake GitHub service user; production would separate CDC identities.
- The custom Python path is watermark + reconciliation, not WAL CDC. The separately executed Estuary path is the log-based CDC proof.
- GCS → Snowflake code is implemented but not provider-executed because available GCP projects have billing disabled and bucket creation returns HTTP 403.
- BigQuery Sandbox is the executed GCP capability proof; it is not presented as a substitute for production GCS architecture.
- The 82,956-row benchmark is controlled evidence, not a production-scale throughput claim.
- Kafka, Spark, Kubernetes and Terraform are intentionally absent because the use case does not justify them.

## Primary review path

1. `README.md`
2. `docs/evidence/README.md`
3. `docs/evidence/estuary_cdc.md`
4. `docs/evidence/gcp_bigquery_sandbox.md`
5. `docs/runbook.md`
6. `docs/demo_script.md`
7. `docs/adr/`
8. GitHub Actions evidence
