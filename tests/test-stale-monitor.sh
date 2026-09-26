#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
tmp=$(mktemp -d)
trap 'rm -rf -- "$tmp"' EXIT
mkdir "$tmp/bin" "$tmp/state" "$tmp/capture"
cp "$root/tests/fixtures/mock-webhook-curl" "$tmp/bin/curl"
cp "$root/tests/fixtures/mock-hostname" "$tmp/bin/hostname"
chmod 0755 "$tmp/bin/curl" "$tmp/bin/hostname"

config="$tmp/unifi-backup.env"
sed -e 's#UNIFI_PASSWORD="CHANGE_ME"#UNIFI_PASSWORD="test-only"#' \
    -e 's#ENABLE_WEBHOOK="false"#ENABLE_WEBHOOK="true"#' \
    -e "s#WEBHOOK_CONFIG_FILE=\"/etc/unifi-backup/webhook.env\"#WEBHOOK_CONFIG_FILE=\"$tmp/webhook.env\"#" \
    -e "s#STATUS_FILE=\"/var/lib/unifi-backup/status.json\"#STATUS_FILE=\"$tmp/state/status.json\"#" \
    -e 's#STALE_WARNING_HOURS="192"#STALE_WARNING_HOURS="1"#' \
    -e 's#STALE_CRITICAL_HOURS="216"#STALE_CRITICAL_HOURS="2"#' \
    "$root/config/unifi-backup.env.example" > "$config"
sed -e 's#https://monitoring.example.invalid/hooks/unifi-backup#https://hooks.example.invalid/stale#' \
    "$root/config/webhook.env.example" > "$tmp/webhook.env"
cat > "$tmp/state/status.json" <<'JSON'
{"schema_version":1,"last_run":{"status":"success","exit_code":0,"completed_timestamp":1,"duration_seconds":1,"remote_status":"disabled","remote_metadata_status":"disabled","email_status":"disabled"},"last_success":{"completed_timestamp":1,"size_bytes":12000,"sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}}
JSON
chmod 0600 "$config" "$tmp/webhook.env"
chmod 0644 "$tmp/state/status.json"
export MOCK_WEBHOOK_CAPTURE="$tmp/capture" MOCK_WEBHOOK_HTTP_STATUS=202

set +e
PATH="$tmp/bin:$PATH" "$root/bin/unifi-backup-monitor" --config "$config" > "$tmp/stale.log" 2>&1
stale_rc=$?
set -e
[[ $stale_rc -eq 2 ]] || { echo "FAIL: stale backup did not return CRITICAL" >&2; exit 1; }
grep -q '^unifi_backup_stale 1$' "$tmp/state/unifi_backup.prom" || { echo "FAIL: stale Prometheus metric missing" >&2; exit 1; }
[[ -f $tmp/capture/payload-1.json ]] || { echo "FAIL: initial stale transition webhook missing" >&2; cat "$tmp/stale.log" >&2; exit 1; }
python3 - "$tmp/state/monitor-state.json" "$tmp/capture/payload-1.json" <<'PY'
import json, pathlib, sys
state = json.loads(pathlib.Path(sys.argv[1]).read_text())
payload = json.loads(pathlib.Path(sys.argv[2]).read_text())
assert state["status"] == "CRITICAL" and state["stale"] is True
assert payload["event"] == "stale_critical" and payload["status"] == "critical"
PY

set +e
PATH="$tmp/bin:$PATH" "$root/bin/unifi-backup-monitor" --config "$config" >/dev/null 2>&1
repeat_rc=$?
set -e
[[ $repeat_rc -eq 2 && $(<"$tmp/capture/count") == "1" ]] || { echo "FAIL: unchanged stale state sent a duplicate webhook" >&2; exit 1; }

now=$(date +%s)
python3 - "$tmp/state/status.json" "$now" <<'PY'
import json, pathlib, sys
path = pathlib.Path(sys.argv[1]); now = int(sys.argv[2]); data = json.loads(path.read_text())
data["last_run"].update({"status": "success", "exit_code": 0, "completed_timestamp": now})
data["last_success"].update({"completed_timestamp": now})
path.write_text(json.dumps(data))
PY
PATH="$tmp/bin:$PATH" "$root/bin/unifi-backup-monitor" --config "$config" >/dev/null 2>&1
[[ $(<"$tmp/capture/count") == "2" ]] || { echo "FAIL: stale recovery webhook was not sent" >&2; exit 1; }
python3 - "$tmp/capture/payload-2.json" <<'PY'
import json, pathlib, sys
data = json.loads(pathlib.Path(sys.argv[1]).read_text())
assert data["event"] == "stale_recovery" and data["status"] == "success"
PY
grep -q '^unifi_backup_stale 0$' "$tmp/state/unifi_backup.prom" || { echo "FAIL: fresh Prometheus metric missing" >&2; exit 1; }

# A recent successful backup followed by a failed run is already handled by the
# normal failure channel; it must not be mislabeled as a stale transition.
python3 - "$tmp/state/status.json" <<'PY'
import json, pathlib, sys
path = pathlib.Path(sys.argv[1]); data = json.loads(path.read_text())
data["last_run"].update({"status": "failure", "exit_code": 74, "message": "download failed"})
path.write_text(json.dumps(data))
PY
set +e
PATH="$tmp/bin:$PATH" "$root/bin/unifi-backup-monitor" --config "$config" >/dev/null 2>&1
fresh_failure_rc=$?
set -e
[[ $fresh_failure_rc -eq 2 && $(<"$tmp/capture/count") == "2" ]] || { echo "FAIL: a fresh run failure was mislabeled as stale" >&2; exit 1; }
echo "PASS: stale backup SLA detects transitions, suppresses duplicates, and reports recovery"
