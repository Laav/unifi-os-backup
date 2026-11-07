# Routine operations

[Documentation index](README.md) · [Monitoring](MONITORING.md) · [Troubleshooting](TROUBLESHOOTING.md)

## Configuration and explicit tests

```bash
sudo unifi-backup-configure
sudo unifi-backup-configure --validate --json
sudo unifi-backup-configure --inspect --json
```

Validation/inspection do not write configuration or perform live network tests. Review/Finish applies a wizard draft only after confirmation. Keep a separately protected configuration backup, including external references and drop-ins, before planned changes.

The existing engine checker is also available. Its live mode verifies authentication without requesting a backup:

```bash
sudo unifi-backup-check --live
```

## Create and inspect a backup

```bash
sudo systemctl start unifi-backup.service
sudo journalctl -u unifi-backup.service --since "10 minutes ago" --no-pager
sudo systemctl show unifi-backup.service -p ActiveState -p SubState -p Result -p ExecMainStatus
sudo unifi-backup-verify --latest --json
```

`systemctl start` normally waits for the oneshot job and does not stream progress. Read journald in another session if needed. A completed successful oneshot normally shows `inactive`, `Result=success` and `ExecMainStatus=0`; that inactive state is expected.

Read the whole run: a local `Backup successful` event can be followed by a required replication or Graph failure. Local artifact validity and overall service outcome are separate. Defaults store artifacts/sidecars under `/var/backups/unifi`; [metadata](METADATA.md) and the [catalog](CATALOG.md) describe identity, checksums and integration results.

With Graph enabled, `Microsoft Graph accepted the message (HTTP 202)` confirms API acceptance. Check the receiving mailbox or message trace for final delivery. ntfy/webhook notifications carry status information rather than the backup attachment.

## Schedule and freshness

The default backup timer runs Sunday at 03:00 in the host timezone. The freshness monitor evaluates status hourly. Inspect active schedules and overrides:

```bash
systemctl list-timers 'unifi-backup*'
systemctl cat unifi-backup.timer unifi-backup.service
```

Configure daily, weekly or custom calendar expressions through the wizard's schedule section. It validates expressions and writes an owned drop-in; administrator overrides are retained. Review the effective calendar, `ExecStart` and writable paths after applying changes. Daemon-reload alone does not restart an active timer.

When ready, activate/restart the intended timers explicitly:

```bash
sudo systemctl enable --now unifi-backup.timer unifi-backup-monitor.timer
```

For an already active timer whose schedule changed, explicitly restart that timer after reviewing the effective configuration. `Persistent=true` can start an overdue job on activation. Change freshness thresholds to match the intended interval; default weekly thresholds warn after 192 hours and become critical after 216 hours.

## Read status

```bash
unifi-backup-status
unifi-backup-status --format json
sudo journalctl -u unifi-backup-monitor.service --since today --no-pager
sudo unifi-backup-catalog --print
```

Text/JSON monitoring exits use 0/1/2/3 for OK/WARNING/CRITICAL/UNKNOWN. Use explicit `--status-file` and freshness arguments for custom paths/intervals; the standalone status command has its own defaults. The monitor service uses the installation configuration. See [MONITORING.md](MONITORING.md) for Prometheus and SNMP/Auvik adapters.

## Optional maintenance workers

Verification, remote-verification and retry are installed with separate timers. Enable the corresponding configuration flag and review prerequisites before deliberately activating a worker:

| Worker | Configuration opt-in | Timer |
|---|---|---|
| Local verification | `VERIFY_ENABLED=true` | `unifi-backup-verify.timer` |
| Remote verification | `REMOTE_VERIFY_ENABLED=true` | `unifi-backup-remote-verify.timer` |
| Replication retries | `RETRY_ENABLED=true` | `unifi-backup-retry.timer` |

Remote verification needs appropriate read/list access; full verification downloads actual bytes. Recovery identities are required only for explicitly selected decryption checks. Inspect pending/dead retries and free disk space: pending tasks can pin local artifacts beyond ordinary retention.

Useful explicit commands:

```bash
sudo unifi-backup-retention --dry-run --json
sudo unifi-backup-remote-verify --latest --full --target s3-primary --json
sudo unifi-backup-retry --json
sudo unifi-backup-analyze --latest --explain
sudo unifi-backup-restore --list --json
```

Replace `s3-primary` with an active target ID. Remote checks contact that target; retry performs due uploads and can request already-configured protection policies. A retention dry-run does not delete files. Analysis does not change valid bytes into corruption failures. Configuration diffing requires explicit normalized exports; it cannot extract native opaque `.unifi` data.

See [verification](VERIFICATION.md), [retries](RETRIES.md), [retention](RETENTION.md) and [recovery](DISASTER-RECOVERY.md) for detailed behavior. Restore preparation stages verified files; an actual UniFi restore remains a separate manual operation and acceptance test.
