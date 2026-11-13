-- Omniscient Home — TimescaleDB schema
-- Requires: timescaledb, pgvector extensions

CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ── Users & auth ────────────────────────────────────────────────

CREATE TABLE users (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email         TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    subscription_tier TEXT NOT NULL DEFAULT 'free'
        CHECK (subscription_tier IN ('free', 'home', 'family', 'pro')),
    mfa_enabled   BOOLEAN NOT NULL DEFAULT FALSE,
    mfa_secret    TEXT,
    fcm_token     TEXT,
    phone         TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── Cameras ──────────────────────────────────────────────────────

CREATE TABLE cameras (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id       UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name           TEXT NOT NULL,
    stream_url     TEXT NOT NULL,
    protocol       TEXT NOT NULL DEFAULT 'rtsp'
        CHECK (protocol IN ('rtsp', 'http', 'https', 'hls', 'file', 'onvif', 'ring', 'nest', 'arlo', 'wyze')),
    location_label TEXT,
    is_edge_only   BOOLEAN NOT NULL DEFAULT FALSE,
    is_active      BOOLEAN NOT NULL DEFAULT TRUE,
    provider_config JSONB NOT NULL DEFAULT '{}',
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── Known persons ────────────────────────────────────────────────

CREATE TABLE persons (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    label            TEXT NOT NULL,
    is_known         BOOLEAN NOT NULL DEFAULT FALSE,
    face_embedding   VECTOR(512),    -- ArcFace/FaceNet embedding
    reid_embedding   VECTOR(512),    -- OSNet x1.0 appearance embedding
    appearance_tags  TEXT[],
    retention_days   INTEGER NOT NULL DEFAULT 30,
    last_seen_at     TIMESTAMPTZ,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── Tracked objects ──────────────────────────────────────────────

CREATE TABLE tracked_objects (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id        UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    category        TEXT NOT NULL,  -- keys, wallet, phone, bag, package, ...
    label           TEXT,
    last_camera_id  UUID REFERENCES cameras(id),
    last_seen_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── Raw detections (hypertable) ──────────────────────────────────

CREATE TABLE detections (
    id          UUID NOT NULL DEFAULT gen_random_uuid(),
    camera_id   UUID NOT NULL REFERENCES cameras(id),
    timestamp   TIMESTAMPTZ NOT NULL,
    frame_id    TEXT NOT NULL,
    track_id    INTEGER,
    class_name  TEXT NOT NULL,
    confidence  FLOAT NOT NULL,
    bbox        FLOAT[4],       -- [x1, y1, x2, y2] normalized 0-1
    person_id   UUID REFERENCES persons(id),
    object_id   UUID REFERENCES tracked_objects(id),
    association_confidence FLOAT,
    association_method TEXT,
    PRIMARY KEY (id, timestamp)
);
SELECT create_hypertable('detections', 'timestamp');

-- ── Activity events (hypertable) ─────────────────────────────────

CREATE TABLE events (
    id              UUID NOT NULL DEFAULT gen_random_uuid(),
    camera_id       UUID NOT NULL REFERENCES cameras(id),
    event_type      TEXT NOT NULL,
    timestamp       TIMESTAMPTZ NOT NULL,
    person_id       UUID REFERENCES persons(id),
    object_id       UUID REFERENCES tracked_objects(id),
    location_label  TEXT,
    action_label    TEXT NOT NULL,
    confidence      FLOAT NOT NULL DEFAULT 1.0,
    metadata        JSONB NOT NULL DEFAULT '{}',
    clip_path       TEXT,
    -- semantic vector for RAG retrieval
    -- all-MiniLM-L6-v2 emits 384-dimensional normalized vectors.
    embedding       VECTOR(384),
    PRIMARY KEY (id, timestamp)
);
SELECT create_hypertable('events', 'timestamp');

-- ── Alert rules ──────────────────────────────────────────────────

CREATE TABLE alert_rules (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id       UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name           TEXT NOT NULL,
    rule_text      TEXT NOT NULL,       -- natural language rule
    compiled_rule  JSONB,               -- parsed AST
    priority       TEXT NOT NULL DEFAULT 'important'
        CHECK (priority IN ('critical', 'important', 'informational')),
    channels       TEXT[] NOT NULL DEFAULT '{push}',
    is_active      BOOLEAN NOT NULL DEFAULT TRUE,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── Alert events ─────────────────────────────────────────────────

CREATE TABLE alert_deliveries (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    rule_id     UUID NOT NULL REFERENCES alert_rules(id) ON DELETE CASCADE,
    event_id    UUID NOT NULL,
    triggered_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    channels_sent TEXT[],
    payload     JSONB
);

-- ── Indexes ──────────────────────────────────────────────────────

CREATE INDEX ON events (camera_id, timestamp DESC);
CREATE INDEX ON events (person_id, timestamp DESC);
CREATE INDEX ON events (event_type, timestamp DESC);
CREATE INDEX ON detections (camera_id, timestamp DESC);
CREATE INDEX ON detections (track_id, camera_id, timestamp DESC);

-- vector similarity indexes for RAG and ReID queries
CREATE INDEX ON events USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);
CREATE INDEX ON persons USING ivfflat (face_embedding vector_cosine_ops)
    WITH (lists = 50);
CREATE INDEX ON persons USING ivfflat (reid_embedding vector_cosine_ops)
    WITH (lists = 50);

-- lookup / range indexes
CREATE INDEX ON alert_deliveries (rule_id, triggered_at DESC);
CREATE INDEX ON alert_deliveries (event_id);
CREATE INDEX ON alert_rules (owner_id, is_active);
CREATE INDEX ON tracked_objects (owner_id, last_seen_at DESC);
