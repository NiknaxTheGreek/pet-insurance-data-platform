# Theory and architecture guide

This guide contains the minimum theory needed to understand and defend the project. It explains the important concepts in project context without duplicating the implementation line-by-line.

The project demonstrates a progression from data analysis to analytics engineering and data engineering:

~~~text
business question
→ relational source
→ incremental ingestion
→ historical warehouse
→ tested analytical models
→ automated verification
~~~

## 1. Core technologies

| Term | Meaning in this project |
| --- | --- |
| SQL | Language used to define, query, join, aggregate and test relational data |
| PostgreSQL | Operational relational database containing customers, pets, policies, claims and payments |
| Python | Implements incremental extraction, hashing, staging, reconciliation and reliability logic |
| Snowflake | Analytical warehouse storing source history, ingestion state and dbt outputs |
| dbt | Organizes SQL transformations, tests, contracts and lineage inside Snowflake |
| Git | Version-control system that records project history |
| GitHub | Hosts the Git repository and runs automation through GitHub Actions |
| Docker | Recreates the PostgreSQL source consistently |
| OIDC | Short-lived workload identity used by GitHub Actions to authenticate to Snowflake |
| Dagster | Demonstrates orchestration of dependent data tasks |
| Neon | Managed PostgreSQL used for the log-based CDC proof |
| Estuary Flow | Managed CDC platform that reads PostgreSQL logical-replication events |
| BigQuery | Independent Google Cloud analytical-warehouse proof |

Git is not GitHub. SQL is not PostgreSQL. Snowflake is not dbt. dbt does not copy the source database into Snowflake.

## 2. Business and relational model

The operational source contains five related entities:

~~~text
customer
  → pet
    → policy
      → claim
        → claim payment
~~~

A **primary key** uniquely identifies a row, for example claim_id.

A **foreign key** requires a relationship to point to an existing row, for example claims.policy_id → policies.policy_id.

A **constraint** enforces a source rule such as:

~~~text
approved amount <= claim amount
monthly premium >= 0
policy end date >= policy start date
~~~

These rules belong in PostgreSQL because invalid operational state should be rejected as early as possible.

Every mutable table also has:
- created_at;
- updated_at;
- is_deleted.

updated_at supports incremental extraction. is_deleted provides observable soft-delete semantics.

The source is reproducible through Docker, and a smoke test proves both the complete relationship chain and database constraint enforcement.

## 3. Source contracts

The YAML files under contracts/ describe the structure the ingestion system agrees to consume.

They define:
- required columns;
- data types;
- nullability;
- primary key;
- data classification.

The live PostgreSQL structure is inspected through information_schema before ingestion.

The compatibility policy is intentionally simple:

~~~text
new additive column
→ allowed and logged

missing required column
→ rejected

incompatible type/nullability/key change
→ rejected
~~~

This separates **database schema creation** from **ingestion compatibility**.

Data classification also distinguishes direct PII, quasi-identifiers, financial fields and operational metadata.

## 4. Incremental ingestion

The custom data path is:

~~~text
PostgreSQL
→ Python
→ Snowflake RAW / CONTROL
→ dbt
~~~

It is an incremental batch design, not WAL-based CDC.

### Composite watermark

The fast path remembers:

~~~text
(updated_at, primary_key)
~~~

rather than timestamp alone.

The primary key breaks ties when multiple rows share the same updated_at value.

### Version identity

Each source row is serialized deterministically and hashed with SHA-256.

A captured version is identified by:

~~~text
source table
+ source primary key
+ source updated timestamp
+ payload hash
~~~

This supports idempotency: replaying the same version does not create another RAW record.

### Staging and MERGE

Candidate rows are placed in a Snowflake staging table.

Snowflake then performs a set-based MERGE into append-only RAW.

RAW is append-only because the warehouse must retain historical source versions rather than overwrite them.

### Atomicity

The critical operation is one transaction:

~~~text
MERGE RAW
+ advance watermark
+ mark batch SUCCESS
~~~

Either all three commit or all three roll back.

This prevents the dangerous state where progress says data was processed even though the data was not committed.

### Reconciliation

A high watermark is efficient but cannot detect every late-arriving version.

The project therefore has a second correctness path that scans current source state and compares complete version identity against RAW.

This allows late new records and late changed versions to be recovered without moving the normal watermark backwards.

The important distinction is:

~~~text
watermark = efficient normal path
reconciliation = bounded correctness path
~~~

## 5. Snowflake layers

Snowflake is divided by responsibility:

~~~text
RAW
captured historical source versions

CONTROL
watermarks, batches, stage and health state

STAGING
typed current-state views

INTERMEDIATE
reusable logic and claim history

MARTS
analyst-facing business models
~~~

RAW uses Snowflake VARIANT to preserve source payloads as semi-structured JSON.

The analytical layers convert those payloads into typed relational columns.

## 6. dbt and analytical modeling

dbt runs SQL transformations inside Snowflake.

The model path is:

~~~text
RAW
→ STAGING
→ INTERMEDIATE
→ MARTS
~~~

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

Grain must be understood before joining or aggregating data.

### Fact and dimension

A **fact table** contains measurable business events. FCT_CLAIMS contains claim, approved and paid amounts.

A **dimension** provides descriptive context. DIM_POLICY provides plan, geography and pet attributes.

### SCD Type 2

A Type-2 slowly changing dimension preserves attribute history instead of overwriting it.

If a customer changes province, the model can retain both the old and current version using effective_from, effective_to and is_current.

### Business tests

dbt tests rules such as:
- approved amount cannot exceed claim amount;
- payment cannot occur before the claim;
- paid amount cannot exceed approved amount;
- claim pet must match policy pet;
- claim date must fall within policy term;
- exactly one current customer-history row must exist;
- direct customer PII must not appear in marts.

A green pipeline means code ran. These tests help establish that the resulting data is also logically valid.

## 7. Portfolio metrics

The portfolio mart groups data by:

~~~text
province × species × plan type
~~~

and calculates measures such as:
- policy count;
- active policies;
- monthly premium book;
- claim count;
- paid claims;
- average claim severity;
- claims per policy.

The model also includes a **paid loss-ratio proxy**:

~~~text
paid claims
──────────────
monthly premium × 12
~~~

It is deliberately called a proxy because the source does not contain actuarial earned-premium exposure.

The project does not present this as a production actuarial loss ratio.

## 8. CI, security and reproducibility

Git records the source history.

GitHub hosts the project and GitHub Actions automates verification.

Platform CI proves three layers:

~~~text
Python tests/static checks
→ clean Docker/PostgreSQL source
→ Snowflake/dbt build
~~~

The Snowflake job runs after the first two succeed.

Security checks include:
- Gitleaks for committed secrets;
- pip-audit for known dependency vulnerabilities;
- Ruff static checks;
- shell syntax validation.

Snowflake automation uses GitHub OIDC/workload identity rather than a stored Snowflake password.

The Makefile provides stable commands such as:

~~~text
make test
make postgres-smoke
make dbt-build
make snowflake-deploy
~~~

This makes the project reproducible without requiring a reviewer to reconstruct command order manually.

## 9. Orchestration

CI and orchestration are different concepts.

**CI** validates changes.

**Orchestration** coordinates dependent data tasks.

Dagster demonstrates:

~~~text
validate source contracts
→ ingest
→ dbt build
→ verify health
~~~

A permanent Dagster service is intentionally not added because the bounded project does not require one.

## 10. True WAL-based CDC

A second data path proves actual PostgreSQL log-based change capture:

~~~text
Neon PostgreSQL
→ logical replication / WAL
→ Estuary Flow
→ Snowflake
~~~

**WAL** means Write-Ahead Log: PostgreSQL's transaction log.

**Logical replication** exposes committed row-level changes such as insert, update and delete.

A PostgreSQL **publication** defines which tables are available to a logical-replication consumer.

The Estuary proof uses:
- Neon with wal_level=logical;
- a direct non-pooler PostgreSQL endpoint;
- a scoped publication;
- Estuary History Mode.

A disposable claim is:
1. inserted;
2. updated;
3. physically deleted.

The resulting create, update and delete events are verified downstream and materialized into Snowflake.

This demonstrates something the watermark design cannot do after a physical row has disappeared.

## 11. Two change-capture approaches

| Property | Python watermark path | Estuary WAL path |
| --- | --- | --- |
| Detection | updated_at + primary key | PostgreSQL transaction log |
| Physical delete | not after row disappears | yes |
| Hashing/reconciliation logic | explicit in project | managed by connector path |
| Transparency for learning | high | more abstracted |
| Purpose here | demonstrate engineering mechanics | prove genuine log-based CDC |

Neither approach is claimed to be universally better.

Architecture should follow requirements such as latency, source behavior, scale and operational cost.

## 12. GCP proof

The verified GCP path uses BigQuery Sandbox.

A deterministic claims file and source manifest are loaded into a typed BigQuery table.

Warehouse aggregates are reconciled back to the manifest.

The repository also retains a production-style GCS → Snowflake design, but that provider path is explicitly marked unexecuted because the available GCP project cannot create the required bucket without billing.

This distinction between implemented design and executed proof is intentional.

## 13. Engineering scope

The project deliberately does not add Kafka, Spark, Kubernetes or a permanent orchestration service merely to increase technology count.

The core capability is demonstrated with:

~~~text
PostgreSQL
Python
Snowflake
dbt
Docker
GitHub Actions
~~~

Additional components are included only when they prove a distinct concept:
- Dagster → orchestration;
- Neon + Estuary → WAL CDC;
- BigQuery → transferable cloud warehouse capability.

## 14. Competency progression

**Data analyst**
- SQL;
- joins;
- aggregation;
- business metrics;
- data validation.

**Analytics engineer**
- model grain;
- dbt;
- staging/intermediate/marts;
- facts and dimensions;
- tests;
- SCD2;
- contracts.

**Data engineer**
- PostgreSQL source design;
- incremental ingestion;
- Snowflake;
- transactions;
- idempotency;
- reconciliation;
- schema compatibility;
- observability.

**Platform-oriented data engineer**
- Git/GitHub;
- Docker;
- CI/CD;
- workload identity;
- security gates;
- orchestration;
- WAL-based CDC;
- cloud integration.

The progression is not about accumulating tools. It is about taking increasing responsibility for how trustworthy data is created, validated and operated.

## 15. Minimal mental model

The entire project can be reduced to:

> PostgreSQL owns mutable operational truth. Python captures source versions safely into append-only Snowflake RAW. Reconciliation closes watermark gaps. dbt turns RAW history into typed current-state and historical analytical models. Tests enforce business and governance rules. GitHub Actions makes the system reproducible and verifiable. Estuary separately proves genuine PostgreSQL WAL CDC.

For exact commands use [reproduction.md](reproduction.md). For operations and recovery use [runbook.md](runbook.md). For executed proof use [evidence/](evidence/).
