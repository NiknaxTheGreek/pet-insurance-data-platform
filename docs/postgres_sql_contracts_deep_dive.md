# PostgreSQL, SQL and source contracts deep dive

This document explains the operational source layer from first principles and then maps each concept to the implementation in this repository.

Use it with:
- [concepts.md](concepts.md) for terminology;
- [engineering_walkthrough.md](engineering_walkthrough.md) for the complete project sequence;
- [ingestion_deep_dive.md](ingestion_deep_dive.md) for what happens after PostgreSQL source data is ready.

Primary implementation files:
- [infra/postgres/init/001_schema.sql](../infra/postgres/init/001_schema.sql)
- [infra/postgres/smoke_test.sql](../infra/postgres/smoke_test.sql)
- [docker-compose.yml](../docker-compose.yml)
- [contracts/](../contracts/)
- [src/insurance_platform/contracts.py](../src/insurance_platform/contracts.py)
- [src/insurance_platform/validate_contracts.py](../src/insurance_platform/validate_contracts.py)
- [tests/test_contracts.py](../tests/test_contracts.py)
- [src/insurance_platform/generate_seed.py](../src/insurance_platform/generate_seed.py)
- [src/insurance_platform/load_seed.py](../src/insurance_platform/load_seed.py)

---

# 1. Why PostgreSQL exists in this architecture

PostgreSQL is the operational source of truth.

That means it represents the current state that an application would use to run the insurance business:

~~~text
customer
→ pet
→ policy
→ claim
→ payment
~~~

This is different from Snowflake.

PostgreSQL is optimized for operational transactions:
- insert a customer;
- update a claim;
- create a payment;
- look up one policy;
- enforce relationships immediately.

Snowflake is optimized for historical analytics across many rows.

The project therefore separates:
- OLTP responsibilities in PostgreSQL;
- analytical/historical responsibilities in Snowflake.

This distinction is fundamental to data engineering.

---

# 2. SQL: language, not product

SQL means Structured Query Language.

SQL is the language used to:
- create tables;
- define constraints;
- insert and update data;
- query rows;
- join related tables;
- aggregate measures.

PostgreSQL is a database management system that implements SQL.

Snowflake also implements SQL, but with different platform-specific syntax and behavior.

So these statements are precise:

~~~text
SQL = language
PostgreSQL = operational relational database
Snowflake = analytical warehouse
dbt = framework that organizes SQL transformations in the warehouse
~~~

---

# 3. The source schema

The source schema is created by:

[001_schema.sql](../infra/postgres/init/001_schema.sql)

The five source tables are:

| Table | One row represents | Primary key |
| --- | --- | --- |
| customers | one customer | customer_id |
| pets | one pet | pet_id |
| policies | one insurance policy | policy_id |
| claims | one insurance claim | claim_id |
| claim_payments | one claim payment | payment_id |

The relational path is:

~~~text
customers
  │
  └── pets
       │
       └── policies
            │
            └── claims
                 │
                 └── claim_payments
~~~

A policy also stores both customer_id and pet_id, which lets the system verify that the insured pet belongs to the expected customer.

A claim stores both policy_id and pet_id, which enables another useful downstream integrity check: the claim pet should match the policy pet.

---

# 4. Primary keys

A primary key uniquely identifies one row.

Examples:

~~~text
customers.customer_id
pets.pet_id
policies.policy_id
claims.claim_id
claim_payments.payment_id
~~~

Why primary keys matter operationally:
- one claim ID cannot exist twice;
- relationships can point to a stable identifier;
- updates can target exactly one record.

Why primary keys matter to ingestion:
- they help identify the business entity;
- they are used as the tie-breaker in the composite watermark;
- they participate in source-version identity.

---

# 5. Foreign keys

A foreign key requires a relationship target to exist.

Examples:

~~~text
pets.customer_id → customers.customer_id

policies.customer_id → customers.customer_id
policies.pet_id      → pets.pet_id

claims.policy_id → policies.policy_id
claims.pet_id    → pets.pet_id

claim_payments.claim_id → claims.claim_id
~~~

If an application tries to create a claim for a nonexistent policy, PostgreSQL can reject it immediately.

This is preferable to discovering that broken relationship days later in a dashboard.

The warehouse still tests relationships independently because source guarantees and analytical guarantees are separate layers of defence.

---

# 6. Data types

The source uses types that reflect business meaning.

Examples:

~~~text
VARCHAR       identifiers and textual attributes
DATE          claim/policy/pet dates
TIMESTAMPTZ   operational timestamps with timezone
NUMERIC       financial values
BOOLEAN       soft-delete flags
~~~

## Why NUMERIC for money?

Financial data should not use binary floating-point when exact decimal behavior is expected.

NUMERIC(12,2) stores decimal amounts such as:

~~~text
11200.00
9700.00
699.00
~~~

without ordinary floating-point approximation issues.

## Why TIMESTAMPTZ?

TIMESTAMPTZ means timestamp with time zone semantics.

The project uses it for created_at and updated_at because ingestion ordering and event timing should be unambiguous across environments.

---

# 7. Source constraints

Constraints encode rules the database can enforce immediately.

Examples from the schema:

## Updated time cannot precede creation

~~~sql
CHECK (updated_at >= created_at)
~~~

## Premium cannot be negative

~~~sql
CHECK (monthly_premium >= 0)
~~~

## Policy end cannot precede start

~~~sql
CHECK (end_date IS NULL OR end_date >= start_date)
~~~

## Claim amount cannot be negative

~~~sql
CHECK (claim_amount >= 0)
~~~

## Approval cannot exceed claim amount

~~~sql
CHECK (
  approved_amount IS NULL
  OR (
      approved_amount >= 0
      AND approved_amount <= claim_amount
  )
)
~~~

## Payment must be positive

~~~sql
CHECK (payment_amount > 0)
~~~

These are source-level invariants.

They protect the operational database before data ever reaches the warehouse.

---

# 8. Accepted business values

The source uses CHECK constraints for bounded business categories.

Examples:

~~~text
species
DOG
CAT

plan_type
ACCIDENT
CORE
COMPREHENSIVE

policy_status
ACTIVE
CANCELLED
LAPSED

claim_type
ACCIDENT
ILLNESS
ROUTINE_CARE

claim_status
SUBMITTED
ASSESSED
APPROVED
REJECTED
PAID
~~~

Why use bounded values?

Without constraints, equivalent or invalid states can creep into data:

~~~text
Paid
PAID
paid
PAIDD
complete
~~~

A controlled vocabulary makes downstream analytics more predictable.

dbt later rechecks accepted values in the warehouse because validation should not depend on a single layer.

---

# 9. The role of updated_at

Every mutable source table contains updated_at.

This field answers:

> When did this current source row last change?

The custom incremental pipeline orders source rows by:

~~~text
(updated_at, primary_key)
~~~

This means updated_at is not merely metadata. It is part of the extraction contract.

Therefore source applications must update it whenever tracked content changes.

A design that depends on updated_at should state this assumption explicitly.

---

# 10. Soft deletes

Every source table contains:

~~~text
is_deleted BOOLEAN NOT NULL DEFAULT FALSE
~~~

A soft delete keeps the row but marks it inactive/deleted.

Example:

~~~text
before:
claim_id = CLM-10043
is_deleted = false

after:
claim_id = CLM-10043
is_deleted = true
updated_at = later timestamp
~~~

Advantages:
- the custom incremental reader can observe deletion state;
- relationships remain inspectable;
- RAW can preserve the deleted version.

Limitation:
- if a row is physically DELETEd, a polling query can no longer see it.

That limitation is why the repository separately proves physical-delete CDC through PostgreSQL WAL and Estuary.

---

# 11. Indexes

The source schema creates indexes on important relationship and change-detection columns.

Examples:

~~~text
pets.customer_id
policies.customer_id
policies.pet_id
claims.policy_id
claims.pet_id
claims.updated_at
claim_payments.claim_id
claim_payments.updated_at
~~~

An index can make selected lookups faster by maintaining an auxiliary search structure.

Trade-off:
- faster reads for indexed access paths;
- extra storage;
- additional write maintenance.

The project does not index every column because indexing everything is not free.

---

# 12. Why Docker is used

[docker-compose.yml](../docker-compose.yml) provides a reproducible local PostgreSQL service.

Without containerization, a reviewer might need to:
- install a specific PostgreSQL version;
- create users;
- create a database;
- apply SQL manually;
- hope local configuration matches the author's machine.

With Docker Compose, the source runtime becomes a project dependency rather than a personal workstation assumption.

The project uses PostgreSQL 16 in a container.

The initialization SQL is mounted so a fresh database starts with the expected schema.

This is reproducibility, not merely convenience.

---

# 13. The source smoke test

[smoke_test.sql](../infra/postgres/smoke_test.sql) proves the relational source actually behaves as expected.

It performs three useful classes of check.

## A. Object existence

It queries information_schema and requires all five source tables to exist.

## B. Valid relationship chain

It inserts:

~~~text
CUS-00001
→ PET-00001
→ POL-00001
→ CLM-10042
→ PAY-10042-T4
~~~

Then it joins across all five tables and requires exactly one complete chain.

That proves more than table creation: it proves the intended key relationships work together.

## C. Invalid claim rejection

It deliberately tries to create:

~~~text
claim amount    1000
approved amount 1200
~~~

The database must raise a check violation.

The test considers that rejection success.

This is an important mindset:

> a deliberately rejected invalid record is a passing integrity test.

---

# 14. information_schema

The source-contract validator inspects PostgreSQL through information_schema.

information_schema is a standard metadata interface exposing database structure.

The validator queries:

~~~text
column_name
data_type
is_nullable
~~~

for the target table.

It separately queries table constraints and key-column metadata to determine the primary key.

This lets the code compare the live database structure with the checked-in contract.

---

# 15. Source contracts

Each YAML file under [contracts/](../contracts/) describes the expected source interface.

Example concepts declared in a contract:

~~~text
version
schema
source_table
primary_key
allow_additive_columns
columns
data_type
nullable
classification
allowed_values
~~~

A contract is different from CREATE TABLE SQL.

The CREATE TABLE statement constructs a database.

The contract says:

> this is the structure the ingestion system agrees to consume.

That makes the dependency explicit.

---

# 16. Data classification

Contracts also classify fields.

Examples from customers.yml:

~~~text
customer_id  → internal_identifier
first_name   → pii_direct
last_name    → pii_direct
email        → pii_direct
phone        → pii_direct
province     → quasi_identifier
postal_code  → quasi_identifier
created_at   → operational
updated_at   → operational
~~~

Other tables use classifications such as:

~~~text
business
financial
operational
internal_identifier
~~~

Why classify data?

Because schema is not only technical shape.

A field's sensitivity affects:
- where it should appear;
- who should consume it;
- whether it belongs in analytical marts;
- what governance tests should exist.

The dbt layer later enforces that direct customer PII does not appear in marts.

---

# 17. Contract loading

Function:

load_contract

File:

[src/insurance_platform/contracts.py](../src/insurance_platform/contracts.py)

Input:

~~~text
path to YAML file
~~~

Behavior:
- open as UTF-8;
- parse YAML;
- require the result to be a mapping/dictionary.

Failure:
- malformed top-level structure raises ValueError.

This is intentionally small.

A configuration file should fail early if its shape is invalid.

---

# 18. Comparing expected and observed metadata

Function:

compare_contract_metadata

Inputs:

~~~text
contract
observed columns
observed primary-key columns
~~~

For every declared column it checks:

~~~text
does the column exist?
does the PostgreSQL type match?
does nullability match?
~~~

It also checks the primary key exactly.

That means a source table cannot silently change from:

~~~text
claim_id primary key
~~~

to some other key without breaking validation.

---

# 19. Additive columns

The contracts set:

~~~text
allow_additive_columns: true
~~~

That means a source table may gain an additional field without immediately breaking ingestion.

Example:

~~~text
submission_channel
~~~

Why allow this?

The RAW design stores the full source payload as JSON/VARIANT, so an extra source field can be preserved even before downstream models use it.

The validator logs additive fields.

This is a practical compatibility policy:

~~~text
new extra column
→ compatible, visible, logged

required column missing
→ breaking

type changes
→ breaking

nullability changes
→ breaking

primary key changes
→ breaking
~~~

---

# 20. Why an additive column is not automatically trusted

Allowing an additive field into RAW does not mean every mart immediately exposes it.

The field still needs:
- business meaning;
- classification;
- transformation design;
- downstream tests;
- intentional publication.

This separates ingestion compatibility from analytical contract design.

That is a useful senior-level distinction.

---

# 21. Contract inspection

Function:

inspect_table_contract

It queries PostgreSQL metadata directly.

First query:

~~~sql
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_schema = ?
  AND table_name = ?
ORDER BY ordinal_position
~~~

Second query identifies primary-key columns through:

~~~text
information_schema.table_constraints
JOIN information_schema.key_column_usage
~~~

Observed metadata is converted into a simple in-memory representation and passed to compare_contract_metadata.

This keeps:
- database inspection;
- comparison logic

separate and testable.

---

# 22. Validating all source contracts

Function:

validate_source_contracts

It:

1. discovers all YAML files in the contract directory;
2. rejects an empty contract directory;
3. loads each contract;
4. inspects the live PostgreSQL table;
5. logs additive fields;
6. logs validation errors;
7. raises once if any contract is invalid;
8. logs a final validation summary when all pass.

The ingestion runner executes this before processing any source table.

Therefore structural incompatibility is detected before normal extraction.

---

# 23. Unit tests for contracts

[tests/test_contracts.py](../tests/test_contracts.py) verifies three essential policies.

## Additive column accepted

Expected columns remain valid while submission_channel appears additionally.

Result:

~~~text
valid
additive_columns = submission_channel
~~~

## Breaking type change rejected

Expected:

~~~text
claim_amount NUMERIC
~~~

Observed:

~~~text
claim_amount TEXT
~~~

Result:

~~~text
invalid
type mismatch
~~~

## Primary key change rejected

Expected:

~~~text
claim_id
~~~

Observed key:

~~~text
policy_id
~~~

Result:

~~~text
invalid
primary-key mismatch
~~~

These tests make the compatibility policy executable rather than merely documented.

---

# 24. Synthetic seed generation

[src/insurance_platform/generate_seed.py](../src/insurance_platform/generate_seed.py) creates reproducible source data.

The generator fixes:

~~~text
SEED = 42
~~~

This means the same input size creates the same logical dataset.

It generates:
- customers;
- one or two pets per customer;
- one policy per generated pet;
- zero to four claims per policy;
- payments for paid claims.

Generated emails use:

~~~text
@example.invalid
~~~

which is intentionally non-real.

The purpose is to create realistic relationships without depending on real customer information.

---

# 25. Referential integrity in generated data

The seed tests verify:

~~~text
every pet customer exists
every policy customer exists
every policy pet exists
every claim policy exists
every claim pet exists
every payment claim exists
~~~

The generator itself is therefore tested.

This matters because test data should not quietly violate the same rules the platform is supposed to demonstrate.

---

# 26. Loading with COPY

[src/insurance_platform/load_seed.py](../src/insurance_platform/load_seed.py) loads generated CSVs in dependency order:

~~~text
customers
pets
policies
claims
claim_payments
~~~

It uses PostgreSQL COPY.

COPY is designed for bulk data transfer and is more efficient than sending one INSERT for every row.

The order matters because parent rows must exist before foreign-key children.

---

# 27. SQL joins: how the business entities connect

A simplified analytical relationship query looks like:

~~~sql
SELECT
    c.customer_id,
    p.pet_id,
    pol.policy_id,
    cl.claim_id,
    pay.payment_id
FROM customers c
JOIN pets p
  ON p.customer_id = c.customer_id
JOIN policies pol
  ON pol.customer_id = c.customer_id
 AND pol.pet_id = p.pet_id
JOIN claims cl
  ON cl.policy_id = pol.policy_id
 AND cl.pet_id = p.pet_id
JOIN claim_payments pay
  ON pay.claim_id = cl.claim_id;
~~~

Each JOIN expresses a relationship between two grains.

A junior engineer should always ask:
- what does one row on the left represent?
- what does one row on the right represent?
- can this join multiply rows?
- should this relationship be one-to-one, one-to-many or many-to-many?

That habit is essential when moving from simple analysis into model engineering.

---

# 28. WHERE, GROUP BY and aggregate thinking

SQL is used differently depending on whether the question concerns:
- individual records;
- filtered records;
- grouped business measures.

Examples:

~~~sql
-- individual current claim
SELECT *
FROM claims
WHERE claim_id = 'CLM-10042';
~~~

~~~sql
-- grouped status counts
SELECT claim_status, COUNT(*)
FROM claims
GROUP BY claim_status;
~~~

~~~sql
-- monetary total
SELECT SUM(claim_amount)
FROM claims;
~~~

The dbt layer builds on exactly these SQL concepts, but makes the transformations reusable and tested.

---

# 29. Transaction semantics in PostgreSQL

A transaction groups multiple changes into one logical unit.

For example, an operational application might need:

~~~text
update claim to PAID
+
insert payment
~~~

If these two actions represent one business event, transactional thinking asks whether partial completion would be acceptable.

The project focuses its explicit atomicity proof in Snowflake ingestion, but understanding source transactions is still foundational.

---

# 30. Why not put every business rule in PostgreSQL?

Some rules belong at the source.

Example:

~~~text
approved_amount <= claim_amount
~~~

The database has enough local information to enforce this immediately.

Other rules are easier to express downstream.

Example:

~~~text
payment_date must not precede the related claim_date
~~~

That crosses table semantics and may belong in analytical quality validation depending on the operational system's ownership boundaries.

The project deliberately demonstrates both:
- database constraints;
- warehouse/dbt tests.

Good engineering is not maximizing one validation layer. It is placing checks where they are useful and independently verifiable.

---

# 31. Source layer competency map

| Skill | Where it appears |
| --- | --- |
| SQL DDL | 001_schema.sql |
| primary/foreign keys | PostgreSQL schema |
| CHECK constraints | PostgreSQL schema |
| types and nullability | PostgreSQL schema + contracts |
| indexes | PostgreSQL schema |
| SQL joins | smoke test + downstream models |
| information_schema | contracts.py |
| schema governance | contracts/*.yml |
| compatibility policy | compare_contract_metadata |
| deterministic data | generate_seed.py |
| bulk load | load_seed.py |
| reproducibility | Docker Compose + Makefile |
| automated source validation | Platform CI PostgreSQL job |

---

# 32. Minimal reproduction

The local source can be reconstructed with:

~~~bash
make bootstrap
make postgres-up
make postgres-wait
make contracts
make postgres-smoke
make postgres-down
~~~

A larger deterministic source can be generated and loaded with:

~~~bash
make postgres-up
make postgres-wait
make seed
make seed-load
~~~

See [reproduction.md](reproduction.md) for the complete repository workflow.

---

# 33. Interview explanation

A concise explanation is:

> PostgreSQL represents the operational source of truth for five related pet-insurance entities. The schema uses primary and foreign keys, typed monetary/date fields, business-value checks, timestamps and soft-delete flags to preserve source integrity. Before ingestion, checked-in YAML contracts are compared with live PostgreSQL metadata through information_schema, allowing compatible additive columns while rejecting breaking type, nullability or primary-key changes. Docker makes the source reproducible, the smoke test proves both a full relationship chain and constraint rejection, and deterministic synthetic data supports repeatable larger-scale testing.

If you can explain why each source constraint exists, how every key relates, and why contracts are separate from CREATE TABLE SQL, you understand the operational foundation rather than only the downstream warehouse.
