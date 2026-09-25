# External integration status

This document is deliberately strict: an integration is marked VERIFIED only after provider-side execution succeeds.

Terminology:
- **Neon** is the managed PostgreSQL source used for the real CDC proof.
- **WAL** is PostgreSQL's write-ahead log, the transaction log from which logical replication exposes row changes.
- **Estuary Flow** is the managed CDC/data-integration platform that consumes those logical changes and materializes them into Snowflake.
- **BigQuery** is Google's analytical warehouse used for the independent GCP batch/reconciliation proof.

For fuller definitions and the distinction between the custom watermark path and true log-based CDC, see [concepts.md](concepts.md).

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

## Google Cloud

Status: **VERIFIED VIA BIGQUERY SANDBOX**

Executed provider path:

`Authenticated Google Cloud Shell → deterministic claims export → BigQuery Sandbox dataset/table → GoogleSQL reconciliation`

Verified:
- Google Cloud project selected in authenticated Cloud Shell.
- BigQuery API enabled.
- typed claims dataset/table created.
- deterministic CSV loaded.
- source manifest compared against BigQuery row count, amount sum and ID bounds.
- final committed runner returned `GCP_BIGQUERY_SANDBOX_ASSERTION=PASS`.
- no billing account or credit card was attached for the proof.

Evidence:
[`docs/evidence/gcp_bigquery_sandbox.md`](evidence/gcp_bigquery_sandbox.md)

### GCS / Snowflake production extension

Status: **IMPLEMENTED BUT NOT PROVIDER-EXECUTED**

The repository includes:
- GitHub→GCP WIF bootstrap hardened to immutable repository IDs;
- private GCS bucket configuration;
- deterministic upload/manifest path;
- Snowflake storage-integration template;
- external stage/COPY;
- reconciliation code.

Provider execution is blocked because the available GCP projects have billing disabled and GCS bucket creation returns HTTP 403. The project intentionally does not attach billing only to satisfy a demo requirement.

This distinction must remain explicit in interviews.
