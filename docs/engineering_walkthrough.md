# Engineering walkthrough: analyst to data engineer

This document is the guided implementation path for the repository. It is organized by engineering responsibility rather than by folder so that the project reads as one coherent system.

Use [concepts.md](concepts.md) whenever a technology or engineering term is unfamiliar.

## 1. Start from the analytical question

Before building ingestion, establish what trusted outputs are needed.

The useful business questions are deliberately simple:
- What claims exist now?
- How much was claimed, approved and paid?
- Which policy, pet and customer geography does each claim belong to?
- How does portfolio performance vary by province, species and plan?
- Can customer geography history be reconstructed?

The final analyst-facing models are:
- dbt/models/marts/fct_claims.sql
- dbt/models/marts/dim_policy.sql
- dbt/models/marts/dim_customer_scd2.sql
- dbt/models/marts/mart_portfolio_performance.sql

This is the data-analyst starting point: define grain, measures, dimensions and business rules before adding platform machinery.

Competency demonstrated: SQL reasoning, joins, aggregation, metric definition, grain awareness and data-quality interpretation.

## 2. Model the operational source correctly

Files:
- infra/postgres/init/001_schema.sql
- docker-compose.yml
- infra/postgres/smoke_test.sql

The five entities are:

~~~text
customer
   └── pet
        └── policy
             └── claim
                  └── claim_payment
~~~

The database enforces what it can safely know:
- primary keys are unique;
- foreign keys preserve relationships;
- CHECK constraints limit status and type values;
- monetary amounts cannot violate basic rules;
- timestamps and date ranges must remain valid.

The smoke test creates one complete relationship chain and proves that an invalid approved amount is rejected.

Why this matters: a warehouse should not be expected to repair a fundamentally incoherent operational model. Good engineering begins by understanding source semantics.

Competency demonstrated: relational modeling, PostgreSQL, constraints, indexes, transactions and reproducible local infrastructure.

## 3. Make test data deterministic

Files:
- src/insurance_platform/generate_seed.py
- src/insurance_platform/load_seed.py
- tests/test_seed_data.py

The generator uses a fixed random seed and synthetic identifiers/PII. Re-running it with the same requested size produces the same dataset.

Loading follows referential order:

~~~text
customers → pets → policies → claims → claim_payments
~~~

PostgreSQL COPY is used for bulk loading instead of row-by-row INSERT statements.

Why this matters: deterministic test data makes failures reproducible and lets a reviewer distinguish a code defect from random input variation.

Competency demonstrated: Python data generation, bulk loading, referential integrity and test design.

## 4. Define source contracts before ingestion

Files:
- contracts/*.yml
- src/insurance_platform/contracts.py
- src/insurance_platform/validate_contracts.py
- tests/test_contracts.py

Each contract declares:
- source table;
- primary key;
- required columns;
- expected PostgreSQL data type;
- nullability;
- data classification;
- selected accepted values.

Compatibility policy:
- additive columns are allowed;
- breaking type, nullability and key changes are rejected.

The schema-evolution workflow proves both the compatible and breaking cases.

Why this matters: without a contract, source drift is discovered only after a pipeline or analytical model behaves incorrectly.

Competency demonstrated: schema governance, metadata inspection, compatibility policy and defensive ingestion.

## 5. Create the Snowflake landing and control plane

File:
- infra/snowflake/deploy.sql

Five schemas separate responsibilities:

~~~text
RAW           captured historical source versions
CONTROL       watermarks, batches, stage and health telemetry
STAGING       typed current-state dbt views
INTERMEDIATE  reusable transformations and history
MARTS         trusted analyst-facing tables
~~~

The essential physical ingestion objects are:
- RAW.SOURCE_RECORDS
- CONTROL.INGESTION_WATERMARKS
- CONTROL.INGESTION_BATCHES
- CONTROL.INGESTION_STAGE
- CONTROL.INGESTION_HEALTH

Why this matters: business history and pipeline state are different concerns. Keeping RAW and CONTROL separate makes failure analysis and operations much clearer.

Competency demonstrated: warehouse design, Snowflake SQL, audit metadata and observability.

## 6. Build deterministic source-version identity

File:
- src/insurance_platform/ingestion.py

A source row becomes a ChangeRecord containing:
- source table;
- source primary key;
- source update timestamp;
- operation;
- payload;
- SHA-256 payload hash.

Payload JSON is serialized canonically before hashing so logically identical objects produce the same digest.

A version is identified by:

~~~text
source_table
+ source_pk
+ source_updated_at
+ payload_hash
~~~

Why this matters: timestamp alone cannot prove that two source payloads are identical. The content hash supplies deterministic version identity and replay protection.

Competency demonstrated: Python domain modeling, serialization, hashing and idempotency.

## 7. Read incrementally with a composite watermark

Files:
- src/insurance_platform/ingestion.py
- src/insurance_platform/run_ingestion.py

The fast-path source predicate is conceptually:

~~~sql
WHERE (updated_at, primary_key) > (:last_updated_at, :last_primary_key)
ORDER BY updated_at, primary_key
~~~

The primary key is a deterministic tie-breaker when multiple rows share one timestamp.

The watermark advances only after the corresponding warehouse transaction succeeds.

Why this matters: a timestamp-only predicate can skip rows at timestamp boundaries. A composite ordered cursor is more robust.

Competency demonstrated: incremental extraction, ordered cursors and failure-safe progress tracking.

## 8. Stage first, then use a set-based Snowflake MERGE

File:
- src/insurance_platform/run_ingestion.py

For each source table:

~~~text
read watermark
→ extract candidate rows
→ build ChangeRecords
→ deduplicate exact versions
→ write STARTED batch audit
→ stage candidates
→ MERGE unseen versions into RAW
→ reconcile staged representation
→ advance watermark
→ mark SUCCESS
→ commit
→ clean stage
~~~

Rows are staged in bounded batches, while Snowflake performs a set-based MERGE.

Why this matters: a warehouse is optimized for set operations. The design avoids one warehouse round trip for every source row.

Competency demonstrated: batching, parameter binding, set-based SQL and warehouse-efficient ingestion.

## 9. Make RAW + watermark + success audit atomic

Files:
- src/insurance_platform/run_ingestion.py
- .github/workflows/transaction-atomicity.yml
- docs/evidence/transaction_atomicity.md

The critical transaction boundary is:

~~~text
BEGIN
  MERGE RAW
  update watermark
  mark batch SUCCESS
COMMIT
~~~

An injected failure between RAW MERGE and watermark update proves that the transaction rolls back correctly. The failed attempt remains auditable separately.

Why this matters: if a watermark advances without the data, records can be skipped permanently. Atomicity keeps data and progress state consistent.

Competency demonstrated: transaction design, rollback reasoning and failure injection.

## 10. Add reconciliation because the watermark is optimization, not truth

File:
- src/insurance_platform/reconcile_source_state.py

A late record can legitimately have an updated_at older than the current high watermark. Normal incremental extraction should not move backwards.

Reconciliation scans current source state and asks whether each complete version identity is represented in RAW.

It recovers:
- a new primary key behind the watermark;
- a changed version of an existing key behind the watermark.

Re-running reconciliation is idempotent.

Why this matters:
- watermark = efficient normal path;
- reconciliation = bounded correctness path.

Competency demonstrated: late-arriving data, backfill reasoning, idempotency and source/warehouse reconciliation.

## 11. Transform RAW history with dbt

Files:
- dbt/dbt_project.yml
- dbt/models/staging/
- dbt/models/intermediate/
- dbt/models/marts/
- dbt/tests/

STAGING reconstructs the latest current version for each source key and casts JSON values into typed columns.

INTERMEDIATE contains:
- INT_CLAIM_EVENTS: append-preserving claim history keyed by RAW_RECORD_ID;
- INT_POLICY_CLAIMS: one row per policy with claim/payment rollups.

MARTS expose:
- current claim fact;
- current policy dimension;
- customer Type-2 history;
- portfolio-performance aggregate.

Why this matters: the warehouse can preserve immutable source history while consumers receive stable, typed business models.

Competency demonstrated: advanced SQL, dbt, model layering, facts/dimensions, grain, incremental models and SCD2.

## 12. Encode business rules as executable tests

Directory:
- dbt/tests/

Examples:
- approved amount cannot exceed claim amount;
- payment date cannot precede claim date;
- paid amount cannot exceed approved amount;
- claim pet must match policy pet;
- policy customer must own the insured pet;
- exactly one current SCD2 row must exist per customer;
- direct customer PII must not appear in marts.

Why this matters: a green pipeline proves that code ran. Data tests prove that the resulting data still satisfies business expectations.

Competency demonstrated: data quality, governance and translating domain rules into executable checks.

## 13. Add CI/CD, security and reproducibility

Files:
- .github/workflows/platform-ci.yml
- .github/workflows/security.yml
- requirements/ci.lock.txt
- Makefile

Platform CI verifies:
1. Python static checks and unit tests;
2. clean Docker/PostgreSQL schema and source contracts;
3. Snowflake OIDC, dbt build and trusted output assertions.

Security adds:
- secret scanning;
- dependency audit;
- static checks;
- shell syntax checks.

Why this matters: a repository becomes an engineering system when verification is repeatable by automation rather than dependent on one laptop.

Competency demonstrated: Git/GitHub, CI, dependency management, security gates and reproducibility.

## 14. Express task dependencies with orchestration

Files:
- src/insurance_platform/orchestration.py
- .github/workflows/dagster-proof.yml

Dagster expresses:

~~~text
validate contracts
→ ingest
→ dbt build
→ verify ingestion health
~~~

Retries are attached only where retry is meaningful.

Why this matters: orchestration is introduced after individual tasks are independently correct. It coordinates work; it does not make broken tasks correct.

Competency demonstrated: workflow dependencies, retries and orchestration boundaries.

## 15. Prove true log-based CDC separately

Files:
- src/insurance_platform/estuary_source_readiness.py
- src/insurance_platform/estuary_flow_spec.py
- src/insurance_platform/estuary_cdc_demo.py
- integrations/estuary/
- .github/workflows/estuary-cdc-proof.yml

Path:

~~~text
Neon PostgreSQL
→ logical replication / WAL
→ Estuary Flow
→ Snowflake CDC history
~~~

A disposable claim is inserted, updated and physically deleted. Estuary emits create, update and delete operations, and Snowflake preserves the history.

Why this matters: the custom Python path teaches incremental engineering mechanics. The Estuary path independently proves genuine transaction-log CDC.

Competency demonstrated: PostgreSQL logical replication, managed CDC, source publications and streaming materialization.

## 16. Add a bounded GCP proof

Files:
- integrations/gcp/BIGQUERY_SANDBOX.md
- integrations/gcp/bootstrap_bigquery_sandbox.sh
- src/insurance_platform/gcp_bigquery_sandbox.py

A deterministic claims dataset and manifest are generated, loaded into BigQuery Sandbox and reconciled using independent warehouse aggregates.

Why this matters: the purpose is not to redesign the main architecture around GCP. It demonstrates that typed loading, deterministic input and reconciliation transfer to another cloud data platform.

Competency demonstrated: cloud CLI use, BigQuery, typed batch loading, manifest-based reconciliation and cost awareness.

## 17. Trace one claim end to end

Use CLM-10042.

Business history:

~~~text
SUBMITTED: R8,500
→ APPROVED: claim revised to R11,200; R9,700 approved
→ PAID: R9,700 payment
~~~

Trace:
1. PostgreSQL owns the mutable operational row.
2. Python detects the new source version.
3. Canonical JSON is hashed.
4. The version is staged.
5. Snowflake MERGE inserts the previously unseen RAW version.
6. The watermark and SUCCESS batch state commit atomically.
7. INT_CLAIM_EVENTS retains each historical claim version.
8. STG_CLAIMS reconstructs the latest current state.
9. FCT_CLAIMS exposes the current paid claim with policy, pet and customer context.
10. dbt tests validate monetary and relationship rules.
11. An unchanged replay inserts no duplicate source version.

If you can explain those eleven steps and point to the corresponding files, you understand the core system.

## 18. Competency progression

| Level | What this repository demonstrates |
| --- | --- |
| Data analyst | SQL, joins, aggregation, business metrics, data validation and interpretation |
| Analytics engineer | dbt, model grain, staging/intermediate/marts, tests, contracts, facts/dimensions and SCD2 |
| Data engineer | PostgreSQL source design, incremental ingestion, Snowflake, transactions, idempotency, reconciliation and observability |
| Platform-oriented data engineer | Docker, Git/GitHub, CI/CD, OIDC, orchestration, security gates, WAL CDC and cloud integration |

The transition is not “using more tools.” It is moving from answering questions with existing data to taking responsibility for how trustworthy data is produced, validated and operated.

## 19. Minimal reproduction order

A junior engineer reproducing the design should proceed in this order:

1. create the PostgreSQL schema and constraints;
2. run the source smoke test;
3. generate and load deterministic synthetic data;
4. validate source contracts;
5. deploy Snowflake RAW/CONTROL objects;
6. implement canonical hashing and the composite watermark;
7. implement staged set-based ingestion;
8. make RAW + watermark + success audit atomic;
9. implement full-state reconciliation;
10. build dbt staging, intermediate and marts;
11. add business-rule and governance tests;
12. automate Python/PostgreSQL/Snowflake/dbt verification in CI;
13. add specialist reliability scenarios;
14. add orchestration;
15. prove managed WAL CDC separately;
16. add bounded cloud integration only if it demonstrates a distinct capability.

For exact commands, continue with [reproduction.md](reproduction.md).
