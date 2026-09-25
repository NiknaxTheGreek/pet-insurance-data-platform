from __future__ import annotations

import csv
import hashlib
import json
from decimal import Decimal
from pathlib import Path

ROWS = [
    {"claim_id": "GCP-CLM-001", "policy_id": "POL-GCP-001", "pet_id": "PET-GCP-001", "claim_type": "ACCIDENT", "claim_date": "2026-09-01", "claim_amount": "8500.00", "approved_amount": "", "claim_status": "SUBMITTED", "is_deleted": "false"},
    {"claim_id": "GCP-CLM-002", "policy_id": "POL-GCP-002", "pet_id": "PET-GCP-002", "claim_type": "ILLNESS", "claim_date": "2026-09-02", "claim_amount": "11200.00", "approved_amount": "9700.00", "claim_status": "APPROVED", "is_deleted": "false"},
    {"claim_id": "GCP-CLM-003", "policy_id": "POL-GCP-003", "pet_id": "PET-GCP-003", "claim_type": "ROUTINE_CARE", "claim_date": "2026-09-03", "claim_amount": "2300.00", "approved_amount": "1800.00", "claim_status": "PAID", "is_deleted": "false"},
]

FIELDS = list(ROWS[0])

def run(output_dir: Path = Path("work/gcp_bigquery")) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "claims_sandbox.csv"
    manifest_path = output_dir / "claims_sandbox_manifest.json"

    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(ROWS)

    manifest = {
        "row_count": len(ROWS),
        "claim_amount_sum": format(sum(Decimal(row["claim_amount"]) for row in ROWS), "f"),
        "min_claim_id": min(row["claim_id"] for row in ROWS),
        "max_claim_id": max(row["claim_id"] for row in ROWS),
        "sha256": hashlib.sha256(csv_path.read_bytes()).hexdigest(),
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(manifest, sort_keys=True))
    return manifest_path

if __name__ == "__main__":
    run()
