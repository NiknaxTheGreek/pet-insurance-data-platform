with policies as (
    select *
    from {{ ref('stg_policies') }}
    where not is_deleted
),

claims as (
    select *
    from {{ ref('stg_claims') }}
    where not is_deleted
),

payments as (
    select
        claim_id,
        sum(payment_amount) as paid_amount
    from {{ ref('stg_claim_payments') }}
    where not is_deleted
      and upper(payment_status) in ('PAID', 'SETTLED')
    group by claim_id
),

claim_rollup as (
    select
        c.policy_id,
        count(*) as claim_count,
        sum(c.claim_amount) as incurred_claim_amount,
        sum(coalesce(c.approved_amount, 0)) as approved_claim_amount,
        sum(coalesce(p.paid_amount, 0)) as paid_claim_amount
    from claims c
    left join payments p on c.claim_id = p.claim_id
    group by c.policy_id
)

select
    p.policy_id,
    p.customer_id,
    p.pet_id,
    p.plan_type,
    p.policy_status,
    p.start_date,
    p.end_date,
    p.monthly_premium,
    coalesce(cr.claim_count, 0) as claim_count,
    coalesce(cr.incurred_claim_amount, 0) as incurred_claim_amount,
    coalesce(cr.approved_claim_amount, 0) as approved_claim_amount,
    coalesce(cr.paid_claim_amount, 0) as paid_claim_amount
from policies p
left join claim_rollup cr on p.policy_id = cr.policy_id
