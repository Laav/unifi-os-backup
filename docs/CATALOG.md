# Central backup catalog

`/var/lib/unifi-backup/catalog.json` is an atomically rebuilt, machine-readable inventory of every managed backup currently present in `BACKUP_DIR` with a valid metadata sidecar.

It contains:

- backup ID, configured controller origin, host, timestamp, filename, size, and SHA256;
- encryption type and whether encryption is enabled;
- local/remote storage status;
- validation/checksum metadata;
- a summary and snapshot of the latest operational status.

The project does not query an undocumented endpoint to invent a firmware version. Firmware is therefore omitted until it can be obtained through a demonstrated, supportable interface.

Rebuild or inspect the catalog:

```bash
sudo unifi-backup-catalog \
  --backup-dir /var/backups/unifi \
  --catalog-file /var/lib/unifi-backup/catalog.json \
  --status-file /var/lib/unifi-backup/status.json
sudo unifi-backup-catalog --print
```

Normal backup and retention-only runs rebuild it automatically. Orphaned, oversized, malformed, symlinked, or filename-mismatched sidecars are excluded. The catalog is mode 0600 because it identifies controllers and storage outcomes.

The catalog covers one installation/controller today. A central management system can collect this stable JSON schema from multiple backup hosts. Multi-controller orchestration remains a separate future feature.

Catalog metadata records validation performed at backup creation. It does not decrypt or restore-test an age artifact, and it is not a cryptographic signature. Keep separately controlled monitoring history if tamper evidence is required.
