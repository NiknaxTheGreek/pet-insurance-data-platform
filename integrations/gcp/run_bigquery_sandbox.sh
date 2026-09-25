#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="${1:-$(gcloud config get-value project 2>/dev/null)}"

if [[ -z "$PROJECT_ID" || "$PROJECT_ID" == "(unset)" ]]; then
  echo "No active Google Cloud project." >&2
  exit 2
fi

export GOOGLE_CLOUD_PROJECT="$PROJECT_ID"
export PYTHONPATH="$PWD/src${PYTHONPATH:+:$PYTHONPATH}"

echo "GCP BigQuery Sandbox proof"
echo "Project: $PROJECT_ID"

gcloud services enable bigquery.googleapis.com --project="$PROJECT_ID"

python -m insurance_platform.gcp_bigquery_sandbox_export

if ! bq --project_id="$PROJECT_ID" show pet_insurance_sandbox >/dev/null 2>&1; then
  bq --project_id="$PROJECT_ID" mk \
    --dataset \
    --location=EU \
    --default_table_expiration=2592000 \
    "$PROJECT_ID:pet_insurance_sandbox"
fi

bq --project_id="$PROJECT_ID" load \
  --replace \
  --source_format=CSV \
  --skip_leading_rows=1 \
  "$PROJECT_ID:pet_insurance_sandbox.claims_backfill" \
  work/gcp_bigquery/claims_sandbox.csv \
  "claim_id:STRING,policy_id:STRING,pet_id:STRING,claim_type:STRING,claim_date:DATE,claim_amount:NUMERIC,approved_amount:NUMERIC,claim_status:STRING,is_deleted:BOOL"

python -m insurance_platform.gcp_bigquery_sandbox_verify

echo
echo "GCP_BIGQUERY_SANDBOX_ASSERTION=PASS"
echo "Dataset: $PROJECT_ID.pet_insurance_sandbox"
echo "Table:   $PROJECT_ID.pet_insurance_sandbox.claims_backfill"
