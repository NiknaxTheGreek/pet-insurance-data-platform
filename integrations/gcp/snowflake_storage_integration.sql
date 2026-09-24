-- ONE-TIME GCS STORAGE INTEGRATION TEMPLATE.
-- Requires an administrative Snowflake role with CREATE INTEGRATION on account.
-- Replace the bucket placeholder before execution.

-- CREATE STORAGE INTEGRATION PET_INSURANCE_GCS_INTEGRATION
--   TYPE = EXTERNAL_STAGE
--   STORAGE_PROVIDER = 'GCS'
--   ENABLED = TRUE
--   STORAGE_ALLOWED_LOCATIONS = ('gcs://<bucket>/pet-insurance-backfill/');

-- Then run:
-- DESC INTEGRATION PET_INSURANCE_GCS_INTEGRATION;
--
-- Grant the returned STORAGE_GCP_SERVICE_ACCOUNT roles/storage.objectViewer
-- on only the target bucket/prefix in Google Cloud.
