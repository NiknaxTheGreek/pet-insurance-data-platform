# Source contract — v1

## Business problem
A pet insurer needs trustworthy analytics from mutable operational policy and claims data. The platform must preserve source changes, process them incrementally, and expose tested analytical models in Snowflake/dbt.

## Source-system contract
PostgreSQL is the simulated mutable operational source. Five entities are intentionally sufficient for the capability proof. Business identifiers are text keys matching the live demo convention (`CUS-*`, `PET-*`, `POL-*`, `CLM-*`, `PAY-*`) so the Dockerized source, seed generator, live Neon source, ingestion logic, and Snowflake RAW contract use the same identifier shape.

| Entity | Grain | Primary key | Important relationships | Change behaviour |
|---|---|---|---|---|
| customers | one row per customer | customer_id | parent of pets/policies | attributes may update; soft-delete flag |
| pets | one row per insured pet | pet_id | belongs to customer | attributes may update; soft-delete flag |
| policies | one row per pet policy | policy_id | belongs to customer + pet | status/premium may update; soft-delete flag |
| claims | one row per claim | claim_id | belongs to policy + pet | status/amounts develop over time; soft-delete flag |
| claim_payments | one row per payment transaction | payment_id | belongs to claim | payment status may update/reverse; soft-delete flag |

## Change-capture contract
Every mutable table carries `created_at`, `updated_at`, and `is_deleted`. These fields provide the minimal source contract required for the first incremental/CDC implementation. The ingestion design must be idempotent and must not treat `updated_at` alone as proof that an event was processed exactly once.

## Analytical outcome
The eventual mart will support portfolio performance analysis including active policies, premiums, claim counts, incurred/approved amounts, paid amounts, frequency/severity proxies, and loss-ratio-style measures where the premium denominator is defined correctly.

## Explicit non-goals for v1
No ML, fraud model, dashboard, Kafka, Airflow, Kubernetes, multi-product insurance model, or microservice architecture. Complexity must be earned by a required capability.


## Reproducibility contract

The checked-in PostgreSQL DDL is exercised in GitHub Actions with PostgreSQL 16 via Docker Compose. The smoke test boots a clean database, verifies all five tables, inserts one complete customer→pet→policy→claim→payment relationship chain using live-style string IDs, and proves the database rejects an invalid claim where approved amount exceeds claim amount.
