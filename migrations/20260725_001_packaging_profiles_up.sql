BEGIN;

CREATE TABLE IF NOT EXISTS schema_migrations (
    version VARCHAR(100) PRIMARY KEY,
    applied_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

ALTER TABLE packaging_materials
    ADD COLUMN IF NOT EXISTS material_type VARCHAR(30);

UPDATE packaging_materials
SET material_type = 'container'
WHERE material_type IS NULL;

ALTER TABLE packaging_materials
    ALTER COLUMN material_type SET DEFAULT 'container',
    ALTER COLUMN material_type SET NOT NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'ck_packaging_material_type'
    ) THEN
        ALTER TABLE packaging_materials
        ADD CONSTRAINT ck_packaging_material_type
        CHECK (
            material_type IN (
                'container',
                'lid',
                'label',
                'inner_box',
                'carton',
                'pallet',
                'other'
            )
        );
    END IF;
END
$$;

CREATE TABLE IF NOT EXISTS packaging_profiles (
    id SERIAL PRIMARY KEY,
    product_id INTEGER NOT NULL
        REFERENCES products(id)
        ON DELETE RESTRICT,
    name VARCHAR(150) NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    effective_from TIMESTAMP WITHOUT TIME ZONE
        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP WITHOUT TIME ZONE
        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITHOUT TIME ZONE
        NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT ck_packaging_profile_version
        CHECK (version > 0),

    CONSTRAINT uq_packaging_profile_product_version
        UNIQUE (product_id, version)
);

CREATE UNIQUE INDEX IF NOT EXISTS
    uq_packaging_profile_active_product
ON packaging_profiles(product_id)
WHERE is_active = TRUE;

CREATE TABLE IF NOT EXISTS packaging_profile_items (
    id SERIAL PRIMARY KEY,
    profile_id INTEGER NOT NULL
        REFERENCES packaging_profiles(id)
        ON DELETE CASCADE,
    material_id INTEGER NOT NULL
        REFERENCES packaging_materials(id)
        ON DELETE RESTRICT,

    quantity_per_product NUMERIC(14,6) NOT NULL,
    component_type VARCHAR(30) NOT NULL DEFAULT 'container',

    consumption_stage VARCHAR(30) NOT NULL DEFAULT 'production',
    rounding_mode VARCHAR(20) NOT NULL DEFAULT 'exact',

    is_primary BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP WITHOUT TIME ZONE
        NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT ck_packaging_profile_item_quantity
        CHECK (quantity_per_product > 0),

    CONSTRAINT ck_packaging_component_type
        CHECK (
            component_type IN (
                'container',
                'lid',
                'label',
                'inner_box',
                'carton',
                'pallet',
                'other'
            )
        ),

    CONSTRAINT ck_packaging_consumption_stage
        CHECK (
            consumption_stage IN (
                'production',
                'dispatch'
            )
        ),

    CONSTRAINT ck_packaging_rounding_mode
        CHECK (
            rounding_mode IN (
                'exact',
                'ceil'
            )
        ),

    CONSTRAINT uq_packaging_profile_material
        UNIQUE (profile_id, material_id)
);

CREATE INDEX IF NOT EXISTS
    ix_packaging_profile_items_profile_id
ON packaging_profile_items(profile_id);

CREATE INDEX IF NOT EXISTS
    ix_packaging_profile_items_material_id
ON packaging_profile_items(material_id);

CREATE TABLE IF NOT EXISTS production_runs (
    id SERIAL PRIMARY KEY,
    warehouse_id INTEGER NOT NULL
        REFERENCES warehouses(id)
        ON DELETE RESTRICT,
    final_product_id INTEGER NOT NULL
        REFERENCES products(id)
        ON DELETE RESTRICT,
    batch_id INTEGER
        REFERENCES batches(id)
        ON DELETE RESTRICT,
    packaging_profile_id INTEGER
        REFERENCES packaging_profiles(id)
        ON DELETE SET NULL,

    produce_quantity DOUBLE PRECISION NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'completed',

    created_by INTEGER
        REFERENCES users(id)
        ON DELETE SET NULL,
    created_at TIMESTAMP WITHOUT TIME ZONE
        NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT ck_production_run_quantity
        CHECK (produce_quantity > 0),

    CONSTRAINT ck_production_run_status
        CHECK (
            status IN (
                'draft',
                'completed',
                'cancelled'
            )
        )
);

CREATE TABLE IF NOT EXISTS production_run_ingredients (
    id SERIAL PRIMARY KEY,
    production_run_id INTEGER NOT NULL
        REFERENCES production_runs(id)
        ON DELETE CASCADE,
    ingredient_id INTEGER NOT NULL
        REFERENCES products(id)
        ON DELETE RESTRICT,

    percentage DOUBLE PRECISION NOT NULL,
    required_quantity DOUBLE PRECISION NOT NULL,
    consumed_quantity DOUBLE PRECISION NOT NULL,

    CONSTRAINT ck_production_ingredient_percentage
        CHECK (percentage > 0 AND percentage <= 100),

    CONSTRAINT ck_production_ingredient_required
        CHECK (required_quantity >= 0),

    CONSTRAINT ck_production_ingredient_consumed
        CHECK (consumed_quantity >= 0)
);

CREATE TABLE IF NOT EXISTS production_run_packaging_items (
    id SERIAL PRIMARY KEY,
    production_run_id INTEGER NOT NULL
        REFERENCES production_runs(id)
        ON DELETE CASCADE,
    material_id INTEGER NOT NULL
        REFERENCES packaging_materials(id)
        ON DELETE RESTRICT,

    quantity_per_product NUMERIC(14,6) NOT NULL,
    required_quantity INTEGER NOT NULL,
    consumed_quantity INTEGER NOT NULL,

    CONSTRAINT ck_production_packaging_ratio
        CHECK (quantity_per_product > 0),

    CONSTRAINT ck_production_packaging_required
        CHECK (required_quantity >= 0),

    CONSTRAINT ck_production_packaging_consumed
        CHECK (consumed_quantity >= 0),

    CONSTRAINT uq_production_run_packaging_material
        UNIQUE (production_run_id, material_id)
);

CREATE TABLE IF NOT EXISTS transfer_packaging_items (
    id SERIAL PRIMARY KEY,
    transfer_id INTEGER NOT NULL
        REFERENCES transfers(id)
        ON DELETE CASCADE,

    packaging_profile_id INTEGER
        REFERENCES packaging_profiles(id)
        ON DELETE SET NULL,

    material_id INTEGER NOT NULL
        REFERENCES packaging_materials(id)
        ON DELETE RESTRICT,

    material_name_snapshot VARCHAR(150) NOT NULL,
    material_sku_snapshot VARCHAR(50) NOT NULL,
    profile_version_snapshot INTEGER,

    quantity_per_product NUMERIC(14,6) NOT NULL,
    consumption_stage_snapshot VARCHAR(30) NOT NULL,
    rounding_mode_snapshot VARCHAR(20) NOT NULL,

    required_quantity INTEGER NOT NULL,
    reserved_quantity INTEGER NOT NULL DEFAULT 0,
    issued_quantity INTEGER NOT NULL DEFAULT 0,
    received_quantity INTEGER NOT NULL DEFAULT 0,
    damaged_quantity INTEGER NOT NULL DEFAULT 0,
    missing_quantity INTEGER NOT NULL DEFAULT 0,

    status VARCHAR(30) NOT NULL DEFAULT 'planned',

    created_at TIMESTAMP WITHOUT TIME ZONE
        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITHOUT TIME ZONE
        NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT ck_transfer_packaging_ratio
        CHECK (quantity_per_product > 0),

    CONSTRAINT ck_transfer_packaging_stage
        CHECK (
            consumption_stage_snapshot IN (
                'production',
                'dispatch'
            )
        ),

    CONSTRAINT ck_transfer_packaging_rounding
        CHECK (
            rounding_mode_snapshot IN (
                'exact',
                'ceil'
            )
        ),

    CONSTRAINT ck_transfer_packaging_quantities
        CHECK (
            required_quantity >= 0
            AND reserved_quantity >= 0
            AND issued_quantity >= 0
            AND received_quantity >= 0
            AND damaged_quantity >= 0
            AND missing_quantity >= 0
        ),

    CONSTRAINT ck_transfer_packaging_status
        CHECK (
            status IN (
                'planned',
                'reserved',
                'issued',
                'received',
                'disputed',
                'released'
            )
        ),

    CONSTRAINT uq_transfer_packaging_material
        UNIQUE (transfer_id, material_id)
);

CREATE INDEX IF NOT EXISTS
    ix_transfer_packaging_items_transfer_id
ON transfer_packaging_items(transfer_id);

CREATE INDEX IF NOT EXISTS
    ix_transfer_packaging_items_material_id
ON transfer_packaging_items(material_id);

INSERT INTO packaging_profiles (
    product_id,
    name,
    version,
    is_active
)
SELECT
    p.id,
    'Default packaging - ' || p.sku,
    1,
    TRUE
FROM products p
WHERE p.product_type = 'finished_good'
  AND p.packaging_material_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM packaging_profiles profile
      WHERE profile.product_id = p.id
        AND profile.is_active = TRUE
  );

INSERT INTO packaging_profile_items (
    profile_id,
    material_id,
    quantity_per_product,
    component_type,
    consumption_stage,
    rounding_mode,
    is_primary
)
SELECT
    profile.id,
    p.packaging_material_id,
    1,
    COALESCE(pm.material_type, 'container'),
    'production',
    'exact',
    TRUE
FROM products p
JOIN packaging_profiles profile
    ON profile.product_id = p.id
   AND profile.is_active = TRUE
JOIN packaging_materials pm
    ON pm.id = p.packaging_material_id
WHERE p.product_type = 'finished_good'
  AND p.packaging_material_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM packaging_profile_items item
      WHERE item.profile_id = profile.id
        AND item.material_id = p.packaging_material_id
  );

INSERT INTO schema_migrations(version)
VALUES ('20260725_001_packaging_profiles')
ON CONFLICT (version) DO NOTHING;

-- Runtime privileges for the production application role.
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE
    packaging_profiles,
    packaging_profile_items,
    production_runs,
    production_run_ingredients,
    production_run_packaging_items,
    transfer_packaging_items
TO warehouse_app;

GRANT USAGE, SELECT ON SEQUENCE
    packaging_profiles_id_seq,
    packaging_profile_items_id_seq,
    production_runs_id_seq,
    production_run_ingredients_id_seq,
    production_run_packaging_items_id_seq,
    transfer_packaging_items_id_seq
TO warehouse_app;


COMMIT;