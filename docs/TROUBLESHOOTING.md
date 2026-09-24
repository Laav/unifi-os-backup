# Troubleshooting

## Endpoint compatibility

The repository uses:

- `POST /api/auth/login`
- `GET /api/backup/download`
- best-effort `POST /api/auth/logout`

These are local UniFi OS controlplane endpoints observed in current deployments; Ubiquiti's public documentation explains UI-based System Config Backup download but does not promise this API contract. They are not the documented UniFi Network Integration API. No speculative fallback endpoint is attempted.

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

For a custom `BACKUP_DIR`, match `ReadWritePaths` as documented in [CONFIGURATION.md](CONFIGURATION.md#custom-backup-directory). Inspect denials with:

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
