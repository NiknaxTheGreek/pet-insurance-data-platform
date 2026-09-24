# Estuary Flow CDC proof

Status: **VERIFIED**

Executed path:

`Neon PostgreSQL public.claims → PostgreSQL logical replication/WAL → Estuary Flow → Snowflake PET_INSURANCE_ESTUARY.CLAIMS`

The custom Python ingestion remains in the repository because it demonstrates watermarking, hashing, reconciliation, transaction boundaries and failure recovery directly. Estuary is the managed CDC path that proves true log-based insert/update/physical-delete capture.

## Source

Verified:
- Neon `wal_level=logical`
- direct non-pooler endpoint
- isolated publication `pet_insurance_estuary_publication`
- published tables: `public.claims`, `public.flow_watermarks`
- source role has replication capability

The workflow derives the direct Neon endpoint from the existing secret at runtime; no additional PostgreSQL password is committed.

## Capture

Published Estuary objects:
- capture: `Private77/pet-insurance/source-neon`
- collection: `Private77/pet-insurance/public/claims`
- connector: `ghcr.io/estuary/source-postgres:v3`
- History Mode: enabled

The capture status reached `Streaming CDC Events`.

A disposable source claim was executed through:
1. INSERT
2. UPDATE
3. physical DELETE

Estuary emitted:
- `_meta.op='c'`
- `_meta.op='u'`
- `_meta.op='d'`

## Snowflake materialization

Published:
- materialization: `Private77/pet-insurance/materialize-snowflake`
- connector: `ghcr.io/estuary/materialize-snowflake:v4`
- database: `SNOWFLAKE_LEARNING_DB`
- schema: `PET_INSURANCE_ESTUARY`
- table: `CLAIMS`
- delta/history-preserving binding

Authentication:
- GitHub OIDC authenticates CI to Snowflake.
- CI generates an ephemeral RSA keypair.
- The public key is assigned to `PET_INSURANCE_GITHUB`.
- JWT authentication is verified.
- The private key exists only in the runner and is used to publish the Estuary connector config.
- `QUOTED_IDENTIFIERS_IGNORE_CASE=FALSE` is enforced.

Initial materialized history: **13 rows**.

For `CLM-EST-36033857733`, Snowflake contains:

| CLAIM_ID | _meta/op |
| --- | --- |
| CLM-EST-36033857733 | c |
| CLM-EST-36033857733 | d |
| CLM-EST-36033857733 | u |

Aggregate assertion:
- create events: **1**
- update events: **1**
- delete events: **1**
- PASS

## Evidence

See:
[`docs/evidence/estuary_cdc.md`](../../docs/evidence/estuary_cdc.md)

Key runs:
- capture publish: `36033392711`
- collection read: `36033652085`
- source C/U/D: `36033857733`
- Snowflake materialization: `36040696100`
- Snowflake C/U/D assertion: `36041150766`

## Production caveat

The bounded trial proof deliberately reuses:
- `pet_insurance_owner` on Neon;
- `PET_INSURANCE_GITHUB` and `SNOWFLAKE_LEARNING_ROLE` on Snowflake.

A production deployment should use dedicated, least-privilege Estuary source and destination identities with environment-specific access and credential rotation.
