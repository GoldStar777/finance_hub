import os
import re
import json
import uuid
import shutil
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Dict, Any

from sqlalchemy import text
from app.config import DATA_DIR, DB_PATH, STAGING_RECEIPTS_DIR, ARCHIVE_RECEIPTS_DIR, BACKUP_DIR

PROFILES_REGISTRY_PATH = DATA_DIR / "profiles.json"
DEFAULT_PROFILE_ID = "default"
DEFAULT_PROFILE_NAME = "Default Profile"

# Global lock for thread-safe registry writes
_registry_lock = threading.Lock()

class ProfileMetadata:
    """Represents a financial workspace profile with dedicated storage."""
    def __init__(
        self,
        id: str,
        name: str,
        created_at: str,
        is_archived: bool = False,
        is_default: bool = False,
        is_active: bool = False
    ):
        self.id = id
        self.name = name
        self.created_at = created_at
        self.is_archived = is_archived
        self.is_default = is_default
        self.is_active = is_active

    @property
    def is_root_default(self) -> bool:
        return self.id == DEFAULT_PROFILE_ID

    @property
    def storage_dir(self) -> Path:
        if self.is_root_default:
            return DATA_DIR
        return DATA_DIR / "profiles" / self.id

    @property
    def db_path(self) -> Path:
        if self.is_root_default:
            return DB_PATH
        return self.storage_dir / "finances.db"

    @property
    def receipts_dir(self) -> Path:
        if self.is_root_default:
            return ARCHIVE_RECEIPTS_DIR
        return self.storage_dir / "receipts"

    @property
    def staging_receipts_dir(self) -> Path:
        if self.is_root_default:
            return STAGING_RECEIPTS_DIR
        return self.storage_dir / "staging_receipts"

    @property
    def backups_dir(self) -> Path:
        if self.is_root_default:
            return BACKUP_DIR
        return self.storage_dir / "backups"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "created_at": self.created_at,
            "is_archived": self.is_archived,
            "is_default": self.is_default,
            "is_active": self.is_active
        }

def _get_alembic_head_revision() -> str:
    """Determines current Alembic head revision dynamically or falls back to known head."""
    from app.database import get_alembic_head_revision
    return get_alembic_head_revision()

def _load_registry_data() -> Dict[str, Any]:
    """Reads profiles.json, initializing with default profile if missing."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not PROFILES_REGISTRY_PATH.exists():
        default_profile = {
            "id": DEFAULT_PROFILE_ID,
            "name": DEFAULT_PROFILE_NAME,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "is_archived": False,
            "is_default": True
        }
        initial_data = {
            "active_profile_id": DEFAULT_PROFILE_ID,
            "profiles": [default_profile]
        }
        _save_registry_data(initial_data)
        return initial_data

    try:
        with open(PROFILES_REGISTRY_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            if not isinstance(data, dict) or "profiles" not in data:
                raise ValueError("Corrupt profiles registry structure.")
            return data
    except Exception:
        # Fallback recovery: ensure default profile is preserved
        default_profile = {
            "id": DEFAULT_PROFILE_ID,
            "name": DEFAULT_PROFILE_NAME,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "is_archived": False,
            "is_default": True
        }
        return {
            "active_profile_id": DEFAULT_PROFILE_ID,
            "profiles": [default_profile]
        }

def _save_registry_data(data: Dict[str, Any]) -> None:
    """Atomically writes registry data to avoid corruption during concurrent accesses."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp_path = PROFILES_REGISTRY_PATH.with_suffix(".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp_path, PROFILES_REGISTRY_PATH)

def list_profiles(include_archived: bool = True) -> List[ProfileMetadata]:
    """Lists all registered profiles."""
    with _registry_lock:
        data = _load_registry_data()
        active_id = data.get("active_profile_id", DEFAULT_PROFILE_ID)
        profiles = []
        for p in data.get("profiles", []):
            if not include_archived and p.get("is_archived", False):
                continue
            is_active = (p.get("id") == active_id)
            profiles.append(
                ProfileMetadata(
                    id=p["id"],
                    name=p.get("name", "Unnamed Profile"),
                    created_at=p.get("created_at", datetime.now(timezone.utc).isoformat()),
                    is_archived=p.get("is_archived", False),
                    is_default=p.get("is_default", False),
                    is_active=is_active
                )
            )
        return profiles

def get_profile(profile_id: str) -> Optional[ProfileMetadata]:
    """Retrieves a single profile by ID."""
    with _registry_lock:
        data = _load_registry_data()
        active_id = data.get("active_profile_id", DEFAULT_PROFILE_ID)
        for p in data.get("profiles", []):
            if p.get("id") == profile_id:
                return ProfileMetadata(
                    id=p["id"],
                    name=p.get("name", "Unnamed Profile"),
                    created_at=p.get("created_at", datetime.now(timezone.utc).isoformat()),
                    is_archived=p.get("is_archived", False),
                    is_default=p.get("is_default", False),
                    is_active=(p["id"] == active_id)
                )
        return None

def get_default_profile() -> Optional[ProfileMetadata]:
    """
    Returns the designated default profile from the registry (is_default == True).
    If no profile is marked default, falls back to the first available profile.
    Never depends on a mutable session-selected active profile.
    """
    with _registry_lock:
        data = _load_registry_data()
        active_id = data.get("active_profile_id", DEFAULT_PROFILE_ID)
        profiles = data.get("profiles", [])
        for p in profiles:
            if p.get("is_default", False):
                return ProfileMetadata(
                    id=p["id"],
                    name=p.get("name", "Unnamed Profile"),
                    created_at=p.get("created_at", datetime.now(timezone.utc).isoformat()),
                    is_archived=p.get("is_archived", False),
                    is_default=True,
                    is_active=(p["id"] == active_id)
                )
        if profiles:
            p0 = profiles[0]
            return ProfileMetadata(
                id=p0["id"],
                name=p0.get("name", "Unnamed Profile"),
                created_at=p0.get("created_at", datetime.now(timezone.utc).isoformat()),
                is_archived=p0.get("is_archived", False),
                is_default=True,
                is_active=(p0["id"] == active_id)
            )
        return None

def get_active_profile_id() -> str:
    """Returns the current globally selected active profile ID."""
    with _registry_lock:
        data = _load_registry_data()
        active_id = data.get("active_profile_id", DEFAULT_PROFILE_ID)
        # Ensure active_id exists in registered profiles
        exists = any(p.get("id") == active_id for p in data.get("profiles", []))
        if not exists:
            return DEFAULT_PROFILE_ID
        return active_id

def set_active_profile_id(profile_id: str) -> ProfileMetadata:
    """Updates the active profile pointer in the global registry."""
    with _registry_lock:
        data = _load_registry_data()
        target = next((p for p in data.get("profiles", []) if p.get("id") == profile_id), None)
        if not target:
            raise ValueError(f"Profile with ID '{profile_id}' does not exist.")
        if target.get("is_archived", False):
            raise ValueError(f"Cannot select archived profile '{target.get('name')}'. Unarchive it first.")

        data["active_profile_id"] = profile_id
        _save_registry_data(data)

        return ProfileMetadata(
            id=target["id"],
            name=target.get("name", "Unnamed Profile"),
            created_at=target.get("created_at", datetime.now(timezone.utc).isoformat()),
            is_archived=target.get("is_archived", False),
            is_default=target.get("is_default", False),
            is_active=True
        )

def create_profile(name: str) -> ProfileMetadata:
    """
    Creates a new isolated financial profile workspace with:
    1. Dedicated opaque storage directory.
    2. Blank SQLite database initialized to Alembic head schema.
    3. Dedicated receipts, staging, and backups folders.
    """
    clean_name = name.strip() if name else ""
    if not clean_name:
        raise ValueError("Profile name cannot be blank.")
    if len(clean_name) > 100:
        raise ValueError("Profile name must be 100 characters or fewer.")

    with _registry_lock:
        data = _load_registry_data()
        # Verify unique name (case-insensitive) for clarity
        for p in data.get("profiles", []):
            if p.get("name", "").strip().lower() == clean_name.lower():
                raise ValueError(f"A profile named '{clean_name}' already exists.")

        profile_id = uuid.uuid4().hex
        new_profile = ProfileMetadata(
            id=profile_id,
            name=clean_name,
            created_at=datetime.now(timezone.utc).isoformat(),
            is_archived=False,
            is_default=False,
            is_active=False
        )

        # Allocate storage directories
        new_profile.storage_dir.mkdir(parents=True, exist_ok=True)
        new_profile.receipts_dir.mkdir(parents=True, exist_ok=True)
        new_profile.staging_receipts_dir.mkdir(parents=True, exist_ok=True)
        new_profile.backups_dir.mkdir(parents=True, exist_ok=True)

        # Initialize SQLite database with complete schema at Alembic head
        from app.database import configure_sqlite_engine, initialize_database_schema
        
        db_url = f"sqlite:///{new_profile.db_path}"
        engine = configure_sqlite_engine(db_url)
        try:
            initialize_database_schema(engine)
        finally:
            engine.dispose()

        # Register in profiles.json
        data.setdefault("profiles", []).append({
            "id": new_profile.id,
            "name": new_profile.name,
            "created_at": new_profile.created_at,
            "is_archived": False,
            "is_default": False
        })
        _save_registry_data(data)

        return new_profile

def update_profile(
    profile_id: str,
    name: Optional[str] = None,
    is_archived: Optional[bool] = None
) -> ProfileMetadata:
    """Updates profile name or archive state with safeguards."""
    with _registry_lock:
        data = _load_registry_data()
        target = next((p for p in data.get("profiles", []) if p.get("id") == profile_id), None)
        if not target:
            raise ValueError(f"Profile with ID '{profile_id}' does not exist.")

        active_id = data.get("active_profile_id", DEFAULT_PROFILE_ID)

        if name is not None:
            clean_name = name.strip()
            if not clean_name:
                raise ValueError("Profile name cannot be blank.")
            if len(clean_name) > 100:
                raise ValueError("Profile name must be 100 characters or fewer.")
            for p in data.get("profiles", []):
                if p["id"] != profile_id and p.get("name", "").strip().lower() == clean_name.lower():
                    raise ValueError(f"Another profile is already named '{clean_name}'.")
            target["name"] = clean_name

        if is_archived is not None:
            if is_archived and profile_id == active_id:
                raise ValueError("Cannot archive the currently active profile. Switch to another profile first.")
            target["is_archived"] = is_archived

        _save_registry_data(data)

        return ProfileMetadata(
            id=target["id"],
            name=target.get("name", "Unnamed Profile"),
            created_at=target.get("created_at", datetime.now(timezone.utc).isoformat()),
            is_archived=target.get("is_archived", False),
            is_default=target.get("is_default", False),
            is_active=(target["id"] == active_id)
        )

def _format_bytes(size: int) -> str:
    """Returns human-readable byte size."""
    if size < 1024:
        return f"{size} B"
    elif size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    elif size < 1024 * 1024 * 1024:
        return f"{size / (1024 * 1024):.1f} MB"
    return f"{size / (1024 * 1024 * 1024):.1f} GB"

def get_profile_impact(profile_id: str) -> Dict[str, Any]:
    """
    Computes an impact summary showing what records, files, and disk space
    will be affected if the profile is deleted.
    """
    profile = get_profile(profile_id)
    if not profile:
        raise ValueError(f"Profile with ID '{profile_id}' not found.")

    with _registry_lock:
        data = _load_registry_data()
        active_id = data.get("active_profile_id", DEFAULT_PROFILE_ID)
        total_count = len(data.get("profiles", []))

    is_active = (profile.id == active_id)
    can_delete = True
    blocking_reason = None

    if is_active:
        can_delete = False
        blocking_reason = "Cannot delete the currently active profile. Switch to another profile first."
    elif total_count <= 1:
        can_delete = False
        blocking_reason = "Cannot delete the only remaining profile."

    # Query record counts from profile database
    accounts_count = 0
    transactions_count = 0
    categories_count = 0
    holdings_count = 0
    staging_items_count = 0

    if profile.db_path.exists():
        try:
            with sqlite3.connect(profile.db_path) as conn:
                cur = conn.cursor()
                def count_table(name: str) -> int:
                    try:
                        return cur.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
                    except Exception:
                        return 0

                accounts_count = count_table("accounts")
                transactions_count = count_table("transactions")
                categories_count = count_table("categories")
                holdings_count = count_table("holdings")
                staging_items_count = count_table("staging_items")
        except Exception:
            pass

    # Count files and disk usage
    receipt_files_count = 0
    backup_files_count = 0
    disk_usage_bytes = 0

    # 1. DB files (including WAL/SHM)
    for p in [profile.db_path, profile.db_path.with_name(f"{profile.db_path.name}-wal"), profile.db_path.with_name(f"{profile.db_path.name}-shm")]:
        if p.exists():
            disk_usage_bytes += p.stat().st_size

    # 2. Receipts
    for r_dir in [profile.receipts_dir, profile.staging_receipts_dir]:
        if r_dir.exists():
            for root, _, files in os.walk(r_dir):
                for f in files:
                    if not f.startswith("."):
                        receipt_files_count += 1
                        try:
                            disk_usage_bytes += os.path.getsize(os.path.join(root, f))
                        except Exception:
                            pass

    # 3. Backups
    if profile.backups_dir.exists():
        for root, _, files in os.walk(profile.backups_dir):
            for f in files:
                if f.endswith(".zip"):
                    backup_files_count += 1
                    try:
                        disk_usage_bytes += os.path.getsize(os.path.join(root, f))
                    except Exception:
                        pass

    return {
        "profile_id": profile.id,
        "profile_name": profile.name,
        "is_active": is_active,
        "is_default": profile.is_default,
        "can_delete": can_delete,
        "blocking_reason": blocking_reason,
        "accounts_count": accounts_count,
        "transactions_count": transactions_count,
        "categories_count": categories_count,
        "holdings_count": holdings_count,
        "staging_items_count": staging_items_count,
        "receipt_files_count": receipt_files_count,
        "backup_files_count": backup_files_count,
        "disk_usage_bytes": disk_usage_bytes,
        "disk_usage_formatted": _format_bytes(disk_usage_bytes)
    }

def delete_profile(profile_id: str, confirm_name: str) -> bool:
    """
    Permanently deletes a profile and its dedicated storage directory.
    Enforces all safeguards:
    - confirm_name must exactly match profile name.
    - cannot delete active profile.
    - cannot delete if only one profile remains.
    - safely designates another remaining profile as default if default profile is deleted.
    - legacy root storage paths for initial profile are cleanly and safely pruned.
    """
    clean_confirm = confirm_name.strip() if confirm_name else ""
    profile = get_profile(profile_id)
    if not profile:
        raise ValueError(f"Profile with ID '{profile_id}' not found.")

    with _registry_lock:
        data = _load_registry_data()
        active_id = data.get("active_profile_id", DEFAULT_PROFILE_ID)
        profiles = data.get("profiles", [])

        if profile.id == active_id:
            raise ValueError("Cannot delete the currently active profile. Switch to another profile first.")
        if len(profiles) <= 1:
            raise ValueError("Cannot delete the only remaining profile.")
        if clean_confirm != profile.name:
            raise ValueError(f"Confirmation name '{clean_confirm}' does not match profile name '{profile.name}'.")

        # Dispose database engine if open
        from app.database import db_registry
        db_registry.dispose_engine(profile.id)

        # Safely remove storage paths strictly confined to this profile
        if profile.is_root_default:
            # Legacy root paths used by the initial profile:
            # 1. Database file & WAL/SHM sidecars
            for db_f in [profile.db_path, profile.db_path.with_name(f"{profile.db_path.name}-wal"), profile.db_path.with_name(f"{profile.db_path.name}-shm")]:
                if db_f.exists():
                    try:
                        db_f.unlink(missing_ok=True)
                    except Exception:
                        pass
            # 2. Files in legacy receipts dirs
            for r_dir in [profile.receipts_dir, profile.staging_receipts_dir]:
                if r_dir.exists():
                    for root, _, files in os.walk(r_dir):
                        for f in files:
                            try:
                                os.unlink(os.path.join(root, f))
                            except Exception:
                                pass
            # 3. Files in legacy backups dir
            if profile.backups_dir.exists():
                for root, _, files in os.walk(profile.backups_dir):
                    for f in files:
                        try:
                            os.unlink(os.path.join(root, f))
                        except Exception:
                            pass
        else:
            # Dedicated profile directory
            if profile.storage_dir.exists():
                shutil.rmtree(profile.storage_dir, ignore_errors=True)

        # Remove from registry
        was_default = profile.is_default
        data["profiles"] = [p for p in profiles if p.get("id") != profile.id]

        # If deleted profile was designated default, designate another remaining profile
        if was_default and data["profiles"]:
            # Prefer active profile if present in remaining, else first
            new_def = next((p for p in data["profiles"] if p.get("id") == active_id), data["profiles"][0])
            new_def["is_default"] = True

        _save_registry_data(data)

    return True

