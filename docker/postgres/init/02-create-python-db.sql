\set ON_ERROR_STOP on

-- C1-D: the Java schema remains in ai_center; Python owns a separate Alembic database.
-- docker-entrypoint-initdb.d only runs on a fresh PostgreSQL volume.
SELECT 'CREATE DATABASE ai_center_py OWNER aicenter'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'ai_center_py')
\gexec
