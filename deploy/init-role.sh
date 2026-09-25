#!/bin/sh
set -eu
psql -h db -U mobin -d mobin -v ON_ERROR_STOP=1 -v app_password="$APP_DB_PASSWORD" <<'SQL'
SELECT format('CREATE ROLE mobin_app LOGIN PASSWORD %L', :'app_password')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'mobin_app') \gexec
ALTER ROLE mobin_app PASSWORD :'app_password';
GRANT CONNECT ON DATABASE mobin TO mobin_app;
GRANT USAGE ON SCHEMA public TO mobin_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO mobin_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO mobin_app;
ALTER DEFAULT PRIVILEGES FOR ROLE mobin IN SCHEMA public
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO mobin_app;
ALTER DEFAULT PRIVILEGES FOR ROLE mobin IN SCHEMA public
GRANT USAGE, SELECT ON SEQUENCES TO mobin_app;
SQL
