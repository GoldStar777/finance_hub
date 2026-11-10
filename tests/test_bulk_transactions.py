"""
Regression test suite for Finance Hub Safe Bulk Editing.

Verifies the 9 requirements from the bulk editing specification:
1. Selecting individual rows and selecting all rows on the current page.
2. Selecting all transactions matching current filters across pages (matching IDs endpoint).
3. Bulk conversion from Income to Expense and Expense to Income, with amounts preserved.
4. Bulk category changes and explicit clearing to Uncategorised.
5. Bulk account assignment, including explicit Unassigned where valid.
6. Unselected fields and timestamps remaining unchanged.
7. Validation failure causing no partial updates.
8. Transfer and reconciliation adjustment restrictions.
9. Profile isolation and correct scoping.
"""

import pytest
from datetime import datetime, timezone
from decimal import Decimal
from fastapi.testclient import TestClient

from app.models import (
    Account,
    AccountType,
    Transaction,
    TransactionType,
    ExpenseNature,
    Category,
)
from app.main import app
from app.ledger import LedgerEngine
from tests.test_profiles import isolated_profiles_env


def test_1_and_2_matching_transaction_ids_and_pagination(db_session, client: TestClient):
    """
    Requirements 1 & 2:
    Pagination on /transactions, and fetching matching transaction IDs across pages
    via /transactions/matching-ids with active filters and search.
    """
    acc_a = Account(name="Current A", account_type=AccountType.CURRENT, currency="GBP", starting_balance_pence=100000)
    acc_b = Account(name="Current B", account_type=AccountType.CURRENT, currency="GBP", starting_balance_pence=100000)
    cat_dining = Category(name="Dining", color="#EF4444")
    db_session.add_all([acc_a, acc_b, cat_dining])
    db_session.commit()

    # Create 30 transactions: 15 for acc_a (merchant 'Coffee'), 15 for acc_b (merchant 'Stationery')
    for i in range(15):
        db_session.add(
            Transaction(
                transaction_date=datetime(2026, 10, i + 1, 12, 0, 0, tzinfo=timezone.utc),
                transaction_type=TransactionType.EXPENSE,
                amount_pence=500 + i * 100,
                merchant=f"Coffee Shop {i}",
                account_id=acc_a.id,
                category_id=cat_dining.id,
            )
        )
    for i in range(15):
        db_session.add(
            Transaction(
                transaction_date=datetime(2026, 10, i + 1, 14, 0, 0, tzinfo=timezone.utc),
                transaction_type=TransactionType.EXPENSE,
                amount_pence=1000 + i * 100,
                merchant=f"Stationery Store {i}",
                account_id=acc_b.id,
            )
        )
    db_session.commit()

    # 1. Page-based listing with limit=10
    res_page = client.get(f"/api/transactions?account_id={acc_a.id}&limit=10&offset=0")
    assert res_page.status_code == 200
    data_page = res_page.json()
    assert len(data_page["items"]) == 10
    assert data_page["total"] == 15

    # 2. Matching IDs endpoint returns all 15 IDs across all pages
    res_ids = client.get(f"/api/transactions/matching-ids?account_id={acc_a.id}")
    assert res_ids.status_code == 200
    data_ids = res_ids.json()
    assert data_ids["total"] == 15
    assert len(data_ids["ids"]) == 15

    # 3. Matching IDs with search term 'Coffee'
    res_search = client.get("/api/transactions/matching-ids?q=Coffee")
    assert res_search.status_code == 200
    assert res_search.json()["total"] == 15

    # 4. Matching IDs with category filter
    res_cat = client.get(f"/api/transactions/matching-ids?category_id={cat_dining.id}")
    assert res_cat.status_code == 200
    assert res_cat.json()["total"] == 15


def test_3_bulk_conversion_income_expense_preserves_amount(db_session, client: TestClient):
    """
    Requirement 3:
    Bulk conversion from Income to Expense and Expense to Income, with amounts preserved.
    """
    acc = Account(
        name="Current",
        account_type=AccountType.CURRENT,
        currency="GBP",
        starting_balance_pence=100000,
        starting_balance_date=datetime(2026, 10, 1, 0, 0, 0, tzinfo=timezone.utc),
    )
    db_session.add(acc)
    db_session.commit()

    # Create 3 Income transactions (e.g. wrongly classified imports)
    tx1 = Transaction(
        transaction_date=datetime(2026, 10, 5, 10, 0, 0, tzinfo=timezone.utc),
        transaction_type=TransactionType.INCOME,
        amount_pence=1250,  # £12.50
        merchant="Pret A Manger",
        account_id=acc.id,
    )
    tx2 = Transaction(
        transaction_date=datetime(2026, 10, 6, 11, 0, 0, tzinfo=timezone.utc),
        transaction_type=TransactionType.INCOME,
        amount_pence=4500,  # £45.00
        merchant="Sainsbury's",
        account_id=acc.id,
    )
    tx3 = Transaction(
        transaction_date=datetime(2026, 10, 7, 12, 0, 0, tzinfo=timezone.utc),
        transaction_type=TransactionType.INCOME,
        amount_pence=9900,  # £99.00
        merchant="Trainline",
        account_id=acc.id,
    )
    db_session.add_all([tx1, tx2, tx3])
    db_session.commit()

    # Pre-conversion: All are Income
    assert LedgerEngine.get_account_balance(db_session, acc.id) == 100000 + 1250 + 4500 + 9900

    # 1. Bulk Convert to Expense
    res = client.post(
        "/api/transactions/bulk",
        json={
            "transaction_ids": [tx1.id, tx2.id, tx3.id],
            "update_transaction_type": True,
            "transaction_type": "expense",
        }
    )
    assert res.status_code == 200
    data = res.json()
    assert data["updated_count"] == 3

    # Verification in DB:
    db_session.expire_all()
    t1 = db_session.query(Transaction).filter(Transaction.id == tx1.id).first()
    t2 = db_session.query(Transaction).filter(Transaction.id == tx2.id).first()
    t3 = db_session.query(Transaction).filter(Transaction.id == tx3.id).first()

    assert t1.transaction_type == TransactionType.EXPENSE
    assert t1.amount_pence == 1250  # EXACT AMOUNT PRESERVED
    assert t2.transaction_type == TransactionType.EXPENSE
    assert t2.amount_pence == 4500
    assert t3.transaction_type == TransactionType.EXPENSE
    assert t3.amount_pence == 9900

    # Account balance now reflects deductions
    assert LedgerEngine.get_account_balance(db_session, acc.id) == 100000 - 1250 - 4500 - 9900

    # 2. Bulk Convert back from Expense to Income
    res2 = client.post(
        "/api/transactions/bulk",
        json={
            "transaction_ids": [tx1.id, tx2.id],
            "update_transaction_type": True,
            "transaction_type": "income",
        }
    )
    assert res2.status_code == 200
    assert res2.json()["updated_count"] == 2

    db_session.expire_all()
    t1_after = db_session.query(Transaction).filter(Transaction.id == tx1.id).first()
    t2_after = db_session.query(Transaction).filter(Transaction.id == tx2.id).first()
    assert t1_after.transaction_type == TransactionType.INCOME
    assert t1_after.amount_pence == 1250
    assert t2_after.transaction_type == TransactionType.INCOME
    assert t2_after.amount_pence == 4500


def test_4_bulk_category_updates_and_clearing_to_uncategorised(db_session, client: TestClient):
    """
    Requirement 4:
    Bulk category changes and explicit clearing to Uncategorised.
    """
    acc = Account(
        name="Current",
        account_type=AccountType.CURRENT,
        currency="GBP",
        starting_balance_pence=100000,
        starting_balance_date=datetime(2026, 10, 1, 0, 0, 0, tzinfo=timezone.utc),
    )
    cat_groceries = Category(name="Groceries", color="#10B981", default_expense_nature=ExpenseNature.VARIABLE)
    cat_leisure = Category(name="Leisure", color="#8B5CF6", default_expense_nature=ExpenseNature.VARIABLE)
    db_session.add_all([acc, cat_groceries, cat_leisure])
    db_session.commit()

    tx1 = Transaction(transaction_type=TransactionType.EXPENSE, amount_pence=1000, merchant="Store 1", account_id=acc.id)
    tx2 = Transaction(transaction_type=TransactionType.EXPENSE, amount_pence=2000, merchant="Store 2", account_id=acc.id)
    tx3 = Transaction(transaction_type=TransactionType.EXPENSE, amount_pence=3000, merchant="Store 3", account_id=acc.id)
    db_session.add_all([tx1, tx2, tx3])
    db_session.commit()

    # 1. Bulk assign to Groceries
    res = client.post(
        "/api/transactions/bulk",
        json={
            "transaction_ids": [tx1.id, tx2.id, tx3.id],
            "update_category": True,
            "category_id": cat_groceries.id,
        }
    )
    assert res.status_code == 200
    assert res.json()["updated_count"] == 3

    db_session.expire_all()
    for tx_id in [tx1.id, tx2.id, tx3.id]:
        tx = db_session.query(Transaction).filter(Transaction.id == tx_id).first()
        assert tx.category_id == cat_groceries.id

    # 2. Bulk explicitly clear category to Uncategorised (category_id = None)
    res_clear = client.post(
        "/api/transactions/bulk",
        json={
            "transaction_ids": [tx1.id, tx2.id],
            "update_category": True,
            "category_id": None,  # Explicit Uncategorised!
        }
    )
    assert res_clear.status_code == 200
    assert res_clear.json()["updated_count"] == 2

    db_session.expire_all()
    t1 = db_session.query(Transaction).filter(Transaction.id == tx1.id).first()
    t2 = db_session.query(Transaction).filter(Transaction.id == tx2.id).first()
    t3 = db_session.query(Transaction).filter(Transaction.id == tx3.id).first()
    assert t1.category_id is None
    assert t2.category_id is None
    assert t3.category_id == cat_groceries.id  # Untouched transaction 3 retains Groceries!


def test_5_bulk_account_assignment_and_explicit_unassigned(db_session, client: TestClient):
    """
    Requirement 5:
    Bulk account assignment, including explicit Unassigned where valid.
    """
    acc1 = Account(name="Account 1", account_type=AccountType.CURRENT, currency="GBP", starting_balance_pence=100000)
    acc2 = Account(name="Account 2", account_type=AccountType.SAVINGS, currency="GBP", starting_balance_pence=50000)
    db_session.add_all([acc1, acc2])
    db_session.commit()

    # Start with unassigned transactions
    tx1 = Transaction(transaction_type=TransactionType.EXPENSE, amount_pence=1500, merchant="Receipt A", account_id=None)
    tx2 = Transaction(transaction_type=TransactionType.EXPENSE, amount_pence=2500, merchant="Receipt B", account_id=None)
    db_session.add_all([tx1, tx2])
    db_session.commit()

    # 1. Bulk assign to Account 1
    res = client.post(
        "/api/transactions/bulk",
        json={
            "transaction_ids": [tx1.id, tx2.id],
            "update_account": True,
            "account_id": acc1.id,
        }
    )
    assert res.status_code == 200

    db_session.expire_all()
    assert db_session.query(Transaction).filter(Transaction.id == tx1.id).first().account_id == acc1.id
    assert db_session.query(Transaction).filter(Transaction.id == tx2.id).first().account_id == acc1.id

    # 2. Bulk set to Unassigned explicitly
    res_unassign = client.post(
        "/api/transactions/bulk",
        json={
            "transaction_ids": [tx1.id],
            "update_account": True,
            "account_id": None,  # Explicit Unassigned!
        }
    )
    assert res_unassign.status_code == 200

    db_session.expire_all()
    assert db_session.query(Transaction).filter(Transaction.id == tx1.id).first().account_id is None
    assert db_session.query(Transaction).filter(Transaction.id == tx2.id).first().account_id == acc1.id


def test_6_unselected_fields_and_provenance_remain_unchanged(db_session, client: TestClient):
    """
    Requirement 6:
    Unselected fields and timestamps remaining completely unchanged.
    """
    acc = Account(name="Checking", account_type=AccountType.CURRENT, currency="GBP", starting_balance_pence=100000)
    cat = Category(name="General", color="#6366F1")
    db_session.add_all([acc, cat])
    db_session.commit()

    t_nominal = datetime(2026, 4, 15, 12, 30, 0, tzinfo=timezone.utc)
    t_effective = datetime(2026, 4, 15, 14, 0, 0, tzinfo=timezone.utc)
    t_created = datetime(2026, 4, 15, 14, 0, 0, tzinfo=timezone.utc)

    tx = Transaction(
        transaction_date=t_nominal,
        effective_timestamp=t_effective,
        created_at=t_created,
        transaction_type=TransactionType.EXPENSE,
        amount_pence=8500,  # £85.00
        merchant="Eurostar Paris",
        notes="Business trip ticket #789",
        entry_method="ocr_receipt",
        original_amount=Decimal("100.0000"),
        original_currency="EUR",
        exchange_rate=Decimal("0.85000000"),
        account_id=acc.id,
    )
    db_session.add(tx)
    db_session.commit()

    # Perform bulk update ONLY changing the category
    res = client.post(
        "/api/transactions/bulk",
        json={
            "transaction_ids": [tx.id],
            "update_category": True,
            "category_id": cat.id,
            # update_transaction_type is False
            # update_account is False
        }
    )
    assert res.status_code == 200

    # Verification: ALL other fields are 100% preserved
    db_session.expire_all()
    updated_tx = db_session.query(Transaction).filter(Transaction.id == tx.id).first()

    assert updated_tx.category_id == cat.id
    assert updated_tx.amount_pence == 8500
    assert updated_tx.merchant == "Eurostar Paris"
    assert updated_tx.notes == "Business trip ticket #789"
    assert updated_tx.entry_method == "ocr_receipt"
    assert updated_tx.account_id == acc.id
    assert updated_tx.transaction_type == TransactionType.EXPENSE
    assert updated_tx.original_currency == "EUR"
    assert float(updated_tx.original_amount) == 100.0
    assert float(updated_tx.exchange_rate) == 0.85
    assert updated_tx.transaction_date.strftime("%Y-%m-%d %H:%M") == "2026-04-15 12:30"
    assert updated_tx.effective_timestamp.strftime("%Y-%m-%d %H:%M") == "2026-04-15 14:00"
    assert updated_tx.created_at.strftime("%Y-%m-%d %H:%M") == "2026-04-15 14:00"


def test_7_validation_failure_causes_no_partial_updates(db_session, client: TestClient):
    """
    Requirement 7:
    Validation failure causing no partial updates (strict all-or-nothing atomicity).
    """
    acc = Account(
        name="Current",
        account_type=AccountType.CURRENT,
        currency="GBP",
        starting_balance_pence=100000,
        starting_balance_date=datetime(2026, 10, 1, 0, 0, 0, tzinfo=timezone.utc),
    )
    db_session.add(acc)
    db_session.commit()

    tx1 = Transaction(transaction_type=TransactionType.INCOME, amount_pence=1000, merchant="Item 1", account_id=acc.id)
    tx2 = Transaction(transaction_type=TransactionType.INCOME, amount_pence=2000, merchant="Item 2", account_id=acc.id)
    db_session.add_all([tx1, tx2])
    db_session.commit()

    # Request includes an invalid/non-existent transaction ID (999999)
    res_missing = client.post(
        "/api/transactions/bulk",
        json={
            "transaction_ids": [tx1.id, tx2.id, 999999],
            "update_transaction_type": True,
            "transaction_type": "expense",
        }
    )
    assert res_missing.status_code == 404
    assert "Transactions not found" in res_missing.json()["detail"]

    # Verify Tx 1 and Tx 2 were NOT updated
    db_session.expire_all()
    assert db_session.query(Transaction).filter(Transaction.id == tx1.id).first().transaction_type == TransactionType.INCOME
    assert db_session.query(Transaction).filter(Transaction.id == tx2.id).first().transaction_type == TransactionType.INCOME

    # Request includes an invalid category ID
    res_bad_cat = client.post(
        "/api/transactions/bulk",
        json={
            "transaction_ids": [tx1.id, tx2.id],
            "update_category": True,
            "category_id": 888888,
        }
    )
    assert res_bad_cat.status_code == 400
    assert "Target category with ID 888888 not found" in res_bad_cat.json()["detail"]

    # Verify no partial updates occurred
    db_session.expire_all()
    assert db_session.query(Transaction).filter(Transaction.id == tx1.id).first().category_id is None
    assert db_session.query(Transaction).filter(Transaction.id == tx2.id).first().category_id is None


def test_8_transfer_and_reconciliation_adjustment_restrictions(db_session, client: TestClient):
    """
    Requirement 8:
    Protect transfers and reconciliation adjustments from invalid changes.
    Do not convert transfers or adjustments to income/expense through bulk edit.
    """
    acc_src = Account(name="Current", account_type=AccountType.CURRENT, currency="GBP", starting_balance_pence=100000)
    acc_dst = Account(name="Savings", account_type=AccountType.SAVINGS, currency="GBP", starting_balance_pence=50000)
    db_session.add_all([acc_src, acc_dst])
    db_session.commit()

    # 1. Normal expense
    tx_exp = Transaction(transaction_type=TransactionType.EXPENSE, amount_pence=2000, merchant="Store", account_id=acc_src.id)
    # 2. Transfer between acc_src and acc_dst
    tx_xfer = Transaction(
        transaction_type=TransactionType.TRANSFER,
        amount_pence=5000,
        merchant="Internal Transfer",
        account_id=acc_src.id,
        destination_account_id=acc_dst.id,
    )
    # 3. Reconciliation adjustment
    tx_adj = Transaction(
        transaction_type=TransactionType.ADJUSTMENT,
        amount_pence=1000,
        merchant="Balance Reconciliation Adjustment",
        account_id=acc_src.id,
    )
    db_session.add_all([tx_exp, tx_xfer, tx_adj])
    db_session.commit()

    # A. Attempt to convert batch containing transfer to Expense
    res_transfer = client.post(
        "/api/transactions/bulk",
        json={
            "transaction_ids": [tx_exp.id, tx_xfer.id],
            "update_transaction_type": True,
            "transaction_type": "expense",
        }
    )
    assert res_transfer.status_code == 400
    assert "is a Transfer and cannot be converted" in res_transfer.json()["detail"]

    # B. Attempt to convert batch containing adjustment to Income
    res_adj = client.post(
        "/api/transactions/bulk",
        json={
            "transaction_ids": [tx_adj.id],
            "update_transaction_type": True,
            "transaction_type": "income",
        }
    )
    assert res_adj.status_code == 400
    assert "is a Reconciliation Adjustment and cannot be converted" in res_adj.json()["detail"]

    # C. Attempt to set transfer to Unassigned
    res_unassign_xfer = client.post(
        "/api/transactions/bulk",
        json={
            "transaction_ids": [tx_xfer.id],
            "update_account": True,
            "account_id": None,
        }
    )
    assert res_unassign_xfer.status_code == 400
    assert "cannot be set to Unassigned" in res_unassign_xfer.json()["detail"]

    # D. Attempt to assign spending category to transfer
    cat = Category(name="Travel", color="#3B82F6")
    db_session.add(cat)
    db_session.commit()

    res_cat_xfer = client.post(
        "/api/transactions/bulk",
        json={
            "transaction_ids": [tx_xfer.id],
            "update_category": True,
            "category_id": cat.id,
        }
    )
    assert res_cat_xfer.status_code == 400
    assert "cannot be assigned a spending category" in res_cat_xfer.json()["detail"]


def test_9_profile_isolation_and_scoping(isolated_profiles_env):
    """
    Requirement 9:
    Profile isolation and request scoping across profiles.
    """
    app.dependency_overrides.clear()
    client = TestClient(app)

    # 1. Switch to Profile 1 (default) and create a transaction
    res1 = client.post("/api/accounts", json={"name": "P1 Checking", "account_type": "current", "starting_balance": 1000.0})
    acc1_id = res1.json()["id"]

    res_tx1 = client.post("/api/transactions", json={
        "transaction_type": "expense",
        "amount": 25.0,
        "merchant": "Profile 1 Only Coffee",
        "account_id": acc1_id,
    })
    tx1_id = res_tx1.json()["id"]

    # 2. Create and switch to Profile 2
    res_p2 = client.post("/api/profiles", json={"name": "Business Workspace"})
    p2_id = res_p2.json()["id"]

    # In Profile 2: transaction from Profile 1 should NOT be visible or updatable
    res_list_p2 = client.get("/api/transactions", headers={"X-Profile-ID": p2_id})
    assert res_list_p2.status_code == 200
    assert not any(t["id"] == tx1_id for t in res_list_p2.json()["items"])

    # Attempting to bulk edit Profile 1 transaction while scoped to Profile 2 must fail (404 Not Found)
    res_bulk_p2 = client.post(
        "/api/transactions/bulk",
        headers={"X-Profile-ID": p2_id},
        json={
            "transaction_ids": [tx1_id],
            "update_transaction_type": True,
            "transaction_type": "income",
        }
    )
    assert res_bulk_p2.status_code == 404
    assert "Transactions not found in active workspace" in res_bulk_p2.json()["detail"]
