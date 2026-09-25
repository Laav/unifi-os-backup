# Backup metadata

Every completed backup has a root-owned mode-0600 JSON sidecar:

```text
unifi_os_backup_2026-09-25_03-00-00.unifi
unifi_os_backup_2026-09-25_03-00-00.unifi.json
```

The schema records:

- schema version and unique backup/run ID;
- UTC creation time;
- host and configured UniFi HTTPS origin;
- managed filename, byte size, and SHA256;
- backup type and tool version;
- selected remote backend plus backup/metadata upload status;
- whether Graph mail was enabled and its status.

No username, password, cookie, CSRF value, SAS, S3 key, Graph credential/token, mailbox, ntfy topic/token, or authorization header is written.

When Graph email is enabled, the message body includes the backup ID and remote-backup status, and the JSON sidecar is attached alongside the `.unifi` file. The sidecar attached to a successfully accepted message reports email success. When remote storage is enabled, the final sidecar is uploaded after the email step.

Metadata improves inventory and integrity checks but does not prove authenticity by itself. Protect it with the backup, and store hashes or signed manifests in a separately controlled system when tamper evidence is required.
