# Database migrations

The migration directory contains upgrades for databases created by older
timekeeper revisions. The Compose `db-migrate` sidecar consults
`schema_migrations` and applies each numbered file once; a failed migration
stops startup and is retried on the next run.

For a manual run, apply migrations before starting application services:

```bash
for migration in infra/db/migrations/*.sql; do
  docker compose exec -T timescaledb \
    psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f - < "$migration"
done
```

The manual loop is intentionally simple and relies on each migration's
idempotent SQL. To get the same skip behavior as Compose, check the ledger
before invoking `psql` for each file.

`001_provider_attribution.sql` adds provider configuration and attribution
fields. If an older database has 768-dimensional event embeddings, it retains
them as `embedding_legacy_768` and creates the current 384-dimensional column;
new events populate the current column without deleting historical events.

`002_alert_delivery_idempotency.sql` removes duplicate historical delivery
rows before adding the uniqueness boundary used by the alert worker.

`003_user_email_canonicalization.sql` normalizes legacy email casing and adds
case-insensitive uniqueness. It aborts before changing data if existing
accounts collide after normalization, so those accounts can be resolved
explicitly by an administrator first.

`004_alert_delivery_event_index.sql` adds the event-id index used by retention
and camera-removal cleanup.

`005_person_owner_last_seen_index.sql` adds the tenant/time index used by the
Persons listing.

`006_camera_health.sql` adds bounded ingestion heartbeat/error fields used to
distinguish online, starting, stale, error, and paused camera states.

`007_camera_frame_metrics.sql` adds the latest observed frame dimensions and
sampled FPS for diagnostics without retaining additional image data.

`008_audit_log.sql` adds the owner-scoped audit history used for deliberate
camera, person, and evidence changes.

`009_event_annotations.sql` adds owner-scoped, bounded operator notes for
individual events. Notes are removed when an event is redacted or expires.
