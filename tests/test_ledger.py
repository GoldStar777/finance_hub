from datetime import datetime, timezone
import pytest
from sqlalchemy.exc import IntegrityError
from app.models import Account, AccountType, Transaction, TransactionType, ExpenseNature, Category
from app.ledger import LedgerEngine

def test_ledger_balance_calculation(db_session):
    # Setup test accounts
    checking = Account(
        name="Barclays Main",
        account_type=AccountType.CURRENT,
        starting_balance_pence=100000, # £1,000.00
        currency="GBP"
    )
    credit_card = Account(
        name="Amex Gold",
        account_type=AccountType.CREDIT_CARD,
        starting_balance_pence=-20000, # -£200.00
        currency="GBP"
    )
    db_session.add_all([checking, credit_card])
    db_session.commit()

    # Initial balance assertions
    assert LedgerEngine.get_account_balance(db_session, checking.id) == 100000
    assert LedgerEngine.get_account_balance(db_session, credit_card.id) == -20000

    # 1. Add Income of £2,500.50 (250050 pence) to checking
    tx_income = Transaction(
        transaction_date=datetime.now(timezone.utc),
        transaction_type=TransactionType.INCOME,
        amount_pence=250050,
        merchant="Employer",
        account_id=checking.id
    )
    # 2. Add Expense of £65.40 (6540 pence) on credit card
    tx_expense = Transaction(
        transaction_date=datetime.now(timezone.utc),
        transaction_type=TransactionType.EXPENSE,
        amount_pence=6540,
        merchant="Waitrose",
        account_id=credit_card.id,
        expense_nature=ExpenseNature.VARIABLE
    )
    db_session.add_all([tx_income, tx_expense])
    db_session.commit()

    # Checking: 100,000 + 250,050 = 350,050 (£3,500.50)
    assert LedgerEngine.get_account_balance(db_session, checking.id) == 350050
    # Credit Card: -20,000 - 6,540 = -26,540 (-£265.40)
    assert LedgerEngine.get_account_balance(db_session, credit_card.id) == -26540

    # 3. Transfer £100.00 (10000 pence) from checking to credit card
    LedgerEngine.record_transfer(
        db_session,
        source_account_id=checking.id,
        dest_account_id=credit_card.id,
        amount_pence=10000,
        date=datetime.now(timezone.utc),
        notes="Card payment"
    )

    # Checking: 350,050 - 10,000 = 340,050 (£3,400.50)
    assert LedgerEngine.get_account_balance(db_session, checking.id) == 340050
    # Credit Card: -26,540 + 10,000 = -16,540 (-£165.40)
    assert LedgerEngine.get_account_balance(db_session, credit_card.id) == -16540

def test_negative_transaction_amount_rejected_by_check_constraint(db_session):
    account = Account(name="Test Acc", account_type=AccountType.CURRENT, starting_balance_pence=0)
    db_session.add(account)
    db_session.commit()

    # Trying to insert negative amount should fail SQLite CHECK constraint
    tx = Transaction(
        transaction_date=datetime.now(timezone.utc),
        transaction_type=TransactionType.EXPENSE,
        amount_pence=-500, # Invalid!
        merchant="Invalid Tx",
        account_id=account.id
    )
    db_session.add(tx)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

def test_foreign_key_enforcement(db_session):
    # Trying to insert transaction with non-existent account_id must fail foreign key check
    tx = Transaction(
        transaction_date=datetime.now(timezone.utc),
        transaction_type=TransactionType.EXPENSE,
        amount_pence=1000,
        merchant="Ghost Account",
        account_id=999999 # Does not exist!
    )
    db_session.add(tx)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

def test_file_backed_sqlite_wal_mode(file_backed_engine):
    engine, db_file = file_backed_engine
    with engine.connect() as conn:
        from sqlalchemy import text
        res = conn.execute(text("PRAGMA journal_mode;")).scalar()
        assert res.lower() == "wal"

