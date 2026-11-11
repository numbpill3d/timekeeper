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
