# ADR 005 — Complexity must be earned

Status: Accepted

## Context

A portfolio project can become less credible when it adds technologies that do not solve a demonstrated problem.

## Decision

Use:

- PostgreSQL
- Python
- Snowflake
- dbt
- Docker Compose
- GitHub Actions

Do not add Kafka, Airflow, Kubernetes, Spark, Terraform, a dashboard, or a microservice layer solely for breadth.

## Why

The required engineering signals are already demonstrated directly:

- incremental capture and CDC semantics
- history
- idempotency/replay
- reconciliation
- data quality and controlled failure
- observability
- tests
- CI/CD
- reproducible source environment
- warehouse modeling
- security-aware authentication

Extra infrastructure would increase surface area without improving the insurance use case.

## Cost/performance posture

The project favors bounded compute and incremental work. dbt processes only missing claim-event records; no-change runs are verified. Docker is ephemeral in CI. Snowflake CI uses the pre-existing learning warehouse rather than provisioning additional compute.

Because the live dataset is intentionally small, this project does not claim benchmark speedups or production cost savings. Performance claims are limited to verified query plans, row counts, and incremental/no-op behavior.


## Deliberate scope boundaries and alternatives

The repository demonstrates a bounded data platform rather than every component that might exist in a larger production estate. The omissions below are intentional and should not be interpreted as implemented capability.

| Capability not implemented here | Current project approach | Tools that could be used instead or added later | When they would be justified |
| --- | --- | --- | --- |
| Persistent production scheduling | GitHub Actions executes controlled workflows; Dagster proves dependency orchestration in-process | Dagster deployment, Apache Airflow, Prefect | recurring SLAs, backfills, many dependent pipelines, operational ownership |
| Durable event streaming / message bus | Estuary reads PostgreSQL WAL directly; custom Python path is batch/incremental | Apache Kafka, Redpanda, Amazon Kinesis, Google Pub/Sub | multiple real-time consumers, event replay requirements, sustained low-latency streaming |
| Alternative CDC / managed ELT | Estuary Flow is the verified managed CDC tool | Debezium + Kafka Connect, Airbyte, Fivetran | different connector coverage, self-hosting requirements, managed-service preference or cost model |
| Infrastructure as code | Snowflake/GCP setup is represented through SQL, shell scripts and documented manual/provider steps | Terraform, OpenTofu, Pulumi | repeatable multi-environment infrastructure, formal promotion and drift control |
| Container orchestration | Docker Compose recreates PostgreSQL locally/CI | Kubernetes, Amazon ECS, Google Cloud Run | long-running containerized services, autoscaling, service discovery and production runtime management |
| Distributed data processing | Snowflake SQL/dbt handles the demonstrated workload | Apache Spark, Databricks | data volume or transformation patterns that no longer fit warehouse SQL efficiently |
| Dedicated data-quality platform | dbt tests, PostgreSQL constraints and custom reconciliation enforce quality | Great Expectations, Soda, Monte Carlo | broader cross-system quality rules, anomaly detection, data observability and ownership workflows |
| Dedicated monitoring/alerting stack | Snowflake CONTROL tables, structured logs and GitHub Actions expose pipeline state | Prometheus + Grafana, Datadog, New Relic, OpenTelemetry | continuous operations, alert routing, SLOs and centralized telemetry |
| Enterprise data catalog | dbt models/docs and repository documentation provide lineage/context | DataHub, OpenMetadata, Collibra, Alation | many datasets, teams, owners, governance domains and discovery requirements |
| BI/dashboard layer | MARTS are the analytical output; no dashboard is shipped | Power BI, Tableau, Looker | business-user consumption, KPI monitoring and self-service reporting |
| Dedicated secrets platform | GitHub OIDC is used for Snowflake and GitHub Secrets stores the PostgreSQL DSN | HashiCorp Vault, AWS Secrets Manager, Google Secret Manager, Azure Key Vault | centralized rotation, multiple runtimes, environment separation and broader credential governance |
| Production backup / disaster recovery | RAW preserves analytical history but is explicitly not a backup system | managed PostgreSQL point-in-time recovery, pgBackRest, WAL-G, cloud snapshots | recovery objectives, disaster recovery and restoration of the operational database |
| Multi-cloud object-storage ingestion | GCS→Snowflake design exists but provider execution is blocked by billing-disabled GCP projects | GCS, Amazon S3, Azure Blob Storage with Snowflake external stages | production file feeds, bulk backfills or object-storage landing zones |
| Separate production environments | trial resources and roles are reused where documented | dedicated dev/test/prod accounts, schemas, roles and service identities | team deployment, change control, least privilege and release promotion |

These alternatives are not automatically "better." Each one adds operational cost and failure modes. The project adds a technology only when it solves a demonstrated requirement rather than to increase the number of tools in the architecture.
