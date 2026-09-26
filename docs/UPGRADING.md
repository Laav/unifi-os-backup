# Upgrading

Read `CHANGELOG.md`, verify the commit/tag, and inspect changes to `bin/`, `systemd/`, and configuration examples.

```bash
cd /opt/unifi-os-backup
git status --short
sudo git pull --ff-only
sudo ./update.sh
sudo unifi-backup-check --live
sudo systemctl start unifi-backup.service
sudo journalctl -u unifi-backup.service -n 100 --no-pager
```

The updater replaces installed executables, the shared library, and units. It does not replace or remove existing files in `/etc/unifi-backup` and never changes `/var/backups/unifi`. It creates newly introduced optional configuration examples only when absent, using fictitious placeholders and mode 0600. New main settings appear in `config/unifi-backup.env.example`; merge the settings you intend to use manually.

## Upgrading from 1.1.0 to 1.2.0

The safe defaults keep encryption and webhooks disabled. After `update.sh`, review and optionally add:

```bash
ENCRYPTION_TYPE="none"
AGE_RECIPIENTS_FILE="/etc/unifi-backup/age-recipients.txt"
CATALOG_FILE="/var/lib/unifi-backup/catalog.json"
STALE_WARNING_HOURS="192"
STALE_CRITICAL_HOURS="216"
NOTIFY_ON_STALE="true"
ENABLE_WEBHOOK="false"
WEBHOOK_CONFIG_FILE="/etc/unifi-backup/webhook.env"
```

The updater creates missing `webhook.env` and `age-recipients.txt` examples but never replaces existing files. It installs and enables the monitor timer without starting a previously inactive timer. After choosing thresholds:

```bash
sudo unifi-backup-check --live
sudo systemctl start unifi-backup.service
sudo systemctl enable --now unifi-backup-monitor.timer
sudo unifi-backup-catalog --print
```

Install `age` and complete the separate recovery-key procedure in [ENCRYPTION.md](ENCRYPTION.md) before changing `ENCRYPTION_TYPE` to `age`. Test decryption and a non-production restore before depending on encrypted backups.

## Upgrading from 1.0.x to 1.1.0

Existing installations remain local-only by default because missing new variables receive safe defaults. After `update.sh`, review and optionally add:

```bash
RETENTION_COUNT="0"
RETENTION_MIN_COUNT="1"
BACKUP_DOWNLOAD_RETRIES="1"
BACKUP_RETRY_DELAY="15"
LOG_FORMAT="text"
STATUS_FILE="/var/lib/unifi-backup/status.json"
REMOTE_STORAGE_TYPE="none"
STORAGE_CONFIG_FILE="/etc/unifi-backup/storage.env"
REMOTE_UPLOAD_REQUIRED="true"
ENABLE_NTFY="false"
NTFY_CONFIG_FILE="/etc/unifi-backup/ntfy.env"
NOTIFY_ON_SUCCESS="false"
NOTIFY_ON_FAILURE="true"
NOTIFY_ON_RECOVERY="true"
```

Do not paste cloud or ntfy secrets into the main file; keep them in their separate mode-0600 files. A first real run creates the status/metrics files and a metadata sidecar. Confirm:

```bash
sudo unifi-backup-status
sudo ls -l /var/lib/unifi-backup
sudo ls -l /var/backups/unifi/*.unifi.json
```

If local repository changes exist, stop and review them instead of forcing a pull. Keep local configuration outside the checkout, use systemd drop-ins for local unit changes, and avoid editing installed scripts directly.

After any UniFi OS upgrade, repeat both the live login check and a real backup because the controlplane endpoints are not a stable public API. After Microsoft configuration changes, send a small test backup and verify message trace.

Rollback by checking out a previously verified tag, running `update.sh`, and retesting. Configuration migrations, when introduced, will be documented in the changelog.
