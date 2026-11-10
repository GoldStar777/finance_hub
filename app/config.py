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

# Default port
DEFAULT_PORT = int(os.getenv("APP_PORT", "8050"))
