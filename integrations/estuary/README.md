# Estuary Flow CDC proof

Status: **READY FOR PROVIDER AUTHORIZATION — NOT YET EXECUTED IN ESTUARY**

The intended isolated proof is:

`Neon PostgreSQL public.claims → Estuary Flow collection → Snowflake PET_INSURANCE_ESTUARY.CLAIMS`

The existing custom Python ingestion remains in the repository because it demonstrates the mechanics directly. Estuary is a second path showing how the same production problem can be delegated to a managed CDC platform.

## Why this path

Estuary's Neon PostgreSQL connector uses PostgreSQL logical replication/WAL. The Snowflake materialization applies captured changes transactionally. This directly addresses the limitation of watermark polling: physical deletes and older change events are available from the replication stream rather than inferred from current table state.

## Source prerequisites

Run:

```bash
python -m insurance_platform.estuary_source_readiness
```

The command:

1. requires `wal_level=logical`;
2. creates `public.flow_watermarks`;
3. creates isolated publication `pet_insurance_estuary_publication`;
4. publishes only `public.flow_watermarks` and `public.claims`.

Logical replication must be enabled in Neon Project Settings before the command can succeed.

For the final Estuary connection, create a **dedicated Neon role** rather than reusing the application owner. Grant the role read access and use a **direct Neon connection string**, not a `-pooler` hostname.

## Capture configuration

Use the Neon PostgreSQL connector:

- image: `ghcr.io/estuary/source-postgres:v3`
- database: `pet_insurance`
- schema: `public`
- stream: `claims`
- publication: `pet_insurance_estuary_publication`
- watermarks table: `public.flow_watermarks`
- history mode: true for the proof so insert/update/delete events remain inspectable

Credentials are entered only in Estuary and are not committed.

## Snowflake destination

Use a dedicated schema and service identity:

- database: current project database
- schema: `PET_INSURANCE_ESTUARY`
- warehouse: X-Small / auto-suspend
- auth: Snowflake JWT key-pair
- `QUOTED_IDENTIFIERS_IGNORE_CASE = FALSE`

The private key belongs in Estuary's connector secret configuration and must never be committed.

## Acceptance proof

The integration is complete only after all of these are executed:

1. baseline claim appears in the Estuary-backed Snowflake table;
2. insert a new isolated claim → destination receives it;
3. update that claim → destination changes;
4. physical DELETE that isolated claim → destination reflects the connector's configured delete semantics / metadata;
5. capture/materialization status is healthy;
6. evidence file records workflow/provider timestamps and Snowflake verification queries.

Until that happens this integration remains explicitly **not verified**.
