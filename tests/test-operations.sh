#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
tmp=$(mktemp -d)
trap 'rm -rf -- "$tmp"' EXIT
mkdir "$tmp/bin" "$tmp/backups" "$tmp/state" "$tmp/targets" "$tmp/disk"
cp "$root/tests/fixtures/mock-curl" "$tmp/bin/curl"
cp "$root/tests/fixtures/mock-hostname" "$tmp/bin/hostname"
chmod 0755 "$tmp/bin/curl" "$tmp/bin/hostname"
if ! command -v flock >/dev/null 2>&1; then
  cp "$root/tests/fixtures/mock-flock" "$tmp/bin/flock"
  chmod 0755 "$tmp/bin/flock"
fi
config="$tmp/backup.env"
sed -e 's#UNIFI_PASSWORD="CHANGE_ME"#UNIFI_PASSWORD="test-only"#' \
    -e "s#BACKUP_DIR=\"/var/backups/unifi\"#BACKUP_DIR=\"$tmp/backups\"#" \
    -e "s#STATUS_FILE=\"/var/lib/unifi-backup/status.json\"#STATUS_FILE=\"$tmp/backups/status.json\"#" \
    -e "s#CATALOG_FILE=\"/var/lib/unifi-backup/catalog.json\"#CATALOG_FILE=\"$tmp/backups/catalog.json\"#" \
    -e "s#LOCK_FILE=\"/run/unifi-backup/unifi-backup.lock\"#LOCK_FILE=\"$tmp/backups/shared.lock\"#" \
    -e 's#BACKUP_TARGETS=""#BACKUP_TARGETS="disk"#' \
    -e "s#BACKUP_TARGET_CONFIG_DIR=\"/etc/unifi-backup/targets.d\"#BACKUP_TARGET_CONFIG_DIR=\"$tmp/targets\"#" \
    -e 's#BACKUP_REQUIRED_TARGETS="0"#BACKUP_REQUIRED_TARGETS="1"#' \
    "$root/config/unifi-backup.env.example" > "$config"
printf '%s\n' 'disk' > "$tmp/disk/.unifi-backup-target"
printf 'TARGET_TYPE="filesystem"\nTARGET_REQUIRED="true"\nTARGET_VERIFY="full"\nFILESYSTEM_REQUIRE_MOUNT="false"\nFILESYSTEM_PATH="%s"\n' "$tmp/disk" > "$tmp/targets/disk.env"
chmod 0600 "$config" "$tmp/targets/disk.env"
export MOCK_EXPECTED_PASSWORD=test-only MOCK_CURL_MODE=success
PATH="$tmp/bin:$PATH" "$root/bin/unifi-backup" --config "$config" > "$tmp/run.log" 2>&1 || { cat "$tmp/run.log" >&2; exit 1; }
PATH="$tmp/bin:$PATH" "$root/bin/unifi-backup-verify" --config "$config" --latest --json > "$tmp/verify.json"
PATH="$tmp/bin:$PATH" "$root/bin/unifi-backup-remote-verify" --config "$config" --latest --full --json > "$tmp/remote.json"
PATH="$tmp/bin:$PATH" "$root/bin/unifi-backup-restore" --config "$config" --target disk --latest --verify-only --json > "$tmp/restore.json"
python3 - "$tmp/verify.json" "$tmp/remote.json" "$tmp/restore.json" <<'PY'
import json, pathlib, sys
v, r, restore = [json.loads(pathlib.Path(p).read_text()) for p in sys.argv[1:]]
assert v['results'][0]['success']
assert r['results'][0]['contents_match'] is True
assert restore['restore_tested'] is False
assert restore['origin'] == 'disk'
PY

# Real Linux flock must serialize maintenance and backup operations. The mock
# used on Windows deliberately does not claim to test kernel locking.
if [[ $(uname -s) == Linux ]]; then
  # The child shell expands its positional argument after acquiring the lock.
  # shellcheck disable=SC2016
  flock "$tmp/backups/shared.lock" bash -c 'touch "$1"; sleep 3' _ "$tmp/locked" &
  holder=$!
  for ((i=0; i<50; i++)); do [[ -f $tmp/locked ]] && break; sleep 0.05; done
  set +e
  PATH="$tmp/bin:$PATH" "$root/bin/unifi-backup-verify" --config "$config" --latest --quiet > "$tmp/lock.log" 2>&1
  lock_rc=$?
  set -e
  wait "$holder"
  [[ $lock_rc -eq 75 ]] || { echo 'FAIL: shared operation lock was not enforced' >&2; exit 1; }
fi
echo 'PASS: Bash backup integrates multi-target replication, verify, remote verify and recovery'
