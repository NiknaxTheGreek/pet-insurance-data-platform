from __future__ import annotations

import argparse
import os
from pathlib import Path
from urllib.parse import unquote, urlparse

import yaml


def required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Required environment variable {name} is not set")
    return value


def parse_postgres_dsn(dsn: str) -> dict[str, str]:
    parsed = urlparse(dsn)
    if parsed.scheme not in {"postgres", "postgresql"}:
        raise ValueError("Estuary PostgreSQL DSN must use postgres:// or postgresql://")
    if not parsed.hostname or not parsed.username or parsed.password is None:
        raise ValueError("Estuary PostgreSQL DSN must include host, user and password")
    if "-pooler" in parsed.hostname:
        raise ValueError(
            "Estuary requires a direct Neon connection; pooled '-pooler' hosts cannot replicate WAL"
        )
    return {
        "address": f"{parsed.hostname}:{parsed.port or 5432}",
        "database": (parsed.path or "/postgres").lstrip("/") or "postgres",
        "user": unquote(parsed.username),
        "password": unquote(parsed.password),
    }


def write_capture_spec(path: Path) -> None:
    prefix = required("ESTUARY_PREFIX").rstrip("/")
    pg = parse_postgres_dsn(required("ESTUARY_POSTGRES_DSN"))

    capture_name = f"{prefix}/pet-insurance/source-neon"
    payload = {
        "captures": {
            capture_name: {
                "endpoint": {
                    "connector": {
                        "image": "ghcr.io/estuary/source-postgres:v3",
                        "config": {
                            **{k: pg[k] for k in ("address", "database", "user")},
                            "historyMode": True,
                            "credentials": {
                                "auth_type": "UserPassword",
                                "password": pg["password"],
                            },
                            "discoveryFilters": {
                                "include_schemas": ["public"],
                                "table_patterns": ["public.claims"],
                            },
                            "advanced": {
                                "publicationName": "pet_insurance_estuary_publication",
                                "watermarksTable": "public.flow_watermarks",
                                "sslmode": "verify-full",
                                "discover_schemas": ["public"],
                            },
                        },
                    }
                },
                "bindings": [],
            }
        }
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def add_snowflake_materialization(path: Path) -> None:
    prefix = required("ESTUARY_PREFIX").rstrip("/")
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))

    capture_name = f"{prefix}/pet-insurance/source-neon"
    capture = payload["captures"][capture_name]
    claims_binding = next(
        (
            binding
            for binding in capture.get("bindings", [])
            if binding.get("resource", {}).get("namespace") == "public"
            and binding.get("resource", {}).get("stream") == "claims"
        ),
        None,
    )
    if claims_binding is None:
        raise RuntimeError("flowctl discover did not produce a public.claims binding")

    collection_name = claims_binding["target"]
    materialization_name = f"{prefix}/pet-insurance/materialize-snowflake"

    payload.setdefault("materializations", {})[materialization_name] = {
        "endpoint": {
            "connector": {
                "image": "ghcr.io/estuary/materialize-snowflake:v4",
                "config": {
                    "host": required("ESTUARY_SNOWFLAKE_HOST"),
                    "database": required("ESTUARY_SNOWFLAKE_DATABASE"),
                    "schema": required("ESTUARY_SNOWFLAKE_SCHEMA"),
                    "warehouse": required("ESTUARY_SNOWFLAKE_WAREHOUSE"),
                    "role": required("ESTUARY_SNOWFLAKE_ROLE"),
                    "timestamp_type": "TIMESTAMP_LTZ",
                    "hardDelete": False,
                    "credentials": {
                        "auth_type": "jwt",
                        "user": required("ESTUARY_SNOWFLAKE_USER"),
                        "private_key": required("ESTUARY_SNOWFLAKE_PRIVATE_KEY"),
                    },
                },
            }
        },
        "bindings": [
            {
                "resource": {"table": "CLAIMS"},
                "source": collection_name,
            }
        ],
    }

    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["capture", "materialization"])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    if args.mode == "capture":
        write_capture_spec(args.output)
    else:
        add_snowflake_materialization(args.output)


if __name__ == "__main__":
    main()
