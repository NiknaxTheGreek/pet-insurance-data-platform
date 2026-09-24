from __future__ import annotations

import csv
import logging
import os
from pathlib import Path

LOGGER = logging.getLogger(__name__)

TABLE_ORDER = (
    "customers",
    "pets",
    "policies",
    "claims",
    "claim_payments",
)


def required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Required environment variable {name} is not set")
    return value


def load_seed(input_dir: Path) -> dict[str, int]:
    import psycopg
    from psycopg import sql

    counts: dict[str, int] = {}
    with psycopg.connect(required("POSTGRES_DSN")) as conn:
        with conn.cursor() as cur:
            for table in TABLE_ORDER:
                path = input_dir / f"{table}.csv"
                if not path.exists():
                    raise FileNotFoundError(path)

                with path.open("r", encoding="utf-8", newline="") as handle:
                    reader = csv.reader(handle)
                    header = next(reader)
                    handle.seek(0)

                    copy_sql = sql.SQL(
                        "COPY {} ({}) FROM STDIN WITH (FORMAT CSV, HEADER TRUE)"
                    ).format(
                        sql.Identifier(table),
                        sql.SQL(", ").join(sql.Identifier(col) for col in header),
                    )
                    with cur.copy(copy_sql) as copy:
                        while chunk := handle.read(1024 * 1024):
                            copy.write(chunk)

                cur.execute(
                    sql.SQL("SELECT COUNT(*) FROM {}").format(sql.Identifier(table))
                )
                counts[table] = int(cur.fetchone()[0])
                LOGGER.info("seed_loaded table=%s rows=%d", table, counts[table])

    return counts


def run() -> None:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    input_dir = Path(os.getenv("SEED_DIR", "data/generated"))
    counts = load_seed(input_dir)
    print("SEED_COUNTS=" + ",".join(f"{k}:{v}" for k, v in counts.items()))
    print(f"SEED_TOTAL_ROWS={sum(counts.values())}")


if __name__ == "__main__":
    run()
