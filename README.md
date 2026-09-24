# UniFi OS System Backup for Linux

Production-oriented Bash tooling that signs in to a local UniFi OS controlplane, downloads a full System Config Backup, validates it, stores it atomically, calculates SHA256, applies retention, and can optionally mail a small backup through Microsoft Graph.

> [!IMPORTANT]
> `POST /api/auth/login` and `GET /api/backup/download` are observed UniFi OS **controlplane endpoints**, not a documented stable public Ubiquiti API. UniFi upgrades can change or remove them. This project fails closed when authentication, status, type, size, or content differs from the expected behavior. Read [Endpoint compatibility](docs/TROUBLESHOOTING.md#endpoint-compatibility) before production use.

## Properties

- TLS verification is mandatory; private CAs use `curl --cacert`.
- Credentials, cookies, Graph tokens, and attachments never appear as command-line values or log content.
- Login JSON is generated with Python `json.dumps`, so quotes, newlines, and special characters are handled correctly.
- Downloads land in a mode-0600 temporary file in the destination filesystem and become visible only after validation and an atomic `mv`.
- Retention only considers exact `unifi_os_backup_YYYY-MM-DD_HH-MM-SS.unifi` names.
- `flock` prevents concurrent runs.
- The systemd service is hardened while retaining the filesystem and network access the job needs.
- Configuration and backup data live outside Git under `/etc/unifi-backup` and `/var/backups/unifi`.

## Supported platform

Ubuntu Server 22.04, 24.04, and 26.04 on x86-64 or ARM64. The repository's CI definition runs the userspace test suite in all three Ubuntu releases. The scripts are architecture-neutral; UniFi OS endpoint compatibility must still be revalidated after each UniFi upgrade. At publication time, Ubiquiti documents its own Linux UniFi OS Server runtime as x86-64, while this backup client can run independently on ARM64.

The official UniFi OS Server currently documents Ubuntu 24.04 or later for its own server runtime. This backup client can run on a separate Ubuntu 22.04 host.

## Quick start

```bash
sudo apt-get update
sudo apt-get install -y git curl python3 coreutils findutils util-linux
sudo git clone https://github.com/Laav/unifi-os-backup.git /opt/unifi-os-backup
cd /opt/unifi-os-backup
sudo ./install.sh
sudoedit /etc/unifi-backup/unifi-backup.env
sudo unifi-backup-check --live
sudo systemctl start unifi-backup.service
sudo systemctl start unifi-backup.timer
```

The installer enables the timer but deliberately does not start it until configuration has been reviewed and a live login check succeeds. The default schedule is Sunday at 03:00 local time, with `Persistent=true`.

See [INSTALL.md](docs/INSTALL.md) for bootstrap installation, [UNIFI-ACCOUNT.md](docs/UNIFI-ACCOUNT.md) for the service identity, [CONFIGURATION.md](docs/CONFIGURATION.md) for every setting, and [MICROSOFT-GRAPH.md](docs/MICROSOFT-GRAPH.md) for optional mail.

Repository maintainers should complete [PUBLISHING.md](docs/PUBLISHING.md), including the privacy review and executable Git-mode checks, before publishing a release.

## Dedicated UniFi account

Create a dedicated local UniFi admin named `uni-bck` (the name is configurable). Use local/unattended credentials because a cloud account with interactive MFA is unsuitable for this job. Grant the narrowest role that can create/download a System Config Backup in your installed UniFi OS release. Ubiquiti does not document a stable fine-grained API permission for this endpoint; use Super Admin only if a tested lower role cannot perform the operation. Never use this identity for routine administration. See the step-by-step [service-account guide](docs/UNIFI-ACCOUNT.md).

Ubiquiti's current UI guidance places local admins under the local Network/Control Plane administration UI; labels vary by release. Validate the account by signing in locally and by running `sudo unifi-backup-check --live`.

## Normal operation

```bash
sudo systemctl start unifi-backup.service
sudo journalctl -u unifi-backup.service --since today
systemctl list-timers unifi-backup.timer
sudo sha256sum /var/backups/unifi/unifi_os_backup_*.unifi
```

Success is logged with the file path, byte size, and SHA256. Passwords, cookies, CSRF values, access tokens, authorization headers, and client secrets are never logged.

## Updating

```bash
cd /opt/unifi-os-backup
sudo git pull --ff-only
sudo ./update.sh
```

`update.sh` never changes `/etc/unifi-backup` or `/var/backups/unifi`. Review [UPGRADING.md](docs/UPGRADING.md) first.

## Security model and limitations

- Backups contain sensitive system configuration. Protect the host, directory, mail route, and recipients accordingly.
- A size/hash check proves transfer consistency, not semantic restorability. Schedule restore tests on a non-production UniFi instance.
- Graph's simple JSON `sendMail` route is intentionally limited to files below 2,800,000 bytes by default. Larger backups remain local and make the service fail clearly.
- Email is transport, not an ideal backup vault. Prefer encrypted, access-controlled storage for large or long-term copies.
- The project does not disable TLS verification and contains no `--insecure` escape hatch.

See [SECURITY.md](SECURITY.md) for reporting and [docs/SECURITY.md](docs/SECURITY.md) for the threat model.

## Project status

Version 1.0.0. This is an independent community project and is not affiliated with or supported by Ubiquiti or Microsoft.

## License

[MIT](LICENSE)
