# dbt modeling layer

## Purpose

dbt (data build tool) manages SQL transformations, tests, contracts and lineage **inside** the Snowflake warehouse. Snowflake stores and executes the analytical data; dbt defines how RAW data becomes trusted analytical models. dbt does not perform the PostgreSQL → Snowflake extraction.

For definitions of dbt, Snowflake, materializations, grain, facts, dimensions and SCD Type 2, see [concepts.md](concepts.md).

The dbt layer converts append-only source history in Snowflake RAW into typed current-state models, reusable intermediate logic, historical event models, and business-facing marts.

## Layering

### STAGING

Five views reconstruct current state from `PET_INSURANCE_RAW.SOURCE_RECORDS` using the reusable `current_raw_records` macro.

- `stg_customers`
- `stg_pets`
- `stg_policies`
- `stg_claims`
- `stg_claim_payments`

Current state is chosen with:

`row_number() over (partition by source_pk order by source_updated_at desc, raw_record_id desc) = 1`

The models type JSON/VARIANT payload values into Snowflake dates, timestamps, decimals, booleans, and strings while retaining source metadata.

### INTERMEDIATE

`int_claim_events` is an incremental model keyed by `raw_record_id`. On incremental runs it uses an explicit `NOT EXISTS` anti-join against already materialized RAW_RECORD_ID values, so a previously missing older event can still be inserted. This gives a dbt-level incremental example without assuming that MAX(raw_record_id) alone proves completeness.

`int_policy_claims` reduces current claims and payments to one row per policy with:
- claim count
- incurred claim amount
- approved claim amount
- paid claim amount

### MARTS

`dim_policy` enriches current policies with customer and pet attributes.

`fct_claims` is the trusted current claim fact with policy/customer/pet context and aggregated payment information.

`dim_customer_scd2` derives Type-2 customer history from every append-only RAW customer version. Verified demo state for `CUS-00001`:

| Province | Effective from | Effective to | Current |
| --- | --- | --- | --- |
| Gauteng | 2026-01-01 08:00Z | 2026-09-23 20:10Z | false |
| Western Cape | 2026-09-23 20:10Z | null | true |

`mart_portfolio_performance` groups the current portfolio by province, species, and plan type and exposes policy count, active policies, premium proxy, claim count, incurred/approved/paid claims, claim frequency, average severity, and a paid loss-ratio proxy.

The loss-ratio field is deliberately named `paid_loss_ratio_proxy`: current monthly premium × 12 is used as an annualized premium proxy because the demo source does not contain actuarial earned-premium exposure. It must not be represented as a production actuarial loss ratio.

## Data quality

The dbt project tests:
- source RAW identifiers and CDC metadata
- model primary-key uniqueness/not-null rules
- source relationships across customer, pet, policy, claim, and payment entities
- approved amount <= claim amount
- payment date >= claim date
- exactly one current SCD2 row per customer
- valid SCD2 effective-date ranges

Verified CI build:
- 11 models
- 67 tests
- 78 total dbt build nodes
- PASS=78
- WARN=0
- ERROR=0
- SKIP=0

## Verified business output

`FCT_CLAIMS` for `CLM-10042`:

- status: `PAID`
- claim amount: R11,200
- approved amount: R9,700
- paid amount: R9,700

`INT_CLAIM_EVENTS` preserves:
`SUBMITTED → APPROVED → PAID`

## Authentication

CI uses GitHub Actions OIDC → Snowflake workload identity federation. `dbt-snowflake 1.12.1` is pinned because that released adapter supports the required `workload_identity` / `OIDC` profile parameters.
