PYTHON ?= python
POSTGRES_DSN ?= postgresql://insurance_app:insurance_dev@localhost:5432/insurance

.PHONY: help bootstrap lint test postgres-up postgres-wait postgres-down contracts postgres-smoke seed seed-load local-verify dbt-debug dbt-build dbt-docs snowflake-deploy

help:
	@printf '%s\n' 	  'bootstrap       Install the exact CI lock and editable project' 	  'lint            Run Ruff fatal/static checks' 	  'test            Run pytest' 	  'postgres-up     Start PostgreSQL 16 with Docker Compose' 	  'postgres-wait   Wait until local PostgreSQL is accepting connections' 	  'contracts       Validate source contracts against POSTGRES_DSN' 	  'postgres-smoke  Prove schema, relationships, and database constraints' 	  'seed            Generate deterministic CSV seed data' 	  'seed-load       COPY generated CSV data into POSTGRES_DSN' 	  'local-verify    Recreate and verify the local source from zero' 	  'dbt-debug       Validate dbt/Snowflake connectivity' 	  'dbt-build       Build and test all dbt models' 	  'dbt-docs        Generate dbt documentation artifacts' 	  'snowflake-deploy Deploy/verify Snowflake RAW and CONTROL objects'

bootstrap:
	$(PYTHON) -m pip install -r requirements/ci.lock.txt
	$(PYTHON) -m pip install --no-deps -e .
	$(PYTHON) -m pip check

lint:
	ruff check src tests --select E9,F --ignore F401

test:
	pytest -q

postgres-up:
	docker compose up -d postgres

postgres-wait:
	@for i in $$(seq 1 30); do 	  if docker compose exec -T postgres pg_isready -U insurance_app -d insurance >/dev/null 2>&1; then 	    echo "PostgreSQL is ready"; exit 0; 	  fi; 	  sleep 2; 	done; 	docker compose logs postgres; 	exit 1

postgres-down:
	docker compose down -v

contracts:
	POSTGRES_DSN="$(POSTGRES_DSN)" $(PYTHON) -m insurance_platform.validate_contracts

postgres-smoke:
	docker compose exec -T postgres 	  psql -U insurance_app -d insurance -v ON_ERROR_STOP=1 	  < infra/postgres/smoke_test.sql

seed:
	$(PYTHON) -m insurance_platform.generate_seed

seed-load:
	POSTGRES_DSN="$(POSTGRES_DSN)" SEED_DIR=data/generated 	  $(PYTHON) -m insurance_platform.load_seed

local-verify: bootstrap lint test
	$(MAKE) postgres-down || true
	$(MAKE) postgres-up
	$(MAKE) postgres-wait
	$(MAKE) contracts
	$(MAKE) postgres-smoke
	$(MAKE) postgres-down

dbt-debug:
	dbt debug --project-dir dbt --profiles-dir dbt

dbt-build:
	dbt build --project-dir dbt --profiles-dir dbt --fail-fast

dbt-docs:
	dbt docs generate --project-dir dbt --profiles-dir dbt

snowflake-deploy:
	snow sql -f infra/snowflake/deploy.sql -x
	snow sql -f infra/snowflake/verify_platform_objects.sql -x
