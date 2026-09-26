# Generic HTTPS webhooks

The optional webhook channel sends a compact JSON event to an administrator-controlled HTTPS endpoint. It is intended for monitoring gateways, RMM/PSA integrations, automation platforms, or a small adapter that translates the generic schema to a vendor-specific Teams, Slack, PRTG, Zabbix, or Checkmk format.

It does not pretend that every vendor accepts the same payload. Use a reviewed adapter, Azure Logic App, Power Automate flow, or equivalent when the destination requires a proprietary schema.

## Configure

```bash
sudoedit /etc/unifi-backup/webhook.env
sudo chmod 0600 /etc/unifi-backup/webhook.env
sudoedit /etc/unifi-backup/unifi-backup.env
```

Main configuration:

```bash
ENABLE_WEBHOOK="true"
WEBHOOK_CONFIG_FILE="/etc/unifi-backup/webhook.env"
NOTIFY_ON_FAILURE="true"
NOTIFY_ON_RECOVERY="true"
NOTIFY_ON_SUCCESS="false"
NOTIFY_ON_STALE="true"
```

Secret configuration:

```bash
WEBHOOK_URL="https://monitoring.example.invalid/hooks/unifi-backup"
WEBHOOK_BEARER_TOKEN="REPLACE_ME"
WEBHOOK_HMAC_SECRET="REPLACE_WITH_AN_INDEPENDENT_SECRET"
WEBHOOK_CA_CERT=""
WEBHOOK_CONNECT_TIMEOUT="15"
WEBHOOK_MAX_TIME="60"
```

The URL may contain a provider-generated secret path or query. It is written to a mode-0600 temporary curl configuration rather than argv. Bearer and HMAC secrets are placed in protected temporary files and never logged.

`WEBHOOK_BEARER_TOKEN` and `WEBHOOK_HMAC_SECRET` are independently optional. With HMAC enabled, verify the lowercase hexadecimal signature from:

```text
X-UniFi-Backup-Signature: sha256=<HMAC-SHA256 of exact request bytes>
```

Compare signatures in constant time. Reject replayed `delivery_id` values when events trigger privileged automation.

## Payload

The schema includes:

- schema version, unique delivery ID, event time, event, status, message, and exit code;
- host and configured UniFi controller origin;
- current backup metadata when available;
- encryption and remote-storage state;
- current monitoring status and last successful backup.

Events are `success`, `failure`, `recovery`, `stale_warning`, `stale_critical`, and `stale_recovery`. Notification delivery failures are logged but do not replace the underlying backup or freshness result.

Never place credentials in custom messages. Treat controller names, backup times, sizes, and topology-related metadata as operationally sensitive.
