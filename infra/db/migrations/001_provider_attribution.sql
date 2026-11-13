-- Idempotent upgrade for databases created before provider attribution support.

-- Older fresh schemas used PostgreSQL's default events_embedding_idx name.
-- Remove that known duplicate before creating the canonical 384-dim index.
DROP INDEX IF EXISTS events_embedding_idx;

CREATE TABLE IF NOT EXISTS schema_migrations (
    version    TEXT PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE cameras
    ADD COLUMN IF NOT EXISTS provider_config JSONB NOT NULL DEFAULT '{}';

ALTER TABLE cameras
    ADD COLUMN IF NOT EXISTS is_edge_only BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE persons
    ADD COLUMN IF NOT EXISTS face_embedding VECTOR(512);

ALTER TABLE persons
    ADD COLUMN IF NOT EXISTS reid_embedding VECTOR(512);

ALTER TABLE persons
    ADD COLUMN IF NOT EXISTS appearance_tags TEXT[];

ALTER TABLE persons
    ADD COLUMN IF NOT EXISTS retention_days INTEGER NOT NULL DEFAULT 30;

ALTER TABLE detections
    ADD COLUMN IF NOT EXISTS association_confidence FLOAT;

ALTER TABLE detections
    ADD COLUMN IF NOT EXISTS association_method TEXT;

-- The original prototype declared events.embedding as VECTOR(768), while the
-- configured all-MiniLM-L6-v2 model emits VECTOR(384). Keep old vectors for
-- auditability and create the correctly-sized column for new events.
DO $$
DECLARE
    embedding_type TEXT;
BEGIN
    SELECT format_type(a.atttypid, a.atttypmod)
      INTO embedding_type
      FROM pg_attribute a
      JOIN pg_class c ON c.oid = a.attrelid
      JOIN pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname = current_schema()
       AND c.relname = 'events'
       AND a.attname = 'embedding'
       AND NOT a.attisdropped;

    IF embedding_type = 'vector(768)' THEN
        ALTER TABLE events RENAME COLUMN embedding TO embedding_legacy_768;
        ALTER TABLE events ADD COLUMN embedding VECTOR(384);
    ELSIF embedding_type IS NULL THEN
        ALTER TABLE events ADD COLUMN embedding VECTOR(384);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS events_embedding_384_idx
    ON events USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

CREATE INDEX IF NOT EXISTS persons_face_embedding_idx
    ON persons USING ivfflat (face_embedding vector_cosine_ops)
    WITH (lists = 50);

CREATE INDEX IF NOT EXISTS persons_reid_embedding_idx
    ON persons USING ivfflat (reid_embedding vector_cosine_ops)
    WITH (lists = 50);

INSERT INTO schema_migrations (version)
VALUES ('001_provider_attribution')
ON CONFLICT (version) DO NOTHING;
