# Updates

Safe Harbor updates are container-image updates plus normal database migration startup behavior. Published-image update flow depends on a compose configuration that points `web` at the GHCR image.

## Manual update flow

For a published-image deployment, from the compose project directory:

```bash
docker compose pull web
docker compose up -d web
```

For the current source-built development and staging compose file, rebuild the local image instead:

```bash
docker compose up -d --build web
```

If a later release also changes worker behavior, update the worker service at the same time:

```bash
docker compose pull web worker
docker compose up -d web worker
```

## Optional: Watchtower

Watchtower can automate image pulls for the web container, but keep it opt-in. Do not auto-update the database container.

For v1, image-only auto-update of `web` is usually safe when you are comfortable with automatic deploys and have a backup strategy. Backups and restore docs land in Phase 2b, so manual updates remain the default until that workflow is documented.
