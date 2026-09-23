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
