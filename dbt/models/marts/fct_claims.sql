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
    c.claim_id,
    c.policy_id,
    c.pet_id,
    d.customer_id,
    d.province,
    d.plan_type,
    d.species,
    d.breed,
    c.claim_type,
    c.claim_status,
    c.claim_date,
    c.claim_amount,
    c.approved_amount,
    coalesce(p.paid_amount, 0) as paid_amount,
    p.latest_payment_date,
    c.source_updated_at
from {{ ref('stg_claims') }} c
join {{ ref('dim_policy') }} d
  on c.policy_id = d.policy_id
left join payments p
  on c.claim_id = p.claim_id
where not c.is_deleted
