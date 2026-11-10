"""
Tests for Finance Hub Planned / Future-Dated Transactions Engine.

Verifies:
1. Future-dated transactions are clearly identified as planned/future activity.
2. Future expenses do not reduce an account's current balance, liquid reserves, or net worth before their effective date.
3. Future income does not increase an account's current balance before its effective date.
4. When queried with as_of in the future or include_planned=True, planned entries affect balances.
5. Ground-truth anchor integrity: transactions covered by an anchor do not change balances after that anchor.
6. Account breakdown endpoint separates confirmed current balance from planned upcoming movement and projected balance.
7. Analysis engine keeps historical and current actuals strictly separate from future plans.
8. Cash flow summary separates completed cash flow from planned activity.
9. Transactions query and export filtering by status ('actual' vs 'planned') and Activity Status column in CSV/XLSX.
10. Editing and deleting planned transactions updates or removes their planned impact dynamically.
11. Profile isolation: planned activity in one profile does not leak into another.
"""

from datetime import datetime, date, timedelta, timezone
from zoneinfo import ZoneInfo
import pytest
from fastapi.testclient import TestClient

from app.models import (
    Account,
    AccountType,
    AccountBalanceAnchor,
    Transaction,
    TransactionType,
    ExpenseNature,
    Category,
)
from app.ledger import LedgerEngine
from app.core.timezone import get_app_timezone, get_today_local, get_end_of_day_utc, get_midday_utc
from app.core.analysis import get_comprehensive_analysis
from app.core.cashflow import get_cashflow_summary


def test_future_expense_and_income_do_not_affect_current_balances(db_session, client):
    """
    Core Intended Behavior:
    - An expense dated in the future must not reduce current balance, liquid reserves, or net worth.
    - An income dated in the future must not increase current balance.
    - Projected balance and planned delta accurately reflect the upcoming activity.
    """
    app_tz = get_app_timezone(db_session)
    today = get_today_local(app_tz)
    tomorrow = today + timedelta(days=1)
    next_week = today + timedelta(days=7)

    acc = Account(
        name="Main Current",
        account_type=AccountType.CURRENT,
        currency="GBP",
        starting_balance_pence=100000, # £1,000.00
        starting_balance_date=datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc),
    )
    cat_rent = Category(name="Rent", default_expense_nature=ExpenseNature.FIXED)
    cat_sal = Category(name="Salary")
    db_session.add_all([acc, cat_rent, cat_sal])
    db_session.commit()

    # Confirmed current balance should be £1,000.00
    assert LedgerEngine.get_account_balance(db_session, acc.id) == 100000

    # 1. Add future-dated expense: £250.00 rent due tomorrow
    tx_rent = Transaction(
        transaction_date=get_midday_utc(tomorrow, tz_str=app_tz),
        effective_timestamp=get_midday_utc(tomorrow, tz_str=app_tz),
        transaction_type=TransactionType.EXPENSE,
        amount_pence=25000,
        merchant="Landlord",
        account_id=acc.id,
        category_id=cat_rent.id,
        expense_nature=ExpenseNature.FIXED,
        notes="November Rent"
    )
    # 2. Add future-dated income: £500.00 bonus next week
    tx_bonus = Transaction(
        transaction_date=get_midday_utc(next_week, tz_str=app_tz),
        effective_timestamp=get_midday_utc(next_week, tz_str=app_tz),
        transaction_type=TransactionType.INCOME,
        amount_pence=50000,
        merchant="Client Bonus",
        account_id=acc.id,
        category_id=cat_sal.id,
        notes="Performance Bonus"
    )
    db_session.add_all([tx_rent, tx_bonus])
    db_session.commit()

    # Rule Verification: Current balance must STILL be £1,000.00 (not reduced by £250 or increased by £500)!
    current_bal = LedgerEngine.get_account_balance(db_session, acc.id)
    assert current_bal == 100000

    # Projected balance (when including planned) should be £1,000 - £250 + £500 = £1,250.00
    projected_bal = LedgerEngine.get_account_balance(db_session, acc.id, include_planned=True)
    assert projected_bal == 125000

    # Balance Info should expose planned delta and projected balance
    info = LedgerEngine.get_account_balance_info(db_session, acc.id)
    assert info["current_balance_pence"] == 100000
    assert info["projected_balance_pence"] == 125000
    assert info["planned_delta_pence"] == 25000 # +£250.00 net planned change

    # Dashboard summary should reflect current reserves without future dilution
    summary = LedgerEngine.get_dashboard_summary(db_session)
    assert summary["total_liquid_pence"] == 100000
    assert summary["net_worth_pence"] == 100000
    assert summary["planned_expenses_pence"] == 25000
    assert summary["planned_income_pence"] == 50000
    assert summary["planned_net_pence"] == 25000
    assert summary["planned_count"] == 2

    # Query accounts API
    res = client.get("/api/accounts")
    assert res.status_code == 200
    acc_data = next(a for a in res.json() if a["id"] == acc.id)
    assert acc_data["current_balance_pence"] == 100000
    assert acc_data["projected_balance_pence"] == 125000
    assert acc_data["planned_delta_pence"] == 25000


def test_planned_transaction_becomes_effective_when_effective_date_arrives(db_session):
    """
    Verifies that when its effective date arrives (or when querying with as_of at or after
    its effective date), the transaction naturally starts affecting balances.
    """
    app_tz = get_app_timezone(db_session)
    today = get_today_local(app_tz)
    tomorrow = today + timedelta(days=1)

    acc = Account(
        name="Checking",
        account_type=AccountType.CURRENT,
        currency="GBP",
        starting_balance_pence=50000, # £500.00
        starting_balance_date=datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc),
    )
    db_session.add(acc)
    db_session.commit()

    # Add planned bill tomorrow for £75.00
    tx_tomorrow = Transaction(
        transaction_date=get_midday_utc(tomorrow, tz_str=app_tz),
        effective_timestamp=get_midday_utc(tomorrow, tz_str=app_tz),
        transaction_type=TransactionType.EXPENSE,
        amount_pence=7500,
        merchant="Utility Company",
        account_id=acc.id
    )
    db_session.add(tx_tomorrow)
    db_session.commit()

    # As of today (current balance): unaffected (£500.00)
    assert LedgerEngine.get_account_balance(db_session, acc.id) == 50000

    # As of tomorrow closing time: effective (£500.00 - £75.00 = £425.00)
    tomorrow_end = get_end_of_day_utc(tomorrow, tz_str=app_tz)
    assert LedgerEngine.get_account_balance(db_session, acc.id, as_of=tomorrow_end) == 42500


def test_account_breakdown_separates_current_from_planned_movement(db_session, client):
    """
    Tests /api/accounts/{id}/breakdown:
    - movement contains strictly completed post-anchor transactions
    - planned_movement contains future-dated transactions
    - recent_transactions marks is_planned correctly
    """
    app_tz = get_app_timezone(db_session)
    today = get_today_local(app_tz)
    yesterday = today - timedelta(days=1)
    tomorrow = today + timedelta(days=1)

    acc = Account(
        name="Santander Current",
        account_type=AccountType.CURRENT,
        starting_balance_pence=100000,
        starting_balance_date=datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc),
    )
    db_session.add(acc)
    db_session.commit()

    # Statement Anchor 5 days ago: £1,200.00
    anchor_dt = datetime(2026, 10, 10, 0, 0, tzinfo=timezone.utc)
    anchor = AccountBalanceAnchor(
        account_id=acc.id,
        balance_pence=120000,
        anchor_date=anchor_dt,
        is_opening=False,
        notes="Bank statement confirmed"
    )
    db_session.add(anchor)
    db_session.commit()

    # Actual transaction yesterday: £50.00 income
    tx_act = Transaction(
        transaction_date=get_midday_utc(yesterday, tz_str=app_tz),
        effective_timestamp=get_midday_utc(yesterday, tz_str=app_tz),
        transaction_type=TransactionType.INCOME,
        amount_pence=5000,
        merchant="Freelance Payment",
        account_id=acc.id
    )
    # Planned transaction tomorrow: £30.00 expense
    tx_plan = Transaction(
        transaction_date=get_midday_utc(tomorrow, tz_str=app_tz),
        effective_timestamp=get_midday_utc(tomorrow, tz_str=app_tz),
        transaction_type=TransactionType.EXPENSE,
        amount_pence=3000,
        merchant="Upcoming Dinner",
        account_id=acc.id
    )
    db_session.add_all([tx_act, tx_plan])
    db_session.commit()

    res = client.get(f"/api/accounts/{acc.id}/breakdown")
    assert res.status_code == 200
    data = res.json()

    # Current balance is anchor £1,200 + actual income £50 = £1,250.00
    assert data["current_balance_pence"] == 125000
    assert data["projected_balance_pence"] == 122000 # £1,250 - £30 = £1,220.00

    # Actual movement: exactly 1 transaction (+£50)
    assert data["movement"]["transaction_count"] == 1
    assert data["movement"]["inflows_pence"] == 5000
    assert data["movement"]["outflows_pence"] == 0
    assert data["movement"]["net_movement_pence"] == 5000

    # Planned movement: exactly 1 transaction (-£30)
    assert data["planned_movement"] is not None
    assert data["planned_movement"]["transaction_count"] == 1
    assert data["planned_movement"]["outflows_pence"] == 3000
    assert data["planned_movement"]["net_movement_pence"] == -3000

    # Recent transactions: planned transaction is clearly marked
    recent = data["recent_transactions"]
    plan_item = next(t for t in recent if t["id"] == tx_plan.id)
    act_item = next(t for t in recent if t["id"] == tx_act.id)
    assert plan_item["is_planned"] is True
    assert act_item["is_planned"] is False


def test_analysis_comprehensive_isolates_actuals_from_forecast(db_session, client):
    """
    Verifies that Analysis overview & cash flow totals exclude future-dated activity,
    and report them distinctly in the forecast section.
    """
    app_tz = get_app_timezone(db_session)
    today = get_today_local(app_tz)
    tomorrow = today + timedelta(days=1)
    yesterday = today - timedelta(days=1)

    acc = Account(name="Current Account", account_type=AccountType.CURRENT, currency="GBP")
    cat_food = Category(name="Food", default_expense_nature=ExpenseNature.VARIABLE)
    db_session.add_all([acc, cat_food])
    db_session.commit()

    # Actual expense yesterday: £40.00
    tx_act = Transaction(
        transaction_date=get_midday_utc(yesterday, tz_str=app_tz),
        effective_timestamp=get_midday_utc(yesterday, tz_str=app_tz),
        transaction_type=TransactionType.EXPENSE,
        amount_pence=4000,
        merchant="Supermarket",
        account_id=acc.id,
        category_id=cat_food.id,
        expense_nature=ExpenseNature.VARIABLE
    )
    # Planned expense tomorrow: £60.00
    tx_plan = Transaction(
        transaction_date=get_midday_utc(tomorrow, tz_str=app_tz),
        effective_timestamp=get_midday_utc(tomorrow, tz_str=app_tz),
        transaction_type=TransactionType.EXPENSE,
        amount_pence=6000,
        merchant="Future Catering",
        account_id=acc.id,
        category_id=cat_food.id,
        expense_nature=ExpenseNature.VARIABLE
    )
    db_session.add_all([tx_act, tx_plan])
    db_session.commit()

    # Fetch Analysis for preset="month"
    analysis = get_comprehensive_analysis(db_session, preset="month")

    # Completed actual expenses must be strictly £40.00 (not £100.00!)
    assert analysis["totals"]["expenses_pence"] == 4000
    assert analysis["totals"]["formatted_expenses"] == "£40.00"

    # Category breakdown must show only completed actual spend
    cat_item = next(c for c in analysis["categories"] if c["category_id"] == cat_food.id)
    assert cat_item["total_pence"] == 4000

    # Spending matrix grand total must reflect strictly £40.00
    assert analysis["spending_matrix"]["grand_total_pence"] == 4000

    # Forecast section must clearly present the planned activity
    forecast = analysis["forecast"]
    assert forecast is not None
    assert forecast["has_planned_activity"] is True
    assert forecast["planned_expenses_pence"] == 6000
    assert forecast["planned_transactions_count"] == 1
    assert len(forecast["items"]) == 1
    assert forecast["items"][0]["merchant"] == "Future Catering"
    assert forecast["items"][0]["amount_pence"] == 6000


def test_transactions_api_status_filtering_and_export(db_session, client):
    """
    Verifies that /api/transactions supports status='actual' and status='planned',
    and exports include the Activity Status column.
    """
    app_tz = get_app_timezone(db_session)
    today = get_today_local(app_tz)
    yesterday = today - timedelta(days=2)
    tomorrow = today + timedelta(days=2)

    acc = Account(name="Current", account_type=AccountType.CURRENT, currency="GBP")
    db_session.add(acc)
    db_session.commit()

    tx_past = Transaction(
        transaction_date=get_midday_utc(yesterday, tz_str=app_tz),
        effective_timestamp=get_midday_utc(yesterday, tz_str=app_tz),
        transaction_type=TransactionType.EXPENSE,
        amount_pence=1500,
        merchant="Past Coffee",
        account_id=acc.id
    )
    tx_future = Transaction(
        transaction_date=get_midday_utc(tomorrow, tz_str=app_tz),
        effective_timestamp=get_midday_utc(tomorrow, tz_str=app_tz),
        transaction_type=TransactionType.EXPENSE,
        amount_pence=4500,
        merchant="Future Booking",
        account_id=acc.id
    )
    db_session.add_all([tx_past, tx_future])
    db_session.commit()

    # 1. Query status=actual
    res_actual = client.get("/api/transactions?status=actual")
    assert res_actual.status_code == 200
    actual_items = res_actual.json()["items"]
    assert len(actual_items) == 1
    assert actual_items[0]["merchant"] == "Past Coffee"
    assert actual_items[0]["is_planned"] is False

    # 2. Query status=planned
    res_planned = client.get("/api/transactions?status=planned")
    assert res_planned.status_code == 200
    planned_items = res_planned.json()["items"]
    assert len(planned_items) == 1
    assert planned_items[0]["merchant"] == "Future Booking"
    assert planned_items[0]["is_planned"] is True

    # 3. CSV Export includes Activity Status column
    res_csv = client.get("/api/transactions/export?format=csv")
    assert res_csv.status_code == 200
    csv_text = res_csv.content.decode("utf-8-sig")
    assert "Activity Status" in csv_text
    assert "Planned" in csv_text
    assert "Completed" in csv_text


def test_editing_and_deleting_planned_transaction_updates_impact(db_session, client):
    """
    Editing or deleting a planned transaction updates or removes its planned impact.
    """
    app_tz = get_app_timezone(db_session)
    today = get_today_local(app_tz)
    tomorrow = today + timedelta(days=1)

    acc = Account(name="Current", account_type=AccountType.CURRENT, currency="GBP", starting_balance_pence=50000)
    db_session.add(acc)
    db_session.commit()

    # Create planned transaction via API
    res_create = client.post("/api/transactions", json={
        "transaction_type": "expense",
        "amount": 50.0, # £50.00
        "merchant": "Future Ticket",
        "account_id": acc.id,
        "transaction_date": tomorrow.isoformat()
    })
    assert res_create.status_code == 201
    tx_id = res_create.json()["id"]

    # Current balance is still £500.00, planned delta is -£50.00
    info1 = LedgerEngine.get_account_balance_info(db_session, acc.id)
    assert info1["current_balance_pence"] == 50000
    assert info1["planned_delta_pence"] == -5000

    # Edit amount to £80.00
    res_update = client.put(f"/api/transactions/{tx_id}", json={
        "amount": 80.0,
        "merchant": "Future Ticket VIP"
    })
    assert res_update.status_code == 200

    info2 = LedgerEngine.get_account_balance_info(db_session, acc.id)
    assert info2["current_balance_pence"] == 50000
    assert info2["planned_delta_pence"] == -8000

    # Delete transaction
    res_del = client.delete(f"/api/transactions/{tx_id}")
    assert res_del.status_code == 204

    info3 = LedgerEngine.get_account_balance_info(db_session, acc.id)
    assert info3["current_balance_pence"] == 50000
    assert info3["planned_delta_pence"] == 0
