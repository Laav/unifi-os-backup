#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

die() { echo "unifi-os-backup updater: ERROR: $*" >&2; exit 1; }
(( EUID == 0 )) || die "run as root (sudo ./update.sh)"
source_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
for file in bin/unifi-backup bin/unifi-mail-backup bin/unifi-backup-check systemd/unifi-backup.service systemd/unifi-backup.timer; do
  [[ -f $source_dir/$file ]] || die "missing source file: $file"
done
for script in "$source_dir/bin/unifi-backup" "$source_dir/bin/unifi-mail-backup" "$source_dir/bin/unifi-backup-check"; do
  bash -n "$script" || die "Bash syntax validation failed: $script"
done

# Configuration and backup data are deliberately never touched here.
install -o root -g root -m 0755 "$source_dir/bin/unifi-backup" /usr/local/sbin/unifi-backup
install -o root -g root -m 0755 "$source_dir/bin/unifi-mail-backup" /usr/local/sbin/unifi-mail-backup
install -o root -g root -m 0755 "$source_dir/bin/unifi-backup-check" /usr/local/sbin/unifi-backup-check
install -o root -g root -m 0644 "$source_dir/systemd/unifi-backup.service" /etc/systemd/system/unifi-backup.service
install -o root -g root -m 0644 "$source_dir/systemd/unifi-backup.timer" /etc/systemd/system/unifi-backup.timer
systemctl daemon-reload
systemctl try-restart unifi-backup.timer >/dev/null 2>&1 || true
echo "Update installed. Configuration and backups were preserved."
echo "Review CHANGELOG.md, then run: sudo unifi-backup-check --live"
