# Configuration

Safe Harbor reads runtime configuration from environment variables. In Docker
Compose installs, most values come from `.env`; a few service-specific values
are also set directly in `docker-compose.yml`.

Use this page as the public operator reference for the variables shipped in
`.env.example`, plus the upload directory variable used by the application
runtime.

Each table uses the same columns:

- **Variable** is the environment variable name.
- **Default** is the application or Compose example default.
- **Required** describes when an operator must set it.
- **Surface** names the service or component that consumes it.
- **Description** gives the operational effect.
- **Docs** links to related local documentation when there is a deeper guide.

## Flask Core

| Variable | Default | Required | Surface | Description | Docs |
| --- | --- | --- | --- | --- | --- |
| `FLASK_APP` | `safeharbor.wsgi:app` | Required for Flask CLI commands outside the container image | Flask CLI | Import path for the WSGI application used by `flask` commands. | - |
| `FLASK_CONFIG` | `development` | Required for production deployment | App factory, web, worker | Selects `development`, `testing`, or `production` config. | [Install](install.md) |
| `SECRET_KEY` | `change-me-in-prod` | Required in production | Flask sessions and CSRF | Secret used to sign sessions and forms; replace before using production config. | [Install](install.md) |

Development to production note: the checked-in Compose file is intentionally
friendly for first-run local use. It sets `FLASK_CONFIG: development` directly
on both `web` and `worker`, which overrides `.env` for those services.
Production deployment therefore requires a deployment override or host
environment that passes `FLASK_CONFIG=production` to `web` and any started
`worker` after a real `SECRET_KEY` is set.

Production startup validation fails when `SECRET_KEY` is blank or still set to
`change-me-in-prod`. It also requires `DATABASE_URL`, `REDIS_URL`, `SMTP_HOST`,
and `STORAGE_DIR` to be present in the production environment.

## Database

| Variable | Default | Required | Surface | Description | Docs |
| --- | --- | --- | --- | --- | --- |
| `DATABASE_URL` | Compose: `postgresql+psycopg://safeharbor:safeharbor@postgres:5432/safeharbor` | Required in production | Web, worker, backup sidecar | Primary SQLAlchemy database URL. | [Install](install.md) |
| `TEST_DATABASE_URL` | `postgresql+psycopg://safeharbor:safeharbor@postgres:5432/safeharbor_test` in `.env.example`; app fallback uses local `localhost` | Optional unless running tests | Test config | Database URL used by pytest fixtures and `FLASK_CONFIG=testing`. | - |

Use the Compose hostname `postgres` from containers. Use `localhost` only for
host-run development commands that connect through a locally exposed database.

The production validator checks that `DATABASE_URL` is set. It does not create
the database for you; the target database must exist and be reachable before the
app starts.

## Redis

| Variable | Default | Required | Surface | Description | Docs |
| --- | --- | --- | --- | --- | --- |
| `REDIS_URL` | Compose: `redis://redis:6379/0`; app fallback `redis://localhost:6379/0` | Required in production | Web, worker | Redis connection URL for background work and shared runtime services. | [Install](install.md) |
| `RQ_QUEUES` | `default` | Optional for custom worker commands | Custom worker command | Queue names for an overridden worker command. | - |

The current Compose worker command hardcodes the `default` queue and passes its
Redis URL directly to `rq worker`, so changing `RQ_QUEUES` in `.env` does not
change the provided worker service. Keep `RQ_QUEUES` documented for
`.env.example` compatibility and set it only when you also override the worker
command to read it.

Use the Compose hostname `redis` from containers. Use `localhost` only for
host-run development commands that connect through a locally exposed Redis
service.

## Email/SMTP

| Variable | Default | Required | Surface | Description | Docs |
| --- | --- | --- | --- | --- | --- |
| `SMTP_HOST` | `.env.example`: `mailhog`; app fallback `localhost` | Required in production | Email sending | SMTP server hostname. | [Install](install.md) |
| `SMTP_PORT` | `1025` | Optional | Email sending | SMTP server port. | - |
| `SMTP_USER` | empty | Optional | Email sending | SMTP username for authenticated relays. | - |
| `SMTP_PASS` | empty | Optional | Email sending | SMTP password for authenticated relays. | - |
| `SMTP_FROM` | `safeharbor@localhost` | Optional, recommended | Email sending | Sender address used for application emails. | - |

For local development, the Compose `dev` profile can start Mailhog. With
Mailhog enabled, use `SMTP_HOST=mailhog` and `SMTP_PORT=1025`, then open its web
UI on port `8025` to inspect messages.

For production, point `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`, and
`SMTP_FROM` at your own relay. If the app sends password reset or account email
links from asynchronous code, also configure the public URL variables below.

## Storage

| Variable | Default | Required | Surface | Description | Docs |
| --- | --- | --- | --- | --- | --- |
| `STORAGE_DIR` | `.env.example`: `/data/uploads`; app fallback `./uploads` | Required in production | Production validation | Public storage setting retained for operator configuration and production validation. | [Install](install.md) |
| `UPLOAD_DIR` | `/data/uploads` | Optional when using the provided Compose volume | Web, upload service, backup and restore CLI | Actual directory used for tank and animal image uploads. | [Backups](backups.md) |
| `UPLOAD_DIR_REQUIRE_WRITABLE` | `1` | Optional | App startup check | When truthy, startup fails if `UPLOAD_DIR` is not writable by the app process. | [Restore](restore.md) |

Current upload behavior is writable. The `web` service mounts the named
`uploads` volume at `/data/uploads`, and the `backups` service also mounts that
same volume read-write so backup and restore commands can package and restore
uploaded files.

Keep `UPLOAD_DIR_REQUIRE_WRITABLE=1` for normal backup and restore workflows;
uploads are writable in the standard services. Set it to `0` only for a custom
diagnostic container that needs to inspect configuration without writing
uploads.

`STORAGE_DIR` is still part of the public environment file and production
validation. `UPLOAD_DIR` is the current runtime path used by upload, backup, and
restore code. In the standard container setup they should both resolve to
`/data/uploads`.

## Logging

| Variable | Default | Required | Surface | Description | Docs |
| --- | --- | --- | --- | --- | --- |
| `LOG_LEVEL` | `INFO` | Optional | Web, worker | Python logging level such as `DEBUG`, `INFO`, `WARNING`, or `ERROR`. | [Observability](observability.md) |

Production logs are intended for container collection. Set `LOG_LEVEL=DEBUG`
only while investigating a specific issue, then return to `INFO` or a quieter
level.

## Reverse Proxy

| Variable | Default | Required | Surface | Description | Docs |
| --- | --- | --- | --- | --- | --- |
| `TRUST_PROXY_HEADERS` | `1` | Optional | Flask request handling | Enables one trusted proxy hop so forwarded scheme, host, and client headers are honored. | [Deploy](deploy.md) |
| `FORWARDED_ALLOW_IPS` | `*` | Optional | Gunicorn | Gunicorn allowlist for forwarded headers from upstream proxy IPs. | [Deploy](deploy.md) |

Leave `TRUST_PROXY_HEADERS=1` when Safe Harbor is behind a trusted reverse proxy
or Cloudflare Tunnel. Set it to `0` when exposing the container directly without
a trusted proxy.

`FORWARDED_ALLOW_IPS=*` is convenient for dynamic proxy environments. If your
proxy source addresses are static, tighten this to the known IPs or CIDRs used
by that proxy.

## Public URL

| Variable | Default | Required | Surface | Description | Docs |
| --- | --- | --- | --- | --- | --- |
| `SERVER_NAME` | empty | Required when background email needs absolute URLs | Flask URL generation | Public hostname without a scheme, such as `safeharbor.example.com`. | [Install](install.md) |
| `PREFERRED_URL_SCHEME` | `https` | Optional | Flask URL generation | Scheme used when Flask builds external URLs without an active request. | [Install](install.md) |

Set these when Safe Harbor sends emails that include application links, such as
password reset or account confirmation messages. Request-handled pages can infer
the host from inbound traffic, but background jobs need `SERVER_NAME` and
`PREFERRED_URL_SCHEME` to build correct absolute URLs.

Use `PREFERRED_URL_SCHEME=https` for normal public deployments. Use `http` only
for local testing or a trusted internal environment that intentionally serves
plain HTTP.

## Sentry

| Variable | Default | Required | Surface | Description | Docs |
| --- | --- | --- | --- | --- | --- |
| `SENTRY_DSN` | empty | Optional | App startup, observability | Enables Sentry error reporting when set; blank disables Sentry initialization. | [Observability](observability.md) |
| `SENTRY_TRACES_SAMPLE_RATE` | `0.0` | Optional | Sentry SDK | Transaction sampling rate from `0.0` to `1.0`; `0.0` records errors only. | [Observability](observability.md) |

The production validator rejects `SENTRY_TRACES_SAMPLE_RATE` values outside the
`0.0` to `1.0` range. Leave `SENTRY_DSN` blank if you do not use Sentry.

When enabled, the Sentry environment name follows the resolved Flask config
name, such as `development`, `testing`, or `production`.

## Cloudflare Tunnel Opt-In

| Variable | Default | Required | Surface | Description | Docs |
| --- | --- | --- | --- | --- | --- |
| `TUNNEL_TOKEN` | empty | Required only when using the `tunnel` Compose profile | `cloudflared` service | Cloudflare Tunnel token from Cloudflare Zero Trust. | [Deploy](deploy.md) |

The Cloudflare Tunnel container does not run by default. It runs only when you
start Compose with `COMPOSE_PROFILES=tunnel` or include `tunnel` in a
comma-separated profile list.

Keep `TUNNEL_TOKEN` in the deployment `.env` or secret manager. Do not commit a
real token.

## Backups Opt-In

| Variable | Default | Required | Surface | Description | Docs |
| --- | --- | --- | --- | --- | --- |
| `BACKUP_SCHEDULE` | `0 0 3 * * *` | Optional when using the `backup` profile | Ofelia scheduler | Six-field cron expression for scheduled backups; default is daily at 03:00 UTC. | [Backups](backups.md) |
| `BACKUP_RETENTION_DAILY` | `7` | Optional when using the `backup` profile | Backup CLI | Number of recent backup tarballs to keep regardless of weekday. | [Backups](backups.md) |
| `BACKUP_RETENTION_WEEKLY` | `4` | Optional when using the `backup` profile | Backup CLI | Number of additional weekly backup tarballs to retain. | [Backups](backups.md) |

Scheduled backups do not run by default. They run only when you start Compose
with `COMPOSE_PROFILES=backup` or include `backup` in a comma-separated profile
list such as `COMPOSE_PROFILES=tunnel,backup`.

The `backups` sidecar stays idle until Ofelia executes the labeled backup job.
Manual backup and restore commands use the same application backup code and the
same `/backups` directory.

## Image Version

| Variable | Default | Required | Surface | Description | Docs |
| --- | --- | --- | --- | --- | --- |
| `SAFEHARBOR_VERSION` | empty, which resolves to `latest` in Compose | Optional, recommended for production | Docker image tag | Tag used by Compose for `ghcr.io/danner26/safeharbor`. | [Update](update.md) |

Leave `SAFEHARBOR_VERSION` blank only when you intentionally want Compose to use
the moving `latest` tag. For production, pin a release tag such as `1.0.0` so
pulls, restarts, and rollbacks are predictable.

Changing `SAFEHARBOR_VERSION` affects the image tag only. It does not switch the
Flask config mode or replace required secrets.

## Timezone

| Variable | Default | Required | Surface | Description | Docs |
| --- | --- | --- | --- | --- | --- |
| `DEFAULT_TZ` | `UTC` when unset | Optional | Tank form defaults and timezone migration fallback | IANA timezone used as a fallback for new tank forms and timezone backfills. | - |

Use an IANA timezone name such as `America/New_York`. Browser JavaScript may
preselect the user's local timezone on modern clients, but `DEFAULT_TZ` remains
the server-side fallback for clients without that behavior.

Changing `DEFAULT_TZ` does not rewrite existing tank records. Each tank stores
its own timezone once created.
