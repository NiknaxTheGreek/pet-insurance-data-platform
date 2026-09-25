# Executed evidence index

The project treats a claim as verified only when it maps to code plus an executed workflow/query.

| Capability | Run | Result |
| --- | ---: | --- |
| Hardened live batched ingestion + health | 35988189813 | PASS |
| Extended reliability / late existing-key recovery / delete | 35989125299 | PASS |
| Additive + breaking schema evolution | 35988832514 | PASS |
| Transaction rollback atomicity | 35989925581 | PASS |
| 10k-customer controlled scale benchmark | 35990122190 | PASS |
| Security: gitleaks + dependency audit + static gate | 35990015486 | PASS |
| Consolidated Platform CI | 35990015280 | PASS |
| Dagster orchestration proof | 35990181134 | PASS |
| Estuary WAL CDC source C/U/D | 36033857733 | PASS |
| Estuary → Snowflake materialization | 36040696100 | PASS |
| Estuary C/U/D history in Snowflake | 36041150766 | PASS |
| GCP BigQuery Sandbox provider proof | manual Cloud Shell | PASS |

The evidence files in this directory contain the scenario, expected result, actual result and verification mechanism. They do not substitute screenshots for executable proof.


## External provider evidence status

| Integration | Status | Evidence |
| --- | --- | --- |
| Estuary provider execution | VERIFIED | WAL/logical replication + INSERT/UPDATE/physical DELETE + Snowflake materialization all passed; see `estuary_cdc.md` |
| GCP provider execution | VERIFIED via BigQuery Sandbox | manual Cloud Shell execution + deterministic manifest reconciliation; see `gcp_bigquery_sandbox.md` |
| GCS→Snowflake provider execution | NOT EXECUTED | billing-disabled projects block bucket creation; implementation retained as production-style extension |

GCP capability is verified via BigQuery Sandbox; only the billing-dependent GCS→Snowflake extension remains unexecuted.
