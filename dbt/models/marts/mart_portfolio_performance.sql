with policy_metrics as (
    select
        pc.*,
        c.province,
        pet.species
    from {{ ref('int_policy_claims') }} pc
    join {{ ref('stg_customers') }} c
      on pc.customer_id = c.customer_id
     and not c.is_deleted
    join {{ ref('stg_pets') }} pet
      on pc.pet_id = pet.pet_id
     and not pet.is_deleted
)

select
    province::varchar as province,
    species::varchar as species,
    plan_type::varchar as plan_type,
    count(*)::number(38, 0) as policy_count,
    count_if(upper(policy_status) = 'ACTIVE')::number(38, 0) as active_policy_count,
    sum(monthly_premium)::number(18, 2) as monthly_premium_book,
    (sum(monthly_premium) * 12)::number(18, 2) as annualized_premium_proxy,
    sum(claim_count)::number(38, 0) as claim_count,
    sum(incurred_claim_amount)::number(18, 2) as incurred_claim_amount,
    sum(approved_claim_amount)::number(18, 2) as approved_claim_amount,
    sum(paid_claim_amount)::number(18, 2) as paid_claim_amount,
    (
      sum(claim_count) / nullif(count(*), 0)
    )::number(18, 6) as claims_per_policy,
    (
      sum(incurred_claim_amount) / nullif(sum(claim_count), 0)
    )::number(18, 2) as average_claim_severity,
    (
      sum(paid_claim_amount) / nullif(sum(monthly_premium) * 12, 0)
    )::number(18, 6) as paid_loss_ratio_proxy
from policy_metrics
group by province, species, plan_type
