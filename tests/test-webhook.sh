#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
tmp=$(mktemp -d)
trap 'rm -rf -- "$tmp"' EXIT
mkdir "$tmp/bin" "$tmp/capture"
cp "$root/tests/fixtures/mock-webhook-curl" "$tmp/bin/curl"
cp "$root/tests/fixtures/mock-hostname" "$tmp/bin/hostname"
chmod 0755 "$tmp/bin/curl" "$tmp/bin/hostname"

config="$tmp/unifi-backup.env"
sed -e 's#https://unifi.example.invalid:11443#https://127.0.0.1:11443#' \
    -e 's#UNIFI_PASSWORD="CHANGE_ME"#UNIFI_PASSWORD="test-only"#' \
    -e 's#ENABLE_WEBHOOK="false"#ENABLE_WEBHOOK="true"#' \
    -e "s#WEBHOOK_CONFIG_FILE=\"/etc/unifi-backup/webhook.env\"#WEBHOOK_CONFIG_FILE=\"$tmp/webhook.env\"#" \
    -e "s#STATUS_FILE=\"/var/lib/unifi-backup/status.json\"#STATUS_FILE=\"$tmp/status.json\"#" \
    "$root/config/unifi-backup.env.example" > "$config"
webhook="$tmp/webhook.env"
sed -e 's#https://monitoring.example.invalid/hooks/unifi-backup#https://hooks.example.invalid/private/path?sig=url-secret#' \
    -e 's#WEBHOOK_BEARER_TOKEN=""#WEBHOOK_BEARER_TOKEN="bearer-test-secret"#' \
    -e 's#WEBHOOK_HMAC_SECRET=""#WEBHOOK_HMAC_SECRET="hmac-test-secret"#' \
    "$root/config/webhook.env.example" > "$webhook"
cat > "$tmp/status.json" <<'JSON'
{"schema_version":1,"last_run":{"status":"failure","exit_code":74},"last_success":{"completed_at":"2026-09-25T03:00:00Z","completed_timestamp":1790305200},"monitoring":{"status":"CRITICAL","status_code":2,"stale":false}}
JSON
cat > "$tmp/backup.unifi.json" <<'JSON'
{"schema_version":1,"backup":{"id":"test-run-id","source":"https://127.0.0.1:11443","filename":"unifi_os_backup_2026-09-25_03-00-00.unifi","size_bytes":12000,"sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"},"encryption":{"enabled":false,"type":"none"},"remote_storage":{"type":"none","backup_status":"disabled"}}
JSON
chmod 0600 "$config" "$webhook" "$tmp/status.json" "$tmp/backup.unifi.json"
export MOCK_WEBHOOK_CAPTURE="$tmp/capture" MOCK_WEBHOOK_HTTP_STATUS=202

PATH="$tmp/bin:$PATH" "$root/bin/unifi-backup-notify" --config "$config" --webhook-config "$webhook" \
  --status-file "$tmp/status.json" --metadata "$tmp/backup.unifi.json" --event failure \
  --exit-code 74 --message 'Backup response validation failed' > "$tmp/notify.log" 2>&1

python3 - "$tmp/capture/payload-1.json" "$tmp/capture/headers-1" <<'PY'
import hashlib, hmac, json, pathlib, sys
payload_path, headers_path = map(pathlib.Path, sys.argv[1:])
body = payload_path.read_bytes()
data = json.loads(body)
headers = headers_path.read_text().splitlines()
assert data["schema_version"] == 1
assert data["event"] == "failure" and data["status"] == "failed" and data["exit_code"] == 74
assert data["controller"] == "https://127.0.0.1:11443"
assert data["backup"]["id"] == "test-run-id"
assert data["monitoring"]["status"] == "CRITICAL"
assert "Authorization: Bearer bearer-test-secret" in headers
expected = hmac.new(b"hmac-test-secret", body, hashlib.sha256).hexdigest()
assert "X-UniFi-Backup-Signature: sha256=" + expected in headers
PY
grep -q 'url-secret' "$tmp/capture/curl-config-1" || { echo "FAIL: protected webhook URL was not used" >&2; exit 1; }
if grep -Eq 'url-secret|bearer-test-secret|hmac-test-secret' "$tmp/capture/argv-1" "$tmp/notify.log"; then
  echo "FAIL: webhook secret leaked into argv or logs" >&2
  exit 1
fi
echo "PASS: generic webhook uses protected URL/auth, signed JSON, and structured monitoring data"
