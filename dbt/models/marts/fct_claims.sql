with payments as (
    select
        claim_id,
        sum(payment_amount) as paid_amount,
        max(payment_date) as latest_payment_date
    from {{ ref('stg_claim_payments') }}
    where not is_deleted
      and upper(payment_status) in ('PAID', 'SETTLED')
    group by claim_id
)

select
    c.claim_id::varchar as claim_id,
    c.policy_id::varchar as policy_id,
    c.pet_id::varchar as pet_id,
    d.customer_id::varchar as customer_id,
    d.province::varchar as province,
    d.plan_type::varchar as plan_type,
    d.species::varchar as species,
    d.breed::varchar as breed,
    c.claim_type::varchar as claim_type,
    c.claim_status::varchar as claim_status,
    c.claim_date::date as claim_date,
    c.claim_amount::number(18, 2) as claim_amount,
    c.approved_amount::number(18, 2) as approved_amount,
    coalesce(p.paid_amount, 0)::number(18, 2) as paid_amount,
    p.latest_payment_date::date as latest_payment_date,
    c.source_updated_at::timestamp_tz as source_updated_at
from {{ ref('stg_claims') }} c
join {{ ref('dim_policy') }} d
  on c.policy_id = d.policy_id
left join payments p
  on c.claim_id = p.claim_id
where not c.is_deleted
