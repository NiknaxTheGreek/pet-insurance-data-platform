# Reliability and failure handling

This project does not treat a green happy path as sufficient evidence. The controlled reliability suite deliberately introduces failure and recovery scenarios against the live PostgreSQL → Snowflake → dbt pipeline.

## Verified scenarios

### 1. Invalid business value is detected

A payment for `CLM-10043` is intentionally written with `payment_date < claim_date`.

The record is ingested into Snowflake RAW, after which the singular dbt test `assert_payment_not_before_claim` is expected to fail. The workflow itself only continues if that specific test returns a failure.

Verified result:
- dbt test returned exactly 1 failing record.
- The workflow recorded the failure as expected rather than treating it as a pipeline defect.
- The source payment date was repaired.
- The repaired version was incrementally ingested.
- The same dbt test then passed.

### 2. Late-arriving source data is recovered

A claim is inserted into PostgreSQL with an `updated_at` timestamp deliberately older than the current claims watermark.

Verified result:
- Normal watermark ingestion extracted 0 claim candidates and therefore did not load the late claim.
- A reconciliation/backfill pass detected one missing source primary key.
- The missing claim was inserted into RAW.
- A second backfill replay inserted 0 additional rows.
- Snowflake contains exactly one RAW version for that late-arriving claim.

This demonstrates an explicit limitation of simple high-watermark ingestion and a recovery mechanism rather than pretending the watermark alone is sufficient.

### 3. Soft delete is propagated

`CLM-10043` is soft-deleted at the source.

Verified result:
- The current RAW version carries `OPERATION = 'DELETE'` and `is_deleted = true`.
- `FCT_CLAIMS` no longer exposes the deleted claim.
- Full dbt build remains green.

### 4. No-change replay remains idempotent

After all repairs and mutations, the live ingestion pipeline is immediately rerun without any source changes.

Verified result:
- The latest five per-table ingestion audit rows show 0 rows extracted and 0 rows inserted.
- Duplicate/backfill replay protection remains intact.

## Observability

Every ingestion pass writes to `PET_INSURANCE_CONTROL.INGESTION_BATCHES` with:
- batch ID
- started/completed timestamps
- status
- rows extracted
- rows inserted
- notes

Per-table structured logs also report source row count, candidate count, inserted count, and reconciliation status.

## CI evidence

The successful controlled failure suite is GitHub Actions run `35917627966`.

The consolidated Platform CI is GitHub Actions run `35918223704`. It verifies:
- Python static checks
- Python tests
- clean PostgreSQL 16 Docker startup
- all five source tables
- foreign-key relationship chain
- PostgreSQL business constraint enforcement
- Snowflake OIDC connectivity
- full dbt build
- dbt docs generation
- trusted `CLM-10042` mart state
- three-row claim-history preservation

Current dbt result in Platform CI: `PASS=67 WARN=0 ERROR=0 SKIP=0`.
