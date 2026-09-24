from __future__ import annotations

import os
import subprocess
from pathlib import Path

from dagster import RetryPolicy, job, op

from insurance_platform.contracts import validate_source_contracts
from insurance_platform.run_ingestion import run as run_ingestion


def _required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Required environment variable {name} is not set")
    return value


@op(retry_policy=RetryPolicy(max_retries=2, delay=2))
def validate_source_contracts_op() -> str:
    import psycopg
    from psycopg.rows import dict_row

    with psycopg.connect(_required("POSTGRES_DSN"), row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            results = validate_source_contracts(cur, Path("contracts"))

    if len(results) != 5:
        raise RuntimeError(f"Expected five source contracts, got {len(results)}")
    return "contracts_valid"


@op(retry_policy=RetryPolicy(max_retries=2, delay=2))
def ingest_source_op(contract_status: str) -> str:
    if contract_status != "contracts_valid":
        raise RuntimeError(f"Unexpected contract status: {contract_status}")
    run_ingestion()
    return "ingestion_complete"


@op(retry_policy=RetryPolicy(max_retries=1, delay=2))
def dbt_build_op(ingestion_status: str) -> str:
    if ingestion_status != "ingestion_complete":
        raise RuntimeError(f"Unexpected ingestion status: {ingestion_status}")

    subprocess.run(
        [
            "dbt",
            "build",
            "--project-dir",
            "dbt",
            "--profiles-dir",
            "dbt",
            "--fail-fast",
        ],
        check=True,
    )
    return "dbt_complete"


@op(retry_policy=RetryPolicy(max_retries=2, delay=2))
def verify_health_op(dbt_status: str) -> None:
    if dbt_status != "dbt_complete":
        raise RuntimeError(f"Unexpected dbt status: {dbt_status}")

    import snowflake.connector

    connection = snowflake.connector.connect(
        account=_required("SNOWFLAKE_ACCOUNT"),
        user=_required("SNOWFLAKE_USER"),
        role=_required("SNOWFLAKE_ROLE"),
        warehouse=_required("SNOWFLAKE_WAREHOUSE"),
        database=_required("SNOWFLAKE_DATABASE"),
        authenticator="WORKLOAD_IDENTITY",
        workload_identity_provider="OIDC",
        token=_required("SNOWFLAKE_TOKEN"),
    )
    try:
        with connection.cursor() as cur:
            cur.execute(
                """
                SELECT
                    COUNT(*) AS TABLES,
                    COUNT_IF(LATEST_STATUS = 'SUCCESS') AS HEALTHY_TABLES,
                    COUNT_IF(LAST_RECONCILIATION_STATUS = 'CONSISTENT') AS CONSISTENT_TABLES
                FROM PET_INSURANCE_CONTROL.INGESTION_HEALTH
                """
            )
            tables, healthy, consistent = map(int, cur.fetchone())
            if (tables, healthy, consistent) != (5, 5, 5):
                raise RuntimeError(
                    "Ingestion health check failed: "
                    f"tables={tables} healthy={healthy} consistent={consistent}"
                )
    finally:
        connection.close()


@job
def pet_insurance_pipeline():
    verify_health_op(
        dbt_build_op(
            ingest_source_op(
                validate_source_contracts_op()
            )
        )
    )


def run() -> None:
    result = pet_insurance_pipeline.execute_in_process()
    if not result.success:
        raise RuntimeError("Dagster pipeline did not complete successfully")


if __name__ == "__main__":
    run()
