#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="${1:-$(gcloud config get-value project 2>/dev/null || true)}"

if [[ -z "$PROJECT_ID" || "$PROJECT_ID" == "(unset)" ]]; then
  echo "No active GCP project. Run: gcloud config set project YOUR_PROJECT_ID" >&2
  exit 2
fi

DATASET="pet_insurance_sandbox"
TABLE="claims"
LOCATION="US"

echo "GCP project: $PROJECT_ID"
echo "BigQuery mode: sandbox / no billing"
echo

python3 -m insurance_platform.gcp_bigquery_sandbox

bq --project_id="$PROJECT_ID" --location="$LOCATION" mk --dataset \
  --default_table_expiration 86400 \
  "$PROJECT_ID:$DATASET" \
  2>/dev/null || true

bq --project_id="$PROJECT_ID" --location="$LOCATION" load \
  --replace \
  --source_format=CSV \
  --skip_leading_rows=1 \
  "$PROJECT_ID:$DATASET.$TABLE" \
  work/gcp_bigquery_sandbox/claims_bigquery_sandbox.csv \
  claim_id:STRING,policy_id:STRING,pet_id:STRING,claim_type:STRING,claim_date:DATE,claim_amount:NUMERIC,approved_amount:NUMERIC,claim_status:STRING,is_deleted:BOOL

python3 - <<'PY'
import json
import subprocess

project = subprocess.check_output(
    ["gcloud", "config", "get-value", "project"],
    text=True,
).strip()
manifest = json.load(open(
    "work/gcp_bigquery_sandbox/claims_bigquery_sandbox_manifest.json",
    encoding="utf-8",
))

query = (
    "SELECT COUNT(*) AS row_count, "
    "CAST(ROUND(SUM(claim_amount), 2) AS STRING) AS claim_amount_sum, "
    "MIN(claim_id) AS min_claim_id, MAX(claim_id) AS max_claim_id "
    f"FROM `{project}.pet_insurance_sandbox.claims`"
)

raw = subprocess.check_output(
    [
        "bq",
        f"--project_id={project}",
        "--location=US",
        "--format=json",
        "query",
        "--use_legacy_sql=false",
        query,
    ],
    text=True,
)
rows = json.loads(raw)
if len(rows) != 1:
    raise SystemExit(f"Expected one aggregate row, got {len(rows)}")

actual = rows[0]
expected = {
    "row_count": str(manifest["row_count"]),
    "claim_amount_sum": manifest["claim_amount_sum"],
    "min_claim_id": manifest["min_claim_id"],
    "max_claim_id": manifest["max_claim_id"],
}

for key, expected_value in expected.items():
    actual_value = str(actual[key])
    if actual_value != str(expected_value):
        raise SystemExit(
            f"BIGQUERY_RECONCILIATION_FAIL {key}: "
            f"expected={expected_value} actual={actual_value}"
        )

print("GCP_BIGQUERY_SANDBOX_RECONCILIATION=PASS")
print(json.dumps({"expected": expected, "actual": actual}, sort_keys=True))
PY

bq --project_id="$PROJECT_ID" --location="$LOCATION" query \
  --use_legacy_sql=false \
  "SELECT claim_status, COUNT(*) AS claims, ROUND(SUM(claim_amount), 2) AS claim_amount
   FROM \`$PROJECT_ID.$DATASET.$TABLE\`
   GROUP BY claim_status
   ORDER BY claim_status"

echo "GCP_BIGQUERY_SANDBOX_PROOF=PASS"
