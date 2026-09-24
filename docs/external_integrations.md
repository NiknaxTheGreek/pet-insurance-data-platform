# External integration status

This document is deliberately strict: an integration is marked VERIFIED only after provider-side execution succeeds.

## Estuary Flow

Status: **BLOCKED_BY_PROVIDER_AUTH + SOURCE_SETTING — NOT VERIFIED**

Completed in repository:
- Neon PostgreSQL readiness checker.
- Isolated publication design for `public.claims` + `public.flow_watermarks`.
- Snowflake dedicated-role/user/schema setup template.
- Capture/materialization acceptance test definition.

Executed evidence:
- readiness workflow run: `36009597153`
- Neon reported:
  - `wal_level=replica`
  - source role: `pet_insurance_owner`
  - `rolreplication=true`
  - `rolsuper=false`

Remaining source action:
- enable Neon logical replication so `wal_level=logical`.
- Neon documents this as a project setting that restarts computes; this project therefore does not change it without explicit operator approval.

Remaining provider action:
- authenticate/create Estuary workspace.
- configure Neon PostgreSQL capture with a dedicated replication credential.
- configure Snowflake materialization with a dedicated JWT key-pair identity.
- execute INSERT / UPDATE / physical DELETE proof and verify Snowflake destination.

Until those steps execute successfully, no README or interview statement may describe Estuary as implemented.

## Google Cloud / GCS

Status: **BLOCKED_BY_PROVIDER_AUTH — NOT VERIFIED**

Completed in repository:
- deterministic PostgreSQL claims export.
- source manifest with SHA-256, row count, claim amount sum and ID bounds.
- unit test proving deterministic export/manifest.
- GitHub→GCP Workload Identity Federation workflow.
- private GCS upload commands.
- Snowflake GCS storage-integration template.
- Snowflake external stage + COPY path.
- source-manifest→Snowflake reconciliation code.
- temporary WIF credential files are gitignored.

Provider probe:
- Google Cloud Console had no authenticated session.
- no project or Cloud Storage resources were available to inspect.
- no billing or paid-resource action was taken.

Remaining provider actions:
- authenticate/select a GCP project.
- create a private proof bucket.
- configure GitHub OIDC/WIF provider + least-privilege service account.
- set GitHub repository variables for project/provider/service account/bucket.
- create Snowflake GCS storage integration and grant its generated Google service account read access to only the proof bucket.
- execute `GCP GCS Backfill Proof` and record reconciliation output.

Until the workflow is green, this path remains a ready-but-unverified integration package.
