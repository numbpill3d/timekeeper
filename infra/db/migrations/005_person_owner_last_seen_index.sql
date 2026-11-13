-- Speed up tenant-scoped person listings ordered by recent activity.

CREATE INDEX IF NOT EXISTS persons_owner_last_seen_idx
    ON persons (owner_id, last_seen_at DESC);

INSERT INTO schema_migrations (version)
VALUES ('005_person_owner_last_seen_index')
ON CONFLICT (version) DO NOTHING;
