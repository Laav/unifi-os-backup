#!/usr/bin/env bash

# Shared, dependency-light helpers. Callers must set PROGRAM and may set
# LOG_FORMAT to either "text" or "json".

ub_log() {
  local level=$1 event=$2 message=$3
  shift 3
  local prefix="${PROGRAM:-unifi-backup}:"

  if [[ ${LOG_FORMAT:-text} != "json" ]]; then
    case "$level" in
      warning) printf '%s WARNING: %s\n' "$prefix" "$message" >&2 ;;
      error) printf '%s ERROR: %s\n' "$prefix" "$message" >&2 ;;
      *) printf '%s %s\n' "$prefix" "$message" ;;
    esac
    return 0
  fi

  if (($# % 2 != 0)); then
    printf '%s ERROR: internal logging field mismatch\n' "$prefix" >&2
    return 70
  fi

  local rendered
  rendered=$(printf '%s\0' "${PROGRAM:-unifi-backup}" "$level" "$event" "$message" "$@" | python3 -c '
import datetime, json, re, sys

parts = sys.stdin.buffer.read().split(b"\0")
if parts and parts[-1] == b"":
    parts.pop()
values = [part.decode("utf-8", "replace") for part in parts]
program, level, event, message, *fields = values
record = {
    "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
    "program": program,
    "level": level,
    "event": event,
    "message": message,
}
for key, value in zip(fields[0::2], fields[1::2]):
    if re.search(r"(?:password|secret|token|authorization|cookie)", key, re.I):
        raise SystemExit("refusing sensitive JSON log field")
    if key.endswith(("_bytes", "_seconds", "_code", "_count", "_timestamp")) and re.fullmatch(r"-?[0-9]+(?:\.[0-9]+)?", value):
        record[key] = float(value) if "." in value else int(value)
    elif value in ("true", "false"):
        record[key] = value == "true"
    else:
        record[key] = value
print(json.dumps(record, separators=(",", ":"), ensure_ascii=True))
') || return $?

  if [[ $level == "warning" || $level == "error" ]]; then
    printf '%s\n' "$rendered" >&2
  else
    printf '%s\n' "$rendered"
  fi
}

ub_info() { ub_log info "$@"; }
ub_warn() { ub_log warning "$@"; }
ub_error() { ub_log error "$@"; }

ub_is_positive_int() { [[ $1 =~ ^[1-9][0-9]*$ ]]; }
ub_is_nonnegative_int() { [[ $1 =~ ^[0-9]+$ ]]; }
ub_is_bool() { [[ $1 == "true" || $1 == "false" ]]; }

# Updated readers hold a shared configuration lock before sourcing any file.
# Configuration apply takes the exclusive lock, then the existing operation
# lock. Nested helpers inherit descriptor 8; production is Linux/flock.
ub_configuration_read_lock() {
  local parent=${1%/*} current
  [[ $(uname -s) == Linux ]] || return 0
  current=$parent
  while [[ $current != / && -n $current ]]; do
    [[ ! -L $current ]] || { echo 'Unsafe configuration ancestor' >&2; return 78; }
    current=${current%/*}
  done
  [[ ! -L $parent/.configure.lock ]] || return 78
  if [[ ! -e $parent/.configure.lock ]]; then
    # Installed services have ProtectSystem=strict. The installer/updater
    # creates this inode; manual test/custom configs may create it on first use.
    (umask 077; set -o noclobber; : >"$parent/.configure.lock") 2>/dev/null || [[ -f $parent/.configure.lock ]] || {
      echo 'Configuration read lock is missing; rerun the installer/updater or initialize it as root' >&2
      return 78
    }
  fi
  if [[ ${UB_CONFIG_READ_LOCK_PATH:-} != "$parent/.configure.lock" || ! -e /proc/$$/fd/8 ]]; then
    exec 8<"$parent/.configure.lock"
    flock -sn 8 || { echo 'Configuration is being changed; retry later' >&2; return 75; }
    UB_CONFIG_READ_LOCK_PATH="$parent/.configure.lock"
    export UB_CONFIG_READ_LOCK_PATH
  else
    [[ $(stat -Lc '%d:%i' /proc/$$/fd/8) == "$(stat -Lc '%d:%i' "$parent/.configure.lock")" ]] || return 75
    flock -sn 8 || return 75
  fi
  [[ ! -e $parent/.configure-pending && ! -L $parent/.configure-pending ]] || {
    echo 'Interrupted configuration transaction: run sudo unifi-backup-configure --recover --yes' >&2
    return 78
  }
}

ub_describe_curl_error() {
  case "$1" in
    5|6) echo "DNS resolution failed" ;;
    7) echo "connection failed" ;;
    28) echo "operation timed out" ;;
    35|51|58|59|60|64|66|77|80|82|83|90|91) echo "TLS/certificate validation failed" ;;
    *) echo "curl transport error $1" ;;
  esac
}
