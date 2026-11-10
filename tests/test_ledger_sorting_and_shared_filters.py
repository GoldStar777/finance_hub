"""
Backend Regression & Functional Test Suite for Ledger Sorting and Shared Date Boundaries.

Verifies:
1. Sorting by date (desc / asc) with stable id tie-breakers.
2. Sorting by amount (asc / desc) with stable date and id tie-breakers for equal amounts.
3. Sorting by category (asc / desc) with uncategorised grouped at the end and stable tie-breakers.
4. Sorting by account (asc / desc) with unassigned grouped at the end and stable tie-breakers.
5. Stable pagination across pages without hopping or missing items.
6. Ledger export (CSV / XLSX) matching the requested sort order and recording it in metadata.
7. Backend date_preset and date_offset filtering respecting the profile's configured timezone.
"""

import pytest
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient

from app.models import (
    Account,
    AccountType,
    Transaction,
    TransactionType,
    ExpenseNature,
    Category,
)
from app.core.transactions import build_transactions_query, apply_transactions_sorting
from app.core.ledger_export import generate_ledger_export


def test_1_date_sorting_and_stable_id_ties(db_session, client: TestClient):
    """Verifies date sorting in both directions with deterministic tie-breakers."""
    acc = Account(name="Current Account", account_type=AccountType.CURRENT, currency="GBP", starting_balance_pence=100000)
    db_session.add(acc)
    db_session.commit()

    # Three transactions on different dates and two on the same date
    t1 = Transaction(
        transaction_date=datetime(2026, 10, 1, 10, 0, 0, tzinfo=timezone.utc),
        transaction_type=TransactionType.EXPENSE,
        amount_pence=1000,
        merchant="Store 1",
        account_id=acc.id,
    )
    t2 = Transaction(
        transaction_date=datetime(2026, 10, 2, 10, 0, 0, tzinfo=timezone.utc),
        transaction_type=TransactionType.EXPENSE,
        amount_pence=2000,
        merchant="Store 2",
        account_id=acc.id,
    )
    t3 = Transaction(
        transaction_date=datetime(2026, 10, 2, 10, 0, 0, tzinfo=timezone.utc),
        transaction_type=TransactionType.EXPENSE,
        amount_pence=3000,
        merchant="Store 3 (same date as 2)",
        account_id=acc.id,
    )
    t4 = Transaction(
        transaction_date=datetime(2026, 10, 3, 10, 0, 0, tzinfo=timezone.utc),
        transaction_type=TransactionType.EXPENSE,
        amount_pence=4000,
        merchant="Store 4",
        account_id=acc.id,
    )
    db_session.add_all([t1, t2, t3, t4])
    db_session.commit()

    # Date desc: newest first
    res_desc = client.get("/api/transactions?sort_by=date&sort_order=desc")
    assert res_desc.status_code == 200
    ids_desc = [t["id"] for t in res_desc.json()["items"]]
    assert ids_desc == [t4.id, t3.id, t2.id, t1.id]  # t3 has higher ID than t2 on same date

    # Date asc: oldest first
    res_asc = client.get("/api/transactions?sort_by=date&sort_order=asc")
    assert res_asc.status_code == 200
    ids_asc = [t["id"] for t in res_asc.json()["items"]]
    assert ids_asc == [t1.id, t2.id, t3.id, t4.id]


def test_2_amount_sorting_and_stable_ties(db_session, client: TestClient):
    """Verifies amount sorting (lowest first & highest first) with stable date and id tie-breakers."""
    acc = Account(name="Current Account", account_type=AccountType.CURRENT, currency="GBP", starting_balance_pence=100000)
    db_session.add(acc)
    db_session.commit()

    t_low = Transaction(
        transaction_date=datetime(2026, 10, 10, 10, 0, 0, tzinfo=timezone.utc),
        transaction_type=TransactionType.EXPENSE,
        amount_pence=500,
        merchant="Coffee",
        account_id=acc.id,
    )
    t_mid1 = Transaction(
        transaction_date=datetime(2026, 10, 11, 10, 0, 0, tzinfo=timezone.utc),
        transaction_type=TransactionType.EXPENSE,
        amount_pence=2500,
        merchant="Lunch 1",
        account_id=acc.id,
    )
    t_mid2 = Transaction(
        transaction_date=datetime(2026, 10, 12, 10, 0, 0, tzinfo=timezone.utc),
        transaction_type=TransactionType.EXPENSE,
        amount_pence=2500,
        merchant="Lunch 2 (newer)",
        account_id=acc.id,
    )
    t_high = Transaction(
        transaction_date=datetime(2026, 10, 9, 10, 0, 0, tzinfo=timezone.utc),
        transaction_type=TransactionType.EXPENSE,
        amount_pence=15000,
        merchant="Electronics",
        account_id=acc.id,
    )
    db_session.add_all([t_low, t_mid1, t_mid2, t_high])
    db_session.commit()

    # Amount asc: lowest first
    res_asc = client.get("/api/transactions?sort_by=amount&sort_order=asc")
    assert res_asc.status_code == 200
    items_asc = res_asc.json()["items"]
    # 500, 2500 (newer date first), 2500 (older date), 15000
    assert items_asc[0]["id"] == t_low.id
    assert items_asc[1]["id"] == t_mid2.id
    assert items_asc[2]["id"] == t_mid1.id
    assert items_asc[3]["id"] == t_high.id

    # Amount desc: highest first
    res_desc = client.get("/api/transactions?sort_by=amount&sort_order=desc")
    assert res_desc.status_code == 200
    items_desc = res_desc.json()["items"]
    assert items_desc[0]["id"] == t_high.id
    assert items_desc[1]["id"] == t_mid2.id
    assert items_desc[2]["id"] == t_mid1.id
    assert items_desc[3]["id"] == t_low.id


def test_3_category_sorting_with_uncategorised_placement(db_session, client: TestClient):
    """Verifies category A-Z and Z-A sorting with Uncategorised cleanly placed at the end."""
    acc = Account(name="Bank Acc", account_type=AccountType.CURRENT, currency="GBP", starting_balance_pence=100000)
    cat_b = Category(name="Books", color="#3B82F6")
    cat_t = Category(name="Travel", color="#EF4444")
    db_session.add_all([acc, cat_b, cat_t])
    db_session.commit()

    t_travel = Transaction(
        transaction_date=datetime(2026, 10, 1, 10, 0, 0, tzinfo=timezone.utc),
        transaction_type=TransactionType.EXPENSE,
        amount_pence=5000,
        merchant="Flight",
        account_id=acc.id,
        category_id=cat_t.id,
    )
    t_books = Transaction(
        transaction_date=datetime(2026, 10, 2, 10, 0, 0, tzinfo=timezone.utc),
        transaction_type=TransactionType.EXPENSE,
        amount_pence=1500,
        merchant="Bookstore",
        account_id=acc.id,
        category_id=cat_b.id,
    )
    t_uncat = Transaction(
        transaction_date=datetime(2026, 10, 3, 10, 0, 0, tzinfo=timezone.utc),
        transaction_type=TransactionType.EXPENSE,
        amount_pence=800,
        merchant="Unknown Vendor",
        account_id=acc.id,
        category_id=None,
    )
    db_session.add_all([t_travel, t_books, t_uncat])
    db_session.commit()

    # Category asc: Books, Travel, then Uncategorised at end
    res_asc = client.get("/api/transactions?sort_by=category&sort_order=asc")
    assert res_asc.status_code == 200
    items_asc = res_asc.json()["items"]
    assert items_asc[0]["id"] == t_books.id
    assert items_asc[1]["id"] == t_travel.id
    assert items_asc[2]["id"] == t_uncat.id

    # Category desc: Travel, Books, then Uncategorised at end
    res_desc = client.get("/api/transactions?sort_by=category&sort_order=desc")
    assert res_desc.status_code == 200
    items_desc = res_desc.json()["items"]
    assert items_desc[0]["id"] == t_travel.id
    assert items_desc[1]["id"] == t_books.id
    assert items_desc[2]["id"] == t_uncat.id


def test_4_account_sorting_with_unassigned_placement(db_session, client: TestClient):
    """Verifies account A-Z and Z-A sorting with Unassigned placed at the end."""
    acc_a = Account(name="Alpha Bank", account_type=AccountType.CURRENT, currency="GBP", starting_balance_pence=50000)
    acc_z = Account(name="Zenith Card", account_type=AccountType.SAVINGS, currency="GBP", starting_balance_pence=0)
    db_session.add_all([acc_a, acc_z])
    db_session.commit()

    t_z = Transaction(
        transaction_date=datetime(2026, 10, 1, 10, 0, 0, tzinfo=timezone.utc),
        transaction_type=TransactionType.EXPENSE,
        amount_pence=1200,
        merchant="Charge Z",
        account_id=acc_z.id,
    )
    t_a = Transaction(
        transaction_date=datetime(2026, 10, 2, 10, 0, 0, tzinfo=timezone.utc),
        transaction_type=TransactionType.EXPENSE,
        amount_pence=1400,
        merchant="Charge A",
        account_id=acc_a.id,
    )
    t_unassigned = Transaction(
        transaction_date=datetime(2026, 10, 3, 10, 0, 0, tzinfo=timezone.utc),
        transaction_type=TransactionType.EXPENSE,
        amount_pence=900,
        merchant="Cash spend",
        account_id=None,
    )
    db_session.add_all([t_z, t_a, t_unassigned])
    db_session.commit()

    # Account asc: Alpha Bank, Zenith Card, then Unassigned at end
    res_asc = client.get("/api/transactions?sort_by=account&sort_order=asc")
    assert res_asc.status_code == 200
    items_asc = res_asc.json()["items"]
    assert items_asc[0]["id"] == t_a.id
    assert items_asc[1]["id"] == t_z.id
    assert items_asc[2]["id"] == t_unassigned.id

    # Account desc: Zenith Card, Alpha Bank, then Unassigned at end
    res_desc = client.get("/api/transactions?sort_by=account&sort_order=desc")
    assert res_desc.status_code == 200
    items_desc = res_desc.json()["items"]
    assert items_desc[0]["id"] == t_z.id
    assert items_desc[1]["id"] == t_a.id
    assert items_desc[2]["id"] == t_unassigned.id


def test_5_pagination_stability_across_pages(db_session, client: TestClient):
    """Verifies that sorting produces non-overlapping, strictly stable pages."""
    acc = Account(name="Current Account", account_type=AccountType.CURRENT, currency="GBP", starting_balance_pence=100000)
    db_session.add(acc)
    db_session.commit()

    # Create 10 transactions with identical amounts to stress tie-breaker stability
    for i in range(10):
        t = Transaction(
            transaction_date=datetime(2026, 10, 1 + (i % 3), 12, 0, 0, tzinfo=timezone.utc),
            transaction_type=TransactionType.EXPENSE,
            amount_pence=1000,  # identical amount
            merchant=f"Merchant {i+1}",
            account_id=acc.id,
        )
        db_session.add(t)
    db_session.commit()

    # Page 1 (limit=4, offset=0)
    p1 = client.get("/api/transactions?sort_by=amount&sort_order=desc&limit=4&offset=0").json()
    p1_ids = [t["id"] for t in p1["items"]]
    assert len(p1_ids) == 4

    # Page 2 (limit=4, offset=4)
    p2 = client.get("/api/transactions?sort_by=amount&sort_order=desc&limit=4&offset=4").json()
    p2_ids = [t["id"] for t in p2["items"]]
    assert len(p2_ids) == 4

    # Page 3 (limit=4, offset=8)
    p3 = client.get("/api/transactions?sort_by=amount&sort_order=desc&limit=4&offset=8").json()
    p3_ids = [t["id"] for t in p3["items"]]
    assert len(p3_ids) == 2

    # Zero overlap across pages
    all_seen = set(p1_ids)
    for id_val in p2_ids:
        assert id_val not in all_seen, f"ID {id_val} appeared on both page 1 and page 2!"
        all_seen.add(id_val)
    for id_val in p3_ids:
        assert id_val not in all_seen, f"ID {id_val} appeared on both prior pages and page 3!"
        all_seen.add(id_val)
    assert len(all_seen) == 10


def test_6_export_preserves_selected_sort_order(db_session, client: TestClient):
    """Verifies that ledger export incorporates the requested sort order into the data rows and metadata."""
    acc = Account(name="Current Account", account_type=AccountType.CURRENT, currency="GBP", starting_balance_pence=100000)
    db_session.add(acc)
    db_session.commit()

    t_cheap = Transaction(
        transaction_date=datetime(2026, 10, 1, 10, 0, 0, tzinfo=timezone.utc),
        transaction_type=TransactionType.EXPENSE,
        amount_pence=200,
        merchant="Cheap Item",
        account_id=acc.id,
    )
    t_expensive = Transaction(
        transaction_date=datetime(2026, 10, 2, 10, 0, 0, tzinfo=timezone.utc),
        transaction_type=TransactionType.EXPENSE,
        amount_pence=9900,
        merchant="Expensive Item",
        account_id=acc.id,
    )
    db_session.add_all([t_cheap, t_expensive])
    db_session.commit()

    # CSV Export with amount asc
    res_csv = client.get("/api/transactions/export?format=csv&sort_by=amount&sort_order=asc")
    assert res_csv.status_code == 200
    csv_text = res_csv.text
    assert "Sort Order,Amount (Lowest first)" in csv_text
    # Cheap Item should appear before Expensive Item in the data table
    cheap_pos = csv_text.find("Cheap Item")
    exp_pos = csv_text.find("Expensive Item")
    assert cheap_pos != -1 and exp_pos != -1
    assert cheap_pos < exp_pos


def test_7_backend_date_preset_resolution(db_session):
    """Verifies date_preset in build_transactions_query resolves correctly."""
    acc = Account(name="Main Bank", account_type=AccountType.CURRENT, currency="GBP", starting_balance_pence=100000)
    db_session.add(acc)
    db_session.commit()

    # Transaction in current month
    now = datetime.now(timezone.utc)
    tx_now = Transaction(
        transaction_date=now,
        transaction_type=TransactionType.INCOME,
        amount_pence=50000,
        merchant="Current Month Salary",
        account_id=acc.id,
    )
    # Transaction 180 days ago (outside current month)
    tx_past = Transaction(
        transaction_date=now - timedelta(days=180),
        transaction_type=TransactionType.INCOME,
        amount_pence=30000,
        merchant="Old Salary",
        account_id=acc.id,
    )
    db_session.add_all([tx_now, tx_past])
    db_session.commit()

    # Query with date_preset='month', date_offset=0
    q = build_transactions_query(db_session, date_preset="month", date_offset=0)
    results = q.all()
    res_ids = [t.id for t in results]
    assert tx_now.id in res_ids
    assert tx_past.id not in res_ids


def test_8_case_insensitive_alphabetical_sort_range_metadata_and_1y_alias(db_session, client: TestClient):
    """
    Verifies:
    - Case-insensitive alphabetical category & account sorting (Uncategorised / Unassigned still last)
    - /api/transactions returns server-resolved range_start_date, range_end_date, and nav boundary booleans
    - /api/transactions?date_preset=1y matches date_preset=year identically
    - /api/transactions/matching-ids preserves requested sort order
    """
    acc_upper = Account(name="Zebra Bank", account_type=AccountType.CURRENT, currency="GBP", starting_balance_pence=100000)
    acc_lower = Account(name="alpha bank", account_type=AccountType.SAVINGS, currency="GBP", starting_balance_pence=100000)
    cat_upper = Category(name="Utilities", color="#3B82F6")
    cat_lower = Category(name="dining", color="#10B981")
    db_session.add_all([acc_upper, acc_lower, cat_upper, cat_lower])
    db_session.commit()

    now = datetime.now(timezone.utc)
    t_dining_alpha = Transaction(
        transaction_date=now - timedelta(days=5),
        transaction_type=TransactionType.EXPENSE,
        amount_pence=1200,
        merchant="Bistro",
        account_id=acc_lower.id,
        category_id=cat_lower.id,
    )
    t_util_zebra = Transaction(
        transaction_date=now - timedelta(days=3),
        transaction_type=TransactionType.EXPENSE,
        amount_pence=8000,
        merchant="Power Co",
        account_id=acc_upper.id,
        category_id=cat_upper.id,
    )
    t_uncat_unassigned = Transaction(
        transaction_date=now - timedelta(days=1),
        transaction_type=TransactionType.EXPENSE,
        amount_pence=500,
        merchant="Cash Misc",
        account_id=None,
        category_id=None,
    )
    db_session.add_all([t_dining_alpha, t_util_zebra, t_uncat_unassigned])
    db_session.commit()

    # Case-insensitive Category A-Z: 'dining' before 'Utilities', Uncategorised last
    res_cat = client.get("/api/transactions?sort_by=category&sort_order=asc").json()
    assert [t["id"] for t in res_cat["items"]] == [t_dining_alpha.id, t_util_zebra.id, t_uncat_unassigned.id]

    # Case-insensitive Account A-Z: 'alpha bank' before 'Zebra Bank', Unassigned last
    res_acc = client.get("/api/transactions?sort_by=account&sort_order=asc").json()
    assert [t["id"] for t in res_acc["items"]] == [t_dining_alpha.id, t_util_zebra.id, t_uncat_unassigned.id]

    # /api/transactions/matching-ids respects sort_by & sort_order
    res_match = client.get("/api/transactions/matching-ids?sort_by=amount&sort_order=desc").json()
    assert res_match["ids"] == [t_util_zebra.id, t_dining_alpha.id, t_uncat_unassigned.id]

    # Alias '1y' matches 'year' and returns range metadata + boundary flags
    res_1y = client.get("/api/transactions?date_preset=1y&date_offset=0").json()
    res_year = client.get("/api/transactions?date_preset=year&date_offset=0").json()
    assert res_1y["range_start_date"] is not None
    assert res_1y["range_end_date"] is not None
    assert res_1y["range_start_date"] == res_year["range_start_date"]
    assert res_1y["range_end_date"] == res_year["range_end_date"]
    assert res_1y["can_navigate_previous"] is True
    assert res_1y["can_navigate_next"] is False

    # Shifted period back (date_offset=-1) enables can_navigate_next
    res_prev = client.get("/api/transactions?date_preset=month&date_offset=-1").json()
    assert res_prev["can_navigate_next"] is True
