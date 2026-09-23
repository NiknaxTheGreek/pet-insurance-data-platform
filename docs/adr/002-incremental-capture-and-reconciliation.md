# ADR 002 — Composite watermarks plus reconciliation

Status: Accepted

## Context

A simple `updated_at > last_timestamp` predicate is unsafe when multiple rows share a timestamp and cannot recover a record that arrives with an older timestamp than the current high-water mark.

## Decision

Normal ingestion uses a composite source watermark:

`(updated_at, source_primary_key)`

ordered lexicographically. Each table stores its last processed timestamp and primary key in Snowflake CONTROL.

This fast path is complemented by a reconciliation/backfill path that compares source primary keys with RAW and inserts missing keys idempotently.

At the dbt level, `int_claim_events` uses an anti-join on `raw_record_id` rather than only `raw_record_id > max(raw_record_id)`. This was changed after live evidence exposed two historical RAW rows that a max-only predicate would never recover.

## Why

The design separates two problems:

- efficient normal change capture
- correctness recovery when late/backfilled data violates high-watermark assumptions

The controlled reliability suite proved both behaviors: a deliberately late claim was missed by the normal watermark scan, then recovered exactly once by reconciliation.

## Consequences

The anti-join is more robust but can scan both RAW and the incremental target. Snowflake EXPLAIN on the current tiny dataset assigned 13,312 bytes across four partitions for the anti-join path. That is evidence of the tradeoff, not a scale benchmark.

At larger scale, alternatives would include bounded lookback windows, source-native CDC/log sequence numbers, Streams, or explicit ingestion event IDs.
