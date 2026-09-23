# Reproduction and operating guide

## Local verification

Requirements:

- Python 3.11+
- Docker with Docker Compose

Install and run Python tests:

```bash
python -m pip install -e ".[dev]"
pytest -q
```

Start a clean PostgreSQL source:

```bash
docker compose up -d postgres
```

Run the source smoke test:

```bash
docker compose exec -T postgres \
  psql -U insurance_app -d insurance -v ON_ERROR_STOP=1 \
  < infra/postgres/smoke_test.sql
```

The smoke test proves:

- all five source tables exist
- live-style text IDs work
- the customer→pet→policy→claim→payment relationship chain is valid
- PostgreSQL rejects a claim where approved amount exceeds claim amount

Stop and remove the environment:

```bash
docker compose down -v
```

## Live PostgreSQL → Snowflake

The live workflow requires:

- GitHub repository secret `POSTGRES_DSN`
- Snowflake service user `PET_INSURANCE_GITHUB`
- GitHub OIDC workload identity configured in Snowflake
- access to `SNOWFLAKE_LEARNING_WH` and `SNOWFLAKE_LEARNING_DB` in the current trial environment

Run the GitHub workflow:

`Live Incremental Ingestion`

The runner reads current Snowflake watermarks, queries only newer PostgreSQL rows, hashes/deduplicates source records, merges them idempotently into RAW, advances table watermarks, and records batch audit rows.

## dbt

CI uses:

- dbt Core 1.12.x
- dbt-snowflake 1.12.1

The Snowflake profile is environment-driven and authenticates through workload identity.

Core commands:

```bash
dbt debug --project-dir dbt --profiles-dir dbt
dbt build --project-dir dbt --profiles-dir dbt --fail-fast
dbt docs generate --project-dir dbt --profiles-dir dbt
```

Do not expect the live dbt commands to work locally unless the same Snowflake OIDC environment variables/token are available.

## Verification workflows

- `Platform CI` — main consolidated quality gate
- `Snowflake OIDC Deploy` — deploys/verifies RAW and CONTROL infrastructure
- `dbt Build` — builds/tests/documents the transformation layer
- `Reliability Failure Suite` — controlled invalid-data, late-arrival and soft-delete scenarios
- `Performance Evidence` — row-count, completeness, explain-plan and warehouse evidence
- `T4 Paid Claim Demo` — focal claim progression to PAID
- `Customer SCD2 Demo` — real customer-history proof

## Secret handling

Never commit the PostgreSQL DSN or Snowflake token.

Snowflake CI uses a short-lived GitHub OIDC token. The only persistent source credential required by the live workflow is `POSTGRES_DSN`, stored as a GitHub Actions repository secret.
