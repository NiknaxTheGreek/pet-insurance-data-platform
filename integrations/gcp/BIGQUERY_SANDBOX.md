# GCP proof — BigQuery Sandbox

Status: **NO-BILLING EXECUTION PATH**

The original GCS design remains in this repository as the production-style cloud-object-storage path, but the available GCP projects have billing disabled. Google Cloud Storage bucket creation therefore returns HTTP 403.

Rather than attach a billing account only to satisfy a portfolio checkbox, the executed GCP proof uses **BigQuery Sandbox**, which Google supports without a credit card or billing account.

Path:

`Cloud Shell → deterministic Python claims dataset → BigQuery Sandbox dataset/table → GoogleSQL reconciliation`

## What this proves

- hands-on Google Cloud Console / Cloud Shell;
- GCP project configuration;
- BigQuery dataset and table creation;
- typed batch loading;
- GoogleSQL aggregation;
- source-manifest vs warehouse reconciliation;
- bounded lifecycle through a 24-hour default table expiration;
- explicit cost and billing awareness.

## Run

From the repository in authenticated Cloud Shell:

```bash
python3 -m pip install -e . --no-deps
bash integrations/gcp/bootstrap_bigquery_sandbox.sh
```

Expected final marker:

`GCP_BIGQUERY_SANDBOX_PROOF=PASS`

## Data

The proof generates 5,000 deterministic, non-PII synthetic claim rows.

The manifest contains SHA-256 of the exact CSV, row count, claim-amount sum, and ID bounds. The script loads the CSV into BigQuery and asserts the warehouse aggregates match.

## Why not GCS in this account?

The GCS/WIF implementation remains under `integrations/gcp/` as a production-style extension.

Provider execution is blocked because both available projects have `billingEnabled: false`. Attempted GCS bucket creation returned HTTP 403 because the project has no active billing account.

This provider/account limitation is documented rather than disguised as an implementation success.

## Production extension

With billing enabled, the intended production-style path is:

`PostgreSQL export → GitHub OIDC/WIF → private GCS → Snowflake storage integration → external stage/COPY → reconciliation`

The code remains in the repository, while BigQuery Sandbox is the executable no-billing GCP capability proof.
