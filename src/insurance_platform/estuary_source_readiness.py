from __future__ import annotations

import logging
import os

LOGGER = logging.getLogger(__name__)


def required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Required environment variable {name} is not set")
    return value


def run() -> None:
    logging.basicConfig(level="INFO", format="%(asctime)s %(levelname)s %(name)s %(message)s")

    import psycopg
    from psycopg.rows import dict_row

    with psycopg.connect(required("POSTGRES_DSN"), row_factory=dict_row, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("SHOW wal_level")
            wal_level = str(cur.fetchone()["wal_level"])
            cur.execute(
                """
                SELECT current_user AS role_name,
                       rolreplication,
                       rolsuper
                FROM pg_roles
                WHERE rolname = current_user
                """
            )
            role = cur.fetchone()

            LOGGER.info(
                "estuary_source_readiness wal_level=%s role=%s rolreplication=%s rolsuper=%s",
                wal_level,
                role["role_name"],
                role["rolreplication"],
                role["rolsuper"],
            )

            if wal_level.lower() != "logical":
                raise RuntimeError(
                    "Neon logical replication is not enabled. Enable it in Neon Project Settings > Beta; "
                    "this changes wal_level to logical and restarts computes."
                )

            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS public.flow_watermarks (
                    slot TEXT PRIMARY KEY,
                    watermark TEXT
                )
                """
            )

            cur.execute(
                """
                SELECT 1
                FROM pg_publication
                WHERE pubname = 'pet_insurance_estuary_publication'
                """
            )
            if cur.fetchone() is None:
                cur.execute(
                    """
                    CREATE PUBLICATION pet_insurance_estuary_publication
                    WITH (publish_via_partition_root = true)
                    """
                )

            cur.execute(
                """
                SELECT schemaname, tablename
                FROM pg_publication_tables
                WHERE pubname = 'pet_insurance_estuary_publication'
                """
            )
            published = {(row["schemaname"], row["tablename"]) for row in cur.fetchall()}

            for qualified in (("public", "flow_watermarks"), ("public", "claims")):
                if qualified not in published:
                    cur.execute(
                        f"ALTER PUBLICATION pet_insurance_estuary_publication "
                        f"ADD TABLE {qualified[0]}.{qualified[1]}"
                    )

            cur.execute(
                """
                SELECT schemaname, tablename
                FROM pg_publication_tables
                WHERE pubname = 'pet_insurance_estuary_publication'
                ORDER BY schemaname, tablename
                """
            )
            final_tables = [f"{r['schemaname']}.{r['tablename']}" for r in cur.fetchall()]

            LOGGER.info(
                "estuary_publication_ready publication=%s tables=%s",
                "pet_insurance_estuary_publication",
                ",".join(final_tables),
            )


if __name__ == "__main__":
    run()
