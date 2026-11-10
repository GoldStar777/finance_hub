"""
Tests for Account Balance Anchors & 'Correct as of' Temporal Verification.
"""

import pytest
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.models import (
    Base, Account, AccountType, Transaction, TransactionType,
    ExpenseNature, AccountBalanceAnchor, StagingItem, StagingStatus
)
from app.ledger import LedgerEngine
from app.core.timezone import (
    get_app_timezone, get_end_of_day_utc, get_midday_utc,
    resolve_anchor_datetime, get_now_utc, ensure_utc
)
from app.core.staging import approve_staging_item
from app.core.reconciliation import create_reconciliation_snapshot
from app.core.cashflow import get_cashflow_summary

@pytest.fixture
def isolated_engine(tmp_path):
    db_file = tmp_path / "test_anchors.db"
    engine = create_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(engine)
    return engine

@pytest.fixture
def isolated_db(isolated_engine):
    SessionLocal = sessionmaker(bind=isolated_engine)
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def test_balance_preservation_across_transactions_before_and_after_creation(isolated_db):
    """
    Requirement 1: Migration preservation guarantee.
    Account created at T_create.
    A backfilled transaction exists at T_before < T_create.
    A forward transaction exists at T_after > T_create.
    The anchor date must be set to min(min_tx - 1s, created_at) to guarantee
    the post-migration balance exactly matches the pre-migration balance.
    """
    t_create = datetime(2026, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
    t_before = datetime(2026, 6, 1, 10, 0, 0, tzinfo=timezone.utc)
    t_after = datetime(2026, 6, 20, 14, 0, 0, tzinfo=timezone.utc)

    # Legacy balance calculation: starting_balance_pence + delta(all transactions)
    # Starting balance = £1,000.00 (100000 pence)
    # Prior expense = £200.00 (-20000 pence)
    # Forward expense = £150.00 (-15000 pence)
    # Expected total balance = 100000 - 20000 - 15000 = 65000 pence (£650.00)
    starting_balance = 100000

    # Calculate anchor date using preservation formula:
    # min_tx = t_before
    # anchor_date = min(t_before - 1s, t_create) = t_before - 1s
    anchor_dt = t_before - timedelta(seconds=1)

    acc = Account(
        name="Preservation Checking",
        account_type=AccountType.CURRENT,
        currency="GBP",
        color="#3B82F6",
        is_active=True,
        created_at=t_create
    )
    acc.balance_anchors.append(
        AccountBalanceAnchor(
            balance_pence=starting_balance,
            anchor_date=anchor_dt,
            is_opening=True,
            notes="Opening balance anchor"
        )
    )
    isolated_db.add(acc)
    isolated_db.commit()
    isolated_db.refresh(acc)

    # Add transaction before account creation
    tx1 = Transaction(
        transaction_date=t_before,
        effective_timestamp=t_before,
        transaction_type=TransactionType.EXPENSE,
        amount_pence=20000,
        merchant="Prior Grocery",
        account_id=acc.id,
        entry_method="manual"
    )
    # Add transaction after account creation
    tx2 = Transaction(
        transaction_date=t_after,
        effective_timestamp=t_after,
        transaction_type=TransactionType.EXPENSE,
        amount_pence=15000,
        merchant="Forward Electronics",
        account_id=acc.id,
        entry_method="manual"
    )
    isolated_db.add_all([tx1, tx2])
    isolated_db.commit()

    # Verify calculated balance is exactly £650.00 (65000 pence)
    calc_bal = LedgerEngine.get_account_balance(isolated_db, acc.id)
    assert calc_bal == 65000

    info = LedgerEngine.get_account_balance_info(isolated_db, acc.id)
    assert info["current_balance_pence"] == 65000
    assert info["delta_since_anchor_pence"] == -35000
    assert "Ledger balance · anchored as of" in info["anchor_label"]

def test_backdated_transaction_does_not_double_deduct_from_dated_anchor(isolated_db):
    """
    Core User Requirement:
    Balance entered as of today. An expense dated last week is added.
    The expense must appear in historical cash flow but must NOT reduce
    today's entered balance again.
    """
    now_utc = datetime.now(timezone.utc)
    last_week_utc = now_utc - timedelta(days=7)

    # 1. User enters balance today of £500.00 (50000 pence)
    acc = Account(
        name="Main Current",
        account_type=AccountType.CURRENT,
        currency="GBP",
        starting_balance_pence=50000,
        starting_balance_date=now_utc
    )
    isolated_db.add(acc)
    isolated_db.commit()
    isolated_db.refresh(acc)

    assert LedgerEngine.get_account_balance(isolated_db, acc.id) == 50000

    # 2. Add an expense dated last week
    tx_past = Transaction(
        transaction_date=last_week_utc,
        effective_timestamp=last_week_utc,
        transaction_type=TransactionType.EXPENSE,
        amount_pence=8000,  # £80.00
        merchant="Past Restaurant",
        account_id=acc.id
    )
    isolated_db.add(tx_past)
    isolated_db.commit()

    # The balance today must REMAIN £500.00!
    assert LedgerEngine.get_account_balance(isolated_db, acc.id) == 50000

    # 3. Add an expense dated today AFTER the anchor
    tx_future = Transaction(
        transaction_date=now_utc + timedelta(minutes=5),
        effective_timestamp=now_utc + timedelta(minutes=5),
        transaction_type=TransactionType.EXPENSE,
        amount_pence=3000,  # £30.00
        merchant="Afternoon Coffee",
        account_id=acc.id
    )
    isolated_db.add(tx_future)
    isolated_db.commit()

    # The balance today must now be £500.00 - £30.00 = £470.00
    assert LedgerEngine.get_account_balance(isolated_db, acc.id) == 47000

def test_multiple_balance_checkpoints(isolated_db):
    """
    Tests sequential checkpoints:
    Anchor 1 (Day 1): £1000.00
    Day 2: Expense £100.00 -> balance £900.00
    Anchor 2 (Day 3): User records checkpoint £850.00 (e.g. bank fee was missing)
    Day 4: Expense £50.00 -> balance £800.00
    """
    d1 = datetime(2026, 10, 1, 12, 0, 0, tzinfo=timezone.utc)
    d2 = datetime(2026, 10, 2, 12, 0, 0, tzinfo=timezone.utc)
    d3 = datetime(2026, 10, 3, 12, 0, 0, tzinfo=timezone.utc)
    d4 = datetime(2026, 10, 4, 12, 0, 0, tzinfo=timezone.utc)

    acc = Account(
        name="Checkpoint Checking",
        account_type=AccountType.CURRENT,
        currency="GBP",
        starting_balance_pence=100000,
        starting_balance_date=d1
    )
    isolated_db.add(acc)
    isolated_db.commit()
    isolated_db.refresh(acc)

    # Day 2: Expense £100
    tx1 = Transaction(
        transaction_date=d2,
        effective_timestamp=d2,
        transaction_type=TransactionType.EXPENSE,
        amount_pence=10000,
        merchant="Day 2 Store",
        account_id=acc.id
    )
    isolated_db.add(tx1)
    isolated_db.commit()

    assert LedgerEngine.get_account_balance(isolated_db, acc.id) == 90000

    # Day 3: User enters checkpoint £850.00
    anchor2 = AccountBalanceAnchor(
        account_id=acc.id,
        balance_pence=85000,
        anchor_date=d3,
        is_opening=False,
        notes="Bank statement checkpoint"
    )
    isolated_db.add(anchor2)
    isolated_db.commit()

    # Balance immediately reflects checkpoint £850.00
    assert LedgerEngine.get_account_balance(isolated_db, acc.id) == 85000

    # Day 4: Expense £50.00
    tx2 = Transaction(
        transaction_date=d4,
        effective_timestamp=d4,
        transaction_type=TransactionType.EXPENSE,
        amount_pence=5000,
        merchant="Day 4 Cafe",
        account_id=acc.id
    )
    isolated_db.add(tx2)
    isolated_db.commit()

    # Balance now £850.00 - £50.00 = £800.00
    assert LedgerEngine.get_account_balance(isolated_db, acc.id) == 80000

    # Add a backdated transaction for Day 2.5 (before checkpoint 2, after anchor 1)
    # It must NOT adjust the Day 4 balance because Checkpoint 2 ground-truth already supersedes it!
    tx_backdated = Transaction(
        transaction_date=datetime(2026, 10, 2, 18, 0, 0, tzinfo=timezone.utc),
        effective_timestamp=datetime(2026, 10, 2, 18, 0, 0, tzinfo=timezone.utc),
        transaction_type=TransactionType.EXPENSE,
        amount_pence=2500,
        merchant="Late discovered slip",
        account_id=acc.id
    )
    isolated_db.add(tx_backdated)
    isolated_db.commit()

    assert LedgerEngine.get_account_balance(isolated_db, acc.id) == 80000

def test_staging_statement_import_anchor_disambiguation(isolated_db):
    """
    Statement intake disambiguation:
    If a statement row is dated on or before a balance anchor:
    - User can choose 'already_reflected' -> does NOT double-deduct from anchor balance.
    - User can choose 'after_anchor' -> DOES deduct from anchor balance.
    """
    anchor_dt = datetime(2026, 10, 15, 14, 0, 0, tzinfo=timezone.utc)
    acc = Account(
        name="Barclays Account",
        account_type=AccountType.CURRENT,
        currency="GBP",
        starting_balance_pence=100000, # £1000.00
        starting_balance_date=anchor_dt
    )
    isolated_db.add(acc)
    isolated_db.commit()
    isolated_db.refresh(acc)

    # Item 1: Dated 2026-10-15 (same day), marked 'already_reflected'
    stg1 = StagingItem(
        status=StagingStatus.PENDING,
        source_type="statement_csv",
        extracted_amount_pence=5000,
        extracted_date=datetime(2026, 10, 15, 10, 0, 0, tzinfo=timezone.utc),
        extracted_merchant="Morning Coffee",
        suggested_account_id=acc.id,
        anchor_mode="already_reflected"
    )
    isolated_db.add(stg1)
    isolated_db.commit()

    tx1 = approve_staging_item(isolated_db, stg1.id)
    assert ensure_utc(tx1.effective_timestamp) <= ensure_utc(anchor_dt)
    # Balance must remain £1000.00 (not £950.00) because it was already reflected in the bank balance!
    assert LedgerEngine.get_account_balance(isolated_db, acc.id) == 100000

    # Item 2: Dated 2026-10-15, marked 'after_anchor'
    stg2 = StagingItem(
        status=StagingStatus.PENDING,
        source_type="statement_csv",
        extracted_amount_pence=2000,
        extracted_date=datetime(2026, 10, 15, 16, 0, 0, tzinfo=timezone.utc),
        extracted_merchant="Evening Transport",
        suggested_account_id=acc.id,
        anchor_mode="after_anchor"
    )
    isolated_db.add(stg2)
    isolated_db.commit()

    tx2 = approve_staging_item(isolated_db, stg2.id)
    assert ensure_utc(tx2.effective_timestamp) > ensure_utc(anchor_dt)
    # Balance must now be £1000.00 - £20.00 = £980.00
    assert LedgerEngine.get_account_balance(isolated_db, acc.id) == 98000

def test_same_day_reconciliation_adjustment_after_anchor(isolated_db):
    """
    Ensure an explicitly confirmed reconciliation adjustment recorded after
    today's balance anchor is properly included in calculated balance.
    """
    anchor_time = datetime.now(timezone.utc) - timedelta(minutes=10)
    acc = Account(
        name="Santander Checking",
        account_type=AccountType.CURRENT,
        currency="GBP",
        starting_balance_pence=100000, # £1000.00
        starting_balance_date=anchor_time
    )
    isolated_db.add(acc)
    isolated_db.commit()
    isolated_db.refresh(acc)

    # Actual balance is £1050.00 -> Discrepancy is +£50.00
    res = create_reconciliation_snapshot(
        db=isolated_db,
        account_id=acc.id,
        actual_balance_pence=105000,
        create_adjustment=True,
        notes="Bank credit adjustment"
    )

    assert res["adjustment_created"] is True
    assert res["new_calculated_balance_pence"] == 105000
    assert LedgerEngine.get_account_balance(isolated_db, acc.id) == 105000

def test_retrospective_balance_inference(isolated_db):
    """
    Querying balance as of a date before the earliest anchor correctly
    infers the historical balance by subtracting the forward transactions.
    """
    d_open = datetime(2026, 10, 20, 12, 0, 0, tzinfo=timezone.utc)
    d_past = datetime(2026, 10, 10, 12, 0, 0, tzinfo=timezone.utc)
    d_between = datetime(2026, 10, 15, 12, 0, 0, tzinfo=timezone.utc)

    acc = Account(
        name="Savings Anchor",
        account_type=AccountType.SAVINGS,
        currency="GBP",
        starting_balance_pence=100000, # £1000 on Oct 20
        starting_balance_date=d_open
    )
    isolated_db.add(acc)
    isolated_db.commit()
    isolated_db.refresh(acc)

    # Income of £300 on Oct 15
    tx_inc = Transaction(
        transaction_date=d_between,
        effective_timestamp=d_between,
        transaction_type=TransactionType.INCOME,
        amount_pence=30000,
        merchant="Oct 15 Transfer In",
        account_id=acc.id
    )
    isolated_db.add(tx_inc)
    isolated_db.commit()

    # Balance on Oct 20 is anchor (£1000)
    assert LedgerEngine.get_account_balance(isolated_db, acc.id) == 100000

    # Balance on Oct 10 (before the £300 income) was £1000 - £300 = £700
    bal_oct10 = LedgerEngine.get_account_balance(isolated_db, acc.id, as_of=d_past)
    assert bal_oct10 == 70000

def test_api_account_anchor_endpoints(client):
    """
    Tests account creation with anchor modes, anchor listing,
    adding checkpoints, and deleting checkpoints via API.
    """
    # 1. Create account with 'now' anchor
    res = client.post("/api/accounts", json={
        "name": "Anchor API Account",
        "account_type": "current",
        "starting_balance": 250.0,
        "as_of_mode": "now"
    })
    assert res.status_code == 201
    data = res.json()
    acc_id = data["id"]
    assert data["starting_balance_pence"] == 25000
    assert data["current_balance_pence"] == 25000
    assert "anchored as of" in data["anchor_label"]

    # 2. List anchors
    res_anchors = client.get(f"/api/accounts/{acc_id}/anchors")
    assert res_anchors.status_code == 200
    anchors = res_anchors.json()
    assert len(anchors) == 1
    assert anchors[0]["is_opening"] is True
    assert anchors[0]["balance_pence"] == 25000
    opening_anchor_id = anchors[0]["id"]

    # 3. Add a checkpoint via POST /accounts/{id}/anchors
    res_checkpoint = client.post(f"/api/accounts/{acc_id}/anchors", json={
        "balance": 300.0,
        "as_of_mode": "date",
        "as_of_date": "2026-10-18",
        "notes": "Mid-month statement check"
    })
    assert res_checkpoint.status_code == 201
    cp_data = res_checkpoint.json()
    assert cp_data["balance_pence"] == 30000
    assert cp_data["is_opening"] is False
    checkpoint_id = cp_data["id"]

    # Verify anchors list now has 2
    res_anchors2 = client.get(f"/api/accounts/{acc_id}/anchors")
    assert len(res_anchors2.json()) == 2

    # 4. Attempt to delete opening anchor -> should be forbidden (400)
    del_res = client.delete(f"/api/accounts/{acc_id}/anchors/{opening_anchor_id}")
    assert del_res.status_code == 400
    assert "Cannot delete the opening balance anchor" in del_res.json()["detail"]

    # 5. Delete checkpoint anchor -> should succeed (204)
    del_cp = client.delete(f"/api/accounts/{acc_id}/anchors/{checkpoint_id}")
    assert del_cp.status_code == 204

    # Verify 1 anchor remains
    res_anchors3 = client.get(f"/api/accounts/{acc_id}/anchors")
    assert len(res_anchors3.json()) == 1

def test_backdated_entry_preserves_entry_timestamp(db_session, client):
    """
    Requirement 1:
    Entering a backdated transaction preserves its chosen transaction date and
    effective timestamp while recording the actual entry time (created_at).
    """
    acc = Account(
        name="Checking Account",
        account_type=AccountType.CURRENT,
        currency="GBP",
        starting_balance_pence=100000,
        starting_balance_date=datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    )
    db_session.add(acc)
    db_session.commit()
    db_session.refresh(acc)

    nominal_dt_str = "2026-08-15T00:00:00"
    before_entry = datetime.now(timezone.utc) - timedelta(seconds=2)

    res = client.post("/api/transactions", json={
        "account_id": acc.id,
        "amount": 45.50,
        "merchant": "Backdated Bookshop",
        "transaction_type": "expense",
        "transaction_date": nominal_dt_str
    })
    assert res.status_code == 201
    data = res.json()
    after_entry = datetime.now(timezone.utc) + timedelta(seconds=2)

    tx = db_session.query(Transaction).filter(Transaction.id == data["id"]).first()
    assert tx is not None

    # Nominal date preserved
    assert tx.transaction_date.year == 2026
    assert tx.transaction_date.month == 8
    assert tx.transaction_date.day == 15

    # Effective timestamp midday of nominal date
    app_tz = get_app_timezone(db_session)
    expected_midday = get_midday_utc(tx.transaction_date, tz_str=app_tz)
    assert ensure_utc(tx.effective_timestamp) == ensure_utc(expected_midday)

    # Persistent entry timestamp (created_at) captures actual entry time
    tx_created = ensure_utc(tx.created_at)
    assert before_entry <= tx_created <= after_entry
    # Created_at is completely separate from nominal date
    assert tx_created.year != 2026 or tx_created.month != 8 or tx_created.day != 15

def test_statement_import_preserves_intake_timestamp(isolated_db):
    """
    Requirement 2:
    Importing a statement row preserves the statement date and records when it was imported or staged.
    """
    acc = Account(
        name="Staging Current",
        account_type=AccountType.CURRENT,
        currency="GBP",
        starting_balance_pence=200000,
        starting_balance_date=datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    )
    isolated_db.add(acc)
    isolated_db.commit()
    isolated_db.refresh(acc)

    # Intake/staging occurred at T_intake (e.g. 5 days ago)
    t_intake = datetime(2026, 10, 10, 9, 30, 0, tzinfo=timezone.utc)
    statement_nominal_date = datetime(2026, 10, 1, 12, 0, 0, tzinfo=timezone.utc)

    stg = StagingItem(
        status=StagingStatus.PENDING,
        source_type="statement_csv",
        extracted_amount_pence=6400,
        extracted_date=statement_nominal_date,
        extracted_merchant="Trainline Travel",
        suggested_account_id=acc.id,
        created_at=t_intake
    )
    isolated_db.add(stg)
    isolated_db.commit()
    isolated_db.refresh(stg)

    # Approval happens later
    tx = approve_staging_item(isolated_db, stg.id)

    # Verify statement nominal date is preserved
    assert ensure_utc(tx.transaction_date) == ensure_utc(statement_nominal_date)

    # Verify created_at preserves the intake/staged timestamp, NOT approval time
    assert tx.created_at is not None
    assert ensure_utc(tx.created_at) == ensure_utc(t_intake)

def test_entry_timestamp_independence_from_cashflow_and_balance(isolated_db):
    """
    Requirement 3:
    The entry timestamp does not alter Cash Flow grouping or account balance calculations.
    """
    acc = Account(
        name="Independence Current",
        account_type=AccountType.CURRENT,
        currency="GBP",
        starting_balance_pence=100000,
        starting_balance_date=datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    )
    isolated_db.add(acc)
    isolated_db.commit()
    isolated_db.refresh(acc)

    # Create two transactions with the same nominal date in May 2026, but vastly different created_at
    nominal_dt = datetime(2026, 5, 20, 12, 0, 0, tzinfo=timezone.utc)

    # Tx1: Entered "today"
    tx1 = Transaction(
        transaction_date=nominal_dt,
        effective_timestamp=nominal_dt,
        created_at=datetime(2026, 10, 22, 14, 0, 0, tzinfo=timezone.utc),
        transaction_type=TransactionType.EXPENSE,
        expense_nature=ExpenseNature.VARIABLE,
        amount_pence=2500,
        merchant="May Expense 1",
        account_id=acc.id
    )

    # Tx2: Entered back in May 2026
    tx2 = Transaction(
        transaction_date=nominal_dt,
        effective_timestamp=nominal_dt,
        created_at=datetime(2026, 5, 20, 12, 5, 0, tzinfo=timezone.utc),
        transaction_type=TransactionType.EXPENSE,
        expense_nature=ExpenseNature.VARIABLE,
        amount_pence=3500,
        merchant="May Expense 2",
        account_id=acc.id
    )
    isolated_db.add_all([tx1, tx2])
    isolated_db.commit()

    # 1. Balance check: both expenses reduce balance (£1000 - £25 - £35 = £940)
    bal_initial = LedgerEngine.get_account_balance(isolated_db, acc.id)
    assert bal_initial == 94000

    # 2. Cash flow check: grouped by nominal date (2026-05) regardless of created_at
    cf_may = get_cashflow_summary(isolated_db, month_str="2026-05", currency_param="GBP")
    assert cf_may["total_expenses_pence"] == 6000
    assert cf_may["variable_expenses_pence"] == 6000

    cf_oct = get_cashflow_summary(isolated_db, month_str="2026-10", currency_param="GBP")
    assert cf_oct["total_expenses_pence"] == 0

    # 3. Alter created_at on tx1 to another timestamp completely
    tx1.created_at = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    isolated_db.commit()

    # Assert balance and cash flow remain exactly identical
    assert LedgerEngine.get_account_balance(isolated_db, acc.id) == 94000
    cf_may_after = get_cashflow_summary(isolated_db, month_str="2026-05", currency_param="GBP")
    assert cf_may_after["total_expenses_pence"] == 6000
    cf_oct_after = get_cashflow_summary(isolated_db, month_str="2026-10", currency_param="GBP")
    assert cf_oct_after["total_expenses_pence"] == 0

def test_unassigned_income_expense_creation_and_discoverability(client, db_session):
    """
    Test creating unassigned income and expense transactions with optional merchant.
    Verify validation rejects unassigned transfers and adjustments.
    Verify discoverability via unassigned_only filter.
    """
    # 1. Create unassigned expense with no merchant (blank/null)
    res_exp = client.post("/api/transactions", json={
        "transaction_type": "expense",
        "amount": 25.50,
        "transaction_date": "2026-10-18T10:00:00Z"
    })
    assert res_exp.status_code == 201
    exp_data = res_exp.json()
    assert exp_data["account_id"] is None
    assert exp_data["is_unassigned"] is True
    assert exp_data["account_name"] == "Unassigned"
    assert exp_data["merchant"] is None
    assert exp_data["display_merchant"] == "Merchant not recorded"

    # Verify DB record has NULL merchant and NULL account_id
    tx_exp = db_session.query(Transaction).filter(Transaction.id == exp_data["id"]).first()
    assert tx_exp.account_id is None
    assert tx_exp.merchant is None

    # 2. Create unassigned income with a merchant
    res_inc = client.post("/api/transactions", json={
        "transaction_type": "income",
        "amount": 100.00,
        "merchant": "Consulting Fee",
        "transaction_date": "2026-10-19T10:00:00Z"
    })
    assert res_inc.status_code == 201
    inc_data = res_inc.json()
    assert inc_data["account_id"] is None
    assert inc_data["is_unassigned"] is True
    assert inc_data["merchant"] == "Consulting Fee"

    # 3. Validation: Unassigned transfer must be rejected (400)
    res_transfer = client.post("/api/transactions", json={
        "transaction_type": "transfer",
        "amount": 50.00,
        "transaction_date": "2026-10-19T10:00:00Z"
    })
    assert res_transfer.status_code == 400
    assert "required for transfers" in res_transfer.json()["detail"].lower()

    # 4. Validation: Unassigned adjustment must be rejected (400)
    res_adj = client.post("/api/transactions", json={
        "transaction_type": "adjustment",
        "amount": 15.00,
        "transaction_date": "2026-10-19T10:00:00Z"
    })
    assert res_adj.status_code == 400
    assert "account is required for reconciliation adjustments" in res_adj.json()["detail"].lower()

    # 5. Discoverability: Filter by unassigned_only=true
    res_list = client.get("/api/transactions?unassigned_only=true")
    assert res_list.status_code == 200
    items = res_list.json()["items"]
    assert len(items) >= 2
    for item in items:
        assert item["is_unassigned"] is True
        assert item["account_id"] is None

def test_unassigned_transactions_excluded_from_balances_and_net_worth(isolated_db):
    """
    An unassigned transaction must not affect any individual account balance,
    net worth, or reconciliation.
    """
    now = datetime.now(timezone.utc)
    acc = Account(
        name="Main Checking",
        account_type=AccountType.CURRENT,
        currency="GBP",
        starting_balance_pence=100000,
        starting_balance_date=now - timedelta(days=5)
    )
    isolated_db.add(acc)
    isolated_db.commit()
    isolated_db.refresh(acc)

    # Balance before unassigned transactions
    assert LedgerEngine.get_account_balance(isolated_db, acc.id) == 100000
    summary_before = LedgerEngine.get_dashboard_summary(isolated_db)
    assert summary_before["net_worth_pence"] == 100000
    assert summary_before["total_liquid_pence"] == 100000

    # Add unassigned expense of £250.00
    tx_unassigned_exp = Transaction(
        transaction_date=now - timedelta(days=2),
        effective_timestamp=now - timedelta(days=2),
        transaction_type=TransactionType.EXPENSE,
        amount_pence=25000,
        merchant=None,
        account_id=None
    )
    # Add unassigned income of £500.00
    tx_unassigned_inc = Transaction(
        transaction_date=now - timedelta(days=1),
        effective_timestamp=now - timedelta(days=1),
        transaction_type=TransactionType.INCOME,
        amount_pence=50000,
        merchant="Freelance Client",
        account_id=None
    )
    isolated_db.add_all([tx_unassigned_exp, tx_unassigned_inc])
    isolated_db.commit()

    # Balance and Net Worth must remain strictly £1,000.00 (100000 pence)!
    assert LedgerEngine.get_account_balance(isolated_db, acc.id) == 100000
    summary_after = LedgerEngine.get_dashboard_summary(isolated_db)
    assert summary_after["net_worth_pence"] == 100000
    assert summary_after["total_liquid_pence"] == 100000

def test_unassigned_transactions_included_in_cash_flow(isolated_db):
    """
    Include unassigned income/expense in base-currency Cash Flow.
    """
    acc = Account(
        name="Business Account",
        account_type=AccountType.CURRENT,
        currency="GBP",
        starting_balance_pence=50000,
        starting_balance_date=datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    )
    isolated_db.add(acc)
    isolated_db.commit()
    isolated_db.refresh(acc)

    # 1. Unassigned transactions in July 2026
    tx1 = Transaction(
        transaction_date=datetime(2026, 7, 10, 12, 0, 0, tzinfo=timezone.utc),
        transaction_type=TransactionType.EXPENSE,
        expense_nature=ExpenseNature.VARIABLE,
        amount_pence=15000,
        merchant=None,
        account_id=None
    )
    tx2 = Transaction(
        transaction_date=datetime(2026, 7, 15, 14, 0, 0, tzinfo=timezone.utc),
        transaction_type=TransactionType.INCOME,
        amount_pence=40000,
        merchant="Direct Payment",
        account_id=None
    )
    isolated_db.add_all([tx1, tx2])
    isolated_db.commit()

    # Cash flow across all accounts for July in base currency GBP
    cf = get_cashflow_summary(isolated_db, month_str="2026-07", currency_param="GBP")
    assert cf["income_pence"] == 40000
    assert cf["total_expenses_pence"] == 15000
    assert cf["variable_expenses_pence"] == 15000
    assert cf["net_surplus_pence"] == 25000

    # If Cash Flow is filtered by the specific account, unassigned transactions are excluded
    cf_acc = get_cashflow_summary(isolated_db, month_str="2026-07", currency_param="GBP", account_id=acc.id)
    assert cf_acc["income_pence"] == 0
    assert cf_acc["total_expenses_pence"] == 0

def test_unassigned_transaction_later_assigned_across_anchor_boundary(isolated_db):
    """
    When an unassigned transaction is later assigned to an account, recalculate
    balances using its effective timestamp and the account's anchors.
    Preserve its original nominal date, entry timestamp, and foreign-currency provenance.
    """
    anchor_dt = datetime(2026, 10, 15, 12, 0, 0, tzinfo=timezone.utc)
    entry_time = datetime(2026, 10, 22, 10, 0, 0, tzinfo=timezone.utc)

    acc = Account(
        name="Target Current",
        account_type=AccountType.CURRENT,
        currency="GBP",
        starting_balance_pence=100000,
        starting_balance_date=anchor_dt
    )
    isolated_db.add(acc)
    isolated_db.commit()
    isolated_db.refresh(acc)

    # Tx A: Dated before anchor (2026-10-10) with foreign currency purchase provenance
    tx_a = Transaction(
        transaction_date=datetime(2026, 10, 10, 9, 0, 0, tzinfo=timezone.utc),
        effective_timestamp=datetime(2026, 10, 10, 9, 0, 0, tzinfo=timezone.utc),
        created_at=entry_time,
        transaction_type=TransactionType.EXPENSE,
        amount_pence=10000,
        merchant="Berlin Hotel",
        account_id=None,
        original_currency="EUR",
        original_amount=115.0,
        exchange_rate=0.86956522
    )

    # Tx B: Dated after anchor (2026-10-20)
    tx_b = Transaction(
        transaction_date=datetime(2026, 10, 20, 15, 0, 0, tzinfo=timezone.utc),
        effective_timestamp=datetime(2026, 10, 20, 15, 0, 0, tzinfo=timezone.utc),
        created_at=entry_time,
        transaction_type=TransactionType.EXPENSE,
        amount_pence=20000,
        merchant="Local Tech Store",
        account_id=None
    )
    isolated_db.add_all([tx_a, tx_b])
    isolated_db.commit()

    # Prior to assignment: account balance is £1,000.00
    assert LedgerEngine.get_account_balance(isolated_db, acc.id) == 100000

    # 1. Later assign Tx A (before anchor)
    tx_a.account_id = acc.id
    isolated_db.commit()

    # Recalculate balance: Tx A occurs BEFORE the anchor, so anchor remains ground truth (£1000.00)
    assert LedgerEngine.get_account_balance(isolated_db, acc.id) == 100000
    # Provenance and timestamps preserved
    assert ensure_utc(tx_a.transaction_date) == ensure_utc(datetime(2026, 10, 10, 9, 0, 0, tzinfo=timezone.utc))
    assert ensure_utc(tx_a.created_at) == ensure_utc(entry_time)
    assert tx_a.original_currency == "EUR"
    assert float(tx_a.original_amount) == 115.0

    # 2. Later assign Tx B (after anchor)
    tx_b.account_id = acc.id
    isolated_db.commit()

    # Recalculate balance: Tx B occurs AFTER the anchor, so balance is £1000 - £200 = £800.00 (80000 pence)
    assert LedgerEngine.get_account_balance(isolated_db, acc.id) == 80000
    assert ensure_utc(tx_b.transaction_date) == ensure_utc(datetime(2026, 10, 20, 15, 0, 0, tzinfo=timezone.utc))
    assert ensure_utc(tx_b.created_at) == ensure_utc(entry_time)

def test_legacy_transaction_entry_timestamp_migration_behavior(tmp_path):
    """
    Migration safety verification:
    If a transaction's true entry time is unavailable, the migration must NOT populate
    created_at with the migration execution timestamp and present it as historical truth.
    Legacy entry timestamps are preserved as NULL (Unknown).
    Also confirms account_id and merchant can be null post-migration.
    """
    from alembic.config import Config
    from alembic import command
    from pathlib import Path
    import sqlalchemy as sa

    base_dir = Path(__file__).resolve().parent.parent
    ini_path = base_dir / "alembic.ini"
    test_db = tmp_path / "legacy_entry_migration.db"

    cfg = Config(str(ini_path))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{test_db}")

    engine = create_engine(f"sqlite:///{test_db}")
    with engine.begin() as conn:
        conn.execute(sa.text("""
            CREATE TABLE accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name VARCHAR(100) NOT NULL UNIQUE,
                account_type VARCHAR(20) NOT NULL,
                starting_balance_pence INTEGER DEFAULT 0 NOT NULL,
                currency VARCHAR(3) DEFAULT 'GBP' NOT NULL,
                color VARCHAR(20) DEFAULT '#3B82F6',
                is_active BOOLEAN DEFAULT 1 NOT NULL,
                valuation_mode VARCHAR(20) DEFAULT 'snapshot' NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
        """))
        conn.execute(sa.text("""
            CREATE TABLE transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                transaction_date DATETIME NOT NULL,
                transaction_type VARCHAR(20) NOT NULL,
                amount_pence INTEGER NOT NULL,
                merchant VARCHAR(255) NOT NULL,
                notes TEXT,
                entry_method VARCHAR(50) DEFAULT 'manual',
                receipt_path VARCHAR(500),
                account_id INTEGER NOT NULL REFERENCES accounts(id),
                destination_account_id INTEGER REFERENCES accounts(id),
                category_id INTEGER,
                expense_nature VARCHAR(20) DEFAULT 'unclassified' NOT NULL,
                original_amount NUMERIC(18, 4),
                original_currency VARCHAR(3),
                exchange_rate NUMERIC(18, 8)
            );
        """))
        conn.execute(sa.text("""
            CREATE TABLE staging_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                status VARCHAR(20) DEFAULT 'pending' NOT NULL,
                extracted_amount_pence INTEGER,
                extracted_date DATETIME,
                extracted_merchant VARCHAR(255),
                suggested_category_name VARCHAR(100),
                suggested_account_id INTEGER,
                suggested_expense_nature VARCHAR(20) DEFAULT 'unclassified' NOT NULL,
                source_type VARCHAR(50) NOT NULL,
                temp_file_path VARCHAR(500),
                raw_payload_json TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
        """))
        conn.execute(sa.text("""
            CREATE TABLE system_settings (
                key VARCHAR(100) PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
        """))
        conn.execute(sa.text("""
            INSERT INTO accounts (id, name, account_type, starting_balance_pence, currency, color, is_active, valuation_mode)
            VALUES (1, 'Legacy Account', 'current', 50000, 'GBP', '#3B82F6', 1, 'snapshot');
        """))
        conn.execute(sa.text("""
            INSERT INTO transactions (id, transaction_date, transaction_type, amount_pence, merchant, entry_method, account_id, expense_nature)
            VALUES (1, '2026-05-10 14:00:00', 'expense', 4500, 'Pre-migration Bakery', 'manual', 1, 'variable');
        """))

    command.stamp(cfg, "c3d4e5f6a7b8")
    command.upgrade(cfg, "head")

    with engine.connect() as conn:
        row = conn.execute(sa.text("""
            SELECT id, transaction_date, effective_timestamp, created_at, merchant, account_id 
            FROM transactions WHERE id = 1
        """)).fetchone()

        assert row[0] == 1
        assert "2026-05-10" in str(row[1])
        assert row[2] is not None
        assert row[3] is None

        conn.execute(sa.text("""
            INSERT INTO transactions (transaction_date, transaction_type, amount_pence, merchant, account_id, expense_nature)
            VALUES ('2026-10-22 12:00:00', 'expense', 3000, NULL, NULL, 'unclassified')
        """))
        unassigned_row = conn.execute(sa.text("""
            SELECT id, merchant, account_id FROM transactions WHERE merchant IS NULL
        """)).fetchone()
        assert unassigned_row is not None
        assert unassigned_row[1] is None
        assert unassigned_row[2] is None

        anchor = conn.execute(sa.text("SELECT balance_pence, is_opening FROM account_balance_anchors WHERE account_id = 1")).fetchone()
        assert anchor is not None
        assert anchor[0] == 50000
        assert anchor[1] == 1


def test_alembic_migration_end_to_end_balance_preservation(tmp_path):
    """
    End-to-end Alembic migration test verifying:
    1. Pre-migration legacy database with transactions dated before and after account creation.
    2. Migration execution (c3d4e5f6a7b8 -> d4e5f6a7b8c9).
    3. Backfilling of effective_timestamp from transaction_date.
    4. Post-migration LedgerEngine balance calculation equals pre-migration balance exactly.
    5. Safe fallback: even if effective_timestamp were NULL, LedgerEngine falls back to transaction_date.
    """
    from alembic.config import Config
    from alembic import command
    from pathlib import Path
    import sqlalchemy as sa
    from sqlalchemy.orm import sessionmaker
    from app.ledger import LedgerEngine

    base_dir = Path(__file__).resolve().parent.parent
    ini_path = base_dir / "alembic.ini"
    test_db = tmp_path / "migration_preservation.db"

    cfg = Config(str(ini_path))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{test_db}")

    engine = create_engine(f"sqlite:///{test_db}")

    # 1. Create legacy schema at c3d4e5f6a7b8 (pre-anchor, starting_balance_pence on accounts, no effective_timestamp on transactions)
    with engine.begin() as conn:
        conn.execute(sa.text("""
            CREATE TABLE accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name VARCHAR(100) NOT NULL UNIQUE,
                account_type VARCHAR(20) NOT NULL,
                starting_balance_pence INTEGER DEFAULT 0 NOT NULL,
                currency VARCHAR(3) DEFAULT 'GBP' NOT NULL,
                color VARCHAR(20) DEFAULT '#3B82F6',
                is_active BOOLEAN DEFAULT 1 NOT NULL,
                valuation_mode VARCHAR(20) DEFAULT 'snapshot' NOT NULL,
                created_at DATETIME DEFAULT '2026-06-15 12:00:00'
            );
        """))
        conn.execute(sa.text("""
            CREATE TABLE transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                transaction_date DATETIME NOT NULL,
                transaction_type VARCHAR(20) NOT NULL,
                amount_pence INTEGER NOT NULL,
                merchant VARCHAR(255) NOT NULL,
                notes TEXT,
                entry_method VARCHAR(50) DEFAULT 'manual',
                receipt_path VARCHAR(500),
                account_id INTEGER NOT NULL REFERENCES accounts(id),
                destination_account_id INTEGER REFERENCES accounts(id),
                category_id INTEGER,
                expense_nature VARCHAR(20) DEFAULT 'unclassified' NOT NULL,
                original_amount NUMERIC(18, 4),
                original_currency VARCHAR(3),
                exchange_rate NUMERIC(18, 8)
            );
        """))
        conn.execute(sa.text("""
            CREATE TABLE staging_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                status VARCHAR(20) DEFAULT 'pending' NOT NULL,
                extracted_amount_pence INTEGER,
                extracted_date DATETIME,
                extracted_merchant VARCHAR(255),
                suggested_category_name VARCHAR(100),
                suggested_account_id INTEGER,
                suggested_expense_nature VARCHAR(20) DEFAULT 'unclassified' NOT NULL,
                source_type VARCHAR(50) NOT NULL,
                temp_file_path VARCHAR(500),
                raw_payload_json TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
        """))
        conn.execute(sa.text("""
            CREATE TABLE system_settings (
                key VARCHAR(100) PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
        """))

        # Account: starting balance £1,000.00 (100,000 pence), created 2026-06-15 12:00:00
        conn.execute(sa.text("""
            INSERT INTO accounts (id, name, account_type, starting_balance_pence, currency, color, is_active, valuation_mode, created_at)
            VALUES (1, 'Legacy Main Account', 'CURRENT', 100000, 'GBP', '#3B82F6', 1, 'snapshot', '2026-06-15 12:00:00');
        """))

        # tx1: backdated before account creation (2026-06-01 10:00:00), expense £200.00 (20,000 pence)
        conn.execute(sa.text("""
            INSERT INTO transactions (id, transaction_date, transaction_type, amount_pence, merchant, entry_method, account_id, expense_nature)
            VALUES (1, '2026-06-01 10:00:00', 'EXPENSE', 20000, 'Pre-Creation Grocery', 'manual', 1, 'VARIABLE');
        """))

        # tx2: after account creation (2026-06-20 14:00:00), expense £150.00 (15,000 pence)
        conn.execute(sa.text("""
            INSERT INTO transactions (id, transaction_date, transaction_type, amount_pence, merchant, entry_method, account_id, expense_nature)
            VALUES (2, '2026-06-20 14:00:00', 'EXPENSE', 15000, 'Post-Creation Store', 'manual', 1, 'VARIABLE');
        """))

    # Pre-migration balance formula: 100000 (starting) - 20000 (tx1) - 15000 (tx2) = 65000 pence (£650.00)
    pre_migration_balance = 100000 - 20000 - 15000

    # 2. Stamp revision c3d4e5f6a7b8 and run migration upgrade head
    command.stamp(cfg, "c3d4e5f6a7b8")
    command.upgrade(cfg, "head")

    # 3. Verify backfill of effective_timestamp in DB
    with engine.connect() as conn:
        rows = conn.execute(sa.text("SELECT id, transaction_date, effective_timestamp FROM transactions ORDER BY id")).fetchall()
        assert len(rows) == 2
        # tx1
        assert rows[0][0] == 1
        assert "2026-06-01" in str(rows[0][1])
        assert "2026-06-01" in str(rows[0][2])
        # tx2
        assert rows[1][0] == 2
        assert "2026-06-20" in str(rows[1][1])
        assert "2026-06-20" in str(rows[1][2])

        # Verify opening anchor was positioned strictly before earliest transaction
        anchor = conn.execute(sa.text("SELECT balance_pence, anchor_date, is_opening FROM account_balance_anchors WHERE account_id = 1")).fetchone()
        assert anchor is not None
        assert anchor[0] == 100000
        assert anchor[2] == 1
        # anchor_date must be strictly earlier than 2026-06-01 10:00:00
        anchor_dt_str = str(anchor[1]).replace("T", " ")
        assert anchor_dt_str <= "2026-06-01 09:59:59"

    # 4. Verify post-migration calculated balance matches pre-migration balance exactly
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    try:
        post_migration_balance = LedgerEngine.get_account_balance(session, 1)
        assert post_migration_balance == pre_migration_balance
        assert post_migration_balance == 65000

        balance_info = LedgerEngine.get_account_balance_info(session, 1)
        assert balance_info["current_balance_pence"] == 65000
        assert balance_info["delta_since_anchor_pence"] == -35000
        assert "Ledger balance · anchored as of" in balance_info["anchor_label"]

        # 5. Verify runtime safe fallback: even if effective_timestamp were NULL, coalesce falls back to transaction_date
        session.close()
        with engine.begin() as conn:
            conn.execute(sa.text("UPDATE transactions SET effective_timestamp = NULL WHERE id = 1"))

        session = SessionLocal()
        fallback_balance = LedgerEngine.get_account_balance(session, 1)
        assert fallback_balance == 65000, "LedgerEngine fallback to transaction_date failed when effective_timestamp was NULL"
    finally:
        session.close()

