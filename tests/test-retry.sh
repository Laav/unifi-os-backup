#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
tmp=$(mktemp -d)
trap 'rm -rf -- "$tmp"' EXIT
mkdir "$tmp/bin" "$tmp/backups"
cp "$root/tests/fixtures/mock-curl" "$tmp/bin/curl"
cp "$root/tests/fixtures/mock-hostname" "$tmp/bin/hostname"
chmod 0755 "$tmp/bin/curl" "$tmp/bin/hostname"
if ! command -v flock >/dev/null 2>&1; then
  cp "$root/tests/fixtures/mock-flock" "$tmp/bin/flock"
  chmod 0755 "$tmp/bin/flock"
fi

config="$tmp/unifi-backup.env"
sed -e 's#https://unifi.example.invalid:11443#https://127.0.0.1:11443#' \
    -e 's#UNIFI_PASSWORD="CHANGE_ME"#UNIFI_PASSWORD="test-only"#' \
    -e "s#BACKUP_DIR=\"/var/backups/unifi\"#BACKUP_DIR=\"$tmp/backups\"#" \
    -e "s#STATUS_FILE=\"/var/lib/unifi-backup/status.json\"#STATUS_FILE=\"$tmp/backups/status.json\"#" \
    -e "s#CATALOG_FILE=\"/var/lib/unifi-backup/catalog.json\"#CATALOG_FILE=\"$tmp/backups/catalog.json\"#" \
    -e 's#BACKUP_RETRY_DELAY="15"#BACKUP_RETRY_DELAY="1"#' \
    -e "s#LOCK_FILE=\"/run/unifi-backup/unifi-backup.lock\"#LOCK_FILE=\"$tmp/backups/.unifi-backup.lock\"#" \
    "$root/config/unifi-backup.env.example" > "$config"
chmod 0600 "$config"

export MOCK_EXPECTED_PASSWORD="test-only"
export MOCK_CURL_MODE="html_once"
export MOCK_CURL_STATE_FILE="$tmp/download-attempted"
PATH="$tmp/bin:$PATH" "$root/bin/unifi-backup" --config "$config" > "$tmp/run.log" 2>&1

grep -q 'retrying with a fresh login' "$tmp/run.log" || { echo "FAIL: transient response did not trigger a bounded retry" >&2; exit 1; }
grep -q 'Backup successful' "$tmp/run.log" || { echo "FAIL: backup did not recover after retry" >&2; exit 1; }
[[ $(find "$tmp/backups" -maxdepth 1 -type f -name '*.unifi' | wc -l) -eq 1 ]] || { echo "FAIL: retry did not produce exactly one final backup" >&2; exit 1; }
echo "PASS: transient invalid response is retried once with fresh authentication"
