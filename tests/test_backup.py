import json
import sqlite3
import zipfile
from datetime import datetime, timezone, timedelta
from pathlib import Path

import openpyxl
import pytest

from app.core.backup import (
    generate_backup_bundle,
    list_existing_backups,
    evaluate_backup_schedule,
    compute_next_backup_due_date,
    set_system_setting,
    get_system_setting
)
from app.restore import perform_restore
from app.models import (
    Account, AccountType, Category, Transaction, TransactionType, 
    ExpenseNature, AssetSnapshot
)

def test_generate_backup_bundle_and_verify_contents(db_session, tmp_path):
    # 1. Populate test data
    acc = Account(
        name="Main Current Account",
        account_type=AccountType.CURRENT,
        starting_balance_pence=100000,
        currency="GBP"
    )
    db_session.add(acc)
    db_session.commit()
    db_session.refresh(acc)

    cat = Category(
        name="Groceries",
        default_expense_nature=ExpenseNature.VARIABLE
    )
    db_session.add(cat)
    db_session.commit()
    db_session.refresh(cat)

    tx = Transaction(
        transaction_date=datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc),
        transaction_type=TransactionType.EXPENSE,
        amount_pence=4550,
        merchant="Waitrose Supermarket",
        account_id=acc.id,
        category_id=cat.id,
        expense_nature=ExpenseNature.VARIABLE,
        notes="Weekly grocery shopping"
    )
    db_session.add(tx)

    snap = AssetSnapshot(
        account_id=acc.id,
        valuation_pence=100000,
        effective_date=datetime(2026, 10, 1, tzinfo=timezone.utc),
        notes="Quarterly reading"
    )
    db_session.add(snap)
    db_session.commit()

    # Create dummy staging and archive receipt files
    staging_dir = tmp_path / "staging_receipts"
    archive_dir = tmp_path / "receipts"
    staging_dir.mkdir(parents=True)
    archive_dir.mkdir(parents=True)
    (staging_dir / "test_staging_receipt.jpg").write_text("dummy staging receipt content")
    (archive_dir / "test_archive_receipt.jpg").write_text("dummy archive receipt content")

    backup_dir = tmp_path / "backups"

    # 2. Run backup generator
    result = generate_backup_bundle(
        db_session,
        backup_dir=backup_dir,
        staging_receipts_dir=staging_dir,
        archive_receipts_dir=archive_dir
    )

    assert result["success"] is True
    zip_path = Path(result["filepath"])
    assert zip_path.exists()
    assert zip_path.stat().st_size > 0

    # 3. Unpack and verify contents
    extract_dir = tmp_path / "unpacked"
    with zipfile.ZipFile(zip_path, "r") as zf:
        assert zf.testzip() is None
        zf.extractall(extract_dir)

    # Check database.db snapshot
    unpacked_db = extract_dir / "database.db"
    assert unpacked_db.exists()
    with sqlite3.connect(unpacked_db) as conn:
        cursor = conn.cursor()
        cursor.execute("PRAGMA integrity_check;")
        assert cursor.fetchall() == [("ok",)]
        cursor.execute("SELECT name FROM accounts WHERE id = ?", (acc.id,))
        assert cursor.fetchone()[0] == "Main Current Account"

    # Check receipts
    assert (extract_dir / "receipts" / "staging" / "test_staging_receipt.jpg").exists()
    assert (extract_dir / "receipts" / "archive" / "test_archive_receipt.jpg").exists()

    # Check manifest.json
    manifest_path = extract_dir / "manifest.json"
    assert manifest_path.exists()
    with open(manifest_path, "r") as f:
        manifest = json.load(f)
    assert manifest["counts"]["accounts"] == 1
    assert manifest["counts"]["transactions"] == 1
    assert manifest["counts"]["receipt_files"] == 2
    assert "database.db" in manifest["sha256"]

    # Check Excel workbook
    excel_path = extract_dir / "finance_hub_summary.xlsx"
    assert excel_path.exists()
    wb = openpyxl.load_workbook(excel_path)
    sheet_names = wb.sheetnames
    assert "Summary" in sheet_names
    assert "Accounts" in sheet_names
    assert "Transactions" in sheet_names
    assert "Categories" in sheet_names
    assert "Cash Flow" in sheet_names
    assert "Investments" in sheet_names

    # Check currency code in Accounts sheet
    ws_acc = wb["Accounts"]
    headers = [cell.value for cell in ws_acc[1]]
    assert "Currency" in headers
    currency_idx = headers.index("Currency") + 1
    assert ws_acc.cell(row=2, column=currency_idx).value == "GBP"

    # Check Transactions sheet has 1 row for transaction
    ws_tx = wb["Transactions"]
    assert ws_tx.max_row == 2  # 1 header + 1 record
    assert ws_tx.cell(row=2, column=4).value == "Waitrose Supermarket"

def test_backup_automation_schedule_and_reminder(db_session, tmp_path):
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir(parents=True)

    # 1. Default state: Automation is OFF
    status = evaluate_backup_schedule(db_session, backup_dir=backup_dir)
    assert status["backup_automation_enabled"] is False
    assert status["backup_frequency_days"] == 30
    assert status["is_backup_overdue"] is True
    assert "Backup recommended" in status["overdue_message"]
    # Verify no backup was created automatically when OFF
    assert len(list_existing_backups(backup_dir)) == 0

    # 2. Turn automation ON and verify it creates a backup when due
    set_system_setting(db_session, "backup_automation_enabled", "true")
    # Reset last check timestamp to allow trigger
    set_system_setting(db_session, "last_backup_check_at", "")

    status2 = evaluate_backup_schedule(db_session, backup_dir=backup_dir)
    assert status2["backup_automation_enabled"] is True
    assert status2["is_backup_overdue"] is False
    assert status2["overdue_message"] is None
    # Now a backup exists
    existing = list_existing_backups(backup_dir)
    assert len(existing) == 1

def test_backup_api_endpoints(client, db_session, tmp_path, monkeypatch):
    # Route backups to tmp_path
    monkeypatch.setattr("app.api.system.BACKUP_DIR", tmp_path / "api_backups")
    monkeypatch.setattr("app.core.backup.BACKUP_DIR", tmp_path / "api_backups")

    # 1. Check initial status
    res = client.get("/api/system/backup-status")
    assert res.status_code == 200
    assert res.json()["backup_automation_enabled"] is False

    # 2. Update automation settings
    upd = client.put("/api/system/settings", json={
        "backup_automation_enabled": True,
        "backup_frequency_days": 14
    })
    assert upd.status_code == 200
    assert upd.json()["backup_automation_enabled"] is True
    assert upd.json()["backup_frequency_days"] == 14

    # 3. Trigger manual backup creation
    create_res = client.post("/api/system/backup")
    assert create_res.status_code == 201
    data = create_res.json()
    assert data["success"] is True
    filename = data["filename"]

    # 4. List backups
    list_res = client.get("/api/system/backups")
    assert list_res.status_code == 200
    archives = list_res.json()
    assert len(archives) >= 1
    assert archives[0]["filename"] == filename

    # 5. Download backup
    dl_res = client.get(f"/api/system/backups/{filename}/download")
    assert dl_res.status_code == 200
    assert dl_res.headers["content-type"] == "application/zip"

def test_offline_restore_validation_and_rollback(tmp_path, db_session):
    # Setup test file database
    target_db = tmp_path / "live" / "finances.db"
    target_db.parent.mkdir(parents=True)
    staging_rec = tmp_path / "live" / "staging_receipts"
    archive_rec = tmp_path / "live" / "receipts"
    staging_rec.mkdir(parents=True)
    archive_rec.mkdir(parents=True)
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir(parents=True)

    # Initialize live DB with initial account
    with sqlite3.connect(target_db) as conn:
        conn.execute("CREATE TABLE accounts (id INTEGER PRIMARY KEY, name TEXT);")
        conn.execute("INSERT INTO accounts (name) VALUES ('Initial Live Account');")
        conn.commit()

    # Create a valid backup bundle using db_session
    acc = Account(name="Restored Account", account_type=AccountType.CURRENT, starting_balance_pence=5000)
    db_session.add(acc)
    db_session.commit()

    bundle_res = generate_backup_bundle(
        db_session,
        backup_dir=backup_dir,
        staging_receipts_dir=staging_rec,
        archive_receipts_dir=archive_rec
    )
    backup_zip = Path(bundle_res["filepath"])

    # Perform offline restore on the test target DB
    success = perform_restore(
        backup_zip,
        db_path=target_db,
        backup_dir=backup_dir,
        staging_receipts_dir=staging_rec,
        archive_receipts_dir=archive_rec,
        port=59999,
        force_lock=True
    )
    assert success is True

    # Verify restored content in target_db
    with sqlite3.connect(target_db) as conn:
        cursor = conn.cursor()
        cursor.execute("PRAGMA integrity_check;")
        assert cursor.fetchall() == [("ok",)]
        cursor.execute("SELECT name FROM accounts WHERE name = 'Restored Account';")
        assert cursor.fetchone() is not None

    # Verify pre-restore safety copy was created
    pre_restore_copies = list(backup_dir.glob("pre_restore_*"))
    assert len(pre_restore_copies) == 1
    assert (pre_restore_copies[0] / "finances.db").exists()


def test_calendar_month_due_date_calculation_and_month_end_clamping():
    # 1. Non-leap year Jan 31 -> Feb 28
    dt_jan31_nonleap = datetime(2025, 1, 31, 14, 30, tzinfo=timezone.utc)
    next_feb = compute_next_backup_due_date(dt_jan31_nonleap, 30)
    assert next_feb == datetime(2025, 2, 28, 14, 30, tzinfo=timezone.utc)

    # 2. Leap year Jan 31 -> Feb 29 (2024 is a leap year)
    dt_jan31_leap = datetime(2024, 1, 31, 10, 0, tzinfo=timezone.utc)
    next_feb_leap = compute_next_backup_due_date(dt_jan31_leap, "monthly")
    assert next_feb_leap == datetime(2024, 2, 29, 10, 0, tzinfo=timezone.utc)

    # 3. Month with 31 days to month with 30 days: Mar 31 -> Apr 30
    dt_mar31 = datetime(2026, 3, 31, 8, 15, tzinfo=timezone.utc)
    next_apr = compute_next_backup_due_date(dt_mar31, "1m")
    assert next_apr == datetime(2026, 4, 30, 8, 15, tzinfo=timezone.utc)

    # 4. Aug 31 -> Sep 30
    dt_aug31 = datetime(2026, 8, 31, 12, 0, tzinfo=timezone.utc)
    next_sep = compute_next_backup_due_date(dt_aug31, 30)
    assert next_sep == datetime(2026, 9, 30, 12, 0, tzinfo=timezone.utc)

    # 5. Year turnover: Dec 31 -> Jan 31
    dt_dec31 = datetime(2026, 12, 31, 23, 59, tzinfo=timezone.utc)
    next_jan = compute_next_backup_due_date(dt_dec31, 30)
    assert next_jan == datetime(2027, 1, 31, 23, 59, tzinfo=timezone.utc)

    # 6. Quarterly (+3 calendar months with clamping): Aug 31 -> Nov 30
    next_quarter = compute_next_backup_due_date(dt_aug31, 90)
    assert next_quarter == datetime(2026, 11, 30, 12, 0, tzinfo=timezone.utc)

    # 7. Bi-weekly (+14 days)
    dt_mid_month = datetime(2026, 10, 5, 10, 0, tzinfo=timezone.utc)
    next_biweekly = compute_next_backup_due_date(dt_mid_month, 14)
    assert next_biweekly == datetime(2026, 10, 19, 10, 0, tzinfo=timezone.utc)

    # 8. Custom day interval (+45 days)
    next_custom = compute_next_backup_due_date(dt_mid_month, 45)
    assert next_custom == dt_mid_month + timedelta(days=45)


def test_backup_workbook_and_manifest_respect_non_gbp_base_currency(db_session, tmp_path, monkeypatch):
    """Backup Excel summary/cashflow labels and manifest schema_revision must reflect active DB state."""
    from app.core.currency import get_effective_base_currency
    from app.database import get_alembic_head_revision

    monkeypatch.setenv("BASE_CURRENCY", "USD")
    assert get_effective_base_currency(db_session) == "USD"

    acc = Account(
        name="Checking USD",
        account_type=AccountType.CURRENT,
        starting_balance_pence=25000,
        currency="USD",
    )
    db_session.add(acc)
    db_session.commit()
    db_session.refresh(acc)

    tx = Transaction(
        transaction_date=datetime(2026, 11, 5, 12, 0, tzinfo=timezone.utc),
        transaction_type=TransactionType.EXPENSE,
        amount_pence=1250,
        merchant="Unassigned Coffee",
        account_id=None,
        expense_nature=ExpenseNature.VARIABLE,
    )
    db_session.add(tx)
    db_session.commit()

    res = generate_backup_bundle(
        db_session,
        backup_dir=tmp_path / "usd_backups",
        staging_receipts_dir=tmp_path / "staging",
        archive_receipts_dir=tmp_path / "archive",
    )
    assert res["manifest"]["schema_revision"] == get_alembic_head_revision()

    with zipfile.ZipFile(res["filepath"], "r") as zf:
        with zf.open("finance_hub_summary.xlsx") as xf:
            wb = openpyxl.load_workbook(xf)
            assert wb["Summary"]["B5"].value == "Amount ($)"
            assert wb["Cash Flow"].cell(row=2, column=6).value == "USD"
            assert wb["Transactions"].cell(row=2, column=6).value == "USD"


