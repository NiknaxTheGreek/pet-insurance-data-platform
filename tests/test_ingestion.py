from datetime import datetime, timezone

import pytest

from insurance_platform.ingestion import (
    ChangeRecord,
    Reconciliation,
    TableSpec,
    Watermark,
    build_incremental_query,
    deduplicate_changes,
    newest_watermark,
    payload_sha256,
    row_to_change,
)


def test_incremental_query_uses_composite_watermark():
    spec = TableSpec("claims", "claim_id")
    wm = Watermark(datetime(2026, 9, 20, 9, 0, tzinfo=timezone.utc), "CLM-10042")
    sql, params = build_incremental_query(spec, ["claim_id", "updated_at"], wm)
    assert "WHERE (updated_at, claim_id) > (%s, %s)" in sql
    assert params == (wm.updated_at, "CLM-10042")


def test_payload_hash_is_order_independent():
    a = {"claim_id": "CLM-10042", "claim_amount": 8500}
    b = {"claim_amount": 8500, "claim_id": "CLM-10042"}
    assert payload_sha256(a) == payload_sha256(b)


def test_row_to_change_marks_soft_delete():
    spec = TableSpec("claims", "claim_id")
    row = {
        "claim_id": "CLM-10042",
        "updated_at": datetime(2026, 9, 22, 13, 56, tzinfo=timezone.utc),
        "is_deleted": True,
    }
    change = row_to_change(spec, row)
    assert change.operation == "DELETE"
    assert change.source_pk == "CLM-10042"


def test_deduplicate_changes_is_idempotent():
    ts = datetime(2026, 9, 22, 13, 56, tzinfo=timezone.utc)
    record = ChangeRecord("claims", "CLM-10042", ts, "UPSERT", {"x": 1}, "abc")
    assert deduplicate_changes([record, record]) == [record]


def test_newest_watermark_uses_updated_at_then_pk():
    a = ChangeRecord("claims", "CLM-10041", datetime(2026, 9, 22, 13, 56, tzinfo=timezone.utc), "UPSERT", {}, "a")
    b = ChangeRecord("claims", "CLM-10042", datetime(2026, 9, 22, 13, 56, tzinfo=timezone.utc), "UPSERT", {}, "b")
    wm = newest_watermark([a, b], Watermark())
    assert wm.source_pk == "CLM-10042"


def test_reconciliation_invariants():
    assert Reconciliation(10, 2, 2).is_consistent
    assert not Reconciliation(2, 1, 2).is_consistent
