# ADR 001 — Append-only RAW in Snowflake

Status: Accepted

## Context

The PostgreSQL source is mutable. Claims change status and amount, payments arrive later, customer attributes change, and records may be soft-deleted. Loading only the latest source row would make prior states impossible to reconstruct and would weaken auditability.

## Decision

Store every accepted source version in `PET_INSURANCE_RAW.SOURCE_RECORDS` as an append-only record with:

- source table
- source primary key
- source `updated_at`
- operation (`UPSERT` / `DELETE`)
- complete source payload as Snowflake `VARIANT`
- deterministic SHA-256 payload hash
- ingestion batch ID
- ingestion timestamp

The ingestion MERGE key is the source table + primary key + source timestamp + payload hash. Replaying the same source version therefore inserts nothing.

## Why

This keeps ingestion simple while preserving enough history for:

- claim state reconstruction
- SCD2 derivation
- audit/debugging
- replay and reconciliation
- soft-delete propagation

It also demonstrates a justified use of semi-structured Snowflake `VARIANT`: RAW preserves the source payload without forcing every operational change into a rigid landing schema.

## Consequences

RAW is not the analytical interface. dbt staging must type the payload and choose current state explicitly. Storage grows with source changes, but the demo dataset is small and historical correctness is more valuable than overwriting prior states.

A production implementation at much larger scale would evaluate retention policy, clustering/search optimization, partition behavior, and possibly table-specific RAW structures.
