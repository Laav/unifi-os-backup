#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
tmp=$(mktemp -d)
trap 'rm -rf -- "$tmp"' EXIT
mkdir "$tmp/bin" "$tmp/backups"
cp "$root/tests/fixtures/mock-graph-curl" "$tmp/bin/curl"
cp "$root/tests/fixtures/mock-hostname" "$tmp/bin/hostname"
chmod 0755 "$tmp/bin/curl" "$tmp/bin/hostname"

config="$tmp/unifi-backup.env"
sed -e 's#https://unifi.example.invalid:11443#https://unifi.example.invalid:11443/?label=<test>\&x=1#' \
    -e 's#UNIFI_PASSWORD="CHANGE_ME"#UNIFI_PASSWORD="test-only"#' \
    -e "s#BACKUP_DIR=\"/var/backups/unifi\"#BACKUP_DIR=\"$tmp/backups\"#" \
    "$root/config/unifi-backup.env.example" > "$config"
graph_config="$tmp/graph.env"
sed -e 's#TENANT_ID="CHANGE_ME"#TENANT_ID="00000000-0000-0000-0000-000000000000"#' \
    -e 's#CLIENT_ID="CHANGE_ME"#CLIENT_ID="11111111-1111-1111-1111-111111111111"#' \
    -e 's#CLIENT_SECRET="CHANGE_ME"#CLIENT_SECRET="test-only-secret"#' \
    "$root/config/graph.env.example" > "$graph_config"
chmod 0600 "$config" "$graph_config"

backup="$tmp/backups/unifi_os_backup_2026-01-02_03-04-05.unifi"
printf 'test-backup-content' > "$backup"
chmod 0600 "$backup"
export MOCK_GRAPH_PAYLOAD_CAPTURE="$tmp/payload.json"

PATH="$tmp/bin:$PATH" "$root/bin/unifi-mail-backup" \
  --config "$config" --graph-config "$graph_config" "$backup" > "$tmp/mail.log" 2>&1

python3 - "$MOCK_GRAPH_PAYLOAD_CAPTURE" "$backup" <<'PY'
import base64, json, pathlib, sys

payload = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
source = pathlib.Path(sys.argv[2]).read_bytes()
message = payload["message"]
body = message["body"]["content"]

assert message["subject"] == "[Success] UniFi OS backup - mail-template-test"
assert message["body"]["contentType"] == "HTML"
assert message["toRecipients"] == [{"emailAddress": {"address": "operations@example.invalid"}}]
assert base64.b64decode(message["attachments"][0]["contentBytes"]) == source
assert "UniFi OS Backup" in body
assert "Backup completed successfully and is ready for secure storage" in body
assert "Backup details" in body
assert "Integrity check" in body
assert "SHA256" in body
assert "No reply is required" in body
assert 'role="presentation"' in body
assert "background-color:#111827" in body
assert "max-width:620px" in body
assert "&lt;test&gt;&amp;x=1" in body
assert "<test>" not in body
assert "mock-graph-access-token" not in body
assert "test-only-secret" not in body
assert "✓" not in body
PY

grep -q 'Microsoft Graph accepted the message (HTTP 202)' "$tmp/mail.log" || {
  echo "FAIL: mocked Graph delivery did not succeed" >&2
  cat "$tmp/mail.log" >&2
  exit 1
}
echo "PASS: minimal Outlook-compatible mail template and escaping"
