from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from uuid import uuid4

from insurance_platform.ingestion import (
    Reconciliation,
    TableSpec,
    Watermark,
    build_incremental_query,
    canonical_json,
    deduplicate_changes,
    log_reconciliation,
    newest_watermark,
    row_to_change,
)

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


def _extract(pg_cursor, spec: TableSpec, watermark: Watermark):
    sql, params = build_incremental_query(spec, ["*"], watermark)
    pg_cursor.execute(sql, params)
    return [row_to_change(spec, row) for row in pg_cursor.fetchall()]


def _merge_raw(sf_cursor, record, batch_id: str) -> int:
    sf_cursor.execute(
        f"""
        MERGE INTO {RAW_TABLE} AS target
        USING (
            SELECT
                %s AS SOURCE_TABLE,
                %s AS SOURCE_PK,
                %s AS SOURCE_UPDATED_AT,
                %s AS OPERATION,
                PARSE_JSON(%s) AS PAYLOAD,
                %s AS PAYLOAD_HASH,
                %s AS BATCH_ID
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
        (
            record.source_table,
            record.source_pk,
            record.source_updated_at,
            record.operation,
            canonical_json(record.payload),
            record.payload_hash,
            batch_id,
        ),
    )
    return max(int(sf_cursor.rowcount or 0), 0)


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


def _write_batch(
    sf_cursor,
    *,
    batch_id: str,
    started_at: datetime,
    status: str,
    rows_extracted: int,
    rows_inserted: int,
    notes: str,
) -> None:
    sf_cursor.execute(
        f"""
        MERGE INTO {BATCH_TABLE} AS target
        USING (
            SELECT
                %s AS BATCH_ID,
                %s AS STARTED_AT,
                CURRENT_TIMESTAMP() AS COMPLETED_AT,
                %s AS STATUS,
                %s AS ROWS_EXTRACTED,
                %s AS ROWS_INSERTED,
                %s AS NOTES
        ) AS source
        ON target.BATCH_ID = source.BATCH_ID
        WHEN NOT MATCHED THEN INSERT (
            BATCH_ID, STARTED_AT, COMPLETED_AT, STATUS,
            ROWS_EXTRACTED, ROWS_INSERTED, NOTES
        ) VALUES (
            source.BATCH_ID, source.STARTED_AT, source.COMPLETED_AT,
            source.STATUS, source.ROWS_EXTRACTED, source.ROWS_INSERTED, source.NOTES
        )
        """,
        (batch_id, started_at, status, rows_extracted, rows_inserted, notes),
    )


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
        role=os.getenv("SNOWFLAKE_ROLE", "SNOWFLAKE_LEARNING_ROLE"),
        warehouse=os.getenv("SNOWFLAKE_WAREHOUSE", "SNOWFLAKE_LEARNING_WH"),
        database=os.getenv("SNOWFLAKE_DATABASE", "SNOWFLAKE_LEARNING_DB"),
        authenticator="WORKLOAD_IDENTITY",
        workload_identity_provider="OIDC",
        token=_required("SNOWFLAKE_TOKEN"),
    )

    try:
        with pg, sf:
            with pg.cursor() as pg_cursor, sf.cursor() as sf_cursor:
                for spec in TABLES:
                    batch_id = f"{os.getenv('GITHUB_RUN_ID', 'local')}-{spec.name}-{uuid4().hex[:8]}"
                    started_at = datetime.now(timezone.utc)
                    watermark = _read_watermark(sf_cursor, spec.name)
                    source_rows = _source_count(pg_cursor, spec)
                    candidates = deduplicate_changes(_extract(pg_cursor, spec, watermark))

                    inserted = 0
                    for record in candidates:
                        inserted += _merge_raw(sf_cursor, record, batch_id)

                    if candidates:
                        _write_watermark(
                            sf_cursor,
                            spec.name,
                            newest_watermark(candidates, watermark),
                        )

                    reconciliation = Reconciliation(
                        source_rows=source_rows,
                        candidate_rows=len(candidates),
                        inserted_rows=inserted,
                    )
                    if not reconciliation.is_consistent:
                        raise RuntimeError(
                            f"Reconciliation failed for {spec.name}: {reconciliation}"
                        )

                    _write_batch(
                        sf_cursor,
                        batch_id=batch_id,
                        started_at=started_at,
                        status="SUCCESS",
                        rows_extracted=len(candidates),
                        rows_inserted=inserted,
                        notes="watermark incremental PostgreSQL to Snowflake ingestion",
                    )
                    log_reconciliation(spec.name, batch_id, reconciliation)

        logging.getLogger(__name__).info("ingestion_run_complete tables=%d", len(TABLES))
    finally:
        pg.close()
        sf.close()


if __name__ == "__main__":
    run()
