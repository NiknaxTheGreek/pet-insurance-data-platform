import csv
from pathlib import Path
from insurance_platform.generate_seed import generate

def read_rows(path:Path):
    with path.open(encoding="utf-8") as f: return list(csv.DictReader(f))

def test_seed_generation_is_deterministic(tmp_path):
    a=generate(tmp_path/"a",n_customers=50); b=generate(tmp_path/"b",n_customers=50)
    assert a==b
    assert (tmp_path/"a"/"claims.csv").read_text()==(tmp_path/"b"/"claims.csv").read_text()

def test_referential_integrity_in_generated_data(tmp_path):
    generate(tmp_path,n_customers=100)
    customers=read_rows(tmp_path/"customers.csv"); pets=read_rows(tmp_path/"pets.csv"); policies=read_rows(tmp_path/"policies.csv"); claims=read_rows(tmp_path/"claims.csv"); payments=read_rows(tmp_path/"claim_payments.csv")
    customer_ids={r["customer_id"] for r in customers}; pet_ids={r["pet_id"] for r in pets}; policy_ids={r["policy_id"] for r in policies}; claim_ids={r["claim_id"] for r in claims}
    assert all(r["customer_id"] in customer_ids for r in pets)
    assert all(r["customer_id"] in customer_ids and r["pet_id"] in pet_ids for r in policies)
    assert all(r["policy_id"] in policy_ids and r["pet_id"] in pet_ids for r in claims)
    assert all(r["claim_id"] in claim_ids for r in payments)

def test_claim_amount_business_rule(tmp_path):
    generate(tmp_path,n_customers=100)
    for row in read_rows(tmp_path/"claims.csv"):
        if row["approved_amount"]: assert 0<=float(row["approved_amount"])<=float(row["claim_amount"])


def test_generated_customer_pii_fields_are_present_and_synthetic(tmp_path):
    generate(tmp_path, n_customers=5)
    customers = read_rows(tmp_path / "customers.csv")
    assert all(row["email"].endswith("@example.invalid") for row in customers)
    assert all("phone" in row and "postal_code" in row for row in customers)
