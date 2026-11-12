# Local verification runbook

Run these checks from the repository root after starting the stack:

```bash
make PYTHON=.venv/bin/python test
TIMEKEEPER_ENV_FILE=.env.example \
  /home/scorn/.local/bin/docker-compose --env-file .env.example config --quiet
curl -fsS http://localhost:8000/health
curl -fsS http://localhost:8001/health
```

Register a development account, create a test camera, and inject a synthetic
event before asking an item question. The answer must come from recorded event
rows and include the timestamp, action, person/item label, and location when
those fields exist.

The default compose setup is local-only: infrastructure ports bind to
`127.0.0.1`. The query service can use its structured fallback without an LLM,
but full natural-language synthesis requires an Ollama model or an explicitly
configured OpenAI key. Install a model only after confirming sufficient disk
space; model downloads are several gigabytes.

Live provider validation additionally requires authorized Ring, Nest, Arlo, or
Wyze credentials and a reachable camera/session. Credentials must remain in
environment variables or secret files, never in `provider_config` or URLs.
