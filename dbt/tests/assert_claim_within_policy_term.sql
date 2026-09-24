select
    c.claim_id,
    c.claim_date,
    p.start_date,
    p.end_date
from {{ ref('stg_claims') }} c
join {{ ref('stg_policies') }} p on c.policy_id = p.policy_id
where not c.is_deleted
  and not p.is_deleted
  and (
      c.claim_date < p.start_date
      or (p.end_date is not null and c.claim_date > p.end_date)
  )
