-- Store bounded frame metrics alongside the ingestion heartbeat.

ALTER TABLE cameras
    ADD COLUMN IF NOT EXISTS last_frame_width INTEGER,
    ADD COLUMN IF NOT EXISTS last_frame_height INTEGER,
    ADD COLUMN IF NOT EXISTS observed_fps REAL;

INSERT INTO schema_migrations (version)
VALUES ('007_camera_frame_metrics')
ON CONFLICT (version) DO NOTHING;
