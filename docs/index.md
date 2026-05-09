# Safe Harbor Documentation

Safe Harbor is a self-hosted aquarium recordkeeping app for people who want
their tank notes, livestock history, maintenance records, and water-quality data
in one place they control.

This documentation is written for operators: the person installing the app,
keeping it updated, watching backups, and restoring service when something goes
wrong. It favors practical steps, expected files, and operational checks over
marketing copy.

Use these pages when you are preparing a new install, reviewing an existing
deployment, or documenting how your household or club runs Safe Harbor.

## What Safe Harbor is

Safe Harbor helps aquarium keepers track tanks, livestock, water-quality
readings, trend charts, and tank-side notes from a mobile-friendly web app. It is
designed to be run by the hobbyist or organization using it, with application
data stored in a database you administer and uploaded files stored on disk in the
deployment environment.

## What's in these docs

- [Installation](install.md) covers the supported setup path, including local
  prerequisites, environment preparation, database initialization, and first
  access checks.

- [Configuration](config.md) explains the environment variables and runtime
  settings that control database access, uploads, email, sessions, proxy
  handling, and other deploy-time behavior.

- [Architecture](architecture.md) describes the major application components,
  request flow, data boundaries, and the operational assumptions behind the
  Flask app, database, uploads, jobs, and proxy layer.

- [Backups](backups.md) explains what needs to be backed up, where backup
  artifacts are written, how scheduled backups are configured, and which health
  checks prove the backup process is working.

- [Restore](restore.md) walks through restore planning, dry-run validation, and
  the command path for recovering the database and uploaded files from a selected
  backup archive.

- [Observability](observability.md) covers logs, health checks, error reporting,
  and the signals operators should inspect before and after deployment changes.

- [Updates](update.md) outlines a practical update workflow: review release
  notes, back up first, apply the new version, run migrations, and verify the
  service before returning it to normal use.

- [Troubleshooting](troubleshooting.md) collects common failure modes and
  recovery checks for startup problems, database connectivity, proxy behavior,
  uploads, scheduled jobs, and restore issues.

## Where things live

- Public repository:
  [https://github.com/danner26/Safe-Harbor](https://github.com/danner26/Safe-Harbor)

- Issue tracker:
  [https://github.com/danner26/Safe-Harbor/issues](https://github.com/danner26/Safe-Harbor/issues)

- Security contact:
  [SECURITY.md](../SECURITY.md)

The repository is the source of truth for released code, documentation, issue
tracking, and security reporting instructions. If you are operating Safe Harbor
for someone else, keep your local deployment notes close to these docs so future
maintenance does not depend on informal notes or personal recall.

## Reading path

For a first install, start with [Installation](install.md), then review
[Configuration](config.md) before starting the service. After the app is running,
read [Backups](backups.md) and [Restore](restore.md) together; a backup strategy
is incomplete until restore has been tested.

For an existing deployment, check [Updates](update.md) before changing versions
and keep [Observability](observability.md) open while verifying the running app.
If something fails, use [Troubleshooting](troubleshooting.md) to narrow the
problem before changing configuration or rebuilding containers.

For maintainers and reviewers, [Architecture](architecture.md) provides the
shared map of the system. It is the best starting point when deciding whether a
change belongs in application code, deployment configuration, database schema,
or operational documentation.
