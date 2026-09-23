# Performance and cost evidence

This project intentionally avoids fabricated benchmark claims. The live dataset is small, so performance evidence is limited to verified warehouse configuration, query plans, row counts, and repeat-run behavior.

## Verified Snowflake compute configuration

The live CI environment uses the existing Snowflake trial learning warehouse:

- warehouse: `SNOWFLAKE_LEARNING_WH`
- type: `STANDARD`
- size: `X-Small`
- auto-resume: `true`
- auto-suspend: `300` seconds

The project does not provision additional warehouses for CI.

## Current RAW footprint

At the latest performance-evidence run:

| Source table | RAW versions | Distinct source keys |
| --- | ---: | ---: |
| customers | 4 | 3 |
| pets | 3 | 3 |
| policies | 3 | 3 |
| claims | 8 | 5 |
| claim_payments | 6 | 3 |

These counts include controlled demo/failure-history versions and therefore intentionally exceed current-source row counts for mutable entities.

## Incremental claim-event model

`INT_CLAIM_EVENTS` currently contains all 8 RAW claim versions.

Verified checks:

- claim event rows: 8
- missing RAW claim event rows: 0
- two consecutive incremental dbt runs completed successfully
- final incremental no-op assertion: pass

### Why the implementation changed

The first version used:

`raw_record_id > max(raw_record_id already modeled)`

Live testing exposed a correctness gap: two historical RAW rows were absent even though no rows were above the model's maximum RAW ID. A max-only predicate could never recover those rows.

The model was changed to a backfill-safe anti-join:

`NOT EXISTS (existing.raw_record_id = raw.raw_record_id)`

The next run repaired the model from 6 to 8 claim-event rows, and subsequent runs report 0 missing rows.

This favors correctness and recoverability over an artificially cheap high-watermark-only scan.

## Snowflake EXPLAIN evidence

On the current tiny dataset, Snowflake explains the missing-event check as an anti-join between RAW and `INT_CLAIM_EVENTS`.

Verified plan statistics:

- partitions total: 4
- partitions assigned: 3
- bytes assigned: 13,312
- RAW scan bytes assigned: 8,704
- existing incremental target scan bytes assigned: 4,608

These figures are useful as proof that the intended plan is actually executing. They are not a production benchmark.

## Cost controls and tradeoffs

Current controls:

- X-Small warehouse
- automatic suspension after five minutes
- automatic resume
- incremental ingestion by source watermark
- idempotent MERGE behavior
- dbt incremental claim-event processing
- ephemeral Docker source in CI
- no always-on orchestrator or streaming infrastructure
- no extra Snowflake warehouse created for this project

The anti-join incremental strategy scans both RAW metadata and the target key set. At larger scale, this would be revisited using one or more of:

- source-native CDC/log sequence numbers
- Snowflake Streams
- explicit immutable ingestion event IDs
- bounded lookback windows plus reconciliation
- table clustering/search optimization when justified by query profile
- separate workload-specific warehouse sizing

## What is deliberately not claimed

This repository does not claim a percentage speedup, production throughput, production SLA, or monetary saving from the small demo workload. Those would require representative volume and controlled benchmark conditions.
