-- Least-privilege access for the running API (psql variables: owner, app).
-- The owner role runs migrations and owns every table; the app role used by
-- FastAPI can read, insert and update rows, but cannot delete rows, truncate
-- tables or change the schema. The audit tables are additionally protected
-- by triggers (migration c7e4a9d2b310).
-- Run once per database, connected to that database, as the owner or a superuser.

REVOKE ALL ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO :"app";

GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA public TO :"app";
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO :"app";

-- Tables and sequences created later by the owner (migrations) get the same grants.
ALTER DEFAULT PRIVILEGES FOR ROLE :"owner" IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE ON TABLES TO :"app";
ALTER DEFAULT PRIVILEGES FOR ROLE :"owner" IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO :"app";
