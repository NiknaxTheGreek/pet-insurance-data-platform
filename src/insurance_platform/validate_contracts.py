from __future__ import annotations

import logging
import os
from pathlib import Path

from insurance_platform.contracts import validate_source_contracts


def required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Required environment variable {name} is not set")
    return value


def run() -> None:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    import psycopg
    from psycopg.rows import dict_row

    contract_dir = Path(os.getenv("SOURCE_CONTRACT_DIR", "contracts"))
    with psycopg.connect(required("POSTGRES_DSN"), row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            validate_source_contracts(cur, contract_dir)


if __name__ == "__main__":
    run()
