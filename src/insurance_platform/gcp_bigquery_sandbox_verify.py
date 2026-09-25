from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


def run(project_id: str) -> None:
    manifest = json.loads(
        Path("work/gcp_bigquery/claims_sandbox_manifest.json").read_text(encoding="utf-8")
    )
    tick = chr(96)
    table = f"{tick}{project_id}.pet_insurance_sandbox.claims_backfill{tick}"
    sql = (
        "SELECT "
        "COUNT(*) AS row_count, "
        "FORMAT('%.2f', SUM(claim_amount)) AS claim_amount_sum, "
        "MIN(claim_id) AS min_claim_id, "
        "MAX(claim_id) AS max_claim_id "
        f"FROM {table}"
    )
    proc = subprocess.run(
        [
            "bq",
            f"--project_id={project_id}",
            "--format=json",
            "query",
            "--use_legacy_sql=false",
            sql,
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    rows = json.loads(proc.stdout)
    if len(rows) != 1:
        raise RuntimeError(f"Expected one reconciliation row, got {rows!r}")

    actual = rows[0]
    expected = {
        "row_count": str(manifest["row_count"]),
        "claim_amount_sum": manifest["claim_amount_sum"],
        "min_claim_id": manifest["min_claim_id"],
        "max_claim_id": manifest["max_claim_id"],
    }
    if actual != expected:
        raise RuntimeError(
            f"BigQuery reconciliation failed: expected={expected}, actual={actual}"
        )

    print(
        json.dumps(
            {"status": "PASS", "expected": expected, "actual": actual},
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    project = os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get(
        "CLOUDSDK_CORE_PROJECT"
    )
    if not project:
        raise RuntimeError("GOOGLE_CLOUD_PROJECT/CLOUDSDK_CORE_PROJECT is not set")
    run(project)
