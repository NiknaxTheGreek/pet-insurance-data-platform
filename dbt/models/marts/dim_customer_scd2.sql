with customer_versions as (
    select
        source_pk::varchar as customer_id,
        payload:first_name::varchar as first_name,
        payload:last_name::varchar as last_name,
        payload:province::varchar as province,
        coalesce(payload:is_deleted::boolean, false) as is_deleted,
        source_updated_at as effective_from,
        lead(source_updated_at) over (
            partition by source_pk
            order by source_updated_at, raw_record_id
        ) as effective_to
    from {{ source('raw', 'source_records') }}
    where lower(source_table) = 'customers'
)

select
    customer_id,
    first_name,
    last_name,
    province,
    is_deleted,
    effective_from,
    effective_to,
    effective_to is null as is_current
from customer_versions
