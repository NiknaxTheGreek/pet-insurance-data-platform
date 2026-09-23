from __future__ import annotations

import logging
import os
from datetime import date, datetime, timezone
from decimal import Decimal

LOGGER = logging.getLogger(__name__)

CLAIM_ID = "CLM-10042"
PAYMENT_ID = "PAY-10042-T4"
EVENT_TS = datetime(2026, 9, 23, 19, 40, 0, tzinfo=timezone.utc)


def required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Required environment variable {name} is not set")
    return value


def run() -> None:
    logging.basicConfig(
        level="INFO",
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    import psycopg
    from psycopg.rows import dict_row

    with psycopg.connect(required("POSTGRES_DSN"), row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT claim_id, claim_amount, approved_amount, claim_status, updated_at
                FROM claims
                WHERE claim_id = %s
                FOR UPDATE
                """,
                (CLAIM_ID,),
            )
            claim = cur.fetchone()
            if claim is None:
                raise RuntimeError(f"{CLAIM_ID} does not exist")

            if claim["claim_amount"] != Decimal("11200.00"):
                raise RuntimeError(f"Unexpected claim_amount: {claim['claim_amount']}")
            if claim["approved_amount"] != Decimal("9700.00"):
                raise RuntimeError(f"Unexpected approved_amount: {claim['approved_amount']}")

            claim_changed = False
            if claim["claim_status"] != "PAID":
                cur.execute(
                    """
                    UPDATE claims
                    SET claim_status = 'PAID',
                        updated_at = %s
                    WHERE claim_id = %s
                    """,
                    (EVENT_TS, CLAIM_ID),
                )
                claim_changed = True

            cur.execute(
                """
                INSERT INTO claim_payments (
                    payment_id,
                    claim_id,
                    payment_date,
                    payment_amount,
                    payment_status,
                    created_at,
                    updated_at,
                    is_deleted
                )
                VALUES (%s, %s, %s, %s, 'PAID', %s, %s, FALSE)
                ON CONFLICT (payment_id) DO NOTHING
                """,
                (
                    PAYMENT_ID,
                    CLAIM_ID,
                    date(2026, 9, 23),
                    Decimal("9700.00"),
                    EVENT_TS,
                    EVENT_TS,
                ),
            )
            payment_inserted = max(int(cur.rowcount or 0), 0)

            cur.execute(
                """
                SELECT claim_id, claim_amount, approved_amount, claim_status, updated_at
                FROM claims
                WHERE claim_id = %s
                """,
                (CLAIM_ID,),
            )
            final_claim = cur.fetchone()

            cur.execute(
                """
                SELECT payment_id, claim_id, payment_date, payment_amount, payment_status, updated_at
                FROM claim_payments
                WHERE payment_id = %s
                """,
                (PAYMENT_ID,),
            )
            payment = cur.fetchone()

            if final_claim["claim_status"] != "PAID":
                raise RuntimeError("T4 claim mutation did not persist")
            if payment is None or payment["payment_amount"] != Decimal("9700.00"):
                raise RuntimeError("T4 payment mutation did not persist")

            LOGGER.info(
                "t4_source_mutation claim_id=%s claim_changed=%s status=%s amount=%s approved=%s updated_at=%s",
                CLAIM_ID,
                claim_changed,
                final_claim["claim_status"],
                final_claim["claim_amount"],
                final_claim["approved_amount"],
                final_claim["updated_at"],
            )
            LOGGER.info(
                "t4_source_payment payment_id=%s inserted=%d claim_id=%s amount=%s status=%s updated_at=%s",
                PAYMENT_ID,
                payment_inserted,
                payment["claim_id"],
                payment["payment_amount"],
                payment["payment_status"],
                payment["updated_at"],
            )


if __name__ == "__main__":
    run()
