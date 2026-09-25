#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
tmp=$(mktemp -d)
trap 'rm -rf -- "$tmp"' EXIT
mkdir "$tmp/bin" "$tmp/backups" "$tmp/capture"
cp "$root/tests/fixtures/mock-storage-curl" "$tmp/bin/curl"
chmod 0755 "$tmp/bin/curl"

config="$tmp/unifi-backup.env"
sed -e 's#https://unifi.example.invalid:11443#https://127.0.0.1:11443#' \
    -e 's#UNIFI_PASSWORD="CHANGE_ME"#UNIFI_PASSWORD="test-only"#' \
    -e "s#BACKUP_DIR=\"/var/backups/unifi\"#BACKUP_DIR=\"$tmp/backups\"#" \
    -e 's#REMOTE_STORAGE_TYPE="none"#REMOTE_STORAGE_TYPE="azure_blob"#' \
    -e "s#STORAGE_CONFIG_FILE=\"/etc/unifi-backup/storage.env\"#STORAGE_CONFIG_FILE=\"$tmp/storage.env\"#" \
    "$root/config/unifi-backup.env.example" > "$config"
storage_config="$tmp/storage.env"
sed -e 's#AZURE_BLOB_SAS_TOKEN="CHANGE_ME"#AZURE_BLOB_SAS_TOKEN="sv=2026-01-01\&sp=cw\&sig=azure-test-secret"#' \
    -e 's#S3_ACCESS_KEY_ID="CHANGE_ME"#S3_ACCESS_KEY_ID="TESTACCESSKEY"#' \
    -e 's#S3_SECRET_ACCESS_KEY="CHANGE_ME"#S3_SECRET_ACCESS_KEY="s3-test-secret"#' \
    "$root/config/storage.env.example" > "$storage_config"
chmod 0600 "$config" "$storage_config"

backup="$tmp/backups/unifi_os_backup_2026-01-02_03-04-05.unifi"
printf 'remote-storage-test' > "$backup"
chmod 0600 "$backup"
export MOCK_STORAGE_CAPTURE="$tmp/capture"
export MOCK_STORAGE_HTTP_STATUS=201
PATH="$tmp/bin:$PATH" "$root/bin/unifi-backup-upload" --config "$config" --storage-config "$storage_config" "$backup" > "$tmp/azure.log" 2>&1

grep -q 'x-ms-blob-type: BlockBlob' "$tmp/capture/headers" || { echo "FAIL: Azure block blob header missing" >&2; exit 1; }
grep -q 'If-None-Match: \*' "$tmp/capture/headers" || { echo "FAIL: Azure overwrite protection missing" >&2; exit 1; }
grep -q 'unifi-os-backups/unifi_os_backup_2026-01-02_03-04-05.unifi?' "$tmp/capture/curl-config" || { echo "FAIL: Azure object URL is incorrect" >&2; exit 1; }
grep -q 'azure-test-secret' "$tmp/capture/curl-config" || { echo "FAIL: Azure SAS was not supplied through the protected curl config" >&2; exit 1; }
if grep -q 'azure-test-secret' "$tmp/capture/argv" "$tmp/azure.log"; then
  echo "FAIL: Azure SAS leaked into argv or logs" >&2
  exit 1
fi

sed -i 's#REMOTE_STORAGE_TYPE="azure_blob"#REMOTE_STORAGE_TYPE="s3"#' "$config"
export MOCK_STORAGE_HTTP_STATUS=200
PATH="$tmp/bin:$PATH" "$root/bin/unifi-backup-upload" --config "$config" --storage-config "$storage_config" "$backup" > "$tmp/s3.log" 2>&1
grep -q '^Authorization: AWS4-HMAC-SHA256 ' "$tmp/capture/headers" || { echo "FAIL: S3 Signature V4 authorization missing" >&2; exit 1; }
grep -q '^x-amz-content-sha256: ' "$tmp/capture/headers" || { echo "FAIL: S3 payload hash header missing" >&2; exit 1; }
grep -q '/unifi-os-backups/production/unifi_os_backup_2026-01-02_03-04-05.unifi' "$tmp/capture/curl-config" || { echo "FAIL: S3 path-style object URL is incorrect" >&2; exit 1; }
if grep -q 's3-test-secret' "$tmp/capture/argv" "$tmp/capture/headers" "$tmp/capture/curl-config" "$tmp/s3.log"; then
  echo "FAIL: S3 secret access key leaked" >&2
  exit 1
fi
echo "PASS: Azure Blob and S3-compatible uploads protect credentials and refuse overwrites"
