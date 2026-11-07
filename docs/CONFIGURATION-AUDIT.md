# Configuration architecture audit (1.4.1)

## Scope and baseline

Inspected the executable entry points, shared Bash loader/common library, every `lib/ub` module, all configuration templates, installer/updater/uninstaller, all packaged services/timers, tests, CI and operator/release documentation. Starting source: `196bab3` (1.3.0), clean worktree. The existing Python suite has 25 cases. The supported CI matrix is Ubuntu 22.04/24.04/26.04; the development host is Windows, not a production Linux server.

## Findings

- Bash entry points source protected, trusted shell files. This remains an existing root-equivalent trust boundary, not a safe parsing API. A manager must not source them to inspect them.
- Main defaults/validation live in `bin/unifi-backup`; advanced validation is repeated in `lib/ub/cli.py`; storage/notification consumers also validate just before use. Existing offline checks do not fully validate enabled integration contents.
- `BACKUP_TARGETS` takes precedence over the legacy single remote destination. Copying `storage.env` into a target and enabling both without an explicit choice could change replication/quorum behavior. Disabling the last multi-target could unexpectedly reactivate dormant legacy storage.
- Installer/updater preserve existing files. They deploy modules by glob but maintain explicit executable/module lists. Noninteractive installation must remain independent of the UI dependency.
- Packaged services hard-code their configuration path and writable directories. Changing a path in the main file alone is insufficient. Existing drop-ins must be retained; schedules belong in a separate owned drop-in.
- The backup reads configuration before acquiring its operation lock. A multi-file configuration transaction therefore needs a configuration read/write lock before sourcing, in addition to the existing backup lock.
- Secret files, independent target credentials and public age recipients have different lifecycles. Physically merging them is not justified.

## Selected architecture

`dialog` UI -> declarative standard-library Python schema/model -> safe literal parser and transactional persistence -> unchanged compatible env/recipient files -> existing engine.

The schema supplies all supported keys, runtime defaults, types, limits, descriptions, groups, sensitivity and dependency metadata. The advanced engine validator reuses it; low-level Bash/provider checks remain defense in depth and retain their compatibility contract. A generated inventory records consumers and legacy status instead of maintaining another hand-written settings table.

`dialog` is preferred over `whiptail`: its parameter-file/file-descriptor support keeps existing values out of process arguments, and its extra navigation buttons and scrollable dialogs meet the UI requirements without a framework. Only interactive configuration requires it. See the [upstream dialog manual](https://invisible-island.net/dialog/manpage/dialog.html). The manager uses no shell, eval, provider SDK, database or web service.

Existing literals/comments/unknown assignments are preserved. Unsupported shell expressions cause an explicit safe refusal, never execution or an automatic reset. Edits remain in memory until review/confirmation. Multi-file apply uses private staging, durable preimages, atomic per-file replacement, a persistent pending marker, reader/operation locks and recoverable rollback. It cannot promise filesystem-level atomicity across multiple files; pending transactions block updated engine readers until recovery.

No automatic storage migration, target activation, remote write/delete, private-key generation, timer activation or live test is introduced. Narrow additive systemd write-path/config-path drop-ins retain hardening; custom conflicting overrides require administrator review.

## Inventory

The complete generated setting inventory is [CONFIGURATION-REFERENCE.md](CONFIGURATION-REFERENCE.md). Regenerate/check it with `unifi-backup-configure --reference` (no configuration or TTY required). Existing backup artifacts, metadata/catalog formats and remote protocols are outside this refactor.
