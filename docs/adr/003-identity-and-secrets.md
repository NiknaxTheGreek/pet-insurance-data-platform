# ADR 003 — GitHub OIDC for Snowflake; secret only for PostgreSQL source

Status: Accepted

## Context

CI needs Snowflake access. Storing a long-lived Snowflake password or private key in GitHub would increase credential-management burden. The PostgreSQL source still requires a connection credential.

## Decision

GitHub Actions authenticates to Snowflake using short-lived OIDC workload identity federation.

No Snowflake password is stored in the repository or GitHub Actions secrets.

The PostgreSQL source DSN is stored as the repository secret `POSTGRES_DSN` and injected only into workflows that need the source.

## Why

OIDC reduces static credential exposure and gives a clear trust boundary between GitHub Actions and Snowflake.

The implementation initially attempted a dedicated least-privilege CI role, but the trial account's verified available `SNOWFLAKE_LEARNING_ROLE` became the execution role so the project could proceed without fabricating privileges. Project objects are isolated in dedicated `PET_INSURANCE_*` schemas.

## Consequences

Using `SNOWFLAKE_LEARNING_ROLE` is a documented trial-environment compromise, not the desired production IAM design.

A production deployment should use a dedicated role with only required warehouse/database/schema privileges and an environment-specific workload identity.
