with latest as (
    {{ current_raw_records('policies') }}
)

select
    source_pk::varchar as policy_id,
    payload:customer_id::varchar as customer_id,
    payload:pet_id::varchar as pet_id,
    payload:plan_type::varchar as plan_type,
    payload:policy_status::varchar as policy_status,
    try_to_date(payload:start_date::varchar) as start_date,
    try_to_date(nullif(payload:end_date::varchar, '')) as end_date,
    try_to_decimal(payload:monthly_premium::varchar, 18, 2) as monthly_premium,
    try_to_timestamp_tz(payload:created_at::varchar) as created_at,
    try_to_timestamp_tz(payload:updated_at::varchar) as updated_at,
    coalesce(payload:is_deleted::boolean, false) as is_deleted,
    source_updated_at,
    raw_record_id,
    batch_id
from latest
