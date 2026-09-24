# Live ingestion evidence

Run: 35988189813  
Workflow: Live Incremental Ingestion  
Result: PASS

Scenario:
- Validate all five live PostgreSQL source contracts.
- Run hardened set-based incremental ingestion.
- Verify batch audit and health state.

Actual evidence:
- source-contract validation: 5 tables, 0 additive tables.
- customers: source rows 3, candidates 0, inserted 0, represented 0.
- pets: source rows 3, candidates 0, inserted 0, represented 0.
- policies: source rows 3, candidates 0, inserted 0, represented 0.
- claims: source rows 5, candidates 0, inserted 0, represented 0.
- claim_payments: source rows 3, candidates 0, inserted 0, represented 0.
- all five batch rows were asserted SUCCESS and CONSISTENT.
- staging-table cleanup and ingestion-health queries passed.

Interpretation:
This is an unchanged-source replay of the hardened implementation. It proves the set-based path remains idempotent and that operational telemetry is populated.
