from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Callable, Iterable, Iterator, Mapping, Protocol, Sequence, TypeVar

LOGGER = logging.getLogger(__name__)
T = TypeVar("T")


@dataclass(frozen=True)
class Watermark:
    updated_at: datetime | None = None
    source_pk: str | None = None


@dataclass(frozen=True)
class TableSpec:
    name: str
    primary_key: str
    updated_at: str = "updated_at"


@dataclass(frozen=True)
class ChangeRecord:
    source_table: str
    source_pk: str
    source_updated_at: datetime
    operation: str
    payload: Mapping[str, Any]
    payload_hash: str


@dataclass(frozen=True)
class Reconciliation:
    source_rows: int
    candidate_rows: int
    inserted_rows: int
    represented_rows: int | None = None

    @property
    def is_consistent(self) -> bool:
        if not (0 <= self.inserted_rows <= self.candidate_rows <= self.source_rows):
            return False
        if self.represented_rows is not None and self.represented_rows != self.candidate_rows:
            return False
        return True


class CursorLike(Protocol):
    def execute(self, query: str, params: Sequence[Any] | None = None) -> Any: ...
    def fetchall(self) -> list[Any]: ...


def canonical_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=_json_default)


def payload_sha256(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def _json_default(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        return format(value, "f")
    if hasattr(value, "isoformat"):
        return value.isoformat()
    raise TypeError(f"Unsupported JSON value: {type(value)!r}")


def build_incremental_query(
    spec: TableSpec,
    columns: Sequence[str],
    watermark: Watermark,
) -> tuple[str, tuple[Any, ...]]:
    selected = ", ".join(columns)
    if watermark.updated_at is None:
        return (
            f"SELECT {selected} FROM {spec.name} "
            f"ORDER BY {spec.updated_at}, {spec.primary_key}",
            (),
        )

    if watermark.source_pk is None:
        raise ValueError("source_pk watermark is required when updated_at is set")

    sql = (
        f"SELECT {selected} FROM {spec.name} "
        f"WHERE ({spec.updated_at}, {spec.primary_key}) > (%s, %s) "
        f"ORDER BY {spec.updated_at}, {spec.primary_key}"
    )
    return sql, (watermark.updated_at, watermark.source_pk)


def row_to_change(
    spec: TableSpec,
    row: Mapping[str, Any],
    *,
    deleted_column: str = "is_deleted",
) -> ChangeRecord:
    payload = dict(row)
    source_pk = str(payload[spec.primary_key])
    source_updated_at = payload[spec.updated_at]
    if not isinstance(source_updated_at, datetime):
        raise TypeError(f"{spec.updated_at} must be a datetime")

    operation = "DELETE" if bool(payload.get(deleted_column, False)) else "UPSERT"
    return ChangeRecord(
        source_table=spec.name,
        source_pk=source_pk,
        source_updated_at=source_updated_at,
        operation=operation,
        payload=payload,
        payload_hash=payload_sha256(payload),
    )


def version_identity(record: ChangeRecord) -> tuple[str, str, datetime, str]:
    return (
        record.source_table,
        record.source_pk,
        record.source_updated_at,
        record.payload_hash,
    )


def deduplicate_changes(records: Iterable[ChangeRecord]) -> list[ChangeRecord]:
    seen: set[tuple[str, str, datetime, str]] = set()
    result: list[ChangeRecord] = []
    for record in records:
        key = version_identity(record)
        if key not in seen:
            seen.add(key)
            result.append(record)
    return result


def newest_watermark(records: Sequence[ChangeRecord], fallback: Watermark) -> Watermark:
    if not records:
        return fallback
    latest = max(records, key=lambda r: (r.source_updated_at, r.source_pk))
    candidate = Watermark(latest.source_updated_at, latest.source_pk)
    return max_watermark(fallback, candidate)


def max_watermark(left: Watermark, right: Watermark) -> Watermark:
    if left.updated_at is None:
        return right
    if right.updated_at is None:
        return left
    left_key = (left.updated_at, left.source_pk or "")
    right_key = (right.updated_at, right.source_pk or "")
    return right if right_key > left_key else left


def chunked(records: Sequence[T], size: int) -> Iterator[Sequence[T]]:
    if size <= 0:
        raise ValueError("chunk size must be positive")
    for index in range(0, len(records), size):
        yield records[index : index + size]


def is_transient_db_error(exc: BaseException) -> bool:
    sqlstate = getattr(exc, "sqlstate", None) or getattr(exc, "pgcode", None)
    if isinstance(sqlstate, str):
        if sqlstate.startswith(("08", "40")):
            return True
        if sqlstate in {"55P03", "57P01", "57P02", "57P03"}:
            return True

    message = str(exc).lower()
    transient_fragments = (
        "connection reset",
        "connection aborted",
        "connection closed",
        "connection timed out",
        "network error",
        "temporarily unavailable",
        "service unavailable",
        "timed out",
    )
    return any(fragment in message for fragment in transient_fragments)


def retry_call(
    operation: Callable[[int], T],
    *,
    is_retryable: Callable[[BaseException], bool] = is_transient_db_error,
    max_attempts: int = 3,
    base_delay_seconds: float = 2.0,
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    if max_attempts < 1:
        raise ValueError("max_attempts must be at least 1")

    for attempt in range(1, max_attempts + 1):
        try:
            return operation(attempt)
        except BaseException as exc:
            if attempt >= max_attempts or not is_retryable(exc):
                raise
            delay = base_delay_seconds * (2 ** (attempt - 1))
            LOGGER.warning(
                "transient_database_error attempt=%d max_attempts=%d delay_seconds=%.1f error_class=%s",
                attempt,
                max_attempts,
                delay,
                type(exc).__name__,
            )
            sleep(delay)

    raise AssertionError("unreachable")


def log_reconciliation(table: str, batch_id: str, reconciliation: Reconciliation) -> None:
    LOGGER.info(
        "ingestion_reconciliation table=%s batch_id=%s source_rows=%d candidates=%d inserted=%d represented=%s consistent=%s",
        table,
        batch_id,
        reconciliation.source_rows,
        reconciliation.candidate_rows,
        reconciliation.inserted_rows,
        reconciliation.represented_rows,
        reconciliation.is_consistent,
    )
