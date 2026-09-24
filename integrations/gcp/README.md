# GCP / GCS historical backfill proof

Status: **READY FOR PROVIDER AUTHORIZATION — NOT YET EXECUTED IN GCP**

Path:

`PostgreSQL current claims export → private Google Cloud Storage object → Snowflake external GCS stage → COPY INTO → reconciliation`

## Security model

GitHub authenticates to Google Cloud using Workload Identity Federation (OIDC), not a service-account key.

Required GitHub repository variables:
- `GCP_PROJECT_ID`
- `GCP_WORKLOAD_IDENTITY_PROVIDER`
- `GCP_SERVICE_ACCOUNT`
- `GCS_BUCKET`

No GCP private key is required.

The service account should have only the bucket permissions required to upload/delete this proof object.

## One-time Snowflake/GCP trust

Snowflake requires a GCS storage integration.

1. Create `PET_INSURANCE_GCS_INTEGRATION` using `integrations/gcp/snowflake_storage_integration.sql`.
2. `DESC INTEGRATION PET_INSURANCE_GCS_INTEGRATION`.
3. Grant the returned Snowflake GCP service account `roles/storage.objectViewer` on the proof bucket.
4. Keep the bucket private.

## Workflow

`GCP GCS Backfill Proof` will:

1. export claims deterministically from live PostgreSQL;
2. write a manifest containing SHA-256, row count, claim-amount sum and ID bounds;
3. authenticate GitHub→GCP through WIF;
4. upload the CSV + manifest to `gs://<bucket>/pet-insurance-backfill/`;
5. create a Snowflake external stage against that prefix;
6. `COPY INTO PET_INSURANCE_GCP.CLAIMS_BACKFILL`;
7. reconcile Snowflake row count / amount sum / ID bounds against the source manifest.

The integration is not complete until that workflow is green.
