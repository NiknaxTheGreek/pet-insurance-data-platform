select
    c.claim_id,
    c.pet_id as claim_pet_id,
    p.pet_id as policy_pet_id
from {{ ref('stg_claims') }} c
join {{ ref('stg_policies') }} p on c.policy_id = p.policy_id
where not c.is_deleted
  and not p.is_deleted
  and c.pet_id <> p.pet_id
