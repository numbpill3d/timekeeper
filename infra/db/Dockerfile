FROM timescale/timescaledb:latest-pg15

# The Timescale image provides the time-series extension but not pgvector.
# Build pgvector against the PostgreSQL 15 headers in this image; Alpine's
# generic package currently targets a newer PostgreSQL major version.
ARG PGVECTOR_VERSION=v0.6.2
RUN apk add --no-cache --virtual .pgvector-build-deps \
      build-base git postgresql15-dev \
    && git clone --depth 1 --branch "${PGVECTOR_VERSION}" \
      https://github.com/pgvector/pgvector.git /tmp/pgvector \
    && make -C /tmp/pgvector WITH_LLVM=0 \
    && make -C /tmp/pgvector install \
    && rm -rf /tmp/pgvector \
    && apk del .pgvector-build-deps
