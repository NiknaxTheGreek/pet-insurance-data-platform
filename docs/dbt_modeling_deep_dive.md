# dbt, Snowflake modeling and business SQL deep dive

This document explains how append-only Snowflake RAW history becomes trusted analytical data.

Read it with [concepts.md](concepts.md), [postgres_sql_contracts_deep_dive.md](postgres_sql_contracts_deep_dive.md), and [ingestion_deep_dive.md](ingestion_deep_dive.md).

Primary files:
- [dbt/dbt_project.yml](../dbt/dbt_project.yml)
- [dbt/profiles.yml](../dbt/profiles.yml)
- [dbt/macros/current_raw_records.sql](../dbt/macros/current_raw_records.sql)
- [dbt/models/staging/](../dbt/models/staging/)
- [dbt/models/intermediate/](../dbt/models/intermediate/)
- [dbt/models/marts/](../dbt/models/marts/)
- [dbt/tests/](../dbt/tests/)

# 1. dbt and Snowflake have different jobs

Snowflake is the analytical database and execution engine.

dbt organizes SQL that Snowflake executes.

dbt supplies model dependencies, tests, contracts, documentation, lineage and incremental materialization. It does not extract PostgreSQL data into Snowflake.

The path is:

~~~text
Snowflake RAW
→ dbt STAGING
→ dbt INTERMEDIATE
→ dbt MARTS
~~~

This is ELT: extract, load, then transform inside the warehouse.

# 2. Project configuration

[dbt_project.yml](../dbt/dbt_project.yml) maps model folders to schemas and default materializations.

~~~text
staging      → views
intermediate → views by default
marts        → tables
~~~

INT_CLAIM_EVENTS overrides the intermediate default and is incremental.

Why views for staging? The logic is thin and should remain close to RAW.

Why tables for marts? They are stable consumer-facing outputs.

Why incremental history? Historical claim versions grow over time and do not need a full rebuild on every normal run.

# 3. Snowflake profile

[profiles.yml](../dbt/profiles.yml) defines account, user, role, database, warehouse and schema.

Authentication uses workload identity plus OIDC and a short-lived token.

Threads is set to 4, allowing dbt to execute independent graph nodes concurrently when dependencies permit.

The query tag is pet_insurance_dbt_ci, which makes dbt-originated warehouse activity easier to identify.

# 4. dbt source declaration

[_sources.yml](../dbt/models/staging/_sources.yml) names the external RAW relation:

~~~text
SNOWFLAKE_LEARNING_DB
PET_INSURANCE_RAW
SOURCE_RECORDS
~~~

The source declaration centralizes physical location, lineage, description and source tests.

source() means data entering the dbt graph.

ref() means another dbt-managed model inside the graph.

# 5. Reconstructing current state

[current_raw_records.sql](../dbt/macros/current_raw_records.sql) contains the central current-state window function:

~~~sql
ROW_NUMBER() OVER (
    PARTITION BY source_pk
    ORDER BY source_updated_at DESC,
             raw_record_id DESC
)
~~~

QUALIFY keeps row number 1.

Meaning:

> for each source primary key, return the newest captured source version.

source_updated_at represents source ordering. raw_record_id is a deterministic warehouse-side tie-breaker.

RAW therefore keeps history while staging exposes current state.

# 6. Grain

Grain means what one row represents.

The important grains are:

| Model | Grain |
| --- | --- |
| STG_CUSTOMERS | one current customer |
| STG_PETS | one current pet |
| STG_POLICIES | one current policy |
| STG_CLAIMS | one current claim |
| STG_CLAIM_PAYMENTS | one current payment |
| INT_CLAIM_EVENTS | one captured claim version |
| INT_POLICY_CLAIMS | one current policy |
| DIM_POLICY | one current policy |
| FCT_CLAIMS | one current non-deleted claim |
| DIM_CUSTOMER_SCD2 | one customer historical version |
| MART_PORTFOLIO_PERFORMANCE | one province × species × plan type |

A large share of analytical defects are grain defects. Before joining models, ask whether one side can contain multiple rows for the join key.

# 7. Staging models

The staging models use current_raw_records and convert semi-structured RAW payloads into typed columns.

[stg_customers.sql](../dbt/models/staging/stg_customers.sql) exposes current customer state. Direct PII remains in restricted staging because this layer reconstructs operational state, but those fields are not published into analytics marts.

[stg_pets.sql](../dbt/models/staging/stg_pets.sql) converts pet identity, ownership, species, breed and date of birth.

[stg_policies.sql](../dbt/models/staging/stg_policies.sql) converts policy dates and monthly premium to warehouse types.

[stg_claims.sql](../dbt/models/staging/stg_claims.sql) converts claim dates and monetary values and exposes only the current claim version.

[stg_claim_payments.sql](../dbt/models/staging/stg_claim_payments.sql) converts payment dates, amounts and status.

TRY_TO_DATE, TRY_TO_TIMESTAMP_TZ and TRY_TO_DECIMAL make parsing explicit. Tests still determine whether required outputs may be null.

# 8. Why staging is intentionally boring

Staging should mostly:
- select the correct source version;
- rename fields;
- cast types;
- normalize flags;
- retain useful source metadata.

Complex business metrics do not belong here because they would be duplicated across consumers and make source-standardization logic harder to reason about.

# 9. Staging tests

[_staging.yml](../dbt/models/staging/_staging.yml) uses generic tests:

~~~text
not_null
unique
relationships
accepted_values
~~~

Examples:
- pet.customer_id must reference a customer;
- claim.policy_id must reference a policy;
- payment.claim_id must reference a claim;
- species must be DOG or CAT;
- claim status must use the defined lifecycle values.

These are structural warehouse expectations.

# 10. Intermediate models

Intermediate models contain reusable business logic that should exist once but is not yet the final consumer interface.

This project has:
- INT_CLAIM_EVENTS for captured claim history;
- INT_POLICY_CLAIMS for policy-grain claim/payment measures.

# 11. INT_CLAIM_EVENTS

[int_claim_events.sql](../dbt/models/intermediate/int_claim_events.sql) reads every RAW claim version, not only the current one.

Its grain is one row per RAW claim event/version.

It carries:
- RAW_RECORD_ID;
- claim ID;
- source timestamp;
- operation;
- policy and pet IDs;
- claim type/status;
- claim and approved amounts;
- delete state;
- batch ID;
- ingestion timestamp.

For CLM-10042 this model preserves SUBMITTED, APPROVED and PAID.

# 12. Incremental claim history

INT_CLAIM_EVENTS uses:
- incremental materialization;
- RAW_RECORD_ID as the unique key;
- merge strategy;
- sync_all_columns on schema change.

On an incremental run, it uses an anti-join against already materialized RAW_RECORD_ID values.

The question is:

> Is this exact RAW event already present in the history model?

This is stronger than filtering only above the current maximum ID because an older missing RAW event can still be inserted later.

That makes the model backfill-safe for missing events.

# 13. INT_POLICY_CLAIMS

[int_policy_claims.sql](../dbt/models/intermediate/int_policy_claims.sql) has one row per current non-deleted policy.

It builds:
- current policies;
- current claims;
- paid/settled payments aggregated by claim;
- claim measures aggregated by policy.

Measures include:

~~~text
claim_count
incurred_claim_amount
approved_claim_amount
paid_claim_amount
~~~

The final join from policy to claim rollup is a LEFT JOIN.

That is important because policies with no claims must still exist with zero claim measures.

An INNER JOIN would incorrectly remove claim-free policies.

# 14. INNER JOIN and LEFT JOIN

INNER JOIN keeps rows with matches on both sides.

LEFT JOIN keeps every left-side row and adds matching right-side values when available.

Examples in this project:

~~~text
policy → required customer/pet context
INNER JOIN

policy → optional claim rollup
LEFT JOIN

claim → optional payment aggregate
LEFT JOIN
~~~

Choosing join type is a business decision, not merely SQL syntax.

# 15. DIM_POLICY

[dim_policy.sql](../dbt/models/marts/dim_policy.sql) has one row per current non-deleted policy.

It enriches policies with:
- province;
- pet name;
- species;
- breed.

It exposes customer_id as an internal identifier but excludes direct customer name, email and phone.

A dimension gives descriptive context for filtering and grouping facts.

# 16. FCT_CLAIMS

[fct_claims.sql](../dbt/models/marts/fct_claims.sql) is the central fact table.

Grain:

~~~text
one current non-deleted claim
~~~

Before payments are joined, payment rows are aggregated by claim.

The aggregate supplies:

~~~text
paid_amount
latest_payment_date
~~~

Why aggregate first?

A claim can have multiple payment rows. Joining raw payments directly would duplicate the claim fact and could double-count claim measures.

The correct sequence is:

~~~text
many payment rows
→ aggregate to one row per claim
→ join to one-row-per-claim fact
~~~

This is grain alignment.


# 17. Fact versus dimension

A fact represents measurable business activity.

FCT_CLAIMS contains measures such as:
- claim_amount;
- approved_amount;
- paid_amount.

A dimension provides descriptive context.

DIM_POLICY contributes:
- province;
- plan type;
- species;
- breed.

This lets analysts aggregate measurable claims by useful business categories.

# 18. DIM_CUSTOMER_SCD2

[dim_customer_scd2.sql](../dbt/models/marts/dim_customer_scd2.sql) has one row per customer historical version.

It reads all RAW customer versions.

LEAD(source_updated_at) over each customer determines when the next captured version begins.

Conceptually:

~~~text
version A:
effective_from = timestamp A
effective_to   = timestamp B
is_current     = false

version B:
effective_from = timestamp B
effective_to   = null
is_current     = true
~~~

This is Type-2 slowly changing dimension logic.

# 19. Why SCD2 matters

An overwrite dimension would only retain the latest province.

SCD2 can retain:

~~~text
CUS-00001 | Gauteng      | A → B | historical
CUS-00001 | Western Cape | B → ∞ | current
~~~

The purpose is historical attribute state, not merely current lookup.

# 20. Portfolio mart

[mart_portfolio_performance.sql](../dbt/models/marts/mart_portfolio_performance.sql) has grain:

~~~text
province × species × plan_type
~~~

It begins from one-row-per-policy INT_POLICY_CLAIMS, then enriches with current customer province and pet species.

It computes:
- policy count;
- active policy count;
- monthly premium book;
- annualized premium proxy;
- claim count;
- incurred claims;
- approved claims;
- paid claims;
- claims per policy;
- average claim severity;
- paid loss-ratio proxy.

# 21. Why upstream grain makes COUNT correct

policy_metrics contains one row per policy.

Therefore:

~~~sql
COUNT(*)
~~~

is a valid policy count.

If the upstream model had multiple rows per policy, this measure would be inflated.

Correct metrics depend on correct grain before aggregation.

# 22. claims_per_policy

Conceptually:

~~~text
total current claim count
─────────────────────────
policy count
~~~

This is a simple frequency-like portfolio metric.

It is not exposure-adjusted actuarial frequency because the bounded source does not contain full exposure measures.

# 23. average claim severity

Conceptually:

~~~text
incurred claim amount
─────────────────────
claim count
~~~

NULLIF prevents division by zero.

This is an example of defensive analytical SQL.

# 24. paid loss-ratio proxy

Conceptually:

~~~text
paid claims
────────────────────────────
current monthly premium × 12
~~~

The name deliberately includes proxy.

A production actuarial loss ratio normally requires earned premium aligned to the loss period and may use different loss definitions.

The source does not contain earned-premium exposure history.

The project therefore states the limitation instead of overstating the metric.

# 25. Model contracts

[_marts.yml](../dbt/models/marts/_marts.yml) enables enforced contracts for marts.

Contracts declare the output interface:
- column names;
- data types;
- selected generic tests.

Examples:

~~~text
claim_amount → NUMBER(18,2)
claim_date   → DATE
is_current   → BOOLEAN
~~~

An enforced contract makes the analytical interface executable rather than informal.

# 26. Generic tests and singular tests

Generic tests are reusable YAML declarations:

~~~text
not_null
unique
relationships
accepted_values
~~~

Singular tests are SQL queries under dbt/tests.

A singular test returns rows that violate a rule.

Semantics:

~~~text
zero violating rows → PASS
one or more rows    → FAIL
~~~

# 27. Approved amount rule

[assert_approved_amount_not_over_claim.sql](../dbt/tests/assert_approved_amount_not_over_claim.sql) returns claims where approved amount exceeds claim amount.

The source database also has a similar constraint.

Rechecking downstream gives independent defence after data movement and transformation.

# 28. Claim pet must match policy pet

[assert_claim_pet_matches_policy.sql](../dbt/tests/assert_claim_pet_matches_policy.sql) checks:

~~~text
claim.pet_id = policy.pet_id
~~~

Both IDs could independently reference valid pets while still disagreeing.

This illustrates semantic integrity beyond ordinary foreign keys.

# 29. Claim date must fall within policy term

[assert_claim_within_policy_term.sql](../dbt/tests/assert_claim_within_policy_term.sql) finds claims before policy start or after a non-null policy end date.

This is a cross-entity business rule.

# 30. Payment cannot precede claim

[assert_payment_not_before_claim.sql](../dbt/tests/assert_payment_not_before_claim.sql) finds:

~~~text
payment_date < claim_date
~~~

The reliability suite deliberately creates this invalid condition, confirms dbt fails, repairs it, then confirms the test passes.

The expected failure is the successful verification.

# 31. Paid amount cannot exceed approval

[assert_payments_not_over_approved.sql](../dbt/tests/assert_payments_not_over_approved.sql) first aggregates payments per claim, then finds:

~~~text
paid_amount > approved_amount
~~~

This catches cases where multiple individually valid payments exceed the approved total collectively.

# 32. Policy customer must own the insured pet

[assert_policy_pet_customer_alignment.sql](../dbt/tests/assert_policy_pet_customer_alignment.sql) compares:

~~~text
policy.customer_id
pet.customer_id
~~~

Again, each foreign key could be valid independently while the combined business relationship is wrong.

# 33. SCD2 quality rules

[assert_one_current_customer_scd2.sql](../dbt/tests/assert_one_current_customer_scd2.sql) requires exactly one current version per customer.

[assert_customer_scd2_valid_ranges.sql](../dbt/tests/assert_customer_scd2_valid_ranges.sql) rejects effective_to earlier than effective_from.

These tests protect temporal consistency.

# 34. PII boundary

[assert_no_direct_pii_in_marts.sql](../dbt/tests/assert_no_direct_pii_in_marts.sql) inspects Snowflake information_schema.

It fails if mart columns include names such as:
- FIRST_NAME;
- LAST_NAME;
- EMAIL;
- PHONE;
- STREET_ADDRESS.

This turns a governance rule into an executable warehouse test.

# 35. dbt build lifecycle

Useful commands:

~~~bash
dbt debug --project-dir dbt --profiles-dir dbt
dbt build --project-dir dbt --profiles-dir dbt --fail-fast
dbt docs generate --project-dir dbt --profiles-dir dbt
~~~

dbt debug validates configuration and connection.

dbt build executes models and tests in dependency order.

dbt docs generate writes graph/catalog documentation artifacts.

Verified result:

~~~text
11 models
67 tests
78 total build nodes
78 / 78 passed
~~~

# 36. CLM-10042 across model layers

RAW preserves captured claim versions.

INT_CLAIM_EVENTS exposes:

~~~text
SUBMITTED
APPROVED
PAID
~~~

STG_CLAIMS selects the newest claim version.

FCT_CLAIMS joins the current claim with policy/pet/customer context and aggregated payments.

Verified final state:

~~~text
claim_id         CLM-10042
claim_status     PAID
claim_amount     11200
approved_amount  9700
paid_amount      9700
~~~

History and current truth are therefore separate products of the same append-only RAW source.

# 37. Analyst to analytics engineer

An analyst may ask:

~~~text
How much was paid by province?
~~~

An analytics engineer also asks:
- what is the model grain?
- can this join multiply rows?
- is province current or historical?
- are deleted records excluded?
- are payment rows aggregated first?
- what tests protect the metric?
- what types and contracts do consumers receive?
- does the source actually support the business interpretation?

The move into analytics engineering is about making analytical correctness reusable.

# 38. Trade-offs

Views for staging:
- advantage: simple and low duplication;
- trade-off: compute happens when queried.

Tables for marts:
- advantage: stable consumer performance;
- trade-off: storage and rebuild work.

Incremental history:
- advantage: avoids rebuilding all captured history;
- trade-off: requires careful uniqueness and backfill logic.

SCD2 from RAW:
- advantage: uses history already captured;
- trade-off: depends on captured source versions and currently tracks a deliberately bounded customer attribute set.

# 39. Competency map

| Skill | Evidence |
| --- | --- |
| SELECT, JOIN, GROUP BY | model SQL |
| grain control | all documented models |
| window functions | current state + SCD2 |
| CTEs | intermediate and marts |
| aggregation | policy and portfolio models |
| NULL handling | COALESCE and NULLIF |
| type casting | staging and marts |
| ref/source | dbt dependency graph |
| incremental modeling | INT_CLAIM_EVENTS |
| facts/dimensions | FCT_CLAIMS / DIM_POLICY |
| SCD2 | DIM_CUSTOMER_SCD2 |
| contracts | mart YAML |
| structural tests | model YAML |
| business tests | dbt/tests |
| governance | PII test |
| domain restraint | paid_loss_ratio_proxy |

# 40. Interview explanation

> dbt transforms append-only Snowflake RAW into typed and tested analytical models. A reusable window-function macro reconstructs current state for each source key in staging. INT_CLAIM_EVENTS separately preserves every captured claim version and incrementally anti-joins on RAW_RECORD_ID so older missing events remain recoverable. INT_POLICY_CLAIMS aligns claim and payment measures to one-policy grain. The marts publish a current claim fact, enriched policy dimension, customer SCD2 and portfolio aggregate. Enforced contracts fix the mart interfaces, while generic and singular SQL tests validate relationships, monetary limits, policy timing, temporal history and the no-direct-PII boundary. The loss-ratio field is explicitly a proxy because the source does not contain earned-premium exposure.

If you can state the grain of every model and explain why each join does or does not multiply rows, you understand the analytical layer at an engineering level.
