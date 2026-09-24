# Reliability evidence

Run: 35989125299  
Workflow: Reliability Failure Suite  
Result: PASS

Executed scenarios:
1. Invalid payment date ingested.
2. dbt test intentionally fails.
3. Source repaired and re-ingested.
4. dbt test passes.
5. New late claim inserted behind watermark.
6. Normal watermark scan misses it.
7. Full-state reconciliation recovers it exactly once.
8. Existing-key late claim baseline inserted behind watermark.
9. Normal ingestion misses it.
10. Reconciliation recovers baseline.
11. Same key mutated again behind watermark.
12. Normal ingestion misses the late version.
13. Reconciliation preserves both versions exactly once.
14. Soft delete propagated.
15. Full dbt build passes.
16. Final unchanged replay inserts zero rows.

Selected actual evidence:
- full-state claims reconciliation recovered 1 missing version while representing every current source version.
- replay reconciliation produced no duplicate.
- soft-delete RAW and mart assertions passed.
- final replay assertion passed.

Key conclusion:
Reconciliation is based on complete source-version identity, not merely “does this primary key exist?”.
