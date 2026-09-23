from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

LOGGER = logging.getLogger(__name__)

CUSTOMER_ID = "CUS-00001"
EVENT_TS = datetime(2026, 9, 23, 20, 10, 0, tzinfo=timezone.utc)
OLD_PROVINCE = "Gauteng"
NEW_PROVINCE = "Western Cape"


def required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Required environment variable {name} is not set")
    return value


def run() -> None:
    logging.basicConfig(level="INFO", format="%(asctime)s %(levelname)s %(name)s %(message)s")

    import psycopg
    from psycopg.rows import dict_row

    with psycopg.connect(required("POSTGRES_DSN"), row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT customer_id, province, updated_at
                FROM customers
                WHERE customer_id = %s
                FOR UPDATE
                """,
                (CUSTOMER_ID,),
            )
            customer = cur.fetchone()
            if customer is None:
                raise RuntimeError(f"{CUSTOMER_ID} does not exist")

            changed = False
            if customer["province"] == OLD_PROVINCE:
                cur.execute(
                    """
                    UPDATE customers
                    SET province = %s,
                        updated_at = %s
                    WHERE customer_id = %s
                    """,
                    (NEW_PROVINCE, EVENT_TS, CUSTOMER_ID),
                )
                changed = True
            elif customer["province"] != NEW_PROVINCE:
                raise RuntimeError(
                    f"Unexpected province for {CUSTOMER_ID}: {customer['province']}"
                )

            cur.execute(
                """
                SELECT customer_id, province, updated_at
                FROM customers
                WHERE customer_id = %s
                """,
                (CUSTOMER_ID,),
            )
            final_customer = cur.fetchone()

            LOGGER.info(
                "customer_history_demo customer_id=%s changed=%s province=%s updated_at=%s",
                CUSTOMER_ID,
                changed,
                final_customer["province"],
                final_customer["updated_at"],
            )


if __name__ == "__main__":
    run()
