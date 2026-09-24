#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="${1:?Usage: bootstrap_gcp.sh PROJECT_ID BUCKET_NAME [LOCATION]}"
BUCKET_NAME="${2:?Usage: bootstrap_gcp.sh PROJECT_ID BUCKET_NAME [LOCATION]}"
LOCATION="${3:-EU}"

REPOSITORY="NiknaxTheGreek/pet-insurance-data-platform"
POOL_ID="github-pet-insurance"
PROVIDER_ID="github"
SERVICE_ACCOUNT_NAME="pet-insurance-github"

gcloud config set project "$PROJECT_ID" >/dev/null

gcloud services enable   iam.googleapis.com   iamcredentials.googleapis.com   sts.googleapis.com   storage.googleapis.com   cloudresourcemanager.googleapis.com

PROJECT_NUMBER="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')"
SERVICE_ACCOUNT_EMAIL="$SERVICE_ACCOUNT_NAME@$PROJECT_ID.iam.gserviceaccount.com"

if ! gcloud iam workload-identity-pools describe "$POOL_ID"   --location=global --project="$PROJECT_ID" >/dev/null 2>&1; then
  gcloud iam workload-identity-pools create "$POOL_ID"     --location=global     --project="$PROJECT_ID"     --display-name="Pet Insurance GitHub Actions"
fi

if ! gcloud iam workload-identity-pools providers describe "$PROVIDER_ID"   --workload-identity-pool="$POOL_ID"   --location=global   --project="$PROJECT_ID" >/dev/null 2>&1; then
  gcloud iam workload-identity-pools providers create-oidc "$PROVIDER_ID"     --workload-identity-pool="$POOL_ID"     --location=global     --project="$PROJECT_ID"     --display-name="GitHub pet-insurance-data-platform"     --issuer-uri="https://token.actions.githubusercontent.com"     --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository,attribute.ref=assertion.ref"     --attribute-condition="assertion.repository=='$REPOSITORY' && assertion.ref=='refs/heads/main'"
fi

if ! gcloud iam service-accounts describe "$SERVICE_ACCOUNT_EMAIL"   --project="$PROJECT_ID" >/dev/null 2>&1; then
  gcloud iam service-accounts create "$SERVICE_ACCOUNT_NAME"     --project="$PROJECT_ID"     --display-name="Pet Insurance GitHub Actions"
fi

PRINCIPAL_SET="principalSet://iam.googleapis.com/projects/$PROJECT_NUMBER/locations/global/workloadIdentityPools/$POOL_ID/attribute.repository/$REPOSITORY"

gcloud iam service-accounts add-iam-policy-binding "$SERVICE_ACCOUNT_EMAIL"   --project="$PROJECT_ID"   --role="roles/iam.workloadIdentityUser"   --member="$PRINCIPAL_SET" >/dev/null

if ! gcloud storage buckets describe "gs://$BUCKET_NAME"   --project="$PROJECT_ID" >/dev/null 2>&1; then
  gcloud storage buckets create "gs://$BUCKET_NAME"     --project="$PROJECT_ID"     --location="$LOCATION"     --default-storage-class=STANDARD     --uniform-bucket-level-access
fi

gcloud storage buckets update "gs://$BUCKET_NAME" --public-access-prevention >/dev/null

gcloud storage buckets add-iam-policy-binding "gs://$BUCKET_NAME"   --member="serviceAccount:$SERVICE_ACCOUNT_EMAIL"   --role="roles/storage.objectAdmin" >/dev/null

PROVIDER_RESOURCE="projects/$PROJECT_NUMBER/locations/global/workloadIdentityPools/$POOL_ID/providers/$PROVIDER_ID"

cat <<EOF
GCP bootstrap complete.

Set these GitHub Actions repository variables:
GCP_PROJECT_ID=$PROJECT_ID
GCP_WORKLOAD_IDENTITY_PROVIDER=$PROVIDER_RESOURCE
GCP_SERVICE_ACCOUNT=$SERVICE_ACCOUNT_EMAIL
GCS_BUCKET=$BUCKET_NAME

Bucket security:
- uniform bucket-level access: enabled at creation
- public access prevention: enforced at creation
- GitHub service account: objectAdmin on this isolated proof bucket only

Next: create the Snowflake GCS storage integration from integrations/gcp/snowflake_storage_integration.sql.
EOF
