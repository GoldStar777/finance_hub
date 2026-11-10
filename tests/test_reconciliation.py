import pytest
from datetime import datetime, timezone
from app.models import (
    Account,
    AccountType,
    AccountSnapshot,
    Transaction,
    TransactionType,
)
from app.ledger import LedgerEngine
from app.core.reconciliation import (
    get_reconciliation_summary,
    create_reconciliation_snapshot,
    list_reconciliation_snapshots,
    delete_reconciliation_snapshot,
)

def test_reconciliation_exact_match(db_session, client):
    """Verifies that when actual matches calculated, discrepancy is zero and no adjustment is created."""
    acc = Account(name="Current Account", account_type=AccountType.CURRENT, currency="GBP", starting_balance_pence=100000)
    db_session.add(acc)
    db_session.commit()

    res = client.post(
        f"/api/accounts/{acc.id}/reconciliation/snapshots",
        json={"actual_balance": 1000.0, "notes": "Monthly check"}
    )
    assert res.status_code == 201
    data = res.json()

    assert data["snapshot"]["actual_balance_pence"] == 100000
    assert data["snapshot"]["calculated_balance_pence"] == 100000
    assert data["snapshot"]["discrepancy_pence"] == 0
    assert data["snapshot"]["discrepancy_direction"] == "exact"
    assert data["adjustment_created"] is False
    assert data["adjustment_transaction_id"] is None
    assert data["new_calculated_balance_pence"] == 100000

    # Verify no adjustment transaction was inserted into DB
    adj_count = db_session.query(Transaction).filter(Transaction.account_id == acc.id).count()
    assert adj_count == 0

def test_reconciliation_positive_discrepancy_snapshot_and_anchor(db_session, client):
    """Verifies that confirming a statement balance sets ground truth anchor to £1050 and saves observational snapshot."""
    acc = Account(name="Current Account", account_type=AccountType.CURRENT, currency="GBP", starting_balance_pence=100000)
    db_session.add(acc)
    db_session.commit()

    # Actual is £1,050, calculated is £1,000 -> discrepancy is +£50 (actual_higher)
    res = client.post(
        f"/api/accounts/{acc.id}/reconciliation/snapshots",
        json={"actual_balance": 1050.0, "notes": "Statement shows higher balance"}
    )
    assert res.status_code == 201
    data = res.json()

    assert data["snapshot"]["discrepancy_pence"] == 5000  # +£50.00
    assert data["snapshot"]["calculated_balance_pence"] == 100000
    assert data["snapshot"]["actual_balance_pence"] == 105000
    assert data["snapshot"]["discrepancy_direction"] == "actual_higher"
    assert data["anchor"]["balance_pence"] == 105000
    assert data["adjustment_created"] is False
    assert data["new_calculated_balance_pence"] == 105000  # Becomes ground truth £1,050!

    # Check ledger balance in DB is now exactly £1,050.00 without any transactions created
    assert LedgerEngine.get_account_balance(db_session, acc.id) == 105000
    assert db_session.query(Transaction).filter(Transaction.account_id == acc.id).count() == 0

def test_reconciliation_positive_discrepancy_with_adjustment(db_session, client):
    """Verifies that an explicitly confirmed positive discrepancy creates a [Positive adjustment]."""
    acc = Account(name="Current Account", account_type=AccountType.CURRENT, currency="GBP", starting_balance_pence=100000)
    db_session.add(acc)
    db_session.commit()

    # App: £1,000. Statement: £1,050. User confirms adjustment.
    res = client.post(
        f"/api/accounts/{acc.id}/reconciliation/snapshots",
        json={
            "actual_balance": 1050.0,
            "create_adjustment": True,
            "notes": "Verified against Barclays paper statement",
            "adjustment_notes": "Credited missing interest"
        }
    )
    assert res.status_code == 201
    data = res.json()

    assert data["adjustment_created"] is True
    assert data["adjustment_transaction_id"] is not None
    assert data["new_calculated_balance_pence"] == 105000  # Updated to match actual!

    # Inspect the created transaction
    tx = db_session.query(Transaction).filter(Transaction.id == data["adjustment_transaction_id"]).first()
    assert tx is not None
    assert tx.transaction_type == TransactionType.ADJUSTMENT
    assert tx.amount_pence == 5000  # £50
    assert "[Positive adjustment]" in tx.notes
    assert "Credited missing interest" in tx.notes

    # Verify ledger engine now returns £1,050
    assert LedgerEngine.get_account_balance(db_session, acc.id) == 105000

def test_reconciliation_negative_discrepancy_with_adjustment(db_session, client):
    """Verifies that an explicitly confirmed negative discrepancy creates a negative adjustment without [Positive adjustment]."""
    acc = Account(name="Current Account", account_type=AccountType.CURRENT, currency="GBP", starting_balance_pence=100000)
    db_session.add(acc)
    db_session.commit()

    # App: £1,000. Statement: £950. User confirms adjustment.
    res = client.post(
        f"/api/accounts/{acc.id}/reconciliation/snapshots",
        json={
            "actual_balance": 950.0,
            "create_adjustment": True,
            "notes": "Bank fee missing from app"
        }
    )
    assert res.status_code == 201
    data = res.json()

    assert data["snapshot"]["discrepancy_pence"] == -5000  # -£50.00
    assert data["snapshot"]["discrepancy_direction"] == "actual_lower"
    assert data["adjustment_created"] is True
    assert data["new_calculated_balance_pence"] == 95000  # Updated to match actual!

    # Inspect the created transaction
    tx = db_session.query(Transaction).filter(Transaction.id == data["adjustment_transaction_id"]).first()
    assert tx is not None
    assert tx.transaction_type == TransactionType.ADJUSTMENT
    assert tx.amount_pence == 5000  # Amount is positive 5000 pence
    assert "[Positive adjustment]" not in tx.notes  # Without positive tag -> negative delta!

    # Verify ledger engine now returns £950
    assert LedgerEngine.get_account_balance(db_session, acc.id) == 95000

def test_credit_card_signed_balance_reconciliation(db_session, client):
    """Verifies that credit card liabilities adhere to signed-balance conventions (negative balance for debt)."""
    # Card starts with £200 debt (-£200.00 = -20000 pence)
    card = Account(name="Amex Card", account_type=AccountType.CREDIT_CARD, currency="GBP", starting_balance_pence=-20000)
    db_session.add(card)
    db_session.commit()

    # 1. Statement says debt is higher: £250 debt (-£250.00 = -25000 pence)
    # Calculated is -£200.00. Discrepancy is -£250 - (-£200) = -£50.00 (-5000 pence)
    res1 = client.post(
        f"/api/accounts/{card.id}/reconciliation/snapshots",
        json={"actual_balance": -250.0, "create_adjustment": True, "notes": "Unrecorded purchase fee"}
    )
    assert res1.status_code == 201
    data1 = res1.json()
    assert data1["snapshot"]["discrepancy_pence"] == -5000
    assert data1["snapshot"]["discrepancy_direction"] == "actual_lower"
    assert data1["new_calculated_balance_pence"] == -25000
    assert LedgerEngine.get_account_balance(db_session, card.id) == -25000

    # 2. Next month statement says debt is lower: £150 debt (-£150.00 = -15000 pence)
    # Calculated is -£250.00. Discrepancy is -£150 - (-£250) = +£100.00 (+10000 pence)
    res2 = client.post(
        f"/api/accounts/{card.id}/reconciliation/snapshots",
        json={"actual_balance": -150.0, "create_adjustment": True, "notes": "Statement credit received"}
    )
    assert res2.status_code == 201
    data2 = res2.json()
    assert data2["snapshot"]["discrepancy_pence"] == 10000
    assert data2["snapshot"]["discrepancy_direction"] == "actual_higher"
    assert data2["new_calculated_balance_pence"] == -15000
    assert LedgerEngine.get_account_balance(db_session, card.id) == -15000

def test_reconciliation_history_and_last_reconciled_status(db_session, client):
    """Verifies snapshot history, status endpoint, and account response decoration."""
    acc = Account(name="Savings Account", account_type=AccountType.SAVINGS, currency="GBP", starting_balance_pence=50000)
    db_session.add(acc)
    db_session.commit()

    # Before reconciliation: last_reconciled_at is None
    res_summary = client.get(f"/api/accounts/{acc.id}/reconciliation")
    assert res_summary.status_code == 200
    assert res_summary.json()["last_reconciled_at"] is None
    assert res_summary.json()["snapshots_count"] == 0

    # Save two snapshots on distinct dates
    dt1 = datetime(2026, 9, 1, 10, 0, 0, tzinfo=timezone.utc)
    dt2 = datetime(2026, 10, 1, 10, 0, 0, tzinfo=timezone.utc)

    client.post(f"/api/accounts/{acc.id}/reconciliation/snapshots", json={"actual_balance": 500.0, "snapshot_date": dt1.isoformat(), "notes": "Sep check"})
    client.post(f"/api/accounts/{acc.id}/reconciliation/snapshots", json={"actual_balance": 510.0, "snapshot_date": dt2.isoformat(), "notes": "Oct check"})

    # Check summary endpoint
    res_summary2 = client.get(f"/api/accounts/{acc.id}/reconciliation")
    assert res_summary2.status_code == 200
    data2 = res_summary2.json()
    assert data2["snapshots_count"] == 2
    assert data2["last_reconciled_at"] is not None
    assert data2["last_snapshot"]["notes"] == "Oct check"

    # Check history listing endpoint
    res_list = client.get(f"/api/accounts/{acc.id}/reconciliation/snapshots")
    assert res_list.status_code == 200
    snapshots = res_list.json()
    assert len(snapshots) == 2
    assert snapshots[0]["notes"] == "Oct check"  # Descending order
    assert snapshots[1]["notes"] == "Sep check"

    # Check /api/accounts list includes last_reconciled_at
    res_accounts = client.get("/api/accounts")
    acc_item = next(a for a in res_accounts.json() if a["id"] == acc.id)
    assert acc_item["last_reconciled_at"] is not None
    assert acc_item["last_reconciled_discrepancy_pence"] == 1000  # 51000 - 50000 = 1000 pence

def test_delete_reconciliation_snapshot(db_session, client):
    """Verifies that deleting an erroneous snapshot removes it from history without touching transactions."""
    acc = Account(name="Current Account", account_type=AccountType.CURRENT, currency="GBP", starting_balance_pence=100000)
    db_session.add(acc)
    db_session.commit()

    res = client.post(f"/api/accounts/{acc.id}/reconciliation/snapshots", json={"actual_balance": 1000.0, "notes": "Typo entry"})
    snap_id = res.json()["snapshot"]["id"]

    # Delete snapshot
    res_del = client.delete(f"/api/accounts/{acc.id}/reconciliation/snapshots/{snap_id}")
    assert res_del.status_code == 204

    # Verify history is now empty
    history = client.get(f"/api/accounts/{acc.id}/reconciliation/snapshots").json()
    assert len(history) == 0

def test_investment_account_reconciliation_rejected(db_session, client):
    """Verifies that investment accounts are rejected from balance reconciliation with an informative error."""
    inv = Account(name="Vanguard ISA", account_type=AccountType.INVESTMENT, currency="GBP", starting_balance_pence=100000)
    db_session.add(inv)
    db_session.commit()

    res = client.get(f"/api/accounts/{inv.id}/reconciliation")
    assert res.status_code == 400
    assert "Investment accounts use the Portfolios and Holdings valuation workflow" in res.json()["detail"]

    res_post = client.post(f"/api/accounts/{inv.id}/reconciliation/snapshots", json={"actual_balance": 1000.0})
    assert res_post.status_code == 400
    assert "Investment accounts use the Portfolios and Holdings valuation workflow" in res_post.json()["detail"]

