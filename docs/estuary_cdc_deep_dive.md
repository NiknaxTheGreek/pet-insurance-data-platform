# Neon, PostgreSQL WAL and Estuary CDC deep dive

This document explains the repository's second data-movement path: true log-based change data capture from PostgreSQL into Snowflake.

Use it with:
- [concepts.md](concepts.md) for terminology;
- [ingestion_deep_dive.md](ingestion_deep_dive.md) for the custom watermark/reconciliation path;
- [docs/evidence/estuary_cdc.md](evidence/estuary_cdc.md) for executed proof.

Primary files:
- [src/insurance_platform/estuary_source_readiness.py](../src/insurance_platform/estuary_source_readiness.py)
- [src/insurance_platform/estuary_flow_spec.py](../src/insurance_platform/estuary_flow_spec.py)
- [src/insurance_platform/estuary_cdc_demo.py](../src/insurance_platform/estuary_cdc_demo.py)
- [integrations/estuary/README.md](../integrations/estuary/README.md)
- [integrations/estuary/generate_keypair.sh](../integrations/estuary/generate_keypair.sh)
- [integrations/estuary/snowflake_setup.sql](../integrations/estuary/snowflake_setup.sql)
- [.github/workflows/estuary-cdc-proof.yml](../.github/workflows/estuary-cdc-proof.yml)

---

# 1. Why a second CDC path exists

The custom Python path demonstrates:
- composite watermarks;
- deterministic hashing;
- idempotent MERGE;
- transactions;
- reconciliation;
- soft deletes;
- failure recovery.

It is intentionally not described as PostgreSQL WAL CDC.

The Estuary path demonstrates something different:

~~~text
Neon PostgreSQL
→ PostgreSQL logical replication / WAL
→ Estuary Flow
→ Snowflake CDC history
~~~

The main capability added by the WAL path is source-log visibility, including a physical DELETE after the source row no longer exists.

---

# 2. Neon

Neon is a managed/serverless PostgreSQL platform.

For this project it provides the PostgreSQL database used by the executed log-based CDC proof.

The important point is:

~~~text
Neon is still PostgreSQL
~~~

The SQL and logical-replication concepts remain PostgreSQL concepts.

Neon provides managed infrastructure around the database.

---

# 3. WAL

WAL means Write-Ahead Log.

PostgreSQL records changes in its transaction log before those changes are fully applied to database pages.

This log is fundamental to durability and recovery.

For CDC, the useful idea is that committed changes can be exposed from the transaction stream rather than rediscovered by repeatedly querying current rows.

---

# 4. Logical replication

Logical replication turns WAL information into logical database changes.

At a high level, a consumer can observe operations such as:

~~~text
INSERT
UPDATE
DELETE
~~~

This is different from the custom watermark path.

The watermark path asks:

> What current source rows sort after my last known updated_at + primary key?

The WAL path asks:

> What committed row changes did PostgreSQL emit?

---

# 5. Why physical delete matters

Suppose a row is physically deleted:

~~~sql
DELETE FROM claims
WHERE claim_id = 'CLM-X';
~~~

After deletion, a normal SELECT from claims cannot see the row.

An updated_at polling process therefore has nothing left to discover.

A logical-replication consumer can observe the DELETE event from the transaction log.

That is why the Estuary proof demonstrates a capability the custom path deliberately does not claim.

---

# 6. Soft delete versus physical delete

Custom path:

~~~text
is_deleted = true
updated_at advances
row remains queryable
→ Python can capture DELETE state
~~~

WAL path:

~~~text
DELETE FROM table
row disappears
→ logical replication emits delete event
~~~

Both can represent deletion semantics, but they observe fundamentally different source behavior.

---

# 7. wal_level

[src/insurance_platform/estuary_source_readiness.py](../src/insurance_platform/estuary_source_readiness.py) executes:

~~~sql
SHOW wal_level
~~~

The required value is:

~~~text
logical
~~~

Why?

PostgreSQL must retain/expose enough logical information for logical replication consumers.

If wal_level is not logical, the readiness script stops with a clear error.

---

# 8. Replication-capable source identity

The readiness script also checks the current PostgreSQL role through pg_roles.

It inspects:

~~~text
rolreplication
rolsuper
~~~

The purpose is to verify that the source identity can support the replication configuration required by the CDC connector.

A production deployment should use a dedicated least-privilege CDC identity rather than casually reusing an owner role.

The evidence explicitly documents that the bounded trial reused the existing Neon owner identity.

---

# 9. Publication

A PostgreSQL publication defines which table changes are made available to logical replication.

The project creates:

~~~text
pet_insurance_estuary_publication
~~~

The publication is intentionally scoped to:

~~~text
public.claims
public.flow_watermarks
~~~

This is preferable to exposing every source table merely because the connector can.

It demonstrates bounded scope.

---

# 10. flow_watermarks table

The readiness code creates:

~~~text
public.flow_watermarks
~~~

This table is used by the Estuary PostgreSQL connector as part of its source integration behavior.

It is included in the publication alongside claims.

The important point is that connector support metadata is isolated and explicit rather than hidden.

---

# 11. Direct Neon endpoint

[src/insurance_platform/estuary_flow_spec.py](../src/insurance_platform/estuary_flow_spec.py) contains direct_neon_dsn.

Neon can provide pooled endpoints whose hostname contains:

~~~text
-pooler
~~~

Connection pooling is useful for ordinary application traffic, but logical replication requires a direct PostgreSQL connection.

The helper removes the pooler marker and preserves the rest of the DSN.

parse_postgres_dsn rejects a pooled host if one reaches the final capture configuration.

This is an example of provider-specific operational knowledge encoded as a validation rule.

---

# 12. DSN parsing

The capture configuration needs separate fields such as:

~~~text
address
database
user
password
~~~

parse_postgres_dsn extracts those from a PostgreSQL connection string.

It validates:
- PostgreSQL scheme;
- hostname;
- username;
- password;
- non-pooler endpoint.

The password is used to construct the connector specification at runtime, not committed to the repository.

---

# 13. Estuary Flow

Estuary Flow is the managed CDC/data-integration platform in this proof.

Its responsibilities are:
- connect to PostgreSQL logical replication;
- maintain a capture;
- materialize source events into an Estuary collection;
- send the collection to a destination connector such as Snowflake.

The repository does not claim that Estuary is required for the custom Python pipeline.

It is a separate managed integration proof.

---

# 14. Capture specification

write_capture_spec generates an Estuary capture configuration.

The capture uses:

~~~text
ghcr.io/estuary/source-postgres:v3
~~~

Key configuration includes:
- direct PostgreSQL address;
- database and user;
- runtime password;
- historyMode = true;
- public schema discovery;
- public.claims table filter;
- publication name;
- flow watermarks table;
- SSL verification.

The generated configuration is therefore reproducible from environment-provided identity rather than manually defined only through a UI.

---

# 15. History Mode

History Mode is enabled in the Estuary capture.

The project wants to preserve the event sequence rather than only an overwritten latest state.

That is necessary for demonstrating:

~~~text
create
update
delete
~~~

as distinct downstream events.

---

# 16. Capture scope

The discovery filter targets:

~~~text
public.claims
~~~

The proof deliberately focuses on one business table.

Why not replicate everything?

Because the purpose is to prove the capability with the minimum necessary surface.

A bounded proof is easier to reason about, secure and verify.

---

# 17. Estuary collection

The published collection is:

~~~text
Private77/pet-insurance/public/claims
~~~

An Estuary collection is the logical dataset produced by the capture.

The executed evidence verified that the collection contained the real source snapshot and later the controlled CDC events.

---

# 18. _meta.op

The proof checks Estuary metadata:

~~~text
c = create
u = update
d = delete
~~~

The disposable claim is required to produce one event of each type.

This metadata is what lets the test distinguish three source operations for the same business key.

---

# 19. Controlled disposable claim

[src/insurance_platform/estuary_cdc_demo.py](../src/insurance_platform/estuary_cdc_demo.py) operates on a unique claim ID supplied by:

~~~text
ESTUARY_DEMO_CLAIM_ID
~~~

The GitHub workflow constructs it from the workflow run ID.

This makes each proof isolated.

Example shape:

~~~text
CLM-EST-36033857733
~~~

The test does not mutate the focal business demonstration claim.

---

# 20. INSERT mutation

The insert step creates a claim with:

~~~text
claim type      ILLNESS
claim amount    1750
status          SUBMITTED
approved        NULL
~~~

ON CONFLICT DO NOTHING prevents a repeated insert command from failing if the exact disposable ID already exists.

After insertion, the workflow waits briefly for asynchronous CDC capture.

Then flowctl reads recent collection events and requires:

~~~text
claim_id = disposable claim
_meta.op = c
~~~

---

# 21. UPDATE mutation

The update changes:

~~~text
claim_amount     2100
approved_amount  1900
claim_status     APPROVED
updated_at       current timestamp
~~~

The source script requires exactly one updated row.

The workflow then requires an Estuary event with:
- the same disposable claim ID;
- _meta.op = u;
- APPROVED status;
- approved amount 1900.00.

This proves that the CDC stream carries changed business values, not just an abstract update marker.

---

# 22. Physical DELETE mutation

The source executes:

~~~sql
DELETE FROM claims
WHERE claim_id = ?
~~~

The script requires exactly one deleted row.

The workflow then checks the Estuary collection for:

~~~text
same claim ID
_meta.op = d
~~~

This is the strongest distinction from the custom polling path.

---

# 23. Why the workflow sleeps

The proof waits 12 seconds after each mutation.

The CDC path is asynchronous:

~~~text
source commit
→ connector observes log
→ Estuary processes event
→ collection becomes readable
~~~

Immediate read-after-write at the destination is not guaranteed.

The bounded wait is simple for this portfolio proof.

A larger production test might poll with timeout/retry rather than use fixed sleep.

---

# 24. flowctl

flowctl is Estuary's command-line interface.

The workflow downloads it at runtime and uses:

~~~text
flowctl collections read
~~~

to inspect recent events.

Authentication uses:

~~~text
FLOW_AUTH_TOKEN
~~~

from GitHub secrets.

The token is not committed.

---

# 25. Snowflake materialization

The capture collection is also materialized into Snowflake.

The generated materialization uses:

~~~text
ghcr.io/estuary/materialize-snowflake:v4
~~~

Destination configuration includes:
- Snowflake host;
- database;
- schema;
- warehouse;
- role;
- user;
- JWT private-key authentication;
- timestamp behavior.

The binding targets:

~~~text
PET_INSURANCE_ESTUARY.CLAIMS
~~~

---

# 26. delta_updates and history preservation

The materialization config uses:

~~~text
delta_updates = true
hardDelete = false
~~~

The purpose is to preserve the event/history-oriented representation rather than simply mutating one final destination row.

That supports the end-to-end assertion that Snowflake contains one create, one update and one delete record for the disposable claim.

---

# 27. RSA key pair

[integrations/estuary/generate_keypair.sh](../integrations/estuary/generate_keypair.sh) generates:
- private key;
- public key;
- public-key body.

Permissions are tightened:

~~~text
directory 700
private key 600
~~~

The script refuses to overwrite existing key material.

It also deliberately does not print the private key.

These are small but useful key-handling safeguards.

---

# 28. Public key and private key roles

Public-key authentication works conceptually as:

~~~text
public key
→ configured on Snowflake user

private key
→ held by authenticated client/connector
~~~

The public key can be shared with the verifying service.

The private key must remain secret.

The repository never commits the private key.

---

# 29. Snowflake Estuary bootstrap

[integrations/estuary/snowflake_setup.sql](../integrations/estuary/snowflake_setup.sql) records a dedicated production-style service-user design.

It creates:
- PET_INSURANCE_ESTUARY_ROLE;
- PET_INSURANCE_ESTUARY service user;
- destination schema;
- required database/warehouse/schema grants;
- RSA public key configuration.

The SQL is a bootstrap template requiring administrative execution.

The bounded executed proof reused existing trial Snowflake identity, and that limitation is explicitly documented.

---

# 30. QUOTED_IDENTIFIERS_IGNORE_CASE

The Snowflake setup sets:

~~~text
QUOTED_IDENTIFIERS_IGNORE_CASE = FALSE
~~~

This avoids identifier-casing behavior that can conflict with connector expectations.

This is provider integration detail rather than a general SQL requirement.

It is worth knowing because connector compatibility often depends on session/account settings beyond basic credentials.

---

# 31. GitHub CDC proof workflow

[estuary-cdc-proof.yml](../.github/workflows/estuary-cdc-proof.yml) is manually dispatched.

Its sequence is:

~~~text
checkout
→ install Python/runtime
→ install flowctl
→ insert disposable claim
→ assert create event
→ update disposable claim
→ assert update event
→ physical delete
→ assert delete event
~~~

This is an integration test against a live managed CDC path.

---

# 32. Why this is stronger than only checking connector status

A connector dashboard saying:

~~~text
Streaming CDC Events
~~~

is useful but insufficient.

The proof performs actual source mutations and verifies the expected downstream event metadata.

That moves the evidence from configuration status to behavioral verification.

---

# 33. Executed evidence

[estuary_cdc.md](evidence/estuary_cdc.md) records the verified provider path.

Verified source state:
- wal_level = logical;
- replication-capable role;
- direct endpoint;
- isolated publication.

Verified capture:
- Estuary capture published;
- collection readable;
- source snapshot observed.

Verified mutation:
- create PASS;
- update PASS;
- delete PASS.

Verified Snowflake:
- materialization published;
- history table created/populated;
- disposable claim contained exactly one c, one u and one d event.

---

# 34. Snapshot versus CDC events

When a connector first starts, it may capture an initial snapshot of existing source data.

After initialization, WAL CDC carries subsequent committed changes.

The evidence distinguishes:
- initial collection snapshot;
- later controlled create/update/delete events.

This is important because seeing existing rows in a destination does not by itself prove ongoing CDC.

---

# 35. Custom Python path versus Estuary path

| Characteristic | Python incremental path | Estuary WAL path |
| --- | --- | --- |
| Change detection | updated_at + PK | PostgreSQL transaction log |
| Current row required? | yes | not after event is emitted |
| Physical DELETE visibility | no | yes |
| Explicit hashing | yes | connector-managed semantics |
| Explicit watermark logic | yes | connector/log position managed |
| Full-state reconciliation | yes | different CDC recovery model |
| Educational transparency | very high | managed abstraction |
| Operational simplicity | custom code to operate | managed connector complexity |
| Best use in project | teach mechanics | prove true log-based CDC |

Neither path is presented as universally superior.

They demonstrate different engineering approaches.

---

# 36. When would WAL CDC be preferable?

WAL CDC becomes attractive when:
- low-latency changes matter;
- physical deletes matter;
- source updated_at cannot be trusted;
- large tables make repeated polling expensive;
- the operational system supports stable logical replication;
- managed connector cost/operations are justified.

---

# 37. When is watermark ingestion reasonable?

A watermark-based batch can be reasonable when:
- latency can be minutes/hours rather than seconds;
- reliable updated_at semantics exist;
- source tables are bounded;
- soft deletes are available;
- implementation transparency matters;
- periodic reconciliation can close late-arrival gaps.

Architecture should follow requirements, not fashion.

---

# 38. Production concerns

The bounded proof intentionally simplifies several production concerns.

A production CDC deployment should consider:
- dedicated least-privilege source replication user;
- dedicated Snowflake destination identity;
- secret/key rotation;
- replication slot monitoring;
- WAL retention pressure;
- connector lag;
- schema evolution behavior;
- dead-letter/error handling;
- backfill/resnapshot procedure;
- alerting and SLOs;
- environment isolation.

The repository demonstrates the core mechanism and honest boundaries.

---

# 39. Competency map

| Skill | Evidence |
| --- | --- |
| PostgreSQL WAL concept | documented/executed logical replication |
| wal_level readiness | estuary_source_readiness.py |
| publication management | readiness script |
| direct Neon endpoint | estuary_flow_spec.py |
| DSN parsing/validation | estuary_flow_spec.py |
| managed CDC config | generated Estuary spec |
| CLI integration | flowctl |
| live C/U/D behavior | estuary_cdc_demo.py + workflow |
| physical DELETE capture | delete assertion |
| Snowflake connector config | materialization spec |
| asymmetric key auth | RSA scripts/setup |
| secret handling | GitHub secrets/runtime key |
| behavioral verification | live mutation proof |
| architecture trade-offs | dual-path design |

---

# 40. Interview explanation

> The custom Python ingestion is intentionally a watermark-and-reconciliation design, so I added a separate managed CDC proof for genuine PostgreSQL log capture. Neon runs PostgreSQL with wal_level=logical. A scoped publication exposes claims and the connector watermarks table to Estuary Flow through a direct non-pooler endpoint. Estuary runs in history mode. The proof creates a disposable claim, updates it, then physically deletes it; the Estuary collection is asserted to contain create, update and delete operations. That collection is materialized into Snowflake with history-preserving settings, and the final Snowflake assertion verifies exactly one c, one u and one d event for the disposable claim. This demonstrates physical-delete CDC that an updated_at polling design cannot observe after the row disappears.

If you can explain WAL, logical replication, publications, direct versus pooled endpoints, the C/U/D proof and why this path is separate from the Python watermark path, you understand the managed CDC portion of the project.
