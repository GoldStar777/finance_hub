import os
from pathlib import Path
from dotenv import load_dotenv

# Base project directory
BASE_DIR = Path(__file__).resolve().parent.parent

# Load optional local .env without overriding explicit process/service env vars
load_dotenv(BASE_DIR / ".env", override=False)

# Persistent storage directory
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

# Database path
DB_PATH = DATA_DIR / "finances.db"
DATABASE_URL = f"sqlite:///{DB_PATH}"

# Staging and archive receipt storage locations
STAGING_RECEIPTS_DIR = DATA_DIR / "staging_receipts"
STAGING_RECEIPTS_DIR.mkdir(parents=True, exist_ok=True)

ARCHIVE_RECEIPTS_DIR = DATA_DIR / "receipts"
ARCHIVE_RECEIPTS_DIR.mkdir(parents=True, exist_ok=True)

# Backward compatibility alias
RECEIPTS_DIR = STAGING_RECEIPTS_DIR

# Backup storage location
BACKUP_DIR = Path(os.getenv("BACKUP_DIR", str(DATA_DIR / "backups")))
BACKUP_DIR.mkdir(parents=True, exist_ok=True)

def _parse_app_port(raw_value: str) -> int:
    """Validates and parses APP_PORT in the valid TCP port range (1-65535)."""
    try:
        port = int(str(raw_value).strip())
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid APP_PORT '{raw_value}'. Expected an integer between 1 and 65535.") from exc
    if not (1 <= port <= 65535):
        raise ValueError(f"Invalid APP_PORT '{raw_value}'. Port must be between 1 and 65535.")
    return port


# Default port
DEFAULT_PORT = _parse_app_port(os.getenv("APP_PORT", "8050"))
