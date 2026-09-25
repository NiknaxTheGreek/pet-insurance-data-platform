from __future__ import annotations

import hashlib
import json

from insurance_platform.gcp_bigquery_sandbox_export import run


def test_bigquery_sandbox_export_manifest(tmp_path):
    manifest_path = run(tmp_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    csv_bytes = (tmp_path / "claims_sandbox.csv").read_bytes()

    assert manifest["row_count"] == 3
    assert manifest["claim_amount_sum"] == "22000.00"
    assert manifest["min_claim_id"] == "GCP-CLM-001"
    assert manifest["max_claim_id"] == "GCP-CLM-003"
    assert manifest["sha256"] == hashlib.sha256(csv_bytes).hexdigest()
