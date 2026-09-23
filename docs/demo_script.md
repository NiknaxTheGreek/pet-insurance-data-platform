# Five-minute demo script

This walkthrough is designed for a technical reviewer who wants evidence rather than a slide deck.

## 0:00–0:45 — Problem and architecture

Open the README.

Explain:

- PostgreSQL represents a mutable operational pet-insurance system.
- Python performs incremental capture into append-only Snowflake RAW.
- CONTROL stores watermarks and ingestion audit records.
- dbt turns RAW into typed staging, reusable intermediates and trusted marts.
- GitHub Actions provides CI/CD and Snowflake OIDC authentication.

Point to the Mermaid architecture diagram.

## 0:45–1:45 — Show the claim history

Open `src/insurance_platform/run_ingestion.py` and `dbt/models/intermediate/int_claim_events.sql`.

Use `CLM-10042` as the narrative:

1. SUBMITTED — R8,500.
2. APPROVED — amount revised to R11,200, approved R9,700.
3. PAID — payment R9,700.

Then open the successful `T4 Paid Claim Demo` workflow.

Call out that the first run found one changed claim and one payment, while the immediate replay found zero candidates/inserts.

## 1:45–2:45 — Show failure handling

Open `Reliability Failure Suite`.

Explain the sequence:

1. Insert an invalid payment dated before its claim.
2. Ingest it.
3. dbt test fails with exactly one bad row.
4. Repair it and ingest the new version.
5. Test passes.
6. Insert a claim with an old source timestamp.
7. Normal watermark scan misses it.
8. Reconciliation finds the missing source key and inserts it exactly once.
9. Soft-delete a claim.
10. dbt removes it from the trusted claim fact.
11. Final replay inserts nothing.

This is the strongest reliability proof in the repository.

## 2:45–3:30 — Show modeling and history

Open:

- `dbt/models/marts/fct_claims.sql`
- `dbt/models/marts/dim_customer_scd2.sql`
- `dbt/models/marts/mart_portfolio_performance.sql`

Explain that only one SCD2 was added because the project optimizes for meaningful engineering signals rather than table count.

Mention the verified customer move from Gauteng to Western Cape.

## 3:30–4:15 — Show CI and reproducibility

Open `Platform CI`.

Show the three green jobs:

- Python quality
- PostgreSQL Docker smoke
- Snowflake dbt build

State the verified dbt result:

`PASS=67 WARN=0 ERROR=0 SKIP=0`

The Docker job proves a clean PostgreSQL 16 environment can boot from the checked-in schema and enforce business constraints.

## 4:15–5:00 — Show judgement and performance

Open:

- `docs/adr/`
- `docs/performance_cost.md`

Explain two decisions:

- high-watermark ingestion is paired with reconciliation because late data can violate watermark assumptions
- the dbt claim-event model was changed from max-ID filtering to a backfill-safe anti-join after live evidence exposed missing historical rows

Verified current state:

- 8 RAW claim versions
- 8 modeled claim events
- 0 missing events
- incremental no-op assertion passes
- Snowflake X-Small warehouse, 300-second auto-suspend

Close with the deliberate non-goals: no Kafka/Airflow/Kubernetes/Spark because they are not needed to prove the defined data-engineering capabilities.
