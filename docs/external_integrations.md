# External integration status

This document is deliberately strict: an integration is marked VERIFIED only after provider-side execution succeeds.

## Estuary Flow

Status: **VERIFIED**

Executed path:

`Neon PostgreSQL public.claims → logical replication/WAL → Estuary Flow → Snowflake PET_INSURANCE_ESTUARY.CLAIMS`

Verified provider-side execution:
- Neon logical replication enabled and confirmed with `wal_level=logical`.
- Isolated publication `pet_insurance_estuary_publication`.
- Publication contains only `public.claims` and `public.flow_watermarks`.
- Direct Neon endpoint verified live.
- Estuary CI authentication verified through `flowctl`.
- Estuary capture published and entered `Streaming CDC Events`.
- Initial claims snapshot read from the Estuary collection.
- Disposable claim executed through INSERT → UPDATE → physical DELETE.
- Estuary emitted `c`, `u`, and `d` events.
- Snowflake JWT materialization published successfully.
- Snowflake materialized 13 history rows.
- Exact disposable claim history in Snowflake contains one create, one update and one delete event.

Primary evidence:
- source readiness: `36028494337`
- direct Neon DSN: `36029268827`
- Estuary auth: `36033188622`
- capture publish: `36033392711`
- collection read: `36033652085`
- source C/U/D proof: `36033857733`
- Snowflake materialization: `36040696100`
- Snowflake C/U/D evidence: `36041150766`

Full evidence:
[`docs/evidence/estuary_cdc.md`](evidence/estuary_cdc.md)

Trial limitation:
- the live proof reuses the existing Neon owner role and Snowflake GitHub service user / learning role.
- production would use separate least-privilege CDC identities.

## Google Cloud / GCS

Status: **BLOCKED_BY_PROVIDER_AUTH — NOT VERIFIED**

Completed in repository:
- deterministic PostgreSQL claims export.
- source manifest with SHA-256, row count, claim amount sum and ID bounds.
- unit test proving deterministic export/manifest.
- GitHub→GCP Workload Identity Federation workflow.
- private GCS upload commands.
- reproducible GCP WIF + private-bucket bootstrap script.
- Snowflake GCS storage-integration template.
- Snowflake external stage + COPY path.
- source-manifest→Snowflake reconciliation code.
- temporary WIF credential files are gitignored.

Remaining provider actions:
- authenticate/select a GCP project.
- run the committed WIF/bucket bootstrap.
- set GitHub repository variables for project/provider/service account/bucket.
- create the Snowflake GCS storage integration and grant its generated Google service account read access to only the proof bucket.
- execute `GCP GCS Backfill Proof` and record reconciliation output.

Until that workflow is green, GCP remains a ready-but-unverified integration package.
