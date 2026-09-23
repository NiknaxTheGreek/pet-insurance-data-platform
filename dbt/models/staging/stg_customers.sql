with latest as (
    {{ current_raw_records('customers') }}
)

select
    source_pk::varchar as customer_id,
    payload:first_name::varchar as first_name,
    payload:last_name::varchar as last_name,
    payload:province::varchar as province,
    try_to_timestamp_tz(payload:created_at::varchar) as created_at,
    try_to_timestamp_tz(payload:updated_at::varchar) as updated_at,
    coalesce(payload:is_deleted::boolean, false) as is_deleted,
    source_updated_at,
    raw_record_id,
    batch_id
from latest
