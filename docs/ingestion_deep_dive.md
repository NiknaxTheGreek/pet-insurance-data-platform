# Ingestion deep dive: PostgreSQL to Snowflake

This is the detailed teaching companion for the core ingestion implementation.

Read this after [engineering_walkthrough.md](engineering_walkthrough.md) and keep [concepts.md](concepts.md) nearby for definitions of PostgreSQL, Snowflake, CDC, watermarks, MERGE, idempotency, transactions and reconciliation.

The implementation files are:

- [ingestion.py](../src/insurance_platform/ingestion.py) — reusable ingestion primitives and correctness rules;
- [run_ingestion.py](../src/insurance_platform/run_ingestion.py) — the live PostgreSQL → Snowflake incremental pipeline;
- [reconcile_source_state.py](../src/insurance_platform/reconcile_source_state.py) — the bounded full-state correctness path;
- [test_ingestion.py](../tests/test_ingestion.py) — unit proofs for the core semantics.

The central design is intentionally small:

~~~text
PostgreSQL current operational rows
        ↓
validate source contract
        ↓
read composite watermark
        ↓
extract ordered changes
        ↓
canonical JSON + SHA-256
        ↓
Snowflake stage
        ↓
transaction:
    count unseen versions
    MERGE unseen versions into RAW
    verify every staged version is represented
    advance watermark
    mark batch SUCCESS
        ↓
commit
        ↓
clean stage
~~~

The high-watermark path is the efficient normal path. Full-state reconciliation is the correctness path for versions that legitimately arrive behind that watermark.

---

## 1. Responsibilities: what each file owns

### ingestion.py

This module contains the rules that should remain true regardless of database connection details:

- what a watermark looks like;
- what one captured source version looks like;
- how source rows are serialized and hashed;
- how the incremental SQL predicate is formed;
- how duplicate versions are removed;
- how a new watermark is selected without moving backwards;
- how bounded batches are produced;
- which database errors are worth retrying;
- what a consistent batch reconciliation means.

A useful summary is: ingestion.py defines the semantics.

### run_ingestion.py

This module connects those semantics to real systems. It connects to PostgreSQL and Snowflake, validates contracts, loops through the five source tables, stages changes, performs the RAW MERGE, advances watermarks, records telemetry and cleans the stage.

A useful summary is: run_ingestion.py executes the semantics.

### reconcile_source_state.py

This module deliberately ignores the fast-path watermark for extraction. It reads the complete current source state and asks whether each complete current source version is represented in RAW.

A useful summary is: reconciliation repairs completeness without inventing a second write mechanism.

---

# 2. The four core data structures

## Watermark

Fields:

~~~text
updated_at
source_pk
~~~

Example:

~~~text
updated_at = 2026-09-23 19:40:00+00
source_pk  = CLM-10042
~~~

Meaning: the incremental reader has safely processed through this ordered source position.

Why two fields? Several records can share one timestamp. The primary key gives deterministic ordering inside that timestamp.

An empty Watermark means the table has not yet been incrementally processed.

Senior-level point: a watermark is progress state, not business truth. It optimizes extraction. That is why the project also has full-state reconciliation.

## TableSpec

Fields:

~~~text
name
primary_key
updated_at
~~~

Examples:

~~~text
customers      → customer_id
pets           → pet_id
policies       → policy_id
claims         → claim_id
claim_payments → payment_id
~~~

The update field defaults to updated_at. One tested ingestion engine can therefore serve five source entities without five duplicated pipelines.

## ChangeRecord

A ChangeRecord is one normalized captured source version.

Fields:

~~~text
source_table
source_pk
source_updated_at
operation
payload
payload_hash
~~~

For a claim it might conceptually look like:

~~~text
source_table      claims
source_pk         CLM-10042
source_updated_at 2026-09-23 19:40:00+00
operation         UPSERT
payload           complete current PostgreSQL row
payload_hash      SHA-256 of canonical payload JSON
~~~

This is the boundary between a PostgreSQL-specific source row and the generic ingestion representation.

## Reconciliation

Fields:

~~~text
source_rows
candidate_rows
inserted_rows
represented_rows
~~~

source_rows is the current number of rows in the source table for this batch context.

candidate_rows is how many source versions this operation considers. In normal ingestion it is the number after the watermark. In full-state reconciliation it is the number of current source versions scanned.

inserted_rows is how many staged versions were not already represented in RAW before MERGE.

represented_rows is how many staged versions are represented in RAW after MERGE.

The consistency rule is:

~~~text
0 <= inserted_rows <= candidate_rows <= source_rows
~~~

and, when represented_rows is supplied:

~~~text
represented_rows == candidate_rows
~~~

This is batch reconciliation. It proves that the staged batch is fully represented after the Snowflake transaction.

Do not confuse this with full-state reconciliation, which scans all current source rows in reconcile_source_state.py.

---

# 3. Canonical JSON and payload hashing

Functions:
- canonical_json
- _json_default
- payload_sha256

A Python dictionary must first become one deterministic text representation before it can be hashed safely.

These objects are logically equivalent:

~~~json
{"claim_id":"CLM-10042","claim_amount":11200}
~~~

~~~json
{"claim_amount":11200,"claim_id":"CLM-10042"}
~~~

canonical_json sorts keys, removes irrelevant whitespace and converts non-native JSON values consistently. That prevents key ordering from looking like a business change.

PostgreSQL NUMERIC values arrive as Decimal values. The serializer converts Decimal using fixed decimal text rather than binary floating point, which is important for financial values.

Datetime and other isoformat-capable values become ISO-formatted strings.

payload_sha256 hashes the UTF-8 canonical JSON and returns a 64-character hexadecimal digest. It is a content fingerprint, not encryption.

Proof: [test_ingestion.py](../tests/test_ingestion.py) verifies that dictionary key order does not change the hash and that PostgreSQL Decimal values hash correctly.

Why a senior cares: an idempotency key must describe business content deterministically, otherwise harmless serialization differences can generate false history.


# 4. Building the incremental PostgreSQL query

Function: **build_incremental_query**

Inputs:

~~~text
TableSpec
selected columns
current Watermark
~~~

Outputs:

~~~text
SQL string
parameter tuple
~~~

## First run

When the watermark is empty, the query is conceptually:

~~~sql
SELECT *
FROM claims
ORDER BY updated_at, claim_id
~~~

There is no lower bound because no progress has been recorded.

## Later runs

With a watermark at 2026-09-23 19:40:00+00 and CLM-10042, the query becomes:

~~~sql
SELECT *
FROM claims
WHERE (updated_at, claim_id) > (%s, %s)
ORDER BY updated_at, claim_id
~~~

The timestamp and claim ID are supplied separately as bound parameters.

PostgreSQL compares the tuple lexicographically: updated_at first, then claim_id when timestamps tie.

So if CLM-10042 and CLM-10043 share one timestamp and the watermark ends at CLM-10042, CLM-10043 is still selected.

Proof: **test_incremental_query_uses_composite_watermark** asserts the exact predicate.

Failure guard: if updated_at exists in the watermark but source_pk does not, the function raises ValueError rather than accepting an ambiguous half-watermark.

---

# 5. Converting a PostgreSQL row into a ChangeRecord

Function: **row_to_change**

Input:

~~~text
TableSpec
PostgreSQL row mapping
~~~

Process:

1. copy the row into a plain payload dictionary;
2. read the primary key;
3. read updated_at;
4. require updated_at to be a datetime;
5. translate the soft-delete flag into an operation;
6. hash the full canonical payload;
7. return a ChangeRecord.

Operation mapping:

~~~text
is_deleted = false → UPSERT
is_deleted = true  → DELETE
~~~

Important limitation: the custom Python path does not observe a physical PostgreSQL DELETE after the row has disappeared. Its delete mechanism is the source soft-delete column. The independent Neon → Estuary path demonstrates actual physical-delete CDC through PostgreSQL WAL.

Proof: **test_row_to_change_marks_soft_delete** verifies that a deleted source row becomes operation DELETE.

---

# 6. Version identity and duplicate removal

Functions:
- version_identity
- deduplicate_changes

The complete version identity is:

~~~text
source_table
source_pk
source_updated_at
payload_hash
~~~

Primary key alone is insufficient because one claim can have multiple valid historical versions.

Primary key plus timestamp alone is also weaker than complete content identity. The payload hash makes the captured version deterministic.

deduplicate_changes keeps the first occurrence of each complete identity within the in-memory candidate set.

Proof: **test_deduplicate_changes_is_idempotent** supplies the same ChangeRecord twice and expects one result.

---

# 7. Selecting the next watermark safely

Functions:
- newest_watermark
- max_watermark

newest_watermark finds the maximum candidate by:

~~~text
(source_updated_at, source_pk)
~~~

It then compares that position with the previous watermark. The final result cannot move backwards.

Late-data example:

~~~text
current watermark: 2026-09-23 19:40 / CLM-10042
late version:      2026-09-21 12:00 / CLM-LATE
~~~

The late version is valid data, but it must not rewind the fast-path cursor. Full-state reconciliation can insert the late version while max_watermark keeps normal progress at September 23.

Tests verify both primary-key tie-breaking and non-regression for late versions.

---

# 8. Bounded chunks

Function: **chunked**

This yields slices of a configured maximum size.

_stage_records uses a default chunk size of 1000 rows.

The point is not to turn the whole pipeline into row-by-row processing. Python sends bounded parameter groups into the stage, while Snowflake later performs one relational MERGE for the staged batch.

A non-positive chunk size is rejected immediately.

---

# 9. Retry classification

Functions:
- is_transient_db_error
- retry_call

Not every failure should be retried.

The implementation recognizes selected transient SQLSTATE categories such as connection exceptions and transaction rollback/serialization states, plus selected lock/server-shutdown states and network-oriented error wording.

A ValueError caused by bad input is not transient and is raised immediately.

With defaults, exponential delays are:

~~~text
attempt 1 fails → wait 2 seconds
attempt 2 fails → wait 4 seconds
attempt 3 fails → raise
~~~

Unit tests verify both a transient failure that later succeeds and a permanent failure that is not retried.

Senior-level point: blind retry can amplify a permanent defect. Retry policy should classify failures, and the repeated operation must be safe. The idempotent RAW MERGE plus rollback semantics make bounded retry appropriate here.

---

# 10. run_ingestion.py configuration

The TABLES tuple defines the complete custom-ingestion source scope:

~~~text
customers      → customer_id
pets           → pet_id
policies       → policy_id
claims         → claim_id
claim_payments → payment_id
~~~

Snowflake physical object names are environment-configurable with deterministic project defaults:

~~~text
PET_INSURANCE_RAW.SOURCE_RECORDS
PET_INSURANCE_CONTROL.INGESTION_WATERMARKS
PET_INSURANCE_CONTROL.INGESTION_BATCHES
PET_INSURANCE_CONTROL.INGESTION_STAGE
~~~

This keeps the implementation portable between environments without hiding the default architecture.

---

# 11. Required environment values

Function: **_required**

It returns a non-empty environment value or raises RuntimeError.

Connection identity includes:

~~~text
POSTGRES_DSN
SNOWFLAKE_ACCOUNT
SNOWFLAKE_USER
SNOWFLAKE_ROLE
SNOWFLAKE_WAREHOUSE
SNOWFLAKE_DATABASE
SNOWFLAKE_TOKEN
~~~

The code does not silently invent missing credentials or fall back to committed secrets.


# 12. Reading the Snowflake watermark

Function: **_read_watermark**

Query:

~~~sql
SELECT LAST_UPDATED_AT, LAST_SOURCE_PK
FROM PET_INSURANCE_CONTROL.INGESTION_WATERMARKS
WHERE SOURCE_TABLE = %s
~~~

If no row exists, an empty Watermark is returned. Otherwise the two stored progress fields become the table watermark.

Values such as SOURCE_TABLE are bound separately from SQL text. Physical object names cannot be ordinary SQL value parameters, so those come from project-controlled constants and environment configuration.

The source table names themselves come from hard-coded TableSpec definitions rather than arbitrary user input.

---

# 13. Counting current source rows

Function: **_source_count**

Conceptual query:

~~~sql
SELECT COUNT(*) AS n
FROM claims
~~~

Purpose: provide a simple source-size reference for telemetry and reconciliation invariants.

At very large production scale, a full COUNT on every normal incremental cycle could become too expensive and would be revisited. For this bounded project it improves transparency and testability.

---

# 14. Extracting source changes

Function: **_extract**

Steps:

1. call build_incremental_query;
2. execute the SQL against PostgreSQL;
3. fetch matching rows;
4. convert each row with row_to_change.

Output:

~~~text
list of ChangeRecord objects
~~~

This separation is useful because database access and change semantics can be tested independently.

---

# 15. Writing the STARTED audit row

Function: **_write_batch_started**

The batch ID combines:

~~~text
GitHub run ID or local marker
source table
short UUID
~~~

The STARTED record captures:

~~~text
batch ID
source table
start time
status
source row count
rows extracted
watermark before
GitHub run ID
notes
~~~

It uses a Snowflake MERGE keyed by BATCH_ID so the audit insertion is stable for one batch identifier.

## Why STARTED is outside the critical data transaction

The Snowflake connection runs with autocommit enabled except when the code explicitly executes BEGIN.

Therefore the STARTED audit row can remain durable even if the later RAW/watermark transaction is rolled back.

This lets the system preserve operational evidence of an attempted batch without compromising data atomicity.

---

# 16. Staging candidate records

Function: **_stage_records**

Input:

~~~text
ChangeRecord list
batch ID
batch size
~~~

If there are no records, the function returns immediately.

Each candidate is bound into:

~~~text
BATCH_ID
SOURCE_TABLE
SOURCE_PK
SOURCE_UPDATED_AT
OPERATION
PAYLOAD_JSON
PAYLOAD_HASH
~~~

The stage INSERT binds ordinary values. PAYLOAD_JSON is canonical JSON text.

Snowflake later converts that text to VARIANT during the set-based MERGE.

Data path:

~~~text
Python mapping
→ canonical JSON text
→ CONTROL.INGESTION_STAGE.PAYLOAD_JSON
→ PARSE_JSON during MERGE
→ RAW.SOURCE_RECORDS.PAYLOAD VARIANT
~~~

Why not call PARSE_JSON directly inside the executemany VALUES clause? Keeping the connector binding to simple values makes the batch insert more reliable and easier to test.

Proof: **test_stage_records_uses_connector_safe_values_binding** verifies that the INSERT contains PAYLOAD_JSON and does not embed PARSE_JSON in the parameterized VALUES clause.

---

# 17. Counting unseen staged versions

Function: **_count_unrepresented_staged**

This runs before RAW MERGE.

Conceptually:

~~~sql
SELECT COUNT(*)
FROM stage
WHERE batch_id = ?
  AND NOT EXISTS (
      SELECT 1
      FROM raw
      WHERE raw.source_table      = stage.source_table
        AND raw.source_pk         = stage.source_pk
        AND raw.source_updated_at = stage.source_updated_at
        AND raw.payload_hash      = stage.payload_hash
  )
~~~

This count is the expected number of new historical versions.

Why calculate it before MERGE? After MERGE all valid candidates should be represented, so the code would no longer know which ones existed beforehand.

Because candidates were deduplicated before staging, the pre-MERGE anti-join gives a clean expected insertion count.

---

# 18. The RAW MERGE

Function: **_merge_staged_raw**

Target:

~~~text
PET_INSURANCE_RAW.SOURCE_RECORDS
~~~

Source:

~~~text
PET_INSURANCE_CONTROL.INGESTION_STAGE
filtered to one BATCH_ID
~~~

Identity condition:

~~~text
SOURCE_TABLE
SOURCE_PK
SOURCE_UPDATED_AT
PAYLOAD_HASH
~~~

Action:

~~~text
WHEN NOT MATCHED → INSERT
~~~

There is intentionally no matched UPDATE.

RAW is append-only historical capture.

An already represented source version should remain unchanged. A genuinely new source version should become a new RAW row.

The MERGE converts PAYLOAD_JSON to Snowflake VARIANT with PARSE_JSON.

Idempotency:

~~~text
first execution: absent identity → insert
replay: same identity exists → no insert
~~~

---

# 19. Counting represented staged versions

Function: **_count_represented_staged**

This runs after MERGE, still inside the explicit transaction.

It asks whether each staged candidate can now be found in RAW by the complete version identity.

Required invariant:

~~~text
represented_rows == candidate_rows
~~~

This is stronger than merely assuming a MERGE that did not throw an exception must have produced the intended representation.

---

# 20. Advancing the watermark

Function: **_write_watermark**

It uses Snowflake MERGE keyed by SOURCE_TABLE.

Existing source table:

~~~text
update LAST_UPDATED_AT
update LAST_SOURCE_PK
update audit timestamp
~~~

Missing source table:

~~~text
insert first watermark
~~~

The watermark write occurs inside the same transaction as RAW MERGE and SUCCESS status.

The caller only writes it when candidate_count is non-zero. An unchanged incremental run therefore does not manufacture a new progress position.

---

# 21. Marking SUCCESS

Function: **_finalize_batch_success**

The durable STARTED record becomes SUCCESS and gains:

~~~text
completion time
rows inserted
watermark after
duration
retry count
reconciliation status
~~~

Error fields are cleared.

This update is inside the explicit data transaction.

Therefore:

~~~text
RAW version
+
watermark
+
SUCCESS audit state
~~~

become durable together.

---

# 22. Marking FAILED

Function: **_finalize_batch_failure**

It records:

~~~text
STATUS = FAILED
duration
retry count
RECONCILIATION_STATUS = FAILED
exception class
truncated exception message
~~~

This happens after the critical transaction has rolled back.

Because it is outside that rolled-back transaction, the failure audit can remain durable.

The design therefore provides both correct rollback and persistent operational evidence.

---

# 23. Cleaning the shared stage

Function: **_cleanup_stage**

Query:

~~~sql
DELETE FROM PET_INSURANCE_CONTROL.INGESTION_STAGE
WHERE BATCH_ID = %s
~~~

Cleanup runs after success and is attempted after failure.

If cleanup itself fails while handling an original failure, the cleanup error is logged separately instead of replacing the original exception.

BATCH_ID is what makes one attempt independently cleanable in the shared stage.


# 24. The critical transaction: _apply_staged_batch

This function is the heart of write correctness.

Inputs include:

~~~text
table specification
batch ID
watermark after
candidate count
source row count
start time
retry attempt
~~~

Execution:

~~~text
BEGIN

1. count currently unrepresented staged versions
2. MERGE staged versions into RAW
3. optional injected failure point for atomicity testing
4. count represented staged versions
5. construct Reconciliation
6. reject inconsistent representation
7. advance watermark if candidates exist
8. mark batch SUCCESS

COMMIT
~~~

Any exception causes:

~~~text
ROLLBACK
~~~

and is re-raised.

## The injected failure hook

INGESTION_FAIL_AFTER_MERGE_TABLE can deliberately raise after RAW MERGE and before watermark advancement.

This is a test hook, not normal business logic. It lets the repository prove the transaction boundary rather than merely claim it.

Verified result in [transaction_atomicity.md](evidence/transaction_atomicity.md):

- RAW MERGE rolled back;
- watermark did not advance;
- FAILED audit remained;
- stage rows were cleaned;
- normal retry loaded the source version once;
- unchanged replay inserted zero.

That proves atomicity plus safe retry behavior.

---

# 25. Per-table orchestration: _process_table

This function coordinates one source table from beginning to end.

## Phase A: identify the attempt

A unique batch ID is created and both a wall-clock timestamp and perf_counter start value are recorded.

The wall clock is useful for audit timestamps. perf_counter is appropriate for measuring elapsed duration.

## Phase B: inspect source and progress state

The function reads:

~~~text
watermark before
source row count
incremental candidates
watermark after
~~~

Candidates are deduplicated before staging.

## Phase C: persist STARTED telemetry

The STARTED audit is written before the critical data transaction.

## Phase D: stage candidates

Candidate versions are inserted under the unique BATCH_ID.

## Phase E: execute with bounded retry

A nested operation calls _apply_staged_batch. retry_call supplies the attempt number.

Recorded retry count is:

~~~text
attempt - 1
~~~

so a first-attempt success records zero retries.

## Phase F: finish

Success:

~~~text
clean stage
log reconciliation
return Reconciliation
~~~

Failure:

~~~text
mark FAILED
attempt stage cleanup
log exception
re-raise
~~~

A table cannot fail silently while the overall run continues as though it succeeded.

---

# 26. Whole-run orchestration: run

run is the executable entry point.

## PostgreSQL connection

POSTGRES_DSN is required.

psycopg uses dictionary rows so source columns can be addressed by field name.

## Snowflake connection

The account, user, role, warehouse and database are required.

Authentication uses:

~~~text
WORKLOAD_IDENTITY
OIDC
short-lived token
~~~

rather than a Snowflake password committed to the repository.

## Why Snowflake autocommit is enabled

Outside explicit BEGIN/COMMIT blocks, audit/staging operations commit independently.

That supports this deliberate lifecycle:

~~~text
durable STARTED audit + staged candidates
        ↓
explicit atomic RAW/watermark/SUCCESS transaction
        ↓
durable cleanup or FAILED audit
~~~

## Source-contract gate

Before any table is processed, validate_source_contracts checks PostgreSQL against the contracts directory.

A breaking source structure is therefore rejected before normal ingestion.

## Table order

The run processes:

~~~text
customers
pets
policies
claims
claim_payments
~~~

This mirrors source dependency direction and keeps evidence easy to reason about.

## Resource cleanup

Both PostgreSQL and Snowflake connections close in a finally block, including when the run fails.

---

# 27. Normal batch reconciliation vs full-state reconciliation

This distinction is essential.

## Normal incremental path

run_ingestion.py asks:

~~~text
Which source rows sort after the saved watermark?
~~~

Then _apply_staged_batch asks:

~~~text
Are all of those staged candidates represented in RAW after MERGE?
~~~

That is incremental extraction plus batch reconciliation.

## Full-state path

reconcile_source_state.py asks:

~~~text
What is the complete current source state regardless of watermark?
~~~

It converts every current row to the same version identity, stages those versions and reuses the same transactional MERGE.

That is full-state reconciliation.

Why not simply reset the watermark? Because moving ordered progress backwards creates broad reprocessing without directly identifying which versions are missing. Complete version identity gives a more precise repair mechanism.

---

# 28. Full-state reconciliation step by step

For each source table, [reconcile_source_state.py](../src/insurance_platform/reconcile_source_state.py):

1. reads the current watermark;
2. selects every current PostgreSQL row ordered by updated_at + primary key;
3. converts each row into ChangeRecord;
4. deduplicates complete identities;
5. computes a non-regressing watermark_after;
6. writes a STARTED audit;
7. stages all current versions;
8. calls the same _apply_staged_batch transaction used by normal ingestion;
9. records how many versions were newly inserted;
10. cleans the stage;
11. logs the reconciliation result.

The recovery path therefore does not invent a second warehouse-write algorithm. It reuses the same tested stage, MERGE, representation checks and transaction boundary.

---

# 29. CLM-10042 through the final PAID event

The focal claim progresses:

~~~text
SUBMITTED
→ APPROVED
→ PAID
~~~

Final state:

~~~text
claim_id         CLM-10042
claim_amount     R11,200
approved_amount  R9,700
paid_amount      R9,700
~~~

The source PAID mutation is implemented in [apply_t4_demo.py](../src/insurance_platform/apply_t4_demo.py) at:

~~~text
2026-09-23 19:40:00+00
~~~

## Step 1: PostgreSQL changes

The claim becomes PAID and its updated_at moves to the event timestamp. A R9,700 payment is inserted.

PostgreSQL remains the operational current-state source.

## Step 2: the claims watermark is read

If the saved claims watermark sorts before this PAID version, the incremental query selects CLM-10042.

## Step 3: the row becomes a ChangeRecord

Conceptually:

~~~text
source_table      claims
source_pk         CLM-10042
source_updated_at 2026-09-23 19:40:00+00
operation         UPSERT
payload           complete claim row
payload_hash      deterministic SHA-256
~~~

## Step 4: the version is staged

The stage receives the source identity, operation, canonical JSON and hash under the batch ID.

## Step 5: unseen versions are counted

If this PAID source version is absent from RAW:

~~~text
expected new insert = 1
~~~

If the exact version already exists:

~~~text
expected new insert = 0
~~~

## Step 6: RAW MERGE executes

If absent, Snowflake appends a new historical RAW row.

Older SUBMITTED and APPROVED versions remain unchanged.

## Step 7: representation is checked

The staged PAID version must be findable in RAW after MERGE.

Otherwise the transaction fails.

## Step 8: watermark advances

Only after successful representation can the claims watermark advance to the new ordered position.

## Step 9: SUCCESS is recorded

The batch stores insertion count, duration, retry count and CONSISTENT status.

## Step 10: COMMIT

RAW, watermark and SUCCESS state become durable together.

## Step 11: dbt uses the history in two ways

INT_CLAIM_EVENTS preserves historical claim versions.

STG_CLAIMS and FCT_CLAIMS reconstruct and expose the latest current claim state.

The same warehouse therefore supports both historical lineage and current analytical truth.

---

# 30. Unchanged normal replay

If PostgreSQL has no rows after the saved watermark:

~~~text
candidates = 0
~~~

_stage_records performs no insert.

The transaction records a valid zero-candidate SUCCESS and does not rewrite the watermark.

Result:

~~~text
0 candidates
0 inserted
0 represented
CONSISTENT
~~~

The verified unchanged-source run is documented in [live_ingestion.md](evidence/live_ingestion.md): all five source tables completed with zero candidates and zero inserts.

---

# 31. Unchanged full-state reconciliation replay

Full-state reconciliation deliberately scans all current source rows.

So candidate_rows can be large even when nothing changed.

If every complete identity already exists in RAW:

~~~text
inserted_rows = 0
represented_rows = candidate_rows
~~~

Meaning: the current source state is already completely represented and no history needs to be appended.

That is different from the normal path's zero-candidate result.

---

# 32. Late new key behind the watermark

Suppose the current watermark is later than September 21, then a new claim is inserted with:

~~~text
updated_at = 2026-09-21 12:00
~~~

Normal incremental ingestion correctly does not select it because it is behind the ordered cursor.

Full-state reconciliation sees the row, calculates its complete version identity, finds that identity missing in RAW and inserts it.

newest_watermark does not move the high watermark backwards.

Result:

~~~text
late data recovered
normal incremental progress preserved
~~~

The reliability workflow verifies this behavior.

---

# 33. Late changed version of an existing key

This is stronger than a late new key.

The primary key already exists in RAW, but the current source payload changes while updated_at is still behind the high watermark.

A recovery rule that only asks whether the primary key exists would fail.

This project's identity includes:

~~~text
primary key
source updated timestamp
payload hash
~~~

so the changed version is recognized as a distinct source version and appended once.

This demonstrates version reconciliation rather than entity-existence checking.

---

# 34. Soft-delete behavior

If PostgreSQL changes is_deleted from false to true and updates updated_at:

~~~text
row_to_change → operation DELETE
~~~

RAW still preserves the complete historical payload.

Current-state dbt models select the latest version and exclude deleted business records where appropriate.

Therefore:

~~~text
RAW retains deletion history
+
trusted current marts omit deleted entities
~~~

Actual physical deletion is demonstrated separately by the Estuary WAL path.

---

# 35. Failure behavior

| Failure | Intended result |
| --- | --- |
| PostgreSQL extraction fails | no RAW transaction and no watermark advancement |
| source contract breaks | stop before ingestion |
| stage bind fails | FAILED batch; cleanup attempted |
| transient database failure | bounded retry |
| permanent logic/data failure | raise without blind retry |
| RAW MERGE fails | rollback |
| staged representation incomplete | rollback |
| injected failure after MERGE | RAW/watermark/SUCCESS rollback |
| transaction fails | durable FAILED audit outside rolled-back transaction |
| stage cleanup fails during failure handling | log separately; preserve original exception |
| late version behind watermark | recover through full-state reconciliation |
| unchanged normal replay | zero candidates and zero inserts |
| unchanged full reconciliation | zero inserts with all current versions represented |

---

# 36. Test and evidence map

Unit tests: [test_ingestion.py](../tests/test_ingestion.py)

| Behavior | Proof |
| --- | --- |
| composite watermark SQL | test_incremental_query_uses_composite_watermark |
| canonical hash ignores key order | test_payload_hash_is_order_independent |
| Decimal values hash safely | test_payload_hash_supports_postgres_decimal_values |
| soft delete becomes DELETE | test_row_to_change_marks_soft_delete |
| duplicate version removed | test_deduplicate_changes_is_idempotent |
| timestamp + PK tie-break | test_newest_watermark_uses_updated_at_then_pk |
| late state cannot rewind watermark | test_newest_watermark_never_moves_backwards_for_late_state |
| complete staged representation required | test_reconciliation_requires_every_candidate_to_be_represented |
| transient retry succeeds after bounded retries | test_retry_call_retries_transient_failure_then_succeeds |
| permanent error is not retried | test_retry_call_does_not_retry_non_transient_failure |
| connector-safe JSON stage binding | test_stage_records_uses_connector_safe_values_binding |

Integration evidence:

- [live ingestion](evidence/live_ingestion.md)
- [transaction atomicity](evidence/transaction_atomicity.md)
- [reliability suite](evidence/reliability.md)
- [scale benchmark](evidence/scale_benchmark.md)

Unit tests prove isolated semantics; workflow evidence proves those semantics against actual database systems.

---

# 37. Why the design is intentionally minimal

The core requirements do not justify Kafka, Spark, Kubernetes, a custom message broker or a permanent orchestration cluster.

The essential core is:

~~~text
PostgreSQL
Python
Snowflake
dbt
GitHub Actions
Docker
~~~

Additional technologies exist only where they prove a distinct capability:

~~~text
Dagster
→ orchestration semantics

Neon + Estuary
→ genuine WAL/log-based CDC

BigQuery Sandbox
→ transferable cloud warehouse and reconciliation capability
~~~

The engineering point is not the number of logos. It is that every component has a specific responsibility.

---

# 38. Trade-offs at larger production scale

## Full source COUNT

Current choice: COUNT each source table for telemetry and invariants.

Advantage: explicit and easy to verify.

Larger-scale concern: repeated full counts can be expensive.

Possible extension: cheaper metadata or separately scheduled reconciliation metrics.

## Full-state reconciliation

Current choice: bounded complete scan.

Advantage: strong and simple correctness proof.

Larger-scale concern: too expensive for extremely large tables at high frequency.

Possible extensions: partitioned reconciliation, key-range jobs, rolling checksums or source-native CDC.

## Shared staging table

Current choice: one shared stage isolated by BATCH_ID.

Advantage: simple physical design and easy auditability.

Larger-scale concern: high concurrency may require retention, partitioning or transient batch-stage strategies.

## Composite timestamp watermark

Current choice: updated_at + primary key plus reconciliation.

Advantage: transparent and easy to reason about.

Limitation: depends on reliable source update semantics and cannot detect a vanished physical row.

Extension: WAL/log-based CDC, demonstrated separately with Estuary.

## In-process extraction

Current choice: fetch bounded project candidates into Python memory.

Advantage: clear implementation and sufficient for demonstrated scale.

Larger-scale extensions: server-side cursors, chunked streaming extraction, bulk file transfer or managed CDC.

The correct engineering position is not that this design handles infinite scale. It is that the design is appropriate for the demonstrated workload, its limits are explicit, and architecture should change when measured scale or latency justifies it.

---

# 39. Study and reproduction order

For local verification:

~~~bash
make bootstrap
make test
make postgres-up
make postgres-smoke
make postgres-down
~~~

For live Snowflake execution, follow [reproduction.md](reproduction.md).

Study the functions in this order:

1. Watermark and TableSpec;
2. canonical_json and payload_sha256;
3. row_to_change and version_identity;
4. build_incremental_query;
5. deduplicate_changes and newest_watermark;
6. _read_watermark and _extract;
7. _write_batch_started;
8. _stage_records;
9. _count_unrepresented_staged;
10. _merge_staged_raw;
11. _count_represented_staged;
12. _write_watermark;
13. _finalize_batch_success and _finalize_batch_failure;
14. _apply_staged_batch;
15. _process_table;
16. run;
17. reconcile_source_state.run.

Once those pieces make sense individually, the complete pipeline is no longer mysterious.

---

# 40. 45-second interview explanation

A technically precise compressed explanation is:

> The custom ingestion path reads mutable PostgreSQL tables incrementally using a composite updated_at plus primary-key watermark. Each source row becomes a deterministic ChangeRecord with canonical JSON and a SHA-256 payload fingerprint. Candidates are staged in Snowflake and merged into append-only RAW using complete source-version identity. RAW insertion, watermark advancement and successful batch state commit in one explicit transaction, while post-MERGE reconciliation verifies every staged candidate is represented. Because high watermarks can miss legitimately late rows, a separate full-state reconciliation scans current source state and appends missing versions idempotently without moving the watermark backwards. dbt then reconstructs current state and historical analytical models from RAW.

If you can explain every phrase in that paragraph, point to the implementing function and describe its failure behavior, you understand the ingestion mechanism rather than merely recognizing the technology names.
