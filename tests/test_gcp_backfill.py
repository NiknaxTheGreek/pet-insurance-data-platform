from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone
from decimal import Decimal

from insurance_platform.gcp_backfill_export import write_export


def test_gcp_backfill_export_is_deterministic_and_reconciliable(tmp_path):
    rows = [
        {
            "claim_id": "CLM-00002",
            "policy_id": "POL-00001",
            "pet_id": "PET-00001",
            "claim_type": "ILLNESS",
            "claim_date": date(2026, 9, 2),
            "claim_amount": Decimal("200.00"),
            "approved_amount": Decimal("150.00"),
            "claim_status": "APPROVED",
            "updated_at": datetime(2026, 9, 3, 8, 0, tzinfo=timezone.utc),
            "is_deleted": False,
        },
        {
            "claim_id": "CLM-00001",
            "policy_id": "POL-00001",
            "pet_id": "PET-00001",
            "claim_type": "ACCIDENT",
            "claim_date": date(2026, 9, 1),
            "claim_amount": Decimal("100.00"),
            "approved_amount": None,
            "claim_status": "SUBMITTED",
            "updated_at": datetime(2026, 9, 1, 8, 0, tzinfo=timezone.utc),
            "is_deleted": False,
        },
    ]

    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"
    manifest_path = write_export(rows, first_dir)
    write_export(rows, second_dir)

    first_csv = (first_dir / "claims_backfill.csv").read_bytes()
    second_csv = (second_dir / "claims_backfill.csv").read_bytes()
    assert first_csv == second_csv

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["row_count"] == 2
    assert manifest["claim_amount_sum"] == "300.00"
    assert manifest["min_claim_id"] == "CLM-00001"
    assert manifest["max_claim_id"] == "CLM-00002"
    assert manifest["sha256"] == hashlib.sha256(first_csv).hexdigest()
