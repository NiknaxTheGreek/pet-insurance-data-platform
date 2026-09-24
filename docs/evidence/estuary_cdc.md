# Estuary WAL CDC → Snowflake evidence

This file records the executed managed-CDC proof. It is separate from the custom Python watermark/reconciliation implementation.

## Path

`Neon PostgreSQL public.claims → logical replication/WAL → Estuary Flow → Snowflake PET_INSURANCE_ESTUARY.CLAIMS`

## Source readiness

Workflow: `Estuary Source Readiness`  
Run: `36028494337`  
Result: PASS

Verified:
- `wal_level=logical`
- source role: `pet_insurance_owner`
- replication capability available
- publication: `pet_insurance_estuary_publication`
- publication scope: `public.claims`, `public.flow_watermarks`

Direct-endpoint proof:

Workflow: `Estuary Source DSN Diagnostic`  
Run: `36029268827`  
Result: PASS

Verified:
- existing pooled Neon DSN can be transformed to the direct endpoint without exposing the secret;
- direct endpoint connects on port 5432;
- direct endpoint reports `wal_level=logical`.

## Estuary authentication and capture

Workflow: `Estuary Auth Diagnostic`  
Run: `36033188622`  
Result: PASS

Verified tenant role:
- prefix: `Private77/`
- capability: admin

Workflow: `Estuary Neon Capture`  
Run: `36033392711`  
Result: PASS

Published:
- capture: `Private77/pet-insurance/source-neon`
- collection: `Private77/pet-insurance/public/claims`

Capture state after initialization:
- source capture status: `Streaming CDC Events`

Workflow: `Estuary Collection Read`  
Run: `36033652085`  
Result: PASS

The collection contained the real source snapshot, including `CLM-10042`, with Estuary source metadata and `_meta.op='c'`.

## Insert / update / physical-delete proof

Workflow: `Estuary CDC Mutation Proof`  
Run: `36033857733`  
Result: PASS

Disposable claim:
`CLM-EST-36033857733`

Executed against live PostgreSQL:
1. INSERT
2. UPDATE to APPROVED
3. physical DELETE

Estuary collection assertions:
- create event: PASS
- update event: PASS
- delete event: PASS
- combined C/U/D assertion: PASS

This is actual log-based CDC evidence. It demonstrates a capability that the custom watermark implementation intentionally cannot provide for physical deletes.

## Snowflake materialization

Workflow: `Estuary Snowflake Materialization`  
Run: `36040696100`  
Result: PASS

Authentication:
- GitHub OIDC authenticated the CI workflow to Snowflake.
- The workflow generated an ephemeral RSA keypair.
- The public key was assigned automatically to `PET_INSURANCE_GITHUB`.
- JWT login with the generated private key passed.
- The private key existed only inside the GitHub runner.
- `QUOTED_IDENTIFIERS_IGNORE_CASE=FALSE` was enforced for Estuary compatibility.

Published:
- materialization: `Private77/pet-insurance/materialize-snowflake`
- destination: `SNOWFLAKE_LEARNING_DB.PET_INSURANCE_ESTUARY.CLAIMS`
- update mode: delta/history-preserving
- initial materialized rows: **13**

## End-to-end Snowflake C/U/D assertion

Workflow: `Estuary Snowflake CDC Evidence`  
Run: `36041150766`  
Result: PASS

For `CLM-EST-36033857733`, Snowflake returned:

| CLAIM_ID | _meta/op |
| --- | --- |
| CLM-EST-36033857733 | c |
| CLM-EST-36033857733 | d |
| CLM-EST-36033857733 | u |

Aggregate assertion:
- create events: **1**
- update events: **1**
- delete events: **1**
- end-to-end assertion: **PASS**

## Scope / production caveat

For this bounded trial proof:
- the existing Neon owner role was reused for the Estuary capture;
- the existing Snowflake GitHub service user / learning role was reused for materialization.

For production, use separate least-privilege CDC identities for Neon and Snowflake, with environment-specific ownership and credential rotation.
