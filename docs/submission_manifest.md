# Submission candidate manifest

Date: 2026-09-23

Repository: `NiknaxTheGreek/pet-insurance-data-platform`

## Verified live evidence

| Capability | Successful GitHub Actions run |
| --- | --- |
| Consolidated Python + Docker + Snowflake/dbt gate | 35919603166 |
| Controlled reliability/failure suite | 35917627966 |
| dbt build/tests/docs | 35919603153 |
| Performance and incremental evidence | 35920236535 |
| Snowflake OIDC infrastructure deploy | 35920035848 |
| Python ingestion tests | 35918223717 |
| T4 paid-claim CDC demo | 35910931007 |
| Customer SCD2 demo | 35913661769 |

## Verified outcomes

- PostgreSQL→Snowflake incremental pipeline is live.
- Snowflake OIDC authentication is live.
- Append-only RAW and CONTROL audit/watermark tables are live.
- `CLM-10042` preserves `SUBMITTED → APPROVED → PAID`.
- T4 payment is R9,700.
- Immediate ingestion replay inserts zero rows when the source is unchanged.
- Customer SCD2 history is verified with a real attribute change.
- Controlled invalid payment data is detected by dbt, repaired and retested.
- Late-arriving claim recovery is verified through reconciliation/backfill.
- Soft-delete propagation is verified through RAW and the trusted mart.
- dbt build result: `PASS=67 WARN=0 ERROR=0 SKIP=0`.
- Dockerized PostgreSQL 16 source boots cleanly and enforces constraints.
- RAW has 8 claim versions and the incremental claim-event model has all 8; missing events = 0.
- Snowflake performance evidence shows the backfill-safe anti-join plan and successful no-op repeat runs.
- Verified Snowflake learning warehouse: Standard X-Small, auto-resume true, auto-suspend 300 seconds.

## Deliberate limitations / not implemented

- Production least-privilege Snowflake role/warehouse/database bootstrap is **PROPOSED**, not the verified trial deployment.
- Current trial execution uses `SNOWFLAKE_LEARNING_ROLE`, `SNOWFLAKE_LEARNING_WH`, and `SNOWFLAKE_LEARNING_DB`.
- Change capture is watermark + reconciliation based, not PostgreSQL WAL/logical replication.
- No Airflow/Kafka/Spark/Kubernetes/Terraform/dashboard/ML layer is implemented because none is required for the defined capability proof.
- Performance evidence is from a deliberately small workload and is not a production-scale benchmark.

## Primary review path

1. `README.md`
2. `docs/demo_script.md`
3. `docs/reliability.md`
4. `docs/performance_cost.md`
5. `docs/adr/`
6. Successful `Platform CI` and `Reliability Failure Suite` runs
