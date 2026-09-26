#!/usr/bin/env bash
set -Eeuo pipefail

PURGE=false
[[ ${1:-} == "--purge" ]] && { PURGE=true; shift; }
if (($#)); then echo "Usage: sudo ./uninstall.sh [--purge]" >&2; exit 64; fi
(( EUID == 0 )) || { echo "Run as root" >&2; exit 77; }

systemctl disable --now unifi-backup.timer >/dev/null 2>&1 || true
systemctl disable --now unifi-backup-monitor.timer >/dev/null 2>&1 || true
systemctl stop unifi-backup.service >/dev/null 2>&1 || true
systemctl stop unifi-backup-monitor.service >/dev/null 2>&1 || true
rm -f -- /usr/local/sbin/unifi-backup /usr/local/sbin/unifi-mail-backup /usr/local/sbin/unifi-backup-check
rm -f -- /usr/local/sbin/unifi-backup-upload /usr/local/sbin/unifi-backup-notify /usr/local/sbin/unifi-backup-status
rm -f -- /usr/local/sbin/unifi-backup-monitor /usr/local/sbin/unifi-backup-catalog
rm -f -- /usr/local/lib/unifi-backup/common.sh
rmdir /usr/local/lib/unifi-backup >/dev/null 2>&1 || true
rm -f -- /etc/systemd/system/unifi-backup.service /etc/systemd/system/unifi-backup.timer
rm -f -- /etc/systemd/system/unifi-backup-monitor.service /etc/systemd/system/unifi-backup-monitor.timer
systemctl daemon-reload

if [[ $PURGE == "true" ]]; then
  config_dir=/etc/unifi-backup
  backup_dir=/var/backups/unifi
  state_dir=/var/lib/unifi-backup
  [[ $config_dir == "/etc/unifi-backup" && $backup_dir == "/var/backups/unifi" && $state_dir == "/var/lib/unifi-backup" ]] || { echo "Unsafe purge paths" >&2; exit 70; }
  rm -rf -- "$config_dir" "$backup_dir" "$state_dir"
  echo "Removed programs, units, configuration, monitoring state, and the default /var/backups/unifi directory (--purge). Custom backup paths were not touched. This is not recoverable."
else
  echo "Removed programs and units. Preserved /etc/unifi-backup, /var/lib/unifi-backup, and /var/backups/unifi."
fi
