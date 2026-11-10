import os
import json
import sqlite3
import pytest
import concurrent.futures
from pathlib import Path
from fastapi.testclient import TestClient

from app.main import app
from app.database import get_db, db_registry
from app.core import profiles as profiles_module
from app.core.backup import evaluate_backup_schedule, generate_backup_bundle
from app.restore import perform_restore
from app.models import Account, AccountType, Transaction, TransactionType

@pytest.fixture
def isolated_profiles_env(tmp_path, monkeypatch):
    """Configures an isolated profiles environment in tmp_path."""
    test_data_dir = tmp_path / "data"
    test_data_dir.mkdir(parents=True, exist_ok=True)
    test_reg_path = test_data_dir / "profiles.json"
    test_db_path = test_data_dir / "finances.db"
    test_receipts = test_data_dir / "receipts"
    test_staging = test_data_dir / "staging_receipts"
    test_backups = test_data_dir / "backups"

    test_receipts.mkdir(parents=True, exist_ok=True)
    test_staging.mkdir(parents=True, exist_ok=True)
    test_backups.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(profiles_module, "DATA_DIR", test_data_dir)
    monkeypatch.setattr(profiles_module, "PROFILES_REGISTRY_PATH", test_reg_path)
    monkeypatch.setattr(profiles_module, "DB_PATH", test_db_path)
    monkeypatch.setattr(profiles_module, "ARCHIVE_RECEIPTS_DIR", test_receipts)
    monkeypatch.setattr(profiles_module, "STAGING_RECEIPTS_DIR", test_staging)
    monkeypatch.setattr(profiles_module, "BACKUP_DIR", test_backups)

    # Initialize default profile database schema
    from app.models import Base
    from app.database import configure_sqlite_engine
    eng = configure_sqlite_engine(f"sqlite:///{test_db_path}")
    Base.metadata.create_all(bind=eng)
    with eng.begin() as conn:
        from sqlalchemy import text
        conn.execute(text("CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY);"))
        conn.execute(text("INSERT INTO alembic_version (version_num) VALUES ('e5f6a7b8c9d0');"))
    eng.dispose()

    # Clear engine cache
    db_registry.dispose_all()

    yield {
        "data_dir": test_data_dir,
        "registry_path": test_reg_path,
        "default_db": test_db_path,
        "backups_dir": test_backups
    }

    db_registry.dispose_all()

def test_default_profile_initialization(isolated_profiles_env):
    """Verifies that the registry initializes automatically with the default profile."""
    profs = profiles_module.list_profiles()
    assert len(profs) == 1
    default_p = profs[0]
    assert default_p.id == "default"
    assert default_p.name == "Default Profile"
    assert default_p.is_default is True
    assert default_p.is_active is True
    assert default_p.db_path == isolated_profiles_env["default_db"]

def test_create_profile_with_alembic_head(isolated_profiles_env):
    """Verifies creating a profile allocates dedicated storage and initializes schema at Alembic head."""
    new_p = profiles_module.create_profile("Business Operations")
    assert new_p.id != "default"
    assert len(new_p.id) == 32  # Opaque UUID hex
    assert new_p.name == "Business Operations"
    assert new_p.is_default is False
    assert new_p.is_archived is False

    # Check dedicated filesystem layout
    assert new_p.storage_dir.exists()
    assert new_p.db_path.exists()
    assert new_p.receipts_dir.exists()
    assert new_p.staging_receipts_dir.exists()
    assert new_p.backups_dir.exists()

    # Verify SQLite schema and Alembic version
    with sqlite3.connect(new_p.db_path) as conn:
        cur = conn.cursor()
        tables = [r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        assert "accounts" in tables
        assert "transactions" in tables
        assert "holdings" in tables
        assert "system_settings" in tables

        alembic_rev = cur.execute("SELECT version_num FROM alembic_version").fetchone()
        assert alembic_rev is not None
        assert alembic_rev[0] in ("e5f6a7b8c9d0", "f6a7b8c9d0e1", "a1b2c3d4e5f6", "b2c3d4e5f6a7", "c3d4e5f6a7b9")

def test_profile_data_isolation(isolated_profiles_env):
    """Ensures records created in one profile never leak into another profile."""
    prof_b = profiles_module.create_profile("Side Business")

    client = TestClient(app)

    # 1. Create account in Default profile
    res_a = client.post(
        "/api/accounts",
        headers={"X-Profile-ID": "default"},
        json={"name": "Default Current Account", "account_type": "current", "starting_balance": 100.0, "currency": "GBP"}
    )
    assert res_a.status_code == 201

    # 2. Verify account exists in default profile
    list_a = client.get("/api/accounts", headers={"X-Profile-ID": "default"}).json()
    assert len(list_a) == 1
    assert list_a[0]["name"] == "Default Current Account"

    # 3. Verify Profile B has 0 accounts (complete isolation)
    list_b = client.get("/api/accounts", headers={"X-Profile-ID": prof_b.id}).json()
    assert len(list_b) == 0

    # 4. Create account in Profile B
    res_b = client.post(
        "/api/accounts",
        headers={"X-Profile-ID": prof_b.id},
        json={"name": "Business Checking", "account_type": "current", "starting_balance": 500.0, "currency": "GBP"}
    )
    assert res_b.status_code == 201

    # 5. Verify Profile B has 1 account and Default still has 1 account (its own)
    list_b_after = client.get("/api/accounts", headers={"X-Profile-ID": prof_b.id}).json()
    assert len(list_b_after) == 1
    assert list_b_after[0]["name"] == "Business Checking"

    list_a_after = client.get("/api/accounts", headers={"X-Profile-ID": "default"}).json()
    assert len(list_a_after) == 1
    assert list_a_after[0]["name"] == "Default Current Account"

def test_overlapping_requests_concurrency_isolation(isolated_profiles_env):
    """
    Proves that overlapping requests for two profile IDs cannot read or write to
    each other's databases or storage, even under concurrent execution.
    """
    prof_alpha = profiles_module.create_profile("Workspace Alpha")
    prof_beta = profiles_module.create_profile("Workspace Beta")

    client = TestClient(app)

    def write_and_query_profile(profile_id: str, account_prefix: str, count: int):
        created_names = []
        for i in range(count):
            name = f"{account_prefix}_Acc_{i}"
            res = client.post(
                "/api/accounts",
                headers={"X-Profile-ID": profile_id},
                json={"name": name, "account_type": "current", "starting_balance": (i + 1) * 10.0, "currency": "GBP"}
            )
            assert res.status_code == 201
            created_names.append(name)

        # Query back
        res_list = client.get("/api/accounts", headers={"X-Profile-ID": profile_id})
        assert res_list.status_code == 200
        fetched_names = [a["name"] for a in res_list.json()]
        return created_names, fetched_names

    # Run writes in parallel across threads to test simultaneous concurrency
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        f_alpha = executor.submit(write_and_query_profile, prof_alpha.id, "Alpha", 5)
        f_beta = executor.submit(write_and_query_profile, prof_beta.id, "Beta", 5)

        created_a, fetched_a = f_alpha.result()
        created_b, fetched_b = f_beta.result()

    # Verify Workspace Alpha has only Alpha accounts
    assert len(fetched_a) == 5
    for name in created_a:
        assert name in fetched_a
        assert name not in fetched_b

    # Verify Workspace Beta has only Beta accounts
    assert len(fetched_b) == 5
    for name in created_b:
        assert name in fetched_b
        assert name not in fetched_a

def test_missing_and_invalid_profile_ids(isolated_profiles_env):
    """
    Verifies request-scoped fail-safe profile resolution:
    - Invalid profile IDs return 404.
    - Missing profile IDs fall back strictly to fixed designated default profile,
      never to a mutable active profile selected by another request.
    """
    client = TestClient(app)

    # 1. Invalid profile ID returns 404
    res_invalid = client.get("/api/accounts", headers={"X-Profile-ID": "non-existent-uuid"})
    assert res_invalid.status_code == 404
    assert "not found" in res_invalid.json()["detail"].lower()

    # 2. Add an account to Default profile
    client.post(
        "/api/accounts",
        headers={"X-Profile-ID": "default"},
        json={"name": "Default Account", "account_type": "current", "starting_balance": 100.0, "currency": "GBP"}
    )

    # 3. Create Profile Beta and switch active pointer to Beta
    prof_beta = profiles_module.create_profile("Profile Beta")
    client.post(
        "/api/accounts",
        headers={"X-Profile-ID": prof_beta.id},
        json={"name": "Beta Account", "account_type": "savings", "starting_balance": 500.0, "currency": "GBP"}
    )
    client.post(f"/api/profiles/{prof_beta.id}/select")
    assert profiles_module.get_active_profile_id() == prof_beta.id

    # 4. An unscoped request (missing X-Profile-ID) MUST route to the fixed designated default profile,
    # NOT to the active profile (Beta)!
    res_unscoped = client.get("/api/accounts")
    assert res_unscoped.status_code == 200
    accs = res_unscoped.json()
    assert len(accs) == 1
    assert accs[0]["name"] == "Default Account"
    assert accs[0]["name"] != "Beta Account"

def test_delete_inactive_default_profile(isolated_profiles_env):
    """
    Verifies that the initial/default profile can be permanently deleted
    once inactive and another profile exists.
    Also verifies:
    - Safely designates another remaining profile as default.
    - Legacy root paths are cleanly removed without touching other profiles or profiles.json.
    - Active profile cannot be deleted.
    - Last remaining profile cannot be deleted.
    """
    client = TestClient(app)

    # 1. Add account to default profile
    client.post(
        "/api/accounts",
        headers={"X-Profile-ID": "default"},
        json={"name": "Default Current", "account_type": "current", "starting_balance": 250.0, "currency": "GBP"}
    )

    # 2. Create second profile ("Personal Workspace")
    res_p2 = client.post("/api/profiles", json={"name": "Personal Workspace"}).json()
    p2_id = res_p2["id"]
    client.post(
        "/api/accounts",
        headers={"X-Profile-ID": p2_id},
        json={"name": "Personal Current", "account_type": "current", "starting_balance": 1000.0, "currency": "GBP"}
    )

    # 3. Cannot delete default profile while it is currently active
    res_del_active = client.request("DELETE", "/api/profiles/default", json={"confirm_name": "Default Profile"})
    assert res_del_active.status_code == 400
    assert "Cannot delete the currently active profile" in res_del_active.json()["detail"]

    # 4. Switch active profile to Personal Workspace
    client.post(f"/api/profiles/{p2_id}/select")
    assert profiles_module.get_active_profile_id() == p2_id

    # 5. Check impact summary for default profile
    res_impact = client.get("/api/profiles/default/impact")
    assert res_impact.status_code == 200
    impact = res_impact.json()
    assert impact["can_delete"] is True
    assert impact["blocking_reason"] is None
    assert impact["accounts_count"] == 1

    # 6. Delete default profile with wrong confirmation name -> rejected
    res_del_mismatch = client.request("DELETE", "/api/profiles/default", json={"confirm_name": "Wrong Name"})
    assert res_del_mismatch.status_code == 400
    assert "does not match" in res_del_mismatch.json()["detail"]

    # 7. Delete default profile with exact name confirmation -> SUCCESS
    res_del = client.request("DELETE", "/api/profiles/default", json={"confirm_name": "Default Profile"})
    assert res_del.status_code == 204

    # 8. Verify default profile is gone from registry
    profs_after = client.get("/api/profiles").json()
    assert len(profs_after) == 1
    remaining_prof = profs_after[0]
    assert remaining_prof["id"] == p2_id
    assert remaining_prof["name"] == "Personal Workspace"
    # Safely designated as default
    assert remaining_prof["is_default"] is True
    assert remaining_prof["is_active"] is True

    # 9. Verify Personal Workspace data is completely intact
    p2_accs = client.get("/api/accounts", headers={"X-Profile-ID": p2_id}).json()
    assert len(p2_accs) == 1
    assert p2_accs[0]["name"] == "Personal Current"

    # 10. Verify legacy root database file was deleted, but profiles directory and profiles.json exist
    default_db_file = isolated_profiles_env["default_db"]
    assert not default_db_file.exists()
    assert isolated_profiles_env["registry_path"].exists()
    assert (isolated_profiles_env["data_dir"] / "profiles" / p2_id).exists()

    # 11. Cannot delete the only remaining profile
    res_del_last = client.request("DELETE", f"/api/profiles/{p2_id}", json={"confirm_name": "Personal Workspace"})
    assert res_del_last.status_code == 400
    assert "Cannot delete the currently active profile" in res_del_last.json()["detail"] or "only remaining profile" in res_del_last.json()["detail"]

def test_profile_scoped_backup_and_restore(isolated_profiles_env):
    """
    Verifies that backup generation, automated schedule evaluation,
    and offline restore strictly use the profile's dedicated database and storage paths.
    """
    prof_target = profiles_module.create_profile("Vault Profile")
    client = TestClient(app)

    # 1. Create account in Vault Profile
    client.post(
        "/api/accounts",
        headers={"X-Profile-ID": prof_target.id},
        json={"name": "Vault Savings", "account_type": "savings", "starting_balance": 5000.0, "currency": "GBP"}
    )

    # 2. Trigger on-demand backup for Vault Profile
    res_backup = client.post("/api/system/backup", headers={"X-Profile-ID": prof_target.id})
    assert res_backup.status_code == 201
    backup_data = res_backup.json()
    assert backup_data["success"] is True

    # Check backup ZIP is strictly inside Vault Profile's backups_dir
    backup_filename = backup_data["filename"]
    assert (prof_target.backups_dir / backup_filename).exists()
    # Must NOT be in the default backup dir
    assert not (isolated_profiles_env["backups_dir"] / backup_filename).exists()

    # 3. Test evaluate_backup_schedule uses Vault Profile's directory
    res_status = client.get("/api/system/backup-status", headers={"X-Profile-ID": prof_target.id})
    assert res_status.status_code == 200
    assert res_status.json()["last_successful_backup_at"] is not None

    # 4. Test offline restore targeting Vault Profile
    backup_zip_path = prof_target.backups_dir / backup_filename
    restore_success = perform_restore(
        zip_path=backup_zip_path,
        db_path=prof_target.db_path,
        backup_dir=prof_target.backups_dir,
        staging_receipts_dir=prof_target.staging_receipts_dir,
        archive_receipts_dir=prof_target.receipts_dir,
        force_lock=True
    )
    assert restore_success is True

    # Check database integrity post-restore
    with sqlite3.connect(prof_target.db_path) as conn:
        cur = conn.cursor()
        acc = cur.execute("SELECT name FROM accounts").fetchone()
        assert acc[0] == "Vault Savings"
