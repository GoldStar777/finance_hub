"""
Isolated verification suite for Finance Hub Repeat Transactions.

Covers:
1. Weekly, biweekly, monthly, quarterly, and yearly date generation (count and end-date modes).
2. Month-end and leap-year clamping without cumulative day-of-month drift.
3. Profile timezone and daylight-saving transitions (GMT/BST, EST/EDT, Pacific/Auckland).
4. Recurrence crossing today: past/today actuals affect current balances while future occurrences stay planned.
5. Ground-truth balance anchor integrity for historical occurrences.
6. Strict atomic rollback when validation or mid-batch database flush/commit fails.
7. Idempotency key retry, conflict, concurrent IntegrityError race, and distinct submission behavior.
8. Independent lifecycle in Ledger, Analysis, CSV/XLSX exports, single edits, bulk delete, and restore.
"""

import csv
import io
import json
from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch
from zoneinfo import ZoneInfo

import openpyxl
import pytest
from sqlalchemy.exc import IntegrityError

from app.core.analysis import get_comprehensive_analysis
from app.core.repeat_transactions import (
    MAX_REPEAT_OCCURRENCES,
    generate_repeat_occurrence_dates,
)
from app.core.timezone import (
    ensure_utc,
    get_app_timezone,
    get_end_of_day_utc,
    get_today_local,
)
from app.ledger import LedgerEngine
from app.models import (
    Account,
    AccountBalanceAnchor,
    AccountType,
    Category,
    ExpenseNature,
    RepeatSeriesBatch,
    SystemSetting,
    Transaction,
    TransactionType,
)


def _setup_workspace(db_session, tz_name: str = "Europe/London"):
    db_session.add(SystemSetting(key="app_timezone", value=tz_name))
    checking = Account(
        name="Everyday Checking",
        account_type=AccountType.CURRENT,
        currency="GBP",
        starting_balance_pence=100000,
        starting_balance_date=datetime(2025, 1, 1, 0, 0, tzinfo=timezone.utc),
    )
    savings = Account(
        name="Goal Savings",
        account_type=AccountType.SAVINGS,
        currency="GBP",
        starting_balance_pence=50000,
        starting_balance_date=datetime(2025, 1, 1, 0, 0, tzinfo=timezone.utc),
    )
    cat_bills = Category(name="Utilities", default_expense_nature=ExpenseNature.FIXED)
    cat_income = Category(name="Freelance", default_expense_nature=ExpenseNature.UNCLASSIFIED)
    db_session.add_all([checking, savings, cat_bills, cat_income])
    db_session.commit()
    return checking, savings, cat_bills, cat_income


def test_1_weekly_biweekly_monthly_quarterly_yearly_generation():
    """Verifies exact date generation across all five frequencies in both count and end-date modes."""
    weekly = generate_repeat_occurrence_dates(
        first_date=date(2026, 1, 5),
        frequency="weekly",
        end_mode="count",
        occurrence_count=4,
    )
    assert weekly == [
        date(2026, 1, 5),
        date(2026, 1, 12),
        date(2026, 1, 19),
        date(2026, 1, 26),
    ]

    biweekly_end = generate_repeat_occurrence_dates(
        first_date=date(2026, 12, 18),
        frequency="biweekly",
        end_mode="end_date",
        last_date=date(2027, 1, 15),
    )
    assert biweekly_end == [
        date(2026, 12, 18),
        date(2027, 1, 1),
        date(2027, 1, 15),
    ]

    monthly = generate_repeat_occurrence_dates(
        first_date=date(2026, 5, 15),
        frequency="monthly",
        end_mode="end_date",
        last_date=date(2026, 8, 14),
    )
    assert monthly == [
        date(2026, 5, 15),
        date(2026, 6, 15),
        date(2026, 7, 15),
    ]

    quarterly = generate_repeat_occurrence_dates(
        first_date=date(2026, 3, 10),
        frequency="quarterly",
        end_mode="count",
        occurrence_count=4,
    )
    assert quarterly == [
        date(2026, 3, 10),
        date(2026, 6, 10),
        date(2026, 9, 10),
        date(2026, 12, 10),
    ]

    yearly = generate_repeat_occurrence_dates(
        first_date=date(2026, 4, 1),
        frequency="yearly",
        end_mode="count",
        occurrence_count=3,
    )
    assert yearly == [
        date(2026, 4, 1),
        date(2027, 4, 1),
        date(2028, 4, 1),
    ]


def test_2_month_end_and_leap_year_anchor_preservation():
    """Ensures shorter months clamp to month-end without losing the anchor day on later months."""
    non_leap_31 = generate_repeat_occurrence_dates(
        first_date=date(2026, 1, 31),
        frequency="monthly",
        end_mode="count",
        occurrence_count=5,
    )
    assert non_leap_31 == [
        date(2026, 1, 31),
        date(2026, 2, 28),
        date(2026, 3, 31),
        date(2026, 4, 30),
        date(2026, 5, 31),
    ]

    leap_31 = generate_repeat_occurrence_dates(
        first_date=date(2024, 1, 31),
        frequency="monthly",
        end_mode="count",
        occurrence_count=3,
    )
    assert leap_31 == [
        date(2024, 1, 31),
        date(2024, 2, 29),
        date(2024, 3, 31),
    ]

    leap_day_yearly = generate_repeat_occurrence_dates(
        first_date=date(2024, 2, 29),
        frequency="yearly",
        end_mode="count",
        occurrence_count=5,
    )
    assert leap_day_yearly == [
        date(2024, 2, 29),
        date(2025, 2, 28),
        date(2026, 2, 28),
        date(2027, 2, 28),
        date(2028, 2, 29),
    ]

    quarterly_30 = generate_repeat_occurrence_dates(
        first_date=date(2025, 11, 30),
        frequency="quarterly",
        end_mode="count",
        occurrence_count=4,
    )
    assert quarterly_30 == [
        date(2025, 11, 30),
        date(2026, 2, 28),
        date(2026, 5, 30),
        date(2026, 8, 30),
    ]


def test_3_profile_timezone_and_dst_boundaries(db_session, client):
    """
    Verifies occurrences preserve exact local calendar dates across DST spring-forward/fall-back
    and respect a non-UTC profile timezone (America/New_York and Pacific/Auckland).
    """
    checking, _, cat_bills, _ = _setup_workspace(db_session, tz_name="America/New_York")

    # Cross US spring-forward (2026-03-08) and fall-back (2026-11-01) using monthly 1st dates
    res = client.post(
        "/api/transactions/repeat",
        json={
            "transaction_type": "expense",
            "amount": 25.00,
            "merchant": "Cloud Hosting",
            "account_id": checking.id,
            "category_id": cat_bills.id,
            "expense_nature": "fixed",
            "frequency": "monthly",
            "first_date": "2026-02-01",
            "end_mode": "count",
            "occurrence_count": 10,
            "idempotency_key": "tz-dst-ny-series-001",
        },
    )
    assert res.status_code == 201
    items = res.json()["items"]
    assert len(items) == 10

    ny_tz = ZoneInfo("America/New_York")
    # Feb (EST -5 -> 17:00Z), Apr (EDT -4 -> 16:00Z), Nov 1 (EDT->EST at 02:00 local, 12:00 EST -> 17:00Z)
    resolved_local = [ensure_utc(datetime.fromisoformat(i["transaction_date"])).astimezone(ny_tz) for i in items]
    expected_months = [2, 3, 4, 5, 6, 7, 8, 9, 10, 11]
    assert [dt.month for dt in resolved_local] == expected_months
    assert all(dt.day == 1 and dt.hour == 12 for dt in resolved_local)
    assert ensure_utc(datetime.fromisoformat(items[0]["transaction_date"])).hour == 17  # EST
    assert ensure_utc(datetime.fromisoformat(items[2]["transaction_date"])).hour == 16  # EDT
    assert ensure_utc(datetime.fromisoformat(items[9]["transaction_date"])).hour == 17  # Back to EST on Nov 1

    # Also switch profile timezone to Pacific/Auckland (UTC+13) and check planned vs active today boundary
    setting = db_session.query(SystemSetting).filter(SystemSetting.key == "app_timezone").first()
    setting.value = "Pacific/Auckland"
    db_session.commit()

    nz_today = get_today_local("Pacific/Auckland")
    nz_yesterday = nz_today - timedelta(days=1)
    nz_tomorrow = nz_today + timedelta(days=1)

    res_nz = client.post(
        "/api/transactions/repeat",
        json={
            "transaction_type": "expense",
            "amount": 10.00,
            "merchant": "Daily Transit",
            "account_id": checking.id,
            "category_id": cat_bills.id,
            "frequency": "weekly",
            "first_date": (nz_today - timedelta(days=7)).isoformat(),
            "end_mode": "end_date",
            "last_date": (nz_today + timedelta(days=7)).isoformat(),
            "idempotency_key": "tz-dst-nz-series-002",
        },
    )
    assert res_nz.status_code == 201
    nz_items = res_nz.json()["items"]
    assert len(nz_items) == 3
    assert nz_items[0]["is_planned"] is False  # today - 7d
    assert nz_items[1]["is_planned"] is False  # today in Pacific/Auckland
    assert nz_items[2]["is_planned"] is True   # today + 7d
    assert nz_tomorrow > nz_today > nz_yesterday


def test_4_recurrence_crossing_today_balances_and_analysis(db_session, client):
    """
    Recurrence crossing today:
    - Past & today occurrences deduct from current balance, liquid reserves, net worth, and Analysis actuals.
    - Future occurrences remain planned, do NOT alter current balances, and appear in Analysis forecast.
    """
    checking, savings, cat_bills, _ = _setup_workspace(db_session, tz_name="Europe/London")
    app_tz = get_app_timezone(db_session)
    today = get_today_local(app_tz)

    # Weekly £50.00 across 5 occurrences: today-14d, today-7d, today, today+7d, today+14d
    first_d = today - timedelta(days=14)
    res = client.post(
        "/api/transactions/repeat",
        json={
            "transaction_type": "expense",
            "amount": 50.00,
            "merchant": "Weekly Groceries",
            "account_id": checking.id,
            "category_id": cat_bills.id,
            "expense_nature": "variable",
            "notes": "Weekly food shop",
            "frequency": "weekly",
            "first_date": first_d.isoformat(),
            "end_mode": "count",
            "occurrence_count": 5,
            "idempotency_key": "cross-today-series-001",
        },
    )
    assert res.status_code == 201
    data = res.json()
    assert data["created_count"] == 5
    planned_flags = [item["is_planned"] for item in data["items"]]
    assert planned_flags == [False, False, False, True, True]

    # Current balance: £1,000 - (3 * £50) = £850 (85,000p); Projected: £750 (75,000p)
    assert LedgerEngine.get_account_balance(db_session, checking.id, include_planned=False) == 85000
    assert LedgerEngine.get_account_balance(db_session, checking.id, include_planned=True) == 75000

    dash = client.get("/api/dashboard/summary").json()
    # Checking £850 + Savings £500 = £1,350
    assert dash["total_liquid_pence"] == 135000
    assert dash["net_worth_pence"] == 135000
    assert dash["planned_expenses_pence"] == 10000  # Two future £50 expenses
    assert dash["planned_count"] == 2

    analysis = get_comprehensive_analysis(db_session, preset="all")
    assert analysis["totals"]["expenses_pence"] == 15000
    assert analysis["forecast"]["planned_expenses_pence"] == 10000
    assert analysis["forecast"]["planned_transactions_count"] == 2


def test_5_anchor_behavior_for_historical_occurrences(db_session, client):
    """
    Historical occurrences dated on or before a ground-truth balance anchor cutoff must NOT change
    the current balance derived from that anchor; only occurrences strictly after the anchor and <= today apply.
    """
    checking, _, cat_bills, _ = _setup_workspace(db_session, tz_name="Europe/London")
    app_tz = get_app_timezone(db_session)
    today = get_today_local(app_tz)

    anchor_day = today - timedelta(days=10)
    anchor_dt = get_end_of_day_utc(anchor_day, tz_str=app_tz)
    anchor = AccountBalanceAnchor(
        account_id=checking.id,
        balance_pence=200000,  # £2,000.00 ground-truth statement balance
        anchor_date=anchor_dt,
        is_opening=False,
        notes="Verified bank balance",
    )
    db_session.add(anchor)
    db_session.commit()

    # Weekly £25 starting today-20d:
    # -20d (pre-anchor), -13d (pre-anchor), -6d (post-anchor actual), +1d (planned), +8d (planned)
    res = client.post(
        "/api/transactions/repeat",
        json={
            "transaction_type": "expense",
            "amount": 25.00,
            "merchant": "Gym Weekly",
            "account_id": checking.id,
            "category_id": cat_bills.id,
            "frequency": "weekly",
            "first_date": (today - timedelta(days=20)).isoformat(),
            "end_mode": "count",
            "occurrence_count": 5,
            "idempotency_key": "anchor-history-series-001",
        },
    )
    assert res.status_code == 201

    # Anchor £2,000 - £25 (today - 6d) = £1,975.00 (pre-anchor -20d and -13d ignored)
    assert LedgerEngine.get_account_balance(db_session, checking.id, include_planned=False) == 197500
    # Including +1d and +8d planned: £2,000 - £75 = £1,925.00
    assert LedgerEngine.get_account_balance(db_session, checking.id, include_planned=True) == 192500

    # All 5 occurrences remain visible in Ledger
    ledger_res = client.get(f"/api/transactions?account_id={checking.id}&limit=50").json()
    assert ledger_res["total"] == 5


def test_6_atomic_rollback_on_invalid_input_or_mid_write_failure(db_session, client):
    """Verifies validation errors and mid-transaction commit/flush failures create zero partial rows."""
    checking, savings, cat_bills, _ = _setup_workspace(db_session)

    # 6a. Pre-validation errors
    bad_cat = client.post(
        "/api/transactions/repeat",
        json={
            "transaction_type": "expense",
            "amount": 40.00,
            "account_id": checking.id,
            "category_id": 999999,
            "frequency": "monthly",
            "first_date": "2026-06-01",
            "end_mode": "count",
            "occurrence_count": 3,
            "idempotency_key": "invalid-cat-001",
        },
    )
    assert bad_cat.status_code == 404

    bad_range = client.post(
        "/api/transactions/repeat",
        json={
            "transaction_type": "expense",
            "amount": 40.00,
            "account_id": checking.id,
            "category_id": cat_bills.id,
            "frequency": "monthly",
            "first_date": "2026-06-15",
            "end_mode": "end_date",
            "last_date": "2026-06-01",
            "idempotency_key": "invalid-range-001",
        },
    )
    assert bad_range.status_code == 400

    over_limit = client.post(
        "/api/transactions/repeat",
        json={
            "transaction_type": "expense",
            "amount": 10.00,
            "account_id": checking.id,
            "frequency": "weekly",
            "first_date": "2026-01-01",
            "end_mode": "end_date",
            "last_date": "2040-01-01",
            "idempotency_key": "over-limit-001",
        },
    )
    assert over_limit.status_code == 400
    assert str(MAX_REPEAT_OCCURRENCES) in over_limit.json()["detail"]

    assert db_session.query(Transaction).count() == 0
    assert db_session.query(RepeatSeriesBatch).count() == 0

    # 6b. Simulated mid-batch failure AFTER adding occurrences during commit
    with patch.object(type(db_session), "commit", side_effect=RuntimeError("Simulated disk I/O error")):
        failed_res = client.post(
            "/api/transactions/repeat",
            json={
                "transaction_type": "transfer",
                "amount": 100.00,
                "account_id": checking.id,
                "destination_account_id": savings.id,
                "frequency": "monthly",
                "first_date": "2026-06-01",
                "end_mode": "count",
                "occurrence_count": 4,
                "idempotency_key": "atomic-failure-001",
            },
        )
    assert failed_res.status_code == 500
    assert "no occurrences were created" in failed_res.json()["detail"].lower()

    db_session.expire_all()
    assert db_session.query(Transaction).count() == 0
    assert db_session.query(RepeatSeriesBatch).count() == 0
    assert LedgerEngine.get_account_balance(db_session, checking.id) == 100000
    assert LedgerEngine.get_account_balance(db_session, savings.id) == 50000


def test_7_retry_idempotency_conflict_race_and_distinct_submission(db_session, client):
    """
    Tests retry/double-submit protection:
    - Replaying same idempotency_key returns existing series (HTTP 200) with zero duplicates.
    - Reusing same idempotency_key with changed parameters raises 409 Conflict.
    - IntegrityError race on concurrent insert resolves to the committed winning batch cleanly.
    - Different idempotency_key creates an independent second series.
    """
    checking, _, cat_bills, _ = _setup_workspace(db_session)
    base_payload = {
        "transaction_type": "expense",
        "amount": 19.99,
        "merchant": "Streaming Plan",
        "account_id": checking.id,
        "category_id": cat_bills.id,
        "expense_nature": "fixed",
        "notes": "Shared plan",
        "frequency": "monthly",
        "first_date": "2026-01-15",
        "end_mode": "count",
        "occurrence_count": 3,
        "idempotency_key": "retry-series-key-001",
    }

    first_res = client.post("/api/transactions/repeat", json=base_payload)
    assert first_res.status_code == 201
    first_body = first_res.json()
    assert first_body["idempotent_replay"] is False
    assert first_body["created_count"] == 3
    first_ids = [item["id"] for item in first_body["items"]]

    # Simulated client retry after network timeout (both body key and header supported)
    retry_res = client.post(
        "/api/transactions/repeat",
        headers={"Idempotency-Key": "retry-series-key-001"},
        json=base_payload,
    )
    assert retry_res.status_code == 200
    retry_body = retry_res.json()
    assert retry_body["idempotent_replay"] is True
    assert retry_body["series_id"] == first_body["series_id"]
    assert [item["id"] for item in retry_body["items"]] == first_ids
    assert db_session.query(Transaction).count() == 3

    # Same key with different payload -> 409 Conflict
    altered_payload = {**base_payload, "amount": 29.99}
    conflict_res = client.post("/api/transactions/repeat", json=altered_payload)
    assert conflict_res.status_code == 409
    assert db_session.query(Transaction).count() == 3

    # Concurrent double-submit race simulation where initial pre-check missed and commit raises IntegrityError
    real_query = db_session.query

    race_bypassed = {"done": False}

    class _EmptyBatchRaceQuery:
        def filter(self, *args, **kwargs):
            return self

        def first(self):
            return None

    def query_with_race(model, *args, **kwargs):
        if model is RepeatSeriesBatch and not race_bypassed["done"]:
            race_bypassed["done"] = True
            return _EmptyBatchRaceQuery()
        return real_query(model, *args, **kwargs)

    with patch.object(db_session, "query", side_effect=query_with_race):
        race_res = client.post("/api/transactions/repeat", json=base_payload)

    assert race_res.status_code == 200
    race_body = race_res.json()
    assert race_body["idempotent_replay"] is True
    assert [item["id"] for item in race_body["items"]] == first_ids
    assert db_session.query(Transaction).count() == 3

    # Separate submission with new key succeeds independently
    second_payload = {**base_payload, "idempotency_key": "retry-series-key-002"}
    second_res = client.post("/api/transactions/repeat", json=second_payload)
    assert second_res.status_code == 201
    assert second_res.json()["series_id"] != first_body["series_id"]
    assert db_session.query(Transaction).count() == 6


def test_8_independent_lifecycle_ledger_analysis_exports_edit_delete_restore(db_session, client):
    """
    Each created occurrence works independently in Ledger, Analysis, CSV/XLSX exports,
    foreign-currency field copying, single-row editing, and bulk deletion/restore workflows.
    """
    checking, savings, cat_bills, _ = _setup_workspace(db_session, tz_name="Europe/London")
    app_tz = get_app_timezone(db_session)
    today = get_today_local(app_tz)

    # Create a 4-occurrence monthly foreign-currency expense crossing today (-1m, today, +1m, +2m)
    first_d = today - timedelta(days=30)
    res = client.post(
        "/api/transactions/repeat",
        json={
            "transaction_type": "expense",
            "amount": 40.00,
            "original_amount": 50.00,
            "original_currency": "USD",
            "merchant": "SaaS Membership",
            "account_id": checking.id,
            "category_id": cat_bills.id,
            "expense_nature": "fixed",
            "notes": "Quarterly team license",
            "frequency": "monthly",
            "first_date": first_d.isoformat(),
            "end_mode": "count",
            "occurrence_count": 4,
            "idempotency_key": "lifecycle-e2e-series-001",
        },
    )
    assert res.status_code == 201
    body = res.json()
    items = body["items"]
    assert len(items) == 4
    series_id = body["series_id"]

    # Every occurrence copies shared fields + foreign currency provenance and series_id provenance
    for item in items:
        assert item["merchant"] == "SaaS Membership"
        assert item["amount_pence"] == 4000
        assert item["original_currency"] == "USD"
        assert item["original_amount"] == 50.0
        assert item["exchange_rate"] == pytest.approx(0.8, rel=1e-6)
        assert item["category_id"] == cat_bills.id
        assert item["expense_nature"] == "fixed"
        assert item["notes"] == "Quarterly team license"
        assert item["repeat_series_id"] == series_id
        assert item["entry_method"] == "manual"

    # Export CSV and XLSX contain all 4 occurrences
    csv_res = client.get("/api/transactions/export?format=csv&sort_by=date&sort_order=asc")
    assert csv_res.status_code == 200
    csv_rows = list(csv.reader(io.StringIO(csv_res.content.decode("utf-8"))))
    merchant_rows = [r for r in csv_rows if "SaaS Membership" in r]
    assert len(merchant_rows) == 4

    xlsx_res = client.get("/api/transactions/export?format=xlsx&sort_by=date&sort_order=asc")
    assert xlsx_res.status_code == 200
    wb = openpyxl.load_workbook(io.BytesIO(xlsx_res.content))
    ws = wb.active
    xlsx_values = [row for row in ws.iter_rows(values_only=True) if any(cell == "SaaS Membership" for cell in row if cell)]
    assert len(xlsx_values) == 4

    # Edit only the 2nd occurrence -> siblings remain completely untouched
    target_id = items[1]["id"]
    edit_res = client.put(
        f"/api/transactions/{target_id}",
        json={"amount": 55.00, "merchant": "SaaS Membership Adjusted"},
    )
    assert edit_res.status_code == 200
    assert edit_res.json()["amount_pence"] == 5500
    assert edit_res.json()["merchant"] == "SaaS Membership Adjusted"

    sibling_res = client.get(f"/api/transactions/{items[0]['id']}").json()
    assert sibling_res["amount_pence"] == 4000
    assert sibling_res["merchant"] == "SaaS Membership"

    # Soft-delete only the 3rd occurrence and restore it safely
    delete_target_id = items[2]["id"]
    del_res = client.post("/api/transactions/bulk-delete", json={"transaction_ids": [delete_target_id]})
    assert del_res.status_code == 200
    assert del_res.json()["deleted_count"] == 1

    active_list = client.get("/api/transactions?limit=50").json()
    assert active_list["total"] == 3
    assert delete_target_id not in [x["id"] for x in active_list["items"]]

    restore_res = client.post("/api/transactions/restore", json={"transaction_ids": [delete_target_id]})
    assert restore_res.status_code == 200
    assert restore_res.json()["restored_count"] == 1

    restored_list = client.get("/api/transactions?limit=50").json()
    assert restored_list["total"] == 4

    # Repeat transfer creates independent transfer entries between valid base-currency accounts
    transfer_res = client.post(
        "/api/transactions/repeat",
        json={
            "transaction_type": "transfer",
            "amount": 100.00,
            "merchant": "Monthly Auto-Save",
            "account_id": checking.id,
            "destination_account_id": savings.id,
            "frequency": "monthly",
            "first_date": today.isoformat(),
            "end_mode": "count",
            "occurrence_count": 2,
            "idempotency_key": "transfer-repeat-001",
        },
    )
    assert transfer_res.status_code == 201
    t_items = transfer_res.json()["items"]
    assert len(t_items) == 2
    assert all(ti["destination_account_id"] == savings.id for ti in t_items)


def test_9_alembic_migration_and_sqlite_connect_upgrade(tmp_path):
    """
    Verifies both Alembic upgrade/downgrade and runtime SQLite connect hook add
    transactions.repeat_series_id and repeat_series_batches idempotently on isolated DBs.
    """
    import sqlalchemy as sa
    from alembic import command
    from alembic.config import Config
    from app.database import Base, configure_sqlite_engine

    # 1. Initialize baseline DB via metadata, remove repeat artifacts & stamp at a1b2c3d4e5f6
    db_file = tmp_path / "alembic_repeat.db"
    db_url = f"sqlite:///{db_file}"
    init_eng = sa.create_engine(db_url)
    Base.metadata.create_all(bind=init_eng)
    init_eng.dispose()

    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", db_url)
    command.stamp(cfg, "head")
    command.downgrade(cfg, "a1b2c3d4e5f6")

    eng = sa.create_engine(db_url)
    insp_before = sa.inspect(eng)
    assert "repeat_series_batches" not in insp_before.get_table_names()
    assert "repeat_series_id" not in [c["name"] for c in insp_before.get_columns("transactions")]
    eng.dispose()

    command.upgrade(cfg, "head")
    eng2 = sa.create_engine(db_url)
    insp_after = sa.inspect(eng2)
    assert "repeat_series_batches" in insp_after.get_table_names()
    assert "repeat_series_id" in [c["name"] for c in insp_after.get_columns("transactions")]
    with eng2.connect() as conn:
        assert conn.execute(sa.text("SELECT version_num FROM alembic_version")).scalar() in ("b2c3d4e5f6a7", "c3d4e5f6a7b9")
    eng2.dispose()

    command.downgrade(cfg, "a1b2c3d4e5f6")
    eng3 = sa.create_engine(db_url)
    insp_down = sa.inspect(eng3)
    assert "repeat_series_batches" not in insp_down.get_table_names()
    assert "repeat_series_id" not in [c["name"] for c in insp_down.get_columns("transactions")]
    eng3.dispose()

    # 2. Opening a pre-migration DB with configure_sqlite_engine upgrades safely on connect
    eng_rt = configure_sqlite_engine(db_url)
    with eng_rt.connect() as conn:
        cols = [r[1] for r in conn.execute(sa.text("PRAGMA table_info(transactions)")).fetchall()]
        tables = [r[0] for r in conn.execute(sa.text("SELECT name FROM sqlite_master WHERE type='table'")).fetchall()]
        assert "repeat_series_id" in cols
        assert "repeat_series_batches" in tables
    eng_rt.dispose()

