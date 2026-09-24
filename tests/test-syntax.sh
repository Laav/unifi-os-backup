#!/usr/bin/env bash
set -Eeuo pipefail
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
files=("$root/install.sh" "$root/update.sh" "$root/uninstall.sh" "$root/bin/unifi-backup" "$root/bin/unifi-mail-backup" "$root/bin/unifi-backup-check" "$root/tests/fixtures/mock-curl" "$root/tests/fixtures/mock-flock")
for file in "${files[@]}"; do
  bash -n "$file"
done
echo "PASS: Bash syntax"
