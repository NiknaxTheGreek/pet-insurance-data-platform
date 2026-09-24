from __future__ import annotations

import argparse
import os
from datetime import date
from decimal import Decimal


def required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Required environment variable {name} is not set")
    return value


def run(mode: str) -> None:
    import psycopg

    claim_id = required("ESTUARY_DEMO_CLAIM_ID")

    with psycopg.connect(required("POSTGRES_DSN"), autocommit=True) as conn:
        with conn.cursor() as cur:
            if mode == "insert":
                cur.execute(
                    """
                    INSERT INTO claims (
                        claim_id,
                        policy_id,
                        pet_id,
                        claim_type,
                        claim_date,
                        claim_amount,
                        approved_amount,
                        claim_status,
                        created_at,
                        updated_at,
                        is_deleted
                    )
                    VALUES (
                        %s,
                        'POL-00002',
                        'PET-00002',
                        'ILLNESS',
                        CURRENT_DATE,
                        1750.00,
                        NULL,
                        'SUBMITTED',
                        CURRENT_TIMESTAMP,
                        CURRENT_TIMESTAMP,
                        FALSE
                    )
                    ON CONFLICT (claim_id) DO NOTHING
                    """,
                    (claim_id,),
                )

            elif mode == "update":
                cur.execute(
                    """
                    UPDATE claims
                    SET claim_amount = 2100.00,
                        approved_amount = 1900.00,
                        claim_status = 'APPROVED',
                        updated_at = CURRENT_TIMESTAMP
                    WHERE claim_id = %s
                    """,
                    (claim_id,),
                )
                if cur.rowcount != 1:
                    raise RuntimeError(f"Expected one claim update for {claim_id}")

            elif mode == "delete":
                cur.execute(
                    "DELETE FROM claims WHERE claim_id = %s",
                    (claim_id,),
                )
                if cur.rowcount != 1:
                    raise RuntimeError(f"Expected one physical delete for {claim_id}")

            else:
                raise ValueError(f"Unsupported mode: {mode}")

    print(f"estuary_demo_source_mutation mode={mode} claim_id={claim_id}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["insert", "update", "delete"])
    args = parser.parse_args()
    run(args.mode)
