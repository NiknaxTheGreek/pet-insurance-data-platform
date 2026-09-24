from datetime import datetime, timezone
from decimal import Decimal

import pytest

from insurance_platform.ingestion import (
    ChangeRecord,
    Reconciliation,
    TableSpec,
    Watermark,
    build_incremental_query,
    deduplicate_changes,
    max_watermark,
    newest_watermark,
    payload_sha256,
    retry_call,
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


def test_payload_hash_supports_postgres_decimal_values():
    payload = {"claim_amount": Decimal("11200.00"), "approved_amount": Decimal("9700.00")}
    digest = payload_sha256(payload)
    assert len(digest) == 64


def test_newest_watermark_never_moves_backwards_for_late_state():
    current = Watermark(
        datetime(2026, 9, 23, 19, 40, tzinfo=timezone.utc),
        "CLM-10042",
    )
    late = ChangeRecord(
        "claims",
        "CLM-10043",
        datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc),
        "UPSERT",
        {},
        "late",
    )
    assert newest_watermark([late], current) == current


def test_max_watermark_uses_pk_as_tie_breaker():
    ts = datetime(2026, 9, 23, 19, 40, tzinfo=timezone.utc)
    left = Watermark(ts, "CLM-10041")
    right = Watermark(ts, "CLM-10042")
    assert max_watermark(left, right) == right


def test_reconciliation_requires_every_candidate_to_be_represented():
    assert Reconciliation(10, 3, 1, represented_rows=3).is_consistent
    assert not Reconciliation(10, 3, 1, represented_rows=2).is_consistent


def test_retry_call_retries_transient_failure_then_succeeds():
    attempts = []
    sleeps = []

    class TransientError(RuntimeError):
        sqlstate = "40001"

    def operation(attempt):
        attempts.append(attempt)
        if attempt < 3:
            raise TransientError("serialization failure")
        return "ok"

    result = retry_call(
        operation,
        max_attempts=3,
        base_delay_seconds=0.5,
        sleep=sleeps.append,
    )

    assert result == "ok"
    assert attempts == [1, 2, 3]
    assert sleeps == [0.5, 1.0]


def test_retry_call_does_not_retry_non_transient_failure():
    attempts = []

    def operation(attempt):
        attempts.append(attempt)
        raise ValueError("bad input")

    with pytest.raises(ValueError, match="bad input"):
        retry_call(operation, sleep=lambda _: None)

    assert attempts == [1]
