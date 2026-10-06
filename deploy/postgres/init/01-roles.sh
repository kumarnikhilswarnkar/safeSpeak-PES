#!/bin/sh
# Runs once, when the PostgreSQL volume is first created (docker-entrypoint-initdb.d).
# Creates the schema-owner role, the least-privilege app role, the application
# database and a test database. Passwords come from environment variables only.
set -eu

: "${OWNER_DB_USER:?}" "${OWNER_DB_PASSWORD:?}" "${APP_DB_USER:?}" "${APP_DB_PASSWORD:?}" "${APP_DB_NAME:?}"
TEST_DB_NAME="${APP_DB_NAME}_test"

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres \
    -v owner="$OWNER_DB_USER" -v owner_pw="$OWNER_DB_PASSWORD" \
    -v app="$APP_DB_USER" -v app_pw="$APP_DB_PASSWORD" \
    -v db="$APP_DB_NAME" -v test_db="$TEST_DB_NAME" <<'SQL'
CREATE ROLE :"owner" LOGIN PASSWORD :'owner_pw';
CREATE ROLE :"app" LOGIN PASSWORD :'app_pw';
CREATE DATABASE :"db" OWNER :"owner";
CREATE DATABASE :"test_db" OWNER :"owner";
REVOKE ALL ON DATABASE :"db" FROM PUBLIC;
REVOKE ALL ON DATABASE :"test_db" FROM PUBLIC;
GRANT CONNECT ON DATABASE :"db" TO :"app";
SQL

for database in "$APP_DB_NAME" "$TEST_DB_NAME"; do
    psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$database" \
        -v owner="$OWNER_DB_USER" -v app="$APP_DB_USER" \
        -c "ALTER SCHEMA public OWNER TO \"$OWNER_DB_USER\"" \
        -f /opt/safespeak/app_role_grants.sql
done
echo "SafeSpeak roles and databases created."
