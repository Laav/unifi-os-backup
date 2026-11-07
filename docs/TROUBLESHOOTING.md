# Troubleshooting

[Documentation index](README.md) · [Operations](OPERATIONS.md) · [Exit codes](EXIT-CODES.md)

## Start with the last run

```bash
sudo journalctl -u unifi-backup.service --since "10 minutes ago" --no-pager
sudo systemctl show unifi-backup.service -p ActiveState -p SubState -p Result -p ExecMainStatus
unifi-backup-status --format json
```

`systemctl start` does not stream normal job progress. A successful oneshot normally becomes inactive after finishing; use `Result` and `ExecMainStatus` together with the complete journal. Login success alone does not confirm that a backup was created. A successful local backup can still be followed by an integration failure.

For missing email, first confirm `Backup successful`, then inspect later Graph events and any earlier failure that stopped the workflow. Confirm email is enabled through the wizard or a private editor. HTTP 202 confirms API acceptance, not delivery; see [Graph failures](#graph-failures). Never post configuration contents or raw HTTP response bodies to diagnose a failure.

## Configuration manager

Use `sudo unifi-backup-configure --validate --json` or a non-mutating `--inspect`. The full wizard requires dialog, a real TTY and at least 60x18; use `ssh -t` when needed. Installer/updater automatically provision missing dependencies; rerun the reviewed current updater if dialog is missing. Check its APT errors and configured repositories/network access if provisioning fails. `--no-install-deps` explicitly disables this behavior. Unsupported shell expressions are deliberately refused rather than executed. Insecure ownership/modes and symlinks must be corrected explicitly.

### Systemd override warning

`Existing administrator drop-ins are retained` is a general reminder emitted by the validator, including when no conflicting administrator override was detected. Warnings alone return 0; JSON output reports `valid: true` when there are no errors. Do not remove overrides to silence this reminder. Inspect the effective units/calendars after deliberately changing paths or schedules.

### Shell expansion is unsupported

Genuine shell expansion such as `$VARIABLE`, `${VARIABLE}` or `$(command)` is unsupported by the manager, even if a legacy Bash reader accepts it. Literal dollars are supported; if an older installation rejects them, follow [UPGRADING.md](UPGRADING.md). Diagnostics identify the file basename, line and setting without printing its value. Inspect that location locally using `sudoedit`; preserve the intended effective value using a literal assignment. Single quotes preserve literal dollars; the manager's serializer safely handles embedded quotes. Never post complete env files, password lines or secret-bearing diffs for troubleshooting. Validation and update do not rewrite these files or execute their contents.

An active configuration lock returns 75; wait and reload instead of deleting the lock inode. An interrupted multi-file apply leaves a private pending marker and blocks updated readers: use `sudo unifi-backup-configure --recover --yes` with the same `--config` path. Never remove the marker to bypass recovery. Custom schedules require `systemd-analyze`, and custom directories must be compatible with the hardened units. See [CONFIGURE.md](CONFIGURE.md) for rollback, overrides and explicit timer activation.

## Endpoint compatibility

The repository uses:

- `POST /api/auth/login`
- `GET /api/backup/download`
- best-effort `POST /api/auth/logout`

These are observed local UniFi OS controlplane endpoints; Ubiquiti's public documentation explains UI-based System Config Backup download but does not promise this API contract. They are not the documented UniFi Network Integration API. No speculative fallback endpoint is attempted.

Before and after every UniFi OS upgrade:

```bash
sudo unifi-backup-check --live
sudo systemctl start unifi-backup.service
sudo journalctl -u unifi-backup.service -n 100 --no-pager
```

`--live` logs in and verifies the TOKEN cookie but does not request a backup. A real service run is needed to test the download endpoint. The implementation safely keeps an incomplete response hidden and deletes it on failure.

Ubiquiti references:

- [Backups and Migration in UniFi](https://help.ui.com/hc/en-us/articles/360008976393-Backups-and-Migration-in-UniFi)
- [Adding Admins in UniFi](https://help.ui.com/hc/en-us/articles/28692158912279-Adding-Admins-in-UniFi)
- [UniFi roles explained](https://help.ui.com/hc/en-us/articles/1500011491541-UniFi-Roles-Explained-Admins-and-Users)
- [Self-Hosting UniFi](https://help.ui.com/hc/en-us/articles/34210126298775-Self-Hosting-UniFi)

## Expected errors

| Symptom | Interpretation/action |
|---|---|
| DNS resolution failed | Check host name, resolver, and network namespace |
| connection failed | Check address, port, firewall, service health |
| TLS/certificate validation failed | Fix hostname/chain/trust; set `UNIFI_CA_CERT` for a private CA; never use `-k` |
| timeout | Check server load/network; tune the two timeouts cautiously |
| HTTP 400 | Request contract may have changed; inspect UniFi release notes and browser developer tools without publishing secrets |
| HTTP 401 | Wrong credentials, account disabled, or login format changed |
| HTTP 403 | Account lacks backup permission or policy blocks it |
| HTTP 404 | Controlplane endpoint changed/was removed; stop automation and investigate, do not guess another path |
| HTTP 429 | Rate limiting; avoid repeated retries and wait |
| HTTP 500 | UniFi internal error; inspect server health/logs |
| HTTP 502/503/504 | Controlplane temporarily unavailable |
| no TOKEN cookie | Login was not actually established or auth behavior changed |
| error-like Content-Type/body | A login/error page was returned instead of a backup |
| backup too small | Server produced an incomplete/error response or minimum is unrealistic |
| lock active | An earlier run is still active; inspect `systemctl status`, do not delete the lock while it runs |

## systemd sandbox denial

For a custom `BACKUP_DIR`, review `ReadWritePaths` as documented in [CONFIGURATION.md](CONFIGURATION.md#paths-and-systemd). The wizard prepares narrow drop-ins; review manual overrides across all affected workers. Inspect denials with:

```bash
sudo journalctl -u unifi-backup.service -b
sudo systemd-analyze security unifi-backup.service
```

Do not weaken all hardening to solve one path mismatch.

## Graph failures

- `invalid_client`: client ID/secret wrong or expired.
- `invalid_scope`: scope must remain `https://graph.microsoft.com/.default`.
- `Authorization_RequestDenied`/403: admin consent, `Mail.Send`, Exchange RBAC scope, or mailbox is wrong.
- HTTP 413 or attachment-size error: lower the configured ceiling; the local backup remains available.
- HTTP 202 but no message: acceptance is asynchronous; use message trace and check Exchange rules/limits.

The software logs sanitized Graph error code/message only, never the token or secret.

## Intermittent error-like backup response

A successful login does not guarantee that the subsequent unsupported backup endpoint immediately returns a backup. An error-like response can be transient or indicate changed endpoint behavior. When `BACKUP_DOWNLOAD_RETRIES` is greater than zero, the workflow waits `BACKUP_RETRY_DELAY`, performs a fresh login and retries only a bounded number of times.

The response is never published as a backup, retained, attached, or uploaded. Because Graph mail happens only after successful backup validation, no success email is sent for such a failed run. The status file, Prometheus metrics, JSON event, systemd exit code, and optional ntfy/webhook failure notification record the failure instead.

If all attempts fail, do not increase retries indefinitely. Check UniFi health and recent upgrades, run `sudo unifi-backup-check --live`, wait a few minutes, and perform one manual service run. Repeated failures may indicate a changed controlplane contract.

## Remote storage and notifications

- Azure/S3 failure with a retained local backup: inspect the `remote_upload_failed` event and [STORAGE.md](STORAGE.md); never paste a SAS or key into an issue.
- HTTP 409/412 from object storage: an object with the same managed name already exists; the uploader refuses overwrite.
- ntfy HTTP 401/403: verify the access token and topic ACL without logging or placing the token on the command line.
- No ntfy notification after an early configuration error: notification configuration may not have been safely loaded yet; systemd/journald remains authoritative.
- Webhook HTTP 4xx/5xx: validate the destination schema/authentication and inspect the receiving system; the URL, Bearer token, and HMAC secret are intentionally not logged.
- A stale alert repeats only after the monitoring state changes. Inspect `status.json`, `monitor-state.json`, `unifi_backup.prom`, and `journalctl -u unifi-backup-monitor.service`.

## Encryption and catalog

- `age: command not found`: rerun the reviewed current installer/updater with automatic dependency provisioning enabled before enabling encryption.
- `AGE_RECIPIENTS_FILE contains no supported public recipient`: replace the placeholder with a native age recipient or supported SSH public recipient.
- Private identity rejected: this is intentional; keep the identity on a separate recovery system.
- Encryption failure: no encrypted artifact is published and the plaintext temporary file is removed by cleanup; inspect sanitized age output and recipient compatibility.
- Catalog missing an entry: verify that both the managed artifact and its exact `.json` sidecar exist, are regular non-symlink files, and contain valid metadata.
