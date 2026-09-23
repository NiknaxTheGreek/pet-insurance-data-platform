select *
from {{ ref('stg_claims') }}
where approved_amount is not null
  and approved_amount > claim_amount
