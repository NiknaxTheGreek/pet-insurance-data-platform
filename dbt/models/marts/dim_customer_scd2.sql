with customer_versions as (
    select
        source_pk::varchar as customer_id,
        payload:province::varchar as province,
        coalesce(payload:is_deleted::boolean, false) as is_deleted,
        source_updated_at::timestamp_tz as effective_from,
        lead(source_updated_at) over (
            partition by source_pk
            order by source_updated_at, raw_record_id
        )::timestamp_tz as effective_to
    from {{ source('raw', 'source_records') }}
    where lower(source_table) = 'customers'
)

select
    customer_id::varchar as customer_id,
    province::varchar as province,
    is_deleted::boolean as is_deleted,
    effective_from::timestamp_tz as effective_from,
    effective_to::timestamp_tz as effective_to,
    (effective_to is null)::boolean as is_current
from customer_versions
