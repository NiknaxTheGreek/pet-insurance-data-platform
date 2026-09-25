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

### 2. Late-arriving source versions are recovered

The suite tests both a new claim key and a later version of an existing claim with `updated_at` values deliberately older than the current claims watermark.

Verified result:
- Normal watermark ingestion misses the deliberately old versions.
- Full-state reconciliation compares complete source-version identity `(source_table, source_pk, source_updated_at, payload_hash)`.
- The missing new-key claim is recovered exactly once.
- A later version of an already-known claim key is also recovered without overwriting the earlier version.
- Replaying reconciliation inserts no duplicates.

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

The current extended controlled failure suite is GitHub Actions run `35989125299`.

The current consolidated Platform CI is GitHub Actions run `36113302708`. It verifies:
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

Current Platform CI results: Python `25 passed`; dbt `PASS=78 WARN=0 ERROR=0 SKIP=0 TOTAL=78`.
