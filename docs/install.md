# Installation

This quickstart gets a new Safe Harbor instance running from the published
container images. It is written for a single Docker host and uses the default
Compose file in the repository.

The default first-run path is intentionally local: the app listens on
`http://localhost:8000/`, uses the development configuration from the Compose
file, and creates the first administrator through the browser setup flow.
Review [Configuration](config.md) before publishing the service beyond the
host.

## 1. Prerequisites

Install these tools on the host before cloning Safe Harbor:

- Docker Engine 24 or newer
- Docker Compose v2
- Git

Use a host with at least:

- 2 GB RAM
- 10 GB free disk space

Supported host platforms:

- Linux
- macOS
- Windows through WSL2

If you expose Safe Harbor directly with a reverse proxy instead of Cloudflare
Tunnel, make sure inbound ports `80` and `443` are open on the host firewall
and reachable from the internet. The default local quickstart does not need
those public ports.

Confirm Docker and Compose are available:

```bash
docker --version
docker compose version
```

Confirm the Docker daemon is running:

```bash
docker info
```

If `docker info` fails, start Docker Desktop on macOS or Windows, or start the
Docker service on Linux before continuing.

## 2. Clone the repo

Clone Safe Harbor and enter the repository:

```bash
git clone https://github.com/danner26/Safe-Harbor.git
cd Safe-Harbor
```

The commands in the rest of this guide assume your shell is in the repository
root, next to `docker-compose.yml` and `.env.example`.

## 3. Configure .env

Create the local environment file:

```bash
cp .env.example .env
```

Open `.env` in your editor and review the minimum first-run settings:

```dotenv
FLASK_CONFIG=development
SECRET_KEY=change-me-in-prod
TRUST_PROXY_HEADERS=0
SAFEHARBOR_VERSION=
SERVER_NAME=
```

Set `SECRET_KEY` before using the app. Use a long random value:

```bash
openssl rand -hex 32
```

Replace the placeholder in `.env`:

```dotenv
SECRET_KEY=paste-a-random-value-here
```

Decide whether Safe Harbor should trust reverse-proxy headers:

```dotenv
TRUST_PROXY_HEADERS=0
```

Use `TRUST_PROXY_HEADERS=0` for the local quickstart, where no trusted proxy is
in front of the app. After setting up Cloudflare Tunnel, Caddy, nginx, or
another trusted reverse proxy, flip this to `TRUST_PROXY_HEADERS=1`; see
[Cloudflare Tunnel](deploy.md#cloudflare-tunnel) for the public-access path.

Leave `SAFEHARBOR_VERSION` blank for the latest published image:

```dotenv
SAFEHARBOR_VERSION=
```

For a stable install, pin a published image tag:

```dotenv
SAFEHARBOR_VERSION=1.0.0
```

Set `SERVER_NAME` only when Safe Harbor needs to send email links, such as
password reset links generated outside a web request:

```dotenv
SERVER_NAME=safeharbor.example.com
PREFERRED_URL_SCHEME=https
```

Leave `SERVER_NAME` blank for a local first run:

```dotenv
SERVER_NAME=
```

### Email is optional

SMTP is optional. Safe Harbor does not require an email server to operate;
password resets work without one. Leave `SMTP_HOST` unset on first install if
you do not have a relay ready — `/healthz` reports `"email": "disabled"` in
that state, and the app logs a startup `WARNING` explaining the deferral.

Two recovery paths work without SMTP:

- **Admin UI (share a one-time URL).** Sign in as an administrator and open
  **Admin → Users → \<user\>**, then click **Issue password reset**. A
  one-time URL appears on the page (expires in 1 hour); copy it and share it
  with the user through your usual channel. The user opens the URL, sets a
  new password, and signs in.
- **CLI (set a password directly).** From the host:

  ```bash
  docker compose exec web flask safeharbor reset-password user@example.com
  ```

  The command prompts for the new password (twice for confirmation) and
  updates it in place. Use this when you are the operator and the user — the
  recovery hatch for a forgotten sole-superuser password.

To enable outbound email later, set `SMTP_HOST` (and the related `SMTP_*`
keys documented in [Configuration](config.md#emailsmtp)) and restart the
stack. Configuring SMTP does not retroactively send messages for resets
issued in the no-SMTP window.

The default Compose stack runs `FLASK_CONFIG=development` for the first-run
setup flow. If you run Safe Harbor with `FLASK_CONFIG=production`, set
`SECRET_KEY` first, then pass `FLASK_CONFIG=production` through your Compose
override or deployment environment after reviewing [Configuration](config.md).

## 4. Pull + start

Pull the configured images:

```bash
docker compose pull
```

Create the host backup directory and assign ownership compatible with the
containers:

```bash
mkdir -p backups && sudo chown -R 1000:1000 backups
```

Safe Harbor bind-mounts `./backups` into the web and backups containers. The
container process writes as UID `1000`, so the host directory must be writable
by that UID before backups or restore exports can be created there.

Start the default stack:

```bash
docker compose up -d
```

The default stack starts the web app, Postgres, Redis, and the background
worker. Wait about 30 seconds while the entrypoint applies migrations and seeds
initial data.

Check container status:

```bash
docker compose ps
```

Check the app health endpoint:

```bash
curl -fsS http://localhost:8000/healthz
```

If the health check fails during the first few seconds, inspect logs and retry:

```bash
docker compose logs --tail=100 web
curl -fsS http://localhost:8000/healthz
```

The `cloudflared` service does not start by default. To run the Compose-managed
Cloudflare Tunnel sidecar, set a tunnel token and opt in to the `tunnel`
profile:

```dotenv
TUNNEL_TOKEN=your-cloudflare-tunnel-token
COMPOSE_PROFILES=tunnel
```

Then start with the same Compose command:

```bash
docker compose up -d
```

Use `COMPOSE_PROFILES=tunnel,backup` only when you want both the tunnel sidecar
and scheduled backup services.

## 5. First login

Open the local app:

```text
http://localhost:8000/
```

On a new install, Safe Harbor redirects to `/setup`. Enter the administrator
email address and password, submit the setup form, then sign in with that
administrator account.

For a headless or scripted install, create the administrator from the running
web container instead:

```bash
docker compose exec web flask --app safeharbor.wsgi:app safeharbor create-admin
```

Follow the prompts for the admin email address and password. After the command
finishes, visit `http://localhost:8000/` and sign in.

If the setup page does not load, or the CLI reports that the web service is not
running, use [Troubleshooting](troubleshooting.md) to check Compose status,
container logs, database connectivity, and health checks.

### Optional: Cloudflare Tunnel

Cloudflare Tunnel is the recommended path for publishing Safe Harbor without
opening inbound ports on a home or small-office network. Start with the local
install above. After reviewing [Deployment](deploy.md), configure tunnel setup
and reverse-proxy details for your environment.

### Optional: Backups

Backups are opt-in. After the app is running, review [Backups](backups.md) to
enable scheduled backups, choose retention settings, and confirm the backup
tarballs include both database data and uploaded files.

### Optional: Troubleshooting

For startup failures, unhealthy containers, setup problems, email issues, or
proxy routing problems, use [Troubleshooting](troubleshooting.md). Include
`docker compose ps`, recent `web` logs, and the failing command output when
diagnosing an install.
