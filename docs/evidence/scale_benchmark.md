# Controlled scale benchmark evidence

Run: 35990122190  
Workflow: Scale Benchmark  
Result: PASS

Environment:
- clean PostgreSQL container;
- isolated Snowflake benchmark RAW/CONTROL schemas;
- same contract validator and set-based ingestion implementation as the live path.

Generated deterministic dataset:
- customers: 10,000
- pets: 14,916
- policies: 14,916
- claims: 29,828
- claim_payments: 13,296
- total rows: 82,956

First ingestion:
- customers: 10,000 candidates / 10,000 inserted / 10,000 represented
- pets: 14,916 / 14,916 / 14,916
- policies: 14,916 / 14,916 / 14,916
- claims: 29,828 / 29,828 / 29,828
- claim_payments: 13,296 / 13,296 / 13,296
- all reconciliations reported consistent.

No-change replay:
- all five tables: 0 candidates / 0 inserted.

This is a controlled benchmark, not an enterprise-scale throughput claim.
