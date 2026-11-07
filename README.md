# UniFi OS Backup

[![Release](https://img.shields.io/github/v/release/Laav/unifi-os-backup?label=release)](https://github.com/Laav/unifi-os-backup/releases/latest)
[![CI](https://github.com/Laav/unifi-os-backup/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/Laav/unifi-os-backup/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Automate UniFi OS System Config Backups on Linux. Create and validate a local backup, protect it with optional encryption, replicate it to independent destinations, and monitor whether a usable backup is available when needed.

Manage the installation through one full-screen terminal configuration interface, including over SSH. The backup engine uses Bash, curl, Python's standard library and systemd; it requires no desktop, Docker, cloud SDK or Python package installation.

**Start here:** [Installation](docs/INSTALL.md) · [Configuration wizard](docs/CONFIGURE.md) · [Documentation](docs/README.md) · [Latest release](https://github.com/Laav/unifi-os-backup/releases/latest)

> [!IMPORTANT]
> This project uses observed UniFi OS controlplane endpoints, including `POST /api/auth/login` and `GET /api/backup/download`. They are not a guaranteed stable public API and can change after a UniFi upgrade. Test both login and backup creation after upgrading UniFi. See [endpoint compatibility](docs/TROUBLESHOOTING.md#endpoint-compatibility).

## Capabilities

| Area | What it provides |
|---|---|
| Backup creation | Dedicated local UniFi account, validated downloads, atomic publication, SHA256 and JSON metadata |
| Configuration | Guided setup, categorized editing, masked secrets, offline validation and reviewed configuration transactions |
| Local protection | Private backup files, age encryption, age/count/minimum retention and optional GFS policies |
| Replication | Azure Blob, S3-compatible and filesystem destinations, independent required targets and persistent retries |
| Verification and recovery | Local and remote integrity checks, a backup catalog and verified staging for manual restoration |
| Monitoring | Freshness detection, structured logs, exit codes, Prometheus metrics and SNMP/Auvik integration patterns |
| Notifications | Optional Microsoft Graph backup email, ntfy and signed generic HTTPS webhooks |
| Analysis | Deterministic anomaly detection and redacted diffs of explicitly supplied normalized configuration exports |

All installations retain a local backup. Optional integrations remain disabled until configured. Native `.unifi` semantic extraction is unsupported; [configuration diffs](docs/CONFIG-DIFF.md) require a separate supported export.

## Supported environment

- Ubuntu Server 22.04, 24.04 and 26.04 with systemd.
- The complete CI suite runs in x86-64 Ubuntu containers for all three releases. The client scripts are architecture-neutral; native ARM64 execution remains an operator acceptance check.
- Root privileges for installation, configuration and backup operations.
- HTTPS access to the UniFi OS controlplane and any enabled integrations.

The backup client can run on a separate host from UniFi OS Server. Check UniFi OS Server's own platform requirements independently.

## Install and configure

The example below pins a published release and leaves automatic scheduling disabled during setup. Review the [latest release](https://github.com/Laav/unifi-os-backup/releases/latest) before selecting a version.

```bash
wget -qO install.sh https://raw.githubusercontent.com/Laav/unifi-os-backup/v1.4.2/install.sh
less install.sh
chmod 0755 install.sh
sudo ./install.sh --dependencies-only
sudo git clone --branch v1.4.2 --depth 1 https://github.com/Laav/unifi-os-backup.git /opt/unifi-os-backup
cd /opt/unifi-os-backup
sudo ./install.sh --no-enable --configure
```

Installer and updater automatically provision missing dependencies through the host's configured APT repositories, including Git, dialog and age. No separate `apt install` step is required. Existing configuration and backups are preserved. Offline or centrally managed hosts can opt out with `--no-install-deps`.

Use a [dedicated local UniFi account](docs/UNIFI-ACCOUNT.md), named `uni-bck` by default, with the narrowest tested permissions that can create a System Config Backup. Enter credentials through the wizard; configuration remains outside Git under `/etc/unifi-backup`.

The wizard supports keyboard navigation, Back/Next, Cancel and explicit Review/Finish. It requires an interactive terminal; unattended installation and ordinary backups do not. See [the setup walkthrough](docs/CONFIGURE.md) for existing installations, custom paths and all integrations.

## Verify the first backup

After reviewing and applying configuration, explicitly validate, test login and create a backup:

```bash
sudo unifi-backup-configure --validate
sudo unifi-backup-check --live
sudo systemctl start unifi-backup.service
sudo journalctl -u unifi-backup.service --since "10 minutes ago" --no-pager
sudo unifi-backup-verify --latest --json
```

The live login check does not create a backup. Service progress appears in journald; a successful oneshot service normally returns to `inactive`. Verify the backup and perform an isolated restore drill before enabling scheduling.

When ready, activate the backup and freshness timers:

```bash
sudo systemctl enable --now unifi-backup.timer unifi-backup-monitor.timer
systemctl list-timers 'unifi-backup*'
```

The backup timer defaults to Sunday at 03:00 in the host's local timezone. `Persistent=true` can trigger an overdue job when a timer is activated. Configure daily, weekly or custom calendars through the wizard. Additional verification/retry timers require separate opt-in; see [operations](docs/OPERATIONS.md).

## Day-to-day administration

```bash
sudo unifi-backup-configure
sudo unifi-backup-configure --inspect --json
unifi-backup-status --format json
sudo unifi-backup-retention --dry-run --json
sudo unifi-backup-restore --list --json
```

Use the [operations guide](docs/OPERATIONS.md) for schedules, logs, service results and routine checks. Use [troubleshooting](docs/TROUBLESHOOTING.md) for validation errors, endpoint failures or missing notifications. A complete [documentation index](docs/README.md) covers storage, monitoring, encryption and recovery.

## Updates

Select a reviewed published tag, then run its updater:

```bash
cd /opt/unifi-os-backup
git status --short
sudo git fetch origin --tags
sudo git switch --detach v1.4.2
sudo ./update.sh
sudo unifi-backup-configure --validate
```

The tag above is an explicit example; choose the release you intend to deploy. Review local changes before switching. The updater installs the checked-out source and preserves configuration and backup data. It does not fetch a release, launch the wizard or migrate storage automatically. Branch-based installations can use `git pull --ff-only` on `main`; see [upgrading and rollback](docs/UPGRADING.md).

Release history belongs in [CHANGELOG.md](CHANGELOG.md) and [GitHub Releases](https://github.com/Laav/unifi-os-backup/releases). `unifi-backup --version` reports the installed software version; documentation on `main` can be newer than a tagged release.

## Security and recovery boundaries

- Configuration directories use root ownership and mode 0700; secret files and backups use mode 0600. Keep credentials, backups, private recovery identities and configuration journals outside Git.
- TLS validation is mandatory. Use a trusted private CA when needed; insecure TLS is unsupported.
- age encryption uses public recipients on the backup host. Keep recovery identities independently protected. Plaintext exists temporarily during download/encryption; use encrypted host storage when transient data must also be protected.
- SHA256 verifies consistency. It does not prove authenticity or that UniFi can restore a file. Protect metadata independently and schedule real restore drills.
- Remote storage needs its own permission, lifecycle and immutability controls. This tool does not delete remote backups or manage provider account permissions.
- Graph attachments have a conservative size ceiling. Oversized files remain local, and HTTP 202 means Graph accepted a message rather than confirmed delivery.

Read the [security design](docs/SECURITY.md), [recovery guide](docs/DISASTER-RECOVERY.md) and [validation boundaries](docs/TESTING.md) before production rollout. Report vulnerabilities through the process in [SECURITY.md](SECURITY.md).

## Contributing and license

See [CONTRIBUTING.md](CONTRIBUTING.md) for checks and documentation conventions, and [RELEASING.md](docs/RELEASING.md) for versioning and publication policy. Editorial documentation changes do not require a software release. Published tags remain immutable.

Licensed under the [MIT License](LICENSE). This is an independent community project, unaffiliated with Ubiquiti, Microsoft, Amazon Web Services, Auvik, age or ntfy.
