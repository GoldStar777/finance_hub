# Finance Hub

Finance Hub is a local-first, single-user personal finance application powered by **FastAPI**, **SQLite**, and **Vue 3**. It binds exclusively to `127.0.0.1`, stores all ledgers, profiles, receipts, and backups on your machine inside `./data`, and makes no external network calls.

---

## Core Capabilities & Local Data Model

- **Integer Minor-Unit Precision**: Monetary values are stored in integer minor units (for example, `amount_pence`) rather than floating-point numbers.
- **Profile-Isolated Workspaces**: Switch between independent financial workspaces (such as personal and shared accounts). Each profile uses its own SQLite database (`PRAGMA journal_mode = WAL`, `PRAGMA foreign_keys = ON`), receipt store, staging folder, and backup archive directory.
- **Ledger, Transfers & Reconciliation**: Track manual, repeat-occurrence, and imported transactions across Current, Savings, Cash, Credit Card, and Investment accounts, with time-aware balance anchors, reconciliation, split expenses, soft-delete recovery, and CSV/filtered exports.
- **Separate Income & Expense Categories**: Explicitly separate `INCOME` and `EXPENSE` categories across entry forms, imports, bulk edits, analysis, and review.
- **Analysis & Data Quality Review**: Filter cash flow, net worth, spending breakdowns, and holdings across shared **Period** and **Filters** toolbars, and review uncategorized items, potential duplicates, unpaired transfers, uncertain imports, and archived links.
- **Offline Receipt & Statement Import**: Stage CSV/XLSX statements (no cloud parsing) and image receipts, with confidence thresholds and explainable local suggestions.

---

## Supported Platforms & Prerequisites

### Prerequisites
- **Python**: `3.10+` with `venv` support (`python3 -m venv`)
- **Node.js & npm**: Node.js `18+` and `npm`
- **Git**: for cloning/updating the repository

### Platform Support

| Platform | Runtime & UI | Background Service Script | Image Receipt OCR |
| :--- | :--- | :--- | :--- |
| **macOS** | Fully supported | `launchd` LaunchAgent (`com.financehub.app`) | **Apple Vision** offline OCR (`pyobjc-framework-*` installed only on macOS) |
| **Linux** | Fully supported | `systemd --user` (`financehub.service`, when user systemd session is active) or foreground | **Manual entry fallback** (`FallbackReceiptParser`); CSV/XLSX imports work identically |
| **Other POSIX / Windows** | Supported manually in foreground (`python run.py` after `npm run build`) | Manual foreground start (`scripts/*.sh` require Bash/POSIX) | Manual entry fallback |

> [!NOTE]
> `requirements.txt` gates `pyobjc-*` packages with `; sys_platform == "darwin"` so `pip install -r requirements.txt` succeeds cleanly on Linux and other non-macOS systems.

---

## Quick Install

Clone the repository and preview or run the idempotent installer:

```bash
git clone <repository-url> finance_hub
cd finance_hub

# 1. Preview every check, path, and command without changing anything
./scripts/install.sh --dry-run

# 2. Install Python dependencies (./venv), build the frontend, and register the user service
./scripts/install.sh
```

Useful installer options:
- `./scripts/install.sh --no-service` — Install `./venv` and build `frontend/dist` without registering `launchd` or `systemd`.
- `./scripts/install.sh --port 8060` — Register the user service with `APP_PORT=8060`.
- `./scripts/install.sh --python /path/to/python3.12` — Select a specific Python 3.10+ interpreter.

Once running, open **[http://127.0.0.1:8050](http://127.0.0.1:8050)** (or your configured `APP_PORT`). Interactive API docs are served locally at `/docs`.

---

## Manual Setup (All Platforms)

```bash
# 1. Create virtual environment and install Python dependencies
python3 -m venv venv
./venv/bin/python -m pip install -r requirements.txt

# 2. Install frontend dependencies and build production SPA
cd frontend
npm ci
npm run build
cd ..

# 3. (Optional) Customize environment variables
cp .env.example .env

# 4. Run Finance Hub locally on http://127.0.0.1:8050
./venv/bin/python run.py
```

`run.py` automatically builds `frontend/dist` if missing, verifies `127.0.0.1:$APP_PORT` is unused before binding, initializes SQLite tables safely, and starts Uvicorn bound to `127.0.0.1`.

---

## Storage Layout (`./data`)

All user financial records stay out of version control inside `./data`:

```text
data/
├── finances.db                 # Default profile SQLite database (+ -wal/-shm during active runs)
├── profiles.json               # Workspace profile registry
├── receipts/                   # Approved archived receipts (default profile)
├── staging_receipts/           # Pending staged uploads/receipts (default profile)
├── backups/                    # Default profile ZIP backups (unless BACKUP_DIR is set)
├── app.log                     # Service stdout log (when run via registered user service)
├── app_error.log               # Service stderr log (when run via registered user service)
└── profiles/
    └── <profile_id>/           # Isolated directory per non-default profile
        ├── finances.db
        ├── receipts/
        ├── staging_receipts/
        └── backups/
```

---

## Configuration

Copy [`.env.example`](.env.example) to `.env` to override defaults (`app/config.py` loads `.env` with `override=False`, so explicit process or service environment variables always take precedence):

| Setting | Default | Scope | Notes |
| :--- | :--- | :--- | :--- |
| `APP_PORT` | `8050` | Process | Localhost port on `127.0.0.1`. |
| `BASE_CURRENCY` | `GBP` | First DB init | 3-letter ISO 4217 code (e.g., `GBP`, `USD`, `EUR`, `CAD`, `AUD`, `CHF`, `INR`). Stored in SQLite `system_settings`; if an already-initialized database has a different stored base currency, startup intentionally fails fast rather than re-labeling existing monetary amounts. |
| `BACKUP_DIR` | `./data/backups` | Default profile | Optional custom directory for the default profile's backup ZIP archives. Non-default profiles always write backups to `./data/profiles/<id>/backups`. |
| `app_timezone` (SQLite) | `Europe/London` | Per profile | IANA timezone stored in `system_settings` under key `app_timezone`, used for local calendar boundaries, daily windows, and balance anchors. |

### Background Service Management

#### macOS (`launchd`)
`./scripts/install.sh` registers `com.financehub.app` at `~/Library/LaunchAgents/com.financehub.app.plist`.

```bash
# Restart after frontend rebuild or backend update
launchctl kickstart -k "gui/$(id -u)/com.financehub.app"

# Inspect logs
tail -f data/app.log data/app_error.log
```

#### Linux (`systemd --user`)
When `systemctl --user` is active, `./scripts/install.sh` registers `~/.config/systemd/user/financehub.service` (or `${XDG_CONFIG_HOME}/systemd/user/financehub.service`).

```bash
systemctl --user status financehub.service
systemctl --user restart financehub.service
journalctl --user -u financehub.service -f
```

---

## Backup & Restore

### Creating & Downloading Backups
- Trigger an on-demand backup from the UI (**Backup Now**) or `POST /api/system/backup`.
- Each ZIP archive bundles the target profile's SQLite database (`sqlite3` online backup + WAL checkpoint consistency), receipt directories, and a SHA-256 manifest.
- Download archives from the UI or `GET /api/system/backups/{filename}/download`.

### Restoring from a Backup Archive
Stop Finance Hub before running the offline restore utility (`app/restore.py`):

```bash
# macOS (if using LaunchAgent)
launchctl bootout "gui/$(id -u)/com.financehub.app"

# Linux (if using systemd user service)
systemctl --user stop financehub.service

# Restore into the default profile (verified with SQLite PRAGMA integrity_check;
# automatically saves a pre-restore rollback copy first)
./venv/bin/python -m app.restore path/to/finance_hub_backup_YYYYMMDD_HHMMSS.zip

# Or restore into a specific profile by ID or name
./venv/bin/python -m app.restore path/to/backup.zip --profile "Shared Household"
```

After restore completes, restart the service (`launchctl bootstrap "gui/$(id -u)" "$HOME/Library/LaunchAgents/com.financehub.app.plist"` on macOS, `systemctl --user start financehub.service` on Linux, or `./venv/bin/python run.py`).

---

## Updating Without Losing Data

Upgrading preserves `./data` and `./.env` untouched:

```bash
git pull --ff-only
./scripts/install.sh
```

If doing a manual update:

```bash
./venv/bin/python -m pip install -r requirements.txt
cd frontend && npm ci && npm run build && cd ..
```

Existing SQLite tables receive additive runtime columns/indexes on startup (`app/database.py`), and Alembic migrations live under `alembic/` (`./venv/bin/alembic upgrade head` targets `sqlite:///data/finances.db` per `alembic.ini`).

---

## Safe Uninstallation

By default, `./scripts/uninstall.sh` removes only the registered background service (`com.financehub.app` / `financehub.service`) and generated build artifacts (`./venv`, `frontend/node_modules`, `frontend/dist`) while **keeping `./data` and `./.env` intact**:

```bash
# Preview what will be removed and what will be preserved
./scripts/uninstall.sh --dry-run

# Remove service + generated dependencies/build artifacts, preserving ./data and ./.env
./scripts/uninstall.sh

# Remove only the background service (keep ./venv and frontend build/dependencies)
./scripts/uninstall.sh --keep-deps
```

To permanently delete `./data` (SQLite databases, profiles, receipts, and backups inside `./data`), you must pass `--purge-data` and confirm interactively (or pair with `--yes` for non-interactive automation). Any custom `BACKUP_DIR` outside `./data` is never modified or deleted automatically.

```bash
./scripts/uninstall.sh --dry-run --purge-data   # Preview exact paths first
./scripts/uninstall.sh --purge-data             # Prompts for exact DELETE DATA confirmation
```

---

## Development, Testing & Building

```bash
# Backend test suite (runs against isolated temporary databases; never touches ./data)
./venv/bin/pytest

# Frontend unit/contract tests
npm --prefix frontend test

# Production frontend typecheck + bundle
npm --prefix frontend run build
```

For hot-reloading UI development alongside the FastAPI backend:

```bash
# Terminal 1: backend API with auto-reload
./venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8050 --reload

# Terminal 2: Vite dev server (http://127.0.0.1:5173)
npm --prefix frontend run dev
```

Note: When serving the production bundle through `run.py`, frontend edits require running `npm --prefix frontend run build` and restarting the app/service.

---

## Privacy Notes & Known Limitations

- **Offline-Only Execution**: No third-party analytics, cloud LLMs, external currency APIs, or telemetry are compiled into or invoked by Finance Hub. Network listeners bind strictly to `127.0.0.1`.
- **Encryption at Rest**: SQLite databases and receipt files inside `./data` are stored unencrypted on your local filesystem. Rely on full-disk encryption (such as FileVault on macOS or LUKS on Linux) and OS user permissions to protect data at rest.
- **Single-User Design**: There is no built-in username/password authentication layer because the server is intended solely for local single-machine access on `127.0.0.1`. Do not expose the application port directly to untrusted networks or a public reverse proxy without adding external authentication and TLS.
- **Platform OCR Difference**: Automatic image receipt text extraction requires macOS Apple Vision (`pyobjc-framework-Vision`, `pyobjc-framework-Quartz`). On Linux and other platforms, image receipts are staged for manual field entry while CSV/XLSX statement imports operate identically.
- **Immutable Initialized Base Currency**: `BASE_CURRENCY` must be chosen before initializing a database and cannot be changed via `.env` afterward without creating a mismatch error.
