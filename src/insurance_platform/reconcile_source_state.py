from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from time import perf_counter
from uuid import uuid4

from insurance_platform.ingestion import (
    Reconciliation,
    deduplicate_changes,
    log_reconciliation,
    newest_watermark,
    retry_call,
    row_to_change,
)
from insurance_platform.run_ingestion import (
    TABLES,
    _apply_staged_batch,
    _cleanup_stage,
    _finalize_batch_failure,
    _read_watermark,
    _required,
    _stage_records,
    _write_batch_started,
)

LOGGER = logging.getLogger(__name__)


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
            for spec in TABLES:
                batch_id = (
                    f"{os.getenv('GITHUB_RUN_ID', 'local')}-"
                    f"reconcile-{spec.name}-{uuid4().hex[:8]}"
                )
                started_at = datetime.now(timezone.utc)
                started_perf = perf_counter()
                watermark_before = _read_watermark(sf_cursor, spec.name)

                pg_cursor.execute(
                    f"SELECT * FROM {spec.name} "
                    f"ORDER BY {spec.updated_at}, {spec.primary_key}"
                )
                source_rows = pg_cursor.fetchall()
                current_versions = deduplicate_changes(
                    row_to_change(spec, row) for row in source_rows
                )
                watermark_after = newest_watermark(current_versions, watermark_before)

                _write_batch_started(
                    sf_cursor,
                    batch_id=batch_id,
                    source_table=spec.name,
                    started_at=started_at,
                    source_rows=len(source_rows),
                    rows_extracted=len(current_versions),
                    watermark_before=watermark_before,
                    notes=(
                        "full-state reconciliation compares source current-version "
                        "identity (table, pk, updated_at, payload_hash) with RAW"
                    ),
                )
                attempts_used = 0
                try:
                    _stage_records(sf_cursor, current_versions, batch_id)

                    def operation(attempt: int) -> Reconciliation:
                        nonlocal attempts_used
                        attempts_used = attempt
                        return _apply_staged_batch(
                            sf_cursor,
                            spec=spec,
                            batch_id=batch_id,
                            watermark_after=watermark_after,
                            candidate_count=len(current_versions),
                            source_rows=len(source_rows),
                            started_perf=started_perf,
                            attempt=attempt,
                        )

                    reconciliation = retry_call(operation)
                    _cleanup_stage(sf_cursor, batch_id)
                    log_reconciliation(spec.name, batch_id, reconciliation)
                    LOGGER.info(
                        "full_state_reconciliation table=%s source_versions=%d newly_inserted=%d",
                        spec.name,
                        len(current_versions),
                        reconciliation.inserted_rows,
                    )
                except BaseException as exc:
                    _finalize_batch_failure(
                        sf_cursor,
                        batch_id=batch_id,
                        duration_ms=int((perf_counter() - started_perf) * 1000),
                        retry_count=max(attempts_used - 1, 0),
                        exc=exc,
                    )
                    raise

        LOGGER.info("full_state_reconciliation_complete tables=%d", len(TABLES))
    finally:
        pg.close()
        sf.close()


if __name__ == "__main__":
    run()
