import threading
from pathlib import Path
from typing import Optional, Generator
from fastapi import Request, HTTPException, status
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import DATABASE_URL, DB_PATH

Base = declarative_base()

def configure_sqlite_engine(url: str) -> Engine:
    """Configures a SQLite engine with WAL mode and foreign key enforcement."""
    engine = create_engine(
        url,
        connect_args={"check_same_thread": False}
    )

    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys = ON;")
        cursor.execute("PRAGMA busy_timeout = 5000;")
        # WAL mode is not supported on in-memory databases (:memory:)
        if ":memory:" not in url and not url.endswith(":"):
            try:
                cursor.execute("PRAGMA journal_mode = WAL;")
            except Exception:
                pass

        # Ensure soft-delete & repeat-series provenance schema exists when opening existing DBs
        try:
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='transactions';")
            if cursor.fetchone():
                cursor.execute("PRAGMA table_info(transactions);")
                cols = {row[1] for row in cursor.fetchall()}
                if "deleted_at" not in cols:
                    cursor.execute("ALTER TABLE transactions ADD COLUMN deleted_at DATETIME;")
                if "deletion_batch_id" not in cols:
                    cursor.execute("ALTER TABLE transactions ADD COLUMN deletion_batch_id VARCHAR(50);")
                if "repeat_series_id" not in cols:
                    cursor.execute("ALTER TABLE transactions ADD COLUMN repeat_series_id VARCHAR(50);")
                cursor.execute(
                    "CREATE INDEX IF NOT EXISTS ix_transactions_repeat_series_id ON transactions (repeat_series_id);"
                )
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS repeat_series_batches (
                        id INTEGER PRIMARY KEY,
                        series_id VARCHAR(50) NOT NULL UNIQUE,
                        idempotency_key VARCHAR(128) NOT NULL UNIQUE,
                        request_hash VARCHAR(64) NOT NULL,
                        occurrence_count INTEGER NOT NULL,
                        transaction_ids_json TEXT NOT NULL,
                        created_at DATETIME NOT NULL
                    );
                """)

            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='categories';")
            if cursor.fetchone():
                cursor.execute("PRAGMA table_info(categories);")
                cat_cols = {row[1] for row in cursor.fetchall()}
                if "category_type" not in cat_cols:
                    cursor.execute(
                        "ALTER TABLE categories ADD COLUMN category_type VARCHAR(10) NOT NULL DEFAULT 'EXPENSE';"
                    )
                cursor.execute(
                    "UPDATE categories SET category_type = 'EXPENSE' "
                    "WHERE category_type IS NULL OR TRIM(category_type) = '';"
                )
        except Exception:
            pass

        cursor.close()

    return engine

class ProfileEngineRegistry:
    """
    Thread-safe registry managing per-profile SQLite database engines and sessionmakers.
    Ensures concurrency isolation without mutable process-wide globals.
    """
    def __init__(self):
        self._engines: dict[str, Engine] = {}
        self._sessionmakers: dict[str, sessionmaker] = {}
        self._lock = threading.Lock()

    def get_engine(self, profile_id: str) -> Engine:
        with self._lock:
            if profile_id not in self._engines:
                from app.core.profiles import get_profile, DEFAULT_PROFILE_ID
                profile = get_profile(profile_id)
                if not profile:
                    profile = get_profile(DEFAULT_PROFILE_ID)

                db_path = profile.db_path if profile else DB_PATH
                db_path.parent.mkdir(parents=True, exist_ok=True)
                url = f"sqlite:///{db_path}"
                eng = configure_sqlite_engine(url)
                self._engines[profile_id] = eng
                self._sessionmakers[profile_id] = sessionmaker(autocommit=False, autoflush=False, bind=eng)
            return self._engines[profile_id]

    def get_sessionmaker(self, profile_id: str) -> sessionmaker:
        self.get_engine(profile_id)
        with self._lock:
            return self._sessionmakers[profile_id]

    def dispose_engine(self, profile_id: str):
        with self._lock:
            if profile_id in self._engines:
                try:
                    self._engines[profile_id].dispose()
                except Exception:
                    pass
                del self._engines[profile_id]
            if profile_id in self._sessionmakers:
                del self._sessionmakers[profile_id]

    def dispose_all(self):
        with self._lock:
            for eng in self._engines.values():
                try:
                    eng.dispose()
                except Exception:
                    pass
            self._engines.clear()
            self._sessionmakers.clear()

# Global engine registry instance
db_registry = ProfileEngineRegistry()

# Ensure default database parent directory exists
Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)

# Default backward-compatible application engine & sessionmaker
engine = db_registry.get_engine("default")
SessionLocal = db_registry.get_sessionmaker("default")

def resolve_request_profile_id(request: Request = None) -> str:
    """
    Extracts and validates target profile ID for the current request.
    Rules:
    1. If 'X-Profile-ID' header is provided:
       Must be non-empty and correspond to an existing registered profile.
       If invalid: raise HTTPException(404, "Profile '{header_id}' not found.").
       Returns validated profile.id.
    2. Fallback for unscoped request:
       Resolves strictly to the fixed designated bootstrap/default profile (is_default=True).
       NEVER resolves based on a mutable process-wide 'currently active' profile pointer.
       If no designated default profile exists: raise HTTPException(400, "Profile context required: 'X-Profile-ID' header must be specified.")
    """
    from app.core.profiles import get_profile, get_default_profile
    if request is not None:
        header_id = request.headers.get("X-Profile-ID")
        if header_id:
            profile = get_profile(header_id.strip())
            if not profile:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Profile '{header_id}' not found."
                )
            return profile.id

    default_prof = get_default_profile()
    if default_prof:
        return default_prof.id

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Profile context required: 'X-Profile-ID' header must be specified."
    )

def get_current_profile(request: Request = None):
    """FastAPI dependency to retrieve the current request's ProfileMetadata."""
    from app.core.profiles import get_profile, get_default_profile
    p_id = resolve_request_profile_id(request)
    profile = get_profile(p_id)
    if not profile:
        profile = get_default_profile()
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Profile '{p_id}' not found."
        )
    return profile

def get_db(request: Request = None):
    """FastAPI request dependency for database session strictly bound to the target profile."""
    profile_id = resolve_request_profile_id(request)
    sm = db_registry.get_sessionmaker(profile_id)
    db = sm()
    try:
        yield db
    finally:
        db.close()
