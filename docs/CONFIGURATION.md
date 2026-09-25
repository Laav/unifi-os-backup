# Configuration

Production configuration is trusted root-owned Bash assignment syntax in `/etc/unifi-backup/unifi-backup.env`. Do not put it in the repository. Use quoted literal assignments only; because the file is sourced by a root process, anyone able to modify it already has root-equivalent code execution.

Required permissions:

```bash
sudo chown root:root /etc/unifi-backup
sudo chmod 0700 /etc/unifi-backup
sudo chown root:root /etc/unifi-backup/*.env
sudo chmod 0600 /etc/unifi-backup/*.env
```

## Settings

| Variable | Default/example | Meaning |
|---|---|---|
| `UNIFI_URL` | `https://unifi.example.invalid:11443` | HTTPS origin only; no path, query, fragment, or embedded credentials |
| `UNIFI_USERNAME` | `uni-bck` | Dedicated local UniFi backup admin |
| `UNIFI_PASSWORD` | none | Account password; required |
| `BACKUP_DIR` | `/var/backups/unifi` | Absolute non-root destination |
| `RETENTION_DAYS` | `35` | Maximum age in days; zero disables age deletion |
| `RETENTION_COUNT` | `0` | Maximum number retained; zero disables the count limit |
| `RETENTION_MIN_COUNT` | `1` | Newest backups always preserved despite age |
| `MIN_BACKUP_SIZE` | `10000` | Minimum accepted response bytes |
| `CURL_CONNECT_TIMEOUT` | `15` | Connection timeout in seconds |
| `CURL_MAX_TIME` | `1800` | Total request timeout in seconds |
| `BACKUP_DOWNLOAD_RETRIES` | `1` | Additional attempts after a transient/error-like download; maximum 3 |
| `BACKUP_RETRY_DELAY` | `15` | Delay between attempts; each retry authenticates again |
| `UNIFI_CA_CERT` | empty | Absolute PEM CA-chain file for a private CA |
| `LOG_FORMAT` | `text` | `text` or compact newline-delimited `json` |
| `STATUS_FILE` | `/var/lib/unifi-backup/status.json` | Atomically maintained non-secret monitoring state |
| `ENABLE_EMAIL` | `false` | Exactly `true` or `false` |
| `GRAPH_CONFIG_FILE` | `/etc/unifi-backup/graph.env` | Graph secret file |
| `REMOTE_STORAGE_TYPE` | `none` | `none`, `azure_blob`, or `s3` |
| `STORAGE_CONFIG_FILE` | `/etc/unifi-backup/storage.env` | Azure/S3 secret file |
| `REMOTE_UPLOAD_REQUIRED` | `true` | Fail the run when enabled remote storage fails |
| `ENABLE_NTFY` | `false` | Enable ntfy status notifications |
| `NTFY_CONFIG_FILE` | `/etc/unifi-backup/ntfy.env` | ntfy secret file |
| `NOTIFY_ON_SUCCESS` | `false` | Send routine success notifications |
| `NOTIFY_ON_FAILURE` | `true` | Notify when a tracked backup run fails |
| `NOTIFY_ON_RECOVERY` | `true` | Notify once after a failure is followed by success |
| `LOCK_FILE` | `/run/unifi-backup/unifi-backup.lock` | Lock in the private runtime directory |

See [RETENTION.md](RETENTION.md), [STORAGE.md](STORAGE.md), [MONITORING.md](MONITORING.md), [METADATA.md](METADATA.md), and [NOTIFICATIONS.md](NOTIFICATIONS.md) for detailed semantics.

For symlink safety, `LOCK_FILE` must be directly below `/run/unifi-backup` or directly inside `BACKUP_DIR`, and its basename must end in `.lock`. The runtime directory is forced to mode 0700 before the file is opened. The systemd service creates `/run/unifi-backup` with `RuntimeDirectory=` and preserves it across oneshot exits so service and manual runs always contend on the same lock; `/run` is cleared on reboot. Manual runs create it when needed.

The script requires HTTPS and has no insecure mode. For a private CA, store its public CA chain outside Git and set:

```bash
UNIFI_CA_CERT="/etc/unifi-backup/ca/unifi-ca.pem"
```

Do not use `curl -k`, `--insecure`, or a certificate without verifying its issuer and hostname.

## Custom backup directory

The systemd sandbox permits writes only to `/var/backups/unifi` by default. If `BACKUP_DIR` changes, add a matching service override:

```bash
sudo systemctl edit unifi-backup.service
```

```ini
[Service]
ReadWritePaths=
ReadWritePaths=/srv/secure-backups/unifi /run/unifi-backup /var/lib/unifi-backup
```

Then create the directory as root with mode 0700 and run `sudo systemctl daemon-reload`. Do not make a home directory the destination; `ProtectHome=true` intentionally blocks it.

## Schedule

The shipped timer runs Sunday at 03:00 local time. It has no randomized delay because one host does not create a fleet thundering herd. A large deployment can add:

```ini
[Timer]
RandomizedDelaySec=30m
```

Use `systemd-analyze calendar 'Sun *-*-* 03:00:00'` and `systemctl list-timers unifi-backup.timer` to inspect the schedule.
