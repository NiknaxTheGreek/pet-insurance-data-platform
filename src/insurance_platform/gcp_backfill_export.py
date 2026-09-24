from __future__ import annotations

import csv
import hashlib
import json
import os
from decimal import Decimal
from pathlib import Path


def required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Required environment variable {name} is not set")
    return value


def run(output_dir: Path = Path("work/gcp_backfill")) -> Path:
    import psycopg
    from psycopg.rows import dict_row

    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "claims_backfill.csv"
    manifest_path = output_dir / "claims_backfill_manifest.json"

    with psycopg.connect(required("POSTGRES_DSN"), row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    claim_id,
                    policy_id,
                    pet_id,
                    claim_type,
                    claim_date,
                    claim_amount,
                    approved_amount,
                    claim_status,
                    updated_at,
                    is_deleted
                FROM claims
                ORDER BY claim_id
                """
            )
            rows = cur.fetchall()

    fieldnames = [
        "claim_id",
        "policy_id",
        "pet_id",
        "claim_type",
        "claim_date",
        "claim_amount",
        "approved_amount",
        "claim_status",
        "updated_at",
        "is_deleted",
    ]

    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: "" if row[key] is None else row[key] for key in fieldnames})

    digest = hashlib.sha256(csv_path.read_bytes()).hexdigest()
    claim_amount_sum = sum((row["claim_amount"] or Decimal("0")) for row in rows)

    manifest = {
        "file": csv_path.name,
        "sha256": digest,
        "row_count": len(rows),
        "claim_amount_sum": format(claim_amount_sum, "f"),
        "min_claim_id": min((row["claim_id"] for row in rows), default=None),
        "max_claim_id": max((row["claim_id"] for row in rows), default=None),
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(manifest, sort_keys=True))
    return manifest_path


if __name__ == "__main__":
    run()
