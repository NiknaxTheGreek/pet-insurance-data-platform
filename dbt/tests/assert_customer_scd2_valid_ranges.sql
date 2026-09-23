select *
from {{ ref('dim_customer_scd2') }}
where effective_to is not null
  and effective_to < effective_from
