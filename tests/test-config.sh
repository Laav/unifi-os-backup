#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
tmp=$(mktemp -d)
trap 'rm -rf -- "$tmp"' EXIT
config="$tmp/unifi-backup.env"
backup_dir="$tmp/backups"
password=$'quote" newline-safe\n!@#$%^&*() \\ slash'
sed -e 's#https://unifi.example.invalid:11443#https://127.0.0.1:11443#' \
    -e '/^UNIFI_PASSWORD=/d' \
    -e "s#BACKUP_DIR=\"/var/backups/unifi\"#BACKUP_DIR=\"$backup_dir\"#" \
    "$root/config/unifi-backup.env.example" > "$config"
printf 'UNIFI_PASSWORD=%q\n' "$password" >> "$config"
chmod 0600 "$config"
"$root/bin/unifi-backup" --config "$config" --validate-config

sed -i 's#UNIFI_URL="https://127.0.0.1:11443"#UNIFI_URL="http://127.0.0.1:11443"#' "$config"
if "$root/bin/unifi-backup" --config "$config" --validate-config >/dev/null 2>&1; then
  echo "FAIL: HTTP URL was accepted" >&2
  exit 1
fi
echo "PASS: configuration validation"
