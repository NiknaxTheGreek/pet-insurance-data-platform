from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from uuid import uuid4

from insurance_platform.contracts import validate_source_contracts
from insurance_platform.ingestion import (
    ChangeRecord,
    Reconciliation,
    TableSpec,
    Watermark,
    build_incremental_query,
    canonical_json,
    chunked,
    deduplicate_changes,
    log_reconciliation,
    newest_watermark,
    retry_call,
    row_to_change,
)

LOGGER = logging.getLogger(__name__)

TABLES = (
    TableSpec("customers", "customer_id"),
    TableSpec("pets", "pet_id"),
    TableSpec("policies", "policy_id"),
    TableSpec("claims", "claim_id"),
    TableSpec("claim_payments", "payment_id"),
)

RAW_TABLE = "PET_INSURANCE_RAW.SOURCE_RECORDS"
WATERMARK_TABLE = "PET_INSURANCE_CONTROL.INGESTION_WATERMARKS"
BATCH_TABLE = "PET_INSURANCE_CONTROL.INGESTION_BATCHES"
STAGE_TABLE = "PET_INSURANCE_CONTROL.INGESTION_STAGE"


def _required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Required environment variable {name} is not set")
    return value


def _read_watermark(sf_cursor, table: str) -> Watermark:
    sf_cursor.execute(
        f"""
        SELECT LAST_UPDATED_AT, LAST_SOURCE_PK
        FROM {WATERMARK_TABLE}
        WHERE SOURCE_TABLE = %s
        """,
        (table,),
    )
    row = sf_cursor.fetchone()
    return Watermark() if row is None else Watermark(row[0], row[1])


def _source_count(pg_cursor, spec: TableSpec) -> int:
    pg_cursor.execute(f"SELECT COUNT(*) AS n FROM {spec.name}")
    return int(pg_cursor.fetchone()["n"])


def _extract(pg_cursor, spec: TableSpec, watermark: Watermark) -> list[ChangeRecord]:
    sql, params = build_incremental_query(spec, ["*"], watermark)
    pg_cursor.execute(sql, params)
    return [row_to_change(spec, row) for row in pg_cursor.fetchall()]


def _write_batch_started(
    sf_cursor,
    *,
    batch_id: str,
    source_table: str,
    started_at: datetime,
    source_rows: int,
    rows_extracted: int,
    watermark_before: Watermark,
    notes: str,
) -> None:
    sf_cursor.execute(
        f"""
        MERGE INTO {BATCH_TABLE} AS target
        USING (
            SELECT
                %s AS BATCH_ID,
                %s AS SOURCE_TABLE,
                %s AS STARTED_AT,
                'STARTED' AS STATUS,
                %s AS SOURCE_ROWS,
                %s AS ROWS_EXTRACTED,
                %s AS WATERMARK_BEFORE_AT,
                %s AS WATERMARK_BEFORE_PK,
                %s AS GITHUB_RUN_ID,
                %s AS NOTES
        ) AS source
        ON target.BATCH_ID = source.BATCH_ID
        WHEN NOT MATCHED THEN INSERT (
            BATCH_ID, SOURCE_TABLE, STARTED_AT, STATUS,
            SOURCE_ROWS, ROWS_EXTRACTED,
            WATERMARK_BEFORE_AT, WATERMARK_BEFORE_PK,
            GITHUB_RUN_ID, NOTES
        ) VALUES (
            source.BATCH_ID, source.SOURCE_TABLE, source.STARTED_AT, source.STATUS,
            source.SOURCE_ROWS, source.ROWS_EXTRACTED,
            source.WATERMARK_BEFORE_AT, source.WATERMARK_BEFORE_PK,
            source.GITHUB_RUN_ID, source.NOTES
        )
        """,
        (
            batch_id,
            source_table,
            started_at,
            source_rows,
            rows_extracted,
            watermark_before.updated_at,
            watermark_before.source_pk,
            os.getenv("GITHUB_RUN_ID"),
            notes,
        ),
    )


def _stage_records(
    sf_cursor,
    records: list[ChangeRecord],
    batch_id: str,
    *,
    batch_size: int = 1000,
) -> None:
    if not records:
        return

    sql = f"""
        INSERT INTO {STAGE_TABLE} (
            BATCH_ID, SOURCE_TABLE, SOURCE_PK, SOURCE_UPDATED_AT,
            OPERATION, PAYLOAD_JSON, PAYLOAD_HASH
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """
    rows = [
        (
            batch_id,
            record.source_table,
            record.source_pk,
            record.source_updated_at,
            record.operation,
            canonical_json(record.payload),
            record.payload_hash,
        )
        for record in records
    ]
    for batch in chunked(rows, batch_size):
        sf_cursor.executemany(sql, batch)

def _count_unrepresented_staged(sf_cursor, batch_id: str) -> int:
    sf_cursor.execute(
        f"""
        SELECT COUNT(*)
        FROM {STAGE_TABLE} stage
        WHERE stage.BATCH_ID = %s
          AND NOT EXISTS (
              SELECT 1
              FROM {RAW_TABLE} raw
              WHERE raw.SOURCE_TABLE = stage.SOURCE_TABLE
                AND raw.SOURCE_PK = stage.SOURCE_PK
                AND raw.SOURCE_UPDATED_AT = stage.SOURCE_UPDATED_AT
                AND raw.PAYLOAD_HASH = stage.PAYLOAD_HASH
          )
        """,
        (batch_id,),
    )
    return int(sf_cursor.fetchone()[0])


def _merge_staged_raw(sf_cursor, batch_id: str) -> None:
    sf_cursor.execute(
        f"""
        MERGE INTO {RAW_TABLE} AS target
        USING (
            SELECT
                SOURCE_TABLE,
                SOURCE_PK,
                SOURCE_UPDATED_AT,
                OPERATION,
                PARSE_JSON(PAYLOAD_JSON) AS PAYLOAD,
                PAYLOAD_HASH,
                BATCH_ID
            FROM {STAGE_TABLE}
            WHERE BATCH_ID = %s
        ) AS source
        ON  target.SOURCE_TABLE = source.SOURCE_TABLE
        AND target.SOURCE_PK = source.SOURCE_PK
        AND target.SOURCE_UPDATED_AT = source.SOURCE_UPDATED_AT
        AND target.PAYLOAD_HASH = source.PAYLOAD_HASH
        WHEN NOT MATCHED THEN INSERT (
            SOURCE_TABLE, SOURCE_PK, SOURCE_UPDATED_AT, OPERATION,
            PAYLOAD, PAYLOAD_HASH, BATCH_ID
        ) VALUES (
            source.SOURCE_TABLE, source.SOURCE_PK, source.SOURCE_UPDATED_AT,
            source.OPERATION, source.PAYLOAD, source.PAYLOAD_HASH, source.BATCH_ID
        )
        """,
        (batch_id,),
    )


def _count_represented_staged(sf_cursor, batch_id: str) -> int:
    sf_cursor.execute(
        f"""
        SELECT COUNT(*)
        FROM {STAGE_TABLE} stage
        WHERE stage.BATCH_ID = %s
          AND EXISTS (
              SELECT 1
              FROM {RAW_TABLE} raw
              WHERE raw.SOURCE_TABLE = stage.SOURCE_TABLE
                AND raw.SOURCE_PK = stage.SOURCE_PK
                AND raw.SOURCE_UPDATED_AT = stage.SOURCE_UPDATED_AT
                AND raw.PAYLOAD_HASH = stage.PAYLOAD_HASH
          )
        """,
        (batch_id,),
    )
    return int(sf_cursor.fetchone()[0])


def _write_watermark(sf_cursor, table: str, watermark: Watermark) -> None:
    sf_cursor.execute(
        f"""
        MERGE INTO {WATERMARK_TABLE} AS target
        USING (
            SELECT %s AS SOURCE_TABLE, %s AS LAST_UPDATED_AT, %s AS LAST_SOURCE_PK
        ) AS source
        ON target.SOURCE_TABLE = source.SOURCE_TABLE
        WHEN MATCHED THEN UPDATE SET
            LAST_UPDATED_AT = source.LAST_UPDATED_AT,
            LAST_SOURCE_PK = source.LAST_SOURCE_PK,
            UPDATED_AT = CURRENT_TIMESTAMP()
        WHEN NOT MATCHED THEN INSERT (
            SOURCE_TABLE, LAST_UPDATED_AT, LAST_SOURCE_PK
        ) VALUES (
            source.SOURCE_TABLE, source.LAST_UPDATED_AT, source.LAST_SOURCE_PK
        )
        """,
        (table, watermark.updated_at, watermark.source_pk),
    )


def _finalize_batch_success(
    sf_cursor,
    *,
    batch_id: str,
    rows_inserted: int,
    watermark_after: Watermark,
    duration_ms: int,
    retry_count: int,
    reconciliation_status: str,
) -> None:
    sf_cursor.execute(
        f"""
        UPDATE {BATCH_TABLE}
        SET COMPLETED_AT = CURRENT_TIMESTAMP(),
            STATUS = 'SUCCESS',
            ROWS_INSERTED = %s,
            WATERMARK_AFTER_AT = %s,
            WATERMARK_AFTER_PK = %s,
            DURATION_MS = %s,
            RETRY_COUNT = %s,
            RECONCILIATION_STATUS = %s,
            ERROR_CLASS = NULL,
            ERROR_MESSAGE = NULL
        WHERE BATCH_ID = %s
        """,
        (
            rows_inserted,
            watermark_after.updated_at,
            watermark_after.source_pk,
            duration_ms,
            retry_count,
            reconciliation_status,
            batch_id,
        ),
    )


def _finalize_batch_failure(
    sf_cursor,
    *,
    batch_id: str,
    duration_ms: int,
    retry_count: int,
    exc: BaseException,
) -> None:
    sf_cursor.execute(
        f"""
        UPDATE {BATCH_TABLE}
        SET COMPLETED_AT = CURRENT_TIMESTAMP(),
            STATUS = 'FAILED',
            DURATION_MS = %s,
            RETRY_COUNT = %s,
            RECONCILIATION_STATUS = 'FAILED',
            ERROR_CLASS = %s,
            ERROR_MESSAGE = %s
        WHERE BATCH_ID = %s
        """,
        (
            duration_ms,
            retry_count,
            type(exc).__name__,
            str(exc)[:2000],
            batch_id,
        ),
    )


def _cleanup_stage(sf_cursor, batch_id: str) -> None:
    sf_cursor.execute(f"DELETE FROM {STAGE_TABLE} WHERE BATCH_ID = %s", (batch_id,))


def _apply_staged_batch(
    sf_cursor,
    *,
    spec: TableSpec,
    batch_id: str,
    watermark_after: Watermark,
    candidate_count: int,
    source_rows: int,
    started_perf: float,
    attempt: int,
) -> Reconciliation:
    sf_cursor.execute("BEGIN")
    try:
        inserted = _count_unrepresented_staged(sf_cursor, batch_id)
        _merge_staged_raw(sf_cursor, batch_id)

        if os.getenv("INGESTION_FAIL_AFTER_MERGE_TABLE") == spec.name:
            raise RuntimeError(
                f"Injected failure after RAW merge before watermark for {spec.name}"
            )

        represented = _count_represented_staged(sf_cursor, batch_id)

        reconciliation = Reconciliation(
            source_rows=source_rows,
            candidate_rows=candidate_count,
            inserted_rows=inserted,
            represented_rows=represented,
        )
        if not reconciliation.is_consistent:
            raise RuntimeError(f"Reconciliation failed for {spec.name}: {reconciliation}")

        if candidate_count:
            _write_watermark(sf_cursor, spec.name, watermark_after)

        _finalize_batch_success(
            sf_cursor,
            batch_id=batch_id,
            rows_inserted=inserted,
            watermark_after=watermark_after,
            duration_ms=int((perf_counter() - started_perf) * 1000),
            retry_count=attempt - 1,
            reconciliation_status="CONSISTENT",
        )
        sf_cursor.execute("COMMIT")
        return reconciliation
    except BaseException:
        sf_cursor.execute("ROLLBACK")
        raise


def _process_table(pg_cursor, sf_cursor, spec: TableSpec) -> Reconciliation:
    batch_id = f"{os.getenv('GITHUB_RUN_ID', 'local')}-{spec.name}-{uuid4().hex[:8]}"
    started_at = datetime.now(timezone.utc)
    started_perf = perf_counter()
    watermark_before = _read_watermark(sf_cursor, spec.name)
    source_rows = _source_count(pg_cursor, spec)
    candidates = deduplicate_changes(_extract(pg_cursor, spec, watermark_before))
    watermark_after = newest_watermark(candidates, watermark_before)

    _write_batch_started(
        sf_cursor,
        batch_id=batch_id,
        source_table=spec.name,
        started_at=started_at,
        source_rows=source_rows,
        rows_extracted=len(candidates),
        watermark_before=watermark_before,
        notes="watermark incremental PostgreSQL to Snowflake ingestion",
    )
    attempts_used = 0
    try:
        _stage_records(sf_cursor, candidates, batch_id)

        def operation(attempt: int) -> Reconciliation:
            nonlocal attempts_used
            attempts_used = attempt
            return _apply_staged_batch(
                sf_cursor,
                spec=spec,
                batch_id=batch_id,
                watermark_after=watermark_after,
                candidate_count=len(candidates),
                source_rows=source_rows,
                started_perf=started_perf,
                attempt=attempt,
            )

        reconciliation = retry_call(operation)
        _cleanup_stage(sf_cursor, batch_id)
        log_reconciliation(spec.name, batch_id, reconciliation)
        return reconciliation
    except BaseException as exc:
        _finalize_batch_failure(
            sf_cursor,
            batch_id=batch_id,
            duration_ms=int((perf_counter() - started_perf) * 1000),
            retry_count=max(attempts_used - 1, 0),
            exc=exc,
        )
        try:
            _cleanup_stage(sf_cursor, batch_id)
        except BaseException:
            LOGGER.exception(
                "ingestion_stage_cleanup_failed table=%s batch_id=%s",
                spec.name,
                batch_id,
            )
        LOGGER.exception(
            "ingestion_batch_failed table=%s batch_id=%s",
            spec.name,
            batch_id,
        )
        raise


def run() -> None:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    import psycopg
    import snowflake.connector
    from psycopg.rows import dict_row

    pg = psycopg.connect(_required("POSTGRES_DSN"), row_factory=dict_row)
    sf = snowflake.connector.connect(
        account=_required("SNOWFLAKE_ACCOUNT"),
        user=_required("SNOWFLAKE_USER"),
        role=_required("SNOWFLAKE_ROLE"),
        warehouse=_required("SNOWFLAKE_WAREHOUSE"),
        database=_required("SNOWFLAKE_DATABASE"),
        authenticator="WORKLOAD_IDENTITY",
        workload_identity_provider="OIDC",
        token=_required("SNOWFLAKE_TOKEN"),
    )
    sf.autocommit(True)

    try:
        with pg.cursor() as pg_cursor, sf.cursor() as sf_cursor:
            contract_dir = Path(os.getenv("SOURCE_CONTRACT_DIR", "contracts"))
            validate_source_contracts(pg_cursor, contract_dir)
            for spec in TABLES:
                _process_table(pg_cursor, sf_cursor, spec)
        LOGGER.info("ingestion_run_complete tables=%d", len(TABLES))
    finally:
        pg.close()
        sf.close()


if __name__ == "__main__":
    run()
