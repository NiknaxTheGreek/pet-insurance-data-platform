from __future__ import annotations

import argparse
import logging
import os
from datetime import datetime, timezone
from decimal import Decimal

LOGGER = logging.getLogger(__name__)

BAD_PAYMENT_ID = "PAY-DQ-10043"
BAD_PAYMENT_CLAIM_ID = "CLM-10043"
LATE_CLAIM_ID = os.getenv("LATE_CLAIM_ID", "CLM-LATE-10045")
LATE_EXISTING_CLAIM_ID = os.getenv("LATE_EXISTING_CLAIM_ID", "CLM-E-10045")
TXN_FAILURE_CLAIM_ID = os.getenv("TXN_FAILURE_CLAIM_ID", "CLM-TX-10045")
SOFT_DELETE_CLAIM_ID = "CLM-10043"


def required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Required environment variable {name} is not set")
    return value


def _touch_expression() -> str:
    return "GREATEST(CURRENT_TIMESTAMP, updated_at + INTERVAL '1 second')"


def inject_invalid_payment(cur) -> None:
    cur.execute(
        """
        SELECT claim_date
        FROM claims
        WHERE claim_id = %s
        """,
        (BAD_PAYMENT_CLAIM_ID,),
    )
    claim = cur.fetchone()
    if claim is None:
        raise RuntimeError(f"{BAD_PAYMENT_CLAIM_ID} does not exist")

    cur.execute(
        """
        INSERT INTO claim_payments (
            payment_id, claim_id, payment_date, payment_amount, payment_status,
            created_at, updated_at, is_deleted
        )
        SELECT
            %s,
            c.claim_id,
            (c.claim_date - INTERVAL '1 day')::date,
            100.00,
            'PAID',
            CURRENT_TIMESTAMP,
            CURRENT_TIMESTAMP,
            FALSE
        FROM claims c
        WHERE c.claim_id = %s
        ON CONFLICT (payment_id) DO UPDATE SET
            payment_date = EXCLUDED.payment_date,
            payment_amount = EXCLUDED.payment_amount,
            payment_status = EXCLUDED.payment_status,
            is_deleted = FALSE,
            updated_at = GREATEST(CURRENT_TIMESTAMP, claim_payments.updated_at + INTERVAL '1 second')
        """,
        (BAD_PAYMENT_ID, BAD_PAYMENT_CLAIM_ID),
    )
    LOGGER.info("dq_injected payment_id=%s rule=payment_date_before_claim", BAD_PAYMENT_ID)


def repair_invalid_payment(cur) -> None:
    cur.execute(
        """
        UPDATE claim_payments p
        SET payment_date = c.claim_date,
            updated_at = GREATEST(CURRENT_TIMESTAMP, p.updated_at + INTERVAL '1 second')
        FROM claims c
        WHERE p.payment_id = %s
          AND p.claim_id = c.claim_id
        """,
        (BAD_PAYMENT_ID,),
    )
    if cur.rowcount != 1:
        raise RuntimeError(f"Expected to repair one row for {BAD_PAYMENT_ID}, got {cur.rowcount}")
    LOGGER.info("dq_repaired payment_id=%s rule=payment_date_not_before_claim", BAD_PAYMENT_ID)


def insert_late_claim(cur) -> None:
    cur.execute(
        """
        INSERT INTO claims (
            claim_id, policy_id, pet_id, claim_type, claim_status, claim_date,
            claim_amount, approved_amount, created_at, updated_at, is_deleted
        )
        SELECT
            %s,
            p.policy_id,
            p.pet_id,
            'ILLNESS',
            'SUBMITTED',
            DATE '2026-09-21',
            1800.00,
            NULL,
            TIMESTAMPTZ '2026-09-21 12:00:00+00',
            TIMESTAMPTZ '2026-09-21 12:00:00+00',
            FALSE
        FROM policies p
        WHERE p.policy_id = 'POL-00002'
        ON CONFLICT (claim_id) DO NOTHING
        """,
        (LATE_CLAIM_ID,),
    )
    LOGGER.info(
        "late_claim_present claim_id=%s source_updated_at=2026-09-21T12:00:00Z",
        LATE_CLAIM_ID,
    )


def insert_late_existing_claim(cur) -> None:
    cur.execute(
        """
        INSERT INTO claims (
            claim_id, policy_id, pet_id, claim_type, claim_status, claim_date,
            claim_amount, approved_amount, created_at, updated_at, is_deleted
        )
        SELECT
            %s,
            p.policy_id,
            p.pet_id,
            'ILLNESS',
            'SUBMITTED',
            DATE '2026-09-21',
            2100.00,
            NULL,
            TIMESTAMPTZ '2026-09-21 13:00:00+00',
            TIMESTAMPTZ '2026-09-21 13:00:00+00',
            FALSE
        FROM policies p
        WHERE p.policy_id = 'POL-00002'
        ON CONFLICT (claim_id) DO NOTHING
        """,
        (LATE_EXISTING_CLAIM_ID,),
    )
    LOGGER.info(
        "late_existing_claim_present claim_id=%s amount=2100 updated_at=2026-09-21T13:00:00Z",
        LATE_EXISTING_CLAIM_ID,
    )


def mutate_late_existing_claim(cur) -> None:
    cur.execute(
        """
        UPDATE claims
        SET claim_amount = 2600.00,
            updated_at = TIMESTAMPTZ '2026-09-21 14:00:00+00'
        WHERE claim_id = %s
          AND claim_amount = 2100.00
        """,
        (LATE_EXISTING_CLAIM_ID,),
    )
    LOGGER.info(
        "late_existing_claim_mutated claim_id=%s changed_rows=%d amount=2600 updated_at=2026-09-21T14:00:00Z",
        LATE_EXISTING_CLAIM_ID,
        cur.rowcount,
    )


def insert_transaction_failure_claim(cur) -> None:
    cur.execute(
        """
        INSERT INTO claims (
            claim_id, policy_id, pet_id, claim_type, claim_status, claim_date,
            claim_amount, approved_amount, created_at, updated_at, is_deleted
        )
        SELECT
            %s,
            p.policy_id,
            p.pet_id,
            'ACCIDENT',
            'SUBMITTED',
            CURRENT_DATE,
            2300.00,
            NULL,
            CURRENT_TIMESTAMP,
            CURRENT_TIMESTAMP,
            FALSE
        FROM policies p
        WHERE p.policy_id = 'POL-00002'
        ON CONFLICT (claim_id) DO NOTHING
        """,
        (TXN_FAILURE_CLAIM_ID,),
    )
    LOGGER.info(
        "transaction_failure_claim_present claim_id=%s inserted_or_existing_rows=%d",
        TXN_FAILURE_CLAIM_ID,
        cur.rowcount,
    )


def soft_delete_claim(cur) -> None:
    cur.execute(
        f"""
        UPDATE claims
        SET is_deleted = TRUE,
            updated_at = {_touch_expression()}
        WHERE claim_id = %s
          AND is_deleted = FALSE
        """,
        (SOFT_DELETE_CLAIM_ID,),
    )
    LOGGER.info(
        "soft_delete_applied claim_id=%s changed_rows=%d",
        SOFT_DELETE_CLAIM_ID,
        cur.rowcount,
    )


def run(mode: str) -> None:
    logging.basicConfig(
        level="INFO",
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    import psycopg
    from psycopg.rows import dict_row

    handlers = {
        "inject-invalid-payment": inject_invalid_payment,
        "repair-invalid-payment": repair_invalid_payment,
        "insert-late-claim": insert_late_claim,
        "insert-late-existing-claim": insert_late_existing_claim,
        "mutate-late-existing-claim": mutate_late_existing_claim,
        "insert-transaction-failure-claim": insert_transaction_failure_claim,
        "soft-delete-claim": soft_delete_claim,
    }

    with psycopg.connect(required("POSTGRES_DSN"), row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            handlers[mode](cur)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "mode",
        choices=[
            "inject-invalid-payment",
            "repair-invalid-payment",
            "insert-late-claim",
            "insert-late-existing-claim",
            "mutate-late-existing-claim",
            "insert-transaction-failure-claim",
            "soft-delete-claim",
        ],
    )
    args = parser.parse_args()
    run(args.mode)
