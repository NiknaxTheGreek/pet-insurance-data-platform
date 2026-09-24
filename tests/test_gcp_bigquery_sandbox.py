from decimal import Decimal

from insurance_platform.gcp_bigquery_sandbox import generate_rows


def test_bigquery_sandbox_dataset_is_deterministic():
    first = generate_rows(10)
    second = generate_rows(10)
    assert first == second
    assert len(first) == 10
    assert first[0]["claim_id"] == "BQ-CLM-000001"
    assert first[-1]["claim_id"] == "BQ-CLM-000010"


def test_bigquery_sandbox_dataset_contains_expected_business_shape():
    rows = generate_rows(100)
    assert {row["claim_status"] for row in rows} == {
        "SUBMITTED",
        "ASSESSED",
        "APPROVED",
        "PAID",
        "REJECTED",
    }
    assert {row["claim_type"] for row in rows} == {
        "ACCIDENT",
        "ILLNESS",
        "ROUTINE_CARE",
    }
    assert all(Decimal(str(row["claim_amount"])) > 0 for row in rows)
