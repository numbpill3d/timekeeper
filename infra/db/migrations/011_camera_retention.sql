-- Add an owner-controlled retention policy to each camera.

ALTER TABLE cameras
    ADD COLUMN IF NOT EXISTS retention_days INTEGER NOT NULL DEFAULT 30;

ALTER TABLE cameras
    DROP CONSTRAINT IF EXISTS cameras_retention_days_check;

ALTER TABLE cameras
    ADD CONSTRAINT cameras_retention_days_check
    CHECK (retention_days BETWEEN 1 AND 3650);

INSERT INTO schema_migrations (version)
VALUES ('011_camera_retention')
ON CONFLICT (version) DO NOTHING;
