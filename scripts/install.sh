#!/usr/bin/env bash
set -euo pipefail

# Finance Hub idempotent installer & non-destructive upgrader.
# Supports macOS (launchd LaunchAgent) and Linux (systemd user service or foreground).

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
DATA_DIR="${PROJECT_DIR}/data"
VENV_DIR="${PROJECT_DIR}/venv"
FRONTEND_DIR="${PROJECT_DIR}/frontend"
REQ_FILE="${PROJECT_DIR}/requirements.txt"

SERVICE_LABEL="com.financehub.app"
SYSTEMD_UNIT="financehub.service"

DRY_RUN=0
NO_SERVICE=0
CUSTOM_PORT=""
PYTHON_BIN="${PYTHON_BIN:-python3}"

usage() {
  cat <<'EOF'
Usage: ./scripts/install.sh [OPTIONS]

Idempotently installs or upgrades Finance Hub dependencies, builds the frontend,
and optionally registers a background user service without modifying ./data.

Options:
  --dry-run        Preview all checks, paths, and actions without making changes
  --no-service     Skip macOS launchd / Linux systemd user service registration
  --port PORT      Set APP_PORT in the registered service (1-65535)
  --python PATH    Python 3.10+ executable to create/use ./venv (default: python3)
  -h, --help       Show this help message
EOF
}

log_info() {
  printf '[INFO] %s\n' "$1"
}

log_dry() {
  printf '[DRY-RUN] %s\n' "$1"
}

log_warn() {
  printf '[WARN] %s\n' "$1" >&2
}

log_err() {
  printf '[ERROR] %s\n' "$1" >&2
}

xml_escape() {
  local s="$1"
  s="${s//&/&amp;}"
  s="${s//</&lt;}"
  s="${s//>/&gt;}"
  s="${s//\"/&quot;}"
  s="${s//\'/&apos;}"
  printf '%s' "$s"
}

run_or_preview() {
  if [[ "${DRY_RUN}" -eq 1 ]]; then
    log_dry "Would run: $*"
  else
    "$@"
  fi
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    --no-service)
      NO_SERVICE=1
      shift
      ;;
    --port)
      if [[ $# -lt 2 ]]; then
        log_err "--port requires a numeric argument."
        exit 2
      fi
      CUSTOM_PORT="$2"
      shift 2
      ;;
    --python)
      if [[ $# -lt 2 ]]; then
        log_err "--python requires a binary path argument."
        exit 2
      fi
      PYTHON_BIN="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      log_err "Unknown option: $1"
      usage >&2
      exit 2
      ;;
  esac
done

if [[ -n "${CUSTOM_PORT}" ]]; then
  if ! [[ "${CUSTOM_PORT}" =~ ^[0-9]+$ ]] || [[ "${CUSTOM_PORT}" -lt 1 ]] || [[ "${CUSTOM_PORT}" -gt 65535 ]]; then
    log_err "Invalid port '${CUSTOM_PORT}'. Expected an integer between 1 and 65535."
    exit 2
  fi
fi

UNAME_S="$(uname -s)"
case "${UNAME_S}" in
  Darwin)
    OS_KIND="macos"
    PLIST_DIR="${HOME}/Library/LaunchAgents"
    SERVICE_FILE="${PLIST_DIR}/${SERVICE_LABEL}.plist"
    ;;
  Linux)
    OS_KIND="linux"
    SYSTEMD_DIR="${XDG_CONFIG_HOME:-${HOME}/.config}/systemd/user"
    SERVICE_FILE="${SYSTEMD_DIR}/${SYSTEMD_UNIT}"
    ;;
  *)
    OS_KIND="other"
    SERVICE_FILE=""
    ;;
esac

log_info "Finance Hub installer (OS=${OS_KIND}, project=${PROJECT_DIR})"
log_info "User data directory will be preserved untouched: ${DATA_DIR}"

# 1. Prerequisite verification
if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
  log_err "Python executable '${PYTHON_BIN}' not found on PATH. Install Python 3.10+ first."
  exit 1
fi

if ! "${PYTHON_BIN}" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)'; then
  PY_VER="$("${PYTHON_BIN}" -c 'import sys; print(".".join(map(str, sys.version_info[:3])))' 2>/dev/null || echo 'unknown')"
  log_err "Python 3.10+ is required (found ${PY_VER})."
  exit 1
fi

if ! "${PYTHON_BIN}" -c 'import venv' >/dev/null 2>&1; then
  log_err "Python 'venv' module is unavailable. On Debian/Ubuntu install python3-venv."
  exit 1
fi

if ! command -v node >/dev/null 2>&1; then
  log_err "Node.js 18+ not found on PATH. Install Node.js before running install.sh."
  exit 1
fi

if ! node -e 'const maj = parseInt((process.versions.node || "0").split(".")[0], 10); process.exit(maj >= 18 ? 0 : 1);'; then
  NODE_VER="$(node -v 2>/dev/null || echo 'unknown')"
  log_err "Node.js 18+ is required (found ${NODE_VER})."
  exit 1
fi

if ! command -v npm >/dev/null 2>&1; then
  log_err "npm not found on PATH. Install Node.js/npm before running install.sh."
  exit 1
fi

if [[ ! -f "${REQ_FILE}" ]]; then
  log_err "Missing requirements.txt at ${REQ_FILE}."
  exit 1
fi

if [[ ! -f "${FRONTEND_DIR}/package.json" ]]; then
  log_err "Missing frontend/package.json at ${FRONTEND_DIR}/package.json."
  exit 1
fi

# 2. Ensure non-destructive data directories exist
for d in "${DATA_DIR}" "${DATA_DIR}/backups" "${DATA_DIR}/receipts" "${DATA_DIR}/staging_receipts"; do
  if [[ -d "${d}" ]]; then
    log_info "Preserving existing directory: ${d}"
  else
    run_or_preview mkdir -p "${d}"
  fi
done

# 3. Create or update Python virtual environment
VENV_PYTHON="${VENV_DIR}/bin/python"
if [[ -x "${VENV_PYTHON}" ]]; then
  log_info "Reusing existing virtual environment: ${VENV_DIR}"
else
  run_or_preview "${PYTHON_BIN}" -m venv "${VENV_DIR}"
fi

run_or_preview "${VENV_PYTHON}" -m pip install -r "${REQ_FILE}"

# 4. Install frontend dependencies & build production SPA
if [[ -f "${FRONTEND_DIR}/package-lock.json" ]]; then
  NPM_INSTALL_CMD="ci"
else
  NPM_INSTALL_CMD="install"
fi

if [[ "${DRY_RUN}" -eq 1 ]]; then
  log_dry "Would run in ${FRONTEND_DIR}: npm ${NPM_INSTALL_CMD}"
  log_dry "Would run in ${FRONTEND_DIR}: npm run build"
else
  (
    cd "${FRONTEND_DIR}"
    npm "${NPM_INSTALL_CMD}"
    npm run build
  )
fi

# 5. Optional .env guidance
if [[ ! -f "${PROJECT_DIR}/.env" ]] && [[ -f "${PROJECT_DIR}/.env.example" ]]; then
  log_info "Optional configuration: copy ${PROJECT_DIR}/.env.example to ${PROJECT_DIR}/.env if you wish to customize APP_PORT, BASE_CURRENCY, or BACKUP_DIR."
fi

# 6. Register background user service (unless --no-service)
if [[ "${NO_SERVICE}" -eq 1 ]]; then
  log_info "Skipping background service setup (--no-service). Start manually with: ${VENV_PYTHON} ${PROJECT_DIR}/run.py"
  exit 0
fi

install_macos_service() {
  local uid_val
  uid_val="$(id -u)"

  if [[ "${DRY_RUN}" -eq 1 ]]; then
    log_dry "Would ensure directory exists: ${PLIST_DIR}"
    log_dry "Would bootout existing ${SERVICE_LABEL} if loaded: launchctl bootout gui/${uid_val}/${SERVICE_LABEL}"
    log_dry "Would write LaunchAgent plist (${SERVICE_LABEL}) to: ${SERVICE_FILE}"
    log_dry "  Program: ${VENV_PYTHON} ${PROJECT_DIR}/run.py"
    log_dry "  WorkingDirectory: ${PROJECT_DIR}"
    if [[ -n "${CUSTOM_PORT}" ]]; then
      log_dry "  APP_PORT: ${CUSTOM_PORT}"
    fi
    log_dry "Would run: launchctl bootstrap gui/${uid_val} ${SERVICE_FILE}"
    log_dry "Would run: launchctl kickstart -k gui/${uid_val}/${SERVICE_LABEL}"
    return 0
  fi

  mkdir -p "${PLIST_DIR}"
  local esc_label esc_py esc_run esc_proj esc_out esc_err esc_port_block
  esc_label="$(xml_escape "${SERVICE_LABEL}")"
  esc_py="$(xml_escape "${VENV_PYTHON}")"
  esc_run="$(xml_escape "${PROJECT_DIR}/run.py")"
  esc_proj="$(xml_escape "${PROJECT_DIR}")"
  esc_out="$(xml_escape "${DATA_DIR}/app.log")"
  esc_err="$(xml_escape "${DATA_DIR}/app_error.log")"

  esc_port_block=""
  if [[ -n "${CUSTOM_PORT}" ]]; then
    esc_port_block=$'\n        <key>APP_PORT</key>\n        <string>'"$(xml_escape "${CUSTOM_PORT}")"'</string>'
  fi

  launchctl bootout "gui/${uid_val}/${SERVICE_LABEL}" >/dev/null 2>&1 || true

  cat > "${SERVICE_FILE}" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${esc_label}</string>
    <key>ProgramArguments</key>
    <array>
        <string>${esc_py}</string>
        <string>${esc_run}</string>
    </array>
    <key>WorkingDirectory</key>
    <string>${esc_proj}</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>${esc_port_block}
    </dict>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>${esc_out}</string>
    <key>StandardErrorPath</key>
    <string>${esc_err}</string>
</dict>
</plist>
EOF

  launchctl bootstrap "gui/${uid_val}" "${SERVICE_FILE}"
  launchctl kickstart -k "gui/${uid_val}/${SERVICE_LABEL}"
  log_info "Registered and started macOS LaunchAgent: ${SERVICE_FILE}"
}

install_linux_service() {
  local env_line=""
  if [[ -n "${CUSTOM_PORT}" ]]; then
    env_line="Environment=APP_PORT=${CUSTOM_PORT}"
  fi

  if [[ "${DRY_RUN}" -eq 1 ]]; then
    log_dry "Would ensure directory exists: ${SYSTEMD_DIR}"
    log_dry "Would write systemd user unit (${SYSTEMD_UNIT}) to: ${SERVICE_FILE}"
    log_dry "  ExecStart=${VENV_PYTHON} ${PROJECT_DIR}/run.py"
    log_dry "  WorkingDirectory=${PROJECT_DIR}"
    if [[ -n "${CUSTOM_PORT}" ]]; then
      log_dry "  APP_PORT=${CUSTOM_PORT}"
    fi
    log_dry "Would enable/start ${SYSTEMD_UNIT} via systemctl --user if active"
    return 0
  fi

  mkdir -p "${SYSTEMD_DIR}"
  cat > "${SERVICE_FILE}" <<EOF
[Unit]
Description=Finance Hub Personal Finance Server
After=network.target

[Service]
Type=simple
WorkingDirectory=${PROJECT_DIR}
${env_line:+${env_line}
}ExecStart=${VENV_PYTHON} ${PROJECT_DIR}/run.py
Restart=on-failure
RestartSec=5
StandardOutput=append:${DATA_DIR}/app.log
StandardError=append:${DATA_DIR}/app_error.log

[Install]
WantedBy=default.target
EOF

  if command -v systemctl >/dev/null 2>&1 && systemctl --user status >/dev/null 2>&1; then
    systemctl --user daemon-reload
    systemctl --user enable --now "${SYSTEMD_UNIT}"
    systemctl --user restart "${SYSTEMD_UNIT}"
    log_info "Registered and started systemd user service: ${SERVICE_FILE}"
  else
    log_warn "Wrote systemd user unit to ${SERVICE_FILE}, but no active systemd --user session was detected."
    log_info "Start Finance Hub in the foreground with: ${VENV_PYTHON} ${PROJECT_DIR}/run.py"
  fi
}

case "${OS_KIND}" in
  macos)
    install_macos_service
    ;;
  linux)
    install_linux_service
    ;;
  *)
    log_warn "Background service setup is not automated on '${UNAME_S}'."
    log_info "Start Finance Hub manually with: ${VENV_PYTHON} ${PROJECT_DIR}/run.py"
    ;;
esac

log_info "Install/upgrade complete. Open http://127.0.0.1:${CUSTOM_PORT:-8050} once running."
