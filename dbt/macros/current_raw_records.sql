{% macro current_raw_records(source_table_name) %}
select *
from {{ source('raw', 'source_records') }}
where lower(source_table) = lower('{{ source_table_name }}')
qualify row_number() over (
    partition by source_pk
    order by source_updated_at desc, raw_record_id desc
) = 1
{% endmacro %}
