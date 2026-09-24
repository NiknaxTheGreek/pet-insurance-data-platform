from __future__ import annotations

import csv
import hashlib
import json
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path


def generate_rows(count: int = 5000) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    start = date(2026, 1, 1)
    statuses = ("SUBMITTED", "ASSESSED", "APPROVED", "PAID", "REJECTED")
    types = ("ACCIDENT", "ILLNESS", "ROUTINE_CARE")

    for i in range(1, count + 1):
        amount = Decimal(500 + (i % 4500)).quantize(Decimal("0.01"))
        status = statuses[i % len(statuses)]
        approved = (
            (amount * Decimal("0.85")).quantize(Decimal("0.01"))
            if status in {"APPROVED", "PAID"}
            else None
        )
        rows.append(
            {
                "claim_id": f"BQ-CLM-{i:06d}",
                "policy_id": f"BQ-POL-{((i - 1) % 1800) + 1:06d}",
                "pet_id": f"BQ-PET-{((i - 1) % 1800) + 1:06d}",
                "claim_type": types[i % len(types)],
                "claim_date": (start + timedelta(days=i % 240)).isoformat(),
                "claim_amount": format(amount, "f"),
                "approved_amount": "" if approved is None else format(approved, "f"),
                "claim_status": status,
                "is_deleted": False,
            }
        )
    return rows


def write_dataset(output_dir: Path, count: int = 5000) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "claims_bigquery_sandbox.csv"
    manifest_path = output_dir / "claims_bigquery_sandbox_manifest.json"
    rows = generate_rows(count)

    fieldnames = [
        "claim_id",
        "policy_id",
        "pet_id",
        "claim_type",
        "claim_date",
        "claim_amount",
        "approved_amount",
        "claim_status",
        "is_deleted",
    ]

    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    digest = hashlib.sha256(csv_path.read_bytes()).hexdigest()
    claim_amount_sum = sum(Decimal(str(row["claim_amount"])) for row in rows)

    manifest = {
        "row_count": len(rows),
        "claim_amount_sum": format(claim_amount_sum, "f"),
        "min_claim_id": rows[0]["claim_id"] if rows else None,
        "max_claim_id": rows[-1]["claim_id"] if rows else None,
        "sha256": digest,
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    print(json.dumps(manifest, sort_keys=True))
    return manifest_path


if __name__ == "__main__":
    write_dataset(Path("work/gcp_bigquery_sandbox"))
