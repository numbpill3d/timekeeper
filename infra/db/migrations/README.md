# Database migrations

The migration directory contains idempotent upgrades for databases created by
older timekeeper revisions. Apply migrations before starting application
services:

```bash
for migration in infra/db/migrations/*.sql; do
  docker compose exec -T timescaledb \
    psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f - < "$migration"
done
```

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
