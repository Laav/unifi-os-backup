#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
tmp=$(mktemp -d)
trap 'rm -rf -- "$tmp"' EXIT
mkdir "$tmp/bin" "$tmp/capture"
cp "$root/tests/fixtures/mock-ntfy-curl" "$tmp/bin/curl"
cp "$root/tests/fixtures/mock-hostname" "$tmp/bin/hostname"
chmod 0755 "$tmp/bin/curl" "$tmp/bin/hostname"

config="$tmp/unifi-backup.env"
sed -e 's#https://unifi.example.invalid:11443#https://127.0.0.1:11443#' \
    -e 's#UNIFI_PASSWORD="CHANGE_ME"#UNIFI_PASSWORD="test-only"#' \
    -e "s#NTFY_CONFIG_FILE=\"/etc/unifi-backup/ntfy.env\"#NTFY_CONFIG_FILE=\"$tmp/ntfy.env\"#" \
    "$root/config/unifi-backup.env.example" > "$config"
ntfy_config="$tmp/ntfy.env"
sed -e 's#NTFY_TOPIC="unifi-backup-example-topic"#NTFY_TOPIC="test-backup-topic"#' \
    -e 's#NTFY_ACCESS_TOKEN="CHANGE_ME"#NTFY_ACCESS_TOKEN="tk_test-only-token"#' \
    "$root/config/ntfy.env.example" > "$ntfy_config"
chmod 0600 "$config" "$ntfy_config"

export MOCK_NTFY_CAPTURE="$tmp/capture"
export MOCK_NTFY_HTTP_STATUS=200
PATH="$tmp/bin:$PATH" "$root/bin/unifi-backup-notify" --config "$config" --ntfy-config "$ntfy_config" \
  --event failure --exit-code 74 --message 'Backup response validation failed' > "$tmp/notify.log" 2>&1

grep -q '/test-backup-topic' "$tmp/capture/curl-config" || { echo "FAIL: ntfy topic URL is incorrect" >&2; exit 1; }
grep -q '^Authorization: Bearer tk_test-only-token$' "$tmp/capture/headers" || { echo "FAIL: ntfy bearer header missing" >&2; exit 1; }
grep -q '^Title: UniFi backup failed - mail-template-test$' "$tmp/capture/headers" || { echo "FAIL: ntfy title is incorrect" >&2; exit 1; }
grep -q '^Priority: high$' "$tmp/capture/headers" || { echo "FAIL: ntfy failure priority is incorrect" >&2; exit 1; }
[[ $(<"$tmp/capture/body") == 'Backup response validation failed' ]] || { echo "FAIL: ntfy body is incorrect" >&2; exit 1; }
if grep -q 'tk_test-only-token' "$tmp/capture/argv" "$tmp/notify.log"; then
  echo "FAIL: ntfy token leaked into argv or logs" >&2
  exit 1
fi
if grep -qi '^Tags:' "$tmp/capture/headers"; then
  echo "FAIL: ntfy notification unexpectedly uses icon-producing tags" >&2
  exit 1
fi
echo "PASS: ntfy notification uses protected bearer authentication without icon tags"
