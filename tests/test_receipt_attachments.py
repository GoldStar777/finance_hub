"""Isolated integration and security tests for profile-scoped receipt attachment access."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app import config as app_config
from app.core import profiles as profiles_module
from app.core.review_suggestions import confirm_transfer_suggestion
from app.database import configure_sqlite_engine, db_registry
from app.main import app
from app.models import (
    Account,
    AccountType,
    Base,
    ExpenseNature,
    StagingItem,
    StagingStatus,
    SystemSetting,
    Transaction,
    TransactionType,
)


@pytest.fixture
def isolated_receipt_env(tmp_path, monkeypatch):
    """Isolates all profile registries, SQLite DBs, and receipt folders inside tmp_path."""
    test_data_dir = tmp_path / "data"
    test_reg_path = test_data_dir / "profiles.json"
    test_db_path = test_data_dir / "finances.db"
    test_receipts = test_data_dir / "receipts"
    test_staging = test_data_dir / "staging_receipts"
    test_backups = test_data_dir / "backups"

    for d in (test_data_dir, test_receipts, test_staging, test_backups):
        d.mkdir(parents=True, exist_ok=True)

    for target_module in (profiles_module, app_config):
        monkeypatch.setattr(target_module, "DATA_DIR", test_data_dir)
        monkeypatch.setattr(target_module, "DB_PATH", test_db_path)
        monkeypatch.setattr(target_module, "ARCHIVE_RECEIPTS_DIR", test_receipts)
        monkeypatch.setattr(target_module, "STAGING_RECEIPTS_DIR", test_staging)
        monkeypatch.setattr(target_module, "BACKUP_DIR", test_backups)
        if hasattr(target_module, "RECEIPTS_DIR"):
            monkeypatch.setattr(target_module, "RECEIPTS_DIR", test_staging)
    monkeypatch.setattr(profiles_module, "PROFILES_REGISTRY_PATH", test_reg_path)

    eng = configure_sqlite_engine(f"sqlite:///{test_db_path}")
    Base.metadata.create_all(bind=eng)
    with eng.begin() as conn:
        conn.execute(text("CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY);"))
        conn.execute(text("INSERT INTO alembic_version (version_num) VALUES ('e5f6a7b8c9d0');"))
    eng.dispose()

    db_registry.dispose_all()
    profiles_module.list_profiles()

    with TestClient(app) as client:
        yield {
            "client": client,
            "data_dir": test_data_dir,
            "tmp_path": tmp_path,
            "default_receipts_dir": test_receipts,
            "default_staging_dir": test_staging,
        }

    db_registry.dispose_all()


def _create_account(db, name: str = "Checking") -> Account:
    acc = Account(name=name, account_type=AccountType.CURRENT, starting_balance_pence=100000)
    db.add(acc)
    db.commit()
    db.refresh(acc)
    return acc


def _create_transaction(
    db,
    account_id: int,
    *,
    merchant: str = "Coffee Roasters",
    amount_pence: int = 450,
    tx_type: TransactionType = TransactionType.EXPENSE,
    receipt_path: str | None = None,
    dest_account_id: int | None = None,
    deleted_at: datetime | None = None,
) -> Transaction:
    tx = Transaction(
        transaction_date=datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc),
        effective_timestamp=datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc),
        transaction_type=tx_type,
        amount_pence=amount_pence,
        merchant=merchant,
        entry_method="receipt_image" if receipt_path else "manual",
        receipt_path=receipt_path,
        account_id=account_id,
        destination_account_id=dest_account_id,
        expense_nature=ExpenseNature.UNCLASSIFIED,
        deleted_at=deleted_at,
        deletion_batch_id="batch_deleted_test" if deleted_at else None,
    )
    db.add(tx)
    db.commit()
    db.refresh(tx)
    return tx


def test_valid_transaction_receipt_open_and_download(isolated_receipt_env):
    env = isolated_receipt_env
    client: TestClient = env["client"]

    receipt_file = env["default_receipts_dir"] / "2026" / "10" / "coffee.jpg"
    receipt_file.parent.mkdir(parents=True, exist_ok=True)
    receipt_bytes = b"\xff\xd8\xff\xe0MOCK_JPEG_RECEIPT_DATA"
    receipt_file.write_bytes(receipt_bytes)

    sm = db_registry.get_sessionmaker("default")
    with sm() as db:
        acc = _create_account(db)
        tx = _create_transaction(db, acc.id, receipt_path="receipts/2026/10/coffee.jpg")
        tx_id = tx.id

    list_resp = client.get("/api/transactions")
    assert list_resp.status_code == 200
    items = list_resp.json()["items"]
    assert len(items) == 1
    assert items[0]["receipt_url"] == f"/api/transactions/{tx_id}/receipt"
    assert "/static/" not in items[0]["receipt_url"]

    inline_resp = client.get(items[0]["receipt_url"])
    assert inline_resp.status_code == 200
    assert inline_resp.content == receipt_bytes
    assert inline_resp.headers["content-type"].startswith("image/jpeg")
    assert inline_resp.headers["content-disposition"].startswith("inline;")
    assert "coffee.jpg" in inline_resp.headers["content-disposition"]

    dl_resp = client.get(f"/api/transactions/{tx_id}/receipt?download=true")
    assert dl_resp.status_code == 200
    assert dl_resp.content == receipt_bytes
    assert dl_resp.headers["content-disposition"].startswith("attachment;")
    assert "coffee.jpg" in dl_resp.headers["content-disposition"]

    # Legacy static paths and mounts must not serve files
    assert client.get("/static/receipts/2026/10/coffee.jpg").status_code == 404
    assert client.get("/receipts_preview/any.jpg").status_code == 404
    assert client.get("/api/staging/receipts/coffee.jpg").status_code in (404, 422)


def test_profile_isolation_for_transactions_and_files(isolated_receipt_env):
    env = isolated_receipt_env
    client: TestClient = env["client"]

    work_prof = profiles_module.create_profile("Work Budget")
    default_file = env["default_receipts_dir"] / "2026" / "10" / "personal.jpg"
    default_file.parent.mkdir(parents=True, exist_ok=True)
    default_file.write_bytes(b"PERSONAL_SECRET_BYTES")

    work_file = work_prof.receipts_dir / "2026" / "10" / "work_invoice.pdf"
    work_file.parent.mkdir(parents=True, exist_ok=True)
    work_file.write_bytes(b"%PDF-1.4 WORK_SECRET")

    with db_registry.get_sessionmaker("default")() as db:
        acc_def = _create_account(db, "Personal")
        acc_def_id = acc_def.id
        tx_def_1 = _create_transaction(db, acc_def_id, receipt_path="receipts/2026/10/personal.jpg")
        tx_def_only = _create_transaction(db, acc_def_id, merchant="Personal #2", receipt_path="receipts/2026/10/personal.jpg")
        tx_def_id = tx_def_1.id
        tx_def_only_id = tx_def_only.id

    with db_registry.get_sessionmaker(work_prof.id)() as db:
        acc_work = _create_account(db, "Work")
        tx_work = _create_transaction(
            db,
            acc_work.id,
            receipt_path=f"profiles/{work_prof.id}/receipts/2026/10/work_invoice.pdf",
        )
        # Crafted cross-profile references in Work DB attempting to reach Default profile files
        tx_forged_rel = _create_transaction(db, acc_work.id, receipt_path="receipts/2026/10/personal.jpg")
        tx_forged_abs = _create_transaction(db, acc_work.id, receipt_path=str(default_file))
        tx_work_only = _create_transaction(
            db,
            acc_work.id,
            merchant="Work Extra",
            receipt_path=f"profiles/{work_prof.id}/receipts/2026/10/work_invoice.pdf",
        )
        tx_work_id = tx_work.id
        tx_forged_rel_id = tx_forged_rel.id
        tx_forged_abs_id = tx_forged_abs.id
        tx_work_only_id = tx_work_only.id

    # Work cannot access Default transaction ID (even colliding ID 1 never returns Personal's file) or forged paths
    assert tx_def_id == tx_work_id == 1
    assert client.get(f"/api/transactions/{tx_def_id}/receipt", headers={"X-Profile-ID": work_prof.id}).content == b"%PDF-1.4 WORK_SECRET"
    assert client.get(f"/api/transactions/{tx_forged_rel_id}/receipt", headers={"X-Profile-ID": work_prof.id}).status_code == 404
    assert client.get(f"/api/transactions/{tx_forged_abs_id}/receipt", headers={"X-Profile-ID": work_prof.id}).status_code == 404

    # Non-existent higher IDs never cross profiles
    assert client.get(f"/api/transactions/{tx_work_only_id}/receipt").status_code == 404
    with db_registry.get_sessionmaker("default")() as db:
        _create_transaction(db, acc_def_id, merchant="Personal #3", receipt_path="receipts/2026/10/personal.jpg")
        _create_transaction(db, acc_def_id, merchant="Personal #4", receipt_path="receipts/2026/10/personal.jpg")
        extra_def_c = _create_transaction(db, acc_def_id, merchant="Personal #5", receipt_path="receipts/2026/10/personal.jpg")
        def_high_id = extra_def_c.id
    assert client.get(f"/api/transactions/{def_high_id}/receipt", headers={"X-Profile-ID": work_prof.id}).status_code == 404

    # Each profile can access its own authorized attachment
    assert client.get(f"/api/transactions/{tx_def_only_id}/receipt").content == b"PERSONAL_SECRET_BYTES"
    work_ok = client.get(f"/api/transactions/{tx_work_id}/receipt", headers={"X-Profile-ID": work_prof.id})
    assert work_ok.status_code == 200
    assert work_ok.content == b"%PDF-1.4 WORK_SECRET"
    assert work_ok.headers["content-type"].startswith("application/pdf")


def test_missing_file_returns_clear_404(isolated_receipt_env):
    env = isolated_receipt_env
    client: TestClient = env["client"]

    with db_registry.get_sessionmaker("default")() as db:
        acc = _create_account(db)
        tx = _create_transaction(db, acc.id, receipt_path="receipts/2026/10/deleted_from_disk.png")
        tx_no_receipt = _create_transaction(db, acc.id, receipt_path=None)
        tx_id = tx.id
        tx_no_id = tx_no_receipt.id

    missing_resp = client.get(f"/api/transactions/{tx_id}/receipt")
    assert missing_resp.status_code == 404
    assert "not found" in missing_resp.json()["detail"].lower()

    assert client.get(f"/api/transactions/{tx_no_id}/receipt").status_code == 404
    assert client.get("/api/transactions/999999/receipt").status_code == 404


def test_path_traversal_and_symlink_escapes_blocked(isolated_receipt_env):
    env = isolated_receipt_env
    client: TestClient = env["client"]

    outside_secret = env["tmp_path"] / "outside_secret.txt"
    outside_secret.write_text("TOP_SECRET_OUTSIDE_DATA", encoding="utf-8")

    outside_dir = env["tmp_path"] / "outside_dir"
    outside_dir.mkdir(parents=True, exist_ok=True)
    (outside_dir / "leak.jpg").write_bytes(b"ESCAPED_DIR_BYTES")

    sym_file = env["default_receipts_dir"] / "symlink_file.txt"
    os.symlink(outside_secret, sym_file)

    sym_dir = env["default_receipts_dir"] / "symlink_subdir"
    os.symlink(outside_dir, sym_dir)

    with db_registry.get_sessionmaker("default")() as db:
        acc = _create_account(db)
        tx_trav_1 = _create_transaction(db, acc.id, receipt_path="../data/profiles.json")
        tx_trav_2 = _create_transaction(db, acc.id, receipt_path="receipts/../../outside_secret.txt")
        tx_abs_out = _create_transaction(db, acc.id, receipt_path=str(outside_secret))
        tx_sym_file = _create_transaction(db, acc.id, receipt_path="receipts/symlink_file.txt")
        tx_sym_dir = _create_transaction(db, acc.id, receipt_path="receipts/symlink_subdir/leak.jpg")
        ids = [tx_trav_1.id, tx_trav_2.id, tx_abs_out.id, tx_sym_file.id, tx_sym_dir.id]

    for bad_tx_id in ids:
        resp = client.get(f"/api/transactions/{bad_tx_id}/receipt")
        assert resp.status_code == 404, f"Unsafe receipt path unexpectedly accessible for tx {bad_tx_id}"


def test_shared_receipt_and_soft_deleted_transactions(isolated_receipt_env):
    env = isolated_receipt_env
    client: TestClient = env["client"]

    shared_file = env["default_receipts_dir"] / "2026" / "10" / "shared_groceries.png"
    shared_file.parent.mkdir(parents=True, exist_ok=True)
    shared_bytes = b"\x89PNG\r\n\x1a\nSHARED_SPLIT_PNG"
    shared_file.write_bytes(shared_bytes)
    rel_path = "receipts/2026/10/shared_groceries.png"

    with db_registry.get_sessionmaker("default")() as db:
        acc = _create_account(db)
        tx_active = _create_transaction(db, acc.id, merchant="Split 1", receipt_path=rel_path)
        tx_deleted = _create_transaction(
            db,
            acc.id,
            merchant="Split 2",
            receipt_path=rel_path,
            deleted_at=datetime.now(timezone.utc),
        )
        active_id = tx_active.id
        deleted_id = tx_deleted.id

    # Active sibling accesses shared file
    r1 = client.get(f"/api/transactions/{active_id}/receipt")
    assert r1.status_code == 200
    assert r1.content == shared_bytes

    # Soft-deleted sibling also preserves receipt access and exposes receipt_url in /deleted list
    del_list = client.get("/api/transactions/deleted")
    assert del_list.status_code == 200
    del_items = del_list.json()["items"]
    assert any(item["id"] == deleted_id and item["receipt_url"] == f"/api/transactions/{deleted_id}/receipt" for item in del_items)

    r2 = client.get(f"/api/transactions/{deleted_id}/receipt")
    assert r2.status_code == 200
    assert r2.content == shared_bytes


def test_paired_transfer_source_destination_and_legacy_provenance(isolated_receipt_env):
    env = isolated_receipt_env
    client: TestClient = env["client"]

    src_file = env["default_receipts_dir"] / "2026" / "10" / "out_leg.csv"
    dest_file = env["default_receipts_dir"] / "2026" / "10" / "in_leg.pdf"
    src_file.parent.mkdir(parents=True, exist_ok=True)
    src_file.write_bytes(b"date,amount\n2026-10-15,-50.00\n")
    dest_file.write_bytes(b"%PDF-1.4 DEST_RECEIPT")

    with db_registry.get_sessionmaker("default")() as db:
        src_acc = _create_account(db, "Current")
        dest_acc = _create_account(db, "Savings")
        out_tx = _create_transaction(
            db,
            src_acc.id,
            merchant="Transfer Out",
            amount_pence=5000,
            tx_type=TransactionType.EXPENSE,
            receipt_path="receipts/2026/10/out_leg.csv",
        )
        in_tx = _create_transaction(
            db,
            dest_acc.id,
            merchant="Transfer In",
            amount_pence=5000,
            tx_type=TransactionType.INCOME,
            receipt_path="receipts/2026/10/in_leg.pdf",
        )
        paired_tx = confirm_transfer_suggestion(
            db,
            source_id=out_tx.id,
            source_kind="ledger",
            destination_id=in_tx.id,
            destination_kind="ledger",
        )
        paired_id = paired_tx.id

        # Simulate legacy DB record that still has stored '/static/...' inside transfer_provenance_registry
        setting = db.query(SystemSetting).filter(SystemSetting.key == "transfer_provenance_registry").first()
        assert setting is not None
        prov_map = json.loads(setting.value)
        prov_map[str(paired_id)]["source_leg"]["receipt_url"] = "/static/receipts/2026/10/out_leg.csv"
        prov_map[str(paired_id)]["destination_leg"]["receipt_url"] = "/static/receipts/2026/10/in_leg.pdf"
        setting.value = json.dumps(prov_map)
        db.commit()

    tx_resp = client.get(f"/api/transactions/{paired_id}")
    assert tx_resp.status_code == 200
    data = tx_resp.json()
    assert data["receipt_url"] == f"/api/transactions/{paired_id}/receipt"
    assert data["destination_receipt_url"] == f"/api/transactions/{paired_id}/receipt?leg=destination"
    assert data["transfer_provenance"]["source_leg"]["receipt_url"] == f"/api/transactions/{paired_id}/receipt"
    assert data["transfer_provenance"]["destination_leg"]["receipt_url"] == f"/api/transactions/{paired_id}/receipt?leg=destination"

    # Existing stored DB setting must NOT have been mutated on read
    with db_registry.get_sessionmaker("default")() as db:
        raw_setting = db.query(SystemSetting).filter(SystemSetting.key == "transfer_provenance_registry").first()
        assert "/static/receipts/2026/10/in_leg.pdf" in raw_setting.value

    src_resp = client.get(data["receipt_url"])
    assert src_resp.status_code == 200
    assert b"-50.00" in src_resp.content

    dest_resp = client.get(data["destination_receipt_url"])
    assert dest_resp.status_code == 200
    assert dest_resp.content == b"%PDF-1.4 DEST_RECEIPT"

    assert client.get(f"/api/transactions/{paired_id}/receipt?leg=invalid").status_code == 422

    # Soft-deleting the paired transfer still preserves access to both receipt legs
    assert client.delete(f"/api/transactions/{paired_id}").status_code == 204
    assert client.get(f"/api/transactions/{paired_id}/receipt").status_code == 200
    assert client.get(f"/api/transactions/{paired_id}/receipt?leg=destination").content == b"%PDF-1.4 DEST_RECEIPT"


def test_staging_item_receipt_authorization_and_profile_isolation(isolated_receipt_env):
    env = isolated_receipt_env
    client: TestClient = env["client"]

    work_prof = profiles_module.create_profile("Side Business")

    default_staged = env["default_staging_dir"] / "default_staged.png"
    default_staged.write_bytes(b"DEFAULT_STAGED_PNG")

    work_staged = work_prof.staging_receipts_dir / "work_staged.jpg"
    work_staged.parent.mkdir(parents=True, exist_ok=True)
    work_staged.write_bytes(b"WORK_STAGED_JPG")

    with db_registry.get_sessionmaker("default")() as db:
        s_def = StagingItem(
            source_type="receipt_image",
            status=StagingStatus.PENDING,
            extracted_merchant="Default Cafe",
            extracted_amount_pence=350,
            temp_file_path="staging_receipts/default_staged.png",
        )
        db.add(s_def)
        db.commit()
        db.refresh(s_def)
        s_def_id = s_def.id

    with db_registry.get_sessionmaker(work_prof.id)() as db:
        s_work = StagingItem(
            source_type="receipt_image",
            status=StagingStatus.PENDING,
            extracted_merchant="Work Supplies",
            extracted_amount_pence=1200,
            temp_file_path=f"profiles/{work_prof.id}/staging_receipts/work_staged.jpg",
        )
        s_trav = StagingItem(
            source_type="receipt_image",
            status=StagingStatus.PENDING,
            extracted_merchant="Traversal Attempt",
            extracted_amount_pence=100,
            temp_file_path="../../profiles.json",
        )
        db.add_all([s_work, s_trav])
        db.commit()
        db.refresh(s_work)
        db.refresh(s_trav)
        s_work_id = s_work.id
        s_trav_id = s_trav.id

    def_item = client.get(f"/api/staging/{s_def_id}").json()
    assert def_item["receipt_url"] == f"/api/staging/{s_def_id}/receipt"
    assert client.get(def_item["receipt_url"]).content == b"DEFAULT_STAGED_PNG"

    # Colliding ID across profiles stays isolated to each profile's own staging DB & files
    assert s_def_id == s_work_id == 1
    assert client.get(f"/api/staging/{s_def_id}/receipt", headers={"X-Profile-ID": work_prof.id}).content == b"WORK_STAGED_JPG"
    # Higher ID present only in Work DB returns 404 in Default profile, and traversal item is rejected in Work
    assert client.get(f"/api/staging/{s_trav_id}/receipt").status_code == 404
    assert client.get(f"/api/staging/{s_trav_id}/receipt", headers={"X-Profile-ID": work_prof.id}).status_code == 404

    work_item = client.get(f"/api/staging/{s_work_id}", headers={"X-Profile-ID": work_prof.id}).json()
    assert work_item["receipt_url"] == f"/api/staging/{s_work_id}/receipt"
    assert client.get(work_item["receipt_url"], headers={"X-Profile-ID": work_prof.id}).content == b"WORK_STAGED_JPG"
