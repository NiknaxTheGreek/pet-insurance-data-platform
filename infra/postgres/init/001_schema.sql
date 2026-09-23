CREATE TABLE IF NOT EXISTS customers (
    customer_id TEXT PRIMARY KEY,
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    province TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    CHECK (updated_at >= created_at)
);

CREATE TABLE IF NOT EXISTS pets (
    pet_id TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL REFERENCES customers(customer_id),
    pet_name TEXT NOT NULL,
    species TEXT NOT NULL CHECK (species IN ('DOG','CAT')),
    breed TEXT NOT NULL,
    date_of_birth DATE NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    CHECK (updated_at >= created_at)
);

CREATE TABLE IF NOT EXISTS policies (
    policy_id TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL REFERENCES customers(customer_id),
    pet_id TEXT NOT NULL REFERENCES pets(pet_id),
    plan_type TEXT NOT NULL CHECK (plan_type IN ('ACCIDENT','CORE','COMPREHENSIVE')),
    policy_status TEXT NOT NULL CHECK (policy_status IN ('ACTIVE','CANCELLED','LAPSED')),
    start_date DATE NOT NULL,
    end_date DATE,
    monthly_premium NUMERIC(12,2) NOT NULL CHECK (monthly_premium >= 0),
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    CHECK (end_date IS NULL OR end_date >= start_date),
    CHECK (updated_at >= created_at)
);

CREATE TABLE IF NOT EXISTS claims (
    claim_id TEXT PRIMARY KEY,
    policy_id TEXT NOT NULL REFERENCES policies(policy_id),
    pet_id TEXT NOT NULL REFERENCES pets(pet_id),
    claim_type TEXT NOT NULL CHECK (claim_type IN ('ACCIDENT','ILLNESS','ROUTINE_CARE')),
    claim_status TEXT NOT NULL CHECK (claim_status IN ('SUBMITTED','ASSESSED','APPROVED','REJECTED','PAID')),
    claim_date DATE NOT NULL,
    claim_amount NUMERIC(12,2) NOT NULL CHECK (claim_amount >= 0),
    approved_amount NUMERIC(12,2),
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    CHECK (approved_amount IS NULL OR (approved_amount >= 0 AND approved_amount <= claim_amount)),
    CHECK (updated_at >= created_at)
);

CREATE TABLE IF NOT EXISTS claim_payments (
    payment_id TEXT PRIMARY KEY,
    claim_id TEXT NOT NULL REFERENCES claims(claim_id),
    payment_date DATE NOT NULL,
    payment_amount NUMERIC(12,2) NOT NULL CHECK (payment_amount > 0),
    payment_status TEXT NOT NULL CHECK (payment_status IN ('PENDING','PAID','SETTLED','REVERSED')),
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    CHECK (updated_at >= created_at)
);

CREATE INDEX IF NOT EXISTS idx_pets_customer_id ON pets(customer_id);
CREATE INDEX IF NOT EXISTS idx_policies_customer_id ON policies(customer_id);
CREATE INDEX IF NOT EXISTS idx_policies_pet_id ON policies(pet_id);
CREATE INDEX IF NOT EXISTS idx_claims_policy_id ON claims(policy_id);
CREATE INDEX IF NOT EXISTS idx_claims_pet_id ON claims(pet_id);
CREATE INDEX IF NOT EXISTS idx_claims_updated_at ON claims(updated_at);
CREATE INDEX IF NOT EXISTS idx_claim_payments_claim_id ON claim_payments(claim_id);
CREATE INDEX IF NOT EXISTS idx_claim_payments_updated_at ON claim_payments(updated_at);
