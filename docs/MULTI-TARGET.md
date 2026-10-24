# Multiple independent destinations

Set `BACKUP_TARGETS="s3-primary azure-secondary mounted-disk"` and place each target's mode-0600 Bash configuration in the root-owned mode-0700 `/etc/unifi-backup/targets.d/` directory. Target IDs contain letters, digits, `_` or `-` only. The generic template is `config/target.env.example`; reuse cloud credentials/settings from `storage.env.example` in each target file.

Each target sets `TARGET_TYPE=s3|azure_blob|filesystem`, `TARGET_REQUIRED=true|false`, `TARGET_VERIFY=none|exists|metadata|full`, and its own timeouts/credentials. `BACKUP_REQUIRED_TARGETS` is the minimum number of successful **remote targets**; the local artifact never counts. Every required target must also succeed. Reports distinguish local integrity, successful/partial/failed replication and overall policy.

When `BACKUP_TARGETS` is nonempty it takes precedence over legacy `REMOTE_STORAGE_TYPE` so there are no duplicate uploads. Without it, the existing upload path/settings remain usable. New standalone tools map the legacy target to ID `legacy`.

Mounted targets require an existing private directory, a mount check by default, and a `.unifi-backup-target` marker containing the target ID. Disabling `FILESYSTEM_REQUIRE_MOUNT` explicitly permits a dedicated ordinary directory. Nothing creates the destination automatically when a mount disappears.

S3 and Azure expose conditional upload, HEAD, GET and paginated listing. Remote metadata objects are immutable snapshots of original backup identity; later operational annotations remain local. Full verification downloads actual bytes; ETags are opaque concurrency tokens and never used as hashes. Listing/read/immutability checks require additional provider permissions beyond legacy write-only credentials. No backend deletes remote objects.
