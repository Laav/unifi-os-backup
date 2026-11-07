#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

PROGRAM="unifi-os-backup installer"
INSTALL_DIR="/opt/unifi-os-backup"
REPOSITORY_URL=""
ENABLE_TIMER=true
CONFIGURE=false
INSTALL_DEPS=true
DEPENDENCIES_ONLY=false

ensure_dependencies() {
  local spec executable package
  local -a packages=() missing_core=() missing_optional=()
  local -A seen=()
  # Never replace an unsupported init system merely to satisfy a dependency.
  command -v systemctl >/dev/null 2>&1 || die "a systemd-based Ubuntu/Debian host is required; no init-system replacement is attempted" 69
  for spec in git:git curl:curl python3:python3 sha256sum:coreutils stat:coreutils install:coreutils mktemp:coreutils find:findutils flock:util-linux hostname:hostname dialog:dialog age:age; do
    executable=${spec%%:*}; package=${spec#*:}
    if ! command -v "$executable" >/dev/null 2>&1; then
      case "$executable" in dialog|age) missing_optional+=("$executable") ;; *) missing_core+=("$executable") ;; esac
      if [[ -z ${seen[$package]:-} ]]; then packages+=("$package"); seen[$package]=1; fi
    fi
  done
  if [[ ! -s /etc/ssl/certs/ca-certificates.crt ]]; then
    packages+=(ca-certificates)
    missing_core+=(ca-certificates)
  fi
  if ((${#packages[@]} == 0)); then
    log "All application dependencies are available"
    return 0
  fi
  if [[ $INSTALL_DEPS == false ]]; then
    ((${#missing_core[@]} == 0)) || die "missing required dependencies: ${missing_core[*]}; automatic provisioning was explicitly disabled" 69
    log "Automatic provisioning disabled; unavailable optional features: ${missing_optional[*]}"
    return 0
  fi
  command -v apt-get >/dev/null 2>&1 || die "automatic provisioning requires APT; pre-provision dependencies on unsupported platforms" 69
  log "Installing missing dependencies from configured APT repositories: ${packages[*]}"
  # No distribution upgrade, repository modification, package removal or
  # unauthenticated download. Abort before deploying application files on error.
  if ! apt-get -o DPkg::Lock::Timeout=120 -o Acquire::Retries=2 update; then
    die "dependency index refresh failed; application files and configuration were not changed" 69
  fi
  if ! DEBIAN_FRONTEND=noninteractive apt-get -o DPkg::Lock::Timeout=120 --assume-yes --no-install-recommends --no-remove --no-upgrade install "${packages[@]}"; then
    die "dependency installation failed; application files and configuration were not changed" 69
  fi
  for executable in "${missing_core[@]}" "${missing_optional[@]}"; do
    if [[ $executable == ca-certificates ]]; then
      [[ -s /etc/ssl/certs/ca-certificates.crt ]] || die "the system CA bundle remains unavailable" 69
    else
      command -v "$executable" >/dev/null 2>&1 || die "dependency remains unavailable after provisioning: $executable" 69
    fi
  done
}

usage() {
  cat <<'EOF'
Usage: sudo ./install.sh [--repository-url HTTPS_GIT_URL] [--install-dir DIR] [--no-enable] [--configure] [--no-install-deps]
       sudo ./install.sh --dependencies-only [--no-install-deps]

From a complete checkout, files are installed from that checkout. When only this
bootstrap script was downloaded, --repository-url is required and Git clones the
repository into /opt/unifi-os-backup.
Missing dependencies (including dialog and age) are installed through configured
APT repositories by default. --no-install-deps opts out for pre-provisioned or
offline systems. --dependencies-only checks/provisions packages without deploying
application/configuration files. --configure explicitly opens the wizard after
installation; ordinary installation remains noninteractive.
EOF
}

while (($#)); do
  case "$1" in
    --repository-url) [[ $# -ge 2 ]] || { usage >&2; exit 64; }; REPOSITORY_URL=$2; shift 2 ;;
    --install-dir) [[ $# -ge 2 ]] || { usage >&2; exit 64; }; INSTALL_DIR=$2; shift 2 ;;
    --no-enable) ENABLE_TIMER=false; shift ;;
    --configure) CONFIGURE=true; shift ;;
    --no-install-deps) INSTALL_DEPS=false; shift ;;
    --dependencies-only) DEPENDENCIES_ONLY=true; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "$PROGRAM: unknown option: $1" >&2; exit 64 ;;
  esac
done

log() { printf '%s: %s\n' "$PROGRAM" "$*"; }
die() { printf '%s: ERROR: %s\n' "$PROGRAM" "$*" >&2; exit "${2:-1}"; }
(( EUID == 0 )) || die "run this installer as root (sudo ./install.sh)" 77
if [[ $DEPENDENCIES_ONLY == true ]]; then
  ensure_dependencies
  exit 0
fi
for protected in /etc/unifi-backup /etc/unifi-backup/targets.d /etc/unifi-backup/.configure.lock /etc/unifi-backup/unifi-backup.env /etc/unifi-backup/graph.env /etc/unifi-backup/storage.env /etc/unifi-backup/ntfy.env /etc/unifi-backup/webhook.env /etc/unifi-backup/age-recipients.txt; do
  [[ ! -L $protected ]] || die "configuration symlink refused" 78
done
if [[ $CONFIGURE == true ]]; then
  [[ -t 0 && -t 1 ]] || die "--configure needs a terminal; use sudo unifi-backup-configure later" 69
fi
[[ $INSTALL_DIR == /* && $INSTALL_DIR != "/" ]] || die "--install-dir must be an absolute, non-root path" 64
ensure_dependencies
if [[ $CONFIGURE == true ]]; then
  command -v dialog >/dev/null 2>&1 || die "the wizard needs dialog; rerun without --no-install-deps to provision it automatically" 69
fi

for command_name in bash curl python3 sha256sum find stat flock systemctl install; do
  command -v "$command_name" >/dev/null 2>&1 || die "missing dependency: $command_name" 69
done

script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
source_dir=$script_dir
if [[ ! -f $source_dir/bin/unifi-backup || ! -f $source_dir/systemd/unifi-backup.service ]]; then
  [[ -n $REPOSITORY_URL ]] || die "standalone bootstrap mode requires --repository-url" 64
  [[ $REPOSITORY_URL =~ ^https://[^[:space:]]+\.git$ ]] || die "repository URL must be an HTTPS .git URL" 64
  [[ $REPOSITORY_URL != *"@"* && $REPOSITORY_URL != *"?"* && $REPOSITORY_URL != *"#"* ]] || die "repository URL must not contain credentials, a query, or a fragment" 64
  command -v git >/dev/null 2>&1 || die "Git is required for bootstrap mode; rerun without --no-install-deps" 69
  if [[ -e $INSTALL_DIR ]]; then
    [[ -d $INSTALL_DIR/.git ]] || die "$INSTALL_DIR already exists and is not a Git checkout" 73
    log "Using existing checkout at $INSTALL_DIR"
  else
    log "Cloning source into $INSTALL_DIR"
    git clone --depth 1 -- "$REPOSITORY_URL" "$INSTALL_DIR"
  fi
  source_dir=$INSTALL_DIR
fi

for required in bin/unifi-backup bin/unifi-mail-backup bin/unifi-backup-check bin/unifi-backup-upload bin/unifi-backup-notify bin/unifi-backup-status bin/unifi-backup-monitor bin/unifi-backup-catalog lib/unifi-backup-common.sh config/unifi-backup.env.example config/graph.env.example config/storage.env.example config/ntfy.env.example config/webhook.env.example config/age-recipients.txt.example systemd/unifi-backup.service systemd/unifi-backup.timer systemd/unifi-backup-monitor.service systemd/unifi-backup-monitor.timer; do
  [[ -f $source_dir/$required ]] || die "incomplete source tree; missing $required" 66
done
for script in "$source_dir/bin/unifi-backup" "$source_dir/bin/unifi-mail-backup" "$source_dir/bin/unifi-backup-check" "$source_dir/bin/unifi-backup-upload" "$source_dir/bin/unifi-backup-notify" "$source_dir/bin/unifi-backup-status" "$source_dir/bin/unifi-backup-monitor" "$source_dir/bin/unifi-backup-catalog" "$source_dir/lib/unifi-backup-common.sh"; do
  bash -n "$script" || die "Bash syntax validation failed: $script" 65
done

log "Installing executables and systemd units"
for module in core verify storage replication retry_queue policy retention recovery anomaly config_diff cli config_schema config_files config_model config_transaction config_ui configure; do
  [[ -f $source_dir/lib/ub/$module.py ]] || die "Missing data module: $module" 66
done
bash -n "$source_dir/lib/unifi-backup-runtime.sh"
install -d -o root -g root -m 0755 /usr/local/sbin /etc/systemd/system
for helper in verify replicate remote-verify retry storage-policy retention restore analyze diff configure; do
  [[ -f $source_dir/bin/unifi-backup-$helper ]] || die "Missing helper: $helper" 66
  bash -n "$source_dir/bin/unifi-backup-$helper"
  install -o root -g root -m 0755 "$source_dir/bin/unifi-backup-$helper" "/usr/local/sbin/unifi-backup-$helper"
done
install -d -o root -g root -m 0755 /usr/local/lib/unifi-backup/ub
install -o root -g root -m 0644 "$source_dir/lib/unifi-backup-runtime.sh" /usr/local/lib/unifi-backup/unifi-backup-runtime.sh
install -o root -g root -m 0644 "$source_dir/lib/ub/"*.py /usr/local/lib/unifi-backup/ub/
for extra in verify remote-verify retry; do
  install -o root -g root -m 0644 "$source_dir/systemd/unifi-backup-$extra.service" "$source_dir/systemd/unifi-backup-$extra.timer" /etc/systemd/system/
done
install -d -o root -g root -m 0700 /etc/unifi-backup/targets.d
if [[ ! -e /etc/unifi-backup/targets.d/target.env.example ]]; then
  install -o root -g root -m 0600 "$source_dir/config/target.env.example" /etc/unifi-backup/targets.d/target.env.example
fi
install -o root -g root -m 0755 "$source_dir/bin/unifi-backup" /usr/local/sbin/unifi-backup
install -o root -g root -m 0755 "$source_dir/bin/unifi-mail-backup" /usr/local/sbin/unifi-mail-backup
install -o root -g root -m 0755 "$source_dir/bin/unifi-backup-check" /usr/local/sbin/unifi-backup-check
install -o root -g root -m 0755 "$source_dir/bin/unifi-backup-upload" /usr/local/sbin/unifi-backup-upload
install -o root -g root -m 0755 "$source_dir/bin/unifi-backup-notify" /usr/local/sbin/unifi-backup-notify
install -o root -g root -m 0755 "$source_dir/bin/unifi-backup-status" /usr/local/sbin/unifi-backup-status
install -o root -g root -m 0755 "$source_dir/bin/unifi-backup-monitor" /usr/local/sbin/unifi-backup-monitor
install -o root -g root -m 0755 "$source_dir/bin/unifi-backup-catalog" /usr/local/sbin/unifi-backup-catalog
install -d -o root -g root -m 0755 /usr/local/lib/unifi-backup
install -o root -g root -m 0644 "$source_dir/lib/unifi-backup-common.sh" /usr/local/lib/unifi-backup/common.sh
install -o root -g root -m 0644 "$source_dir/systemd/unifi-backup.service" /etc/systemd/system/unifi-backup.service
install -o root -g root -m 0644 "$source_dir/systemd/unifi-backup.timer" /etc/systemd/system/unifi-backup.timer
install -o root -g root -m 0644 "$source_dir/systemd/unifi-backup-monitor.service" /etc/systemd/system/unifi-backup-monitor.service
install -o root -g root -m 0644 "$source_dir/systemd/unifi-backup-monitor.timer" /etc/systemd/system/unifi-backup-monitor.timer

install -d -o root -g root -m 0700 /etc/unifi-backup
[[ ! -L /etc/unifi-backup/.configure.lock ]] || die "unsafe configuration lock symlink" 78
if [[ ! -e /etc/unifi-backup/.configure.lock ]]; then
  install -o root -g root -m 0600 /dev/null /etc/unifi-backup/.configure.lock
fi
install -d -o root -g root -m 0700 /var/backups/unifi
install -d -o root -g root -m 0755 /var/lib/unifi-backup
if [[ ! -e /etc/unifi-backup/unifi-backup.env ]]; then
  install -o root -g root -m 0600 "$source_dir/config/unifi-backup.env.example" /etc/unifi-backup/unifi-backup.env
  log "Created /etc/unifi-backup/unifi-backup.env; replace the placeholders before the first run"
else
  log "Preserved existing /etc/unifi-backup/unifi-backup.env"
fi
if [[ ! -e /etc/unifi-backup/graph.env ]]; then
  install -o root -g root -m 0600 "$source_dir/config/graph.env.example" /etc/unifi-backup/graph.env
  log "Created optional /etc/unifi-backup/graph.env with placeholders"
else
  log "Preserved existing /etc/unifi-backup/graph.env"
fi
if [[ ! -e /etc/unifi-backup/storage.env ]]; then
  install -o root -g root -m 0600 "$source_dir/config/storage.env.example" /etc/unifi-backup/storage.env
  log "Created optional /etc/unifi-backup/storage.env with placeholders"
else
  log "Preserved existing /etc/unifi-backup/storage.env"
fi
if [[ ! -e /etc/unifi-backup/ntfy.env ]]; then
  install -o root -g root -m 0600 "$source_dir/config/ntfy.env.example" /etc/unifi-backup/ntfy.env
  log "Created optional /etc/unifi-backup/ntfy.env with placeholders"
else
  log "Preserved existing /etc/unifi-backup/ntfy.env"
fi
if [[ ! -e /etc/unifi-backup/webhook.env ]]; then
  install -o root -g root -m 0600 "$source_dir/config/webhook.env.example" /etc/unifi-backup/webhook.env
  log "Created optional /etc/unifi-backup/webhook.env with placeholders"
else
  log "Preserved existing /etc/unifi-backup/webhook.env"
fi
if [[ ! -e /etc/unifi-backup/age-recipients.txt ]]; then
  install -o root -g root -m 0600 "$source_dir/config/age-recipients.txt.example" /etc/unifi-backup/age-recipients.txt
  log "Created optional /etc/unifi-backup/age-recipients.txt placeholder"
else
  log "Preserved existing /etc/unifi-backup/age-recipients.txt"
fi
chown root:root /etc/unifi-backup /etc/unifi-backup/unifi-backup.env /etc/unifi-backup/graph.env /etc/unifi-backup/storage.env /etc/unifi-backup/ntfy.env /etc/unifi-backup/webhook.env /etc/unifi-backup/age-recipients.txt /var/backups/unifi /var/lib/unifi-backup
chmod 0700 /etc/unifi-backup /var/backups/unifi
chmod 0755 /var/lib/unifi-backup
chmod 0600 /etc/unifi-backup/unifi-backup.env /etc/unifi-backup/graph.env /etc/unifi-backup/storage.env /etc/unifi-backup/ntfy.env /etc/unifi-backup/webhook.env /etc/unifi-backup/age-recipients.txt

systemctl daemon-reload
if [[ $ENABLE_TIMER == "true" ]]; then
  systemctl enable unifi-backup.timer
  systemctl enable unifi-backup-monitor.timer
  log "Enabled backup and freshness-monitor timers (they are not started until configuration is validated)"
else
  log "Timer installation completed without enabling it"
fi

cat <<'EOF'

Installation complete.
  1. Run: sudo unifi-backup-configure
     Or retain the documented manual configuration workflow.
  2. Validate without network: sudo unifi-backup-configure --validate
     Optional explicit login test: sudo unifi-backup-check --live
  3. Run: sudo systemctl start unifi-backup.service
  4. Start scheduling: sudo systemctl start unifi-backup.timer
  5. Start freshness checks: sudo systemctl start unifi-backup-monitor.timer
EOF
if [[ $CONFIGURE == true ]]; then
  /usr/local/sbin/unifi-backup-configure --guided
fi
