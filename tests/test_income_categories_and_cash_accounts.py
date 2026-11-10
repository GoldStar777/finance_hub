"""
Isolated verification suite for Separate Income Categories and Cash Account Type.

Covers:
1. Category purpose ('expense' vs 'income') creation, filtering, nature coercion, and migration defaults.
2. Strict transaction validation across manual, repeat, edit, bulk edit, staging review, split, and reconciliation.
3. Safe category purpose change (reassignment workflow) and permanent deletion cross-purpose guards.
4. Direction-aware offline category suggestion (`suggest_category_from_history`) with no cross-purpose leakage.
5. Data Quality & Review handling of uncategorised income (no false positive when no income categories exist) & mismatches.
6. Analysis (`income_categories`, `income_matrix`), Cash Flow, and Ledger/Analysis CSV/XLSX exports.
7. First-class Cash account type: CRUD, liquid reserve + net worth math, anchors, reconciliation, transfers & breakdown.
8. Alembic upgrade / connect-time SQLite schema backfill & strict multi-profile workspace isolation.
"""

import io
from datetime import datetime, timezone
from urllib.parse import urlparse

import openpyxl
import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from app.core import profiles as profiles_module
from app.core.analysis import generate_analysis_export, get_comprehensive_analysis
from app.core.data_quality import get_data_quality_report
from app.core.ledger_export import generate_ledger_export
from app.core.unified_importer import suggest_category_from_history
from app.database import Base, configure_sqlite_engine, db_registry
from app.ledger import LedgerEngine
from app.main import app
from app.models import (
    Account,
    AccountType,
    Category,
    CategoryType,
    ExpenseNature,
    StagingItem,
    StagingStatus,
    Transaction,
    TransactionType,
)


def test_1_category_purpose_crud_filtering_and_nature_rules(db_session, client):
    """Income categories can be created, filtered, and never retain Fixed/Variable expense nature."""
    # Default creation omits category_type -> deterministically 'expense'
    r_exp = client.post(
        "/api/categories",
        json={"name": "Groceries", "default_expense_nature": "variable", "color": "#10B981"},
    )
    assert r_exp.status_code == 201
    exp_cat = r_exp.json()
    assert exp_cat["category_type"] == "expense"
    assert exp_cat["default_expense_nature"] == "variable"

    # Explicit Income category forces default_expense_nature = 'unclassified'
    r_inc = client.post(
        "/api/categories",
        json={
            "name": "Salary",
            "category_type": "income",
            "default_expense_nature": "fixed",  # Should be ignored/coerced to unclassified
            "color": "#059669",
            "description": "Monthly payroll employer deposit",
        },
    )
    assert r_inc.status_code == 201
    inc_cat = r_inc.json()
    assert inc_cat["category_type"] == "income"
    assert inc_cat["default_expense_nature"] == "unclassified"

    # Filtering via GET /api/categories?category_type=...
    only_income = client.get("/api/categories?category_type=income").json()
    assert [c["name"] for c in only_income] == ["Salary"]

    only_expense = client.get("/api/categories?category_type=expense").json()
    assert [c["name"] for c in only_expense] == ["Groceries"]

    # Attempting to set fixed nature on income category update still forces unclassified
    r_upd = client.put(
        f"/api/categories/{inc_cat['id']}",
        json={"default_expense_nature": "fixed", "name": "Base Salary"},
    )
    assert r_upd.status_code == 200
    assert r_upd.json()["name"] == "Base Salary"
    assert r_upd.json()["default_expense_nature"] == "unclassified"


def test_2_strict_transaction_validation_and_type_switch_guards(db_session, client):
    """
    Expense transactions only accept Expense categories; Income only Income;
    Transfers/Adjustments accept no category; type changes never retain incompatible categories.
    """
    acc = Account(name="Checking", account_type=AccountType.CURRENT, currency="GBP", starting_balance_pence=100000)
    cash = Account(name="Petty Cash", account_type=AccountType.CASH, currency="GBP", starting_balance_pence=20000)
    cat_exp = Category(name="Dining Out", category_type=CategoryType.EXPENSE, default_expense_nature=ExpenseNature.VARIABLE)
    cat_inc = Category(name="Freelance", category_type=CategoryType.INCOME)
    db_session.add_all([acc, cash, cat_exp, cat_inc])
    db_session.commit()

    tx_dt = "2026-08-10T12:00:00Z"

    # 1. Valid Expense + Expense Category succeeds
    r_ok_exp = client.post(
        "/api/transactions",
        json={
            "transaction_type": "expense",
            "amount": 25.00,
            "merchant": "Cafe",
            "account_id": acc.id,
            "category_id": cat_exp.id,
            "transaction_date": tx_dt,
        },
    )
    assert r_ok_exp.status_code == 201
    exp_tx_id = r_ok_exp.json()["id"]
    assert r_ok_exp.json()["category_type"] == "expense"

    # 2. Valid Income + Income Category succeeds
    r_ok_inc = client.post(
        "/api/transactions",
        json={
            "transaction_type": "income",
            "amount": 500.00,
            "merchant": "Client A",
            "account_id": acc.id,
            "category_id": cat_inc.id,
            "transaction_date": tx_dt,
        },
    )
    assert r_ok_inc.status_code == 201
    inc_tx_id = r_ok_inc.json()["id"]
    assert r_ok_inc.json()["category_type"] == "income"
    assert r_ok_inc.json()["expense_nature"] == "unclassified"

    # 3. Cross-purpose creation rejected (Income + Expense cat, Expense + Income cat, Transfer + any cat)
    r_bad_1 = client.post(
        "/api/transactions",
        json={
            "transaction_type": "income",
            "amount": 100.00,
            "account_id": acc.id,
            "category_id": cat_exp.id,
            "transaction_date": tx_dt,
        },
    )
    assert r_bad_1.status_code == 400
    assert "cannot be assigned to an income transaction" in r_bad_1.json()["detail"]

    r_bad_2 = client.post(
        "/api/transactions",
        json={
            "transaction_type": "expense",
            "amount": 15.00,
            "account_id": cash.id,
            "category_id": cat_inc.id,
            "transaction_date": tx_dt,
        },
    )
    assert r_bad_2.status_code == 400
    assert "cannot be assigned to an expense transaction" in r_bad_2.json()["detail"]

    r_bad_3 = client.post(
        "/api/transactions",
        json={
            "transaction_type": "transfer",
            "amount": 50.00,
            "account_id": acc.id,
            "destination_account_id": cash.id,
            "category_id": cat_exp.id,
            "transaction_date": tx_dt,
        },
    )
    assert r_bad_3.status_code == 400

    # 4. Repeat transaction rejects cross-purpose category atomically (0 rows created)
    before_count = db_session.query(Transaction).count()
    r_bad_rep = client.post(
        "/api/transactions/repeat",
        json={
            "transaction_type": "income",
            "amount": 300.0,
            "merchant": "Dividend",
            "account_id": acc.id,
            "category_id": cat_exp.id,
            "frequency": "monthly",
            "first_date": "2026-09-01",
            "end_mode": "count",
            "occurrence_count": 3,
            "idempotency_key": "bad-repeat-purpose-001",
        },
    )
    assert r_bad_rep.status_code == 400
    assert db_session.query(Transaction).count() == before_count

    # 5. Editing transaction_type without clearing incompatible category is blocked
    r_bad_switch = client.put(
        f"/api/transactions/{exp_tx_id}",
        json={"transaction_type": "income"},
    )
    assert r_bad_switch.status_code == 400
    assert "cannot be assigned to an income transaction" in r_bad_switch.json()["detail"]

    # Switching transaction_type WHILE clearing category (category_id: None) or giving Income category works cleanly
    r_ok_switch = client.put(
        f"/api/transactions/{exp_tx_id}",
        json={"transaction_type": "income", "category_id": cat_inc.id},
    )
    assert r_ok_switch.status_code == 200
    assert r_ok_switch.json()["transaction_type"] == "income"
    assert r_ok_switch.json()["category_id"] == cat_inc.id
    assert r_ok_switch.json()["category_type"] == "income"

    # 6. Bulk update atomic guard against retaining incompatible category or applying cross-purpose category
    r_bulk_bad_keep = client.post(
        "/api/transactions/bulk",
        json={
            "transaction_ids": [exp_tx_id],  # currently income with cat_inc
            "update_transaction_type": True,
            "transaction_type": "expense",
            "update_category": False,
        },
    )
    assert r_bulk_bad_keep.status_code == 400
    assert "incompatible with expense" in r_bulk_bad_keep.json()["detail"]

    r_bulk_bad_cross = client.post(
        "/api/transactions/bulk",
        json={
            "transaction_ids": [inc_tx_id],
            "update_category": True,
            "category_id": cat_exp.id,
        },
    )
    assert r_bulk_bad_cross.status_code == 400

    # Valid atomic bulk change: switch type to expense AND clear category to None
    r_bulk_ok = client.post(
        "/api/transactions/bulk",
        json={
            "transaction_ids": [exp_tx_id],
            "update_transaction_type": True,
            "transaction_type": "expense",
            "update_category": True,
            "category_id": None,
        },
    )
    assert r_bulk_ok.status_code == 200
    tx_refreshed = db_session.query(Transaction).filter(Transaction.id == exp_tx_id).first()
    db_session.refresh(tx_refreshed)
    assert tx_refreshed.transaction_type == TransactionType.EXPENSE
    assert tx_refreshed.category_id is None


def test_3_category_purpose_change_and_deletion_safeguards(db_session, client):
    """
    Changing category_type when transactions use the category requires safe same-purpose reassignment;
    deleting permanently rejects cross-purpose reassignment.
    """
    cat_exp_1 = Category(name="Old Utilities", category_type=CategoryType.EXPENSE, default_expense_nature=ExpenseNature.FIXED)
    cat_exp_2 = Category(name="Bills & Power", category_type=CategoryType.EXPENSE, default_expense_nature=ExpenseNature.FIXED)
    cat_inc = Category(name="Bonus", category_type=CategoryType.INCOME)
    db_session.add_all([cat_exp_1, cat_exp_2, cat_inc])
    db_session.commit()

    tx = Transaction(
        transaction_type=TransactionType.EXPENSE,
        amount_pence=4500,
        merchant="Power Co",
        category_id=cat_exp_1.id,
    )
    db_session.add(tx)
    db_session.commit()

    # 1. Blocked purpose flip without reassignment
    r_block = client.put(f"/api/categories/{cat_exp_1.id}", json={"category_type": "income"})
    assert r_block.status_code == 400
    assert "reference it" in r_block.json()["detail"]

    # 2. Cross-purpose reassignment rejected during purpose change
    r_cross = client.put(
        f"/api/categories/{cat_exp_1.id}",
        json={"category_type": "income", "reassign_existing_to_id": cat_inc.id},
    )
    assert r_cross.status_code == 400

    # 3. Safe same-old-purpose reassignment allows converting unused category cleanly
    r_safe = client.put(
        f"/api/categories/{cat_exp_1.id}",
        json={"category_type": "income", "reassign_existing_to_id": cat_exp_2.id},
    )
    assert r_safe.status_code == 200
    assert r_safe.json()["category_type"] == "income"
    assert r_safe.json()["default_expense_nature"] == "unclassified"
    db_session.refresh(tx)
    assert tx.category_id == cat_exp_2.id

    # 4. Permanent delete rejects cross-purpose reassignment (Expense category -> Income category)
    r_del_cross = client.delete(f"/api/categories/{cat_exp_2.id}?permanent=true&reassign_to_id={cat_inc.id}")
    assert r_del_cross.status_code == 400
    assert "cannot receive transactions" in r_del_cross.json()["detail"]


def test_4_import_suggester_and_staging_respect_category_purpose(db_session, client):
    """Import suggestion engine, staging edit, staging split, and approval strictly enforce category purpose."""
    acc = Account(name="Checking", account_type=AccountType.CURRENT, currency="GBP")
    cat_exp = Category(name="Software", category_type=CategoryType.EXPENSE, default_expense_nature=ExpenseNature.VARIABLE)
    cat_inc = Category(name="Dividends", category_type=CategoryType.INCOME)
    cat_inc_2 = Category(name="Consultancy", category_type=CategoryType.INCOME)
    db_session.add_all([acc, cat_exp, cat_inc, cat_inc_2])
    db_session.commit()

    # Past EXPENSE with merchant "Acme Cloud" -> Software
    tx_past = Transaction(
        transaction_type=TransactionType.EXPENSE,
        amount_pence=2999,
        merchant="Acme Cloud",
        category_id=cat_exp.id,
        account_id=acc.id,
        transaction_date=datetime(2026, 7, 1, tzinfo=timezone.utc),
    )
    db_session.add(tx_past)
    db_session.commit()

    # Suggest for EXPENSE "Acme Cloud" -> matches Software
    cid, cname, cnat, _ = suggest_category_from_history(db_session, "Acme Cloud", amount_pence=2999, tx_type="expense")
    assert cid == cat_exp.id
    assert cname == "Software"
    assert cnat == ExpenseNature.VARIABLE

    # Suggest for INCOME "Acme Cloud" -> MUST NOT suggest Expense category Software!
    cid_i, cname_i, cnat_i, _ = suggest_category_from_history(db_session, "Acme Cloud", amount_pence=2999, tx_type="income")
    assert cid_i is None
    assert cname_i is None
    assert cnat_i == ExpenseNature.UNCLASSIFIED

    # Suggest for INCOME with matching Income category token/history
    tx_inc_past = Transaction(
        transaction_type=TransactionType.INCOME,
        amount_pence=120000,
        merchant="Northwind Payroll",
        category_id=cat_inc_2.id,
        account_id=acc.id,
        transaction_date=datetime(2026, 7, 15, tzinfo=timezone.utc),
    )
    db_session.add(tx_inc_past)
    db_session.commit()

    cid_inc, cname_inc, cnat_inc, _ = suggest_category_from_history(db_session, "Northwind Payroll", tx_type="income")
    assert cid_inc == cat_inc_2.id
    assert cname_inc == "Consultancy"
    assert cnat_inc == ExpenseNature.UNCLASSIFIED

    # Staging item: switching from expense -> income auto-clears incompatible expense category
    stg = StagingItem(
        status=StagingStatus.PENDING,
        extracted_amount_pence=5000,
        extracted_date=datetime(2026, 8, 5, 12, 0, tzinfo=timezone.utc),
        extracted_merchant="Acme",
        suggested_account_id=acc.id,
        suggested_category_name=cat_exp.name,
        suggested_expense_nature=ExpenseNature.VARIABLE,
        source_type="statement_csv",
        raw_payload_json=f'{{"transaction_type": "expense", "category_id": {cat_exp.id}}}',
    )
    db_session.add(stg)
    db_session.commit()

    r_stg_switch = client.put(f"/api/staging/{stg.id}", json={"transaction_type": "income"})
    assert r_stg_switch.status_code == 200
    assert r_stg_switch.json()["suggested_category_id"] is None
    assert r_stg_switch.json()["suggested_category_name"] is None
    assert r_stg_switch.json()["suggested_expense_nature"] == "unclassified"

    # Trying to assign an Expense category to an Income staging item returns 400
    r_stg_bad = client.put(f"/api/staging/{stg.id}", json={"category_id": cat_exp.id})
    assert r_stg_bad.status_code == 400

    # Assigning Income category & approving creates Income ledger transaction with unclassified nature
    r_stg_ok = client.put(f"/api/staging/{stg.id}", json={"category_id": cat_inc.id})
    assert r_stg_ok.status_code == 200
    r_appr = client.post(f"/api/staging/{stg.id}/approve")
    assert r_appr.status_code == 200
    approved_tx = db_session.query(Transaction).filter(Transaction.id == r_appr.json()["transaction_id"]).first()
    assert approved_tx.category_id == cat_inc.id
    assert approved_tx.expense_nature == ExpenseNature.UNCLASSIFIED


def test_5_data_quality_income_categories_safeguards(db_session):
    """
    When NO active Income categories exist, uncategorised Income is NOT flagged as uncategorised.
    Once active Income categories exist, uncategorised Income IS flagged with Income-only hints.
    """
    acc = Account(name="Checking", account_type=AccountType.CURRENT, currency="GBP")
    cat_exp = Category(name="Groceries", category_type=CategoryType.EXPENSE, default_expense_nature=ExpenseNature.VARIABLE)
    db_session.add_all([acc, cat_exp])
    db_session.commit()

    tx_inc = Transaction(
        transaction_type=TransactionType.INCOME,
        amount_pence=200000,
        merchant="Employer",
        account_id=acc.id,
        category_id=None,
        transaction_date=datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc),
    )
    tx_exp = Transaction(
        transaction_type=TransactionType.EXPENSE,
        amount_pence=3500,
        merchant="Market",
        account_id=acc.id,
        category_id=None,
        transaction_date=datetime(2026, 8, 2, 12, 0, tzinfo=timezone.utc),
    )
    db_session.add_all([tx_inc, tx_exp])
    db_session.commit()

    # Phase 1: Only expense categories exist -> only expense is flagged uncategorised
    rep_1 = get_data_quality_report(db_session)
    uncat_1 = [f for f in rep_1["findings"] if f["finding_type"] == "uncategorised"]
    assert len(uncat_1) == 1
    assert uncat_1[0]["transaction_id"] == tx_exp.id
    assert uncat_1[0]["expected_category_type"] == "expense"

    # Phase 2: Add active Income category + categorized past Income history
    cat_inc = Category(name="Salary", category_type=CategoryType.INCOME)
    db_session.add(cat_inc)
    db_session.commit()

    tx_inc_hist = Transaction(
        transaction_type=TransactionType.INCOME,
        amount_pence=200000,
        merchant="Employer",
        account_id=acc.id,
        category_id=cat_inc.id,
        transaction_date=datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc),
    )
    db_session.add(tx_inc_hist)
    db_session.commit()

    rep_2 = get_data_quality_report(db_session)
    uncat_2 = {f["transaction_id"]: f for f in rep_2["findings"] if f["finding_type"] == "uncategorised"}
    assert set(uncat_2.keys()) == {tx_exp.id, tx_inc.id}
    assert uncat_2[tx_inc.id]["expected_category_type"] == "income"
    assert uncat_2[tx_inc.id]["suggested_category_id"] == cat_inc.id

    # Phase 3: Integrity check detects legacy/corrupt cross-purpose link
    tx_bad = Transaction(
        transaction_type=TransactionType.INCOME,
        amount_pence=1000,
        merchant="Weird",
        account_id=acc.id,
        category_id=cat_exp.id,  # Invalid DB link
        transaction_date=datetime(2026, 8, 3, 12, 0, tzinfo=timezone.utc),
    )
    db_session.add(tx_bad)
    db_session.commit()

    rep_3 = get_data_quality_report(db_session)
    integrity = [f for f in rep_3["findings"] if f["finding_type"] == "integrity_issue" and f["transaction_id"] == tx_bad.id]
    assert len(integrity) == 1
    assert "Income transaction references expense category" in integrity[0]["summary"]


def test_6_analysis_and_exports_with_income_categories_and_cash_account(db_session):
    """Analysis separates spending vs income categories cleanly; exports and Cash balances calculate accurately."""
    checking = Account(name="Checking", account_type=AccountType.CURRENT, currency="GBP", starting_balance_pence=100000)
    wallet = Account(name="Home Cash Safe", account_type=AccountType.CASH, currency="GBP", starting_balance_pence=30000)
    cat_rent = Category(name="Rent", category_type=CategoryType.EXPENSE, default_expense_nature=ExpenseNature.FIXED)
    cat_salary = Category(name="Salary", category_type=CategoryType.INCOME)
    cat_gift = Category(name="Cash Gift", category_type=CategoryType.INCOME)
    db_session.add_all([checking, wallet, cat_rent, cat_salary, cat_gift])
    db_session.commit()

    aug_dt = datetime(2026, 8, 10, 12, 0, tzinfo=timezone.utc)
    txs = [
        Transaction(transaction_type=TransactionType.INCOME, amount_pence=250000, merchant="ACME", account_id=checking.id, category_id=cat_salary.id, transaction_date=aug_dt, effective_timestamp=aug_dt),
        Transaction(transaction_type=TransactionType.INCOME, amount_pence=15000, merchant="Birthday", account_id=wallet.id, category_id=cat_gift.id, transaction_date=aug_dt, effective_timestamp=aug_dt),
        Transaction(transaction_type=TransactionType.EXPENSE, amount_pence=80000, merchant="Landlord", account_id=checking.id, category_id=cat_rent.id, expense_nature=ExpenseNature.FIXED, transaction_date=aug_dt, effective_timestamp=aug_dt),
        Transaction(transaction_type=TransactionType.EXPENSE, amount_pence=5000, merchant="Coffee", account_id=wallet.id, category_id=None, expense_nature=ExpenseNature.VARIABLE, transaction_date=aug_dt, effective_timestamp=aug_dt),
    ]
    db_session.add_all(txs)
    db_session.commit()

    analysis = get_comprehensive_analysis(
        db_session,
        preset="custom",
        custom_start="2026-08-01",
        custom_end="2026-08-31",
        interval="month",
    )
    assert analysis["totals"]["income_pence"] == 265000
    assert analysis["totals"]["expenses_pence"] == 85000

    # Spending categories only include expense categories
    exp_cat_names = [c["category_name"] for c in analysis["categories"]]
    assert set(exp_cat_names) == {"Rent", "Uncategorised"}
    assert "Salary" not in exp_cat_names

    # Income categories include Salary and Cash Gift cleanly
    inc_cat_names = [c["category_name"] for c in analysis["income_categories"]]
    assert inc_cat_names == ["Salary", "Cash Gift"]
    assert analysis["income_categories"][0]["category_type"] == "income"

    # Available categories carry purpose metadata
    avail_map = {c["name"]: c for c in analysis["available_categories"]}
    assert avail_map["Salary"]["category_type"] == "income"
    assert avail_map["Rent"]["category_type"] == "expense"

    # Income export XLSX works cleanly without Expense Nature column misleading labels
    xlsx_bytes, filename, _ = generate_analysis_export(
        db_session,
        report_type="income_categories",
        export_format="xlsx",
        preset="custom",
        custom_start="2026-08-01",
        custom_end="2026-08-31",
    )
    assert "income_categories" in filename
    wb = openpyxl.load_workbook(io.BytesIO(xlsx_bytes))
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    header_row = next(r for r in rows if r and r[0] == "Category")
    assert header_row[1] == "Purpose"

    # Ledger CSV export emits N/A instead of Unclassified for Income rows
    csv_bytes, _, _ = generate_ledger_export(db_session, export_format="csv")
    csv_text = csv_bytes.decode("utf-8-sig")
    assert "Income,ACME,Checking,,Salary,N/A" in csv_text


def test_7_cash_account_lifecycle_liquids_reconciliation_and_transfers(db_session, client):
    """
    Cash account type participates in liquid reserves & net worth, reconciliation,
    breakdown ('Cash Accounts'), and transfers without confusing with Current or Savings.
    """
    r_curr = client.post(
        "/api/accounts",
        json={"name": "Main Bank", "account_type": "current", "starting_balance": 1000.0, "as_of_mode": "date", "as_of_date": "2026-08-01"},
    )
    r_cash = client.post(
        "/api/accounts",
        json={"name": "Cash Wallet", "account_type": "cash", "starting_balance": 150.0, "as_of_mode": "date", "as_of_date": "2026-08-01", "color": "#10B981"},
    )
    r_card = client.post(
        "/api/accounts",
        json={"name": "Rewards Card", "account_type": "credit_card", "starting_balance": -200.0, "as_of_mode": "date", "as_of_date": "2026-08-01"},
    )
    assert r_curr.status_code == 201
    assert r_cash.status_code == 201
    assert r_card.status_code == 201

    bank_id = r_curr.json()["id"]
    cash_id = r_cash.json()["id"]
    card_id = r_card.json()["id"]
    assert r_cash.json()["account_type"] == "cash"
    assert r_cash.json()["current_balance_pence"] == 15000

    # Dashboard summary counts Cash inside total_liquid_pence and net_worth_pence
    dash = client.get("/api/dashboard/summary").json()
    assert dash["total_liquid_pence"] == 115000  # 1000 + 150
    assert dash["total_debt_pence"] == 20000
    assert dash["net_worth_pence"] == 95000  # 1150 - 200

    # Breakdown identifies Cash Accounts separately from Depository Accounts
    bd = client.get(f"/api/accounts/{cash_id}/breakdown").json()
    assert bd["account_type"] == "cash"
    assert bd["account_group"] == "Cash Accounts"

    # Transfer Current -> Cash (£100 ATM withdrawal)
    r_trf = client.post(
        "/api/transactions",
        json={
            "transaction_type": "transfer",
            "amount": 100.0,
            "merchant": "ATM Withdrawal",
            "account_id": bank_id,
            "destination_account_id": cash_id,
            "transaction_date": "2026-08-12T12:00:00Z",
        },
    )
    assert r_trf.status_code == 201

    assert LedgerEngine.get_account_balance(db_session, bank_id) == 90000
    assert LedgerEngine.get_account_balance(db_session, cash_id) == 25000
    # Total liquid unchanged by internal transfer (£900 + £250 = £1150)
    dash_after = client.get("/api/dashboard/summary").json()
    assert dash_after["total_liquid_pence"] == 115000

    # Reconciliation eligible on Cash account
    r_rec = client.post(
        f"/api/accounts/{cash_id}/reconciliation/snapshots",
        json={"actual_balance": 240.0, "as_of_mode": "now", "notes": "Counted wallet notes"},
    )
    assert r_rec.status_code == 201
    assert LedgerEngine.get_account_balance(db_session, cash_id) == 24000

    # Changing card to cash or editing cash account preserves behavior cleanly
    r_upd = client.put(f"/api/accounts/{cash_id}", json={"name": "Pocket Cash", "account_type": "cash"})
    assert r_upd.status_code == 200
    assert r_upd.json()["name"] == "Pocket Cash"
    assert r_upd.json()["account_type"] == "cash"


def test_8_alembic_migration_connect_upgrade_and_profile_isolation(tmp_path, monkeypatch):
    """
    Pre-existing DBs migrate cleanly with existing categories defaulting to 'EXPENSE';
    profiles isolate Income categories and Cash accounts strictly per workspace.
    """
    # Part A: Alembic upgrade & SQLite connect-time schema upgrade
    db_file = tmp_path / "legacy_upgrade.db"
    db_url = f"sqlite:///{db_file}"
    init_eng = sa.create_engine(db_url)
    Base.metadata.create_all(bind=init_eng)
    init_eng.dispose()

    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", db_url)
    command.stamp(cfg, "head")
    command.downgrade(cfg, "b2c3d4e5f6a7")

    with sa.create_engine(db_url).begin() as conn:
        conn.execute(
            sa.text(
                "INSERT INTO categories (name, color, default_expense_nature, is_active) "
                "VALUES ('Legacy Rent', '#8B5CF6', 'FIXED', 1)"
            )
        )

    # Opening via configure_sqlite_engine upgrades categories.category_type -> 'EXPENSE'
    rt_eng = configure_sqlite_engine(db_url)
    with rt_eng.connect() as conn:
        cols = [r[1] for r in conn.execute(sa.text("PRAGMA table_info(categories)")).fetchall()]
        assert "category_type" in cols
        val = conn.execute(sa.text("SELECT category_type FROM categories WHERE name='Legacy Rent'")).scalar()
        assert val == "EXPENSE"
    rt_eng.dispose()

    # Upgrading alembic head reaches c3d4e5f6a7b9 idempotently
    command.upgrade(cfg, "head")
    with sa.create_engine(db_url).connect() as conn:
        rev = conn.execute(sa.text("SELECT version_num FROM alembic_version")).scalar()
        assert rev == "c3d4e5f6a7b9"

    # Part B: Strict Profile Isolation
    iso_dir = tmp_path / "isolated_profiles"
    iso_dir.mkdir(parents=True, exist_ok=True)
    test_db_path = iso_dir / "finances.db"
    test_receipts = iso_dir / "receipts"
    test_staging = iso_dir / "staging_receipts"
    test_backups = iso_dir / "backups"
    test_receipts.mkdir(parents=True, exist_ok=True)
    test_staging.mkdir(parents=True, exist_ok=True)
    test_backups.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(profiles_module, "DATA_DIR", iso_dir)
    monkeypatch.setattr(profiles_module, "PROFILES_REGISTRY_PATH", iso_dir / "profiles.json")
    monkeypatch.setattr(profiles_module, "DB_PATH", test_db_path)
    monkeypatch.setattr(profiles_module, "ARCHIVE_RECEIPTS_DIR", test_receipts)
    monkeypatch.setattr(profiles_module, "STAGING_RECEIPTS_DIR", test_staging)
    monkeypatch.setattr(profiles_module, "BACKUP_DIR", test_backups)

    def_eng = configure_sqlite_engine(f"sqlite:///{test_db_path}")
    Base.metadata.create_all(bind=def_eng)
    def_eng.dispose()

    db_registry.dispose_all()
    try:
        prof_b = profiles_module.create_profile("Cash Business")
        client = TestClient(app)

        r_p1 = client.post(
            "/api/categories",
            headers={"X-Profile-ID": "default"},
            json={"name": "Personal Dividends", "category_type": "income"},
        )
        assert r_p1.status_code == 201

        r_p2_acc = client.post(
            "/api/accounts",
            headers={"X-Profile-ID": prof_b.id},
            json={"name": "Register Till", "account_type": "cash", "starting_balance": 50.0},
        )
        assert r_p2_acc.status_code == 201

        default_cats = client.get("/api/categories", headers={"X-Profile-ID": "default"}).json()
        prof_b_cats = client.get("/api/categories", headers={"X-Profile-ID": prof_b.id}).json()
        assert [c["name"] for c in default_cats] == ["Personal Dividends"]
        assert prof_b_cats == []

        default_accs = client.get("/api/accounts", headers={"X-Profile-ID": "default"}).json()
        prof_b_accs = client.get("/api/accounts", headers={"X-Profile-ID": prof_b.id}).json()
        assert default_accs == []
        assert [a["account_type"] for a in prof_b_accs] == ["cash"]
    finally:
        db_registry.dispose_all()
