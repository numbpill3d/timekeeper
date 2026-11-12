# Production readiness

## Local stack

1. Copy `.env.example` to `.env` and replace every development credential.
2. Set `ENVIRONMENT=production`, a random `JWT_SECRET` of at least 32
   characters, a browser-reachable `S3_PUBLIC_ENDPOINT_URL`, and real storage
   credentials.
3. Run `docker compose up --build`. The `db-migrate` one-shot service must
   complete before application services start.
4. Confirm `GET /health` reports both `database: ok` and `redis: ok`.
5. Confirm the frontend can open an event clip. The API should return a
   short-lived signed URL, never an internal MinIO hostname or raw credential.

Use a host with Docker Compose available for steps 3–5. The repository's CI
workflow validates the rendered Compose configuration, while a complete local
stack still requires Docker Engine and its runtime images.

## Provider credentials

Prefer a secret manager or mounted secret files. For example:

```bash
RING_ACCESS_TOKEN_FILE=/run/secrets/ring_access_token
```

The ingestion service reads `*_ACCESS_TOKEN_FILE` without persisting the
secret in `provider_config`. Provider-specific OAuth refresh requires the
relevant vendor application credentials and token endpoint. Set the provider’s
`*_REFRESH_TOKEN`, `*_TOKEN_URL`, `*_CLIENT_ID`, and `*_CLIENT_SECRET` through
the secret manager; the adapter refreshes in memory and retries one expired
session. Static access tokens are never persisted.

## Recognition validation

The vision service uses FaceNet/MTCNN when its weights are available, then
falls back to OSNet appearance ReID. Enroll a known person by allowing a clear
face and full-body view to be observed, label the resulting person in the
Persons screen, and verify subsequent detections match that owner’s cameras.
Do not treat a low-confidence match as proof of identity.

## Required release gates

- Run the provider smoke tests in `docs/provider-smoke-test.md` with real
  hardware or a validated RTSP/WHEP bridge.
- Run the complete Docker stack and verify Kafka, TimescaleDB, MinIO, Ollama,
  ingestion, vision, event processing, query, alerts, and API health.
- Test token expiry/rotation using the provider’s official OAuth flow.
- Verify retention deletes both database events and their corresponding object
  keys, including legacy URL-shaped clip values.
