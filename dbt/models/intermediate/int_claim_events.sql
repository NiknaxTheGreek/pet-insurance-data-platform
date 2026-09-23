{{
    config(
        materialized='incremental',
        unique_key='raw_record_id',
        incremental_strategy='merge',
        on_schema_change='sync_all_columns'
    )
}}

select
    raw_record_id,
    source_pk::varchar as claim_id,
    source_updated_at,
    operation,
    payload:policy_id::varchar as policy_id,
    payload:pet_id::varchar as pet_id,
    payload:claim_type::varchar as claim_type,
    payload:claim_status::varchar as claim_status,
    try_to_decimal(payload:claim_amount::varchar, 18, 2) as claim_amount,
    try_to_decimal(payload:approved_amount::varchar, 18, 2) as approved_amount,
    coalesce(payload:is_deleted::boolean, false) as is_deleted,
    batch_id,
    ingested_at
from {{ source('raw', 'source_records') }}
where lower(source_table) = 'claims'

{% if is_incremental() %}
  and raw_record_id > (select coalesce(max(raw_record_id), 0) from {{ this }})
{% endif %}
