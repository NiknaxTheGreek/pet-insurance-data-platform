from __future__ import annotations

import json
import os
from pathlib import Path


def required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Required environment variable {name} is not set")
    return value


def run() -> None:
    import snowflake.connector

    manifest = json.loads(
        Path("work/gcp_backfill/claims_backfill_manifest.json").read_text(encoding="utf-8")
    )

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
        with sf.cursor() as cur:
            cur.execute(
                """
                SELECT
                    COUNT(*) AS ROW_COUNT,
                    COALESCE(SUM(CLAIM_AMOUNT), 0) AS CLAIM_AMOUNT_SUM,
                    MIN(CLAIM_ID) AS MIN_CLAIM_ID,
                    MAX(CLAIM_ID) AS MAX_CLAIM_ID
                FROM PET_INSURANCE_GCP.CLAIMS_BACKFILL
                """
            )
            row = cur.fetchone()

        actual = {
            "row_count": int(row[0]),
            "claim_amount_sum": format(row[1], "f"),
            "min_claim_id": row[2],
            "max_claim_id": row[3],
        }
        expected = {
            key: manifest[key]
            for key in ("row_count", "claim_amount_sum", "min_claim_id", "max_claim_id")
        }
        if actual != expected:
            raise RuntimeError(f"GCP backfill reconciliation failed: expected={expected}, actual={actual}")
        print(json.dumps({"status": "PASS", "expected": expected, "actual": actual}, sort_keys=True))
    finally:
        sf.close()


if __name__ == "__main__":
    run()
