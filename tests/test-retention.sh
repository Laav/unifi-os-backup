#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
tmp=$(mktemp -d)
trap 'rm -rf -- "$tmp"' EXIT
backup_dir="$tmp/backups"
mkdir "$backup_dir"
config="$tmp/unifi-backup.env"
sed -e 's#https://unifi.example.invalid:11443#https://127.0.0.1:11443#' \
    -e 's#UNIFI_PASSWORD="CHANGE_ME"#UNIFI_PASSWORD="test-only"#' \
    -e "s#BACKUP_DIR=\"/var/backups/unifi\"#BACKUP_DIR=\"$backup_dir\"#" \
    -e 's#RETENTION_DAYS="35"#RETENTION_DAYS="1"#' \
    "$root/config/unifi-backup.env.example" > "$config"
chmod 0600 "$config"

managed="$backup_dir/unifi_os_backup_2020-01-01_00-00-00.unifi"
unmanaged="$backup_dir/do-not-delete.unifi"
near_match="$backup_dir/unifi_os_backup_NOT-A-DATE.unifi"
: > "$managed"; : > "$unmanaged"; : > "$near_match"
touch -d '10 days ago' "$managed" "$unmanaged" "$near_match"
"$root/bin/unifi-backup" --config "$config" --retention-only
[[ ! -e $managed ]] || { echo "FAIL: expired managed file remains" >&2; exit 1; }
[[ -e $unmanaged && -e $near_match ]] || { echo "FAIL: retention deleted an unmanaged file" >&2; exit 1; }
echo "PASS: defensive retention"
