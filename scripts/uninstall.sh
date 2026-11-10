#!/usr/bin/env bash
set -euo pipefail

# Finance Hub safe uninstaller.
# Preserves user financial data (./data and ./.env) by default.
# Requires --purge-data (plus confirmation unless paired with --yes) to remove ./data.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
DATA_DIR="${PROJECT_DIR}/data"
VENV_DIR="${PROJECT_DIR}/venv"
FRONTEND_NODE_MODULES="${PROJECT_DIR}/frontend/node_modules"
FRONTEND_DIST="${PROJECT_DIR}/frontend/dist"
ENV_FILE="${PROJECT_DIR}/.env"

SERVICE_LABEL="com.financehub.app"
SYSTEMD_UNIT="financehub.service"

DRY_RUN=0
PURGE_DATA=0
ASSUME_YES=0
KEEP_DEPS=0

usage() {
  cat <<'EOF'
Usage: ./scripts/uninstall.sh [OPTIONS]

Removes Finance Hub's registered background service and generated build/runtime
directories (./venv, frontend/node_modules, frontend/dist) while preserving ./data
and .env by default.

Options:
  --dry-run      Preview everything that would be removed or preserved without modifying disk
  --keep-deps    Only remove the background service; keep ./venv and frontend build/deps
  --purge-data   Also delete ./data (SQLite databases, profiles, receipts, backups).
                 Prompts for explicit confirmation unless --yes is also supplied.
  --yes          Skip interactive confirmation for --purge-data (has NO effect without --purge-data)
  -h, --help     Show this help message
EOF
}

log_info() {
  printf '[INFO] %s\n' "$1"
}

log_keep() {
  printf '[KEEP] %s\n' "$1"
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

preview_purge_contents() {
  local prefix="$1"
  if [[ ! -e "${DATA_DIR}" ]]; then
    printf '%s User data directory does not exist (nothing to purge): %s\n' "${prefix}" "${DATA_DIR}"
    return 0
  fi

  local size_str db_count zip_count total_files
  size_str="$(du -sh "${DATA_DIR}" 2>/dev/null | awk '{print $1}' || echo 'unknown')"
  db_count="$(find "${DATA_DIR}" -type f -name '*.db' 2>/dev/null | wc -l | tr -d ' ')"
  zip_count="$(find "${DATA_DIR}" -type f -name '*.zip' 2>/dev/null | wc -l | tr -d ' ')"
  total_files="$(find "${DATA_DIR}" -type f 2>/dev/null | wc -l | tr -d ' ')"

  printf '%s Purge scope inside %s (total size: %s, files: %s, SQLite DBs: %s, backup ZIPs: %s):\n' \
    "${prefix}" "${DATA_DIR}" "${size_str}" "${total_files}" "${db_count}" "${zip_count}"

  if [[ "${total_files}" -gt 0 ]]; then
    local shown=0
    while IFS= read -r entry; do
      shown=$((shown + 1))
      if [[ "${shown}" -le 30 ]]; then
        printf '%s   - %s\n' "${prefix}" "${entry}"
      fi
    done < <(find "${DATA_DIR}" -mindepth 1 -maxdepth 4 2>/dev/null | sort)
    if [[ "${shown}" -gt 30 ]]; then
      printf '%s   ... and %s more path(s) inside %s\n' "${prefix}" "$((shown - 30))" "${DATA_DIR}"
    fi
  else
    printf '%s   - (empty directory tree inside %s)\n' "${prefix}" "${DATA_DIR}"
  fi
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    --purge-data)
      PURGE_DATA=1
      shift
      ;;
    --yes)
      ASSUME_YES=1
      shift
      ;;
    --keep-deps)
      KEEP_DEPS=1
      shift
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

UNAME_S="$(uname -s)"
case "${UNAME_S}" in
  Darwin)
    OS_KIND="macos"
    SERVICE_FILE="${HOME}/Library/LaunchAgents/${SERVICE_LABEL}.plist"
    ;;
  Linux)
    OS_KIND="linux"
    SERVICE_FILE="${XDG_CONFIG_HOME:-${HOME}/.config}/systemd/user/${SYSTEMD_UNIT}"
    ;;
  *)
    OS_KIND="other"
    SERVICE_FILE=""
    ;;
esac

if [[ "${PURGE_DATA}" -eq 1 ]] && [[ "${DRY_RUN}" -eq 0 ]] && [[ "${ASSUME_YES}" -eq 0 ]]; then
  printf '\n[WARNING] --purge-data will permanently delete all financial data in:\n'
  printf '  %s\n' "${DATA_DIR}"
  printf 'This includes SQLite databases, workspace profiles, archived/staged receipts, logs, and local backups inside ./data.\n'
  preview_purge_contents "[PURGE-PREVIEW]"
  printf '[KEEP] Local configuration (.env) and any custom BACKUP_DIR outside ./data will remain untouched.\n'
  if [[ -t 0 ]]; then
    printf 'Type DELETE DATA to confirm: '
    IFS= read -r confirm_reply || confirm_reply=""
  else
    log_err "Refusing non-interactive --purge-data without --yes."
    exit 1
  fi
  if [[ "${confirm_reply}" != "DELETE DATA" ]]; then
    log_err "Confirmation mismatch. Aborting uninstall before removing any data."
    exit 1
  fi
fi

log_info "Finance Hub uninstaller (OS=${OS_KIND}, project=${PROJECT_DIR})"

# 1. Stop and remove Finance Hub background service definition (if present)
remove_macos_service() {
  local uid_val
  uid_val="$(id -u)"
  if [[ "${DRY_RUN}" -eq 1 ]]; then
    log_dry "Would unload LaunchAgent if loaded: launchctl bootout gui/${uid_val}/${SERVICE_LABEL}"
    if [[ -e "${SERVICE_FILE}" ]]; then
      log_dry "Would remove LaunchAgent plist: ${SERVICE_FILE}"
    else
      log_info "LaunchAgent plist not present (nothing to remove): ${SERVICE_FILE}"
    fi
    return 0
  fi

  if command -v launchctl >/dev/null 2>&1; then
    launchctl bootout "gui/${uid_val}/${SERVICE_LABEL}" >/dev/null 2>&1 || true
  fi
  if [[ -e "${SERVICE_FILE}" ]]; then
    rm -f "${SERVICE_FILE}"
    log_info "Removed LaunchAgent plist: ${SERVICE_FILE}"
  else
    log_info "LaunchAgent plist not present: ${SERVICE_FILE}"
  fi
}

remove_linux_service() {
  if [[ "${DRY_RUN}" -eq 1 ]]; then
    log_dry "Would stop/disable ${SYSTEMD_UNIT} via systemctl --user if active"
    if [[ -e "${SERVICE_FILE}" ]]; then
      log_dry "Would remove systemd user unit: ${SERVICE_FILE}"
    else
      log_info "Systemd user unit not present (nothing to remove): ${SERVICE_FILE}"
    fi
    return 0
  fi

  if command -v systemctl >/dev/null 2>&1 && systemctl --user status >/dev/null 2>&1; then
    systemctl --user disable --now "${SYSTEMD_UNIT}" >/dev/null 2>&1 || true
    systemctl --user daemon-reload >/dev/null 2>&1 || true
  fi
  if [[ -e "${SERVICE_FILE}" ]]; then
    rm -f "${SERVICE_FILE}"
    log_info "Removed systemd user unit: ${SERVICE_FILE}"
  else
    log_info "Systemd user unit not present: ${SERVICE_FILE}"
  fi
}

case "${OS_KIND}" in
  macos)
    remove_macos_service
    ;;
  linux)
    remove_linux_service
    ;;
  *)
    log_info "No automated background service managed on '${UNAME_S}'."
    ;;
esac

# 2. Remove generated dependencies/build outputs unless --keep-deps
if [[ "${KEEP_DEPS}" -eq 1 ]]; then
  log_keep "Preserving runtime dependencies and build artifacts (--keep-deps)."
else
  for artifact_dir in "${VENV_DIR}" "${FRONTEND_NODE_MODULES}" "${FRONTEND_DIST}"; do
    if [[ -e "${artifact_dir}" ]]; then
      if [[ "${DRY_RUN}" -eq 1 ]]; then
        log_dry "Would remove generated artifact directory: ${artifact_dir}"
      else
        rm -rf "${artifact_dir}"
        log_info "Removed generated artifact directory: ${artifact_dir}"
      fi
    else
      log_info "Artifact directory not present: ${artifact_dir}"
    fi
  done
fi

# 3. Preserve or explicitly purge ./data
if [[ "${PURGE_DATA}" -eq 1 ]]; then
  if [[ -e "${DATA_DIR}" ]]; then
    if [[ "${DRY_RUN}" -eq 1 ]]; then
      log_dry "Would permanently delete user data directory (--purge-data): ${DATA_DIR}"
      preview_purge_contents "[DRY-RUN]"
    else
      rm -rf "${DATA_DIR}"
      log_info "Deleted user data directory (--purge-data): ${DATA_DIR}"
    fi
  else
    log_info "User data directory not present: ${DATA_DIR}"
  fi
else
  log_keep "User financial data preserved untouched: ${DATA_DIR} (pass --purge-data to remove)"
fi

if [[ -e "${ENV_FILE}" ]]; then
  log_keep "Local configuration file preserved untouched: ${ENV_FILE}"
fi

log_info "Note: Any custom BACKUP_DIR outside ${DATA_DIR} is never modified or deleted automatically."
log_info "Uninstall complete."
