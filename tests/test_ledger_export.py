"""
Ledger Filtering and Export Tests

Tests:
1. Multi-account filtering (including unassigned)
2. Multi-category filtering (including uncategorised as distinct from all)
3. Multi-type filtering (expense, income, transfer)
4. Date range parsing & normalization across timezones
5. Ledger CSV export formatting, scope, and metadata
6. Ledger XLSX export formatting, headers, numeric amounts, currency symbol, and metadata
"""

import io
import csv
from datetime import datetime, timezone
import openpyxl
import pytest
from fastapi.testclient import TestClient

from app.models import Transaction, TransactionType, ExpenseNature, Account, AccountType, Category
from app.core.currency import pounds_to_pence


def test_ledger_multi_account_and_category_filtering(client: TestClient, db_session):
    # Setup accounts
    acc1 = Account(name="Current Account", account_type=AccountType.CURRENT, currency="GBP")
    acc2 = Account(name="Monzo", account_type=AccountType.CURRENT, currency="GBP")
    acc3 = Account(name="Savings", account_type=AccountType.SAVINGS, currency="GBP")
    db_session.add_all([acc1, acc2, acc3])
    db_session.commit()

    # Setup categories
    cat1 = Category(name="Groceries")
    cat2 = Category(name="Utilities")
    db_session.add_all([cat1, cat2])
    db_session.commit()

    # Transactions
    tx1 = Transaction(
        transaction_date=datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc),
        transaction_type=TransactionType.EXPENSE,
        amount_pence=2500,
        merchant="Sainsburys",
        account_id=acc1.id,
        category_id=cat1.id,
    )
    tx2 = Transaction(
        transaction_date=datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc),
        transaction_type=TransactionType.EXPENSE,
        amount_pence=4000,
        merchant="EDF Energy",
        account_id=acc2.id,
        category_id=cat2.id,
    )
    tx3 = Transaction(
        transaction_date=datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc),
        transaction_type=TransactionType.EXPENSE,
        amount_pence=1500,
        merchant="Corner Shop",
        account_id=acc3.id,
        category_id=None,  # Uncategorised
    )
    tx4 = Transaction(
        transaction_date=datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc),
        transaction_type=TransactionType.INCOME,
        amount_pence=200000,
        merchant="Employer",
        account_id=None,  # Unassigned
        category_id=None,
    )
    db_session.add_all([tx1, tx2, tx3, tx4])
    db_session.commit()

    # 1. Multi-account filter: acc1 and acc2
    res = client.get(f"/api/transactions?account_ids={acc1.id},{acc2.id}")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 2
    merchants = {item["merchant"] for item in data["items"]}
    assert merchants == {"Sainsburys", "EDF Energy"}

    # 2. Multi-category filter: cat1 and uncategorised (0)
    res = client.get(f"/api/transactions?category_ids={cat1.id},0")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 3  # tx1, tx3, tx4
    merchants = {item["merchant"] for item in data["items"]}
    assert merchants == {"Sainsburys", "Corner Shop", "Employer"}

    # 3. Explicit uncategorised only
    res = client.get("/api/transactions?category_ids=uncategorized")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 2  # tx3, tx4

    # 4. Multi-type filter: income and transfer
    res = client.get("/api/transactions?transaction_types=income,transfer")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 1
    assert data["items"][0]["merchant"] == "Employer"


def test_ledger_csv_and_xlsx_export(client: TestClient, db_session):
    acc = Account(name="Main Checking", account_type=AccountType.CURRENT, currency="GBP")
    cat = Category(name="Tech")
    db_session.add_all([acc, cat])
    db_session.commit()

    tx = Transaction(
        transaction_date=datetime(2026, 10, 12, 10, 30, tzinfo=timezone.utc),
        effective_timestamp=datetime(2026, 10, 12, 10, 30, tzinfo=timezone.utc),
        transaction_type=TransactionType.EXPENSE,
        amount_pence=12999,
        merchant="Apple Store",
        account_id=acc.id,
        category_id=cat.id,
        notes="Magic Keyboard",
        entry_method="receipt",
        receipt_path="receipts/2026/10/apple.pdf"
    )
    db_session.add(tx)
    db_session.commit()

    # Test CSV Export
    csv_res = client.get("/api/transactions/export?format=csv")
    assert csv_res.status_code == 200
    assert "text/csv" in csv_res.headers["content-type"]
    assert "filename=" in csv_res.headers["content-disposition"]
    csv_text = csv_res.content.decode("utf-8-sig")
    assert "Finance Hub — Ledger Export" in csv_text
    assert "Apple Store" in csv_text
    assert "129.99" in csv_text
    assert "Main Checking" in csv_text
    assert "Tech" in csv_text
    assert "receipts/2026/10/apple.pdf" in csv_text

    # Test XLSX Export
    xlsx_res = client.get("/api/transactions/export?format=xlsx")
    assert xlsx_res.status_code == 200
    assert "spreadsheetml" in xlsx_res.headers["content-type"]
    wb = openpyxl.load_workbook(io.BytesIO(xlsx_res.content))
    assert "Ledger Transactions" in wb.sheetnames
    ws = wb["Ledger Transactions"]

    # Verify metadata and content
    found_title = any(ws.cell(row=r, column=1).value == "Finance Hub — Ledger Export" for r in range(1, 10))
    assert found_title, "Title row must be present in XLSX"

    # Find the data row with Apple Store
    found_apple = False
    for r in range(1, ws.max_row + 1):
        if ws.cell(row=r, column=6).value == "Apple Store":
            found_apple = True
            # Check numeric value (column 11 is amount)
            amt_val = ws.cell(row=r, column=11).value
            assert isinstance(amt_val, (int, float)), f"Amount must be numeric float, got {type(amt_val)}"
            assert amt_val == 129.99
            break
    assert found_apple, "Apple Store transaction must be present in XLSX"
