
BEGIN;

DO $$
DECLARE
    target RECORD;
BEGIN
    FOR target IN
        SELECT c.relname
          FROM pg_class c
          JOIN pg_namespace n ON n.oid = c.relnamespace
         WHERE n.nspname = 'public'
           AND c.relkind = 'r'          -- ordinary tables; a view has no RLS
           AND NOT c.relrowsecurity     -- idempotent, and quiet about it
    LOOP
        EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', target.relname);
    END LOOP;
END
$$;

DO $$
DECLARE
    role_name TEXT;
BEGIN
    FOREACH role_name IN ARRAY ARRAY['anon', 'authenticated'] LOOP
        IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = role_name) THEN
            RAISE NOTICE 'role % does not exist here; skipping', role_name;
            CONTINUE;
        END IF;

        EXECUTE format('REVOKE ALL ON ALL TABLES IN SCHEMA public FROM %I', role_name);
        EXECUTE format('REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM %I', role_name);
        EXECUTE format('REVOKE ALL ON ALL FUNCTIONS IN SCHEMA public FROM %I', role_name);
        EXECUTE format('REVOKE ALL ON SCHEMA public FROM %I', role_name);

        EXECUTE format(
            'ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public '
            'REVOKE ALL ON TABLES FROM %I', role_name
        );
        EXECUTE format(
            'ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public '
            'REVOKE ALL ON SEQUENCES FROM %I', role_name
        );
        EXECUTE format(
            'ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public '
            'REVOKE ALL ON FUNCTIONS FROM %I', role_name
        );

        RAISE NOTICE 'revoked public schema access from %', role_name;
    END LOOP;
END
$$;


COMMIT;
