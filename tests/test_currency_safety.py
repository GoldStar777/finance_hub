import os
import pytest
from decimal import Decimal
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.models import Account, AccountType, Transaction, TransactionType, ExpenseNature, SystemSetting, StagingItem, StagingStatus
from app.core.currency import (
    SUPPORTED_CURRENCIES,
    CurrencySpec,
    get_currency_spec,
    get_stored_base_currency,
    get_effective_base_currency,
    get_base_currency_spec,
    validate_origin_amount,
    format_origin_amount,
    major_to_minor_units,
    minor_to_major_units,
    format_base_amount,
    BASE_CURRENCY_SETTING_KEY
)
from app.ledger import LedgerEngine
from app.core.staging import approve_staging_item, update_staging_item
from app.main import app

@pytest.fixture
def isolated_db(tmp_path):
    """Provides a clean, isolated SQLite database session."""
    db_file = tmp_path / "test_currency.db"
    engine = create_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()

@pytest.fixture
def client(isolated_db):
    """TestClient overriding get_db dependency with isolated_db."""
    def _override_get_db():
        try:
            yield isolated_db
        finally:
            pass

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()

def test_first_run_base_currency_initialization(isolated_db, monkeypatch):
    """Tests that first run initializes and persists default 'GBP' in system_settings."""
    monkeypatch.delenv("BASE_CURRENCY", raising=False)
    assert get_stored_base_currency(isolated_db) is None

    base_curr = get_effective_base_currency(isolated_db)
    assert base_curr == "GBP"

    stored = get_stored_base_currency(isolated_db)
    assert stored == "GBP"

def test_first_run_custom_base_currency_initialization(isolated_db, monkeypatch):
    """Tests that first run initializes from BASE_CURRENCY env var if valid."""
    monkeypatch.setenv("BASE_CURRENCY", "EUR")
    base_curr = get_effective_base_currency(isolated_db)
    assert base_curr == "EUR"
    assert get_stored_base_currency(isolated_db) == "EUR"

def test_base_currency_env_conflict_fails_fast(isolated_db, monkeypatch):
    """Tests that if stored base currency is GBP, conflicting BASE_CURRENCY env var fails fast."""
    isolated_db.add(SystemSetting(key=BASE_CURRENCY_SETTING_KEY, value="GBP"))
    isolated_db.commit()

    # Conflicting env var
    monkeypatch.setenv("BASE_CURRENCY", "USD")
    with pytest.raises(RuntimeError) as exc_info:
        get_effective_base_currency(isolated_db)
    assert "Base currency configuration conflict" in str(exc_info.value)
    assert "Stored base currency in database is 'GBP'" in str(exc_info.value)
    assert "environment variable BASE_CURRENCY is 'USD'" in str(exc_info.value)

    # Unset env var does not conflict
    monkeypatch.delenv("BASE_CURRENCY", raising=False)
    assert get_effective_base_currency(isolated_db) == "GBP"

    # Matching env var succeeds
    monkeypatch.setenv("BASE_CURRENCY", "GBP")
    assert get_effective_base_currency(isolated_db) == "GBP"

def test_unsupported_base_currency_non_two_decimal(isolated_db, monkeypatch):
    """Tests that currencies with 0 or 3 decimals cannot be configured as base currency."""
    monkeypatch.setenv("BASE_CURRENCY", "JPY")
    with pytest.raises(ValueError) as exc_info:
        get_effective_base_currency(isolated_db)
    assert "minor unit precision: 0" in str(exc_info.value)

    monkeypatch.setenv("BASE_CURRENCY", "KWD")
    with pytest.raises(ValueError) as exc_info:
        get_effective_base_currency(isolated_db)
    assert "minor unit precision: 3" in str(exc_info.value)

def test_account_creation_and_update_enforces_base_currency(client, isolated_db):
    """Tests that financial accounts must match configured base currency."""
    get_effective_base_currency(isolated_db)  # sets GBP

    # Creating account with non-base currency fails with HTTP 400
    res_bad = client.post("/api/accounts", json={
        "name": "US Dollar Checking",
        "account_type": "current",
        "currency": "USD",
        "starting_balance": 100.0
    })
    assert res_bad.status_code == 400
    assert "does not match the configured base currency 'GBP'" in res_bad.json()["detail"]

    # Creating account with base currency (or omitted) succeeds
    res_good = client.post("/api/accounts", json={
        "name": "Nationwide Current",
        "account_type": "current",
        "currency": "GBP",
        "starting_balance": 1000.0
    })
    assert res_good.status_code == 201
    acc_id = res_good.json()["id"]
    assert res_good.json()["currency"] == "GBP"

    # Updating account currency to non-base fails with HTTP 400
    res_up_bad = client.put(f"/api/accounts/{acc_id}", json={
        "currency": "EUR"
    })
    assert res_up_bad.status_code == 400
    assert "Cannot change account currency" in res_up_bad.json()["detail"]

def test_foreign_origin_precision_and_validation():
    """Tests explicit precision validation for zero-, two-, and three-decimal currencies."""
    # JPY: 0 decimals
    assert validate_origin_amount(1500, "JPY") == Decimal("1500")
    assert format_origin_amount(1500, "JPY") == "¥1,500"
    with pytest.raises(ValueError) as exc:
        validate_origin_amount("1500.50", "JPY")
    assert "supports at most 0 decimals" in str(exc.value)

    # USD: 2 decimals
    assert validate_origin_amount(42.50, "USD") == Decimal("42.50")
    assert format_origin_amount(42.50, "USD") == "$42.50"
    with pytest.raises(ValueError) as exc:
        validate_origin_amount("42.555", "USD")
    assert "supports at most 2 decimals" in str(exc.value)

    # KWD: 3 decimals
    assert validate_origin_amount("5.250", "KWD") == Decimal("5.250")
    assert format_origin_amount("5.250", "KWD") == "KWD 5.250"
    with pytest.raises(ValueError) as exc:
        validate_origin_amount("5.2505", "KWD")
    assert "supports at most 3 decimals" in str(exc.value)

def test_foreign_transaction_mode_a_actual_bank_charge(client, isolated_db):
    """
    Mode A: User records foreign purchase by entering actual bank-charged base currency.
    Verifies canonical integer minor units and derived implied effective rate.
    """
    get_effective_base_currency(isolated_db)
    acc = Account(name="Travel Card", account_type=AccountType.CREDIT_CARD, currency="GBP", starting_balance_pence=0)
    isolated_db.add(acc)
    isolated_db.commit()

    # User spent $50.00 USD, card statement charged £39.25 GBP
    res = client.post("/api/transactions", json={
        "transaction_type": "expense",
        "account_id": acc.id,
        "merchant": "New York Diner",
        "amount": 39.25,
        "original_amount": 50.00,
        "original_currency": "USD"
    })
    assert res.status_code == 201
    data = res.json()
    assert data["amount_pence"] == 3925
    assert data["amount_pounds"] == 39.25
    assert data["original_amount"] == 50.00
    assert data["original_currency"] == "USD"
    assert data["is_implied_rate"] is True
    assert data["exchange_rate"] == 0.785  # 39.25 / 50.00
    assert "implied effective rate" in data["implied_effective_rate_label"]

    # Ledger balance reflects canonical base amount
    bal = LedgerEngine.get_account_balance(isolated_db, acc.id)
    assert bal == -3925

def test_foreign_transaction_mode_b_exchange_rate_calculation(client, isolated_db):
    """
    Mode B: User enters exchange rate and canonical base amount is calculated via ROUND_HALF_UP.
    """
    get_effective_base_currency(isolated_db)
    acc = Account(name="Current Account", account_type=AccountType.CURRENT, currency="GBP", starting_balance_pence=100000)
    isolated_db.add(acc)
    isolated_db.commit()

    # Spent €40.00 EUR at rate 0.85400000 -> 34.16 GBP (3416 pence)
    res = client.post("/api/transactions", json={
        "transaction_type": "expense",
        "account_id": acc.id,
        "merchant": "Paris Bistro",
        "original_amount": 40.00,
        "original_currency": "EUR",
        "exchange_rate": 0.85400000
    })
    assert res.status_code == 201
    data = res.json()
    assert data["amount_pence"] == 3416
    assert data["amount_pounds"] == 34.16
    assert data["original_amount"] == 40.00
    assert data["original_currency"] == "EUR"
    assert data["exchange_rate"] == 0.85400000

def test_transfers_reject_foreign_currency(client, isolated_db):
    """Tests that internal transfers cannot carry foreign currency metadata."""
    get_effective_base_currency(isolated_db)
    acc1 = Account(name="Checking", account_type=AccountType.CURRENT, currency="GBP", starting_balance_pence=50000)
    acc2 = Account(name="Savings", account_type=AccountType.SAVINGS, currency="GBP", starting_balance_pence=0)
    isolated_db.add_all([acc1, acc2])
    isolated_db.commit()

    res = client.post("/api/transactions", json={
        "transaction_type": "transfer",
        "account_id": acc1.id,
        "destination_account_id": acc2.id,
        "amount": 100.0,
        "original_currency": "USD",
        "original_amount": 125.0
    })
    assert res.status_code == 400
    assert "Foreign currency tracking is not supported on internal transfers" in res.json()["detail"]

def test_staging_blocks_approval_when_base_amount_missing(isolated_db):
    """
    Tests that a foreign-denominated receipt or statement item with missing base amount
    cannot be approved into the ledger until resolved by the user.
    """
    get_effective_base_currency(isolated_db)
    acc = Account(name="Main Card", account_type=AccountType.CREDIT_CARD, currency="GBP", starting_balance_pence=0)
    isolated_db.add(acc)
    isolated_db.commit()

    import json
    payload = {
        "transaction_type": "expense",
        "currency": "GBP",
        "original_amount": 45.00,
        "original_currency": "USD",
        "requires_base_amount": True,
        "currency_conflict": True,
        "currency_conflict_message": "Receipt is in USD (45.00). Enter actual GBP charge."
    }
    item = StagingItem(
        status=StagingStatus.PENDING,
        extracted_merchant="Cafe Manhattan",
        extracted_date=datetime.now(timezone.utc),
        extracted_amount_pence=None,  # Not yet provided by user!
        suggested_account_id=acc.id,
        source_type="receipt_image",
        raw_payload_json=json.dumps(payload)
    )
    isolated_db.add(item)
    isolated_db.commit()

    # Attempting to approve must fail
    with pytest.raises(ValueError) as exc:
        approve_staging_item(isolated_db, item.id)
    assert "positive base-currency (GBP) transaction amount is required" in str(exc.value)

    # User updates the item with the actual card charge (£35.40)
    update_staging_item(isolated_db, item.id, {"amount": 35.40})
    isolated_db.refresh(item)
    assert item.extracted_amount_pence == 3540

    # Approval now succeeds atomically
    tx = approve_staging_item(isolated_db, item.id)
    assert tx.amount_pence == 3540
    assert tx.original_currency == "USD"
    assert tx.original_amount == Decimal("45.00")
    assert tx.exchange_rate is not None
    assert round(float(tx.exchange_rate), 4) == round(35.40 / 45.00, 4)

def test_alembic_migration_compatibility(tmp_path):
    """Tests the Alembic migration up and down against an isolated temporary database."""
    from alembic.config import Config
    from alembic import command
    from pathlib import Path

    base_dir = Path(__file__).resolve().parent.parent
    ini_path = base_dir / "alembic.ini"
    test_db = tmp_path / "migration_test.db"

    cfg = Config(str(ini_path))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{test_db}")

    # Setup isolated database in 8d1f2a3c4b5e schema state
    engine = create_engine(f"sqlite:///{test_db}")
    with engine.begin() as conn:
        from sqlalchemy import text
        conn.execute(text("""
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
        conn.execute(text("""
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
                expense_nature VARCHAR(20) DEFAULT 'unclassified' NOT NULL
            );
        """))
        conn.execute(text("""
            CREATE TABLE system_settings (
                key VARCHAR(100) PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
        """))
        conn.execute(text("""
            INSERT INTO accounts (id, name, account_type, starting_balance_pence, currency, color, is_active, valuation_mode)
            VALUES (1, 'Test Acc', 'current', 1000, 'GBP', '#3B82F6', 1, 'snapshot');
        """))
        conn.execute(text("""
            INSERT INTO transactions (id, transaction_date, transaction_type, amount_pence, merchant, entry_method, account_id, expense_nature)
            VALUES (1, CURRENT_TIMESTAMP, 'expense', 5000, 'Pre-migration Shop', 'manual', 1, 'variable');
        """))

    command.stamp(cfg, "8d1f2a3c4b5e")

    # Upgrade to new head (c3d4e5f6a7b8)
    command.upgrade(cfg, "c3d4e5f6a7b8")

    # Verify column existence and that pre-existing transaction has NULLs
    with engine.connect() as conn:
        from sqlalchemy import text
        row = conn.execute(text("SELECT id, amount_pence, original_amount, original_currency, exchange_rate FROM transactions WHERE id = 1")).fetchone()
        assert row[0] == 1
        assert row[1] == 5000
        assert row[2] is None  # original_amount
        assert row[3] is None  # original_currency
        assert row[4] is None  # exchange_rate

        # Verify base_currency was initialized in system_settings
        setting = conn.execute(text("SELECT value FROM system_settings WHERE key = 'base_currency'")).fetchone()
        assert setting[0] == "GBP"

    # Downgrade back to 8d1f2a3c4b5e
    command.downgrade(cfg, "8d1f2a3c4b5e")

    with engine.connect() as conn:
        insp = create_engine(f"sqlite:///{test_db}").connect()
        from sqlalchemy import inspect
        cols = {c["name"] for c in inspect(engine).get_columns("transactions")}
        assert "original_amount" not in cols
        assert "original_currency" not in cols
        assert "exchange_rate" not in cols
        # Transaction still exists intact
        count = conn.execute(text("SELECT COUNT(*) FROM transactions")).scalar()
        assert count == 1

def test_api_system_config_endpoint(client, isolated_db):
    """Verifies GET /api/system/config returns base currency and supported currencies registry."""
    res = client.get("/api/system/config")
    assert res.status_code == 200
    data = res.json()
    assert data["base_currency"] == "GBP"
    assert data["base_currency_symbol"] == "£"
    assert data["base_currency_decimals"] == 2
    assert "supported_currencies" in data
    assert "USD" in data["supported_currencies"]
    assert data["supported_currencies"]["USD"]["symbol"] == "$"
    assert data["supported_currencies"]["USD"]["can_be_base"] is True
    assert "JPY" in data["supported_currencies"]
    assert data["supported_currencies"]["JPY"]["can_be_base"] is False

