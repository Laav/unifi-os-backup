# Local backup retention

[Documentation index](README.md) · [Retries and retention pins](RETRIES.md) · [Remote immutability](IMMUTABILITY.md)

Configure retention in the wizard's schedule/retention section, or edit protected literal settings manually. The default mode is `legacy`: age/count rules with a minimum safety floor. `gfs` selects daily, weekly, monthly and yearly representatives instead. Both modes respect pending replication pins.

## Age, count and minimum

An example policy:

```bash
RETENTION_MODE="legacy"
RETENTION_DAYS="35"
RETENTION_COUNT="12"
RETENTION_MIN_COUNT="2"
```

- `RETENTION_DAYS=0` disables deletion by age.
- `RETENTION_COUNT=0` disables the maximum-count limit.
- The newest `RETENTION_MIN_COUNT` backups remain protected even beyond the age limit.
- Outside that floor, either the age or count limit can select a backup for deletion.
- A nonzero count limit must be at least the minimum count.

The example normally retains at least two and at most twelve backups, deleting those older than 35 days outside the floor. Pending retry tasks can retain additional files beyond both limits; monitor queue state and available disk space.

## Grandfather-father-son policy

Opt in explicitly. For example:

```bash
RETENTION_MODE="gfs"
GFS_DAILY="14"
GFS_WEEKLY="8"
GFS_MONTHLY="12"
GFS_YEARLY="3"
```

GFS keeps the newest backup per distinct UTC filename period for each tier. The union of those tier representatives, the minimum-count floor and pending retry pins is protected. At least one tier must be nonzero. GFS replaces the ordinary age/count deletion selection; it does not impose an additional maximum count on protected representatives. Encryption does not change selection.

## Preview and apply

Inspect decisions before making a change:

```bash
sudo unifi-backup-retention --dry-run --json
```

Dry-run lists keep/delete decisions without deleting backups. To apply the reviewed policy without requesting a new UniFi backup:

```bash
sudo unifi-backup --retention-only
```

Normal backup runs also apply retention and rebuild the catalog. Do not run old retention implementations against sources still pinned by a newer retry queue.

## Deletion boundaries

Only managed `unifi_os_backup_YYYY-MM-DD_HH-MM-SS.unifi` and `.unifi.age` names are candidates. Removal also handles the artifact's exact `.json` sidecar; unrelated files are ignored. Empty/root paths, unsafe links, invalid values and unexpected sidecar object types fail safely.

Queue corruption blocks retention safely. Exhausted/expired or other terminal retry tasks become visible dead letters and release their pins. A dead letter means replication is no longer guaranteed; investigate it rather than assuming every retained backup is safely offsite.

Remote retention is administered separately through provider lifecycle policies. Keep object deletion out of upload credentials and align lifecycle expiry with required immutability and recovery windows. See [remote retention](STORAGE.md#remote-retention).
