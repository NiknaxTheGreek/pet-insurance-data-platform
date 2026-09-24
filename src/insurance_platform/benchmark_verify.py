from __future__ import annotations

import json
import os


TABLES = ("customers", "pets", "policies", "claims", "claim_payments")


def required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Required environment variable {name} is not set")
    return value


def run() -> None:
    import psycopg
    import snowflake.connector

    pg = psycopg.connect(required("POSTGRES_DSN"))
    sf = snowflake.connector.connect(
        account=required("SNOWFLAKE_ACCOUNT"),
        user=required("SNOWFLAKE_USER"),
        role=required("SNOWFLAKE_ROLE"),
        warehouse=required("SNOWFLAKE_WAREHOUSE"),
        database=required("SNOWFLAKE_DATABASE"),
        authenticator="WORKLOAD_IDENTITY",
        workload_identity_provider="OIDC",
        token=required("SNOWFLAKE_TOKEN"),
    )

    try:
        source_counts = {}
        with pg.cursor() as cur:
            for table in TABLES:
                cur.execute(f"SELECT COUNT(*) FROM {table}")
                source_counts[table] = int(cur.fetchone()[0])

        raw_counts = {}
        with sf.cursor() as cur:
            for table in TABLES:
                cur.execute(
                    """
                    SELECT COUNT(*), COUNT(DISTINCT SOURCE_PK)
                    FROM PET_INSURANCE_BENCHMARK.SOURCE_RECORDS
                    WHERE SOURCE_TABLE = %s
                    """,
                    (table,),
                )
                raw_rows, distinct_keys = map(int, cur.fetchone())
                raw_counts[table] = {
                    "raw_rows": raw_rows,
                    "distinct_keys": distinct_keys,
                }
                if raw_rows != source_counts[table] or distinct_keys != source_counts[table]:
                    raise RuntimeError(
                        f"Benchmark count mismatch for {table}: "
                        f"source={source_counts[table]} raw={raw_rows} distinct={distinct_keys}"
                    )

            cur.execute(
                """
                SELECT COUNT(*)
                FROM PET_INSURANCE_BENCHMARK.SOURCE_RECORDS
                """
            )
            raw_total = int(cur.fetchone()[0])

        source_total = sum(source_counts.values())
        if raw_total != source_total:
            raise RuntimeError(
                f"Benchmark total mismatch: source={source_total} raw={raw_total}"
            )

        summary = {
            "source_counts": source_counts,
            "raw_counts": raw_counts,
            "source_total": source_total,
            "raw_total": raw_total,
            "reconciled": True,
        }
        print(json.dumps(summary, sort_keys=True))
    finally:
        pg.close()
        sf.close()


if __name__ == "__main__":
    run()
