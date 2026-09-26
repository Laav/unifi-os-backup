# Notifications

ntfy and generic HTTPS webhooks are optional status-notification channels. Neither carries the `.unifi` attachment. Microsoft Graph mail remains a separate optional channel.

Install a protected configuration example:

```bash
sudo install -o root -g root -m 0600 \
  /opt/unifi-os-backup/config/ntfy.env.example \
  /etc/unifi-backup/ntfy.env
sudoedit /etc/unifi-backup/ntfy.env
```

Enable it in the main configuration:

```bash
ENABLE_NTFY="true"
NTFY_CONFIG_FILE="/etc/unifi-backup/ntfy.env"
NOTIFY_ON_FAILURE="true"
NOTIFY_ON_RECOVERY="true"
NOTIFY_ON_SUCCESS="false"
```

Configure either ntfy.sh or an HTTPS self-hosted server:

```bash
NTFY_BASE_URL="https://ntfy.sh"
NTFY_TOPIC="unguessable-protected-topic"
NTFY_ACCESS_TOKEN="REPLACE_ME"
NTFY_ALLOW_ANONYMOUS="false"
```

Bearer authentication is placed in a mode-0600 temporary header file. The topic URL is placed in a mode-0600 curl configuration file, so neither appears in the process list. Anonymous publishing requires the explicit `NTFY_ALLOW_ANONYMOUS=true` opt-in and is not recommended.

Failure notifications are sent after the local status file records the failure. If the previous run failed and a later run succeeds, one recovery notification is sent. Success notifications are off by default to reduce noise. Notification failure is logged but does not replace or hide the backup result.

The hourly monitor can also emit transition-only `stale_warning`, `stale_critical`, and `stale_recovery` notifications. See [MONITORING.md](MONITORING.md). For structured JSON and monitoring/RMM integration, see [WEBHOOKS.md](WEBHOOKS.md).

No ntfy tags are used, because recognized tags may be rendered as icons or emoji. Messages contain plain text only.

ntfy may cache message content and process subscriber data. Review the [ntfy publishing/authentication documentation](https://docs.ntfy.sh/publish/) and [privacy policy](https://docs.ntfy.sh/privacy/) before using the public service. Self-host ntfy when the operational metadata must remain under your control.
