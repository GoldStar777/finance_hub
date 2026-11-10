"""
Comprehensive Regression & Audit Test Suite for Finance Hub's Simplified Ground-Truth Reconciliation Model.

Verifies the 8 core requirements from the ground-truth reconciliation specification:
1. Reconciling an account atomically creates a snapshot and a new balance anchor.
2. The anchor uses the confirmed statement balance and resolved effective timestamp.
3. A discrepancy with an optional note saves successfully without altering the anchor balance or existing ledger entries.
4. An optional missing transaction entered during reconciliation appears in cash-flow and spending analysis,
   but does not alter the confirmed anchor balance or double-deduct from the account balance.
5. Transactions after the anchor alter the current balance.
6. Editing or adding a transaction before a later anchor changes historical balances before that anchor,
   but does not change balances on or after the anchor.
7. A failure during reconciliation rolls back both the snapshot and the anchor.
8. Existing transfers, investments, historical analysis, and profile isolation continue working under this model.
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import (
    Base,
    Account,
    AccountType,
    Transaction,
    TransactionType,
    ExpenseNature,
    Category,
    AccountBalanceAnchor,
    AccountSnapshot,
    Holding,
    HoldingValuation,
)
from app.ledger import LedgerEngine
from app.core.timezone import ensure_utc, resolve_anchor_datetime
from app.core.reconciliation import (
    create_reconciliation_snapshot,
    get_reconciliation_summary,
    list_reconciliation_snapshots,
    delete_reconciliation_snapshot,
)
from app.core.cashflow import get_cashflow_summary
from app.core.analysis import compute_balances_and_net_worth


@pytest.fixture
def audit_db(tmp_path):
    """Creates a clean, isolated SQLite database for audit tests."""
    db_file = tmp_path / "audit_balance.db"
    engine = create_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def test_scenario_1_atomic_snapshot_and_anchor_creation(audit_db):
    """
    Scenario 1:
    Reconciling an account atomically creates a snapshot and a new balance anchor.
    """
    t_start = datetime(2026, 10, 1, 0, 0, 0, tzinfo=timezone.utc)
    acc = Account(
        name="Main Current Account",
        account_type=AccountType.CURRENT,
        currency="GBP",
        is_active=True,
    )
    acc.balance_anchors.append(
        AccountBalanceAnchor(
            balance_pence=100000,  # £1,000.00
            anchor_date=t_start,
            is_opening=True,
            notes="Opening balance",
        )
    )
    audit_db.add(acc)
    audit_db.commit()

    # Pre-reconciliation checks
    assert audit_db.query(AccountSnapshot).filter(AccountSnapshot.account_id == acc.id).count() == 0
    assert audit_db.query(AccountBalanceAnchor).filter(AccountBalanceAnchor.account_id == acc.id).count() == 1

    # User reconciles statement balance: £1,200.00 (120,000 pence)
    res = create_reconciliation_snapshot(
        db=audit_db,
        account_id=acc.id,
        actual_balance_pence=120000,
        as_of_mode="now",
        notes="Monthly statement check",
    )

    # Both snapshot and anchor must be present in response
    assert "snapshot" in res
    assert "anchor" in res
    assert res["snapshot"]["actual_balance_pence"] == 120000
    assert res["anchor"]["balance_pence"] == 120000
    assert res["new_calculated_balance_pence"] == 120000

    # In database: both records exist
    snapshots = audit_db.query(AccountSnapshot).filter(AccountSnapshot.account_id == acc.id).all()
    anchors = audit_db.query(AccountBalanceAnchor).filter(AccountBalanceAnchor.account_id == acc.id).all()

    assert len(snapshots) == 1
    assert len(anchors) == 2  # Opening anchor + new reconciliation anchor

    new_anchor = [a for a in anchors if not a.is_opening][0]
    assert new_anchor.balance_pence == 120000
    assert snapshots[0].actual_balance_pence == 120000
    assert snapshots[0].calculated_balance_pence == 100000
    assert snapshots[0].discrepancy_pence == 20000


def test_scenario_2_anchor_uses_statement_balance_and_resolved_timestamp(audit_db):
    """
    Scenario 2:
    The anchor uses the confirmed statement balance and resolved effective timestamp.
    """
    t_start = datetime(2026, 9, 1, 0, 0, 0, tzinfo=timezone.utc)
    acc = Account(
        name="Savings Account",
        account_type=AccountType.SAVINGS,
        currency="GBP",
        is_active=True,
    )
    acc.balance_anchors.append(
        AccountBalanceAnchor(
            balance_pence=50000,
            anchor_date=t_start,
            is_opening=True,
        )
    )
    audit_db.add(acc)
    audit_db.commit()

    # Reconcile as of a past date: "2026-09-30"
    expected_cutoff = resolve_anchor_datetime("date", "2026-09-30", tz_str="Europe/London")
    res = create_reconciliation_snapshot(
        db=audit_db,
        account_id=acc.id,
        actual_balance_pence=75000,  # £750.00
        as_of_mode="date",
        as_of_date="2026-09-30",
        notes="September month-end bank statement",
    )

    anchor_data = res["anchor"]
    assert anchor_data["balance_pence"] == 75000
    assert ensure_utc(anchor_data["anchor_date"]) == ensure_utc(expected_cutoff)

    # LedgerEngine balance as of that cutoff is exactly £750.00
    assert LedgerEngine.get_account_balance(audit_db, acc.id, as_of=expected_cutoff) == 75000


def test_scenario_3_discrepancy_note_preserves_anchor_and_existing_transactions(audit_db):
    """
    Scenario 3:
    A discrepancy with an optional note saves successfully without altering the anchor balance
    or existing ledger entries.
    """
    t_start = datetime(2026, 10, 1, 0, 0, 0, tzinfo=timezone.utc)
    acc = Account(
        name="Current Account",
        account_type=AccountType.CURRENT,
        currency="GBP",
        is_active=True,
    )
    acc.balance_anchors.append(
        AccountBalanceAnchor(
            balance_pence=100000,  # £1,000.00
            anchor_date=t_start,
            is_opening=True,
        )
    )
    audit_db.add(acc)
    audit_db.commit()

    # Create 2 existing transactions
    t1 = datetime(2026, 10, 5, 12, 0, 0, tzinfo=timezone.utc)
    tx1 = Transaction(
        transaction_date=t1,
        effective_timestamp=t1,
        transaction_type=TransactionType.EXPENSE,
        amount_pence=15000,  # £150
        merchant="Groceries",
        account_id=acc.id,
    )
    t2 = datetime(2026, 10, 8, 12, 0, 0, tzinfo=timezone.utc)
    tx2 = Transaction(
        transaction_date=t2,
        effective_timestamp=t2,
        transaction_type=TransactionType.INCOME,
        amount_pence=30000,  # £300
        merchant="Freelance Payment",
        account_id=acc.id,
    )
    audit_db.add_all([tx1, tx2])
    audit_db.commit()

    # Pre-reconciliation balance: £1,000 - £150 + £300 = £1,150 (115,000 pence)
    assert LedgerEngine.get_account_balance(audit_db, acc.id) == 115000

    # User enters statement balance: £1,100 (discrepancy: -£50) with an explanation note
    t_recon = datetime(2026, 10, 15, 12, 0, 0, tzinfo=timezone.utc)
    res = create_reconciliation_snapshot(
        db=audit_db,
        account_id=acc.id,
        actual_balance_pence=110000,  # £1,100
        snapshot_date=t_recon,
        notes="Bank monthly maintenance fee missing from records",
    )

    # 1. Snapshot preserves discrepancy and note
    assert res["snapshot"]["discrepancy_pence"] == -5000  # -£50.00
    assert res["snapshot"]["notes"] == "Bank monthly maintenance fee missing from records"

    # 2. Anchor balance is confirmed statement balance (not altered by note)
    assert res["anchor"]["balance_pence"] == 110000
    assert res["new_calculated_balance_pence"] == 110000

    # 3. Existing ledger transactions are COMPLETELY UNTOUCHED
    tx1_db = audit_db.query(Transaction).filter(Transaction.id == tx1.id).first()
    tx2_db = audit_db.query(Transaction).filter(Transaction.id == tx2.id).first()
    assert tx1_db.amount_pence == 15000
    assert tx1_db.merchant == "Groceries"
    assert tx2_db.amount_pence == 30000
    assert tx2_db.merchant == "Freelance Payment"
    # No synthetic adjustment transaction created
    all_txs = audit_db.query(Transaction).filter(Transaction.account_id == acc.id).all()
    assert len(all_txs) == 2


def test_scenario_4_missing_transaction_in_cashflow_without_double_deduction(audit_db):
    """
    Scenario 4:
    An optional missing transaction entered during reconciliation appears in cash-flow
    and spending analysis, but does not alter the confirmed anchor balance or double-deduct
    from the account balance.
    """
    t_start = datetime(2026, 10, 1, 0, 0, 0, tzinfo=timezone.utc)
    acc = Account(
        name="Checking Account",
        account_type=AccountType.CURRENT,
        currency="GBP",
        is_active=True,
    )
    acc.balance_anchors.append(
        AccountBalanceAnchor(
            balance_pence=100000,  # £1,000.00
            anchor_date=t_start,
            is_opening=True,
        )
    )
    cat = Category(name="Dining & Coffee", color="#F59E0B")
    audit_db.add_all([acc, cat])
    audit_db.commit()

    # Pre-reconciliation calculated balance = £1,000.00
    assert LedgerEngine.get_account_balance(audit_db, acc.id) == 100000

    # User reconciles statement balance on Oct 20: £950.00 (discrepancy: -£50)
    # User provides missing transaction: £50 at "Artisan Cafe" on Oct 10
    t_recon = datetime(2026, 10, 20, 23, 59, 59, tzinfo=timezone.utc)
    res = create_reconciliation_snapshot(
        db=audit_db,
        account_id=acc.id,
        actual_balance_pence=95000,  # £950.00
        snapshot_date=t_recon,
        notes="Unrecorded coffee shop visit",
        missing_transaction={
            "transaction_type": "expense",
            "amount": 50.0,
            "merchant": "Artisan Cafe",
            "category_id": cat.id,
            "transaction_date": "2026-10-10",
            "notes": "Team coffee meetup",
        },
    )

    # Verification:
    # 1. Missing transaction was created
    assert res["missing_transaction_created"] is True
    assert res["missing_transaction_id"] is not None

    missing_tx = audit_db.query(Transaction).filter(Transaction.id == res["missing_transaction_id"]).first()
    assert missing_tx is not None
    assert missing_tx.merchant == "Artisan Cafe"
    assert missing_tx.amount_pence == 5000
    assert missing_tx.category_id == cat.id
    # Nominal date is October 10
    assert missing_tx.transaction_date.strftime("%Y-%m-%d") == "2026-10-10"
    # Effective timestamp is on or before anchor date
    assert ensure_utc(missing_tx.effective_timestamp) <= ensure_utc(t_recon)

    # 2. NO DOUBLE DEDUCTION:
    # Account balance must be EXACTLY £950.00 (95,000 pence), NOT £900.00!
    assert LedgerEngine.get_account_balance(audit_db, acc.id) == 95000
    assert res["new_calculated_balance_pence"] == 95000

    # 3. Missing transaction appears in Cash-Flow summary for October 2026
    cf = get_cashflow_summary(
        db=audit_db,
        month_str="2026-10",
        currency_param="GBP",
    )
    assert cf["total_expenses_pence"] == 5000  # The £50 coffee expense is reported in cash-flow!
    assert len(cf["categories"]) == 1
    assert cf["categories"][0]["category_name"] == "Dining & Coffee"
    assert cf["categories"][0]["total_pence"] == 5000


def test_scenario_5_transactions_after_anchor_alter_current_balance(audit_db):
    """
    Scenario 5:
    Transactions after the anchor alter the current balance.
    """
    t_recon = datetime(2026, 10, 20, 12, 0, 0, tzinfo=timezone.utc)
    acc = Account(
        name="Operational Account",
        account_type=AccountType.CURRENT,
        currency="GBP",
        is_active=True,
    )
    acc.balance_anchors.append(
        AccountBalanceAnchor(
            balance_pence=100000,  # £1,000.00
            anchor_date=t_recon,
            is_opening=False,
            notes="Reconciliation anchor",
        )
    )
    audit_db.add(acc)
    audit_db.commit()

    # Pre-transaction balance is £1,000.00
    assert LedgerEngine.get_account_balance(audit_db, acc.id) == 100000

    # Record expense occurring strictly AFTER the anchor: Oct 25
    t_after = datetime(2026, 10, 25, 15, 0, 0, tzinfo=timezone.utc)
    tx_after = Transaction(
        transaction_date=t_after,
        effective_timestamp=t_after,
        transaction_type=TransactionType.EXPENSE,
        amount_pence=15000,  # £150.00
        merchant="Office Supplies",
        account_id=acc.id,
    )
    audit_db.add(tx_after)
    audit_db.commit()

    # Balance after anchor reflects the expense: £1,000 - £150 = £850 (85,000 pence)
    assert LedgerEngine.get_account_balance(audit_db, acc.id) == 85000

    # Summary metrics also reflect the change
    summary = LedgerEngine.get_dashboard_summary(audit_db)
    assert summary["total_liquid_pence"] == 85000
    assert summary["net_worth_pence"] == 85000


def test_scenario_6_earlier_edits_bounded_by_later_anchors(audit_db):
    """
    Scenario 6:
    Editing or adding a transaction before a later anchor changes historical balances
    before that anchor, but does not change balances on or after the anchor.
    """
    # 1. April 30 anchor: £1,000.00
    t_april = datetime(2026, 4, 30, 23, 59, 59, tzinfo=timezone.utc)
    acc = Account(
        name="Bounded Checking",
        account_type=AccountType.CURRENT,
        currency="GBP",
        is_active=True,
    )
    acc.balance_anchors.append(
        AccountBalanceAnchor(
            balance_pence=100000,
            anchor_date=t_april,
            is_opening=True,
        )
    )
    audit_db.add(acc)
    audit_db.commit()

    # 2. June 15 transaction: expense £200.00
    t_june = datetime(2026, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
    tx_june = Transaction(
        transaction_date=t_june,
        effective_timestamp=t_june,
        transaction_type=TransactionType.EXPENSE,
        amount_pence=20000,
        merchant="June Vendor",
        account_id=acc.id,
    )
    audit_db.add(tx_june)
    audit_db.commit()

    # 3. October 31 anchor: £1,500.00
    t_october = datetime(2026, 10, 31, 23, 59, 59, tzinfo=timezone.utc)
    acc.balance_anchors.append(
        AccountBalanceAnchor(
            balance_pence=150000,
            anchor_date=t_october,
            is_opening=False,
        )
    )
    audit_db.commit()

    # Pre-edit check:
    t_june_end = datetime(2026, 6, 30, 23, 59, 59, tzinfo=timezone.utc)
    t_nov = datetime(2026, 11, 1, 0, 0, 0, tzinfo=timezone.utc)
    assert LedgerEngine.get_account_balance(audit_db, acc.id, as_of=t_june_end) == 80000
    assert LedgerEngine.get_account_balance(audit_db, acc.id, as_of=t_nov) == 150000
    assert LedgerEngine.get_account_balance(audit_db, acc.id) == 150000

    # 4. Edit June transaction: increase expense from £200 to £350 (35,000 pence)
    tx_june.amount_pence = 35000
    audit_db.commit()

    # Historical June balance changes to £650 (65,000 pence):
    assert LedgerEngine.get_account_balance(audit_db, acc.id, as_of=t_june_end) == 65000

    # Balance on or after October anchor is BOUNDED and DOES NOT CHANGE (remains £1,500):
    assert LedgerEngine.get_account_balance(audit_db, acc.id, as_of=t_nov) == 150000
    assert LedgerEngine.get_account_balance(audit_db, acc.id) == 150000


def test_scenario_7_atomic_rollback_on_failure(audit_db):
    """
    Scenario 7:
    A failure during reconciliation rolls back both the snapshot and the anchor.
    """
    t_start = datetime(2026, 10, 1, 0, 0, 0, tzinfo=timezone.utc)
    acc = Account(
        name="Rollback Checking",
        account_type=AccountType.CURRENT,
        currency="GBP",
        is_active=True,
    )
    acc.balance_anchors.append(
        AccountBalanceAnchor(
            balance_pence=100000,
            anchor_date=t_start,
            is_opening=True,
        )
    )
    audit_db.add(acc)
    audit_db.commit()

    initial_snaps = audit_db.query(AccountSnapshot).filter(AccountSnapshot.account_id == acc.id).count()
    initial_anchors = audit_db.query(AccountBalanceAnchor).filter(AccountBalanceAnchor.account_id == acc.id).count()

    # Simulate an error during commit/flush
    with patch.object(audit_db, "commit", side_effect=RuntimeError("Simulated database write error")):
        with pytest.raises(RuntimeError, match="Simulated database write error"):
            create_reconciliation_snapshot(
                db=audit_db,
                account_id=acc.id,
                actual_balance_pence=120000,
                notes="Will fail",
            )

    # Verification: BOTH snapshot and anchor rolled back
    final_snaps = audit_db.query(AccountSnapshot).filter(AccountSnapshot.account_id == acc.id).count()
    final_anchors = audit_db.query(AccountBalanceAnchor).filter(AccountBalanceAnchor.account_id == acc.id).count()

    assert final_snaps == initial_snaps
    assert final_anchors == initial_anchors


def test_scenario_8_transfers_investments_historical_analysis_preservation(audit_db):
    """
    Scenario 8:
    Existing transfers, investments, historical analysis, and profile isolation
    continue working under this model.
    """
    t_base = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

    # 1. Transfers preserve net worth
    acc_from = Account(name="Current", account_type=AccountType.CURRENT, currency="GBP", is_active=True)
    acc_to = Account(name="Savings", account_type=AccountType.SAVINGS, currency="GBP", is_active=True)
    acc_from.balance_anchors.append(AccountBalanceAnchor(balance_pence=100000, anchor_date=t_base, is_opening=True))
    acc_to.balance_anchors.append(AccountBalanceAnchor(balance_pence=50000, anchor_date=t_base, is_opening=True))

    # Investment account
    acc_inv = Account(name="ISA Portfolio", account_type=AccountType.INVESTMENT, currency="GBP", is_active=True)

    audit_db.add_all([acc_from, acc_to, acc_inv])
    audit_db.commit()

    net_worth_before = LedgerEngine.get_dashboard_summary(audit_db)["net_worth_pence"]
    assert net_worth_before == 150000

    LedgerEngine.record_transfer(
        db=audit_db,
        source_account_id=acc_from.id,
        dest_account_id=acc_to.id,
        amount_pence=25000,
        date=datetime(2026, 2, 1, 10, 0, 0, tzinfo=timezone.utc),
    )

    net_worth_after = LedgerEngine.get_dashboard_summary(audit_db)["net_worth_pence"]
    assert net_worth_after == net_worth_before  # Net worth perfectly preserved

    # 2. Investment accounts derive balances from holdings valuation
    holding = Holding(
        name="Global Index Fund",
        ticker="VWRL",
        asset_class="equity",
        currency="GBP",
        account_id=acc_inv.id,
    )
    audit_db.add(holding)
    audit_db.commit()

    audit_db.add(
        HoldingValuation(
            holding_id=holding.id,
            effective_date=datetime(2026, 3, 1, 12, 0, 0, tzinfo=timezone.utc),
            quantity=10.0,
            unit_price_pence=10000,
            valuation_pence=100000,
        )
    )
    audit_db.commit()

    assert LedgerEngine.get_account_balance(audit_db, acc_inv.id) == 100000

    # Investment accounts reject balance reconciliation
    with pytest.raises(ValueError, match="Investment accounts use the Portfolios and Holdings valuation workflow"):
        create_reconciliation_snapshot(
            db=audit_db,
            account_id=acc_inv.id,
            actual_balance_pence=100000,
        )

    # 3. Historical Analysis inference marker
    buckets = [
        {"key": "2025-12-31", "label": "Dec 2025", "end_date": "2025-12-31", "as_of_utc": datetime(2025, 12, 31, 23, 59, 59, tzinfo=timezone.utc), "is_partial": False, "partial_label": None},
        {"key": "2026-03-31", "label": "Mar 2026", "end_date": "2026-03-31", "as_of_utc": datetime(2026, 3, 31, 23, 59, 59, tzinfo=timezone.utc), "is_partial": False, "partial_label": None},
    ]
    analysis = compute_balances_and_net_worth(audit_db, buckets, "GBP")

    # Dec 2025 is before Jan 1 opening anchor -> must be flagged as inferred
    assert analysis[0]["account_balances"][0]["is_inferred"] is True
    # Mar 2026 is after opening anchor -> not inferred
    assert analysis[1]["account_balances"][0]["is_inferred"] is False
