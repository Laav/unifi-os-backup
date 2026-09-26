#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
tmp=$(mktemp -d)
trap 'rm -rf -- "$tmp"' EXIT
mkdir "$tmp/bin" "$tmp/backups"
cp "$root/tests/fixtures/mock-curl" "$tmp/bin/curl"
cp "$root/tests/fixtures/mock-hostname" "$tmp/bin/hostname"
cp "$root/tests/fixtures/mock-age" "$tmp/bin/age"
chmod 0755 "$tmp/bin/curl" "$tmp/bin/hostname" "$tmp/bin/age"
if ! command -v flock >/dev/null 2>&1; then
  cp "$root/tests/fixtures/mock-flock" "$tmp/bin/flock"
  chmod 0755 "$tmp/bin/flock"
fi

recipients="$tmp/age-recipients.txt"
printf '%s\n' 'age1testpublicrecipient000000000000000000000000000000000000000000000000' > "$recipients"
config="$tmp/unifi-backup.env"
sed -e 's#https://unifi.example.invalid:11443#https://127.0.0.1:11443#' \
    -e 's#UNIFI_PASSWORD="CHANGE_ME"#UNIFI_PASSWORD="test-only"#' \
    -e "s#BACKUP_DIR=\"/var/backups/unifi\"#BACKUP_DIR=\"$tmp/backups\"#" \
    -e "s#STATUS_FILE=\"/var/lib/unifi-backup/status.json\"#STATUS_FILE=\"$tmp/backups/status.json\"#" \
    -e "s#CATALOG_FILE=\"/var/lib/unifi-backup/catalog.json\"#CATALOG_FILE=\"$tmp/backups/catalog.json\"#" \
    -e 's#ENCRYPTION_TYPE="none"#ENCRYPTION_TYPE="age"#' \
    -e "s#AGE_RECIPIENTS_FILE=\"/etc/unifi-backup/age-recipients.txt\"#AGE_RECIPIENTS_FILE=\"$recipients\"#" \
    -e 's#BACKUP_DOWNLOAD_RETRIES="1"#BACKUP_DOWNLOAD_RETRIES="0"#' \
    -e "s#LOCK_FILE=\"/run/unifi-backup/unifi-backup.lock\"#LOCK_FILE=\"$tmp/backups/.unifi-backup.lock\"#" \
    "$root/config/unifi-backup.env.example" > "$config"
chmod 0600 "$config" "$recipients"
export MOCK_EXPECTED_PASSWORD="test-only" MOCK_CURL_MODE="success"

PATH="$tmp/bin:$PATH" "$root/bin/unifi-backup" --config "$config" > "$tmp/run.log" 2>&1
artifact=$(find "$tmp/backups" -maxdepth 1 -type f -name 'unifi_os_backup_*.unifi.age' -print -quit)
[[ -n $artifact && -f $artifact.json ]] || { echo "FAIL: encrypted backup or sidecar missing" >&2; exit 1; }
[[ -z $(find "$tmp/backups" -maxdepth 1 -type f -name 'unifi_os_backup_*.unifi' -print -quit) ]] || { echo "FAIL: completed plaintext backup remains at rest" >&2; exit 1; }
[[ $(head -c 21 "$artifact") == 'age-encryption.org/v1' ]] || { echo "FAIL: encrypted artifact header is invalid" >&2; exit 1; }

python3 - "$artifact" "$artifact.json" "$tmp/backups/catalog.json" <<'PY'
import hashlib, json, pathlib, sys
artifact, metadata_path, catalog_path = map(pathlib.Path, sys.argv[1:])
metadata = json.loads(metadata_path.read_text())
catalog = json.loads(catalog_path.read_text())
assert metadata["backup"]["filename"].endswith(".unifi.age")
assert metadata["backup"]["sha256"] == hashlib.sha256(artifact.read_bytes()).hexdigest()
assert metadata["encryption"]["enabled"] is True
assert metadata["encryption"]["type"] == "age"
assert metadata["encryption"]["status"] == "success"
assert metadata["encryption"]["original_filename"].endswith(".unifi")
assert metadata["encryption"]["plaintext_size_bytes"] > 10000
assert len(metadata["encryption"]["plaintext_sha256"]) == 64
assert catalog["summary"]["backup_count"] == 1
assert catalog["summary"]["encrypted_count"] == 1
assert catalog["backups"][0]["filename"] == artifact.name
assert catalog["backups"][0]["encryption"] == {"enabled": True, "type": "age"}
PY
grep -q 'Backup encrypted at rest with age recipients' "$tmp/run.log" || { echo "FAIL: encryption success was not logged" >&2; exit 1; }

sleep 1
export MOCK_AGE_FAIL="true"
set +e
PATH="$tmp/bin:$PATH" "$root/bin/unifi-backup" --config "$config" > "$tmp/encryption-failure.log" 2>&1
failure_rc=$?
set -e
[[ $failure_rc -eq 74 ]] || { echo "FAIL: encryption failure returned unexpected exit $failure_rc" >&2; exit 1; }
[[ $(find "$tmp/backups" -maxdepth 1 -type f -name 'unifi_os_backup_*.unifi.age' | wc -l) -eq 1 ]] || { echo "FAIL: encryption failure published another artifact" >&2; exit 1; }
[[ -z $(find "$tmp/backups" -maxdepth 1 -type f \( -name '*.tmp' -o -name 'unifi_os_backup_*.unifi' \) -print -quit) ]] || { echo "FAIL: encryption failure left plaintext or temporary data" >&2; exit 1; }
unset MOCK_AGE_FAIL

printf '%s\n' 'AGE-SECRET-KEY-1TESTPRIVATEIDENTITY' > "$recipients"
if PATH="$tmp/bin:$PATH" "$root/bin/unifi-backup" --config "$config" --validate-config > "$tmp/private.log" 2>&1; then
  echo "FAIL: a private age identity was accepted as a recipient file" >&2
  exit 1
fi
grep -q 'public recipients only' "$tmp/private.log" || { echo "FAIL: private age identity rejection is unclear" >&2; exit 1; }
echo "PASS: optional age encryption removes completed plaintext and updates the central catalog"
