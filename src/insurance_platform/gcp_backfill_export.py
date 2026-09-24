from __future__ import annotations

import csv
import hashlib
import json
import os
from decimal import Decimal
from pathlib import Path
from typing import Mapping, Sequence


FIELDNAMES = [
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


def required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Required environment variable {name} is not set")
    return value


def write_export(
    rows: Sequence[Mapping[str, object]],
    output_dir: Path,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "claims_backfill.csv"
    manifest_path = output_dir / "claims_backfill_manifest.json"

    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {key: "" if row[key] is None else row[key] for key in FIELDNAMES}
            )

    digest = hashlib.sha256(csv_path.read_bytes()).hexdigest()
    claim_amount_sum = sum(
        (row["claim_amount"] or Decimal("0"))
        for row in rows
    )

    manifest = {
        "file": csv_path.name,
        "sha256": digest,
        "row_count": len(rows),
        "claim_amount_sum": format(claim_amount_sum, "f"),
        "min_claim_id": min((str(row["claim_id"]) for row in rows), default=None),
        "max_claim_id": max((str(row["claim_id"]) for row in rows), default=None),
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return manifest_path


def run(output_dir: Path = Path("work/gcp_backfill")) -> Path:
    import psycopg
    from psycopg.rows import dict_row

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

    manifest_path = write_export(rows, output_dir)
    print(manifest_path.read_text(encoding="utf-8"))
    return manifest_path


if __name__ == "__main__":
    run()
