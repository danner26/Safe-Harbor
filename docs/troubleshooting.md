# Troubleshooting

Use this guide when a Safe Harbor install, update, backup, restore, or tunnel
does not behave as expected. Run commands from the directory that contains
`docker-compose.yml`.

## Stack won't come up after `docker compose up -d`

Start with container state and the web/Postgres logs:

```bash
docker compose ps
docker compose logs --tail=100 web
docker compose logs --tail=100 postgres
```

Common causes are a host port conflict on `8000`, a missing `.env`, or a bad
`DATABASE_URL`. In the default Compose stack, `DATABASE_URL` should point at the
Compose service name `postgres`, not `localhost`. After fixing the cause, run:

```bash
docker compose up -d
docker compose logs --tail=100 web
```

## Empty parameter columns in batch entry

Older fresh installs could show empty measurement parameter columns because
reference tables were not seeded. The entrypoint now runs `safeharbor seed`
automatically after migrations, so new installs should have units, parameter
types, and parameter ranges before the app starts.

If the columns are still empty, run the seed manually and inspect its result:

```bash
docker compose exec web flask --app safeharbor.wsgi:app safeharbor seed
echo $?
docker compose logs --tail=100 web
```

## First-run wizard not showing

A brand-new install should redirect to `/setup` until the first administrator
exists. If it does not, inspect logs and database connectivity:

```bash
docker compose logs --tail=100 web
docker compose exec postgres pg_isready -U safeharbor
docker compose exec web flask --app safeharbor.wsgi:app shell
```

Inside the Flask shell:

```python
from safeharbor.models.account import User
User.query.count()
```

If the count is `0`, `/setup` should be available. If the count is greater than
`0`, the wizard is correctly hidden.

## `create-admin` CLI as a headless alternate

Use the CLI when the browser setup flow is unavailable, the host is headless, or
automation needs to create the first administrator after the stack is healthy.

```bash
docker compose exec web flask --app safeharbor.wsgi:app safeharbor create-admin
```

On a new install it prompts:

```text
Email:
Password:
Confirm password:
Unit system [imperial]:
```

Enter an administrator email address, a password of at least 10 characters, the
same password again, and either `imperial` or `metric`. The command refuses to
run after any user exists.

## Pre-upgrade backup didn't run on `docker compose pull`

`docker compose pull` only downloads images. The pre-upgrade backup check runs
when a new web or worker container starts and the entrypoint sees that the
current database revision differs from the migration heads.

```bash
docker compose exec web flask --app safeharbor.wsgi:app db current
docker compose exec web flask --app safeharbor.wsgi:app db heads
docker compose exec web sh -c 'test -w /backups && echo writable'
docker compose logs --tail=150 web
```

If `current` already matches `heads`, no pre-upgrade backup is expected. During
startup with pending migrations, a log line of
`pre-upgrade backup failed; continuing` usually means the host `./backups` bind
mount is missing or not writable by the container user. Use the install guide's
backup directory pre-create command:

```bash
mkdir -p backups && sudo chown -R 1000:1000 backups
docker compose up -d --force-recreate web worker
```

## Restore fails with Postgres version mismatch

Safe Harbor backup tarballs wrap a PostgreSQL custom-format dump at `db.dump`
plus the saved `uploads/` tree. The embedded dump follows PostgreSQL
dump/restore compatibility rules, so restoring with an older `pg_restore` than
the source `pg_dump` can fail.

Before a destructive restore, ask Safe Harbor to inspect the archive with a
dry-run:

```bash
docker compose --profile backup exec backups flask safeharbor restore --from /backups/<filename>.tar --dry-run
```

For advanced archive inspection, extract `db.dump` from the tarball into a
temporary directory before running `pg_restore --list`:

```bash
mkdir -p /tmp/safeharbor-restore-check
tar -xf /path/to/<filename>.tar -C /tmp/safeharbor-restore-check db.dump
pg_restore --list /tmp/safeharbor-restore-check/db.dump
```

If the restore tool is too old for the archive, upgrade the Postgres image or
restore into a matching newer Postgres container before running the normal
restore command.

## Cloudflare Tunnel won't connect or returns 502

Check both sides of the tunnel:

```bash
docker compose logs --tail=100 cloudflared
docker compose logs --tail=100 web
```

Likely causes are a missing or wrong `TUNNEL_TOKEN`, a public hostname in the
Cloudflare dashboard that does not point to `http://web:8000`, missing
`TRUST_PROXY_HEADERS=1`, or a `FORWARDED_ALLOW_IPS` value that excludes the
proxy path. Dynamic tunnel environments commonly need the default `*` unless
you have a stable proxy IP.

After changing `.env`, recreate the affected containers:

```bash
docker compose up -d --force-recreate web cloudflared
```

## Backups don't run

Scheduled backups run only when the `backup` Compose profile is active and
Ofelia is running. Check `.env`:

```dotenv
COMPOSE_PROFILES=backup
BACKUP_SCHEDULE=0 0 3 * * *
```

`BACKUP_SCHEDULE` must be a six-field cron expression:
`second minute hour day-of-month month day-of-week`.

```bash
docker compose --profile backup ps ofelia backups
docker compose --profile backup logs --tail=100 ofelia
docker compose --profile backup exec backups sh -c 'test -w /backups && echo writable'
```

If `/backups` is not writable, fix the host bind mount:

```bash
mkdir -p backups && sudo chown -R 1000:1000 backups
```

## GHCR pull fails

If the container package or requested tag is private, GHCR image pulls require
authentication:

```bash
docker login ghcr.io
docker compose pull
```

If the package is public, anonymous pulls should work for normal installs. If
pulls still fail, check authentication state, the requested tag, network
restrictions, and registry rate limits.

## `flask safeharbor seed` fails on re-run

The seed command should be idempotent. Existing units, parameter types, and
parameter ranges are matched by natural keys and skipped instead of duplicated.

Capture the exact failing command, exit status, and stderr:

```bash
docker compose exec web flask --app safeharbor.wsgi:app safeharbor seed
echo $?
docker compose logs --tail=100 web
```

Open a GitHub issue with that output, the Safe Harbor image tag, and the natural
key mentioned in the conflict. Do not manually delete reference rows unless you
have a database backup and understand which measurements depend on them.
