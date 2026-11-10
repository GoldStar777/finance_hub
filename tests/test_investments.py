import pytest
from datetime import datetime, timezone, timedelta
from decimal import Decimal
import sqlalchemy as sa
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from app.database import Base
from app.models import Account, AccountType, AssetSnapshot, Holding, HoldingValuation
from app.ledger import LedgerEngine
from app.core.investments import (
    get_holding_latest_valuation, get_account_holdings_breakdown,
    sync_account_checkpoint_snapshot, get_portfolio_summary
)
from app.main import app
from app.database import get_db

# Fixtures db_session and client are provided by tests/conftest.py


def test_investment_account_balance_and_snapshot_conversion(db_session):
    """Verifies that an investment account balance derives from holdings, and snapshot histories convert cleanly."""
    acc = Account(
        name="Vanguard ISA",
        account_type=AccountType.INVESTMENT,
        currency="GBP"
    )
    db_session.add(acc)
    db_session.commit()

    # Without holdings or snapshots, balance is 0
    bal = LedgerEngine.get_account_balance(db_session, acc.id)
    assert bal == 0

    # Add historical AssetSnapshot
    snap = AssetSnapshot(
        account_id=acc.id,
        valuation_pence=250000,
        effective_date=datetime.now(timezone.utc)
    )
    db_session.add(snap)
    db_session.commit()

    # Before conversion, balance is still 0 (no holdings yet)
    assert LedgerEngine.get_account_balance(db_session, acc.id) == 0

    # Run idempotent conversion migration step
    from app.core.investments import convert_snapshot_histories_to_holdings
    res = convert_snapshot_histories_to_holdings(db_session)
    assert res["converted_accounts"] == 1
    assert res["created_holdings"] == 1
    assert res["created_valuations"] == 1

    # After conversion, balance is derived from the synthetic holding
    bal = LedgerEngine.get_account_balance(db_session, acc.id)
    assert bal == 250000
    synth = db_session.query(Holding).filter(Holding.account_id == acc.id).first()
    assert synth.name == "Portfolio Valuation"
    assert synth.asset_class == "portfolio"


def test_holding_creation_with_fractional_units(db_session):
    """Tests fractional quantity support (e.g. 15.48201234 shares)."""
    acc = Account(
        name="Trading 212",
        account_type=AccountType.INVESTMENT,
        currency="GBP"
    )
    db_session.add(acc)
    db_session.commit()

    holding = Holding(
        account_id=acc.id,
        name="Vanguard S&P 500 UCITS ETF",
        ticker="VUAG",
        asset_class="etf",
        currency="GBP"
    )
    db_session.add(holding)
    db_session.commit()

    # Add fractional valuation: 15.48201234 shares @ £85.1234 = £1317.88 (131788 pence)
    val = HoldingValuation(
        holding_id=holding.id,
        effective_date=datetime.now(timezone.utc),
        quantity=Decimal("15.48201234"),
        unit_price_pence=Decimal("8512.34"),
        valuation_pence=131788
    )
    db_session.add(val)
    db_session.commit()

    latest = get_holding_latest_valuation(db_session, holding.id)
    assert latest is not None
    assert latest.quantity == Decimal("15.48201234")
    assert latest.valuation_pence == 131788


def test_holdings_immediately_determine_balance_without_mode_switch(db_session):
    """
    Ensures that adding holdings immediately determines account balance,
    eliminating the silent exclusion issue.
    """
    acc = Account(
        name="Fidelity SIPP",
        account_type=AccountType.INVESTMENT,
        currency="GBP"
    )
    db_session.add(acc)
    db_session.commit()

    # User adds a holding with £1,000 value
    h1 = Holding(account_id=acc.id, name="Fund A", asset_class="fund")
    db_session.add(h1)
    db_session.commit()
    val1 = HoldingValuation(
        holding_id=h1.id,
        effective_date=datetime.now(timezone.utc),
        quantity=Decimal("10"),
        valuation_pence=100000
    )
    db_session.add(val1)
    db_session.commit()

    # Holdings immediately determine account balance without requiring any mode switch
    assert LedgerEngine.get_account_balance(db_session, acc.id) == 100000


def test_unvalued_holding_distinguished_from_zero_valuation(db_session):
    """
    Ensures active holdings without any valuation are explicitly tracked as unvalued,
    while zero is a valid recorded valuation.
    """
    acc = Account(
        name="Crypto Wallet",
        account_type=AccountType.INVESTMENT,
        currency="GBP",
        valuation_mode="holdings"
    )
    db_session.add(acc)
    db_session.commit()

    # Holding 1: Valued at zero (e.g. fully sold or closed)
    h_zero = Holding(account_id=acc.id, name="Token Zero", ticker="ZRO")
    db_session.add(h_zero)
    db_session.commit()
    val_zero = HoldingValuation(
        holding_id=h_zero.id,
        effective_date=datetime.now(timezone.utc),
        quantity=Decimal("0"),
        valuation_pence=0
    )
    db_session.add(val_zero)

    # Holding 2: Unvalued (no valuation records at all)
    h_unvalued = Holding(account_id=acc.id, name="Token Pending", ticker="PND")
    db_session.add(h_unvalued)

    # Holding 3: Valued at £500
    h_active = Holding(account_id=acc.id, name="Bitcoin", ticker="BTC")
    db_session.add(h_active)
    db_session.commit()
    val_btc = HoldingValuation(
        holding_id=h_active.id,
        effective_date=datetime.now(timezone.utc),
        quantity=Decimal("0.01"),
        valuation_pence=50000
    )
    db_session.add(val_btc)
    db_session.commit()

    breakdown = get_account_holdings_breakdown(db_session, acc.id)
    assert breakdown["holdings_count"] == 3
    assert breakdown["valued_count"] == 2 # h_zero and h_active
    assert breakdown["unvalued_count"] == 1 # h_unvalued
    assert breakdown["has_unvalued_holdings"] is True
    assert breakdown["total_pence"] == 50000 # 0 + 0 + 50000


def test_out_of_order_valuations_and_corrections(db_session):
    """
    Tests that chronological ordering is strictly preserved by effective_date DESC,
    and deleting/updating an errant record cleanly recalculates.
    """
    acc = Account(name="Test Acc", account_type=AccountType.INVESTMENT, currency="GBP")
    db_session.add(acc)
    db_session.commit()

    h = Holding(account_id=acc.id, name="Apple Inc", ticker="AAPL")
    db_session.add(h)
    db_session.commit()

    t_now = datetime.now(timezone.utc)
    t_past = t_now - timedelta(days=30)

    # 1. Enter today's valuation: 10 units @ £150 = £1,500
    v_today = HoldingValuation(
        holding_id=h.id,
        effective_date=t_now,
        quantity=Decimal("10"),
        valuation_pence=150000
    )
    db_session.add(v_today)
    db_session.commit()

    assert get_holding_latest_valuation(db_session, h.id).valuation_pence == 150000

    # 2. Enter backdated valuation from last month: 8 units @ £140 = £1,120
    v_last_month = HoldingValuation(
        holding_id=h.id,
        effective_date=t_past,
        quantity=Decimal("8"),
        valuation_pence=112000
    )
    db_session.add(v_last_month)
    db_session.commit()

    # Effective valuation is STILL today's valuation!
    assert get_holding_latest_valuation(db_session, h.id).valuation_pence == 150000

    # Querying as of past date returns past valuation
    assert get_holding_latest_valuation(db_session, h.id, as_of_date=t_past).valuation_pence == 112000

    # 3. Correction: Delete today's valuation
    db_session.delete(v_today)
    db_session.commit()

    # Now past valuation is promoted as the latest
    assert get_holding_latest_valuation(db_session, h.id).valuation_pence == 112000


def test_checkpoint_sync_rule(db_session):
    """
    Tests that checkpoint sync generates an AssetSnapshot matching the sum of
    latest valuations for each active holding as of the specified date.
    """
    acc = Account(name="Index Portfolio", account_type=AccountType.INVESTMENT, currency="GBP")
    db_session.add(acc)
    db_session.commit()

    h1 = Holding(account_id=acc.id, name="Fund 1")
    h2 = Holding(account_id=acc.id, name="Fund 2")
    db_session.add_all([h1, h2])
    db_session.commit()

    t1 = datetime(2026, 10, 1, tzinfo=timezone.utc)
    t2 = datetime(2026, 10, 15, tzinfo=timezone.utc)

    # h1 valued at t1: £1,000; at t2: £1,200
    db_session.add(HoldingValuation(holding_id=h1.id, effective_date=t1, quantity=Decimal("10"), valuation_pence=100000))
    db_session.add(HoldingValuation(holding_id=h1.id, effective_date=t2, quantity=Decimal("10"), valuation_pence=120000))

    # h2 valued only at t1: £800
    db_session.add(HoldingValuation(holding_id=h2.id, effective_date=t1, quantity=Decimal("5"), valuation_pence=80000))
    db_session.commit()

    # Checkpoint at t1: h1(1000) + h2(800) = 1800
    snap_t1 = sync_account_checkpoint_snapshot(db_session, acc.id, effective_date=t1)
    assert snap_t1.valuation_pence == 180000

    # Checkpoint at t2: h1(1200) + h2(800 from t1) = 2000
    snap_t2 = sync_account_checkpoint_snapshot(db_session, acc.id, effective_date=t2)
    assert snap_t2.valuation_pence == 200000


def test_api_investments_endpoints(client, db_session):
    """Tests the full REST API lifecycle for investments."""
    # 1. Create account
    res = client.post("/api/accounts", json={
        "name": "Robinhood",
        "account_type": "investment",
        "currency": "GBP",
        "starting_balance": 0.0
    })
    assert res.status_code == 201
    acc_id = res.json()["id"]

    # 2. Add holding with initial valuation
    res = client.post(f"/api/investments/accounts/{acc_id}/holdings", json={
        "name": "Tesla Inc",
        "ticker": "TSLA",
        "asset_class": "equity",
        "initial_quantity": 5.5,
        "initial_unit_price": 200.0
    })
    assert res.status_code == 201
    holding_data = res.json()
    holding_id = holding_data["id"]
    assert holding_data["latest_quantity"] == 5.5
    assert holding_data["latest_valuation_pence"] == 110000 # £1100.00
    assert holding_data["is_valued"] is True

    # 3. Switch valuation mode to holdings
    res = client.put(f"/api/investments/accounts/{acc_id}/valuation-mode", json={
        "valuation_mode": "holdings"
    })
    assert res.status_code == 200
    assert res.json()["valuation_mode"] == "holdings"
    assert res.json()["current_balance_pence"] == 110000

    # 4. Check summary endpoint
    res = client.get("/api/investments/summary")
    assert res.status_code == 200
    summary = res.json()
    assert summary["total_invested_pence"] == 110000
    assert len(summary["accounts"]) >= 1

    # 5. Check dashboard summary reflects invested assets
    res = client.get("/api/dashboard/summary")
    assert res.status_code == 200
    dash = res.json()
    assert dash["total_invested_pence"] == 110000
    assert dash["formatted_total_invested"] == "£1,100.00"

    # 6. Add second valuation checkpoint (quantity increase)
    res = client.post(f"/api/investments/holdings/{holding_id}/valuations", json={
        "quantity": 10.0,
        "unit_price": 210.0,
        "notes": "Added 4.5 shares"
    })
    assert res.status_code == 201
    val_id = res.json()["id"]
    assert res.json()["valuation_pence"] == 210000

    # 7. Check account holdings endpoint
    res = client.get(f"/api/investments/accounts/{acc_id}/holdings")
    assert res.status_code == 200
    holdings_res = res.json()
    assert holdings_res["total_valuation_pence"] == 210000
    assert holdings_res["holdings_count"] == 1
    assert holdings_res["has_unvalued_holdings"] is False

    # 8. Checkpoint sync
    res = client.post(f"/api/investments/accounts/{acc_id}/checkpoints")
    assert res.status_code == 200
    assert res.json()["valuation_pence"] == 210000

    # 9. Delete valuation (revert)
    res = client.delete(f"/api/investments/valuations/{val_id}")
    assert res.status_code == 204

    # Verification: restored to initial valuation (£1,100.00)
    res = client.get(f"/api/investments/holdings/{holding_id}")
    assert res.status_code == 200
    assert res.json()["latest_valuation_pence"] == 110000


def test_alembic_migration_baseline_upgrade_and_downgrade(tmp_path):
    """
    Scenario 1: Tests clean upgrade and downgrade against the original baseline schema.
    """
    from alembic.config import Config
    from alembic import command
    from sqlalchemy import inspect

    test_db_file = tmp_path / "baseline_migration.db"
    test_db_url = f"sqlite:///{test_db_file}"

    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", test_db_url)

    # 1. Setup isolated database with original baseline schema (57ad957569a1)
    test_engine = create_engine(test_db_url)
    with test_engine.connect() as conn:
        conn.execute(sa.text("""
            CREATE TABLE accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name VARCHAR(100) NOT NULL UNIQUE,
                account_type VARCHAR(20) NOT NULL,
                starting_balance_pence INTEGER DEFAULT 0 NOT NULL,
                currency VARCHAR(3) DEFAULT 'GBP' NOT NULL,
                color VARCHAR(20) DEFAULT '#3B82F6',
                is_active BOOLEAN DEFAULT 1 NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """))
        conn.execute(sa.text("""
            INSERT INTO accounts (id, name, account_type, starting_balance_pence, currency, color, is_active)
            VALUES (1, 'Vanguard ISA', 'investment', 50000, 'GBP', '#3B82F6', 1)
        """))
        conn.commit()

    # 2. Upgrade to head
    command.stamp(alembic_cfg, "57ad957569a1")
    command.upgrade(alembic_cfg, "head")

    inspector = inspect(test_engine)
    table_names = inspector.get_table_names()
    assert "holdings" in table_names
    assert "holding_valuations" in table_names
    assert "valuation_mode" in [c["name"] for c in inspector.get_columns("accounts")]

    # 3. Downgrade back
    command.downgrade(alembic_cfg, "57ad957569a1")
    inspector_after = inspect(test_engine)
    assert "holdings" not in inspector_after.get_table_names()
    assert "holding_valuations" not in inspector_after.get_table_names()
    assert "valuation_mode" not in [c["name"] for c in inspector_after.get_columns("accounts")]
    test_engine.dispose()


def test_alembic_migration_partial_failure_recovery(tmp_path):
    """
    Scenario 2: Tests recovery against the exact partial state:
    accounts.valuation_mode already exists, holdings and holding_valuations already exist,
    while alembic_version still records 57ad957569a1.
    """
    from alembic.config import Config
    from alembic import command
    from sqlalchemy import inspect

    test_db_file = tmp_path / "partial_state_migration.db"
    test_db_url = f"sqlite:///{test_db_file}"

    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", test_db_url)

    # 1. Setup database representing the exact interrupted state
    test_engine = create_engine(test_db_url)
    with test_engine.connect() as conn:
        conn.execute(sa.text("""
            CREATE TABLE accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name VARCHAR(100) NOT NULL UNIQUE,
                account_type VARCHAR(20) NOT NULL,
                starting_balance_pence INTEGER DEFAULT 0 NOT NULL,
                currency VARCHAR(3) DEFAULT 'GBP' NOT NULL,
                color VARCHAR(20) DEFAULT '#3B82F6',
                is_active BOOLEAN DEFAULT 1 NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                valuation_mode VARCHAR(20) DEFAULT 'snapshot' NOT NULL
            )
        """))
        conn.execute(sa.text("""
            CREATE TABLE holdings (
                id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT, 
                account_id INTEGER NOT NULL, 
                name VARCHAR(150) NOT NULL, 
                ticker VARCHAR(30), 
                asset_class VARCHAR(50) DEFAULT 'equity' NOT NULL, 
                currency VARCHAR(3) DEFAULT 'GBP' NOT NULL, 
                is_active BOOLEAN DEFAULT '1' NOT NULL, 
                notes TEXT, 
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP, 
                FOREIGN KEY(account_id) REFERENCES accounts (id) ON DELETE CASCADE
            )
        """))
        conn.execute(sa.text("""
            CREATE TABLE holding_valuations (
                id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT, 
                holding_id INTEGER NOT NULL, 
                effective_date DATETIME NOT NULL, 
                quantity NUMERIC(18, 8) NOT NULL, 
                unit_price_pence NUMERIC(14, 4), 
                valuation_pence INTEGER NOT NULL, 
                notes VARCHAR(255), 
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP, 
                FOREIGN KEY(holding_id) REFERENCES holdings (id) ON DELETE CASCADE
            )
        """))
        conn.execute(sa.text("""
            INSERT INTO accounts (id, name, account_type, starting_balance_pence, currency, color, is_active, valuation_mode)
            VALUES (1, 'Existing Account', 'investment', 100000, 'GBP', '#3B82F6', 1, 'snapshot')
        """))
        conn.commit()

    # Stamp as 57ad957569a1 (the reported state where revision has not advanced)
    command.stamp(alembic_cfg, "57ad957569a1")

    # 2. Run upgrade to head: must NOT fail with 'table holdings already exists'
    command.upgrade(alembic_cfg, "head")

    # 3. Verify final state and version advanced to 8d1f2a3c4b5e
    inspector = inspect(test_engine)
    assert "holdings" in inspector.get_table_names()
    assert "holding_valuations" in inspector.get_table_names()
    assert "valuation_mode" in [c["name"] for c in inspector.get_columns("accounts")]

    with test_engine.connect() as conn:
        rev = conn.execute(sa.text("SELECT version_num FROM alembic_version")).scalar()
        assert rev in ("8d1f2a3c4b5e", "c3d4e5f6a7b8", "d4e5f6a7b8c9", "e5f6a7b8c9d0", "f6a7b8c9d0e1", "a1b2c3d4e5f6", "b2c3d4e5f6a7", "c3d4e5f6a7b9")
        acc_data = conn.execute(sa.text("SELECT id, name, valuation_mode FROM accounts WHERE id = 1")).fetchone()
        assert acc_data[1] == "Existing Account"
        assert acc_data[2] == "snapshot"

    test_engine.dispose()


def test_alembic_migration_completed_state_is_idempotent(tmp_path):
    """
    Scenario 3: Tests that running upgrade head when already on the completed state
    succeeds as a clean no-op.
    """
    from alembic.config import Config
    from alembic import command

    test_db_file = tmp_path / "completed_state_migration.db"
    test_db_url = f"sqlite:///{test_db_file}"

    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", test_db_url)

    # Setup database directly at completed schema
    test_engine = create_engine(test_db_url)
    with test_engine.connect() as conn:
        conn.execute(sa.text("CREATE TABLE accounts (id INTEGER PRIMARY KEY, name TEXT, valuation_mode TEXT)"))
        conn.execute(sa.text("CREATE TABLE holdings (id INTEGER PRIMARY KEY, account_id INTEGER, name TEXT, asset_class TEXT, currency TEXT, is_active BOOLEAN, notes TEXT, created_at DATETIME, ticker TEXT)"))
        conn.execute(sa.text("CREATE TABLE holding_valuations (id INTEGER PRIMARY KEY, holding_id INTEGER, effective_date DATETIME, quantity NUMERIC, unit_price_pence NUMERIC, valuation_pence INTEGER, notes TEXT, created_at DATETIME)"))
        conn.commit()

    command.stamp(alembic_cfg, "8d1f2a3c4b5e")
    # Upgrade head when already at head should be a clean no-op
    command.upgrade(alembic_cfg, "head")
    test_engine.dispose()


def test_alembic_migration_fails_on_corrupt_existing_table(tmp_path):
    """
    Scenario 4: Tests that if an existing table has an unexpected schema (missing columns),
    the migration halts with RuntimeError and does NOT advance the revision.
    """
    from alembic.config import Config
    from alembic import command
    import pytest

    test_db_file = tmp_path / "corrupt_schema_migration.db"
    test_db_url = f"sqlite:///{test_db_file}"

    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", test_db_url)

    # Setup database with malformed holdings table (missing account_id and asset_class)
    test_engine = create_engine(test_db_url)
    with test_engine.connect() as conn:
        conn.execute(sa.text("CREATE TABLE accounts (id INTEGER PRIMARY KEY, name TEXT)"))
        conn.execute(sa.text("CREATE TABLE holdings (id INTEGER PRIMARY KEY, bogus_col TEXT)"))
        conn.commit()

    command.stamp(alembic_cfg, "57ad957569a1")

    # Must raise RuntimeError and NOT advance revision
    with pytest.raises(RuntimeError, match="missing required columns"):
        command.upgrade(alembic_cfg, "head")

    with test_engine.connect() as conn:
        rev = conn.execute(sa.text("SELECT version_num FROM alembic_version")).scalar()
        assert rev == "57ad957569a1"

    test_engine.dispose()


def test_alembic_migration_e5f6a7b8c9d0_snapshot_conversion(tmp_path):
    """
    Scenario 5: Tests that migration e5f6a7b8c9d0 safely converts snapshot-only accounts
    to synthetic holdings and is completely idempotent on temporary database.
    """
    from alembic.config import Config
    from alembic import command
    from sqlalchemy import inspect

    test_db_file = tmp_path / "e5f6_migration.db"
    test_db_url = f"sqlite:///{test_db_file}"

    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", test_db_url)

    # 1. Setup isolated database with d4e5f6a7b8c9 schema
    test_engine = create_engine(test_db_url)
    with test_engine.connect() as conn:
        conn.execute(sa.text("""
            CREATE TABLE accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name VARCHAR(100) NOT NULL UNIQUE,
                account_type VARCHAR(20) NOT NULL,
                starting_balance_pence INTEGER DEFAULT 0 NOT NULL,
                currency VARCHAR(3) DEFAULT 'GBP' NOT NULL,
                color VARCHAR(20) DEFAULT '#3B82F6',
                is_active BOOLEAN DEFAULT 1 NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                valuation_mode VARCHAR(20) DEFAULT 'snapshot' NOT NULL
            );
        """))
        conn.execute(sa.text("""
            CREATE TABLE holdings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id INTEGER NOT NULL,
                name VARCHAR(150) NOT NULL,
                ticker VARCHAR(30),
                asset_class VARCHAR(50) DEFAULT 'equity' NOT NULL,
                currency VARCHAR(3) DEFAULT 'GBP' NOT NULL,
                is_active BOOLEAN DEFAULT 1 NOT NULL,
                notes TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
        """))
        conn.execute(sa.text("""
            CREATE TABLE holding_valuations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                holding_id INTEGER NOT NULL,
                effective_date DATETIME NOT NULL,
                quantity NUMERIC(18, 8) NOT NULL,
                unit_price_pence NUMERIC(14, 4),
                valuation_pence INTEGER NOT NULL,
                notes VARCHAR(255),
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
        """))
        conn.execute(sa.text("""
            CREATE TABLE asset_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id INTEGER NOT NULL,
                valuation_pence INTEGER NOT NULL,
                effective_date DATETIME NOT NULL,
                notes VARCHAR(255),
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
        """))
        conn.commit()

    command.stamp(alembic_cfg, "d4e5f6a7b8c9")

    # 2. Insert test data: Account 1 (snapshot only) and Account 2 (with holding)
    with test_engine.connect() as conn:
        conn.execute(sa.text("""
            INSERT INTO accounts (id, name, account_type, starting_balance_pence, currency, color, is_active, valuation_mode)
            VALUES (1, 'Snapshot Account', 'investment', 0, 'GBP', '#3B82F6', 1, 'snapshot'),
                   (2, 'Detailed Account', 'investment', 0, 'GBP', '#10B981', 1, 'snapshot')
        """))
        conn.execute(sa.text("""
            INSERT INTO asset_snapshots (account_id, effective_date, valuation_pence, notes)
            VALUES (1, '2026-09-01 00:00:00', 750000, 'Sept snapshot'),
                   (1, '2026-10-01 00:00:00', 800000, 'Oct snapshot'),
                   (2, '2026-10-01 00:00:00', 500000, 'Detailed snap')
        """))
        conn.execute(sa.text("""
            INSERT INTO holdings (id, account_id, name, asset_class, currency, is_active)
            VALUES (1, 2, 'Existing Fund', 'fund', 'GBP', 1)
        """))
        conn.execute(sa.text("""
            INSERT INTO holding_valuations (holding_id, effective_date, quantity, unit_price_pence, valuation_pence)
            VALUES (1, '2026-10-01 00:00:00', 10.0, 50000, 500000)
        """))
        conn.commit()

    # 3. Upgrade to head (e5f6a7b8c9d0)
    command.upgrade(alembic_cfg, "head")

    with test_engine.connect() as conn:
        rev = conn.execute(sa.text("SELECT version_num FROM alembic_version")).scalar()
        assert rev in ("e5f6a7b8c9d0", "f6a7b8c9d0e1", "a1b2c3d4e5f6", "b2c3d4e5f6a7", "c3d4e5f6a7b9")

        # Account 1 should have received a synthetic holding 'Portfolio Valuation'
        synth = conn.execute(sa.text("SELECT id, name, asset_class FROM holdings WHERE account_id = 1")).fetchone()
        assert synth is not None
        assert synth[1] == "Portfolio Valuation"
        assert synth[2] == "portfolio"

        # Account 1 should have 2 valuations matching the snapshots
        vals = conn.execute(sa.text("SELECT valuation_pence FROM holding_valuations WHERE holding_id = :h_id ORDER BY effective_date ASC"), {"h_id": synth[0]}).fetchall()
        assert len(vals) == 2
        assert vals[0][0] == 750000
        assert vals[1][0] == 800000

        # Account 2 must have NO synthetic holdings created
        h2 = conn.execute(sa.text("SELECT count(*) FROM holdings WHERE account_id = 2")).scalar()
        assert h2 == 1

        # Valuation mode on both accounts should now be 'holdings'
        modes = conn.execute(sa.text("SELECT valuation_mode FROM accounts WHERE account_type = 'investment'")).fetchall()
        for m in modes:
            assert m[0] == "holdings"

    # 4. Idempotent upgrade head re-run
    command.upgrade(alembic_cfg, "head")

    test_engine.dispose()



# ---------------------------------------------------------------------------
# Holdings-Only Investment Model & Lump-Sum Usability Tests
# ---------------------------------------------------------------------------

def test_new_investment_account_defaults_to_holdings_mode_and_zero_balance(client, db_session):
    """
    Verifies that:
    1. Creating a new investment account does not require an opening balance.
    2. The new account automatically defaults to valuation_mode='holdings'.
    3. If there are no holdings, it shows a clear zero balance and unvalued/no-holdings state.
    """
    res = client.post("/api/accounts", json={
        "name": "Trading 212 ISA",
        "account_type": "investment",
        "currency": "GBP"
    })
    assert res.status_code == 201
    acc_data = res.json()
    assert acc_data["valuation_mode"] == "holdings"
    assert acc_data["current_balance_pence"] == 0
    assert acc_data["formatted_balance"] == "£0.00"
    assert acc_data["holdings_count"] == 0
    assert acc_data["has_unvalued_holdings"] is False
    assert "No holdings" in acc_data["anchor_label"]


def test_four_decimal_unit_price_precision_and_valuation(client, db_session):
    """
    Verifies that:
    1. Unit prices with four decimal places (e.g. £12.3456) are preserved without rounding off to pence.
    2. Total holding value is calculated using decimal arithmetic, rounding quantity * unit_price once (ROUND_HALF_UP).
    3. The API response returns exact 4-decimal unit_price_pounds, unit_price_pence, and formatted_unit_price.
    4. Two-decimal unit prices (e.g. £85.12) format without trailing zeros.
    """
    res_acc = client.post("/api/accounts", json={
        "name": "AJ Bell SIPP",
        "account_type": "investment",
        "currency": "GBP"
    })
    acc_id = res_acc.json()["id"]

    # Add holding with 4-decimal unit price: 10 units @ £12.3456 -> 12346 pence (£123.46)
    res_hold = client.post(f"/api/investments/accounts/{acc_id}/holdings", json={
        "name": "Global Equity Fund Class A",
        "ticker": "GEFA",
        "asset_class": "fund",
        "initial_quantity": 10.0,
        "initial_unit_price": 12.3456
    })
    assert res_hold.status_code == 201
    h_data = res_hold.json()
    holding_id = h_data["id"]

    assert h_data["latest_unit_price_pounds"] == 12.3456
    assert h_data["formatted_unit_price"] == "£12.3456"
    assert h_data["latest_valuation_pence"] == 12346
    assert h_data["formatted_valuation"] == "£123.46"

    # Fractional position with 4-decimal unit price:
    # 15.4820 units @ £12.3456 = 19113.45792 pence -> 19113 pence (£191.13)
    res_val = client.post(f"/api/investments/holdings/{holding_id}/valuations", json={
        "quantity": 15.4820,
        "unit_price": 12.3456,
        "notes": "Monthly regular investment"
    })
    assert res_val.status_code == 201
    v_data = res_val.json()
    assert v_data["unit_price_pounds"] == 12.3456
    assert v_data["formatted_unit_price"] == "£12.3456"
    assert v_data["valuation_pence"] == 19113
    assert v_data["formatted_valuation"] == "£191.13"


def test_full_holding_detail_editing_and_account_reassignment(client, db_session):
    """
    Verifies that:
    1. A holding's name, ticker, asset class, notes, and target investment account can be edited.
    2. Editing details does not alter or delete historical valuations.
    3. Reassigning a holding to another investment account preserves valuation history
       and immediately updates the calculated balance of both accounts.
    """
    res_a = client.post("/api/accounts", json={"name": "Vanguard ISA", "account_type": "investment", "currency": "GBP"})
    acc_a_id = res_a.json()["id"]

    res_b = client.post("/api/accounts", json={"name": "Interactive Investor SIPP", "account_type": "investment", "currency": "GBP"})
    acc_b_id = res_b.json()["id"]

    res_hold = client.post(f"/api/investments/accounts/{acc_a_id}/holdings", json={
        "name": "Vanguard Emerging Markets",
        "ticker": "VEM",
        "asset_class": "fund",
        "initial_quantity": 25.0,
        "initial_valuation": 500.00
    })
    holding_id = res_hold.json()["id"]

    client.post(f"/api/investments/holdings/{holding_id}/valuations", json={
        "quantity": 30.0,
        "valuation": 750.00,
        "notes": "Dividend reinvestment"
    })

    assert client.get(f"/api/accounts/{acc_a_id}").json()["current_balance_pence"] == 75000
    assert client.get(f"/api/accounts/{acc_b_id}").json()["current_balance_pence"] == 0

    res_edit = client.put(f"/api/investments/holdings/{holding_id}", json={
        "name": "Vanguard FTSE Emerging Markets UCITS ETF",
        "ticker": "VFEM",
        "asset_class": "etf",
        "account_id": acc_b_id,
        "notes": "Transferred holding from ISA to SIPP"
    })
    assert res_edit.status_code == 200

    # Both account balances immediately update
    assert client.get(f"/api/accounts/{acc_a_id}").json()["current_balance_pence"] == 0
    assert client.get(f"/api/accounts/{acc_b_id}").json()["current_balance_pence"] == 75000


def test_account_total_updates_automatically_on_holding_lifecycle(client, db_session):
    """
    Verifies that the investment account total updates automatically when holdings or valuations
    are added, edited, or deleted.
    """
    res_acc = client.post("/api/accounts", json={"name": "Freetrade ISA", "account_type": "investment", "currency": "GBP"})
    acc_id = res_acc.json()["id"]

    assert client.get(f"/api/accounts/{acc_id}").json()["current_balance_pence"] == 0

    # Add unvalued holding
    res_h1 = client.post(f"/api/investments/accounts/{acc_id}/holdings", json={
        "name": "Apple Inc",
        "ticker": "AAPL",
        "asset_class": "equity"
    })
    h1_id = res_h1.json()["id"]

    acc_info = client.get(f"/api/accounts/{acc_id}").json()
    assert acc_info["current_balance_pence"] == 0
    assert acc_info["has_unvalued_holdings"] is True
    assert "Unvalued" in acc_info["anchor_label"]

    # Record valuation for Apple (£300.00)
    res_val1 = client.post(f"/api/investments/holdings/{h1_id}/valuations", json={
        "quantity": 2.0,
        "valuation": 300.00
    })
    val1_id = res_val1.json()["id"]
    assert client.get(f"/api/accounts/{acc_id}").json()["current_balance_pence"] == 30000

    # Add second holding with initial valuation £200.00
    res_h2 = client.post(f"/api/investments/accounts/{acc_id}/holdings", json={
        "name": "Microsoft Corp",
        "ticker": "MSFT",
        "asset_class": "equity",
        "initial_quantity": 1.0,
        "initial_valuation": 200.00
    })
    h2_id = res_h2.json()["id"]
    assert client.get(f"/api/accounts/{acc_id}").json()["current_balance_pence"] == 50000

    # Update valuation of Apple from £300 to £350
    client.put(f"/api/investments/valuations/{val1_id}", json={
        "valuation": 350.00
    })
    assert client.get(f"/api/accounts/{acc_id}").json()["current_balance_pence"] == 55000

    # Delete holding 2 (Microsoft)
    client.delete(f"/api/investments/holdings/{h2_id}")
    assert client.get(f"/api/accounts/{acc_id}").json()["current_balance_pence"] == 35000


def test_holdings_only_investment_account_balance(client, db_session):
    """
    Verifies that all investment accounts derive their balance solely from active holdings,
    regardless of whether valuation_mode was legacy snapshot.
    """
    res = client.post("/api/accounts", json={
        "name": "Legacy Snapshot Account",
        "account_type": "investment",
        "currency": "GBP"
    })
    acc_id = res.json()["id"]
    acc_data = res.json()
    assert acc_data["current_balance_pence"] == 0
    assert acc_data["formatted_balance"] == "£0.00"
    assert "No holdings" in acc_data["anchor_label"]

    # Adding a holding immediately determines the account balance
    res_h = client.post(f"/api/investments/accounts/{acc_id}/holdings", json={
        "name": "Global Equity Index",
        "asset_class": "fund",
        "initial_quantity": 100.0,
        "initial_unit_price": 25.50
    })
    assert res_h.status_code == 201

    acc_after = client.get(f"/api/accounts/{acc_id}").json()
    assert acc_after["current_balance_pence"] == 255000
    assert acc_after["formatted_balance"] == "£2,550.00"
    assert "1 active holdings" in acc_after["anchor_label"]


def test_lump_sum_holding_quantity_one_and_valuation(client, db_session):
    """
    Verifies that an asset without natural sub-holdings can be represented as one holding
    with quantity 1.0, where unit price and total valuation are equivalent, and
    its value appears cleanly in portfolio summary with asset_class='portfolio'.
    """
    res_acc = client.post("/api/accounts", json={
        "name": "Personal Pension Plan",
        "account_type": "investment",
        "currency": "GBP"
    })
    acc_id = res_acc.json()["id"]

    # 1. Create lump-sum holding with quantity = 1.0 and total valuation = £50,000.00
    res_h = client.post(f"/api/investments/accounts/{acc_id}/holdings", json={
        "name": "Pension Value",
        "ticker": None,
        "asset_class": "portfolio",
        "initial_quantity": 1.0,
        "initial_valuation": 50000.00
    })
    assert res_h.status_code == 201
    h_data = res_h.json()
    h_id = h_data["id"]
    assert h_data["latest_quantity"] == 1.0
    assert h_data["latest_unit_price_pounds"] == 50000.0
    assert h_data["latest_valuation_pence"] == 5000000
    assert h_data["formatted_valuation"] == "£50,000.00"

    # Account balance immediately becomes £50,000.00
    acc_data = client.get(f"/api/accounts/{acc_id}").json()
    assert acc_data["current_balance_pence"] == 5000000
    assert acc_data["formatted_balance"] == "£50,000.00"

    # 2. Update valuation via + Value with quantity = 1.0 to £52,500.00
    res_val = client.post(f"/api/investments/holdings/{h_id}/valuations", json={
        "quantity": 1.0,
        "valuation": 52500.00,
        "notes": "Annual pension statement check"
    })
    assert res_val.status_code == 201
    assert res_val.json()["valuation_pence"] == 5250000

    # Account balance immediately updates to £52,500.00
    acc_data2 = client.get(f"/api/accounts/{acc_id}").json()
    assert acc_data2["current_balance_pence"] == 5250000

    # 3. Check /api/investments/summary portfolio allocation
    summary = client.get("/api/investments/summary").json()
    alloc = summary["asset_allocation"]
    portfolio_alloc = next((a for a in alloc if a["asset_class"] == "portfolio"), None)
    assert portfolio_alloc is not None
    assert portfolio_alloc["total_pence"] == 5250000
    assert portfolio_alloc["total_pounds"] == 52500.0


def test_snapshot_history_conversion_to_synthetic_holding(db_session):
    """
    Verifies that:
    1. An account with historical AssetSnapshot records and NO holdings is converted into
       one synthetic holding ('Portfolio Valuation') with quantity 1.0 and matching dated valuations.
    2. An account that already has detailed holdings is left untouched (zero double counting).
    3. The conversion step is idempotent when executed multiple times.
    """
    from app.core.investments import convert_snapshot_histories_to_holdings

    # Account A: Snapshot history only (no holdings)
    acc_a = Account(name="Old Snapshot Account", account_type=AccountType.INVESTMENT, currency="GBP")
    db_session.add(acc_a)
    db_session.commit()

    t1 = datetime(2026, 9, 1, tzinfo=timezone.utc)
    t2 = datetime(2026, 10, 1, tzinfo=timezone.utc)
    db_session.add(AssetSnapshot(account_id=acc_a.id, effective_date=t1, valuation_pence=1000000, notes="Sept valuation"))
    db_session.add(AssetSnapshot(account_id=acc_a.id, effective_date=t2, valuation_pence=1200000, notes="Oct valuation"))

    # Account B: Already has holdings (like AJ Bell LISA)
    acc_b = Account(name="Account With Holdings", account_type=AccountType.INVESTMENT, currency="GBP")
    db_session.add(acc_b)
    db_session.commit()
    h_b = Holding(account_id=acc_b.id, name="Vanguard Fund", asset_class="fund")
    db_session.add(h_b)
    db_session.commit()
    db_session.add(HoldingValuation(holding_id=h_b.id, effective_date=t1, quantity=Decimal("50"), valuation_pence=500000))
    # Account B also has a legacy asset snapshot
    db_session.add(AssetSnapshot(account_id=acc_b.id, effective_date=t1, valuation_pence=500000))
    db_session.commit()

    # Run conversion
    res = convert_snapshot_histories_to_holdings(db_session)
    assert res["converted_accounts"] == 1
    assert res["created_holdings"] == 1
    assert res["created_valuations"] == 2

    # Account A now has a synthetic holding with 2 valuations
    holdings_a = db_session.query(Holding).filter(Holding.account_id == acc_a.id).all()
    assert len(holdings_a) == 1
    synth = holdings_a[0]
    assert synth.name == "Portfolio Valuation"
    assert synth.asset_class == "portfolio"
    vals_a = db_session.query(HoldingValuation).filter(HoldingValuation.holding_id == synth.id).order_by(HoldingValuation.effective_date.asc()).all()
    assert len(vals_a) == 2
    assert vals_a[0].valuation_pence == 1000000
    assert vals_a[0].quantity == Decimal("1.0")
    assert vals_a[1].valuation_pence == 1200000
    assert vals_a[1].quantity == Decimal("1.0")
    # Account A's ledger balance now matches the latest snapshot
    assert LedgerEngine.get_account_balance(db_session, acc_a.id) == 1200000

    # Account B was untouched: only 1 holding exists (Vanguard Fund)
    holdings_b = db_session.query(Holding).filter(Holding.account_id == acc_b.id).all()
    assert len(holdings_b) == 1
    assert holdings_b[0].name == "Vanguard Fund"

    # Idempotent re-run
    res2 = convert_snapshot_histories_to_holdings(db_session)
    assert res2["converted_accounts"] == 0
    assert res2["created_holdings"] == 0
    assert res2["created_valuations"] == 0

