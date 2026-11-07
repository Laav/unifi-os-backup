# Installation

[Documentation index](README.md) · [Configuration wizard](CONFIGURE.md) · [Operations](OPERATIONS.md)

## Prerequisites and dependency provisioning

Use Ubuntu Server 22.04, 24.04 or 26.04 with systemd, root access and HTTPS connectivity to the UniFi OS controlplane. The backup client can run separately from UniFi OS Server. It uses Bash, curl, Python's standard library and standard Linux utilities; no pip packages, cloud SDKs or desktop environment are needed.

Installer and updater check for missing dependencies and provision them through configured APT repositories, including Git, CA certificates, dialog and age. No manual package-install step is required. APT repositories and their trust configuration must already work. An unsupported init system is not replaced.

| Option | Behavior |
|---|---|
| `--configure` | Installer opens the wizard after deployment; requires an interactive terminal |
| `--no-enable` | Installer does not enable the backup or monitor timers; use for an initial test installation |
| `--dependencies-only` | Installer checks/provisions packages without cloning or deploying application/configuration files |
| `--no-install-deps` | Installer/updater skip APT for offline or pre-provisioned systems |

With the explicit dependency opt-out, missing core tools fail with exit 69; missing dialog/age warn and leave their features unavailable. `--configure` still requires dialog. Ordinary installation, update and scheduled backups never require a TTY.

APT runs only when dependencies are missing. Provisioning uses noninteractive installation with `--no-install-recommends`, `--no-remove` and `--no-upgrade`. It requests no distribution upgrade or repository changes. APT can adjust transitive dependencies; package changes are not transactional or rolled back. Provisioning failure stops application deployment with exit 69.

## Recommended first run on a test machine

Choose a reviewed [published release](https://github.com/Laav/unifi-os-backup/releases/latest). The following example pins `v1.4.2`; substitute the same reviewed tag in both download and clone commands when selecting another release.

```bash
wget -qO install.sh https://raw.githubusercontent.com/Laav/unifi-os-backup/v1.4.2/install.sh
less install.sh
chmod 0755 install.sh
sudo ./install.sh --dependencies-only
sudo git clone --branch v1.4.2 --depth 1 https://github.com/Laav/unifi-os-backup.git /opt/unifi-os-backup
cd /opt/unifi-os-backup
git log -1 --show-signature
sudo ./install.sh --no-enable --configure
```

The initial standalone step provisions Git and other dependencies without creating a checkout. Installation then uses the pinned checkout. If Git is already available, start with the clone command; the installer still provisions other missing dependencies.

Use the host's existing curl instead of wget if preferred:

```bash
curl --fail --silent --show-error --output install.sh \
  https://raw.githubusercontent.com/Laav/unifi-os-backup/v1.4.2/install.sh
```

Inspect downloaded code before running it. Validate any available independently trusted checksum/signature; do not assume an annotated tag is signed. Avoid `curl ... | sudo bash`, which removes the inspection step.

Only use this procedure for a fresh checkout path. For an existing installation use [UPGRADING.md](UPGRADING.md); do not clone over an existing directory. `--no-enable` leaves fresh timers disabled and does not deactivate already running timers on a reused installation.

## Configure and validate

Create the [dedicated UniFi account](UNIFI-ACCOUNT.md), then complete the [guided setup](CONFIGURE.md). Enter the HTTPS origin, local account credentials, local destination and any desired integrations. Review every change before Finish. Cancel leaves the draft unapplied.

After an unattended installation, launch configuration separately:

```bash
sudo unifi-backup-configure --guided
sudo unifi-backup-configure --validate --json
sudo unifi-backup-configure --inspect --json
```

For unattended deployment omit `--configure`. Existing manually managed files remain supported; see [CONFIGURATION.md](CONFIGURATION.md) for ownership, literal assignment syntax and the generated field reference. Installation/update create examples only when their destinations are absent and never overwrite existing credentials.

## First backup and activation

Use a dedicated test account and isolated storage/notification destinations. Explicitly test login, create one backup and verify it:

```bash
sudo unifi-backup-check --live
sudo systemctl start unifi-backup.service
sudo journalctl -u unifi-backup.service --since "10 minutes ago" --no-pager
sudo unifi-backup-verify --latest --json
```

Login success does not verify the download endpoint. Integrity success does not prove application-level restorability. Complete an isolated [recovery drill](DISASTER-RECOVERY.md), inspect effective systemd drop-ins and review schedule/freshness thresholds before enabling scheduling.

```bash
sudo systemctl enable --now unifi-backup.timer unifi-backup-monitor.timer
systemctl list-timers 'unifi-backup*'
```

The default backup is Sunday at 03:00 local time. A persistent timer can start an overdue job immediately on activation. The wizard also has explicit timer actions; avoid them until acceptance is complete. Verification, remote-verification and retry timers are installed separately and remain opt-in. See [OPERATIONS.md](OPERATIONS.md).

## Alternative: automatic-clone bootstrap

For an inspected default-branch installation, download the standalone installer and let it provision Git and clone the repository:

```bash
wget -qO install.sh https://raw.githubusercontent.com/Laav/unifi-os-backup/main/install.sh
less install.sh
chmod 0755 install.sh
sudo ./install.sh --repository-url https://github.com/Laav/unifi-os-backup.git --no-enable
```

This selects the current default branch, even if the bootstrap script itself came from a tag. Use the pinned-checkout procedure above when reproducible source selection is required. Existing configuration remains external to the checkout.

## Installed layout

| Path | Purpose and permissions |
|---|---|
| `/opt/unifi-os-backup/` | Source checkout used for installation and updates |
| `/usr/local/sbin/unifi-backup*` | Installed CLI programs, root-owned mode 0755 |
| `/usr/local/sbin/unifi-mail-backup` | Optional Graph mailer, root-owned mode 0755 |
| `/usr/local/lib/unifi-backup/` | Shared Bash/Python modules, root-owned code |
| `/etc/unifi-backup/` | Private configuration directory, root:root mode 0700 |
| `/etc/unifi-backup/*.env` | Main/integration files, root:root mode 0600 |
| `/etc/unifi-backup/targets.d/` | Private per-target configuration, directory 0700 and files 0600 |
| `/var/backups/unifi/` | Default private backup directory, directory 0700 and artifacts 0600 |
| `/var/lib/unifi-backup/` | Operational state, private catalog/reports and readable monitoring outputs; directory 0755 |
| `/etc/systemd/system/unifi-backup*` | Installed units/timers and reviewed drop-ins |

Shared logging is installed as `/usr/local/lib/unifi-backup/common.sh`. Individual state-file visibility is documented in [MONITORING.md](MONITORING.md); a readable state directory does not make every file public. Custom paths and administrator drop-ins remain supported.

## Removal

From the source checkout, `sudo ./uninstall.sh` removes application programs/units while retaining configuration, backups, state, manager-owned drop-ins and private transaction journals. It does not uninstall APT packages.

`sudo ./uninstall.sh --purge` permanently removes the default `/etc/unifi-backup`, `/var/lib/unifi-backup` and `/var/backups/unifi` trees. Preserve verified independent copies first. Purge removes only recognized manager-owned drop-ins and retains other administrator overrides. External custom configuration and backup paths are not purged automatically.
