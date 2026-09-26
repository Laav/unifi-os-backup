# Monitoring

Monitoring should answer whether a validated backup exists and whether the most recent run succeeded—not merely whether the timer fired.

Each real backup run atomically updates:

```text
/var/lib/unifi-backup/status.json
/var/lib/unifi-backup/unifi_backup.prom
```

These files contain operational state, filenames, sizes, timestamps, hashes, and integration statuses, but no credentials or tokens. They are mode 0644 in a mode-0755 state directory so local monitoring agents can read them. Backup metadata remains mode 0600 under the backup directory.

## Automatic stale-backup detection

`unifi-backup-monitor.timer` runs hourly, evaluates the configured freshness SLA, refreshes the Prometheus textfile, and records `/var/lib/unifi-backup/monitor-state.json`. Start it after validating the installation:

```bash
sudo systemctl enable --now unifi-backup-monitor.timer
systemctl list-timers unifi-backup-monitor.timer
```

Configure the SLA in `unifi-backup.env`:

```bash
STALE_WARNING_HOURS="192"
STALE_CRITICAL_HOURS="216"
NOTIFY_ON_STALE="true"
```

With ntfy or webhooks enabled, notifications are emitted only when the state changes to WARNING/CRITICAL or returns to OK. Repeated hourly checks in the same state do not create duplicate alerts. The timer service treats exit 1/2 as expected monitoring outcomes; exit 3 (UNKNOWN) remains a systemd failure.

## Status command

```bash
unifi-backup-status
unifi-backup-status --format json
unifi-backup-status --format prometheus
unifi-backup-status --format snmp
```

Defaults assume the shipped weekly timer:

- WARNING when the last success exceeds 192 hours (8 days);
- CRITICAL after 216 hours (9 days);
- CRITICAL immediately when the most recent run failed;
- UNKNOWN when the status file is missing or invalid.

Override age thresholds for a different schedule:

```bash
unifi-backup-status --warning-age-hours 26 --critical-age-hours 48
```

Text and JSON formats use Nagios-compatible exits. SNMP prints only `0`, `1`, `2`, or `3` and exits zero. See [EXIT-CODES.md](EXIT-CODES.md).

## Auvik through SNMP

Auvik supports numeric custom SNMP pollers for an OID not collected by default. On the Linux backup host, configure Net-SNMP with SNMPv3 and restrict access to the Auvik collector. Add this `extend` directive to the active `snmpd.conf` (the include layout varies by Ubuntu package configuration):

```text
extend unifiBackup /usr/local/sbin/unifi-backup-status --format snmp
```

Restart `snmpd`, confirm the command locally, and derive the numeric instance OID rather than copying a guessed OID:

```bash
/usr/local/sbin/unifi-backup-status --format snmp
snmptranslate -On 'NET-SNMP-EXTEND-MIB::nsExtendOutput1Line."unifiBackup"'
```

In Auvik, open **Discovery → Discovery Settings → SNMP Poller Settings**, add the derived numeric OID as a Numeric poller, target only the backup host, choose an appropriate polling interval, and alert when the value is greater than zero:

- `0`: OK
- `1`: WARNING (backup too old)
- `2`: CRITICAL (last run failed/no successful backup/critically old)
- `3`: UNKNOWN (state unavailable)

Test the exact OID from the Auvik collector network before relying on the alert. See Auvik's current [custom SNMP poller documentation](https://support.auvik.com/hc/en-us/articles/206617226-How-do-I-manage-custom-SNMP-Pollers).

## Prometheus/node_exporter

Point node_exporter's textfile collector at `/var/lib/unifi-backup`. It reads `unifi_backup.prom`, which is atomically replaced. The file exposes run success, exit code, timestamps, current age, `unifi_backup_stale`, duration, size, remote upload, and email state. The hourly monitor refreshes age-dependent values between backup runs.

Calculate current age in PromQL so it continues increasing between runs:

```promql
time() - unifi_backup_last_success_timestamp_seconds
```

Example alerts:

```promql
unifi_backup_last_run_success == 0
```

```promql
time() - unifi_backup_last_success_timestamp_seconds > 9 * 24 * 60 * 60
```

The node_exporter textfile collector reads `*.prom` files and does not accept client-side sample timestamps. See the official [node_exporter textfile collector documentation](https://github.com/prometheus/node_exporter#textfile-collector).

## JSON journald events

Set `LOG_FORMAT="json"` to write one compact JSON object per event to stdout/stderr; systemd captures these in journald. Each object includes UTC timestamp, program, level, event, message, and non-secret event fields. Query them normally:

```bash
sudo journalctl -u unifi-backup.service -o cat --since today
```

Forward journald through the organization's existing agent to Sentinel, Splunk, Elastic, Loki, Graylog, or another log platform. The project does not install or open a network listener.
