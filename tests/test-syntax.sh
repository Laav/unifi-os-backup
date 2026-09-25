#!/usr/bin/env bash
set -Eeuo pipefail
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
files=("$root/install.sh" "$root/update.sh" "$root/uninstall.sh" "$root/bin/"* "$root/lib/"*.sh "$root/tests/fixtures/mock-"*)
for file in "${files[@]}"; do
  bash -n "$file"
done
echo "PASS: Bash syntax"
