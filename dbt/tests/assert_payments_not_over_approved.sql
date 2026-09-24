with paid as (
    select
        claim_id,
        sum(payment_amount) as paid_amount
    from {{ ref('stg_claim_payments') }}
    where not is_deleted
      and upper(payment_status) in ('PAID', 'SETTLED')
    group by claim_id
)
select
    c.claim_id,
    c.approved_amount,
    p.paid_amount
from {{ ref('stg_claims') }} c
join paid p on c.claim_id = p.claim_id
where not c.is_deleted
  and c.approved_amount is not null
  and p.paid_amount > c.approved_amount
