-- Speed up retention and camera-removal cleanup by event identifier.

CREATE INDEX IF NOT EXISTS alert_deliveries_event_id_idx
    ON alert_deliveries (event_id);

INSERT INTO schema_migrations (version)
VALUES ('004_alert_delivery_event_index')
ON CONFLICT (version) DO NOTHING;
