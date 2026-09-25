# Google Cloud evidence — BigQuery Sandbox workaround

Status: **VERIFIED GCP EXECUTION (NO BILLING)**

The original production-style GCP design remains:

`PostgreSQL export → GitHub OIDC/WIF → private GCS → Snowflake storage integration → external stage/COPY → reconciliation`

That path could not be executed in the available Google Cloud projects because both projects have billing disabled. GCS bucket creation returned HTTP 403 for the selected project.

Rather than attach billing only to satisfy a portfolio checkbox, the project includes and executed a no-billing Google Cloud proof using **BigQuery Sandbox**.

## Executed path

`Cloud Shell → deterministic Python claims export → BigQuery Sandbox dataset/table → GoogleSQL reconciliation`

Manual provider execution was confirmed by the operator on 2026-09-25 with the final PASS marker from the committed runner.

Committed command:

```bash
bash integrations/gcp/run_bigquery_sandbox.sh
```

Expected/confirmed terminal marker:

```text
GCP_BIGQUERY_SANDBOX_ASSERTION=PASS
```

## What the proof executes

The runner:

1. uses the active authenticated Google Cloud project;
2. enables the BigQuery API;
3. generates a deterministic, non-PII claims export;
4. writes a manifest containing:
   - SHA-256 of the exact CSV,
   - row count,
   - claim-amount sum,
   - minimum and maximum claim ID;
5. creates `pet_insurance_sandbox` with bounded table expiration;
6. loads the typed CSV into `claims_backfill`;
7. queries the loaded table with GoogleSQL;
8. compares BigQuery aggregates against the source manifest;
9. exits non-zero on mismatch;
10. prints `GCP_BIGQUERY_SANDBOX_ASSERTION=PASS` only after reconciliation succeeds.

## CI evidence around the runner

Although Cloud Shell execution is manual because it uses the user's authenticated Google session, the implementation is covered by repository CI:

- BigQuery Sandbox export fixture: PASS
- BigQuery reconciliation verifier: PASS
- no-billing BigQuery runner syntax/security checks: PASS
- latest Python suite: **25 passed**

Relevant commits:
- `2afe300495d3c41af5939c50ea3284bfb52b7075` — no-billing BigQuery Sandbox GCP proof
- `bf656d0d8df522e93c08bc51730df6a748a11ca3` — BigQuery export fixture
- `dc3201d9c3b474496c2977bacee95b7b31231985` — reconciliation verifier
- `03652fec695d8fbff85f50a20179aac8b1fbb3a7` — no-billing runner
- `96fb76e3250122803d98208bff9a4e7963bc8e3d` — manifest tests
- `18071d0ea9d1d9fd13ad2f54f621feb4883d5922` — runner syntax gate

## GCS / Snowflake production-style extension

The repository still contains:
- hardened GitHub→GCP WIF bootstrap;
- private-bucket configuration;
- deterministic GCS export;
- Snowflake storage-integration template;
- external-stage/COPY implementation;
- manifest-to-Snowflake reconciliation.

Provider execution is **not claimed** for this GCS path because:
- project billing is disabled;
- GCS bucket creation is blocked by the provider with HTTP 403;
- `SNOWFLAKE_LEARNING_ROLE` also lacks account-level `CREATE INTEGRATION`, which is intentionally not broadened just to satisfy the demo.

This limitation is documented rather than hidden.

## Reviewer interpretation

The project can truthfully claim:
- hands-on Google Cloud Console / Cloud Shell execution;
- GCP project configuration;
- BigQuery dataset/table creation;
- typed batch loading;
- GoogleSQL;
- deterministic manifest reconciliation;
- cost/billing-aware engineering judgment.

It should **not** claim:
- executed GCS→Snowflake provider integration;
- executed GitHub→GCP WIF authentication in the no-billing account;
- production-scale BigQuery performance.
