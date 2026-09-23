with latest as (
    {{ current_raw_records('claims') }}
)

select
    source_pk::varchar as claim_id,
    payload:policy_id::varchar as policy_id,
    payload:pet_id::varchar as pet_id,
    payload:claim_type::varchar as claim_type,
    payload:claim_status::varchar as claim_status,
    try_to_date(payload:claim_date::varchar) as claim_date,
    try_to_decimal(payload:claim_amount::varchar, 18, 2) as claim_amount,
    try_to_decimal(payload:approved_amount::varchar, 18, 2) as approved_amount,
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
