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

ub_describe_curl_error() {
  case "$1" in
    5|6) echo "DNS resolution failed" ;;
    7) echo "connection failed" ;;
    28) echo "operation timed out" ;;
    35|51|58|59|60|64|66|77|80|82|83|90|91) echo "TLS/certificate validation failed" ;;
    *) echo "curl transport error $1" ;;
  esac
}
