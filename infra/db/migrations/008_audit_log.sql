-- Keep a minimal, owner-scoped record of destructive evidence changes.

CREATE TABLE IF NOT EXISTS audit_log (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id      UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    action        TEXT NOT NULL,
    resource_type TEXT NOT NULL,
    resource_id   UUID,
    metadata      JSONB NOT NULL DEFAULT '{}',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS audit_log_owner_created_idx
    ON audit_log (owner_id, created_at DESC, id DESC);

INSERT INTO schema_migrations (version)
VALUES ('008_audit_log')
ON CONFLICT (version) DO NOTHING;
