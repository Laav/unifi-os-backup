# Upgrading

Read `CHANGELOG.md`, verify the commit/tag, and inspect changes to `bin/`, `systemd/`, and configuration examples.

```bash
cd /opt/unifi-os-backup
git status --short
sudo git pull --ff-only
sudo ./update.sh
sudo unifi-backup-check --live
sudo systemctl start unifi-backup.service
```

The updater replaces installed executables and units only. It does not edit or remove `/etc/unifi-backup` and `/var/backups/unifi`. New settings appear only in `config/*.example`; merge them manually when the changelog says they are required.

If local repository changes exist, stop and review them instead of forcing a pull. Keep local configuration outside the checkout, use systemd drop-ins for local unit changes, and avoid editing installed scripts directly.

After any UniFi OS upgrade, repeat both the live login check and a real backup because the controlplane endpoints are not a stable public API. After Microsoft configuration changes, send a small test backup and verify message trace.

Rollback by checking out a previously verified tag, running `update.sh`, and retesting. Configuration migrations, when introduced, will be documented in the changelog.
