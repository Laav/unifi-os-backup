#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

die() { echo "unifi-os-backup updater: ERROR: $*" >&2; exit 1; }
(( EUID == 0 )) || die "run as root (sudo ./update.sh)"
source_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
for file in bin/unifi-backup bin/unifi-mail-backup bin/unifi-backup-check bin/unifi-backup-upload bin/unifi-backup-notify bin/unifi-backup-status bin/unifi-backup-monitor bin/unifi-backup-catalog lib/unifi-backup-common.sh config/storage.env.example config/ntfy.env.example config/webhook.env.example config/age-recipients.txt.example systemd/unifi-backup.service systemd/unifi-backup.timer systemd/unifi-backup-monitor.service systemd/unifi-backup-monitor.timer; do
  [[ -f $source_dir/$file ]] || die "missing source file: $file"
done
for script in "$source_dir/bin/unifi-backup" "$source_dir/bin/unifi-mail-backup" "$source_dir/bin/unifi-backup-check" "$source_dir/bin/unifi-backup-upload" "$source_dir/bin/unifi-backup-notify" "$source_dir/bin/unifi-backup-status" "$source_dir/bin/unifi-backup-monitor" "$source_dir/bin/unifi-backup-catalog" "$source_dir/lib/unifi-backup-common.sh"; do
  bash -n "$script" || die "Bash syntax validation failed: $script"
done

# Existing configuration and backup data are deliberately never replaced or removed.
install -o root -g root -m 0755 "$source_dir/bin/unifi-backup" /usr/local/sbin/unifi-backup
install -o root -g root -m 0755 "$source_dir/bin/unifi-mail-backup" /usr/local/sbin/unifi-mail-backup
install -o root -g root -m 0755 "$source_dir/bin/unifi-backup-check" /usr/local/sbin/unifi-backup-check
install -o root -g root -m 0755 "$source_dir/bin/unifi-backup-upload" /usr/local/sbin/unifi-backup-upload
install -o root -g root -m 0755 "$source_dir/bin/unifi-backup-notify" /usr/local/sbin/unifi-backup-notify
install -o root -g root -m 0755 "$source_dir/bin/unifi-backup-status" /usr/local/sbin/unifi-backup-status
install -o root -g root -m 0755 "$source_dir/bin/unifi-backup-monitor" /usr/local/sbin/unifi-backup-monitor
install -o root -g root -m 0755 "$source_dir/bin/unifi-backup-catalog" /usr/local/sbin/unifi-backup-catalog
install -d -o root -g root -m 0755 /usr/local/lib/unifi-backup /var/lib/unifi-backup
install -o root -g root -m 0644 "$source_dir/lib/unifi-backup-common.sh" /usr/local/lib/unifi-backup/common.sh
install -o root -g root -m 0644 "$source_dir/systemd/unifi-backup.service" /etc/systemd/system/unifi-backup.service
install -o root -g root -m 0644 "$source_dir/systemd/unifi-backup.timer" /etc/systemd/system/unifi-backup.timer
install -o root -g root -m 0644 "$source_dir/systemd/unifi-backup-monitor.service" /etc/systemd/system/unifi-backup-monitor.service
install -o root -g root -m 0644 "$source_dir/systemd/unifi-backup-monitor.timer" /etc/systemd/system/unifi-backup-monitor.timer

# Existing configuration is never replaced. New optional secret-file examples
# are installed only when their destination does not exist.
install -d -o root -g root -m 0700 /etc/unifi-backup
for optional_config in storage ntfy webhook; do
  destination="/etc/unifi-backup/${optional_config}.env"
  if [[ ! -e $destination ]]; then
    install -o root -g root -m 0600 "$source_dir/config/${optional_config}.env.example" "$destination"
    echo "Created optional $destination with fictitious placeholders."
  fi
done
if [[ ! -e /etc/unifi-backup/age-recipients.txt ]]; then
  install -o root -g root -m 0600 "$source_dir/config/age-recipients.txt.example" /etc/unifi-backup/age-recipients.txt
  echo "Created optional /etc/unifi-backup/age-recipients.txt placeholder."
fi
systemctl daemon-reload
systemctl try-restart unifi-backup.timer >/dev/null 2>&1 || true
systemctl enable unifi-backup-monitor.timer >/dev/null 2>&1 || true
systemctl try-restart unifi-backup-monitor.timer >/dev/null 2>&1 || true
echo "Update installed. Configuration and backups were preserved."
echo "Review CHANGELOG.md and merge new options from config/*.example as needed."
echo "Then run: sudo unifi-backup-check --live && sudo systemctl start unifi-backup.service"
