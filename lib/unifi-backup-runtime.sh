#!/usr/bin/env bash
# Shared Bash entry point. Credentials are transported to Python over stdin,
# never through arguments, exported environment variables, or an eval parser.
ub_runtime() {
  : "${ub_lib:?Caller must set the shared library directory}"
  : "${ub_dir:?Caller must set the executable directory}"
  local ub_command=$1 ub_config=/etc/unifi-backup/unifi-backup.env
  shift
  local -a ub_args=()
  while (($#)); do
    case "$1" in
      --config) [[ $# -ge 2 ]] || return 64; ub_config=$2; shift 2 ;;
      *) ub_args+=("$1"); shift ;;
    esac
  done
  if [[ " ${ub_args[*]} " == *" --help "* || " ${ub_args[*]} " == *" -h "* || " ${ub_args[*]} " == *" --version "* ]]; then
    python3 "$ub_lib/ub/cli.py" "$ub_command" "${ub_args[@]}"
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
  if [[ $ub_command != validate && ${UNIFI_BACKUP_LOCK_HELD:-0} == 1 && $(uname -s) == Linux ]]; then
    # A caller flag alone is insufficient: the inherited descriptor must refer
    # to the configured lock inode and must actually hold/acquire that lock.
    [[ -e /proc/$$/fd/9 && ! -L $ub_lock ]] || return 75
    [[ $(stat -Lc '%d:%i' /proc/$$/fd/9) == "$(stat -Lc '%d:%i' "$ub_lock")" ]] || return 75
    flock -n 9 || return 75
  fi
  if [[ $ub_command != validate && ${UNIFI_BACKUP_LOCK_HELD:-0} != 1 ]]; then
    [[ $ub_lock == /run/unifi-backup/*.lock || ${ub_lock%/*} == "${BACKUP_DIR:-/var/backups/unifi}" ]] || return 78
    mkdir -p -- "${ub_lock%/*}"
    [[ ! -L $ub_lock && ! -L ${ub_lock%/*} ]] || return 78
    chmod 0700 "${ub_lock%/*}"
    exec 9>"$ub_lock"
    flock -n 9 || { echo 'Another backup operation holds the shared lock' >&2; return 75; }
  fi
  ub_emit() {
    local ub_var ub_value
    while IFS= read -r ub_var; do
      case "$ub_var" in
        BACKUP_*|RETENTION_*|GFS_*|VERIFY_*|RETRY_*|RESTORE_*|ANOMALY_*|DIFF_*|TARGET_*|FILESYSTEM_*|S3_*|AZURE_*|STORAGE_*|REMOTE_*|STATUS_FILE|CATALOG_FILE|MIN_BACKUP_SIZE|LOG_FORMAT)
          ub_value=${!ub_var}
          # Native Windows Python in developer tests needs canonical paths.
          # This branch is never taken on supported Linux production hosts.
          case "$ub_var" in
            *_DIR|*_FILE|*_PATH)
              if [[ ( ${OSTYPE:-} == msys || ${OSTYPE:-} == cygwin ) && $ub_value == /* ]]; then ub_value=$(cygpath -am "$ub_value"); fi ;;
          esac
          printf '%s\0%s\0' "$ub_var" "$ub_value" ;;
      esac
    done < <(compgen -A variable)
  }
  ub_config_stream() {
    printf '@section\0main\0CONFIG_FILE\0%s\0' "$ub_config"
    ub_emit
    local ub_target ub_target_file
    if [[ -n ${BACKUP_TARGETS:-} ]]; then
      local -a ub_targets
      local -A ub_seen=()
      read -r -a ub_targets <<< "$BACKUP_TARGETS"
      ((${#ub_targets[@]} <= 32)) || return 78
      for ub_target in "${ub_targets[@]}"; do
        [[ $ub_target =~ ^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$ ]] || return 78
        [[ $ub_target != main && -z ${ub_seen[$ub_target]:-} ]] || { echo 'Duplicate or reserved storage target identifier' >&2; return 78; }
        ub_seen[$ub_target]=1
        ub_target_file="${BACKUP_TARGET_CONFIG_DIR:-/etc/unifi-backup/targets.d}/$ub_target.env"
        ub_private_file "$ub_target_file" || return $?
        (
          # Avoid accidental credential inheritance between independent targets.
          local ub_var
          while IFS= read -r ub_var; do
            case "$ub_var" in TARGET_*|FILESYSTEM_*|S3_*|AZURE_*|STORAGE_*) unset "$ub_var" ;; esac
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
  local ub_rc=0
  ub_config_stream | python3 "$ub_lib/ub/cli.py" "$ub_command" "${ub_args[@]}" || ub_rc=$?
  case "$ub_command" in
    verify|remote-verify|replicate|retry|retention|analyze|diff)
      local ub_catalog="$ub_dir/unifi-backup-catalog"
      [[ -x $ub_catalog ]] || ub_catalog=/usr/local/sbin/unifi-backup-catalog
      if [[ -d ${BACKUP_DIR:-/var/backups/unifi} && -x $ub_catalog ]]; then
        "$ub_catalog" --backup-dir "${BACKUP_DIR:-/var/backups/unifi}" --catalog-file "${CATALOG_FILE:-/var/lib/unifi-backup/catalog.json}" \
          --status-file "${STATUS_FILE:-/var/lib/unifi-backup/status.json}" >/dev/null || true
      fi ;;
  esac
  if [[ " ${ub_args[*]} " == *" --scheduled "* && $ub_rc -ne 0 && ( ${ENABLE_NTFY:-false} == true || ${ENABLE_WEBHOOK:-false} == true ) ]]; then
    local ub_notifier="$ub_dir/unifi-backup-notify"
    local ub_event=failure
    [[ $ub_command != analyze ]] || ub_event=warning
    [[ -x $ub_notifier ]] || ub_notifier=/usr/local/sbin/unifi-backup-notify
    "$ub_notifier" --config "$ub_config" --event "$ub_event" --message "Scheduled $ub_command reported an issue (exit $ub_rc); see operation-specific state" --exit-code "$ub_rc" || true
  fi
  return "$ub_rc"
}
