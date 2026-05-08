# Updates

Safe Harbor updates are container-image updates plus normal database migration startup behavior. Published-image update flow depends on a compose configuration that points `web` at the GHCR image.

## Manual update flow

For a published-image deployment, from the compose project directory:

```bash
docker compose pull web
docker compose up -d web
```

## Pinning a version

Production deployments should pin a known release instead of tracking a moving tag:

```bash
printf "SAFEHARBOR_VERSION=v1.0.0\n" >> .env
docker compose pull web
docker compose up -d web
```

Docker Compose reads `.env` automatically from the compose project directory. This assumes the deployment is already configured for production, including a real `SECRET_KEY` and any compose override needed for production mode; `SAFEHARBOR_VERSION` only controls the image tag. Pinning keeps production rollouts intentional and makes rollback decisions clearer. To roll forward, update `SAFEHARBOR_VERSION` in `.env` to the next release tag, pull the image, and restart the service.

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

For v1, image-only auto-update of `web` is usually safe when you are comfortable with automatic deploys and have a backup strategy. Manual updates remain the default until that workflow is documented.

## GHCR authentication

If the GHCR package is private, authenticate first:

```bash
docker login ghcr.io
```

After the package at `ghcr.io/danner26/safeharbor` is public, no GHCR login is required for normal pulls.
