with latest as (
    {{ current_raw_records('claim_payments') }}
)

select
    source_pk::varchar as payment_id,
    payload:claim_id::varchar as claim_id,
    try_to_date(payload:payment_date::varchar) as payment_date,
    try_to_decimal(payload:payment_amount::varchar, 18, 2) as payment_amount,
    payload:payment_status::varchar as payment_status,
    try_to_timestamp_tz(payload:created_at::varchar) as created_at,
    coalesce(
        try_to_timestamp_tz(payload:updated_at::varchar),
        source_updated_at
    ) as updated_at,
    coalesce(payload:is_deleted::boolean, false) as is_deleted,
    source_updated_at,
    raw_record_id,
    batch_id
from latest
