# Retention

Local retention combines age, maximum count, and a minimum safety floor:

```bash
RETENTION_DAYS="35"
RETENTION_COUNT="12"
RETENTION_MIN_COUNT="2"
```

Semantics:

- `RETENTION_DAYS=0` disables deletion by age.
- `RETENTION_COUNT=0` disables the maximum-count limit.
- `RETENTION_MIN_COUNT` always preserves that many newest backups, even when they exceed the age limit.
- When both age and count are enabled, a backup outside the minimum floor is deleted when either limit selects it.
- `RETENTION_COUNT` must be zero or at least `RETENTION_MIN_COUNT`.

For example, `35/12/2` keeps at least the newest two backups, deletes backups older than 35 days, and never retains more than the newest 12.

Only exact names matching `unifi_os_backup_YYYY-MM-DD_HH-MM-SS.unifi` are candidates. Deleting a backup also deletes only its exact `.unifi.json` metadata sidecar. Other files are ignored. Empty paths, `/`, symlink destinations, invalid numbers, and unexpected sidecar object types cause a safe failure.

Preview the directory yourself, then run retention without downloading a backup:

```bash
sudo find /var/backups/unifi -maxdepth 1 -type f -printf '%TY-%Tm-%Td %TT %f\n' | sort
sudo unifi-backup --retention-only
```

Remote object retention is deliberately not performed with the upload credential. Use Azure Blob or S3 lifecycle policies as described in [STORAGE.md](STORAGE.md#remote-retention).
