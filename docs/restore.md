# Restore

Use this procedure to restore Safe Harbor from a backup tarball created by
`flask safeharbor backup`.

The restore command replaces the PostgreSQL database and uploads directory with
the contents of the selected tarball. Run the dry-run validation first, then
stop the application before the destructive restore.

## When to use this

Use this guide for three restore scenarios.

### Disaster recovery

Use this when the Docker host died, the disk failed, or the original machine is
gone. Start from a fresh Safe Harbor deployment, place a known-good tarball in
`./backups/`, and restore it through the `backups` sidecar.

### Point-in-time rollback

Use this when recent corruption means the whole application state must roll
back to an earlier backup. This restores database rows and uploaded files from
the selected point in time.

### Dev refresh

Use this to refresh a local development database from a production backup.
Confirm the local `.env` points at the local database before running the
restore.

## Pre-restore checklist

1. Stop the web app:

    ```bash
    docker compose stop web worker
    ```

2. Confirm `DATABASE_URL` in your `.env` points at the database you intend to
   overwrite.

3. Optional: take a fresh backup of current state first:

    ```bash
    docker compose --profile backup exec backups flask safeharbor backup
    ```

## Step 1: Validate the tarball with `--dry-run`

Run the dry-run before every restore:

!!! warning "Use the container path, not the host path"
    The `--from` value is resolved inside the `backups` container.
    Use `/backups/<filename>.tar` (the container's bind-mount path),
    not the host path like `/Users/me/Source/Safe-Harbor/app/backups/<filename>.tar`.

```bash
docker compose --profile backup exec backups flask safeharbor restore --from /backups/<filename>.tar --dry-run
```

!!! tip "Dry-run first"
    The dry-run checks that the tarball is readable, contains the expected
    `db.dump` and `uploads/` members, and can be inspected by `pg_restore`.
    It does not overwrite the database or uploads.

A successful dry-run prints a summary like this:

```text
would restore N tables, M upload files (total <size>) from <path>
```

Success means:

- The command exits with status `0`.
- The tarball structure passed validation.
- `pg_restore --list` could inspect the database dump.
- No database rows or upload files changed.

If the dry-run fails, do not continue to the destructive restore. Re-check the
filename, re-fetch the backup from your off-site copy, or restore a different
tarball.

## Step 2: Run the restore

After the dry-run succeeds and the app is stopped, run the restore:

```bash
docker compose --profile backup exec backups flask safeharbor restore --from /backups/<filename>.tar
```

!!! danger "This overwrites application state"
    The restore replaces the target database contents and upload files with
    the contents of the selected backup tarball. Confirm `.env` points at the
    database you intend to overwrite before you continue.

The command prompts before making destructive changes:

```text
Type 'restore' to confirm — this WILL OVERWRITE the database and uploads:
```

Type exactly `restore` and press Enter to proceed:

```text
restore
```

Any other input aborts the restore and leaves the destructive step unstarted.

For non-interactive use, such as a recovery script, pass `--yes` to skip the
prompt:

```bash
docker compose --profile backup exec backups flask safeharbor restore --from /backups/<filename>.tar --yes
```

Use `--yes` with care. It removes the final human confirmation before the
database and uploads are overwritten.

When the restore finishes, it prints
`restored N tables and M upload files from /backups/<filename>.tar`.

## Step 3: Restart the app

Start the app containers again:

```bash
docker compose start web worker
```

Verify the restored state:

1. Open the site.
2. Log in.
3. View a tank dashboard.
4. Confirm measurements, animals, and uploaded images match the restored backup.

If something looks wrong, see Troubleshooting before attempting another restore.

## Troubleshooting

### Postgres version mismatch

If you migrated the host to a newer PostgreSQL major version since the backup,
`pg_restore` may fail. Restore into a fresh Postgres 16 instance, or downgrade
the host's Postgres version to match the backup source.

### Partial restore after crash mid-process

`pg_restore` is transactional. If it crashed mid-restore, the database may be in
an inconsistent state. Drop the database and restore fresh from the tarball.

### Corrupted tarball

Re-fetch the tarball from your off-site copy, such as a NAS or restic
repository. The dry-run surfaces tarball corruption before the destructive
restore step.

### Manual recovery

Advanced users can unpack the tarball manually and restore each part by hand:

```bash
tar -xf <file>.tar
pg_restore --clean --if-exists --no-owner --no-acl -d <database> db.dump
cp -r uploads/* /data/uploads/
```

Use manual recovery only when the normal restore command is not available. Point
`pg_restore` at the correct database and copy uploads into the correct volume
path.

## Drift caveats

Restoring an older backup into a newer schema can fail or produce a confused
state if migrations were applied between the backup and now.

Use one of these approaches instead: restore into an empty database and re-apply
migrations forward, or run `flask db downgrade` before restoring a backup that
matches that older schema.

Do not assume the application will repair drift between an old backup and a
newer partially migrated database.
