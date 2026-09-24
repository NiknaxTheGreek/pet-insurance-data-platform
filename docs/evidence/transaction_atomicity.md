# Transaction atomicity evidence

Run: 35989925581  
Workflow: Transaction Atomicity  
Result: PASS

Injected failure point:
After the claims RAW MERGE and before watermark update.

Observed:
- injected failure was detected as expected;
- RAW rollback assertion passed;
- FAILED batch audit assertion passed;
- failed-stage cleanup assertion passed;
- watermark did not advance with an uncommitted RAW state;
- normal retry later loaded the claim exactly once;
- final unchanged replay inserted zero rows.

The source record used for the proof was `CLM-TX-1`.

This demonstrates that RAW mutation and watermark progression are an atomic unit, while the failure audit remains durable outside the rolled-back transaction.
