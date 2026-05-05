# syntax=docker/dockerfile:1.7

# Stage 1: builder — install uv, sync deps into a venv
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1

# Build deps for source-installed C extensions: libsass==0.23.0 ships no
# arm64 manylinux wheel and falls back to source build (needs gcc).
# Builder stage only — runtime image copies the prebuilt venv and stays slim.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:0.4.18 /uv /usr/local/bin/uv

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --extra dev

COPY src/ ./src/
COPY migrations/ ./migrations/
RUN uv sync --frozen --extra dev

# Stage 2: runtime
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

# Non-root user with a home dir so gunicorn's control-server feature can write
# its socket without "Permission denied: '/home/safeharbor'" warnings
RUN groupadd --system --gid 1000 safeharbor && \
    useradd --system --uid 1000 --gid safeharbor \
        --create-home --home-dir /home/safeharbor safeharbor

# Pre-create /data/uploads with safeharbor ownership BEFORE the named volume
# mounts. Docker copies a non-empty mount-point's contents AND ownership into
# an empty named volume on first mount; without this, the volume inherits
# root:root from the daemon and the safeharbor process can't write to it,
# tripping _validate_upload_dir at app startup.
RUN mkdir -p /data/uploads && chown -R safeharbor:safeharbor /data

WORKDIR /app
COPY --from=builder --chown=safeharbor:safeharbor /app /app
COPY --chown=safeharbor:safeharbor docker/docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

USER safeharbor

EXPOSE 8000

ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "2", "--access-logfile", "-", "safeharbor.wsgi:app"]
