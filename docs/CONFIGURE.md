# Terminal configuration manager

[Documentation index](README.md) · [Installation](INSTALL.md) · [Configuration reference](CONFIGURATION-REFERENCE.md)

`sudo unifi-backup-configure` provides one full-screen management interface for the backup engine and its integrations. It keeps separate secret files and per-target configuration where their independent lifecycles require them. The wizard is optional; manually maintained files and scheduled jobs remain supported.

## Requirements and quick start

Ubuntu Server 22.04/24.04/26.04, Linux root privileges and Python's standard library. Only the interactive interface additionally needs `dialog`, a real TTY, `TERM` other than `dumb`, and at least 60 columns by 18 rows (100x28 or larger is recommended). It uses the available terminal size, supports resizing between dialogs and works over SSH; no desktop, pip packages or cloud SDKs are needed.

```bash
sudo ./install.sh --configure
# Or after an ordinary unattended install/update:
sudo unifi-backup-configure
sudo unifi-backup-configure --guided
```

Installation/update automatically provisions missing `dialog` and other application dependencies using APT. `--no-install-deps` opts out for pre-provisioned/offline systems. No package installation happens during the wizard, validation or scheduled backups.

For SSH automation do not invoke the wizard. For an interactive remote session use `ssh -t HOST`, then run it there. Terminal, scrollback and session recording are security boundaries: never record secret entry. Passwords/tokens use an empty, non-echoing password box; existing values are never prefilled. Blank keeps an existing sensitive value; clearing requires a separate explicit action. Login passwords containing special characters/multiline literals are preserved and serialized safely; the single-line UI is not a multiline secret editor.

Keyboard navigation: arrows select, Tab/Shift-Tab move between controls, Space toggles checkboxes, Enter confirms, and Escape cancels a dialog. Back returns to the previous guided section; Next advances. Canceling a section returns to the main menu without writing. Exit asks before discarding an unapplied draft. Nothing is applied until **Review and Finish** and its final confirmation.

## Fresh installation walkthrough

1. Create the dedicated local UniFi service account as described in [UNIFI-ACCOUNT.md](UNIFI-ACCOUNT.md).
2. Run the guided wizard. Enter the HTTPS origin/port, username, masked password and optional trusted CA chain. There is no insecure TLS option.
3. Choose the private local directory, request timeouts/retries, daily/weekly/custom systemd schedule and legacy or GFS retention. Schedule changes are validated by `systemd-analyze calendar`.
4. Keep encryption disabled or configure existing **public** age/SSH recipients. Confirm age is available; installer/updater provision it unless dependency installation was explicitly disabled. The wizard never generates, writes, displays or exports private recovery identities. Independently secure and restore-test the recovery keys.
5. Keep local-only storage, or add independent Azure Blob, S3 or private mounted-filesystem targets. New targets are initially disabled. Enter protected provider settings, optional/required status, verification level and any explicit immutability request; then explicitly enable the target. Retry limits are installation-wide; the remote success quorum excludes local storage.
6. Enable only required notifications and configure their separate files. Disabled integrations are not required. Graph needs Mail.Send application consent and mailbox scoping; the wizard does not send or expose attachments. See [MICROSOFT-GRAPH.md](MICROSOFT-GRAPH.md).
7. Review categorized old/new values (sensitive values hidden), changed/new files, narrow systemd drop-ins, directory creation, dependencies, errors and warnings. Finish explicitly writes the transaction; a failed validation writes no configuration.
8. Optionally run the offered existing offline checker. A UniFi login test, provider listing/capability inspection, ntfy/webhook test message or timer activation requires its own explicit action. No real backup runs as a side effect of Finish.
9. After checking the resulting units, deliberately start a first backup and verify it before enabling scheduling.

Filesystem targets must already exist with root ownership, mode 0700, the expected mount and a `.unifi-backup-target` marker matching the target ID. The wizard never creates a fake mount destination or removes remote objects. Read-only cloud tests need read/list permissions beyond legacy upload-only credentials; lack of those permissions does not mean write-only backup credentials were automatically changed.

## Existing installations

Run the existing updater first, allow any jobs started by the older binaries to finish, and review [UPGRADING.md](UPGRADING.md). Updating does not source, rewrite or migrate configuration through the manager. Opening the wizard reads existing literal assignments and uses current values rather than resetting to new defaults.

The manager understands UTF-8 comments, blank lines, `export NAME=literal`, single/double quoted literals, concatenated literal segments, escaped unquoted values and a restricted ANSI-C literal syntax used by Bash `printf %q`. ANSI hex/octal escapes retain byte semantics and must decode safely as UTF-8. Outside quoted literals use LF line endings; unquoted tilde expansion and CRLF shell lines are refused rather than reinterpreted. Unknown literal assignments and custom comments remain unchanged. It refuses command substitution, variable expansion, arrays, source/include statements, functions, multiple commands on one line, or other executable shell syntax. It never falls back to evaluating those files. Convert unsupported expressions to literal assignments manually after a private backup; do not paste secrets into a shell command or a support ticket.

Malformed/insecure **inactive** optional files are preserved with a warning and cannot be edited/enabled until fixed. An unsafe main file blocks safe inspection entirely. Missing optional files are created only when edited and applied. Existing custom file references remain in use; choose a new reference deliberately rather than expecting a merge/copy migration.

Configuration, public recipients, private-identity references and operational state have separate file roles. References cannot alias another role, a lock, a status/catalog file or a transaction journal. These conflicts block manager planning even for disabled integrations, to prevent a later edit from overwriting another resource. Correct references explicitly; the existing manually configured engine is not rewritten automatically.

### Storage mode transitions

Nonempty `BACKUP_TARGETS` continues to override legacy `REMOTE_STORAGE_TYPE`/`STORAGE_CONFIG_FILE`. Legacy remains supported and is not redundant for existing write-only single-target deployments. The UI offers legacy editing separately. It never converts its credentials into an active target.

To migrate, explicitly set legacy storage to `none`, add/configure a disabled independent target, validate it, enable it and review required-target/quorum policy before Finish. Disabling/removing a target only removes its active ID; its protected credential file, remote backups and other local data remain. Pending retry tasks need review before removal; the worker's existing removed-target/dead-letter behavior remains unchanged. The last active target cannot silently reactivate dormant legacy storage.

## All sections and advanced configuration

The main menu includes guided setup, existing configuration, destinations, notifications, schedule/retention, validation, status/diagnostics and Exit. Additional entries provide public recipients, advanced settings and Review/Finish.

Advanced editing covers freshness thresholds, text/JSON logging, status/catalog paths, local/remote verification, existing verification identity references, retry queue limits/backoff, anomaly detection, normalized-export diffing and recovery preparation limits. Defaults remain unchanged unless edited. Remote verification/retry/verification flags and their timers are independent; both must be enabled for scheduled work.

The canonical field definitions are in `lib/ub/config_schema.py`; [CONFIGURATION-REFERENCE.md](CONFIGURATION-REFERENCE.md) is generated from them. It maps every managed setting to file, default, consumers, validation, sensitivity, dependency and active/legacy status. Do not maintain a second manual settings table. Lower-level Bash/provider validation remains defense in depth; the manager uses the shared advanced-engine validator plus stricter offline file/dependency checks. A manager-only limitation does not force working manual installations to migrate.

## Automation: no TTY or dialog

```bash
unifi-backup-configure --help
unifi-backup-configure --version
sudo unifi-backup-configure --validate --json
sudo unifi-backup-configure --inspect --json
sudo unifi-backup-configure --dry-run
sudo unifi-backup-configure --config /srv/private/unifi/main.env --validate
unifi-backup-configure --reference
```

Validation is offline: it checks syntax, security, HTTPS/ports, bounded numbers/booleans, paths/CA files, credentials for enabled integrations, target identifiers/policies/quorum, retention, retry/encryption prerequisites and systemd access. It does not test remote authentication or automatically change permissions/install packages. Age validation encrypts a synthetic string locally to check public recipients; no key is generated. Inspection writes no persistent configuration, lock or state files; temporary local validation resources are cleaned up.

Exit codes: 0 valid (warnings allowed), 64 usage, 65 unsupported/invalid syntax, 69 missing dependency/UI, 73 apply failed with completed rollback, 74 local I/O/data failure, 75 lock/conflict/incomplete rollback, 77 manager security/ownership violation, 78 invalid configuration, and 128+signal on interruption. Live helpers retain their existing exit categories; monitoring retains Nagios 0/1/2/3. Reports distinguish warnings and error categories without including raw secret values or unknown settings.

## Scheduling and systemd access

The manager owns only `90-unifi-backup-configure.conf` below the relevant `.timer.d`/`.service.d` directories. It never rewrites packaged units or administrator drop-ins. A foreign file occupying that exact filename blocks apply. Schedule replacement resets OnCalendar only in the owned timer drop-in. Additional write access is limited to validated private backup/filesystem-target paths; service config-path overrides pass `--config` explicitly. ProtectSystem, ProtectHome, capabilities and other hardening remain unchanged.

ReadWritePaths is additive: existing administrative rules remain administrator-controlled. Returning to the default path removes the manager's previous extra grants by rewriting its own drop-in, not by resetting all administrator grants. Directories under protected home/system/temporary paths and broad write grants are refused. Later administrator drop-ins may still take precedence. Review `systemctl cat` and the effective `systemctl show` results before production use. See [systemd.exec](https://www.freedesktop.org/software/systemd/man/latest/systemd.exec.html).

Finish performs daemon-reload when necessary, but does not enable/start/restart timers. Explicit timer management is available under diagnostics after configuration is applied and valid. A schedule change on an active timer needs an explicit restart (or a separately approved restart-if-active action). Starting a Persistent timer may immediately run an overdue backup/remote operation; the UI warns before confirmation.

## Transactions, backup and recovery of configuration

Configuration readers hold a shared `.configure.lock` before sourcing. The installer/updater creates this root-owned 0600 inode so hardened services can open it **read-only**. Apply takes the exclusive configuration lock first, then the old/new operation locks. Both direct engine runs and updated scheduled helpers participate. Optimistic fingerprints also reject manual/dependency edits made during a session; reload the wizard instead of overwriting them.

This coordinates one installation's main file and its referenced files. Independent installations with different main configuration directories must not concurrently share secret files without external coordination. Manual editors and older binaries do not participate automatically; do not run them concurrently with a transaction.

After validation, private preimages/postimages and a manifest are staged under `/etc/unifi-backup/.configure-transactions/ID/` (or beside the custom main file). Files are fsynced and individually atomically replaced. A durable `.configure-pending` marker blocks updated readers until the multi-file transaction completes. **There is no filesystem-wide atomic commit across files or systemd.** Normal exceptions/signals trigger rollback; SIGKILL/power loss requires explicit recovery. A rollback error deliberately leaves the marker and journal for repair. Do not delete the marker to bypass recovery.

```bash
# Recover an interrupted apply (requires no parseable current main file):
sudo unifi-backup-configure --recover --yes
# Or undo a completed apply, using the privately recorded ID:
sudo unifi-backup-configure --rollback TRANSACTION_ID --yes
# For custom main paths use the same --config argument for recovery.
```

Rollback preflights hashes, preimages and affected current files, and refuses to overwrite later edits. Directory creation may leave empty private directories after failure; timer activation is a separate operational action and is not undone by file rollback. Journals retain previous secrets intentionally. Protect/retain them like credentials, rotate affected secrets after exposure, and prune only completed, no-longer-needed journals after a verified independent backup. There is no automatic journal deletion or config export containing secrets. Ordinary uninstall preserves them; explicit purge removes the default configuration tree irrecoverably.

For an independent configuration backup, stop configuration writes and use your approved root-only encrypted host/config backup mechanism for the configuration tree **and referenced external files/owned drop-ins**. The central backup catalog does not include configuration secrets. Never copy journals, env files, private identities or configuration archives into Git or public artifacts. Application-version rollback remains separate from configuration transaction rollback.

## Troubleshooting and rollout checklist

- No TTY/TERM: open an interactive terminal (`ssh -t`) or use offline commands.
- Missing dialog: rerun the current `sudo ./update.sh` or `sudo ./install.sh`; missing dependencies are provisioned automatically. `--no-install-deps` deliberately opts out. Normal backups need no dialog.
- Small terminal: resize to at least 60x18 and reopen. Unapplied edits are not persisted.
- Unsupported Bash syntax: preserve a private backup, replace expressions with literals manually; the manager will not execute them.
- Unsafe permissions/symlink: correct owner/modes and choose nonsymlinked paths; the manager does not silently chmod existing secret files or follow links.
- Lock conflict: wait for the current writer/backup, then reload. Do not delete a held lock inode.
- Pending transaction: use explicit recovery; investigate failed storage/reload before restarting backups.
- Custom overrides: inspect effective calendars, ExecStart/config references, writable/readable paths and active timer state.

Before production rollout run the complete tests from [TESTING.md](TESTING.md) on Ubuntu, including real dialog PTY and lifecycle sandbox tests. On a disposable host test fresh and existing literal configurations, masked edits, Back/Cancel, no-op repeat apply, missing dependencies, custom directories/CA and calendars, legacy and multi-target policies, signal recovery and concurrent jobs. Then test actual provider permissions and one explicitly selected UniFi login/backup/verification plus an isolated recovery drill. No live cloud, Graph delivery or controller restore is implied by unit/mock test success.
