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
newest="$backup_dir/unifi_os_backup_2026-01-01_00-00-00.unifi"
unmanaged="$backup_dir/do-not-delete.unifi"
near_match="$backup_dir/unifi_os_backup_NOT-A-DATE.unifi"
: > "$managed"; : > "$managed.json"; : > "$newest"; : > "$unmanaged"; : > "$near_match"
touch -d '10 days ago' "$managed" "$unmanaged" "$near_match"
"$root/bin/unifi-backup" --config "$config" --retention-only
[[ ! -e $managed ]] || { echo "FAIL: expired managed file remains" >&2; exit 1; }
[[ ! -e $managed.json ]] || { echo "FAIL: metadata sidecar for expired backup remains" >&2; exit 1; }
[[ -e $newest ]] || { echo "FAIL: retention deleted the minimum preserved backup" >&2; exit 1; }
[[ -e $unmanaged && -e $near_match ]] || { echo "FAIL: retention deleted an unmanaged file" >&2; exit 1; }

count_dir="$tmp/count-backups"
mkdir "$count_dir"
count_config="$tmp/count.env"
sed -e 's#https://unifi.example.invalid:11443#https://127.0.0.1:11443#' \
    -e 's#UNIFI_PASSWORD="CHANGE_ME"#UNIFI_PASSWORD="test-only"#' \
    -e "s#BACKUP_DIR=\"/var/backups/unifi\"#BACKUP_DIR=\"$count_dir\"#" \
    -e 's#RETENTION_DAYS="35"#RETENTION_DAYS="0"#' \
    -e 's#RETENTION_COUNT="0"#RETENTION_COUNT="3"#' \
    "$root/config/unifi-backup.env.example" > "$count_config"
chmod 0600 "$count_config"
for day in 01 02 03 04 05; do
  file="$count_dir/unifi_os_backup_2026-01-${day}_00-00-00.unifi"
  : > "$file"
  : > "$file.json"
  touch -d "$((10#$day)) days ago" "$file"
done
"$root/bin/unifi-backup" --config "$count_config" --retention-only
[[ $(find "$count_dir" -maxdepth 1 -type f -name '*.unifi' | wc -l) -eq 3 ]] || { echo "FAIL: count retention did not keep exactly three backups" >&2; exit 1; }
[[ $(find "$count_dir" -maxdepth 1 -type f -name '*.unifi.json' | wc -l) -eq 3 ]] || { echo "FAIL: count retention did not keep matching metadata" >&2; exit 1; }
echo "PASS: defensive retention"
