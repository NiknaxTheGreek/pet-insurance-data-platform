select customer_id
from {{ ref('dim_customer_scd2') }}
group by customer_id
having count_if(is_current) != 1
