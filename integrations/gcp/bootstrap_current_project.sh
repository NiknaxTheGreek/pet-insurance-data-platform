#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="$(gcloud config get-value project 2>/dev/null || true)"
if [[ -z "$PROJECT_ID" || "$PROJECT_ID" == "(unset)" ]]; then
  echo "No active Google Cloud project is selected." >&2
  echo "Available projects:" >&2
  gcloud projects list --format="table(projectId,name,projectNumber)" >&2
  echo >&2
  echo "Select one with:" >&2
  echo "  gcloud config set project YOUR_PROJECT_ID" >&2
  exit 2
fi

BUCKET_NAME="${PROJECT_ID}-pet-insurance-backfill"
LOCATION="${GCP_BACKFILL_LOCATION:-EU}"

echo "Selected GCP project: $PROJECT_ID"
echo "Proof bucket: $BUCKET_NAME"
echo "Location: $LOCATION"
echo

bash integrations/gcp/bootstrap_gcp.sh "$PROJECT_ID" "$BUCKET_NAME" "$LOCATION"
