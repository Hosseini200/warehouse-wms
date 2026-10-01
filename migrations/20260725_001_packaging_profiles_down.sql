BEGIN;

DELETE FROM schema_migrations
WHERE version = '20260725_001_packaging_profiles';

DROP TABLE IF EXISTS transfer_packaging_items;
DROP TABLE IF EXISTS production_run_packaging_items;
DROP TABLE IF EXISTS production_run_ingredients;
DROP TABLE IF EXISTS production_runs;
DROP TABLE IF EXISTS packaging_profile_items;
DROP TABLE IF EXISTS packaging_profiles;

ALTER TABLE packaging_materials
    DROP CONSTRAINT IF EXISTS ck_packaging_material_type;

ALTER TABLE packaging_materials
    DROP COLUMN IF EXISTS material_type;

DO $$
DECLARE
    migration_count BIGINT;
BEGIN
    IF to_regclass('public.schema_migrations') IS NOT NULL THEN
        EXECUTE 'SELECT COUNT(*) FROM public.schema_migrations'
        INTO migration_count;

        IF migration_count = 0 THEN
            EXECUTE 'DROP TABLE public.schema_migrations';
        END IF;
    END IF;
END
$$;

COMMIT;