select
    p.policy_id::varchar as policy_id,
    p.customer_id::varchar as customer_id,
    p.pet_id::varchar as pet_id,
    p.plan_type::varchar as plan_type,
    p.policy_status::varchar as policy_status,
    p.start_date::date as start_date,
    p.end_date::date as end_date,
    p.monthly_premium::number(18, 2) as monthly_premium,
    c.province::varchar as province,
    pet.pet_name::varchar as pet_name,
    pet.species::varchar as species,
    pet.breed::varchar as breed
from {{ ref('stg_policies') }} p
join {{ ref('stg_customers') }} c
  on p.customer_id = c.customer_id
 and not c.is_deleted
join {{ ref('stg_pets') }} pet
  on p.pet_id = pet.pet_id
 and not pet.is_deleted
where not p.is_deleted
