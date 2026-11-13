-- Keep timeline and item-history lookups bounded by their tenant-scoped
-- relationship before applying the requested time window. The migration
-- runner executes each file outside an explicit transaction, allowing these
-- indexes to build without blocking live event writes.

CREATE INDEX CONCURRENTLY IF NOT EXISTS events_camera_timestamp_idx
    ON events (camera_id, timestamp DESC);

CREATE INDEX CONCURRENTLY IF NOT EXISTS events_person_timestamp_idx
    ON events (person_id, timestamp DESC)
    WHERE person_id IS NOT NULL;

CREATE INDEX CONCURRENTLY IF NOT EXISTS events_object_timestamp_idx
    ON events (object_id, timestamp DESC)
    WHERE object_id IS NOT NULL;

INSERT INTO schema_migrations (version)
VALUES ('010_event_lookup_indexes')
ON CONFLICT (version) DO NOTHING;
