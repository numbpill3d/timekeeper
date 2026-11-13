-- Record the latest ingestion heartbeat without storing stream URLs or errors.

ALTER TABLE cameras
    ADD COLUMN IF NOT EXISTS last_frame_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS last_error_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS last_error_code TEXT,
    ADD COLUMN IF NOT EXISTS consecutive_failures INTEGER NOT NULL DEFAULT 0;

INSERT INTO schema_migrations (version)
VALUES ('006_camera_health')
ON CONFLICT (version) DO NOTHING;
