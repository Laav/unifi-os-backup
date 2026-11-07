# Installation

## Prerequisites

- Ubuntu Server 22.04, 24.04, or 26.04.
- Bash 4+, curl, Python 3, systemd, `sha256sum`, `find`, `stat`, `mktemp`, and `flock`.
- Root access for installation and production execution.
- Network reachability to the HTTPS UniFi OS controlplane.
- `age` only when optional encryption at rest is enabled.
- Python's standard library is sufficient for the new data/storage helpers; no pip packages or cloud SDKs are needed.
- The 1.4 wizard requires `dialog` and an interactive terminal. Backups, offline configuration validation and unattended installation do not require a terminal.

From 1.4.2, installer and updater automatically install missing dependencies from configured APT repositories, including Git, CA certificates, `dialog` and `age`. No manual package-install step is required. The system must already use systemd and have working APT repositories/network access. If Git is absent, use the bootstrap download below with the system's existing wget or curl.

Use `--no-install-deps` for offline or centrally provisioned hosts. Missing core dependencies then fail with exit 69; missing dialog/age warn and leave those features unavailable. `--configure` still requires dialog. `sudo ./install.sh --dependencies-only` checks/provisions packages without deploying application/configuration files. When all dependencies are available, APT is not invoked. Package installation uses noninteractive APT with `--no-install-recommends`, `--no-remove` and `--no-upgrade`; there is no distribution upgrade or repository modification. APT can install/adjust transitive dependencies, and package changes are not rolled back if provisioning fails. Application deployment stops on provisioning failure.

## Preferred: inspect a Git checkout

```bash
sudo git clone https://github.com/Laav/unifi-os-backup.git /opt/unifi-os-backup
cd /opt/unifi-os-backup
git status
git log -1 --show-signature
sudo ./install.sh
# Optional from version 1.4; dependencies are provisioned automatically:
# sudo ./install.sh --configure
```

Pinning a release tag or verified commit is preferable to installing an unreviewed moving branch.

## Bootstrap download

Download and inspect the installer; do not pipe remote code directly into a root shell:

```bash
wget -qO install.sh https://raw.githubusercontent.com/Laav/unifi-os-backup/main/install.sh
less install.sh
chmod 0755 install.sh
sudo ./install.sh --repository-url https://github.com/Laav/unifi-os-backup.git
```

The standalone installer provisions missing Git/application dependencies, clones into `/opt/unifi-os-backup`, then installs from that checkout. Bootstrap selects the current default branch. For stronger supply-chain assurance, download a tagged release, compare a checksum published through an independent trusted channel, verify any available trusted signature, and inspect the diff before running it. Dependencies use the host's existing APT trust/repository policy. Do not disable repository signature verification to work around provisioning failures.

`curl ... | sudo bash` is not recommended: it removes the inspection step and can execute a truncated, redirected, or newly replaced response immediately as root.

## Installed paths

| Path | Mode | Purpose |
|---|---:|---|
| `/usr/local/sbin/unifi-backup` | 0755 | Backup workflow |
| `/usr/local/sbin/unifi-mail-backup` | 0755 | Optional Graph mailer |
| `/usr/local/sbin/unifi-backup-check` | 0755 | Configuration/live check |
| `/usr/local/sbin/unifi-backup-upload` | 0755 | Optional Azure Blob/S3 uploader |
| `/usr/local/sbin/unifi-backup-notify` | 0755 | Optional ntfy/generic-webhook publisher |
| `/usr/local/sbin/unifi-backup-status` | 0755 | Monitoring output for RMM/SNMP/Prometheus |
| `/usr/local/sbin/unifi-backup-monitor` | 0755 | Hourly freshness/SLA transition evaluator |
| `/usr/local/sbin/unifi-backup-catalog` | 0755 | Atomic machine-readable inventory builder |
| `/usr/local/lib/unifi-backup/common.sh` | 0644 | Shared structured logging helpers |
| `/etc/unifi-backup/` | 0700 | Configuration directory |
| `/etc/unifi-backup/*.env` | 0600 | Root-owned secrets |
| `/var/backups/unifi/` | 0700 | Backups |
| `/var/lib/unifi-backup/` | 0755 | Non-secret status and Prometheus metrics |
| `/etc/systemd/system/unifi-backup*` | 0644 | Backup and freshness-monitor units/timers |

The examples are copied only when the destination does not exist. Re-running `install.sh` preserves configuration and backups.

Version 1.3 also installs `unifi-backup-verify`, `-replicate`, `-remote-verify`, `-retry`, `-storage-policy`, `-retention`, `-restore`, `-analyze` and `-diff`, the shared `lib/ub` Python modules, a protected `targets.d` example, and three optional timers. Verification/remote-verification/retry timers are not enabled or started by installation/update. Their config flags also default to false.

For a stable reproducible installation, select the published `v1.4.2` tag before running the installer. See [UPGRADING.md](UPGRADING.md) and [RELEASING.md](RELEASING.md).

## Recommended first run on a test machine

```bash
wget -qO install.sh https://raw.githubusercontent.com/Laav/unifi-os-backup/v1.4.2/install.sh
less install.sh
chmod 0755 install.sh
# Provision Git/UI/application dependencies without cloning or deploying files:
sudo ./install.sh --dependencies-only
sudo git clone --branch v1.4.2 --depth 1 https://github.com/Laav/unifi-os-backup.git /opt/unifi-os-backup
cd /opt/unifi-os-backup
sudo ./install.sh --no-enable --configure
sudo unifi-backup-configure --validate --json
sudo unifi-backup-configure --inspect --json
```

This installs from a pinned release and leaves scheduling disabled. In the wizard, review each section and confirm Finish; Cancel does not apply a draft. Test data should use a dedicated service account and isolated storage/mail destinations. Only when ready, explicitly test login and create one backup:

```bash
sudo unifi-backup-check --live
sudo systemctl start unifi-backup.service
sudo journalctl -u unifi-backup.service -n 100 --no-pager
sudo unifi-backup-verify --latest --json
```

Inspect effective drop-ins and complete a recovery drill before enabling timers. None of the commands above enables automatic scheduling; avoid the wizard's separate timer-activation action until acceptance is complete.

## Activate

Version 1.4 provides one terminal configuration interface:

```bash
sudo unifi-backup-configure --guided
sudo unifi-backup-configure --validate
```

See [CONFIGURE.md](CONFIGURE.md) for every section, existing installations, migration/rollback, schedules and safe live-test choices. `install.sh --configure` explicitly launches it; ordinary install and update never require it. Older v1.3.0 installations do not contain this new command; use the manual workflow below until updated. Referenced configuration and manager journals remain outside Git.

```bash
sudoedit /etc/unifi-backup/unifi-backup.env
sudo chown -R root:root /etc/unifi-backup
sudo chmod 0700 /etc/unifi-backup
sudo chmod 0600 /etc/unifi-backup/*.env
sudo chmod 0600 /etc/unifi-backup/age-recipients.txt
sudo unifi-backup-check --live
sudo systemctl start unifi-backup.service
sudo systemctl start unifi-backup.timer
sudo systemctl start unifi-backup-monitor.timer
```

Check `systemctl status` and `journalctl -u unifi-backup.service` after the first real run.

## Uninstall

`sudo ./uninstall.sh` removes programs and units but preserves secrets, monitoring state, and backups. `sudo ./uninstall.sh --purge` also permanently deletes `/etc/unifi-backup`, `/var/lib/unifi-backup`, and `/var/backups/unifi`; inspect and copy important backups first.

Ordinary removal also retains manager-owned drop-ins and private configuration rollback journals. Purge removes only exact manager-owned drop-ins with their expected header, preserving other administrator overrides. External custom configuration/backup paths are not purged automatically.
