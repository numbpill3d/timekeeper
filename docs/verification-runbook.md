# Local verification runbook

Run these checks from the repository root after starting the stack:

The complete Python dependency set is tested on Python 3.11. On Python 3.13+
or newer, the pinned vision packages currently declare incompatible NumPy
markers; use the repository's Python 3.11 environment for `make test`.

The CI runtime-audit matrix also pins `actions/setup-python` to Python 3.11
for every declared requirement file, including the full vision stack. Do not
use a workstation Python 3.14 environment as evidence for that audit.

```bash
make PYTHON=.venv/bin/python test
make mobile-typecheck
docker compose --env-file .env.example config --quiet
curl -fsS http://localhost:8000/health
```

Register a development account, create a test camera, and inject a synthetic
event before asking an item question. The answer must come from recorded event
rows and include the timestamp, action, person/item label, and location when
those fields exist.

For a repeatable hardware-free fixture, use `scripts/seed_synthetic.py` as
documented in the README. It creates two inactive kitchen/garage cameras and
deterministic John/toolbox events for an existing owner, without deleting or
modifying live camera credentials. The movement event includes the source and
destination camera names so the handoff answer can be verified without
physical hardware.

The CI event-pipeline smoke test runs the real processor, TimescaleDB, Kafka,
object storage, and API with a scripted detection sequence. It checks a signed
JPEG through the API, restarts the processor, and verifies an inferred handoff
across two Kafka partitions. Run it from a clean checkout with the development
ports free. These commands create and then remove a disposable stack and data:

```bash
export COMPOSE_PROJECT_NAME=timekeeper-smoke
docker compose --env-file .env.example up -d --build event-processor api
python3 scripts/smoke_event_pipeline.py
docker compose --env-file .env.example down --volumes
```

The default compose setup is local-only: infrastructure ports bind to
`127.0.0.1`; the query service is internal to the Compose network and is
reached through the authenticated API proxy. The query service can use its structured fallback without an LLM,
but full natural-language synthesis requires an Ollama model or an explicitly
configured OpenAI key. Install a model only after confirming sufficient disk
space; model downloads are several gigabytes.

Live provider validation additionally requires authorized Ring, Nest, Arlo, or
Wyze credentials and a reachable camera/session. Credentials must remain in
environment variables or secret files, never in `provider_config` or URLs.
