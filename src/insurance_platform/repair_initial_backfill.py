from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from uuid import uuid4

from insurance_platform.ingestion import Reconciliation, row_to_change
from insurance_platform.run_ingestion import (
    TABLES,
    RAW_TABLE,
    _merge_raw,
    _required,
    _write_batch,
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
                    started_at = datetime.now(timezone.utc)
                    batch_id = f"{os.getenv('GITHUB_RUN_ID', 'local')}-backfill-{spec.name}-{uuid4().hex[:8]}"

                    pg_cursor.execute(
                        f"SELECT * FROM {spec.name} ORDER BY {spec.updated_at}, {spec.primary_key}"
                    )
                    source_rows = pg_cursor.fetchall()

                    missing = []
                    for row in source_rows:
                        source_pk = str(row[spec.primary_key])
                        sf_cursor.execute(
                            f"""
                            SELECT COUNT(*)
                            FROM {RAW_TABLE}
                            WHERE SOURCE_TABLE = %s
                              AND SOURCE_PK = %s
                            """,
                            (spec.name, source_pk),
                        )
                        if int(sf_cursor.fetchone()[0]) == 0:
                            missing.append(row_to_change(spec, row))

                    inserted = sum(_merge_raw(sf_cursor, r, batch_id) for r in missing)

                    sf_cursor.execute(
                        f"""
                        SELECT COUNT(DISTINCT SOURCE_PK)
                        FROM {RAW_TABLE}
                        WHERE SOURCE_TABLE = %s
                        """,
                        (spec.name,),
                    )
                    raw_distinct_pks = int(sf_cursor.fetchone()[0])

                    expected_pks = len({str(row[spec.primary_key]) for row in source_rows})
                    if raw_distinct_pks != expected_pks:
                        raise RuntimeError(
                            f"Backfill reconciliation failed for {spec.name}: "
                            f"source distinct PKs={expected_pks}, RAW distinct PKs={raw_distinct_pks}"
                        )

                    reconciliation = Reconciliation(
                        source_rows=len(source_rows),
                        candidate_rows=len(missing),
                        inserted_rows=inserted,
                    )
                    if not reconciliation.is_consistent:
                        raise RuntimeError(
                            f"Backfill insert reconciliation failed for {spec.name}: {reconciliation}"
                        )

                    _write_batch(
                        sf_cursor,
                        batch_id=batch_id,
                        started_at=started_at,
                        status="SUCCESS",
                        rows_extracted=len(missing),
                        rows_inserted=inserted,
                        notes="one-time missing-primary-key backfill after demo-history bootstrap",
                    )
                    LOGGER.info(
                        "backfill_reconciliation table=%s source_rows=%d missing_pks=%d inserted=%d raw_distinct_pks=%d",
                        spec.name,
                        len(source_rows),
                        len(missing),
                        inserted,
                        raw_distinct_pks,
                    )

        LOGGER.info("backfill_complete tables=%d", len(TABLES))
    finally:
        pg.close()
        sf.close()


if __name__ == "__main__":
    run()
