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
    -e 's#BACKUP_DOWNLOAD_RETRIES="1"#BACKUP_DOWNLOAD_RETRIES="0"#' \
    -e 's#LOG_FORMAT="text"#LOG_FORMAT="json"#' \
    -e "s#LOCK_FILE=\"/run/unifi-backup/unifi-backup.lock\"#LOCK_FILE=\"$tmp/backups/.unifi-backup.lock\"#" \
    "$root/config/unifi-backup.env.example" > "$config"
chmod 0600 "$config"

export MOCK_EXPECTED_PASSWORD="test-only"
export MOCK_CURL_MODE="success"
PATH="$tmp/bin:$PATH" "$root/bin/unifi-backup" --config "$config" > "$tmp/success.log" 2>&1

backup=$(find "$tmp/backups" -maxdepth 1 -type f -name '*.unifi' -print -quit)
[[ -n $backup && -f $backup.json && -f $tmp/backups/status.json && -f $tmp/backups/unifi_backup.prom ]] || { echo "FAIL: metadata, status, or metrics output is missing" >&2; exit 1; }
python3 - "$tmp/success.log" "$backup" "$backup.json" "$tmp/backups/status.json" <<'PY'
import hashlib, json, pathlib, sys

log_path, backup_path, metadata_path, status_path = map(pathlib.Path, sys.argv[1:])
records = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines() if line]
events = {record["event"] for record in records}
assert {"authentication_succeeded", "backup_succeeded", "backup_checksum", "retention_complete"} <= events
assert all(record["program"] == "unifi-backup" for record in records)
joined = log_path.read_text(encoding="utf-8")
assert "test-only" not in joined and "mock-token-secret" not in joined and "mock-csrf-secret" not in joined

backup = backup_path.read_bytes()
metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
assert metadata["schema_version"] == 1
assert metadata["backup"]["sha256"] == hashlib.sha256(backup).hexdigest()
assert metadata["backup"]["size_bytes"] == len(backup)
assert metadata["tool"]["version"] == "1.1.0"
assert metadata["remote_storage"]["type"] == "none"
assert metadata["email"] == {"enabled": False, "status": "disabled"}
assert "test-only" not in metadata_path.read_text(encoding="utf-8")

status = json.loads(status_path.read_text(encoding="utf-8"))
assert status["last_run"]["status"] == "success"
assert status["last_run"]["exit_code"] == 0
assert status["last_success"]["sha256"] == metadata["backup"]["sha256"]
PY
grep -q '^unifi_backup_last_run_success 1$' "$tmp/backups/unifi_backup.prom" || { echo "FAIL: atomic textfile metrics are incorrect" >&2; exit 1; }

status_json=$("$root/bin/unifi-backup-status" --status-file "$tmp/backups/status.json" --format json --warning-age-hours 192 --critical-age-hours 216)
python3 - "$status_json" <<'PY'
import json, sys
data=json.loads(sys.argv[1])
assert data["monitoring"]["status"] == "OK"
assert data["monitoring"]["status_code"] == 0
PY

sleep 1
export MOCK_CURL_MODE="html"
set +e
PATH="$tmp/bin:$PATH" "$root/bin/unifi-backup" --config "$config" > "$tmp/failure.log" 2>&1
backup_rc=$?
set -e
[[ $backup_rc -eq 74 ]] || { echo "FAIL: invalid response returned exit $backup_rc instead of 74" >&2; exit 1; }

set +e
status_text=$("$root/bin/unifi-backup-status" --status-file "$tmp/backups/status.json" --format text)
status_rc=$?
set -e
[[ $status_rc -eq 2 && $status_text == CRITICAL* ]] || { echo "FAIL: failed run was not CRITICAL" >&2; exit 1; }
[[ $("$root/bin/unifi-backup-status" --status-file "$tmp/backups/status.json" --format snmp) == "2" ]] || { echo "FAIL: SNMP status is not numeric CRITICAL" >&2; exit 1; }
"$root/bin/unifi-backup-status" --status-file "$tmp/backups/status.json" --format prometheus | grep -q '^unifi_backup_last_run_success 0$' || {
  echo "FAIL: Prometheus output did not expose the failed run" >&2
  exit 1
}
python3 - "$tmp/backups/status.json" <<'PY'
import json, pathlib, sys
data=json.loads(pathlib.Path(sys.argv[1]).read_text())
assert data["last_run"]["status"] == "failure"
assert data["last_run"]["exit_code"] == 74
assert data["last_success"] is not None
PY
echo "PASS: JSON logs, metadata, status history, SNMP and Prometheus output"
