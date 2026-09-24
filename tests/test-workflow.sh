#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
tmp=$(mktemp -d)
trap 'rm -rf -- "$tmp"' EXIT
mkdir "$tmp/bin" "$tmp/backups" "$tmp/locks"
cp "$root/tests/fixtures/mock-curl" "$tmp/bin/curl"
chmod 0755 "$tmp/bin/curl"
if ! command -v flock >/dev/null 2>&1; then
  cp "$root/tests/fixtures/mock-flock" "$tmp/bin/flock"
  chmod 0755 "$tmp/bin/flock"
fi

password=$'quotes " and newline\nwith $() `ticks` \\ backslash'
export MOCK_EXPECTED_PASSWORD=$password
config="$tmp/unifi-backup.env"
sed -e 's#https://unifi.example.invalid:11443#https://127.0.0.1:11443#' \
    -e '/^UNIFI_PASSWORD=/d' \
    -e "s#BACKUP_DIR=\"/var/backups/unifi\"#BACKUP_DIR=\"$tmp/backups\"#" \
    -e "s#LOCK_FILE=\"/run/unifi-backup/unifi-backup.lock\"#LOCK_FILE=\"$tmp/backups/.unifi-backup.lock\"#" \
    "$root/config/unifi-backup.env.example" > "$config"
printf 'UNIFI_PASSWORD=%q\n' "$password" >> "$config"
chmod 0600 "$config"

log_file="$tmp/run.log"
if ! PATH="$tmp/bin:$PATH" "$root/bin/unifi-backup" --config "$config" > "$log_file" 2>&1; then
  echo "FAIL: mocked successful backup run failed" >&2
  cat "$log_file" >&2
  exit 1
fi
mapfile -t backups < <(find "$tmp/backups" -maxdepth 1 -type f -name 'unifi_os_backup_*.unifi')
[[ ${#backups[@]} -eq 1 ]] || { echo "FAIL: expected exactly one completed backup" >&2; exit 1; }
[[ $(stat -c '%a' "${backups[0]}") == "600" ]] || { echo "FAIL: backup mode is not 0600" >&2; exit 1; }
[[ $(stat -c '%s' "${backups[0]}") -gt 10000 ]] || { echo "FAIL: backup is too small" >&2; exit 1; }
python3 - "$log_file" "$password" <<'PY'
import pathlib,sys
log=pathlib.Path(sys.argv[1]).read_text()
for secret in (sys.argv[2],"mock-token-secret","mock-csrf-secret"):
    assert secret not in log, "secret leaked into log"
assert "Backup successful" in log
assert "SHA256:" in log
PY
echo "PASS: atomic backup workflow and log redaction"

rm -f -- "${backups[0]}"
export MOCK_CURL_MODE=html
if PATH="$tmp/bin:$PATH" "$root/bin/unifi-backup" --config "$config" > "$tmp/html.log" 2>&1; then
  echo "FAIL: HTML response was accepted as a backup" >&2
  exit 1
fi
[[ -z $(find "$tmp/backups" -maxdepth 1 -type f \( -name '*.unifi' -o -name '*.tmp' \) -print -quit) ]] || {
  echo "FAIL: failed HTML download left a backup or temporary file" >&2; exit 1;
}
grep -q 'error-like Content-Type' "$tmp/html.log" || {
  echo "FAIL: unexpected HTML-response error" >&2
  cat "$tmp/html.log" >&2
  exit 1
}
echo "PASS: HTML error response fails closed"

export MOCK_CURL_MODE=login401
if PATH="$tmp/bin:$PATH" "$root/bin/unifi-backup" --config "$config" > "$tmp/401.log" 2>&1; then
  echo "FAIL: HTTP 401 login was accepted" >&2
  exit 1
fi
grep -q 'HTTP 401, authentication failed' "$tmp/401.log" || {
  echo "FAIL: unexpected authentication error" >&2
  cat "$tmp/401.log" >&2
  exit 1
}
python3 - "$tmp/401.log" "$password" <<'PY'
import pathlib,sys
log=pathlib.Path(sys.argv[1]).read_text()
for secret in (sys.argv[2],"mock-token-secret","mock-csrf-secret"):
    assert secret not in log, "secret leaked into failure log"
PY
echo "PASS: authentication failure handling"
