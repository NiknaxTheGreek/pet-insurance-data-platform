# ADR 004 — dbt layering and one intentional SCD2

Status: Accepted

## Context

The project must demonstrate modeling discipline without creating dozens of unnecessary warehouse objects.

## Decision

Use four logical layers:

`RAW → STAGING → INTERMEDIATE → MARTS`

- STAGING reconstructs current source state and types VARIANT payloads.
- INTERMEDIATE contains reusable business logic and the incremental claim-event history.
- MARTS exposes trusted policy/claims outputs.
- One SCD2 model, `dim_customer_scd2`, demonstrates historical dimensional modeling.

No additional SCD2 dimensions are added unless a business requirement needs them.

## Why

One well-verified history pattern is a stronger engineering signal than duplicating the same pattern across every entity.

The customer SCD2 was proven with a real source change from Gauteng to Western Cape, creating one closed historical row and one current row.

## Consequences

Current marts deliberately use current-state policy/customer/pet context. They are not a full actuarial point-in-time warehouse.

If historical-as-of reporting became a requirement, facts would need effective-date joins to historical dimensions and an earned-premium exposure model.
