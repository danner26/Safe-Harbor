# Safe Harbor

Self-hosted aquarium tracking for private, owner-controlled tank records.

Safe Harbor is an open-source aquarium tracker for people who want their tank
data to live on their own system. It is built for single-tenant home aquarists
and small-fish-room operators who need practical records without handing
livestock history, water readings, or maintenance notes to a hosted service.

The project focuses on privacy, local control, and data ownership. You run the
application, keep the database, decide how it is exposed, and choose how backups
leave the machine. That keeps day-to-day husbandry records useful without
creating lock-in around the service that stores them.

## Features

- Tank inventory for aquariums, systems, and equipment context.
- Livestock history for current animals, removals, deaths, transfers, and notes.
- Water-quality logging with trend charts powered by Plotly.
- Mobile-friendly batch entry for tank-side measurement sessions.
- Scheduled local backups and restore documentation for recovery drills.
- Optional Cloudflare Tunnel support for controlled remote access.
- Configurable timezone handling for local schedules and timestamps.

## Quickstart

This abridged path is for local evaluation or development. For a complete
walkthrough, use the [installation guide](docs/install.md).

1. Clone the repository:

   ```bash
   git clone https://github.com/danner26/Safe-Harbor.git
   cd Safe-Harbor
   ```

2. Install Python 3.12 and `uv`, then install project dependencies:

   ```bash
   uv sync --extra dev
   ```

3. Create local configuration:

   ```bash
   cp .env.example .env
   ```

   Review the values in `.env`, especially database, upload, timezone, tunnel,
   and backup settings.

4. Start the application with Docker Compose:

   ```bash
   docker compose pull web
   docker compose up -d web
   ```

   Open <http://localhost:8000> and follow the rest of
   [docs/install.md](docs/install.md) for first-user setup and production notes.

## Documentation

Rendered documentation is published with MkDocs at:

<https://danner26.github.io/Safe-Harbor/>

The documentation source starts at [docs/index.md](docs/index.md), with these
entry points:

- [Installation](docs/install.md)
- [Configuration](docs/config.md)
- [Deployment](docs/deploy.md)
- [Observability](docs/observability.md)
- [Updates](docs/update.md)

## Backups And Restore

Safe Harbor includes an opt-in scheduled local backup sidecar for Docker
deployments. When enabled, the backup service writes dated tarballs under the
configured backup directory. Those archives are intended to capture database
state and uploaded files together so a restore can recover the records that make
the app useful.

Read [Backups](docs/backups.md) before enabling the schedule. It covers local
retention, off-site copy options, and the Docker Compose profile used by the
backup service.

Read [Restore](docs/restore.md) before you need it. A backup process is only
useful if the restore path has been rehearsed on the same kind of deployment you
expect to recover.

## Development Checks

Common local checks:

```bash
ruff check .
ruff format --check .
mypy src/safeharbor
pytest -q tests/unit
```

Integration and visual checks require the Docker stack and documented runtime
prerequisites. See the project documentation for environment-specific commands.

## Status

Status: v1 candidate. Cutover post-merge.

## License

Apache 2.0; see [LICENSE](LICENSE).
