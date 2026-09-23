\set ON_ERROR_STOP on

DO $$
DECLARE
    table_count integer;
BEGIN
    SELECT count(*)
    INTO table_count
    FROM information_schema.tables
    WHERE table_schema = 'public'
      AND table_name IN ('customers', 'pets', 'policies', 'claims', 'claim_payments');

    IF table_count <> 5 THEN
        RAISE EXCEPTION 'Expected 5 source tables, found %', table_count;
    END IF;
END
$$;

INSERT INTO customers (
    customer_id, first_name, last_name, province, created_at, updated_at, is_deleted
) VALUES (
    'CUS-00001', 'Docker', 'Customer', 'Gauteng',
    TIMESTAMPTZ '2026-01-01 08:00:00+00',
    TIMESTAMPTZ '2026-01-01 08:00:00+00',
    FALSE
);

INSERT INTO pets (
    pet_id, customer_id, pet_name, species, breed, date_of_birth,
    created_at, updated_at, is_deleted
) VALUES (
    'PET-00001', 'CUS-00001', 'Milo', 'DOG', 'Labrador', DATE '2020-01-01',
    TIMESTAMPTZ '2026-01-01 08:05:00+00',
    TIMESTAMPTZ '2026-01-01 08:05:00+00',
    FALSE
);

INSERT INTO policies (
    policy_id, customer_id, pet_id, plan_type, policy_status, start_date, end_date,
    monthly_premium, created_at, updated_at, is_deleted
) VALUES (
    'POL-00001', 'CUS-00001', 'PET-00001', 'COMPREHENSIVE', 'ACTIVE',
    DATE '2026-01-01', NULL, 699.00,
    TIMESTAMPTZ '2026-01-01 08:10:00+00',
    TIMESTAMPTZ '2026-01-01 08:10:00+00',
    FALSE
);

INSERT INTO claims (
    claim_id, policy_id, pet_id, claim_type, claim_status, claim_date,
    claim_amount, approved_amount, created_at, updated_at, is_deleted
) VALUES (
    'CLM-10042', 'POL-00001', 'PET-00001', 'ILLNESS', 'PAID', DATE '2026-09-20',
    11200.00, 9700.00,
    TIMESTAMPTZ '2026-09-20 09:00:00+00',
    TIMESTAMPTZ '2026-09-23 19:40:00+00',
    FALSE
);

INSERT INTO claim_payments (
    payment_id, claim_id, payment_date, payment_amount, payment_status,
    created_at, updated_at, is_deleted
) VALUES (
    'PAY-10042-T4', 'CLM-10042', DATE '2026-09-23', 9700.00, 'PAID',
    TIMESTAMPTZ '2026-09-23 19:40:00+00',
    TIMESTAMPTZ '2026-09-23 19:40:00+00',
    FALSE
);

DO $$
DECLARE
    joined_count integer;
BEGIN
    SELECT count(*)
    INTO joined_count
    FROM customers c
    JOIN pets p ON p.customer_id = c.customer_id
    JOIN policies pol ON pol.customer_id = c.customer_id AND pol.pet_id = p.pet_id
    JOIN claims cl ON cl.policy_id = pol.policy_id AND cl.pet_id = p.pet_id
    JOIN claim_payments pay ON pay.claim_id = cl.claim_id
    WHERE c.customer_id = 'CUS-00001'
      AND cl.claim_id = 'CLM-10042'
      AND pay.payment_id = 'PAY-10042-T4';

    IF joined_count <> 1 THEN
        RAISE EXCEPTION 'Expected one complete source relationship chain, found %', joined_count;
    END IF;
END
$$;

DO $$
BEGIN
    BEGIN
        INSERT INTO claims (
            claim_id, policy_id, pet_id, claim_type, claim_status, claim_date,
            claim_amount, approved_amount, created_at, updated_at, is_deleted
        ) VALUES (
            'CLM-19999', 'POL-00001', 'PET-00001', 'ILLNESS', 'APPROVED',
            DATE '2026-09-21', 1000.00, 1200.00,
            TIMESTAMPTZ '2026-09-21 09:00:00+00',
            TIMESTAMPTZ '2026-09-21 09:00:00+00',
            FALSE
        );

        RAISE EXCEPTION 'approved_amount constraint did not reject invalid claim';
    EXCEPTION
        WHEN check_violation THEN
            RAISE NOTICE 'Expected approved_amount <= claim_amount constraint fired.';
    END;
END
$$;

SELECT
    (SELECT count(*) FROM customers) AS customers,
    (SELECT count(*) FROM pets) AS pets,
    (SELECT count(*) FROM policies) AS policies,
    (SELECT count(*) FROM claims) AS claims,
    (SELECT count(*) FROM claim_payments) AS claim_payments;
