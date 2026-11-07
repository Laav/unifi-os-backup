# Configuration

[Documentation index](README.md) · [Configuration wizard](CONFIGURE.md) · [Field reference](CONFIGURATION-REFERENCE.md)

Use the terminal manager to configure the existing backup engine through one interface:

```bash
sudo unifi-backup-configure
sudo unifi-backup-configure --validate --json
sudo unifi-backup-configure --inspect --json
```

Read [CONFIGURE.md](CONFIGURE.md) for guided/existing setup, navigation, every section, explicit tests, transactional apply, rollback and systemd handling. Production backup operation still works with manually maintained files and does not require the wizard or dialog.

## Single reference and file layout

[CONFIGURATION-REFERENCE.md](CONFIGURATION-REFERENCE.md) is generated from `lib/ub/config_schema.py` using `unifi-backup-configure --reference`. It maps managed keys to source files, runtime defaults, consumers, types/limits, sensitivity, dependencies and legacy status. Examples use fictitious placeholders, not necessarily runtime defaults. Do not duplicate this setting table in other documents.

Configuration remains physically separated for independent credential lifecycles:

- Main: `/etc/unifi-backup/unifi-backup.env`.
- Enabled Graph, legacy storage, ntfy and webhook integrations: their referenced protected env files.
- Independent targets: `BACKUP_TARGET_CONFIG_DIR/ID.env`; only IDs in `BACKUP_TARGETS` are active.
- Age: a separate public-recipient file; private recovery identities are not managed.
- Scheduling and custom access/config paths: narrow manager-owned systemd drop-ins, not shell variables.

Existing custom references remain supported. Nonempty `BACKUP_TARGETS` overrides legacy `REMOTE_STORAGE_TYPE`/`STORAGE_CONFIG_FILE`; no automatic merge, credential copy or legacy activation occurs. Local storage always remains enabled. Retry backoff/limits are global while each task retains its own target and due time. A target can explicitly override the inherited remote download safety limit.

## Manual configuration and trust

Existing engine configuration is trusted root-owned Bash assignment syntax, sourced by root after permission/read-lock checks. Anyone who can modify it already has root-equivalent authority. Keep it outside Git. Prefer literal assignments: the manager refuses executable expressions, expansions, includes, arrays and unsupported syntax instead of evaluating or overwriting them. It preserves unknown literals and comments where safe; those unknown values are not included in diagnostics.

```bash
sudo chown root:root /etc/unifi-backup
sudo chmod 0700 /etc/unifi-backup
sudo chown root:root /etc/unifi-backup/*.env
sudo chmod 0600 /etc/unifi-backup/*.env
```

Apply the same root:root/0700/0600 contract to custom secret directories/files and targets.d. Do not indiscriminately chmod external CA stores or private recovery key collections. Do not edit files concurrently with a manager transaction; reload when a conflict is reported. The installer/updater pre-creates the private shared configuration lock, so hardened services need only read access to it. Pending interrupted transactions must be recovered before normal operations.

No insecure TLS mode exists. For a private CA, install the verified public PEM chain and configure its absolute path. The manager checks ownership/path safety and PEM loading; the existing curl path uses normal verification and `--cacert`. A valid certificate file alone does not establish that the endpoint hostname or credentials work; use an explicit live login check.

## Paths and systemd

The packaged sandbox writes only to its default backup/runtime/state locations. Merely changing BACKUP_DIR does not make it writable in a service. The manager validates dedicated private paths and prepares narrow additive service overrides for the backup, maintenance workers and monitor as needed, retaining ProtectSystem/ProtectHome/capability restrictions.

For manual changes, review all affected services, including verification, retry and monitor, not just the main backup unit. Use systemd drop-ins, never edit packaged units or allow writes to a broad system root. Avoid home/temporary paths hidden by ProtectHome/PrivateTmp. Keep status.json/catalog.json directly below /var/lib/unifi-backup or BACKUP_DIR as required by the engine. The operation lock must be directly below /run/unifi-backup or BACKUP_DIR with a safe .lock basename.

The default calendar remains Sunday at 03:00 local time with Persistent=true. Validate a replacement using `systemd-analyze calendar EXPRESSION`; daily, weekly and custom calendars are supported by the wizard. Daemon-reload alone does not restart an active timer. Deliberately review and restart/activate the desired timer; Persistent activation may immediately run an overdue job.

For deeper feature semantics see [ENCRYPTION.md](ENCRYPTION.md), [RETENTION.md](RETENTION.md), [STORAGE.md](STORAGE.md), [MULTI-TARGET.md](MULTI-TARGET.md), [MONITORING.md](MONITORING.md), [METADATA.md](METADATA.md), [CATALOG.md](CATALOG.md), [NOTIFICATIONS.md](NOTIFICATIONS.md), [WEBHOOKS.md](WEBHOOKS.md), [RETRIES.md](RETRIES.md) and [IMMUTABILITY.md](IMMUTABILITY.md).
