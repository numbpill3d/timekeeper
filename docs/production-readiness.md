# Production readiness

## Local stack

Infrastructure image references are pinned by digest in Compose and the
TimescaleDB Dockerfile. Refresh those digests deliberately during dependency
upgrades rather than relying on mutable tags.

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

The bundled stack does not include an external edge-processing agent. Cameras
marked `is_edge_only` in a legacy database are skipped by ingestion, and new
edge-only cameras are rejected by the API until an agent integration is added.

Application containers run with `no-new-privileges` and no Linux capabilities.
Keep those restrictions enabled in production overrides unless a provider
integration demonstrably requires a narrowly scoped capability.

## Provider credentials

Prefer a secret manager or mounted secret files. For example:

```bash
TIMEKEEPER_SECRETS_DIR=/srv/timekeeper/secrets
RING_ACCESS_TOKEN_FILE=/run/secrets/ring_access_token
```

Compose mounts `TIMEKEEPER_SECRETS_DIR` read-only at `/run/secrets` in the
ingestion and alert services. Keep the directory outside the repository and
restrict its files to the service account that runs Compose.

The ingestion service reads `*_ACCESS_TOKEN_FILE` without persisting the
secret in `provider_config`. Provider-specific OAuth refresh requires the
relevant vendor application credentials and token endpoint. Set the provider’s
`*_REFRESH_TOKEN`, `*_TOKEN_URL`, `*_CLIENT_ID`, and `*_CLIENT_SECRET` through
the secret manager; the adapter refreshes in memory and retries one expired
session. Static access tokens are never persisted.

## Recognition validation

The vision image bundles the official OSNet x1.0 ImageNet weights, so the
default appearance ReID path does not depend on a first-start network download.
FaceNet/MTCNN can be
provided separately when its model dependencies are validated; the default
image omits the stale published FaceNet package pin so it can use maintained
Torch/Torchvision releases. Enroll a known person by allowing a clear
face and full-body view to be observed, label the resulting person in the
Persons screen, and verify subsequent detections match that owner’s cameras.
Do not treat a low-confidence match as proof of identity.

## Required release gates

- Run the provider smoke tests in `docs/provider-smoke-test.md` with real
  hardware or a validated RTSP/WHEP bridge.
- Run the complete Docker stack and verify Kafka, TimescaleDB, MinIO, Ollama,
  ingestion, vision, event processing, query, alerts, and API health.
- Test token expiry/rotation using the provider’s official OAuth flow.
- Verify retention deletes raw detections, database events, and their
  corresponding object keys, including legacy URL-shaped clip values.
