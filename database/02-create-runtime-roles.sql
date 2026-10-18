\set ON_ERROR_STOP on
\getenv database_name POSTGRES_DB
\getenv schema_owner POSTGRES_USER
\getenv app_user APP_DB_USER
\getenv app_password APP_DB_PASSWORD
\getenv exporter_user POSTGRES_EXPORTER_USER
\getenv exporter_password POSTGRES_EXPORTER_PASSWORD

SELECT format('CREATE ROLE %I LOGIN PASSWORD %L', :'app_user', :'app_password')
WHERE NOT EXISTS (
  SELECT 1 FROM pg_roles WHERE rolname = :'app_user'
)
\gexec

SELECT format('ALTER ROLE %I LOGIN PASSWORD %L', :'app_user', :'app_password')
\gexec

GRANT CONNECT ON DATABASE :"database_name" TO :"app_user";
GRANT USAGE ON SCHEMA public TO :"app_user";
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO :"app_user";
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO :"app_user";

ALTER DEFAULT PRIVILEGES FOR ROLE :"schema_owner" IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO :"app_user";
ALTER DEFAULT PRIVILEGES FOR ROLE :"schema_owner" IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO :"app_user";

SELECT format(
  'CREATE ROLE %I LOGIN PASSWORD %L',
  :'exporter_user',
  :'exporter_password'
)
WHERE NOT EXISTS (
  SELECT 1 FROM pg_roles WHERE rolname = :'exporter_user'
)
\gexec

SELECT format(
  'ALTER ROLE %I LOGIN PASSWORD %L',
  :'exporter_user',
  :'exporter_password'
)
\gexec

GRANT CONNECT ON DATABASE :"database_name" TO :"exporter_user";
GRANT pg_monitor TO :"exporter_user";
