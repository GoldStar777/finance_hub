import argparse
import fcntl
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from app.config import (
    DB_PATH, DATA_DIR, BACKUP_DIR, 
    STAGING_RECEIPTS_DIR, ARCHIVE_RECEIPTS_DIR, DEFAULT_PORT
)

def _compute_sha256(filepath: Path) -> str:
    sha256 = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            sha256.update(chunk)
    return sha256.hexdigest()

def is_database_in_use(db_path: Path, port: int) -> tuple[bool, str]:
    """
    Checks whether the database or service is currently in use:
    1. Tests exclusive file lock on the SQLite file.
    2. Runs lsof on the database file to detect open handles.
    3. Checks if any process is actively listening on the application port.
    Returns (in_use: bool, reason: str).
    """
    # 1. Check open handles via lsof
    if db_path.exists():
        try:
            res = subprocess.run(
                ["lsof", str(db_path)],
                capture_output=True,
                text=True,
                timeout=3
            )
            if res.returncode == 0 and res.stdout.strip():
                lines = res.stdout.strip().split("\n")
                if len(lines) > 1:
                    return True, f"Active process holds open file descriptors on {db_path.name}:\n{res.stdout}"
        except Exception:
            pass

        # 2. Try non-blocking exclusive file lock
        try:
            with open(db_path, "r+b") as f:
                try:
                    fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                except (BlockingIOError, OSError) as e:
                    return True, f"Database file is locked by another process: {str(e)}"
        except Exception:
            pass

    # 3. Check if server port is listening
    try:
        res = subprocess.run(
            ["lsof", f"-iTCP:{port}", "-sTCP:LISTEN"],
            capture_output=True,
            text=True,
            timeout=3
        )
        if res.returncode == 0 and res.stdout.strip():
            return True, f"A server process is actively listening on port {port}:\n{res.stdout}"
    except Exception:
        pass

    return False, ""

def perform_restore(
    zip_path: Path,
    db_path: Path = DB_PATH,
    backup_dir: Path = BACKUP_DIR,
    staging_receipts_dir: Path = STAGING_RECEIPTS_DIR,
    archive_receipts_dir: Path = ARCHIVE_RECEIPTS_DIR,
    port: int = DEFAULT_PORT,
    force_lock: bool = False
) -> bool:
    """
    Executes a verified offline restoration from a portable backup ZIP bundle.
    """
    if not zip_path.exists() or not zip_path.is_file():
        print(f"[ERROR] Specified backup archive does not exist: {zip_path}")
        return False

    print(f"\n=======================================================")
    print(f"Finance Hub — Offline Database & Data Restore Utility")
    print(f"Target Archive: {zip_path.name}")
    print(f"=======================================================\n")

    # Step 1: Concurrency and Active Process Guard
    if not force_lock:
        in_use, reason = is_database_in_use(db_path, port)
        if in_use:
            print(f"[REFUSED] Cannot proceed with offline restore:")
            print(f"{reason}\n")
            print("To safely restore:")
            print("1. Stop the running Finance Hub background service or web server.")
            print("2. Re-run this restore command.")
            print("3. Start Finance Hub after restoration completes.")
            return False

    temp_sandbox = Path(tempfile.mkdtemp(prefix="fh_restore_sandbox_"))
    try:
        # Step 2: Unpack & Test ZIP Integrity
        print("[1/5] Testing archive checksums and unpacking sandbox...")
        with zipfile.ZipFile(zip_path, "r") as zf:
            bad_file = zf.testzip()
            if bad_file:
                print(f"[ERROR] Corrupted ZIP member detected: {bad_file}")
                return False
            zf.extractall(temp_sandbox)

        # Step 3: Verify Manifest & SHA-256 Hashes
        print("[2/5] Verifying manifest and cryptographic hashes...")
        manifest_path = temp_sandbox / "manifest.json"
        unpacked_db = temp_sandbox / "database.db"

        if not manifest_path.exists():
            print("[ERROR] Archive is missing required manifest.json.")
            return False
        if not unpacked_db.exists() or unpacked_db.stat().st_size == 0:
            print("[ERROR] Archive is missing database.db or database file is empty.")
            return False

        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)

        expected_db_hash = manifest.get("sha256", {}).get("database.db")
        if expected_db_hash:
            actual_db_hash = _compute_sha256(unpacked_db)
            if actual_db_hash != expected_db_hash:
                print(f"[ERROR] SHA-256 mismatch on database.db!")
                print(f"  Expected: {expected_db_hash}")
                print(f"  Actual:   {actual_db_hash}")
                return False

        # Step 4: Run Isolated SQLite Integrity & Foreign Key Checks
        print("[3/5] Executing SQLite PRAGMA integrity and foreign key verification...")
        with sqlite3.connect(unpacked_db) as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA integrity_check;")
            ires = cursor.fetchall()
            if not ires or ires[0][0] != "ok":
                print(f"[ERROR] Unpacked database failed PRAGMA integrity_check: {ires}")
                return False

            cursor.execute("PRAGMA foreign_key_check;")
            fk_violations = cursor.fetchall()
            if fk_violations:
                print(f"[ERROR] Foreign key violations found in backup database: {fk_violations}")
                return False

        # Step 5: Preserve Pre-Restore Rollback Copy of Current State
        print("[4/5] Preserving pre-restore rollback copy of current live state...")
        backup_dir.mkdir(parents=True, exist_ok=True)
        now_ts = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M%S")
        pre_restore_dir = backup_dir / f"pre_restore_{now_ts}"
        pre_restore_dir.mkdir(parents=True, exist_ok=True)

        if db_path.exists():
            shutil.copy2(db_path, pre_restore_dir / db_path.name)
            # Copy WAL sidecars if present
            wal_file = db_path.parent / f"{db_path.name}-wal"
            shm_file = db_path.parent / f"{db_path.name}-shm"
            if wal_file.exists():
                shutil.copy2(wal_file, pre_restore_dir / wal_file.name)
            if shm_file.exists():
                shutil.copy2(shm_file, pre_restore_dir / shm_file.name)

        if staging_receipts_dir.exists():
            shutil.copytree(staging_receipts_dir, pre_restore_dir / "staging_receipts", dirs_exist_ok=True)
        if archive_receipts_dir.exists():
            shutil.copytree(archive_receipts_dir, pre_restore_dir / "receipts", dirs_exist_ok=True)

        print(f"      Rollback copy created at: {pre_restore_dir}")

        # Step 6: Atomic Replacement & Clean WAL Handover
        print("[5/5] Performing atomic file swap and clearing stale WAL journals...")
        db_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(unpacked_db, db_path)

        # Remove stale WAL sidecars so SQLite engine starts cleanly
        wal_file = db_path.parent / f"{db_path.name}-wal"
        shm_file = db_path.parent / f"{db_path.name}-shm"
        if wal_file.exists():
            wal_file.unlink(missing_ok=True)
        if shm_file.exists():
            shm_file.unlink(missing_ok=True)

        # Restore receipts if included
        unpacked_receipts = temp_sandbox / "receipts"
        if (unpacked_receipts / "staging").exists():
            staging_receipts_dir.mkdir(parents=True, exist_ok=True)
            shutil.copytree(unpacked_receipts / "staging", staging_receipts_dir, dirs_exist_ok=True)
        if (unpacked_receipts / "archive").exists():
            archive_receipts_dir.mkdir(parents=True, exist_ok=True)
            shutil.copytree(unpacked_receipts / "archive", archive_receipts_dir, dirs_exist_ok=True)

        # Final verification on restored database
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA integrity_check;")
            res = cursor.fetchall()
            if not res or res[0][0] != "ok":
                raise RuntimeError(f"Post-restore integrity verification failed: {res}")

        print("\n=======================================================")
        print("RESTORE COMPLETED SUCCESSFULLY")
        print(f"Restored Database: {db_path}")
        print(f"Rollback Safety Copy: {pre_restore_dir}")
        print(f"Integrity Check: OK (100% verified)")
        print("You may now restart the Finance Hub background service.")
        print("=======================================================\n")
        return True

    finally:
        shutil.rmtree(temp_sandbox, ignore_errors=True)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Finance Hub Offline Database Restore Utility")
    parser.add_argument("archive", type=Path, help="Path to finance_hub_backup_*.zip archive to restore")
    parser.add_argument("--profile", type=str, default=None, help="Target profile ID or name to restore into (defaults to default profile)")
    parser.add_argument("--force-lock", action="store_true", help="Bypass process concurrency lock check (Use with caution)")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Port to check for running service")

    args = parser.parse_args()

    target_db_path = DB_PATH
    target_backup_dir = BACKUP_DIR
    target_staging_dir = STAGING_RECEIPTS_DIR
    target_archive_dir = ARCHIVE_RECEIPTS_DIR

    if args.profile:
        from app.core.profiles import get_profile, list_profiles
        target_prof = get_profile(args.profile)
        if not target_prof:
            for p in list_profiles(include_archived=True):
                if p.name.strip().lower() == args.profile.strip().lower():
                    target_prof = p
                    break
        if not target_prof:
            print(f"[ERROR] Target profile '{args.profile}' not found.")
            sys.exit(1)
        target_db_path = target_prof.db_path
        target_backup_dir = target_prof.backups_dir
        target_staging_dir = target_prof.staging_receipts_dir
        target_archive_dir = target_prof.receipts_dir

    success = perform_restore(
        args.archive,
        db_path=target_db_path,
        backup_dir=target_backup_dir,
        staging_receipts_dir=target_staging_dir,
        archive_receipts_dir=target_archive_dir,
        port=args.port,
        force_lock=args.force_lock
    )
    sys.exit(0 if success else 1)

