#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

PROGRAM="unifi-os-backup installer"
INSTALL_DIR="/opt/unifi-os-backup"
REPOSITORY_URL=""
ENABLE_TIMER=true

usage() {
  cat <<'EOF'
Usage: sudo ./install.sh [--repository-url HTTPS_GIT_URL] [--install-dir DIR] [--no-enable]

From a complete checkout, files are installed from that checkout. When only this
bootstrap script was downloaded, --repository-url is required and Git clones the
repository into /opt/unifi-os-backup.
EOF
}

while (($#)); do
  case "$1" in
    --repository-url) [[ $# -ge 2 ]] || { usage >&2; exit 64; }; REPOSITORY_URL=$2; shift 2 ;;
    --install-dir) [[ $# -ge 2 ]] || { usage >&2; exit 64; }; INSTALL_DIR=$2; shift 2 ;;
    --no-enable) ENABLE_TIMER=false; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "$PROGRAM: unknown option: $1" >&2; exit 64 ;;
  esac
done

log() { printf '%s: %s\n' "$PROGRAM" "$*"; }
die() { printf '%s: ERROR: %s\n' "$PROGRAM" "$*" >&2; exit "${2:-1}"; }
(( EUID == 0 )) || die "run this installer as root (sudo ./install.sh)" 77
[[ $INSTALL_DIR == /* && $INSTALL_DIR != "/" ]] || die "--install-dir must be an absolute, non-root path" 64

for command_name in bash curl python3 sha256sum find stat flock systemctl install; do
  command -v "$command_name" >/dev/null 2>&1 || die "missing dependency: $command_name" 69
done

script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
source_dir=$script_dir
if [[ ! -f $source_dir/bin/unifi-backup || ! -f $source_dir/systemd/unifi-backup.service ]]; then
  [[ -n $REPOSITORY_URL ]] || die "standalone bootstrap mode requires --repository-url" 64
  [[ $REPOSITORY_URL =~ ^https://[^[:space:]]+\.git$ ]] || die "repository URL must be an HTTPS .git URL" 64
  [[ $REPOSITORY_URL != *"@"* && $REPOSITORY_URL != *"?"* && $REPOSITORY_URL != *"#"* ]] || die "repository URL must not contain credentials, a query, or a fragment" 64
  command -v git >/dev/null 2>&1 || die "Git is required for bootstrap mode. Install it explicitly (apt-get install git) and retry." 69
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
  1. Edit /etc/unifi-backup/unifi-backup.env
  2. Run: sudo unifi-backup-check --live
  3. Run: sudo systemctl start unifi-backup.service
  4. Start scheduling: sudo systemctl start unifi-backup.timer
  5. Start freshness checks: sudo systemctl start unifi-backup-monitor.timer
EOF
