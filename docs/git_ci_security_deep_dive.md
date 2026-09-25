# Git, GitHub, CI/CD, security and OIDC deep dive

This document explains the repository and automation layer that turns the project from local files into a reproducible engineering system.

Primary files:
- [.github/workflows/platform-ci.yml](../.github/workflows/platform-ci.yml)
- [.github/workflows/security.yml](../.github/workflows/security.yml)
- [.github/workflows/dagster-proof.yml](../.github/workflows/dagster-proof.yml)
- [Makefile](../Makefile)
- [pyproject.toml](../pyproject.toml)
- [requirements/ci.lock.txt](../requirements/ci.lock.txt)
- [infra/snowflake/bootstrap_oidc.sql](../infra/snowflake/bootstrap_oidc.sql)

# 1. Git and GitHub are different

Git is the version-control system. It records project history as commits and supports branches.

GitHub hosts the Git repository and adds web review, Actions automation, artifacts, permissions and OIDC identity for workflows.

The project can use Git without GitHub, but the verified CI surface depends on GitHub Actions.

# 2. Repository, commit and branch

A repository contains the version-controlled code, SQL, tests, configuration and documentation plus their history.

A commit is a snapshot of coherent changes with a parent relationship and message.

A branch points to a sequence of commits.

This project uses main as the active review branch and submission-final-2026-09-25 as the frozen reviewer checkpoint.

# 3. CI and CD

CI means continuous integration: automatically checking that changes integrate correctly.

CD commonly means continuous delivery or deployment.

This repository is strongest on CI and controlled workflow execution. It should not be described as a complete enterprise production deployment platform.

# 4. GitHub Actions workflow anatomy

Workflow YAML can define triggers, permissions, jobs, runner environments, steps, environment values, secrets and artifacts.

Platform CI runs manually, on selected pushes to main, and on pull requests affecting relevant implementation paths.

Specialist proof workflows are mainly manual because they represent targeted integration scenarios rather than work required on every commit.

# 5. Workflow permissions

Platform CI requests:

~~~text
id-token: write
contents: read
~~~

contents: read permits checkout.

id-token: write permits the workflow to request a GitHub OIDC identity token.

The workflow does not request broad repository write privileges merely because they are available.

# 6. Platform CI jobs

[platform-ci.yml](../.github/workflows/platform-ci.yml) contains:

~~~text
Python quality
PostgreSQL Docker smoke
Snowflake dbt build
~~~

The first two can run independently.

The Snowflake/dbt job depends on both, so remote warehouse verification is not attempted when foundational checks already fail.

# 7. Python quality

The Python job:
1. checks out the repository;
2. installs Python 3.12;
3. installs the locked CI dependencies;
4. installs the project editable without dependency re-resolution;
5. runs pip check;
6. runs Ruff fatal/static checks;
7. runs pytest.

A lock file keeps CI on a known tested dependency set.

pip check verifies installed dependency consistency.

pytest verifies the Python semantics before remote systems are involved.

# 8. Ruff

Ruff is a Python linter/static checker.

The workflow focuses on serious E9/F categories rather than turning style preference into the main engineering gate.

# 9. PostgreSQL Docker job

The source integration job:
1. checks out code;
2. installs the runtime;
3. starts PostgreSQL with Docker Compose;
4. waits for pg_isready;
5. validates source contracts;
6. runs the SQL smoke test;
7. shows container state even on failure;
8. tears down the database and volumes.

This verifies that the source can be reconstructed from a clean environment rather than depending on one laptop.

# 10. Service started versus service ready

docker compose up means the process has started.

It does not guarantee PostgreSQL is ready to accept SQL.

The workflow polls pg_isready for a bounded period.

This is a small example of operational engineering: readiness and process existence are different states.

# 11. Snowflake/dbt job

The Snowflake job runs only when the event is not a pull request.

It:
1. checks out code;
2. installs Python;
3. obtains a Snowflake OIDC token;
4. installs the locked dbt toolchain;
5. runs dbt debug;
6. runs dbt build;
7. generates dbt docs;
8. verifies the focal claim and claim history with direct Snowflake SQL;
9. uploads dbt artifacts.

A successful dbt build proves the model graph and tests passed.

The extra SQL assertions connect technical success to the business scenario: CLM-10042 must be PAID with claim amount 11200, approved amount 9700 and paid amount 9700, and its historical model must contain three claim events.

# 12. CI artifacts

The workflow uploads:

~~~text
manifest.json
run_results.json
catalog.json
index.html
~~~

These preserve dbt graph, execution and catalog information from the run.

# 13. OIDC

OIDC means OpenID Connect.

GitHub Actions can request a signed short-lived identity token for the workflow.

The security improvement is:

~~~text
short-lived federated identity
instead of
long-lived Snowflake password
~~~

# 14. Workload identity

Workload identity lets automation authenticate as a workload rather than by reusing a human credential.

The dbt profile uses workload identity, the OIDC provider and the Snowflake token produced for the job.

Benefits:
- reduced static-secret exposure;
- short credential lifetime;
- automation identity can be separated from human identity.

# 15. Proposed production bootstrap

[bootstrap_oidc.sql](../infra/snowflake/bootstrap_oidc.sql) is explicitly marked proposed production bootstrap.

Verified trial execution uses PET_INSURANCE_GITHUB with the learning role, warehouse and database.

The proposed design records the intended least-privilege direction:
- dedicated CI/CD role;
- X-Small warehouse;
- dedicated analytics database;
- narrow grants.

It must not be described as deployed.

# 16. Least privilege

Least privilege means granting only what the workload needs.

The proposed runtime role receives warehouse usage/operate, database usage and schema-creation capability rather than broad account administration.

ACCOUNTADMIN appears only in the bootstrap because administrative setup requires higher privilege.

It is not the intended ordinary CI runtime role.

# 17. Security Gate

[security.yml](../.github/workflows/security.yml) separates:
- secret scanning;
- dependency/static/script checks.

This keeps security concerns visible rather than burying them inside the main build job.

# 18. Gitleaks

Gitleaks searches Git history for likely committed secrets.

The workflow checks out complete history using fetch-depth 0.

That matters because deleting a credential from the latest file does not remove it from old Git commits.

# 19. Dependency audit

pip-audit checks the installed Python environment against known vulnerability advisories.

A clean audit does not prove that software can never contain a vulnerability.

It proves that the installed dependency set was checked against known advisories at execution time.

# 20. Shell syntax validation

The security workflow runs bash -n on integration scripts.

bash -n parses shell syntax without executing provider operations.

This provides a cheap static gate for scripts whose full execution requires cloud identity.

# 21. Makefile as project interface

[Makefile](../Makefile) provides stable commands:

~~~text
make bootstrap
make lint
make test
make postgres-up
make contracts
make postgres-smoke
make local-verify
make dbt-debug
make dbt-build
make dbt-docs
make snowflake-deploy
~~~

This prevents documentation from becoming a collection of long implementation-specific commands.

The Makefile is the human-facing command interface to common project operations.

# 22. local-verify

The local verification target chains bootstrap, lint, tests, a clean PostgreSQL start, readiness wait, contract validation, smoke tests and teardown.

That creates a zero-to-green reproducibility path.

# 23. pyproject.toml

[pyproject.toml](../pyproject.toml) defines:
- package metadata;
- Python version;
- build backend;
- base dependency;
- ingestion dependencies;
- development dependencies;
- orchestration dependencies;
- pytest configuration.

Separating optional dependency groups means a minimal installation does not need every cloud/database/orchestration package.

# 24. Dependency lock

requirements/ci.lock.txt pins the tested CI environment.

Advantage:
- reproducible dependency versions.

Trade-off:
- upgrades are deliberate maintenance rather than automatically floating to newest releases.

For CI, that trade-off is normally desirable.

# 25. Dagster proof

[dagster-proof.yml](../.github/workflows/dagster-proof.yml) obtains Snowflake OIDC identity, installs orchestration dependencies, runs the Dagster job in-process and verifies ingestion health directly in Snowflake.

Dagster and GitHub Actions solve different problems.

GitHub Actions provides the remote automation environment.

Dagster expresses the data-task dependency chain:

~~~text
validate contracts
→ ingest
→ dbt build
→ verify health
~~~

# 26. Secrets and environment variables

Sensitive connection values belong in secrets.

Non-sensitive runtime configuration can be supplied as variables or checked-in defaults where appropriate.

POSTGRES_DSN is supplied through repository Actions secrets.

Snowflake uses OIDC rather than a stored warehouse password.

Environment variables are a configuration mechanism, not automatically a security mechanism. Security depends on where their values originate.

# 27. Cleanup and failure handling

Automation should preserve useful failure evidence and still clean disposable resources.

Examples:
- PostgreSQL status and teardown use always-run behavior;
- dbt build uses fail-fast;
- direct Snowflake assertions force a failure when the focal business result is wrong;
- specialist reliability workflows distinguish deliberate expected rejection from accidental infrastructure failure.

# 28. Why the workflow surface is intentionally small

The final repository keeps the workflows that communicate stable capabilities rather than every one-off diagnostic workflow used during implementation.

Benefits:
- easier reviewer navigation;
- lower maintenance;
- less duplicate configuration;
- clearer operating surface.

Executed provider evidence remains in docs/evidence even when a temporary setup workflow is not part of the final front door.

# 29. Reproducibility is not identical to production deployment

This repository is reproducible and production-style, but a full production platform would add organization-specific controls such as:
- environment promotion;
- approval policy;
- protected branches;
- ownership/on-call;
- monitoring/SLOs;
- backup/recovery;
- infrastructure lifecycle;
- secret rotation policy.

The correct claim is demonstrated engineering capability, not complete enterprise operations.

# 30. Competency map

| Skill | Evidence |
| --- | --- |
| Git repository organization | complete versioned project |
| branches | main + frozen submission branch |
| CI | Platform CI |
| path filtering | workflow triggers |
| job dependencies | Snowflake job needs foundation jobs |
| artifacts | dbt artifact upload |
| container integration test | PostgreSQL Docker job |
| workload identity | Snowflake OIDC |
| least-privilege design | proposed bootstrap |
| secret scanning | Gitleaks |
| dependency audit | pip-audit |
| static checks | Ruff |
| shell validation | bash -n |
| stable developer commands | Makefile |
| dependency grouping | pyproject.toml |
| reproducible CI dependencies | lock file |
| orchestration proof | Dagster workflow |

# 31. Trade-offs

GitHub Actions gives visible evidence, repository integration and OIDC without maintaining a CI server.

It is not automatically the best permanent scheduler for every production data workload.

Manual specialist workflows reduce unnecessary cost and provider mutation, but some specialist proofs are not rerun on every commit.

OIDC adds identity configuration complexity, but replaces a more fragile long-lived password model for automation.

# 32. Interview explanation

> Git records the project history while GitHub provides the review and automation surface. Platform CI gates Python tests, a clean Docker/PostgreSQL source, Snowflake authentication and the full dbt build. Job dependencies avoid remote warehouse work when foundational checks already fail. GitHub OIDC provides short-lived workload identity to Snowflake instead of a stored warehouse password. A separate Security Gate scans complete Git history for secrets, audits installed dependencies, runs static Python checks and validates shell syntax. The Makefile and locked dependencies give a stable reproducible developer interface, while Dagster demonstrates data-workflow orchestration separately from CI.

If you can explain the difference between Git, GitHub, CI, orchestration, secrets and workload identity, you understand the platform layer rather than simply recognizing Actions YAML.
