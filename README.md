# Timekeeper

Local-first camera intelligence for answering questions about recorded events.
Attach a live camera feed, let the CV pipeline turn observations into
timestamped evidence, and ask questions such as:

> At 4:30 PM, who grabbed the blue toolbox and where did they go?

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
- Stores events, labels, confidence, embeddings, and clip references in
  PostgreSQL/TimescaleDB with pgvector.
- Answers natural-language questions through RAG + text-to-SQL, with a
  parameterized no-LLM fallback for common item/person/time questions.
- Provides a React/Vite dashboard, FastAPI API, mobile app foundation, alerts,
  retention cleanup, and private signed clip URLs.
- Keeps camera/provider credentials out of event data and rejects credential
  material embedded in camera URLs or provider configuration.

The bundled `yolov8n.pt` weights cover the mapped COCO categories such as
people, phones, laptops, bags, bottles, cups, books, animals, cars, and
bicycles. Categories such as keys, wallets, medication, and packages require
custom YOLO weights supplied through `YOLO_MODEL`; the query fallback supports
both the canonical labels and common aliases such as “scissors” → “tool”.

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
- Python 3.10+ for local tests.
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

The API is available at `http://127.0.0.1:8000`, the query engine at
`http://127.0.0.1:8001`, and the web UI during development at
`http://127.0.0.1:3000`.

The UI can be run separately:

```bash
cd apps/web
npm ci
npm run dev -- --host 127.0.0.1
```

## Camera feeds

Direct feeds use RTSP/RTSPS, HTTP(S), HLS, or a local file URL. Give every
camera a stable location label such as `front door`, `garage`, or `kitchen`.

Provider adapters accept `ring://device-id`, `nest://device-id`,
`arlo://device-id`, and `wyze://device-id` when the corresponding authenticated
session or local bridge is configured. Nest requires `NEST_PROJECT_ID`; Ring
uses its authenticated WHEP live-video API; Arlo and Wyze can use a configured
RTSP or WebRTC bridge. Provider secrets belong in environment variables or
secret files, never in `provider_config`, URLs, commits, or screenshots.

## Query behavior

The evidence answer includes the timestamp, action, person/object label,
location, confidence, and supporting clip references when available. If the
LLM is unavailable, the query engine uses a safe parameterized planner for
questions such as:

```text
Did John pick up my keys today?
Where was the blue toolbox yesterday?
What happened in the garage this afternoon?
```

An empty or low-confidence result is reported as uncertain rather than being
presented as a fact. An Ollama model or configured OpenAI-compatible provider
is required for richer natural-language synthesis; the structured fallback does
not require either provider.

## Verification

From the repository root:

```bash
make PYTHON=.venv/bin/python test
make mobile-typecheck
python -m compileall -q api services shared tests
TIMEKEEPER_ENV_FILE=.env.example \
  docker compose --env-file .env.example config --quiet
```

The complete local checklist is in
[`docs/verification-runbook.md`](docs/verification-runbook.md). Live provider
validation additionally requires an authorized camera session and hardware.
The prioritized product improvement backlog is in
[`docs/ux-improvement-plan.md`](docs/ux-improvement-plan.md).

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

Run only on feeds you are authorized to monitor and retain. Configure retention
periods, access controls, backups, and notice/consent requirements for your
jurisdiction before using the system around other people. Timekeeper is an
evidence retrieval system, not a guarantee of identity or intent.

## License

MIT
