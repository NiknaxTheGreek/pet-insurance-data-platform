import pytest

from insurance_platform.estuary_flow_spec import direct_neon_dsn, parse_postgres_dsn


def test_estuary_dsn_parser_accepts_direct_neon_connection():
    parsed = parse_postgres_dsn(
        "postgresql://cdc_user:s3cret@ep-direct.aws.neon.tech:5432/pet_insurance?sslmode=require"
    )
    assert parsed == {
        "address": "ep-direct.aws.neon.tech:5432",
        "database": "pet_insurance",
        "user": "cdc_user",
        "password": "s3cret",
    }


def test_estuary_dsn_parser_rejects_neon_pooler():
    with pytest.raises(ValueError, match="direct Neon connection"):
        parse_postgres_dsn(
            "postgresql://cdc_user:s3cret@ep-example-pooler.aws.neon.tech/pet_insurance"
        )


def test_direct_neon_dsn_removes_pooler_but_preserves_connection_parts():
    direct = direct_neon_dsn(
        "postgresql://cdc_user:s3cret@ep-example-pooler.aws.neon.tech:5432/pet_insurance?sslmode=require"
    )
    assert direct == (
        "postgresql://cdc_user:s3cret@ep-example.aws.neon.tech:5432/"
        "pet_insurance?sslmode=require"
    )
