# Architecture and core concepts

This document explains the main ideas used by the pet-insurance data platform and how they fit together.

## 1. System overview

The platform starts with operational insurance data in PostgreSQL and produces tested analytical models in Snowflake.

~~~text
PostgreSQL
→ Python ingestion
→ Snowflake RAW / CONTROL
→ dbt STAGING
→ dbt INTERMEDIATE
→ dbt MARTS
~~~

A second data path captures PostgreSQL change events through the database transaction log:

~~~text
Neon PostgreSQL
→ PostgreSQL WAL / logical replication
→ Estuary Flow
→ Snowflake change history
~~~

GitHub Actions runs the automated checks and live proof workflows. Docker provides a reproducible PostgreSQL environment. Dagster expresses the dependency order of the main data tasks.

### Operational system versus analytical system

The source and warehouse are separated because they solve different problems.

**PostgreSQL** is the operational system. It is designed around transactions such as submitting a claim, updating a policy or recording a payment. This is an OLTP-style workload: many relatively small reads and writes that support the running application.

**Snowflake** is the analytical system. It is used for transformations, history, aggregates and reporting across larger volumes of data. This is an OLAP-style workload.

Running large analytical scans and joins directly against the production PostgreSQL database could make application work compete for CPU, memory, disk I/O and database connections. Moving analytical work to Snowflake isolates those workloads and gives dbt a warehouse designed for transformation and reporting.

## 2. Core technologies

| Term | Meaning here |
| --- | --- |
| SQL | Language used to create, query, join, aggregate and test relational data |
| PostgreSQL | Operational relational database containing customers, pets, policies, claims and payments |
| Python | Reads source changes, builds version identities, stages data and performs reconciliation |
| Snowflake | Analytical warehouse storing historical source versions, ingestion state and analytical models |
| dbt | Organizes SQL transformations, tests, contracts and lineage inside Snowflake |
| Git | Version-control system that records changes to the project |
| GitHub | Hosts the Git repository and runs automation through GitHub Actions |
| Docker | Recreates the PostgreSQL source environment consistently |
| OIDC | Short-lived identity mechanism used by GitHub Actions to authenticate to Snowflake |
| Dagster | Orchestrates dependent data tasks |
| Neon | Managed PostgreSQL used by the log-based change-capture path |
| Estuary Flow | Managed service that reads PostgreSQL change events and materializes them downstream |
| BigQuery | Google Cloud analytical warehouse used for an independent batch/reconciliation proof |

## 3. What CDC means

**CDC stands for Change Data Capture.**

CDC is the process of detecting changes made in a source database and propagating those changes into another system. The important distinction is between the **pattern** and the **tool**: CDC describes what the pipeline is doing; Estuary Flow is the managed product used in this project to implement a log-based CDC path.

CDC is useful because a changing source does not need to be copied in full after every update. At scale, transmitting and processing the relevant changes can reduce source load, data transfer and repeated processing.

For example, a claim may change over time:

~~~text
SUBMITTED
→ APPROVED
→ PAID
~~~

A downstream warehouse should learn about each change instead of seeing only the final row.

Typical database changes are:

~~~text
INSERT  → a new row appears
UPDATE  → an existing row changes
DELETE  → a row is removed
~~~

This project demonstrates two ways to detect change:

**Incremental row scanning**

The Python pipeline reads PostgreSQL rows in the order:

~~~text
(updated_at, primary_key)
~~~

and stores each new source version in Snowflake.

**Log-based capture**

The Estuary path reads PostgreSQL's transaction log through logical replication and captures insert, update and delete events directly.

Both approaches keep downstream data synchronized with a changing source, but they observe changes differently.

## 4. Relational source model

The operational source contains five related entities:

~~~text
customer
  → pet
    → policy
      → claim
        → claim payment
~~~

A **primary key** uniquely identifies a row, such as claim_id.

A **foreign key** connects one table to another, such as:

~~~text
claims.policy_id → policies.policy_id
~~~

A **constraint** enforces a rule directly in the database.

Examples:

~~~text
approved_amount <= claim_amount
monthly_premium >= 0
policy end date >= policy start date
~~~

Each mutable table also stores:

~~~text
created_at
updated_at
is_deleted
~~~

updated_at records when the current row last changed. is_deleted represents a soft delete while keeping the row available for history and relationships.

## 5. Source contracts

The YAML files under contracts/ describe the structure expected by the ingestion process.

They define:
- required columns;
- data types;
- nullability;
- primary key;
- data classification.

Before ingestion, the live PostgreSQL schema is inspected through information_schema.

The compatibility rules are:

~~~text
additive column
→ accepted and logged

required column missing
→ rejected

incompatible type, nullability or primary-key change
→ rejected
~~~

This lets the source evolve in compatible ways while stopping changes that could invalidate the pipeline.

## 6. Incremental ingestion

The Python ingestion process keeps track of its progress with a **watermark**.

The watermark contains:

~~~text
(updated_at, primary_key)
~~~

The timestamp orders changes over time. The primary key breaks ties when multiple records share the same timestamp.

Each extracted row is serialized consistently and hashed with SHA-256.

A source version is identified by:

~~~text
source table
+ source primary key
+ source updated timestamp
+ payload hash
~~~

This makes replay idempotent: processing the same source version again does not create another historical copy.

### Staging and MERGE

Candidate rows are first written to a Snowflake staging table.

Snowflake then performs a set-based MERGE into the RAW history table.

RAW is append-only, so new versions are added while previous versions remain available.

### Transaction boundary

Three pieces of state belong together:

~~~text
RAW version
watermark
successful batch audit
~~~

They are committed in one Snowflake transaction.

If that transaction fails, all three roll back together.

### Reconciliation

A late source record can have an updated_at value older than the current watermark.

Reconciliation scans the current source state and checks whether each complete source-version identity exists in RAW.

Missing versions are inserted without moving the watermark backwards.

The two mechanisms therefore work together:

~~~text
watermark
→ efficient incremental reading

reconciliation
→ recovery of missing current source versions
~~~

## 7. Snowflake layers

Snowflake separates ingestion state from transformation and business-facing analytics:

~~~text
RAW
historical source versions

CONTROL
watermarks, batch audits, staging and ingestion health

STAGING
typed current-state views

INTERMEDIATE
reusable transformations and historical claim events

MARTS
business-facing analytical models
~~~

**RAW is the ingestion boundary.** It keeps source versions close to the form in which they arrived. That source-faithful layer makes it possible to trace a downstream number back to an input, compare transformed data with the ingested record, and rebuild downstream models after transformation logic changes. RAW is therefore useful for auditability and reprocessing, but it is not a substitute for PostgreSQL backup or disaster-recovery procedures.

RAW stores source payloads as Snowflake VARIANT, which can hold parsed JSON.

The dbt layers convert those payloads into typed relational columns. STAGING gives consistent names and types; INTERMEDIATE holds reusable business logic; MARTS expose curated datasets shaped for analysis and reporting.

## 8. dbt and analytical models

dbt is the transformation framework used after ingestion. It does not store the source data itself; it executes version-controlled SQL inside Snowflake, manages model dependencies, and attaches tests and documentation to those models.

The model path is:

~~~text
RAW
→ STAGING
→ INTERMEDIATE
→ MARTS
~~~

A **mart** is a curated analytical dataset intended for a specific business use. It shields analysts and BI tools from source-oriented RAW structures and exposes stable measures and dimensions instead.

**Grain** means what one row represents.

Examples:

~~~text
STG_CLAIMS
→ one current claim

INT_CLAIM_EVENTS
→ one captured claim version

FCT_CLAIMS
→ one current non-deleted claim

DIM_CUSTOMER_SCD2
→ one customer historical version

MART_PORTFOLIO_PERFORMANCE
→ one province × species × plan type
~~~

A **fact table** contains measurable business activity. FCT_CLAIMS contains claim, approved and paid amounts.

A **dimension** supplies descriptive context. DIM_POLICY contains plan, geography and pet attributes.

### SCD Type 2

A Type-2 slowly changing dimension preserves attribute history.

If a customer changes province, the model can retain:

~~~text
Gauteng      → historical version
Western Cape → current version
~~~

using effective_from, effective_to and is_current.

### Data-quality tests

dbt checks rules such as:
- approved amount cannot exceed claim amount;
- payment cannot occur before the claim;
- paid amount cannot exceed approved amount;
- claim pet must match policy pet;
- claim date must fall inside the policy term;
- one current customer-history row must exist;
- direct customer PII must stay out of marts.

## 9. Portfolio metrics

The portfolio mart groups policies and claims by:

~~~text
province × species × plan type
~~~

Measures include:
- policy count;
- active policy count;
- monthly premium book;
- claim count;
- incurred claim amount;
- approved claim amount;
- paid claim amount;
- claims per policy;
- average claim severity.

The paid loss-ratio proxy uses:

~~~text
paid claims
────────────────────────
monthly premium × 12
~~~

The source does not contain earned-premium exposure, so this metric uses annualized current premium as its denominator.

## 10. Automation and security

Git records the project history.

GitHub Actions runs automated verification.

Platform CI checks:

~~~text
Python tests and static checks
→ clean Docker/PostgreSQL source
→ Snowflake/dbt build
~~~

Security checks include:
- Gitleaks for committed secrets;
- pip-audit for known dependency vulnerabilities;
- Ruff static checks;
- shell syntax validation.

Snowflake authentication from GitHub uses OIDC workload identity, which provides a short-lived credential to the workflow.

The Makefile provides repeatable commands such as:

~~~text
make test
make postgres-smoke
make dbt-build
make snowflake-deploy
~~~

## 11. Orchestration

Dagster expresses the main task order:

~~~text
validate source contracts
→ ingest
→ dbt build
→ verify ingestion health
~~~

This allows dependencies and retries to be expressed as one data workflow.

## 12. PostgreSQL WAL and Estuary Flow

**WAL** stands for Write-Ahead Log.

PostgreSQL records committed database changes in this transaction log.

**Logical replication** exposes those changes as row-level events that another system can consume.

A PostgreSQL **publication** defines which tables are available to that replication stream.

The Estuary path uses:
- Neon PostgreSQL with wal_level=logical;
- a direct PostgreSQL endpoint;
- a scoped publication;
- Estuary History Mode.

The verification performs three source operations on a disposable claim:

~~~text
INSERT
UPDATE
DELETE
~~~

The downstream collection and Snowflake history are then checked for one create, one update and one delete event.

Because the DELETE is read from PostgreSQL's log, it can still be captured after the source row has physically disappeared.

## 13. BigQuery proof

The Google Cloud path generates a deterministic claims file and a manifest containing expected row count and aggregate values.

The file is loaded into a typed BigQuery table.

BigQuery results are then compared with the manifest.

This verifies the same general pattern used elsewhere in the project:

~~~text
move data
→ calculate independent expectations
→ reconcile destination results
~~~

A separate GCS-to-Snowflake implementation remains in the repository. Provider-side execution requires a billing-enabled GCP project for bucket creation.

## 14. End-to-end example

For claim CLM-10042:

~~~text
PostgreSQL
SUBMITTED
→ APPROVED
→ PAID
~~~

The Python pipeline captures each new source version in Snowflake RAW.

dbt exposes:
- all captured claim versions in INT_CLAIM_EVENTS;
- the latest current claim in FCT_CLAIMS.

The final fact row contains:

~~~text
claim status     PAID
claim amount     R11,200
approved amount  R9,700
paid amount      R9,700
~~~

An unchanged replay produces no additional source version.

For exact commands see [reproduction.md](reproduction.md). For operational procedures see [runbook.md](runbook.md). Executed results are under [evidence/](evidence/).
