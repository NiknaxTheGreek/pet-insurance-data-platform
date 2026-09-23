{{
    config(
        materialized='incremental',
        unique_key='raw_record_id',
        incremental_strategy='merge',
        on_schema_change='sync_all_columns'
    )
}}

select
    raw.raw_record_id,
    raw.source_pk::varchar as claim_id,
    raw.source_updated_at,
    raw.operation,
    raw.payload:policy_id::varchar as policy_id,
    raw.payload:pet_id::varchar as pet_id,
    raw.payload:claim_type::varchar as claim_type,
    raw.payload:claim_status::varchar as claim_status,
    try_to_decimal(raw.payload:claim_amount::varchar, 18, 2) as claim_amount,
    try_to_decimal(raw.payload:approved_amount::varchar, 18, 2) as approved_amount,
    coalesce(raw.payload:is_deleted::boolean, false) as is_deleted,
    raw.batch_id,
    raw.ingested_at
from {{ source('raw', 'source_records') }} raw
where lower(raw.source_table) = 'claims'

{% if is_incremental() %}
  and not exists (
      select 1
      from {{ this }} existing
      where existing.raw_record_id = raw.raw_record_id
  )
{% endif %}
