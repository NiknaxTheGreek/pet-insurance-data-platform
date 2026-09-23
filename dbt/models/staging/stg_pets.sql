with latest as (
    {{ current_raw_records('pets') }}
)

select
    source_pk::varchar as pet_id,
    payload:customer_id::varchar as customer_id,
    payload:pet_name::varchar as pet_name,
    payload:species::varchar as species,
    payload:breed::varchar as breed,
    try_to_date(payload:date_of_birth::varchar) as date_of_birth,
    try_to_timestamp_tz(payload:created_at::varchar) as created_at,
    try_to_timestamp_tz(payload:updated_at::varchar) as updated_at,
    coalesce(payload:is_deleted::boolean, false) as is_deleted,
    source_updated_at,
    raw_record_id,
    batch_id
from latest
