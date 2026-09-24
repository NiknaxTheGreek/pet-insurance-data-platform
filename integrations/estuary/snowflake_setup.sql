-- ESTUARY SNOWFLAKE SETUP TEMPLATE.
-- Run as an administrative role only after an Estuary account is available.
-- This file deliberately contains no private key.

SET database_name = 'SNOWFLAKE_LEARNING_DB';
SET warehouse_name = 'SNOWFLAKE_LEARNING_WH';
SET estuary_role = 'PET_INSURANCE_ESTUARY_ROLE';
SET estuary_user = 'PET_INSURANCE_ESTUARY';
SET estuary_schema = 'PET_INSURANCE_ESTUARY';

CREATE ROLE IF NOT EXISTS IDENTIFIER($estuary_role);
CREATE SCHEMA IF NOT EXISTS IDENTIFIER($database_name).IDENTIFIER($estuary_schema);

CREATE USER IF NOT EXISTS IDENTIFIER($estuary_user)
  TYPE = SERVICE
  DEFAULT_ROLE = $estuary_role
  DEFAULT_WAREHOUSE = $warehouse_name;

GRANT ROLE IDENTIFIER($estuary_role) TO USER IDENTIFIER($estuary_user);
ALTER USER IDENTIFIER($estuary_user) SET QUOTED_IDENTIFIERS_IGNORE_CASE = FALSE;

GRANT USAGE ON DATABASE IDENTIFIER($database_name) TO ROLE IDENTIFIER($estuary_role);
GRANT USAGE ON WAREHOUSE IDENTIFIER($warehouse_name) TO ROLE IDENTIFIER($estuary_role);
GRANT USAGE, CREATE TABLE, CREATE STAGE
  ON SCHEMA IDENTIFIER($database_name).IDENTIFIER($estuary_schema)
  TO ROLE IDENTIFIER($estuary_role);

-- After generating a key pair outside the repository, assign ONLY the public key:
-- ALTER USER PET_INSURANCE_ESTUARY SET RSA_PUBLIC_KEY='<base64 public key body>';
