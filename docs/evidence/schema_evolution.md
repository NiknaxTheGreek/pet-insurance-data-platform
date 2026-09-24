# Schema-evolution evidence

Run: 35988832514  
Workflow: Schema Evolution  
Result: PASS

Baseline:
All five source contracts passed.

Additive change:
```sql
ALTER TABLE claims ADD COLUMN submission_channel VARCHAR(30);
```

A representative row was set to `WEB`.

Observed:
- contract validation logged `submission_channel` as additive;
- validation still passed;
- source serialization preserved `submission_channel=WEB`.

Breaking change:
The workflow changed `claim_status` nullability incompatibly.

Observed:
- contract validation failed with a nullability mismatch;
- the workflow asserted that rejection;
- schema was restored and validation passed again.

Conclusion:
Additive changes are tolerated/preserved; governed breaking changes fail before ingestion.
