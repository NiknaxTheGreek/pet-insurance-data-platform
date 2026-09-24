select
    p.policy_id,
    p.customer_id as policy_customer_id,
    pet.customer_id as pet_customer_id
from {{ ref('stg_policies') }} p
join {{ ref('stg_pets') }} pet on p.pet_id = pet.pet_id
where not p.is_deleted
  and not pet.is_deleted
  and p.customer_id <> pet.customer_id
