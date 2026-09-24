select
    p.policy_id,
    p.customer_id,
    p.pet_id,
    p.plan_type,
    p.policy_status,
    p.start_date,
    p.end_date,
    p.monthly_premium,
    c.province,
    pet.pet_name,
    pet.species,
    pet.breed
from {{ ref('stg_policies') }} p
join {{ ref('stg_customers') }} c
  on p.customer_id = c.customer_id
 and not c.is_deleted
join {{ ref('stg_pets') }} pet
  on p.pet_id = pet.pet_id
 and not pet.is_deleted
where not p.is_deleted
