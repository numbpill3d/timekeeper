# Timekeeper

Local-first camera intelligence for answering questions about recorded events.
Attach a live camera feed, let the CV pipeline turn observations into
timestamped evidence, and ask questions such as:

> At 4:30 PM, who grabbed the toolbox and where did they go?

Timekeeper answers from recorded events and supporting clips. It does not
invent an identity or action when the evidence is missing or weak.

![Timekeeper dashboard](docs/assets/timekeeper-ui.png)

## What it does

- Ingests RTSP/RTSPS, HTTP(S), HLS, local files, and supported provider sessions.
- Detects and tracks people and objects with a local CV pipeline.
- Associates people and objects using time, position, tracking, and ReID data.
- Correlates cross-camera object movement with stable track IDs when available,
  and otherwise uses a conservative, lower-confidence category/time-window
  match only when the evidence is unambiguous.
- Preserves source and destination camera names on correlated handoffs so an
  answer can show the verified camera path as well as the recorded locations.
- Stores events, labels, confidence, embeddings, and clip references in
  PostgreSQL/TimescaleDB with pgvector.
- Answers natural-language questions through RAG + text-to-SQL, with a
  parameterized no-LLM fallback for common item/person/time questions.
- Uses maintained sentence-transformer and transformer releases for local
  semantic retrieval; the query-engine image keeps the CPU Torch constraint
  separate so upgrades do not pull CUDA runtimes.
- Uses maintained CPU Torch/Torchvision releases in the default vision image;
  OSNet appearance ReID is the supported default identity signal. FaceNet/MTCNN
  remains an optional integration for deployments that provide and validate
  its separate model dependencies.
- Provides a React/Vite dashboard, FastAPI API, mobile app foundation, alerts,
  bounded retention cleanup for raw detections/events/clips, and private signed
  clip URLs. Reviewers can also attach owner-scoped notes to timeline events;
  notes are editable on web/mobile and are removed with the evidence they
  describe.
- Provides URL-backed timeline search, time ranges, event-type and camera-source
  filters on web/mobile, plus grouped evidence review and CSV snapshots.
- Provides bounded per-camera retention policies with read-only impact previews;
  person-specific retention settings take precedence when evidence is associated
  with a person.
- Keeps camera/provider credentials out of event data and rejects credential
  material embedded in camera URLs or provider configuration.

The vision image bundles SHA-256-verified YOLO and OSNet weights. The default
`yolov8n.pt` detector covers the
people, phones, laptops, bags, bottles, cups, books, animals, cars, and
bicycles. Custom YOLO weights supplied through `YOLO_MODEL` can add classes
such as keys, wallets, medication, packages, or toolbox; those class names are
preserved by the vision pipeline and the structured query fallback supports
common household labels and aliases such as “scissors” → “tool”. Color and
other fine-grained attributes are not currently inferred unless the custom
model emits them as distinct classes.

## Architecture

```text
camera/provider feed
        │
        ▼
ingestion → Kafka → vision (detect / track / ReID)
                         │
                         ▼
                 event processor → TimescaleDB + pgvector
                         │
       dashboard/mobile ─┴─ query engine (RAG / SQL / evidence answer)
                         │
                         ▼
                    FastAPI API
```

The default deployment is local Docker Compose. Infrastructure ports bind to
`127.0.0.1`; production deployments still need their own network, secret,
backup, and access-control policy.

## Quick start

### Prerequisites

- Docker Engine and Docker Compose.
- At least 8 GB free disk for the CPU images; model downloads require more.
- Python 3.11 for local tests and the complete dependency set (the Docker
  images and CI verification use Python 3.11).
- Node.js/npm for the web application.
- Node.js/npm for the mobile typecheck (an Android/iOS SDK is only required for
  device builds).

### Start the stack

```bash
git clone https://github.com/numbpill3d/timekeeper.git
cd timekeeper
cp .env.example .env
# Edit .env. Keep provider credentials in environment variables or secret files.
docker compose up --build
```

The API is available at `http://127.0.0.1:8000` and the web UI during
development at `http://127.0.0.1:3000`. The query engine is intentionally
internal to the Compose network; use the authenticated `/query` API route
instead of calling it directly.

The UI can be run separately:

```bash
cd apps/web
npm ci
npm run dev -- --host 127.0.0.1
```

## Camera feeds

Direct feeds use RTSP/RTSPS, HTTP(S), HLS, or a local file URL. Give every
camera a stable location label such as `front door`, `garage`, or `kitchen`.
When the protocol is omitted, Timekeeper infers the direct-feed adapter from
the URL scheme; an explicitly contradictory protocol is rejected before the
camera is saved.

Provider adapters accept `ring://device-id`, `nest://device-id`,
`arlo://device-id`, and `wyze://device-id` when the corresponding authenticated
session or local bridge is configured. Nest requires `NEST_PROJECT_ID`; Ring
uses its authenticated WHEP live-video API; Arlo and Wyze can use a configured
RTSP or WebRTC bridge. Provider secrets belong in environment variables or
secret files, never in `provider_config`, URLs, commits, or screenshots.

The bundled deployment processes feeds in the local ingestion/vision stack.
The legacy `is_edge_only` database flag is retained for compatibility, but the
repository does not include an external edge agent; new edge-only cameras are
rejected and existing ones are skipped by ingestion until such an agent is
connected.

Multiple cameras can run concurrently. The ingestion service creates one
reconnecting stream task per active camera and reloads additions, removals, and
source edits without restarting the service. Vision keeps tracker state scoped
to each camera, while the event processor keeps per-camera aggregators and
correlates supported item handoffs across cameras. Add cameras individually in
the Cameras screen; each feed publishes camera-keyed frames and evidence keeps
its source camera identity.

For larger deployments, run multiple vision replicas in the same Kafka
consumer group:

```bash
docker compose up --build --scale vision=4
```

`KAFKA_TOPIC_PARTITIONS` defaults to four for fresh local topics. Keep it at or
above the maximum number of vision replicas, and expand an existing topic
before scaling a deployment whose topics were created with fewer partitions:

```bash
docker compose exec kafka kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --alter --topic omniscient.frames --partitions 4
```

Frames are keyed by camera ID and all replicas use the same
`VISION_CONSUMER_GROUP`, so Kafka keeps each camera's ordered tracker state on
one worker. The same pattern can be applied to `event-processor` after
expanding `omniscient.detections` when downstream throughput requires it.

Removing a camera is destructive: its detections, events, alert-delivery
records, event annotations, and private evidence clips are removed as part of
the operation.
Deactivate or retain the camera if its history must remain available.

## Query behavior

The evidence answer includes the timestamp, action, person/object label,
location, confidence, and supporting clip references when available. If the
LLM is unavailable, the query engine uses a safe parameterized planner for
questions such as:

```text
Did John pick up my keys today?
Where was the toolbox yesterday?
What happened in the garage this afternoon?
What happened to the toolbox between 4:30 and 5:15 pm?
```

An empty or low-confidence result is reported as uncertain rather than being
presented as a fact. An Ollama model or configured OpenAI-compatible provider
is required for richer natural-language synthesis; the structured fallback does
not require either provider and understands common bounded time ranges,
including overnight ranges such as “between 11 pm and 1 am.” When a fallback
question explicitly asks who picked up, placed, moved, entered, or left, it also
filters to that recorded event type instead of mixing unrelated activity.
For an item-history question, the answer is ordered as a timeline and can
join the same person’s later exit when the evidence supports it. For example,
the bundled fixture produces a story like:

```text
At 4:35 PM, John picked up blue toolbox in the kitchen.
At 4:39 PM, John moved blue toolbox from kitchen to garage.
At 4:41 PM, John placed blue toolbox at garage.
At 4:45 PM, John left at garage.
```

Each returned evidence row identifies its event time, camera, confidence, and
an optional short-lived verification clip; the UI also lets an authorized
reviewer redact a supporting event and its clip.

## Verification

From the repository root:

```bash
make PYTHON=.venv/bin/python test
make PYTHON=.venv/bin/python security
make mobile-typecheck
python -m compileall -q api services shared tests
docker compose --env-file .env.example config --quiet
```

`requirements-dev.txt` includes the dependency-audit tool used by the
`security` target. The local target checks the API requirement file without
resolving heavyweight ML packages; CI additionally resolves and audits the
complete runtime matrix and its transitive dependency graphs.

The complete local checklist is in
[`docs/verification-runbook.md`](docs/verification-runbook.md). Live provider
validation additionally requires an authorized camera session and hardware.
The prioritized product improvement backlog is in
[`docs/ux-improvement-plan.md`](docs/ux-improvement-plan.md).

### Hardware-free query demo

After the stack is running and a local account exists, seed deterministic
events for that account without connecting a camera:

```bash
DATABASE_URL=postgresql://omniscient:changeme@127.0.0.1:5432/omniscient \
TIMEKEEPER_DEMO_OWNER_EMAIL="you@example.com" \
.venv/bin/python scripts/seed_synthetic.py
```

Or, with `DATABASE_URL` already exported:

```bash
make synthetic-fixture OWNER_EMAIL="you@example.com"
```

The fixture creates two inactive cameras (kitchen and garage), uses no camera
credentials, never creates an account, and is safe to rerun. Its movement event
also carries the source and destination camera names so the demo exercises the
same handoff evidence shown by a live multi-camera setup.
Ask the UI: `What happened to the blue toolbox?` or
`Who picked up the blue toolbox?`.

Every push and pull request runs the Python, web, mobile, and Compose gates in
GitHub Actions. Hardware/provider smoke tests remain a separate release check.

## Repository layout

- `api/` — FastAPI authentication, cameras, events, alerts, and query proxy.
- `apps/web/` — React/Vite dashboard.
- `apps/mobile/` — Expo/React Native client foundation.
- `services/ingestion/` — camera/provider feed ingestion.
- `services/vision/` — detection, tracking, face recognition, and ReID.
- `services/event-processor/` — event aggregation and persistence.
- `services/query-engine/` — RAG, safe SQL validation, fallback planning, and
  evidence formatting.
- `infra/db/` — TimescaleDB/pgvector image, schema, and migrations.
- `docs/` — provider and verification runbooks.

## Privacy and operational boundaries

Run only on feeds you are authorized to monitor and retain. Configure the
`DEFAULT_RETENTION_DAYS` deployment setting and any person-specific overrides,
along with access controls, backups, and notice/consent requirements for your
jurisdiction before using the system around other people. Timekeeper is an
evidence retrieval system, not a guarantee of identity or intent.

## License

MIT
