from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import yaml

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class ContractValidation:
    source_table: str
    errors: tuple[str, ...]
    additive_columns: tuple[str, ...]

    @property
    def is_valid(self) -> bool:
        return not self.errors


def load_contract(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"Contract {path} must contain a mapping")
    return payload


def compare_contract_metadata(
    contract: Mapping[str, Any],
    observed_columns: Mapping[str, tuple[str, bool]],
    primary_key_columns: set[str],
) -> ContractValidation:
    table = str(contract["source_table"])
    expected_columns = contract.get("columns", {})
    allow_additive = bool(contract.get("allow_additive_columns", False))
    errors: list[str] = []

    for name, spec in expected_columns.items():
        if name not in observed_columns:
            errors.append(f"missing required column: {name}")
            continue

        observed_type, observed_nullable = observed_columns[name]
        expected_type = str(spec["data_type"]).lower()
        expected_nullable = bool(spec.get("nullable", True))

        if observed_type.lower() != expected_type:
            errors.append(
                f"type mismatch for {name}: expected {expected_type}, observed {observed_type.lower()}"
            )
        if observed_nullable != expected_nullable:
            errors.append(
                f"nullability mismatch for {name}: "
                f"expected nullable={expected_nullable}, observed nullable={observed_nullable}"
            )

    expected_names = set(expected_columns)
    additive_columns = tuple(sorted(set(observed_columns) - expected_names))
    if additive_columns and not allow_additive:
        errors.append(
            "unexpected additive columns: " + ", ".join(additive_columns)
        )

    expected_pk = str(contract["primary_key"])
    if primary_key_columns != {expected_pk}:
        errors.append(
            f"primary-key mismatch: expected [{expected_pk}], "
            f"observed {sorted(primary_key_columns)}"
        )

    return ContractValidation(
        source_table=table,
        errors=tuple(errors),
        additive_columns=additive_columns,
    )


def inspect_table_contract(pg_cursor, contract: Mapping[str, Any]) -> ContractValidation:
    table = str(contract["source_table"])
    schema = str(contract.get("schema", "public"))

    pg_cursor.execute(
        """
        SELECT column_name, data_type, is_nullable
        FROM information_schema.columns
        WHERE table_schema = %s
          AND table_name = %s
        ORDER BY ordinal_position
        """,
        (schema, table),
    )
    observed_columns = {
        row["column_name"]: (
            row["data_type"],
            str(row["is_nullable"]).upper() == "YES",
        )
        for row in pg_cursor.fetchall()
    }

    pg_cursor.execute(
        """
        SELECT kcu.column_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON tc.constraint_name = kcu.constraint_name
         AND tc.table_schema = kcu.table_schema
         AND tc.table_name = kcu.table_name
        WHERE tc.constraint_type = 'PRIMARY KEY'
          AND tc.table_schema = %s
          AND tc.table_name = %s
        ORDER BY kcu.ordinal_position
        """,
        (schema, table),
    )
    primary_key_columns = {row["column_name"] for row in pg_cursor.fetchall()}

    return compare_contract_metadata(
        contract,
        observed_columns,
        primary_key_columns,
    )


def validate_source_contracts(pg_cursor, contract_dir: Path) -> list[ContractValidation]:
    paths = sorted(contract_dir.glob("*.yml"))
    if not paths:
        raise RuntimeError(f"No source contracts found in {contract_dir}")

    results: list[ContractValidation] = []
    for path in paths:
        contract = load_contract(path)
        result = inspect_table_contract(pg_cursor, contract)
        results.append(result)

        if result.additive_columns:
            LOGGER.warning(
                "source_contract_additive_columns table=%s columns=%s",
                result.source_table,
                ",".join(result.additive_columns),
            )

        if result.errors:
            for error in result.errors:
                LOGGER.error(
                    "source_contract_error table=%s error=%s",
                    result.source_table,
                    error,
                )

    invalid = [result for result in results if not result.is_valid]
    if invalid:
        details = "; ".join(
            f"{result.source_table}: {', '.join(result.errors)}"
            for result in invalid
        )
        raise RuntimeError(f"Source contract validation failed: {details}")

    LOGGER.info(
        "source_contract_validation_complete tables=%d additive_tables=%d",
        len(results),
        sum(bool(result.additive_columns) for result in results),
    )
    return results
