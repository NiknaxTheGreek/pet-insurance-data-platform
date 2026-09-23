select p.*
from {{ ref('stg_claim_payments') }} p
join {{ ref('stg_claims') }} c on p.claim_id = c.claim_id
where p.payment_date < c.claim_date
