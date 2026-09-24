-- depends_on: {{ ref('dim_policy') }}
-- depends_on: {{ ref('dim_customer_scd2') }}
-- depends_on: {{ ref('fct_claims') }}
-- depends_on: {{ ref('mart_portfolio_performance') }}

select
    table_name,
    column_name
from {{ target.database }}.information_schema.columns
where table_schema = 'PET_INSURANCE_MARTS'
  and upper(column_name) in (
      'FIRST_NAME',
      'LAST_NAME',
      'EMAIL',
      'EMAIL_ADDRESS',
      'PHONE',
      'PHONE_NUMBER',
      'STREET_ADDRESS'
  )
