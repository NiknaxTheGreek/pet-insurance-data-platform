from __future__ import annotations

import argparse
import os
from pathlib import Path
from urllib.parse import unquote, urlparse, urlunparse

import yaml


def required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Required environment variable {name} is not set")
    return value


def direct_neon_dsn(dsn: str) -> str:
    parsed = urlparse(dsn)
    if not parsed.hostname:
        raise ValueError("Neon DSN must include a hostname")

    host = parsed.hostname.replace("-pooler", "")
    userinfo = ""
    if parsed.username is not None:
        userinfo = parsed.username
        if parsed.password is not None:
            userinfo += f":{parsed.password}"
        userinfo += "@"

    port = f":{parsed.port}" if parsed.port else ""
    netloc = f"{userinfo}{host}{port}"
    return urlunparse(
        (
            parsed.scheme,
            netloc,
            parsed.path,
            parsed.params,
            parsed.query,
            parsed.fragment,
        )
    )


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
    source_dsn = os.getenv("ESTUARY_POSTGRES_DSN")
    if not source_dsn:
        source_dsn = direct_neon_dsn(required("POSTGRES_DSN"))
    pg = parse_postgres_dsn(source_dsn)

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
    if path.exists():
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    else:
        payload = {}

    collection_name = f"{prefix}/pet-insurance/public/claims"
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
                "resource": {
                    "table": "CLAIMS",
                    "delta_updates": True,
                },
                "source": collection_name,
                "fields": {
                    "recommended": 2,
                    "require": {
                        "flow_document": {},
                    },
                },
            }
        ],
    }

    path.parent.mkdir(parents=True, exist_ok=True)
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
