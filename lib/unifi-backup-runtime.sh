#!/usr/bin/env bash
# Shared Bash entry point. Credentials are transported to Python over stdin,
# never through arguments, exported environment variables, or an eval parser.
ub_runtime() {
  local ub_command=$1 ub_config=/etc/unifi-backup/unifi-backup.env
  shift
  local -a ub_args=()
  while (($#)); do
    case "$1" in
      --config) [[ $# -ge 2 ]] || return 64; ub_config=$2; shift 2 ;;
      *) ub_args+=("$1"); shift ;;
    esac
  done
  if [[ " ${ub_args[*]} " == *" --help "* || " ${ub_args[*]} " == *" -h "* ]]; then
    python3 "$ub_lib/ub/cli.py" "$ub_command" --help
    return
  fi
  ub_private_file() {
    local f=$1 m o d
    [[ $f == /* && -f $f && ! -L $f ]] || { echo 'Invalid private configuration path' >&2; return 78; }
    m=$(stat -c %a "$f"); o=$(stat -c %u "$f"); d=${f%/*}
    [[ $o == "$EUID" && ! -L $d && $(stat -c %u "$d") == "$EUID" ]] || return 78
    (( (8#$m & 8#077) == 0 && (8#$(stat -c %a "$d") & 8#077) == 0 )) || {
      echo 'Configuration requires mode 0600 and directory mode 0700' >&2; return 78;
    }
  }
  ub_private_file "$ub_config" || return $?
  # shellcheck disable=SC1090
  source "$ub_config"
  local ub_lock=${LOCK_FILE:-/run/unifi-backup/unifi-backup.lock}
  if [[ ${UNIFI_BACKUP_LOCK_HELD:-0} != 1 ]]; then
    [[ $ub_lock == /run/unifi-backup/*.lock || ${ub_lock%/*} == "${BACKUP_DIR:-/var/backups/unifi}" ]] || return 78
    mkdir -p -- "${ub_lock%/*}"
    [[ ! -L $ub_lock && ! -L ${ub_lock%/*} ]] || return 78
    exec 9>"$ub_lock"
    flock -n 9 || { echo 'Another backup operation holds the shared lock' >&2; return 75; }
  fi
  ub_emit() {
    local ub_var
    while IFS= read -r ub_var; do
      case "$ub_var" in
        BACKUP_*|RETENTION_*|GFS_*|VERIFY_*|RETRY_*|RESTORE_*|ANOMALY_*|DIFF_*|TARGET_*|S3_*|AZURE_*|STORAGE_*|REMOTE_*|STATUS_FILE|CATALOG_FILE|MIN_BACKUP_SIZE|LOG_FORMAT)
          printf '%s\0%s\0' "$ub_var" "${!ub_var}" ;;
      esac
    done < <(compgen -A variable)
  }
  ub_config_stream() {
    printf '@section\0main\0CONFIG_FILE\0%s\0' "$ub_config"
    ub_emit
    local ub_target ub_target_file
    if [[ -n ${BACKUP_TARGETS:-} ]]; then
      local -a ub_targets
      read -r -a ub_targets <<< "$BACKUP_TARGETS"
      ((${#ub_targets[@]} <= 32)) || return 78
      for ub_target in "${ub_targets[@]}"; do
        [[ $ub_target =~ ^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$ ]] || return 78
        ub_target_file="${BACKUP_TARGET_CONFIG_DIR:-/etc/unifi-backup/targets.d}/$ub_target.env"
        ub_private_file "$ub_target_file" || return $?
        (
          # Avoid accidental credential inheritance between independent targets.
          local ub_var
          while IFS= read -r ub_var; do
            case "$ub_var" in TARGET_*|S3_*|AZURE_*|STORAGE_*) unset "$ub_var" ;; esac
          done < <(compgen -A variable)
          # shellcheck disable=SC1090
          source "$ub_target_file"
          printf '@section\0%s\0' "$ub_target"
          ub_emit
        ) || return $?
      done
    elif [[ ${REMOTE_STORAGE_TYPE:-none} != none ]]; then
      ub_private_file "${STORAGE_CONFIG_FILE:-/etc/unifi-backup/storage.env}" || return $?
      (
        # shellcheck disable=SC1090
        source "${STORAGE_CONFIG_FILE:-/etc/unifi-backup/storage.env}"
        printf '@section\0legacy\0TARGET_TYPE\0%s\0TARGET_REQUIRED\0%s\0' "$REMOTE_STORAGE_TYPE" "${REMOTE_UPLOAD_REQUIRED:-true}"
        ub_emit
      ) || return $?
    fi
    printf '@complete\0true\0'
  }
  ub_config_stream | python3 "$ub_lib/ub/cli.py" "$ub_command" "${ub_args[@]}"
}
