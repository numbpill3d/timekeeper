-- Keep operator notes separate from machine-generated event metadata so notes
-- can be edited without rewriting evidence records.

CREATE TABLE IF NOT EXISTS event_annotations (
    event_id   UUID NOT NULL,
    owner_id   UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    note       TEXT NOT NULL CHECK (char_length(note) BETWEEN 1 AND 2000),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (event_id, owner_id)
);

CREATE INDEX IF NOT EXISTS event_annotations_owner_updated_idx
    ON event_annotations (owner_id, updated_at DESC);

INSERT INTO schema_migrations (version)
VALUES ('009_event_annotations')
ON CONFLICT (version) DO NOTHING;
