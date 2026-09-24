# Installation

## Prerequisites

- Ubuntu Server 22.04, 24.04, or 26.04.
- Bash 4+, curl, Python 3, systemd, `sha256sum`, `find`, `stat`, `mktemp`, and `flock`.
- Root access for installation and production execution.
- Network reachability to the HTTPS UniFi OS controlplane.

On Ubuntu:

```bash
sudo apt-get update
sudo apt-get install -y git curl python3 coreutils findutils util-linux
```

## Preferred: inspect a Git checkout

```bash
sudo git clone https://github.com/Laav/unifi-os-backup.git /opt/unifi-os-backup
cd /opt/unifi-os-backup
git status
git log -1 --show-signature
sudo ./install.sh
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

The standalone installer requires Git, clones into `/opt/unifi-os-backup`, then installs from that checkout. It deliberately does not install packages behind the administrator's back. For stronger supply-chain assurance, download a tagged release, compare a checksum published through an independent trusted channel, verify a signed tag/commit, and inspect the diff before running it.

`curl ... | sudo bash` is not recommended: it removes the inspection step and can execute a truncated, redirected, or newly replaced response immediately as root.

## Installed paths

| Path | Mode | Purpose |
|---|---:|---|
| `/usr/local/sbin/unifi-backup` | 0755 | Backup workflow |
| `/usr/local/sbin/unifi-mail-backup` | 0755 | Optional Graph mailer |
| `/usr/local/sbin/unifi-backup-check` | 0755 | Configuration/live check |
| `/etc/unifi-backup/` | 0700 | Configuration directory |
| `/etc/unifi-backup/*.env` | 0600 | Root-owned secrets |
| `/var/backups/unifi/` | 0700 | Backups |
| `/etc/systemd/system/unifi-backup.*` | 0644 | Unit and timer |

The examples are copied only when the destination does not exist. Re-running `install.sh` preserves configuration and backups.

## Activate

```bash
sudoedit /etc/unifi-backup/unifi-backup.env
sudo chown -R root:root /etc/unifi-backup
sudo chmod 0700 /etc/unifi-backup
sudo chmod 0600 /etc/unifi-backup/*.env
sudo unifi-backup-check --live
sudo systemctl start unifi-backup.service
sudo systemctl start unifi-backup.timer
```

Check `systemctl status` and `journalctl -u unifi-backup.service` after the first real run.

## Uninstall

`sudo ./uninstall.sh` removes programs and units but preserves secrets and backups. `sudo ./uninstall.sh --purge` also permanently deletes `/etc/unifi-backup` and `/var/backups/unifi`; inspect and copy important backups first.
