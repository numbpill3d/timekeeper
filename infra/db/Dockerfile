FROM timescale/timescaledb:latest-pg15

# The Timescale image provides the time-series extension but not pgvector.
# Alpine publishes a matching PostgreSQL 15 vector package, which keeps the
# local image small and avoids compiling PostgreSQL extensions in the build.
RUN apk add --no-cache postgresql-pgvector
