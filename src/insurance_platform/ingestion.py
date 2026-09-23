from __future__ import annotations

import hashlib
import json
import logging
from decimal import Decimal
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable, Mapping, Protocol, Sequence

LOGGER = logging.getLogger(__name__)


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

    @property
    def is_consistent(self) -> bool:
        return 0 <= self.inserted_rows <= self.candidate_rows <= self.source_rows


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


def build_incremental_query(spec: TableSpec, columns: Sequence[str], watermark: Watermark) -> tuple[str, tuple[Any, ...]]:
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


def deduplicate_changes(records: Iterable[ChangeRecord]) -> list[ChangeRecord]:
    seen: set[tuple[str, str, datetime, str]] = set()
    result: list[ChangeRecord] = []
    for record in records:
        key = (
            record.source_table,
            record.source_pk,
            record.source_updated_at,
            record.payload_hash,
        )
        if key not in seen:
            seen.add(key)
            result.append(record)
    return result


def newest_watermark(records: Sequence[ChangeRecord], fallback: Watermark) -> Watermark:
    if not records:
        return fallback
    latest = max(records, key=lambda r: (r.source_updated_at, r.source_pk))
    return Watermark(latest.source_updated_at, latest.source_pk)


def log_reconciliation(table: str, batch_id: str, reconciliation: Reconciliation) -> None:
    LOGGER.info(
        "ingestion_reconciliation table=%s batch_id=%s source_rows=%d candidates=%d inserted=%d consistent=%s",
        table,
        batch_id,
        reconciliation.source_rows,
        reconciliation.candidate_rows,
        reconciliation.inserted_rows,
        reconciliation.is_consistent,
    )
