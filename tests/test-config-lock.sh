#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
if [[ $(uname -s) != Linux ]]; then
  echo 'SKIP: configuration reader/writer flock test requires Linux'
  exit 0
fi
tmp=$(mktemp -d)
trap 'rm -rf -- "$tmp"' EXIT
config="$tmp/config.env"
printf '%s\n' '# synthetic' > "$config"
printf '' > "$tmp/.configure.lock"
chmod 0600 "$config" "$tmp/.configure.lock"

# Shared readers must work with a read-only descriptor (systemd protects /etc).
bash -c 'source "$1/lib/unifi-backup-common.sh"; ub_configuration_read_lock "$2"; [[ -r /proc/$$/fd/8 ]]' _ "$root" "$config"

# An exclusive writer prevents sourcing a mixture of old and new files.
# The child, not the parent shell, expands its positional argument.
# shellcheck disable=SC2016
flock "$tmp/.configure.lock" bash -c 'touch "$1"; sleep 2' _ "$tmp/locked" &
holder=$!
for ((i=0; i<50; i++)); do [[ -f $tmp/locked ]] && break; sleep 0.05; done
set +e
bash -c 'source "$1/lib/unifi-backup-common.sh"; ub_configuration_read_lock "$2"' _ "$root" "$config" > "$tmp/result" 2>&1
rc=$?
set -e
wait "$holder"
[[ $rc == 75 ]] || { echo 'FAIL: configuration writer lock was not enforced' >&2; exit 1; }

printf '%s\n' 'synthetic pending marker' > "$tmp/.configure-pending"
set +e
bash -c 'source "$1/lib/unifi-backup-common.sh"; ub_configuration_read_lock "$2"' _ "$root" "$config" > "$tmp/result" 2>&1
rc=$?
set -e
[[ $rc == 78 ]] || { echo 'FAIL: pending transaction did not block readers' >&2; exit 1; }
echo 'PASS: configuration locks serialize readers and block interrupted transactions'
