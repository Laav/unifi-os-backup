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
    "$root/config/unifi-backup.env.example" > "$config"
graph_config="$tmp/graph.env"
sed -e 's#TENANT_ID="CHANGE_ME"#TENANT_ID="00000000-0000-0000-0000-000000000000"#' \
    -e 's#CLIENT_ID="CHANGE_ME"#CLIENT_ID="11111111-1111-1111-1111-111111111111"#' \
    -e 's#CLIENT_SECRET="CHANGE_ME"#CLIENT_SECRET="test-only-secret"#' \
    "$root/config/graph.env.example" > "$graph_config"
chmod 0600 "$config" "$graph_config"

backup="$backup_dir/unifi_os_backup_2026-01-02_03-04-05.unifi"
truncate -s 3000000 "$backup"
chmod 0600 "$backup"
if "$root/bin/unifi-mail-backup" --config "$config" --graph-config "$graph_config" "$backup" > "$tmp/mail.log" 2>&1; then
  echo "FAIL: oversized simple attachment was accepted" >&2
  exit 1
fi
grep -q 'too large for this simple Graph sendMail attachment path' "$tmp/mail.log" || {
  echo "FAIL: unexpected oversized-attachment error" >&2
  cat "$tmp/mail.log" >&2
  exit 1
}
[[ -f $backup && $(stat -c '%s' "$backup") -eq 3000000 ]] || { echo "FAIL: oversized local backup was modified" >&2; exit 1; }
echo "PASS: oversized Graph attachment is rejected and retained"
