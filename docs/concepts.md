# Core concepts and technology glossary

This guide defines the technologies and engineering ideas used in this repository in the context in which they are actually used. It is written so that someone moving from data analysis into data engineering can learn the system without reducing the technical precision expected by a senior reviewer.

A useful one-line map is:

SQL expresses data logic; PostgreSQL owns operational state; Python moves and reconciles changes; Snowflake stores warehouse history and analytics; dbt transforms and tests warehouse data; Git records code history; GitHub hosts the repository and runs automation; Neon and Estuary provide a separate log-based CDC proof.

## 1. Roles represented by the project

### Data analyst
A data analyst turns existing data into answers through querying, validation, aggregation, visualization and interpretation. In this project the analyst-facing outputs are the trusted marts, especially FCT_CLAIMS and MART_PORTFOLIO_PERFORMANCE.

### Analytics engineer
An analytics engineer sits between analysis and platform engineering. The emphasis is warehouse modeling, reusable SQL transformations, testing, lineage and business semantics. The dbt layer is the clearest example here.

### Data engineer
A data engineer takes responsibility for how trustworthy data is produced and operated: source integration, ingestion, storage, schema management, reliability, security, orchestration and observability. The PostgreSQL source, Python ingestion, Snowflake RAW/CONTROL layers, reconciliation, CI/CD and CDC integrations demonstrate those responsibilities.

## 2. Relational and SQL foundations

### Database
A database is an organized persistent data store managed by a database management system. PostgreSQL is the operational database in this project; Snowflake is the analytical warehouse.

### Relational database
A relational database stores data in tables with defined columns and relationships. Rows represent records, columns represent attributes, and keys connect entities. The source model uses customers, pets, policies, claims and claim payments.

### SQL
SQL means Structured Query Language. It is the language used to define, query and transform relational data. SQL is not a database product. PostgreSQL, Snowflake and BigQuery all use SQL, but each has its own dialect and platform behavior.

This project uses SQL to define schemas and constraints, query source data, transform warehouse data through dbt, test business rules and reconcile results.

### PostgreSQL
PostgreSQL is an open-source relational database management system. Here it represents the operational source of truth: the application-style system in which customers, pets, policies, claims and payments are created and updated.

### OLTP
OLTP means online transaction processing. It describes systems optimized for frequent small transactions such as inserts, updates and point lookups. The PostgreSQL source is OLTP-style.

### Primary key
A primary key uniquely identifies a row. Examples are claim_id and policy_id. Primary keys also provide deterministic ordering when used with updated_at in the composite ingestion watermark.

### Foreign key
A foreign key requires a value to reference an existing row in another table. For example, claims.policy_id references policies.policy_id. Foreign keys protect relationship integrity at the source.

### Constraint
A constraint is a database-enforced rule. Examples include approved_amount <= claim_amount, non-negative premiums and valid date ranges.

### Index
An index is an auxiliary structure that speeds selected lookups at the cost of storage and write overhead. The source indexes relationship keys and updated_at columns used by ingestion.

### Transaction and ACID
A transaction groups database changes into one unit of work. ACID is shorthand for atomicity, consistency, isolation and durability.

The critical property here is atomicity: RAW insertion, watermark advancement and the SUCCESS audit either all commit or all roll back. That prevents warehouse data and ingestion progress from disagreeing.

## 3. Warehousing and modeling

### Data warehouse
A data warehouse is an analytical store optimized for history, transformation, aggregation and reporting rather than application transactions.

### Snowflake
Snowflake is a cloud data platform with a SQL analytical engine and independent compute warehouses. In this project it stores append-only source history, ingestion control state, dbt transformations and trusted analytical marts.

### Database, schema and table in Snowflake
A Snowflake database is a top-level logical container. A schema groups related objects inside it. A table stores rows.

The project separates responsibilities through schemas:
- PET_INSURANCE_RAW: captured source versions;
- PET_INSURANCE_CONTROL: watermarks, batches and health telemetry;
- PET_INSURANCE_STAGING: typed current-state views;
- PET_INSURANCE_INTERMEDIATE: reusable logic and history;
- PET_INSURANCE_MARTS: analyst-facing models.

The word schema is overloaded: it can mean a Snowflake namespace or the structural definition of a dataset. Context determines the meaning.

### JSON and VARIANT
JSON is a text format for nested key/value data. Snowflake VARIANT is a semi-structured type that stores parsed JSON.

RAW stores each source row as a VARIANT payload so source history can be retained without flattening every source column immediately. dbt staging later converts the payload into typed columns.

### ETL and ELT
ETL means extract, transform, load. ELT means extract, load, transform.

This project is primarily ELT:
1. extract source changes from PostgreSQL;
2. load historical versions into Snowflake RAW;
3. transform them inside Snowflake with dbt.

### dbt
dbt, data build tool, manages SQL transformations inside a warehouse. It does not replace PostgreSQL, Snowflake or the Python ingestion layer, and it does not perform the source-to-Snowflake extraction.

dbt provides SQL models, dependency management, tests, contracts, documentation, lineage and incremental materializations.

### dbt model
A dbt model is normally a SQL SELECT statement that dbt materializes as a view, table or incremental table. The file name becomes the model name.

### Materialization
A materialization defines how a model is persisted:
- view: stores query logic and computes results when queried;
- table: stores query results physically;
- incremental: updates only the required subset after the initial build.

### STAGING
STAGING reconstructs clean current source state, names fields, casts data types and normalizes flags. It deliberately contains little business logic.

### INTERMEDIATE
INTERMEDIATE contains reusable transformation logic that is not yet the final analyst interface. Here it includes claim history and policy-level claim/payment rollups.

### MART
A mart is a curated dataset intended for analytical consumption. The project exposes a claims fact, policy dimension, customer-history dimension and portfolio-performance mart.

### Grain
Grain answers: what does one row represent?

Examples:
- STG_CLAIMS: one row per current claim;
- INT_CLAIM_EVENTS: one row per captured claim version;
- FCT_CLAIMS: one row per current non-deleted analytical claim;
- DIM_CUSTOMER_SCD2: one row per customer historical version;
- MART_PORTFOLIO_PERFORMANCE: one row per province × species × plan type.

Grain should be defined before writing joins or aggregations because many data errors are actually grain errors.

### Fact table
A fact table represents measurable business events or observations. FCT_CLAIMS is the central fact because a claim is an event with monetary measures such as claim, approved and paid amounts.

### Dimension table
A dimension supplies descriptive context used to group, filter or enrich facts. DIM_POLICY supplies policy, customer-geography and pet context.

### SCD Type 2
SCD means slowly changing dimension. Type 2 preserves attribute history by creating a new version rather than overwriting the old one. DIM_CUSTOMER_SCD2 keeps historical province versions with effective_from, effective_to and is_current.

## 4. Ingestion and reliability

### Data pipeline
A data pipeline is a repeatable sequence that moves or transforms data between systems. The main path is PostgreSQL → Python → Snowflake → dbt.

### Batch processing
Batch processing handles bounded groups of records rather than every source event continuously. The custom Python path is batch-oriented incremental ingestion.

### CDC
CDC means change data capture: identifying inserts, updates and deletes so downstream systems can reproduce source changes.

This repository demonstrates two approaches:
- custom incremental capture using updated_at + primary key plus reconciliation;
- true log-based CDC using PostgreSQL WAL through Estuary.

The Python path should not be described as WAL CDC.

### WAL
WAL means write-ahead log. PostgreSQL records database changes in its transaction log before applying them to data pages. Logical replication can expose those changes as a stream suitable for CDC.

### Logical replication
Logical replication exposes row-level logical changes from PostgreSQL. The Estuary proof uses it to observe create, update and physical-delete events.

### Watermark
A watermark records how far an incremental reader has safely progressed through a source.

### Composite watermark
A composite watermark uses more than one ordering field. This project uses (updated_at, primary_key), not timestamp alone. The primary key deterministically orders rows sharing a timestamp.

### Canonical serialization
Canonical serialization converts equivalent structured data into one deterministic representation. The ingestion sorts JSON keys and normalizes values before hashing so key order does not create false changes.

### SHA-256 and payload hash
SHA-256 is a cryptographic hash function that maps input data to a fixed 256-bit digest. The project hashes canonical payload JSON to create a stable content fingerprint. The hash supports version identity and replay protection; it is not used for password storage.

### Idempotency
An operation is idempotent when repeating it produces the same final state as running it once. Replaying an unchanged source version inserts no duplicate RAW version.

### MERGE
MERGE is a set-based SQL operation that compares a source set with a target and conditionally inserts or updates rows. The ingestion uses one Snowflake MERGE per source table rather than one warehouse statement per record.

### Reconciliation
Reconciliation compares independent source and destination expectations to prove completeness.

The custom pipeline performs source-state reconciliation to recover versions behind the high watermark. The GCP proof compares manifest aggregates with BigQuery aggregates.

### Soft delete
A soft delete marks a record as deleted, usually with is_deleted=true, without physically removing it. RAW preserves the delete state while current marts exclude deleted business records.

### Data contract
A data contract is an executable agreement about a dataset's expected structure and semantics. Source contracts here define required columns, types, nullability, primary keys, classifications and selected accepted values.

### Schema evolution
Schema evolution is structural change over time. The project's policy allows compatible additive columns but rejects breaking type, nullability or key changes.

### Observability
Observability is the ability to determine system state from telemetry. INGESTION_BATCHES and INGESTION_HEALTH expose status, row counts, duration, retries, watermarks and errors.

## 5. Version control, automation and delivery

### Git
Git is a distributed version-control system. It records file changes as commits, supports branches and makes development history reproducible.

### Repository
A Git repository is the version-controlled project: code, SQL, configuration, tests, documentation and their history.

### Commit
A commit is a snapshot of repository changes with a parent and message. Coherent commits make technical changes reviewable.

### Branch
A branch is a movable reference to a sequence of commits. main is the active review branch; submission-final-2026-09-25 is the frozen reviewer checkpoint.

### GitHub
GitHub hosts Git repositories and adds collaboration and automation services. Git and GitHub are not the same thing: Git is the version-control system; GitHub is a hosting and automation platform built around Git.

### CI/CD
CI means continuous integration: automatically validating changes through tests and checks. CD commonly means continuous delivery or deployment: making validated changes releasable or deploying them automatically.

This project is strongest on CI and controlled workflow execution.

### GitHub Actions
GitHub Actions is GitHub's workflow automation service. YAML files under .github/workflows define jobs that run on GitHub-hosted runners.

### Docker
Docker packages software and runtime dependencies into containers. The project uses a PostgreSQL container so a clean source system can be reproduced consistently.

### Docker Compose
Docker Compose defines and starts related containers from one configuration. Here it provides the local PostgreSQL service, initialization and health checks.

### OIDC and workload identity
OIDC means OpenID Connect. It is an identity protocol based on signed tokens. Workload identity lets automation use short-lived identity instead of a long-lived password or private key.

GitHub Actions authenticates to Snowflake using OIDC, reducing static-secret exposure.

### Orchestration
Orchestration coordinates dependent tasks, retries and execution order across a data workflow.

### Dagster
Dagster is a data orchestrator. Here it expresses: validate contracts → ingest → dbt build → verify health. The project demonstrates orchestration without requiring a permanent Dagster service.

## 6. Managed services and cloud integrations

### Neon
Neon is a managed/serverless PostgreSQL service. The project uses Neon as the PostgreSQL source for the real logical-replication/WAL CDC proof.

### Estuary Flow
Estuary Flow is a managed data-integration and streaming platform. Here it reads PostgreSQL logical-replication changes from Neon and materializes the resulting history into Snowflake.

### Google Cloud Platform
Google Cloud Platform, or GCP, is Google's cloud platform. The repository contains a bounded GCP capability proof and a separate production-style object-storage extension.

### BigQuery
BigQuery is Google's managed analytical warehouse. BigQuery Sandbox provides a limited no-billing execution path. The project loads a deterministic typed claims dataset and reconciles it using GoogleSQL.

### Google Cloud Storage
Google Cloud Storage, or GCS, is object storage for files and blobs. The repository retains a production-style GCS → Snowflake backfill design, separate from the verified BigQuery Sandbox proof.

### Workload Identity Federation
GCP Workload Identity Federation, or WIF, lets an external identity such as GitHub Actions exchange an OIDC token for short-lived Google Cloud credentials without storing a service-account key.

## 7. How the concepts fit together

~~~text
Operational application concepts
PostgreSQL + SQL + keys + constraints + transactions
                         ↓
Data movement concepts
watermark + hashing + batching + MERGE + idempotency + reconciliation
                         ↓
Warehouse concepts
Snowflake RAW/CONTROL + dbt STAGING/INTERMEDIATE/MARTS
                         ↓
Analytical concepts
grain + facts + dimensions + SCD2 + business metrics + tests
                         ↓
Operational engineering
Git + GitHub Actions + Docker + OIDC + Dagster + observability
                         ↓
Managed integration proof
Neon WAL → Estuary Flow → Snowflake
~~~

For the guided implementation path, continue with [engineering_walkthrough.md](engineering_walkthrough.md).

Deep implementation references:
- [PostgreSQL, SQL and source contracts](postgres_sql_contracts_deep_dive.md)
- [Ingestion: PostgreSQL → Snowflake](ingestion_deep_dive.md)
- [dbt, Snowflake modeling and business SQL](dbt_modeling_deep_dive.md)
- [Git, GitHub, CI/CD, security and OIDC](git_ci_security_deep_dive.md)
- [Neon, PostgreSQL WAL and Estuary CDC](estuary_cdc_deep_dive.md)
