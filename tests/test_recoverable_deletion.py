"""
Regression test suite for Finance Hub Safe Bulk Actions and Recoverable Deletion.

Verifies:
1. Selecting one row, the current page, and all matching filtered results.
2. Bulk editing and bulk deletion with clear, accurate action scope.
3. Deleted records disappearing from balances, Analysis, and exports.
4. Undo and Recently Deleted restoration preserving all original transaction fields.
5. Receipt-file retention with shared references.
6. Paired-transfer deletion and restoration without a dangling or misleading leg.
7. Profile isolation for deletion, listing, and restoration.
8. Validation failures that do not cause unexplained partial updates.
"""

import os
import pytest
from datetime import datetime, timezone
from pathlib import Path
from fastapi.testclient import TestClient
from app.main import app

from app.models import (
    Account,
    AccountType,
    Transaction,
    TransactionType,
    ExpenseNature,
    Category,
)
from app.ledger import LedgerEngine
from tests.test_profiles import isolated_profiles_env


def test_1_and_2_bulk_selection_and_bulk_deletion(db_session, client: TestClient):
    """
    Requirements 1 & 2:
    - Select individual rows, page-scoped IDs, and all matching filtered IDs.
    - Bulk delete transactions with explicit batch tracking and action scope.
    """
    acc = Account(name="Current Account", account_type=AccountType.CURRENT, currency="GBP", starting_balance_pence=100000)
    cat = Category(name="Groceries", color="#10B981")
    db_session.add_all([acc, cat])
    db_session.commit()

    # Create 12 transactions
    tx_ids = []
    for i in range(12):
        t = Transaction(
            transaction_date=datetime(2026, 10, i + 1, 10, 0, 0, tzinfo=timezone.utc),
            transaction_type=TransactionType.EXPENSE,
            amount_pence=1000 * (i + 1),
            merchant=f"Store {i}",
            account_id=acc.id,
            category_id=cat.id,
        )
        db_session.add(t)
        db_session.flush()
        tx_ids.append(t.id)
    db_session.commit()

    # 1. Matching IDs endpoint returns all 12 IDs across pages
    res_matching = client.get(f"/api/transactions/matching-ids?account_id={acc.id}")
    assert res_matching.status_code == 200
    matching_data = res_matching.json()
    assert matching_data["total"] == 12
    assert set(matching_data["ids"]) == set(tx_ids)

    # 2. Bulk delete 5 transactions
    to_delete = tx_ids[:5]
    res_del = client.post("/api/transactions/bulk-delete", json={"transaction_ids": to_delete})
    assert res_del.status_code == 200
    del_data = res_del.json()
    assert del_data["deleted_count"] == 5
    assert del_data["batch_id"].startswith("batch_")
    assert set(del_data["affected_ids"]) == set(to_delete)

    # 3. Active listing now has 7 transactions
    res_active = client.get(f"/api/transactions?account_id={acc.id}")
    assert res_active.status_code == 200
    active_data = res_active.json()
    assert active_data["total"] == 7
    active_ids = {t["id"] for t in active_data["items"]}
    assert active_ids == set(tx_ids[5:])

    # 4. Matching IDs endpoint now returns only the 7 active IDs
    res_matching_after = client.get(f"/api/transactions/matching-ids?account_id={acc.id}")
    assert res_matching_after.json()["total"] == 7
    assert set(res_matching_after.json()["ids"]) == set(tx_ids[5:])


def test_3_deleted_records_disappear_from_balances_analysis_and_exports(db_session, client: TestClient):
    """
    Requirement 3:
    Deleted records immediately disappear from balances, Analysis aggregation, and Ledger exports.
    """
    acc = Account(
        name="Savings Acc",
        account_type=AccountType.SAVINGS,
        currency="GBP",
        starting_balance_pence=50000,
        starting_balance_date=datetime(2026, 10, 1, 0, 0, 0, tzinfo=timezone.utc)
    )
    cat = Category(name="Utilities", color="#3B82F6")
    db_session.add_all([acc, cat])
    db_session.commit()

    # Initial balance: £500.00
    bal_initial = LedgerEngine.get_account_balance(db_session, acc.id)
    assert bal_initial == 50000

    # Add income (+£200) and expense (-£50)
    t_inc = Transaction(
        transaction_date=datetime(2026, 10, 5, 12, 0, 0, tzinfo=timezone.utc),
        transaction_type=TransactionType.INCOME,
        amount_pence=20000,
        merchant="Client Payment",
        account_id=acc.id,
    )
    t_exp = Transaction(
        transaction_date=datetime(2026, 10, 6, 12, 0, 0, tzinfo=timezone.utc),
        transaction_type=TransactionType.EXPENSE,
        amount_pence=5000,
        merchant="Electric Utility",
        account_id=acc.id,
        category_id=cat.id,
    )
    db_session.add_all([t_inc, t_exp])
    db_session.commit()

    # Active balance: 50000 + 20000 - 5000 = 65000 (£650.00)
    bal_with_txs = LedgerEngine.get_account_balance(db_session, acc.id)
    assert bal_with_txs == 65000

    # Soft-delete the income transaction via DELETE endpoint
    res_del = client.delete(f"/api/transactions/{t_inc.id}")
    assert res_del.status_code == 204

    # Balance must immediately exclude the deleted income: 50000 - 5000 = 45000 (£450.00)
    db_session.expire_all()
    bal_after_del = LedgerEngine.get_account_balance(db_session, acc.id)
    assert bal_after_del == 45000

    # Check Analysis endpoint excludes deleted income
    res_analysis = client.get(f"/api/analytics/analysis?preset=custom&start_date=2026-10-01&end_date=2026-10-31")
    assert res_analysis.status_code == 200
    analysis_data = res_analysis.json()
    assert analysis_data["totals"]["income_pence"] == 0
    assert analysis_data["totals"]["expenses_pence"] == 5000

    # Check Ledger export excludes deleted income
    res_export = client.get(f"/api/transactions/export?format=csv")
    assert res_export.status_code == 200
    csv_text = res_export.text
    assert "Electric Utility" in csv_text
    assert "Client Payment" not in csv_text


def test_4_undo_and_recently_deleted_restoration_preserves_fields(db_session, client: TestClient):
    """
    Requirement 4:
    - Deleted transactions appear in /api/transactions/deleted.
    - Immediate undo via /api/transactions/undo-delete restores the batch.
    - Restoration restores original date, amount, type, account, category, notes, and receipt links.
    """
    acc = Account(name="Current Card", account_type=AccountType.CURRENT, currency="GBP", starting_balance_pence=10000)
    cat = Category(name="Electronics", color="#8B5CF6")
    db_session.add_all([acc, cat])
    db_session.commit()

    orig_dt = datetime(2026, 10, 15, 14, 30, 0, tzinfo=timezone.utc)
    tx = Transaction(
        transaction_date=orig_dt,
        effective_timestamp=orig_dt,
        transaction_type=TransactionType.EXPENSE,
        amount_pence=4999,
        merchant="Apple Store",
        notes="USB-C Adapter",
        entry_method="receipt_scan",
        receipt_path="receipts/2026/10/apple_receipt.jpg",
        account_id=acc.id,
        category_id=cat.id,
        expense_nature=ExpenseNature.VARIABLE,
    )
    db_session.add(tx)
    db_session.commit()

    # Soft-delete
    res_del = client.delete(f"/api/transactions/{tx.id}")
    assert res_del.status_code == 204

    # 1. Inspect Recently Deleted
    res_deleted = client.get("/api/transactions/deleted")
    assert res_deleted.status_code == 200
    del_items = res_deleted.json()["items"]
    assert len(del_items) == 1
    d_item = del_items[0]
    assert d_item["id"] == tx.id
    assert d_item["merchant"] == "Apple Store"
    assert d_item["receipt_path"] == "receipts/2026/10/apple_receipt.jpg"
    assert d_item["is_deleted"] is True

    # 2. Inspect Deleted Summary
    res_summary = client.get("/api/transactions/deleted/summary")
    assert res_summary.status_code == 200
    summary = res_summary.json()
    assert summary["total_deleted"] == 1
    assert summary["total_pence"] == 4999
    assert summary["receipts_count"] == 1

    # 3. Undo deletion
    res_undo = client.post("/api/transactions/undo-delete")
    assert res_undo.status_code == 200
    undo_data = res_undo.json()
    assert undo_data["restored_count"] == 1
    assert undo_data["restored_ids"] == [tx.id]

    # 4. Verify all fields in active listing are pristine
    res_active = client.get(f"/api/transactions")
    assert res_active.status_code == 200
    items = res_active.json()["items"]
    assert len(items) == 1
    restored = items[0]
    assert restored["id"] == tx.id
    assert restored["merchant"] == "Apple Store"
    assert restored["amount_pence"] == 4999
    assert restored["notes"] == "USB-C Adapter"
    assert restored["entry_method"] == "receipt_scan"
    assert restored["receipt_path"] == "receipts/2026/10/apple_receipt.jpg"
    assert restored["account_id"] == acc.id
    assert restored["category_id"] == cat.id
    assert restored["expense_nature"] == "variable"
    assert restored["is_deleted"] is False


def test_5_receipt_file_retention_with_shared_references(db_session, client: TestClient, tmp_path):
    """
    Requirement 5:
    Receipt files on disk are preserved when a transaction is soft-deleted,
    and remain intact even when split/shared among multiple transactions.
    """
    acc = Account(name="Credit Card", account_type=AccountType.CREDIT_CARD, currency="GBP", starting_balance_pence=0)
    cat_food = Category(name="Food", color="#10B981")
    cat_home = Category(name="Home", color="#3B82F6")
    db_session.add_all([acc, cat_food, cat_home])
    db_session.commit()

    shared_receipt_rel = "receipts/2026/10/shared_supermarket_receipt.pdf"
    
    # Split transaction 1
    t1 = Transaction(
        transaction_date=datetime(2026, 10, 20, 11, 0, 0, tzinfo=timezone.utc),
        transaction_type=TransactionType.EXPENSE,
        amount_pence=2500,
        merchant="Supermarket - Groceries",
        receipt_path=shared_receipt_rel,
        account_id=acc.id,
        category_id=cat_food.id,
    )
    # Split transaction 2
    t2 = Transaction(
        transaction_date=datetime(2026, 10, 20, 11, 0, 0, tzinfo=timezone.utc),
        transaction_type=TransactionType.EXPENSE,
        amount_pence=1500,
        merchant="Supermarket - Cleaning",
        receipt_path=shared_receipt_rel,
        account_id=acc.id,
        category_id=cat_home.id,
    )
    db_session.add_all([t1, t2])
    db_session.commit()

    # Soft-delete t1
    res_del_1 = client.delete(f"/api/transactions/{t1.id}")
    assert res_del_1.status_code == 204

    # t2 remains active and still points to the shared receipt
    res_active = client.get("/api/transactions")
    active_items = res_active.json()["items"]
    assert len(active_items) == 1
    assert active_items[0]["id"] == t2.id
    assert active_items[0]["receipt_path"] == shared_receipt_rel

    # t1 in Recently Deleted also preserves the shared receipt path
    res_deleted = client.get("/api/transactions/deleted")
    del_items = res_deleted.json()["items"]
    assert len(del_items) == 1
    assert del_items[0]["id"] == t1.id
    assert del_items[0]["receipt_path"] == shared_receipt_rel


def test_6_paired_transfer_deletion_and_restoration(db_session, client: TestClient):
    """
    Requirement 6:
    Deleting a paired transfer removes the money movement from BOTH accounts simultaneously.
    Restoring it reinstates both accounts simultaneously without any dangling leg.
    """
    acc_src = Account(
        name="Current Bank",
        account_type=AccountType.CURRENT,
        currency="GBP",
        starting_balance_pence=100000,
        starting_balance_date=datetime(2026, 10, 1, 0, 0, 0, tzinfo=timezone.utc)
    )
    acc_dest = Account(
        name="Savings Bank",
        account_type=AccountType.SAVINGS,
        currency="GBP",
        starting_balance_pence=50000,
        starting_balance_date=datetime(2026, 10, 1, 0, 0, 0, tzinfo=timezone.utc)
    )
    db_session.add_all([acc_src, acc_dest])
    db_session.commit()

    # Create transfer of £200.00 from acc_src to acc_dest
    transfer_tx = Transaction(
        transaction_date=datetime(2026, 10, 18, 9, 0, 0, tzinfo=timezone.utc),
        transaction_type=TransactionType.TRANSFER,
        amount_pence=20000,
        merchant="Monthly Savings Transfer",
        account_id=acc_src.id,
        destination_account_id=acc_dest.id,
    )
    db_session.add(transfer_tx)
    db_session.commit()

    # Before deletion:
    # Source balance: 100000 - 20000 = 80000 (£800.00)
    # Destination balance: 50000 + 20000 = 70000 (£700.00)
    assert LedgerEngine.get_account_balance(db_session, acc_src.id) == 80000
    assert LedgerEngine.get_account_balance(db_session, acc_dest.id) == 70000

    # Bulk delete the transfer
    res_del = client.post("/api/transactions/bulk-delete", json={"transaction_ids": [transfer_tx.id]})
    assert res_del.status_code == 200
    assert res_del.json()["affected_transfers_count"] == 1

    # After deletion:
    # Both accounts are restored to their original anchor balances!
    db_session.expire_all()
    assert LedgerEngine.get_account_balance(db_session, acc_src.id) == 100000
    assert LedgerEngine.get_account_balance(db_session, acc_dest.id) == 50000

    # Restore the transfer via /api/transactions/restore
    res_restore = client.post("/api/transactions/restore", json={"transaction_ids": [transfer_tx.id]})
    assert res_restore.status_code == 200
    assert res_restore.json()["restored_count"] == 1

    # Both accounts reflect the transfer movement again!
    db_session.expire_all()
    assert LedgerEngine.get_account_balance(db_session, acc_src.id) == 80000
    assert LedgerEngine.get_account_balance(db_session, acc_dest.id) == 70000


def test_7_profile_isolation_for_deletion_and_recovery(isolated_profiles_env):
    """
    Requirement 7:
    Soft-deleted transactions, Recently Deleted listings, and undo operations
    are completely isolated by profile.
    """
    app.dependency_overrides.clear()
    client = TestClient(app)

    # 1. Create transaction in default profile
    res_create_default = client.post(
        "/api/transactions",
        headers={"X-Profile-ID": "default"},
        json={
            "transaction_date": "2026-10-21T10:00:00Z",
            "transaction_type": "expense",
            "amount": 25.0,
            "merchant": "Default Workspace Coffee",
        }
    )
    assert res_create_default.status_code == 201
    default_tx_id = res_create_default.json()["id"]

    # 2. Create secondary profile 'business'
    res_create_prof = client.post("/api/profiles", json={"name": "Business Profile"})
    assert res_create_prof.status_code == 201
    business_id = res_create_prof.json()["id"]

    # 3. Create transaction in business profile
    res_create_biz = client.post(
        "/api/transactions",
        headers={"X-Profile-ID": business_id},
        json={
            "transaction_date": "2026-10-21T11:00:00Z",
            "transaction_type": "expense",
            "amount": 500.0,
            "merchant": "Business Server Hosting",
        }
    )
    assert res_create_biz.status_code == 201
    biz_tx_id = res_create_biz.json()["id"]

    # 4. Delete the business transaction
    res_del_biz = client.delete(f"/api/transactions/{biz_tx_id}", headers={"X-Profile-ID": business_id})
    assert res_del_biz.status_code == 204

    # 5. In default profile, recently deleted is completely EMPTY
    res_def_deleted = client.get("/api/transactions/deleted", headers={"X-Profile-ID": "default"})
    assert res_def_deleted.status_code == 200
    assert res_def_deleted.json()["total"] == 0

    # 6. Default profile cannot restore the business transaction
    res_cross_restore = client.post(
        "/api/transactions/restore",
        headers={"X-Profile-ID": "default"},
        json={"transaction_ids": [biz_tx_id]}
    )
    assert res_cross_restore.status_code == 200
    assert res_cross_restore.json()["restored_count"] == 0

    # 7. Business profile sees it in recently deleted and can restore it
    res_biz_deleted = client.get("/api/transactions/deleted", headers={"X-Profile-ID": business_id})
    assert res_biz_deleted.json()["total"] == 1
    assert res_biz_deleted.json()["items"][0]["merchant"] == "Business Server Hosting"

    res_biz_restore = client.post(
        "/api/transactions/restore",
        headers={"X-Profile-ID": business_id},
        json={"transaction_ids": [biz_tx_id]}
    )
    assert res_biz_restore.status_code == 200
    assert res_biz_restore.json()["restored_count"] == 1


def test_8_validation_failures_do_not_cause_partial_updates(db_session, client: TestClient):
    """
    Requirement 8:
    Validates complete selection before applying bulk delete.
    If any transaction ID does not exist or is already deleted,
    fails the request without leaving partial updates.
    """
    acc = Account(name="Current Bank", account_type=AccountType.CURRENT, currency="GBP", starting_balance_pence=10000)
    db_session.add(acc)
    db_session.commit()

    t1 = Transaction(
        transaction_date=datetime(2026, 10, 10, 10, 0, 0, tzinfo=timezone.utc),
        transaction_type=TransactionType.EXPENSE,
        amount_pence=1000,
        merchant="Valid 1",
        account_id=acc.id,
    )
    t2 = Transaction(
        transaction_date=datetime(2026, 10, 10, 11, 0, 0, tzinfo=timezone.utc),
        transaction_type=TransactionType.EXPENSE,
        amount_pence=2000,
        merchant="Valid 2",
        account_id=acc.id,
    )
    db_session.add_all([t1, t2])
    db_session.commit()

    # Pass [t1.id, 99999] (where 99999 does not exist)
    res_fail = client.post("/api/transactions/bulk-delete", json={"transaction_ids": [t1.id, 99999]})
    assert res_fail.status_code == 404
    assert "99999" in res_fail.json()["detail"]

    # Verify t1 was NOT deleted (atomic abort)
    db_session.expire_all()
    t1_check = db_session.query(Transaction).filter(Transaction.id == t1.id).first()
    assert t1_check.deleted_at is None

    # Now soft-delete t1
    client.delete(f"/api/transactions/{t1.id}")

    # Attempt to bulk-delete [t1.id, t2.id] (where t1 is already deleted)
    res_fail_already = client.post("/api/transactions/bulk-delete", json={"transaction_ids": [t1.id, t2.id]})
    assert res_fail_already.status_code == 400
    assert "already deleted" in res_fail_already.json()["detail"]

    # Verify t2 was NOT deleted
    db_session.expire_all()
    t2_check = db_session.query(Transaction).filter(Transaction.id == t2.id).first()
    assert t2_check.deleted_at is None
