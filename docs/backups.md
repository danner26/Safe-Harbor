# Backups

## Overview

Safe Harbor's backup sidecar creates a portable archive of the application database and uploaded files. The sidecar runs the same Flask management command used for manual backups, but it is kept in a separate Compose service so scheduled backup work does not run inside the web request process.

Scheduled backups run through the `backup` compose profile. When the profile is enabled, ofelia watches the `backups` service labels and executes `flask safeharbor backup` on the configured cron schedule. Output lands in `/backups/` inside the container, which is mounted to `./backups/` on the host.

## What's included

Each backup is one tarball named:

```text
./backups/safeharbor-backup-<UTC>.tar
```

The timestamp is generated in UTC with second precision, for example:

```text
safeharbor-backup-2026-05-07T03-00-00Z.tar
```

The tarball contains:

| Path | Description |
| --- | --- |
| `db.dump` | PostgreSQL custom-format dump created by `pg_dump -F c`. |
| `uploads/` | The full Safe Harbor uploads tree from the application upload volume. |

The command writes to a temporary `*.tmp` archive first, then atomically replaces the final tarball path when the archive is complete.

## Configuration

Configure scheduled backup behavior in `.env`.

| Var | Default | Description |
| --- | --- | --- |
| `BACKUP_SCHEDULE` | `0 0 3 * * *` | ofelia 6-field cron expression (default = daily 03:00 UTC) |
| `BACKUP_RETENTION_DAILY` | `7` | Keep this many recent tarballs regardless of weekday |
| `BACKUP_RETENTION_WEEKLY` | `4` | Additionally keep one tarball per ISO week, up to this many weeks |

`BACKUP_SCHEDULE` uses ofelia's six-field cron syntax:

```text
second minute hour day-of-month month day-of-week
```

The default value runs once per day at 03:00 UTC.

Retention settings are read by the backup command after each successful archive is written. They apply only to files matching Safe Harbor's backup filename pattern:

```text
safeharbor-backup-YYYY-MM-DDTHH-MM-SSZ.tar
```

## Enabling scheduled backups

Enable the `backup` compose profile in `.env`:

```dotenv
COMPOSE_PROFILES=backup
```

If another optional profile is already enabled, use a comma-separated list:

```dotenv
COMPOSE_PROFILES=tunnel,backup
```

Then start or refresh the stack:

```bash
docker compose up -d
```

Compose starts the `ofelia` scheduler and the idle `backups` sidecar whenever the `backup` profile is active. Ofelia then executes the labeled backup job inside the `backups` container according to `BACKUP_SCHEDULE`.

Confirm the profile services are present:

```bash
docker compose --profile backup ps ofelia backups
```

## Manual on-demand backup

Run the backup command directly in the sidecar when you want a backup immediately:

```bash
docker compose --profile backup exec backups flask safeharbor backup
```

!!! tip "Manual backups use the same output path"
    The command writes to `/backups/` inside the container. In the standard Compose stack that is the host directory `./backups/`, so the new tarball appears beside scheduled backups.

The command prints the output path and final archive size. If retention deletes older tarballs during the same run, it also prints the number of pruned files.

## Retention algorithm

After each successful backup, Safe Harbor scans the output directory for files matching `safeharbor-backup-*.tar` with the expected timestamped filename shape. Files that do not match that pattern are ignored by retention.

The command sorts matching tarballs by file modification time, newest first. It keeps the set union of:

```text
{BACKUP_RETENTION_DAILY most recent tarballs}
union
{first tarball encountered for each ISO week, up to BACKUP_RETENTION_WEEKLY weeks}
```

Any matching tarball outside that kept set is deleted.

For example, assume `BACKUP_RETENTION_DAILY=7`, `BACKUP_RETENTION_WEEKLY=4`, and 14 daily backups span 2 ISO weeks. The algorithm keeps:

```text
{7 most recent} union {1 per ISO week x 4 weeks}
```

That means up to 7 daily backups plus up to 4 weekly marker backups are retained, with overlap deduplicated. In the 14-backup, 2-week example, the weekly markers may already be among the 7 most recent files, so the final count can be less than 11.

Weekly markers are based on each tarball's file modification time in UTC, not on a timestamp parsed from inside the archive.

## Off-site copy

Keep `./backups/` on durable local storage, then copy or sync that directory to storage outside the Docker host. The backup command only writes local tarballs; off-site transfer is a host responsibility.

### SMB (Windows / generic)

Install CIFS support on the host, then create a credentials file readable only by root:

```bash
sudo install -m 0600 -o root -g root /dev/null /etc/safeharbor-smb.credentials
```

Example credentials file:

```ini
username=backup-user
password=change-this-password
domain=WORKGROUP
```

Mount the SMB share:

```bash
sudo mkdir -p /mnt/safeharbor-backups
sudo mount.cifs //nas.example.local/safeharbor-backups /mnt/safeharbor-backups \
  -o credentials=/etc/safeharbor-smb.credentials,uid=1000,gid=1000,iocharset=utf8,file_mode=0600,dir_mode=0700
```

Sample `/etc/fstab` entry:

```fstab
//nas.example.local/safeharbor-backups /mnt/safeharbor-backups cifs credentials=/etc/safeharbor-smb.credentials,uid=1000,gid=1000,iocharset=utf8,file_mode=0600,dir_mode=0700,nofail,x-systemd.automount 0 0
```

Point Safe Harbor's `./backups/` directory at the mounted path. One simple option is to replace `./backups/` with a symlink:

```bash
mkdir -p /mnt/safeharbor-backups/current
ln -sfn /mnt/safeharbor-backups/current ./backups
```

You can also keep `./backups/` as a normal local directory and run a host-level sync job from `./backups/` to the mounted share.

### NFS (Linux / generic)

Install NFS client support on the host, create a mountpoint, and mount the export with NFSv4:

```bash
sudo mkdir -p /mnt/safeharbor-backups
sudo mount.nfs nas.example.local:/exports/safeharbor-backups /mnt/safeharbor-backups \
  -o nfsvers=4,rw,hard,noatime
```

Sample `/etc/fstab` entry:

```fstab
nas.example.local:/exports/safeharbor-backups /mnt/safeharbor-backups nfs nfsvers=4,rw,hard,noatime,nofail,x-systemd.automount 0 0
```

As with SMB, either point `./backups/` at a directory on the mount or keep `./backups/` local and sync it to the mounted path from the host.

### Build your own

Tools such as rclone, restic, and borg are good fits for host-managed backup replication. Point them at `./backups/`, let Safe Harbor produce the local tarballs, and keep the transfer policy outside the application stack.

## Security note: docker socket exposure

!!! warning "Ofelia needs limited Docker socket access"
    Ofelia mounts `/var/run/docker.sock` read-only so it can discover labeled containers and run the configured exec job inside the `backups` container. This is an exec-only scheduling model: the scheduler does not need start or stop privileges for this workflow, but Docker socket access is still sensitive because the worst-case impact is the ability to execute commands inside other containers, no start/stop privilege.

The compose service applies two container-level mitigations:

- `no-new-privileges:true` prevents the ofelia process from gaining extra privileges inside its container.
- `read_only: true` gives the ofelia container a read-only filesystem.

These mitigations reduce the scheduler container's write surface, but they do not make Docker socket access risk-free. Run the backup profile only on hosts where the Compose operator is trusted.

## Disaster recovery

Backups are only useful if they can be restored. See [Restore](restore.md) for the disaster recovery procedure, including dry-run validation and the restore command that overwrites the database and uploads from a selected tarball.
