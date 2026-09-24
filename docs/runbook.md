# Operations runbook

This runbook is for diagnosing and recovering the live PostgreSQL → Snowflake → dbt pipeline.

## 1. Ingestion failed

Symptoms:
- GitHub Actions `Live Incremental Ingestion` is red.
- `PET_INSURANCE_CONTROL.INGESTION_HEALTH.LATEST_STATUS = 'FAILED'`.

Check:
```sql
select *
from PET_INSURANCE_CONTROL.INGESTION_HEALTH
order by SOURCE_TABLE;
```

Then inspect:
```sql
select *
from PET_INSURANCE_CONTROL.INGESTION_BATCHES
where STATUS = 'FAILED'
order by STARTED_AT desc;
```

Expected behavior:
- RAW and watermark updates are committed together.
- A failure after RAW MERGE but before watermark update rolls back both.
- Failure metadata remains in the batch audit.
- Staging rows are cleaned up.

Proof: GitHub Actions run 35989925581.

Recovery:
1. Fix the root cause.
2. Re-run the ingestion workflow.
3. Verify the failed source version appears once in RAW.
4. Re-run unchanged and confirm 0 extracted / 0 inserted.

## 2. PostgreSQL source unreachable

Check:
- `POSTGRES_DSN` exists in repository Actions secrets.
- Source host accepts connections.
- The source database is `pet_insurance`.
- The runtime user has SELECT access to the five source tables.

Do not advance any Snowflake watermark if extraction fails.

Recovery:
- Restore source connectivity and re-run.
- The unchanged Snowflake state should remain valid because extraction precedes the transactional RAW/watermark write.

## 3. Snowflake unavailable or authentication fails

Check GitHub OIDC identity and environment:
- `SNOWFLAKE_ACCOUNT`
- `SNOWFLAKE_USER`
- `SNOWFLAKE_ROLE`
- `SNOWFLAKE_WAREHOUSE`
- `SNOWFLAKE_DATABASE`

Use `Snowflake OIDC Deploy` to verify workload identity and platform objects.

Never replace OIDC with a committed password or private key.

## 4. Watermark looks wrong

Inspect:
```sql
select *
from PET_INSURANCE_CONTROL.INGESTION_WATERMARKS
order by SOURCE_TABLE;
```

Compare with the latest source values.

Important: a high watermark is only the fast path. A source record with an older `updated_at` can fall behind the watermark.

Recovery:
```bash
python -m insurance_platform.reconcile_source_state
```

This compares the full current source-version identity:
`(source_table, source_pk, source_updated_at, payload_hash)`

It therefore recovers:
- a new late key;
- a late changed version of an existing key.

Proof: reliability run 35989125299.

## 5. Duplicate or replayed source event

Expected behavior:
- deterministic canonical JSON → SHA-256 payload hash;
- RAW merge identity includes table, primary key, source timestamp and payload hash;
- replaying the same source version inserts nothing.

Verify:
```sql
select SOURCE_TABLE, SOURCE_PK, SOURCE_UPDATED_AT, PAYLOAD_HASH, count(*)
from PET_INSURANCE_RAW.SOURCE_RECORDS
group by 1,2,3,4
having count(*) > 1;
```

Expected result: zero rows.

## 6. Late-arriving record

Run normal ingestion first. If the version is behind the current watermark it may be missed.

Then run full-state reconciliation:
```bash
python -m insurance_platform.reconcile_source_state
```

Verify the version appears exactly once, then replay reconciliation and confirm zero new inserts.

## 7. dbt test failed

Run:
```bash
dbt test --project-dir dbt --profiles-dir dbt --select <test_name>
```

Do not bypass the test.

Identify whether the issue is:
- invalid source data;
- transformation bug;
- contract mismatch;
- legitimate business-rule change.

The reliability suite intentionally proves the repair lifecycle for a payment dated before its claim.

## 8. Source schema changed

Run:
```bash
python -m insurance_platform.validate_contracts
```

Rules:
- additive columns are allowed and logged;
- missing required fields fail;
- incompatible type/nullability changes fail;
- primary-key changes fail.

For an additive field:
1. confirm RAW preserves it;
2. decide whether it belongs in typed staging/marts;
3. update the contract deliberately if it becomes governed.

Proof: schema-evolution run 35988832514.

## 9. Soft delete

Source rows with `is_deleted=true` are mapped to RAW operation `DELETE`.

Verify latest RAW state:
```sql
select SOURCE_PK, OPERATION, PAYLOAD:is_deleted::boolean
from PET_INSURANCE_RAW.SOURCE_RECORDS
where SOURCE_TABLE='claims' and SOURCE_PK='<claim>'
qualify row_number() over (
  partition by SOURCE_PK order by SOURCE_UPDATED_AT desc, RAW_RECORD_ID desc
)=1;
```

Trusted current marts should not expose the deleted claim.

## 10. Backfill required

For current-state reconciliation:
```bash
python -m insurance_platform.reconcile_source_state
```

For larger historical file backfills, use a separate bounded backfill path; do not reset production watermarks to an older value.

## 11. Secret rotated

Update only the secret store / workload identity configuration.

Never edit code to embed credentials.

After rotation:
1. run Security Gate;
2. run Snowflake OIDC Deploy;
3. run Live Incremental Ingestion;
4. verify `INGESTION_HEALTH`.

## 12. Warehouse unexpectedly running

Inspect Snowflake warehouse state and auto-suspend.

Verified project setting:
- X-Small
- Standard
- auto-resume enabled
- auto-suspend 300 seconds

Do not add a continuously running warehouse for this project.

## 13. Escalation evidence to capture

For every incident record:
- GitHub run ID
- commit SHA
- source table
- batch ID
- error class/message
- watermark before/after
- source/candidate/inserted counts
- reconciliation result
- recovery command
- final verification query
