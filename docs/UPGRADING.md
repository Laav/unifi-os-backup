# Upgrading

## Upgrade 1.2.0 source to the published 1.3.0 release

Origin had no published release/tag before 1.3.0; the preceding source version was 1.2.0 at `0d96e1f`. The updater continues to install the currently checked-out source. It does not fetch or choose a release itself.

```bash
cd /opt/unifi-os-backup
git status --short
sudo git fetch origin --tags
sudo git switch --detach v1.3.0
sudo ./update.sh
unifi-backup --version
sudo unifi-backup-check --live
sudo systemctl start unifi-backup.service
sudo unifi-backup-verify --latest --json
```

Review local modifications before switching. Existing credentials, age recipients/identities, backups and status data are preserved. No new cloud operation or lock is enabled by default. New optional settings are in the main example, and `targets.d/target.env.example` is installed without activating it.

Enable only the required scheduled operations after configuration/testing:

```bash
sudo systemctl enable --now unifi-backup-verify.timer
sudo systemctl enable --now unifi-backup-remote-verify.timer
sudo systemctl enable --now unifi-backup-retry.timer
```

Their corresponding `VERIFY_ENABLED`, `REMOTE_VERIFY_ENABLED`, and `RETRY_ENABLED` flags also need `true`. Timer intervals are independent systemd drop-ins; retry backoff is independent of timer frequency. A missing new flag means disabled. New remote reads/listing/immutability require reviewed permissions; legacy write-only credentials remain sufficient for the original uploader.

For a later release rollback, select the previously verified published tag and rerun its updater. Because no preceding published release exists for this first release, the documented source rollback is `git switch --detach 0d96e1f`, then `sudo ./update.sh`. First disable the new timers, preserve monitoring/queue files and inspect pending/dead tasks; the old version does not understand retry pins or GFS. Do not run old retention against backups still required by the new retry queue. Encrypted artifacts and original metadata remain compatible, but new operational annotations may be ignored by old tooling.

The existing `main` workflow remains available: switch to `main`, review status, use `git pull --ff-only`, then run `update.sh`. Use the release tag for a reproducible stable installation. See [RELEASING.md](RELEASING.md).

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
