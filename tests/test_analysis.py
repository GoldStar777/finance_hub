import pytest
from datetime import datetime, date, time, timedelta, timezone
from zoneinfo import ZoneInfo
from decimal import Decimal

from app.models import (
    Account,
    AccountType,
    Category,
    Transaction,
    TransactionType,
    ExpenseNature,
    AccountBalanceAnchor,
    AccountSnapshot,
    Holding,
    HoldingValuation,
    SystemSetting,
)
from app.core.analysis import (
    resolve_date_range,
    generate_intervals,
    compute_cashflow_and_spending,
    compute_balances_and_net_worth,
    compute_portfolio_value_history,
    get_comprehensive_analysis,
    VALID_PRESETS,
    VALID_INTERVALS,
)
from app.core.timezone import get_app_timezone

def test_date_range_presets_and_interval_resolution(db_session):
    """
    Verifies that date range presets resolve correctly in application timezone:
    - Weeks start on Monday and end on Sunday.
    - Months start on 1st and end on last day.
    - Partial periods are clearly flagged and labeled.
    """
    tz_str = get_app_timezone(db_session)
    tz = ZoneInfo(tz_str)
    today = datetime.now(tz).date()

    # 1. Week preset (Monday to Sunday)
    preset, start_d, end_d, s_utc, e_utc, tz_res, offset, can_prev, can_next = resolve_date_range(db_session, preset="week")
    assert preset == "week"
    assert start_d.weekday() == 0  # Monday
    assert end_d.weekday() == 6    # Sunday
    assert (end_d - start_d).days == 6

    # 2. Month preset
    preset, start_d, end_d, _, _, _, _, _, _ = resolve_date_range(db_session, preset="month")
    assert preset == "month"
    assert start_d.day == 1

    # 3. Custom range
    preset, start_d, end_d, _, _, _, _, _, _ = resolve_date_range(
        db_session, preset="custom", custom_start="2026-05-01", custom_end="2026-05-15"
    )
    assert preset == "custom"
    assert start_d == date(2026, 5, 1)
    assert end_d == date(2026, 5, 15)

    # 4. Bucketing by week
    buckets = generate_intervals(date(2026, 10, 5), date(2026, 10, 25), "week", tz)
    assert len(buckets) == 3
    for b in buckets:
        b_start = date.fromisoformat(b["start_date"])
        b_end = date.fromisoformat(b["end_date"])
        assert b_start <= b_end
        assert b_start.weekday() == 0
        assert b_end.weekday() == 6

def test_cashflow_totals_and_transfer_exclusions(db_session):
    """
    Verifies that:
    - Internal transfers between accounts contribute strictly £0 to income and expenses.
    - Operating income and expenses are summed.
    - Reconciliation adjustments are separated from operating surplus.
    """
    acc_cur = Account(name="Current Account", account_type=AccountType.CURRENT, currency="GBP", starting_balance_pence=100000)
    acc_sav = Account(name="Savings Account", account_type=AccountType.SAVINGS, currency="GBP", starting_balance_pence=50000)
    cat_food = Category(name="Food", default_expense_nature=ExpenseNature.VARIABLE)
    db_session.add_all([acc_cur, acc_sav, cat_food])
    db_session.commit()

    d1 = datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc)
    d2 = datetime(2026, 10, 10, 14, 0, tzinfo=timezone.utc)
    d3 = datetime(2026, 10, 15, 9, 0, tzinfo=timezone.utc)

    # 1. Salary (£2,000)
    tx_salary = Transaction(
        transaction_date=d1,
        transaction_type=TransactionType.INCOME,
        amount_pence=200000,
        merchant="Employer",
        account_id=acc_cur.id
    )

    # 2. Food expense (£50)
    tx_food = Transaction(
        transaction_date=d2,
        transaction_type=TransactionType.EXPENSE,
        amount_pence=5000,
        merchant="Supermarket",
        account_id=acc_cur.id,
        category_id=cat_food.id,
        expense_nature=ExpenseNature.VARIABLE
    )

    # 3. Internal transfer to savings (£500) - MUST NOT BE EXPENSE OR INCOME!
    tx_transfer = Transaction(
        transaction_date=d3,
        transaction_type=TransactionType.TRANSFER,
        amount_pence=50000,
        merchant="Transfer to Savings",
        account_id=acc_cur.id,
        destination_account_id=acc_sav.id
    )

    # 4. Reconciliation adjustment (+£10 credit)
    tx_adj = Transaction(
        transaction_date=d3,
        transaction_type=TransactionType.ADJUSTMENT,
        amount_pence=1000,
        notes="[Positive adjustment] Interest correction",
        account_id=acc_cur.id
    )

    db_session.add_all([tx_salary, tx_food, tx_transfer, tx_adj])
    db_session.commit()

    buckets = generate_intervals(date(2026, 10, 1), date(2026, 10, 31), "month", ZoneInfo("Europe/London"))
    totals, time_series, categories, matrix = compute_cashflow_and_spending(db_session, buckets, "GBP")

    assert totals["income_pence"] == 200000
    assert totals["expenses_pence"] == 5000
    assert totals["net_savings_pence"] == 195000
    assert totals["cumulative_income_pence"] == 200000
    assert totals["cumulative_expenses_pence"] == 5000
    assert totals["cumulative_net_flow_pence"] == 195000
    assert totals["transfers_volume_pence"] == 50000
    assert totals["transfers_count"] == 1
    assert totals["adjustments_inflow_pence"] == 1000
    assert totals["adjustments_net_pence"] == 1000

    # Category breakdown and matrix
    assert len(categories) == 1
    assert categories[0]["category_name"] == "Food"
    assert categories[0]["total_pence"] == 5000
    assert matrix["grand_total_pence"] == 5000
    assert len(matrix["rows"]) == 1
    assert matrix["rows"][0]["category_name"] == "Food"
    assert matrix["rows"][0]["row_total_pence"] == 5000
    assert matrix["rows"][0]["cells"]["2026-10"]["amount_pence"] == 5000
    assert categories[0]["percentage"] == 100.0

def test_balance_anchor_inference_prior_to_earliest_anchor(db_session):
    """
    Verifies that before an account's earliest anchor:
    - Balances are computed via retrospective inference from reverse transactions.
    - is_inferred is True with clear advisory warning.
    - Never presented as verified.
    """
    # Create opening balance anchor as of 2026-10-15: £1,000 (100,000 pence)
    anchor_dt = datetime(2026, 10, 15, 0, 0, tzinfo=timezone.utc)
    acc = Account(
        name="Bank Account",
        account_type=AccountType.CURRENT,
        currency="GBP",
        starting_balance_pence=100000,
        starting_balance_date=anchor_dt
    )
    db_session.add(acc)
    db_session.commit()

    # Pre-anchor transaction on 2026-10-14: £200 expense (between as_of 12th and anchor 15th)
    tx_pre = Transaction(
        transaction_date=datetime(2026, 10, 14, 12, 0, tzinfo=timezone.utc),
        transaction_type=TransactionType.EXPENSE,
        amount_pence=20000,
        account_id=acc.id
    )
    # Post-anchor transaction on 2026-10-20: £100 expense
    tx_post = Transaction(
        transaction_date=datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc),
        transaction_type=TransactionType.EXPENSE,
        amount_pence=10000,
        account_id=acc.id
    )
    db_session.add_all([tx_pre, tx_post])
    db_session.commit()

    # Bucket 1: 2026-10-01 to 2026-10-12 (Prior to anchor)
    # Bucket 2: 2026-10-16 to 2026-10-25 (After anchor)
    b1 = {
        "key": "b1",
        "label": "Early Oct",
        "end_date": "2026-10-12",
        "is_partial": False,
        "partial_label": None,
        "as_of_utc": datetime(2026, 10, 12, 23, 59, 59, tzinfo=timezone.utc)
    }
    b2 = {
        "key": "b2",
        "label": "Late Oct",
        "end_date": "2026-10-25",
        "is_partial": False,
        "partial_label": None,
        "as_of_utc": datetime(2026, 10, 25, 23, 59, 59, tzinfo=timezone.utc)
    }

    nw_buckets = compute_balances_and_net_worth(db_session, [b1, b2], "GBP")
    assert len(nw_buckets) == 2

    # In early Oct (prior to anchor), balance is inferred (anchor 100,000 + 20,000 = 120,000)
    b1_acc = nw_buckets[0]["account_balances"][0]
    assert b1_acc["is_inferred"] is True
    assert "inferred" in b1_acc["inferred_warning"].lower()
    assert b1_acc["balance_pence"] == 120000
    assert nw_buckets[0]["has_inferred_balances"] is True

    # In late Oct (after anchor), balance is verified (anchor 100,000 - 10,000 = 90,000)
    b2_acc = nw_buckets[1]["account_balances"][0]
    assert b2_acc["is_inferred"] is False
    assert b2_acc["inferred_warning"] is None
    assert b2_acc["balance_pence"] == 90000

def test_reconciliation_discrepancy_reported_without_ledger_distortion(db_session):
    """
    Verifies that reconciliation snapshots:
    - Report discrepancy between actual and calculated balance.
    - Do NOT alter ledger balance or invent adjustments.
    """
    acc = Account(
        name="Credit Card",
        account_type=AccountType.CREDIT_CARD,
        currency="GBP",
        starting_balance_pence=5000,
        starting_balance_date=datetime(2026, 10, 1, 0, 0, tzinfo=timezone.utc)
    )
    db_session.add(acc)
    db_session.commit()

    # User recorded observational snapshot on 2026-10-15 with actual balance £45 (£5 discrepancy)
    snap = AccountSnapshot(
        account_id=acc.id,
        snapshot_date=datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc),
        actual_balance_pence=4500,
        calculated_balance_pence=5000,
        discrepancy_pence=-500,
        notes="Observational bank statement check"
    )
    db_session.add(snap)
    db_session.commit()

    b = {
        "key": "oct",
        "label": "Oct 2026",
        "end_date": "2026-10-31",
        "is_partial": False,
        "partial_label": None,
        "as_of_utc": datetime(2026, 10, 31, 23, 59, 59, tzinfo=timezone.utc)
    }

    nw = compute_balances_and_net_worth(db_session, [b], "GBP")
    acc_res = nw[0]["account_balances"][0]

    # Ledger balance remains 5000
    assert acc_res["balance_pence"] == 5000
    # Reconciliation snapshot discrepancy is reported
    assert acc_res["reconciliation_discrepancy_pence"] == -500
    assert acc_res["reconciliation_actual_pence"] == 4500

def test_sparse_holding_valuation_history(db_session):
    """
    Verifies portfolio valuation trajectory:
    - Values are carried forward from latest valuation on or before period end.
    - Sparse checkpoints are detected and explained.
    """
    inv_acc = Account(name="SIPP Pension", account_type=AccountType.INVESTMENT, currency="GBP", starting_balance_pence=0)
    db_session.add(inv_acc)
    db_session.commit()

    h = Holding(name="Vanguard All-Cap", ticker="VAFTGAG", account_id=inv_acc.id)
    db_session.add(h)
    db_session.commit()

    # Single valuation checkpoint on 2026-09-01: £15,000 (1,500,000 pence)
    val = HoldingValuation(
        holding_id=h.id,
        effective_date=datetime(2026, 9, 1, 10, 0, tzinfo=timezone.utc),
        quantity=Decimal("100"),
        unit_price_pence=Decimal("15000"),
        valuation_pence=1500000
    )
    db_session.add(val)
    db_session.commit()

    # Buckets across 6 months
    buckets = generate_intervals(date(2026, 5, 1), date(2026, 10, 31), "month", ZoneInfo("Europe/London"))
    series, is_sparse, explanation = compute_portfolio_value_history(db_session, buckets, "GBP")

    assert is_sparse is True
    assert "infrequent or sparse" in explanation.lower()

    # Buckets before Sept 2026 (May, Jun, Jul, Aug) have unavailable valuation (no checkpoints on or before end)
    assert series[0]["is_available"] is False
    assert series[0]["total_valuation_pence"] is None
    assert series[0]["formatted_total_valuation"] == "Unavailable"
    assert series[0]["accounts"][0]["is_available"] is False
    assert series[0]["accounts"][0]["formatted_valuation"] == "Unavailable"

    # Buckets from Sept onwards have valuation of £15,000
    sept_bucket = next(s for s in series if s["key"] == "2026-09")
    oct_bucket = next(s for s in series if s["key"] == "2026-10")
    
    # September: Checkpoint was inside this period, so is_available is True and is_carried_forward is False
    assert sept_bucket["is_available"] is True
    assert sept_bucket["is_carried_forward"] is False
    assert sept_bucket["total_valuation_pence"] == 1500000
    assert sept_bucket["valuation_date"] == "01/09/2026"
    assert sept_bucket["accounts"][0]["is_carried_forward"] is False

    # October: Checkpoint was on 01/09/2026 (< 01/10/2026), so is_available is True and is_carried_forward is True
    assert oct_bucket["is_available"] is True
    assert oct_bucket["is_carried_forward"] is True
    assert oct_bucket["carried_forward_date"] == "01/09/2026"
    assert oct_bucket["total_valuation_pence"] == 1500000
    assert oct_bucket["accounts"][0]["is_carried_forward"] is True
    assert oct_bucket["accounts"][0]["carried_forward_date"] == "01/09/2026"

def test_cumulative_net_savings_across_multiple_periods_and_filters(db_session):
    """
    Verifies that running cumulative net savings:
    - Accumulates income minus expenses strictly across the selected range.
    - Preserves previous sum across empty intervals without interpolating or distorting.
    - Excludes internal transfers entirely.
    - Keeps reconciliation adjustments separate from operating cash flow.
    - Respects account and category filters accurately.
    """
    acc_main = Account(name="Main Checking", account_type=AccountType.CURRENT, currency="GBP", starting_balance_pence=100000)
    acc_aux = Account(name="Aux Savings", account_type=AccountType.SAVINGS, currency="GBP", starting_balance_pence=50000)
    cat_salary = Category(name="Income/Salary", default_expense_nature=ExpenseNature.VARIABLE)
    cat_groceries = Category(name="Groceries", default_expense_nature=ExpenseNature.VARIABLE)
    cat_bills = Category(name="Utilities", default_expense_nature=ExpenseNature.FIXED)
    db_session.add_all([acc_main, acc_aux, cat_salary, cat_groceries, cat_bills])
    db_session.commit()

    # Buckets: July, August, September, October 2026
    buckets = generate_intervals(date(2026, 7, 1), date(2026, 10, 31), "month", ZoneInfo("Europe/London"))
    assert len(buckets) == 4

    # 1. July: Income £3,000 on main, Groceries £1,000 on main
    # Net: +£2,000 -> Cumulative: £2,000
    db_session.add_all([
        Transaction(
            transaction_date=datetime(2026, 7, 10, 10, 0, tzinfo=timezone.utc),
            transaction_type=TransactionType.INCOME,
            amount_pence=300000,
            account_id=acc_main.id,
            category_id=cat_salary.id
        ),
        Transaction(
            transaction_date=datetime(2026, 7, 15, 12, 0, tzinfo=timezone.utc),
            transaction_type=TransactionType.EXPENSE,
            amount_pence=100000,
            account_id=acc_main.id,
            category_id=cat_groceries.id,
            expense_nature=ExpenseNature.VARIABLE
        )
    ])

    # 2. August: EMPTY PERIOD (no transactions at all)
    # Net: £0 -> Cumulative: £2,000 (must remain flat)

    # 3. September: Income £1,000 on main, Bills £1,500 on main
    # Net: -£500 -> Cumulative: £1,500
    db_session.add_all([
        Transaction(
            transaction_date=datetime(2026, 9, 5, 10, 0, tzinfo=timezone.utc),
            transaction_type=TransactionType.INCOME,
            amount_pence=100000,
            account_id=acc_main.id,
            category_id=cat_salary.id
        ),
        Transaction(
            transaction_date=datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc),
            transaction_type=TransactionType.EXPENSE,
            amount_pence=150000,
            account_id=acc_main.id,
            category_id=cat_bills.id,
            expense_nature=ExpenseNature.FIXED
        )
    ])

    # 4. October:
    # - Internal transfer £500 (must be 0 impact)
    # - Positive reconciliation adjustment £50 (must be separate from operating cash flow)
    # Net: £0 -> Cumulative: £1,500
    db_session.add_all([
        Transaction(
            transaction_date=datetime(2026, 10, 5, 10, 0, tzinfo=timezone.utc),
            transaction_type=TransactionType.TRANSFER,
            amount_pence=50000,
            account_id=acc_main.id,
            destination_account_id=acc_aux.id
        ),
        Transaction(
            transaction_date=datetime(2026, 10, 15, 10, 0, tzinfo=timezone.utc),
            transaction_type=TransactionType.ADJUSTMENT,
            amount_pence=5000,
            notes="[Positive adjustment] Reconciliation bonus",
            account_id=acc_main.id
        )
    ])
    db_session.commit()

    # Test unfiltered multi-period cumulative savings
    totals, series, _, matrix = compute_cashflow_and_spending(db_session, buckets, "GBP")

    # Bucket 0 (July): +£2,000 (Income £3,000, Expense £1,000)
    assert series[0]["income_pence"] == 300000
    assert series[0]["expenses_pence"] == 100000
    assert series[0]["net_savings_pence"] == 200000
    assert series[0]["cumulative_income_pence"] == 300000
    assert series[0]["cumulative_expenses_pence"] == 100000
    assert series[0]["cumulative_net_flow_pence"] == 200000
    assert series[0]["cumulative_net_savings_pence"] == 200000

    # Bucket 1 (August - Empty period): £0 net, cumulative curves remain flat
    assert series[1]["income_pence"] == 0
    assert series[1]["expenses_pence"] == 0
    assert series[1]["net_savings_pence"] == 0
    assert series[1]["cumulative_income_pence"] == 300000
    assert series[1]["cumulative_expenses_pence"] == 100000
    assert series[1]["cumulative_net_flow_pence"] == 200000
    assert series[1]["cumulative_net_savings_pence"] == 200000

    # Bucket 2 (September): Income £1,000, Expense £1,500 -> Net -£500
    # Cumulative: Income £4,000, Expenses £2,500, Net Flow £1,500
    assert series[2]["income_pence"] == 100000
    assert series[2]["expenses_pence"] == 150000
    assert series[2]["net_savings_pence"] == -50000
    assert series[2]["cumulative_income_pence"] == 400000
    assert series[2]["cumulative_expenses_pence"] == 250000
    assert series[2]["cumulative_net_flow_pence"] == 150000
    assert series[2]["cumulative_net_savings_pence"] == 150000

    # Bucket 3 (October): transfer & adjustment excluded from operating surplus -> net £0
    # Cumulative curves remain flat: Income £4,000, Expenses £2,500, Net Flow £1,500
    assert series[3]["transfers_volume_pence"] == 50000
    assert series[3]["adjustments_net_pence"] == 5000
    assert series[3]["income_pence"] == 0
    assert series[3]["expenses_pence"] == 0
    assert series[3]["net_savings_pence"] == 0
    assert series[3]["cumulative_income_pence"] == 400000
    assert series[3]["cumulative_expenses_pence"] == 250000
    assert series[3]["cumulative_net_flow_pence"] == 150000
    assert series[3]["cumulative_net_savings_pence"] == 150000

    # Totals across range
    assert totals["income_pence"] == 400000
    assert totals["expenses_pence"] == 250000
    assert totals["net_savings_pence"] == 150000
    assert totals["cumulative_income_pence"] == 400000
    assert totals["cumulative_expenses_pence"] == 250000
    assert totals["cumulative_net_flow_pence"] == 150000
    assert totals["cumulative_net_savings_pence"] == 150000

    # Test Matrix: 4 periods, 2 categories (Groceries £1,000, Utilities £1,500)
    assert len(matrix["periods"]) == 4
    assert matrix["grand_total_pence"] == 250000
    assert len(matrix["rows"]) == 2
    # Groceries row: July £1,000, August £0, September £0, October £0 -> row total £1,000
    groceries_row = next(r for r in matrix["rows"] if r["category_name"] == "Groceries")
    assert groceries_row["row_total_pence"] == 100000
    assert groceries_row["cells"]["2026-07"]["amount_pence"] == 100000
    assert groceries_row["cells"]["2026-08"]["amount_pence"] == 0
    assert groceries_row["cells"]["2026-09"]["amount_pence"] == 0
    assert groceries_row["cells"]["2026-10"]["amount_pence"] == 0

    # Utilities row: July £0, August £0, September £1,500, October £0 -> row total £1,500
    utils_row = next(r for r in matrix["rows"] if r["category_name"] == "Utilities")
    assert utils_row["row_total_pence"] == 150000
    assert utils_row["cells"]["2026-07"]["amount_pence"] == 0
    assert utils_row["cells"]["2026-09"]["amount_pence"] == 150000

    # Period column totals: July £1,000, August £0, September £1,500, October £0
    assert matrix["periods"][0]["period_total_pence"] == 100000
    assert matrix["periods"][1]["period_total_pence"] == 0
    assert matrix["periods"][2]["period_total_pence"] == 150000
    assert matrix["periods"][3]["period_total_pence"] == 0

    # Test filtering by Category (e.g. Groceries only)
    tot_groceries, series_groceries, _, matrix_groceries = compute_cashflow_and_spending(
        db_session, buckets, "GBP", category_id=cat_groceries.id
    )
    # Groceries: only £1,000 expense in July, zero in other buckets
    assert series_groceries[0]["cumulative_net_savings_pence"] == -100000
    assert series_groceries[1]["cumulative_net_savings_pence"] == -100000
    assert series_groceries[2]["cumulative_net_savings_pence"] == -100000
    assert series_groceries[3]["cumulative_net_savings_pence"] == -100000
    assert tot_groceries["cumulative_net_savings_pence"] == -100000

    # Test filtering by Category (Salary only)
    tot_sal, series_sal, _, _ = compute_cashflow_and_spending(
        db_session, buckets, "GBP", category_id=cat_salary.id
    )
    assert series_sal[0]["cumulative_net_savings_pence"] == 300000
    assert series_sal[1]["cumulative_net_savings_pence"] == 300000
    assert series_sal[2]["cumulative_net_savings_pence"] == 400000
    assert series_sal[3]["cumulative_net_savings_pence"] == 400000
    assert tot_sal["cumulative_net_savings_pence"] == 400000

def test_comprehensive_analysis_api_contract(db_session, client):
    """
    Verifies that the /api/analytics/analysis endpoint returns the complete structure
    with all 5 sections (Overview, Cash Flow, Spending, Balances & Net Worth, Investments),
    plus the primary Spending Matrix.
    """
    acc = Account(name="Current", account_type=AccountType.CURRENT, currency="GBP", starting_balance_pence=50000)
    db_session.add(acc)
    db_session.commit()

    res = client.get("/api/analytics/analysis?preset=month")
    assert res.status_code == 200
    data = res.json()

    assert "range_info" in data
    assert "totals" in data
    assert "time_series" in data
    assert "categories" in data
    assert "spending_matrix" in data
    assert "net_worth_series" in data
    assert "investments_series" in data
    assert data["range_info"]["preset"] == "month"
    assert "offset" in data["range_info"]
    assert "can_navigate_previous" in data["range_info"]
    assert "can_navigate_next" in data["range_info"]

def test_period_navigation_offsets_and_future_cutoff(db_session, client):
    """
    Verifies that:
    - Period navigation shifts range by the window duration.
    - Future dates cannot be navigated to: Next is disabled and clamped at current date.
    - All time cannot navigate forward or backward.
    """
    tz_str = get_app_timezone(db_session)
    tz = ZoneInfo(tz_str)
    today = datetime.now(tz).date()

    # 1. Month preset: offset 0 (current month) -> can_navigate_next must be False
    _, start_0, end_0, _, _, _, off_0, prev_0, next_0 = resolve_date_range(db_session, preset="month", offset=0)
    assert off_0 == 0
    assert start_0.year == today.year and start_0.month == today.month
    assert prev_0 is True
    assert next_0 is False

    # 2. Month preset: offset -1 (previous month) -> can_navigate_next must be True
    _, start_prev, end_prev, _, _, _, off_prev, prev_p, next_p = resolve_date_range(db_session, preset="month", offset=-1)
    assert off_prev == -1
    # Check that previous month is exactly 1 month prior
    assert end_prev < start_0
    assert prev_p is True
    assert next_p is True

    # 3. Future attempt: offset +1 should clamp to 0 and disable next
    _, start_fut, end_fut, _, _, _, off_fut, _, next_fut = resolve_date_range(db_session, preset="month", offset=1)
    assert off_fut == 0
    assert next_fut is False

    # 4. All time: cannot navigate forward or backward
    _, _, _, _, _, _, off_all, prev_all, next_all = resolve_date_range(db_session, preset="all", offset=0)
    assert off_all == 0
    assert prev_all is False
    assert next_all is False

    # 5. API endpoint honors offset parameter
    acc = Account(name="Test Checking", account_type=AccountType.CURRENT, currency="GBP", starting_balance_pence=10000)
    db_session.add(acc)
    db_session.commit()

    res = client.get("/api/analytics/analysis?preset=month&offset=-1")
    assert res.status_code == 200
    data = res.json()
    assert data["range_info"]["offset"] == -1
    assert data["range_info"]["can_navigate_next"] is True

def test_category_colors_and_stable_palette(db_session):
    """
    Verifies that:
    - Custom category colors configured on categories are strictly preserved.
    - Categories without a custom color receive distinct, stable colors from the palette.
    - Active categories pass resolved colors to the frontend.
    """
    cat_custom = Category(name="Gym & Fitness", color="#00F2F9", default_expense_nature=ExpenseNature.VARIABLE)
    cat_default = Category(name="Sundries", color=None, default_expense_nature=ExpenseNature.VARIABLE)
    db_session.add_all([cat_custom, cat_default])
    db_session.commit()

    res = get_comprehensive_analysis(db_session, preset="month")
    cats = res["available_categories"]

    gym_cat = next(c for c in cats if c["name"] == "Gym & Fitness")
    sundries_cat = next(c for c in cats if c["name"] == "Sundries")

    # Custom color preserved
    assert gym_cat["color"] == "#00F2F9"
    # Unconfigured category assigned a stable palette color, not None or uniform fallback
    assert sundries_cat["color"] is not None
    assert sundries_cat["color"].startswith("#")
    assert sundries_cat["color"] != "#8B5CF6" or gym_cat["color"] != sundries_cat["color"]

def test_bucket_category_and_nature_breakdowns(db_session, client):
    """
    Verifies that time_series buckets contain detailed category breakdowns
    (category_spending_details) and nature breakdowns (nature_spending_details)
    for stacked bar rendering and multi-series line charts.
    """
    acc = Account(name="Current Account", account_type=AccountType.CURRENT, currency="GBP", starting_balance_pence=100000)
    cat_fixed = Category(name="Rent", color="#10B981", default_expense_nature=ExpenseNature.FIXED)
    cat_var = Category(name="Dining", color="#F59E0B", default_expense_nature=ExpenseNature.VARIABLE)
    db_session.add_all([acc, cat_fixed, cat_var])
    db_session.commit()

    d = datetime.now(timezone.utc)
    tx1 = Transaction(
        transaction_date=d,
        transaction_type=TransactionType.EXPENSE,
        amount_pence=80000,
        merchant="Landlord",
        account_id=acc.id,
        category_id=cat_fixed.id,
        expense_nature=ExpenseNature.FIXED
    )
    tx2 = Transaction(
        transaction_date=d,
        transaction_type=TransactionType.EXPENSE,
        amount_pence=20000,
        merchant="Bistro",
        account_id=acc.id,
        category_id=cat_var.id,
        expense_nature=ExpenseNature.VARIABLE
    )
    db_session.add_all([tx1, tx2])
    db_session.commit()

    res = client.get("/api/analytics/analysis?preset=month")
    assert res.status_code == 200
    data = res.json()
    assert len(data["time_series"]) > 0

    # Find the bucket containing today
    active_buckets = [b for b in data["time_series"] if b["expenses_pence"] > 0]
    assert len(active_buckets) > 0
    bucket = active_buckets[0]

    assert "category_spending_details" in bucket
    assert "nature_spending_details" in bucket
    assert len(bucket["category_spending_details"]) >= 2
    
    # Check category details
    cat_details = {c["category_name"]: c for c in bucket["category_spending_details"]}
    assert "Rent" in cat_details
    assert cat_details["Rent"]["amount_pence"] == 80000
    assert cat_details["Rent"]["percentage"] == 80.0
    assert cat_details["Rent"]["category_color"] == "#10B981"
    assert cat_details["Rent"]["transaction_count"] == 1

    assert "Dining" in cat_details
    assert cat_details["Dining"]["amount_pence"] == 20000
    assert cat_details["Dining"]["percentage"] == 20.0
    assert cat_details["Dining"]["category_color"] == "#F59E0B"

    # Check nature details
    nat_details = {n["nature"]: n for n in bucket["nature_spending_details"]}
    assert nat_details["fixed"]["amount_pence"] == 80000
    assert nat_details["fixed"]["percentage"] == 80.0
    assert nat_details["variable"]["amount_pence"] == 20000
    assert nat_details["variable"]["percentage"] == 20.0

def test_category_filter_in_analysis(db_session, client):
    """
    Verifies that drilling down by category_id restricts spending totals and series
    to that category only.
    """
    acc = Account(name="Current Account", account_type=AccountType.CURRENT, currency="GBP", starting_balance_pence=100000)
    cat_a = Category(name="Books", default_expense_nature=ExpenseNature.VARIABLE)
    cat_b = Category(name="Electronics", default_expense_nature=ExpenseNature.VARIABLE)
    db_session.add_all([acc, cat_a, cat_b])
    db_session.commit()

    d = datetime.now(timezone.utc)
    tx_a = Transaction(
        transaction_date=d,
        transaction_type=TransactionType.EXPENSE,
        amount_pence=1500,
        merchant="Bookstore",
        account_id=acc.id,
        category_id=cat_a.id,
        expense_nature=ExpenseNature.VARIABLE
    )
    tx_b = Transaction(
        transaction_date=d,
        transaction_type=TransactionType.EXPENSE,
        amount_pence=50000,
        merchant="TechStore",
        account_id=acc.id,
        category_id=cat_b.id,
        expense_nature=ExpenseNature.VARIABLE
    )
    db_session.add_all([tx_a, tx_b])
    db_session.commit()

    # Query with category_id = cat_a.id
    res = client.get(f"/api/analytics/analysis?preset=month&category_id={cat_a.id}")
    assert res.status_code == 200
    data = res.json()
    assert data["category_id"] == cat_a.id
    assert data["category_name"] == "Books"
    assert data["totals"]["expenses_pence"] == 1500

def test_spending_matrix_and_uncategorised_handling(db_session, client):
    """
    Verifies that the spending matrix:
    - Lists categories as rows, with periods as columns.
    - Accurately computes row totals, column totals, and grand total.
    - Labels transactions without category as 'Uncategorised'.
    - Handles empty period cells with £0.00 / 0 pence without error.
    """
    acc = Account(name="Current Account", account_type=AccountType.CURRENT, currency="GBP", starting_balance_pence=100000)
    cat_groceries = Category(name="Groceries", default_expense_nature=ExpenseNature.VARIABLE, color="#10B981")
    cat_dining = Category(name="Dining Out", default_expense_nature=ExpenseNature.VARIABLE, color="#F59E0B")
    db_session.add_all([acc, cat_groceries, cat_dining])
    db_session.commit()

    # July 2026: Groceries £80
    d_jul = datetime(2026, 7, 10, 12, 0, tzinfo=timezone.utc)
    tx_jul = Transaction(
        transaction_date=d_jul,
        transaction_type=TransactionType.EXPENSE,
        amount_pence=8000,
        merchant="Tesco",
        account_id=acc.id,
        category_id=cat_groceries.id,
        expense_nature=ExpenseNature.VARIABLE
    )
    # August 2026: Uncategorised £30
    d_aug = datetime(2026, 8, 15, 14, 0, tzinfo=timezone.utc)
    tx_aug = Transaction(
        transaction_date=d_aug,
        transaction_type=TransactionType.EXPENSE,
        amount_pence=3000,
        merchant="Corner Shop",
        account_id=acc.id,
        category_id=None,
        expense_nature=ExpenseNature.UNCLASSIFIED
    )
    # September 2026: Dining £50, Groceries £40
    d_sep = datetime(2026, 9, 20, 18, 0, tzinfo=timezone.utc)
    tx_sep1 = Transaction(
        transaction_date=d_sep,
        transaction_type=TransactionType.EXPENSE,
        amount_pence=5000,
        merchant="Pizza Express",
        account_id=acc.id,
        category_id=cat_dining.id,
        expense_nature=ExpenseNature.VARIABLE
    )
    tx_sep2 = Transaction(
        transaction_date=d_sep,
        transaction_type=TransactionType.EXPENSE,
        amount_pence=4000,
        merchant="Sainsburys",
        account_id=acc.id,
        category_id=cat_groceries.id,
        expense_nature=ExpenseNature.VARIABLE
    )
    db_session.add_all([tx_jul, tx_aug, tx_sep1, tx_sep2])
    db_session.commit()

    buckets = generate_intervals(date(2026, 7, 1), date(2026, 9, 30), "month", ZoneInfo("Europe/London"))
    totals, series, categories, matrix = compute_cashflow_and_spending(db_session, buckets, "GBP")

    assert totals["expenses_pence"] == 20000  # 80 + 30 + 50 + 40 = £200
    assert matrix["grand_total_pence"] == 20000

    # 3 periods: July, August, September
    assert len(matrix["periods"]) == 3
    assert matrix["periods"][0]["period_total_pence"] == 8000
    assert matrix["periods"][1]["period_total_pence"] == 3000
    assert matrix["periods"][2]["period_total_pence"] == 9000

    # Rows: Groceries (£120), Dining Out (£50), Uncategorised (£30)
    assert len(matrix["rows"]) == 3
    row_names = [r["category_name"] for r in matrix["rows"]]
    assert "Groceries" in row_names
    assert "Dining Out" in row_names
    assert "Uncategorised" in row_names

    groceries_row = next(r for r in matrix["rows"] if r["category_name"] == "Groceries")
    assert groceries_row["row_total_pence"] == 12000
    assert groceries_row["cells"]["2026-07"]["amount_pence"] == 8000
    assert groceries_row["cells"]["2026-08"]["amount_pence"] == 0
    assert groceries_row["cells"]["2026-09"]["amount_pence"] == 4000

    uncat_row = next(r for r in matrix["rows"] if r["category_name"] == "Uncategorised")
    assert uncat_row["row_total_pence"] == 3000
    assert uncat_row["cells"]["2026-07"]["amount_pence"] == 0
    assert uncat_row["cells"]["2026-08"]["amount_pence"] == 3000
    assert uncat_row["cells"]["2026-09"]["amount_pence"] == 0

def test_cumulative_flow_trends_with_no_income_periods(db_session):
    """
    Verifies that cumulative cash-flow trends:
    - Cumulative income rises when income occurs and remains flat during periods with zero income.
    - Cumulative spending is always positive and rising as expenses occur.
    - Net flow equals cumulative income minus cumulative spending, plotting positive when ahead
      and dropping (or negative) when spending overtakes income.
    """
    acc = Account(name="Current Account", account_type=AccountType.CURRENT, currency="GBP", starting_balance_pence=100000)
    cat_salary = Category(name="Salary", default_expense_nature=ExpenseNature.VARIABLE)
    cat_rent = Category(name="Rent", default_expense_nature=ExpenseNature.FIXED)
    db_session.add_all([acc, cat_salary, cat_rent])
    db_session.commit()

    # Period 1 (Jan 2026): Income £3,000, Expense £1,000
    # Net: +£2,000. Cumulative: Inc £3,000, Exp £1,000, Net £2,000
    tx1_inc = Transaction(
        transaction_date=datetime(2026, 1, 5, 10, 0, tzinfo=timezone.utc),
        transaction_type=TransactionType.INCOME,
        amount_pence=300000,
        merchant="Employer",
        account_id=acc.id,
        category_id=cat_salary.id
    )
    tx1_exp = Transaction(
        transaction_date=datetime(2026, 1, 10, 10, 0, tzinfo=timezone.utc),
        transaction_type=TransactionType.EXPENSE,
        amount_pence=100000,
        merchant="Landlord",
        account_id=acc.id,
        category_id=cat_rent.id,
        expense_nature=ExpenseNature.FIXED
    )
    # Period 2 (Feb 2026): No income, Expense £1,500
    # Net: -£1,500. Cumulative: Inc £3,000 (flat), Exp £2,500, Net £500
    tx2_exp = Transaction(
        transaction_date=datetime(2026, 2, 10, 10, 0, tzinfo=timezone.utc),
        transaction_type=TransactionType.EXPENSE,
        amount_pence=150000,
        merchant="Landlord",
        account_id=acc.id,
        category_id=cat_rent.id,
        expense_nature=ExpenseNature.FIXED
    )
    # Period 3 (Mar 2026): No income, Expense £1,500
    # Net: -£1,500. Cumulative: Inc £3,000 (flat), Exp £4,000, Net -£1,000 (spending ahead!)
    tx3_exp = Transaction(
        transaction_date=datetime(2026, 3, 10, 10, 0, tzinfo=timezone.utc),
        transaction_type=TransactionType.EXPENSE,
        amount_pence=150000,
        merchant="Landlord",
        account_id=acc.id,
        category_id=cat_rent.id,
        expense_nature=ExpenseNature.FIXED
    )
    db_session.add_all([tx1_inc, tx1_exp, tx2_exp, tx3_exp])
    db_session.commit()

    buckets = generate_intervals(date(2026, 1, 1), date(2026, 3, 31), "month", ZoneInfo("Europe/London"))
    totals, series, _, _ = compute_cashflow_and_spending(db_session, buckets, "GBP")

    # Period 1 (Jan)
    assert series[0]["cumulative_income_pence"] == 300000
    assert series[0]["cumulative_expenses_pence"] == 100000
    assert series[0]["cumulative_net_flow_pence"] == 200000

    # Period 2 (Feb) - No income: income stays flat, spending increases, net flow declines
    assert series[1]["income_pence"] == 0
    assert series[1]["cumulative_income_pence"] == 300000  # Stays flat!
    assert series[1]["cumulative_expenses_pence"] == 250000  # 1,000 + 1,500 = 2,500
    assert series[1]["cumulative_net_flow_pence"] == 50000   # 3,000 - 2,500 = 500

    # Period 3 (Mar) - No income: spending overtakes income, net flow becomes negative!
    assert series[2]["income_pence"] == 0
    assert series[2]["cumulative_income_pence"] == 300000  # Stays flat!
    assert series[2]["cumulative_expenses_pence"] == 400000  # 2,500 + 1,500 = 4,000
    assert series[2]["cumulative_net_flow_pence"] == -100000  # 3,000 - 4,000 = -1,000

    # Totals across range
    assert totals["cumulative_income_pence"] == 300000
    assert totals["cumulative_expenses_pence"] == 400000
    assert totals["cumulative_net_flow_pence"] == -100000

def test_ledger_drilldown_query_filtering(db_session, client):
    """
    Verifies that the transactions API correctly filters by category_id (including 0 for uncategorized)
    and by start_date / end_date for seamless drill-down from matrix cells.
    """
    acc = Account(name="Current Account", account_type=AccountType.CURRENT, currency="GBP", starting_balance_pence=100000)
    cat_food = Category(name="Food", default_expense_nature=ExpenseNature.VARIABLE)
    db_session.add_all([acc, cat_food])
    db_session.commit()

    # Tx 1: Food on 2026-08-10 (£25)
    tx1 = Transaction(
        transaction_date=datetime(2026, 8, 10, 12, 0, tzinfo=timezone.utc),
        transaction_type=TransactionType.EXPENSE,
        amount_pence=2500,
        merchant="Cafe",
        account_id=acc.id,
        category_id=cat_food.id
    )
    # Tx 2: Food on 2026-09-15 (£45)
    tx2 = Transaction(
        transaction_date=datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc),
        transaction_type=TransactionType.EXPENSE,
        amount_pence=4500,
        merchant="Restaurant",
        account_id=acc.id,
        category_id=cat_food.id
    )
    # Tx 3: Uncategorised on 2026-08-20 (£10)
    tx3 = Transaction(
        transaction_date=datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc),
        transaction_type=TransactionType.EXPENSE,
        amount_pence=1000,
        merchant="Corner Shop",
        account_id=acc.id,
        category_id=None
    )
    db_session.add_all([tx1, tx2, tx3])
    db_session.commit()

    # 1. Filter Food in August only: should return only tx1
    res1 = client.get(f"/api/transactions?category_id={cat_food.id}&start_date=2026-08-01&end_date=2026-08-31")
    assert res1.status_code == 200
    items1 = res1.json()["items"]
    assert len(items1) == 1
    assert items1[0]["id"] == tx1.id

    # 2. Filter Uncategorised (category_id=0): should return tx3
    res2 = client.get("/api/transactions?category_id=0")
    assert res2.status_code == 200
    items2 = res2.json()["items"]
    assert len(items2) == 1
    assert items2[0]["id"] == tx3.id

    # 3. Filter uncategorized_only=true
    res3 = client.get("/api/transactions?uncategorized_only=true")
    assert res3.status_code == 200
    items3 = res3.json()["items"]
    assert len(items3) == 1
    assert items3[0]["id"] == tx3.id


def test_multi_select_account_and_category_filter_composition(db_session, client):
    """
    Verifies searchable multi-select account_ids and category_ids (including 0 for Uncategorised)
    filter composition across cash flow totals, time_series, spending_matrix, and net_worth_series.
    """
    acc1 = Account(name="Checking One", account_type=AccountType.CURRENT, currency="GBP", starting_balance_pence=100000, color="#10B981")
    acc2 = Account(name="Savings Two", account_type=AccountType.SAVINGS, currency="GBP", starting_balance_pence=200000, color="#3B82F6")
    acc3 = Account(name="Credit Three", account_type=AccountType.CREDIT_CARD, currency="GBP", starting_balance_pence=0, color="#F43F5E")
    cat1 = Category(name="Groceries", default_expense_nature=ExpenseNature.VARIABLE, color="#10B981")
    cat2 = Category(name="Dining", default_expense_nature=ExpenseNature.VARIABLE, color="#F59E0B")
    cat3 = Category(name="Travel", default_expense_nature=ExpenseNature.VARIABLE, color="#8B5CF6")
    db_session.add_all([acc1, acc2, acc3, cat1, cat2, cat3])
    db_session.commit()

    d_jul = datetime(2026, 7, 15, 12, 0, tzinfo=timezone.utc)
    d_aug = datetime(2026, 8, 15, 12, 0, tzinfo=timezone.utc)

    db_session.add_all([
        # Acc 1, Groceries: £40 in July
        Transaction(transaction_date=d_jul, transaction_type=TransactionType.EXPENSE, amount_pence=4000, merchant="Tesco", account_id=acc1.id, category_id=cat1.id),
        # Acc 2, Dining: £60 in August
        Transaction(transaction_date=d_aug, transaction_type=TransactionType.EXPENSE, amount_pence=6000, merchant="Bistro", account_id=acc2.id, category_id=cat2.id),
        # Acc 3, Travel: £150 in August
        Transaction(transaction_date=d_aug, transaction_type=TransactionType.EXPENSE, amount_pence=15000, merchant="Trainline", account_id=acc3.id, category_id=cat3.id),
        # Acc 1, Uncategorised: £25 in August
        Transaction(transaction_date=d_aug, transaction_type=TransactionType.EXPENSE, amount_pence=2500, merchant="Mystery Shop", account_id=acc1.id, category_id=None),
    ])
    db_session.commit()

    # 1. Multi-account filter: acc1 + acc2 (excludes acc3's £150 Travel)
    res_acc = client.get(
        f"/api/analytics/analysis?preset=custom&start_date=2026-07-01&end_date=2026-08-31&interval=month&account_ids={acc1.id},{acc2.id}"
    )
    assert res_acc.status_code == 200
    data_acc = res_acc.json()
    assert data_acc["account_ids"] == [acc1.id, acc2.id]
    assert data_acc["account_names"] == ["Checking One", "Savings Two"]
    # Total expenses = £40 + £60 + £25 = £125 (12500 pence)
    assert data_acc["totals"]["expenses_pence"] == 12500
    assert data_acc["spending_matrix"]["grand_total_pence"] == 12500
    # Net worth series only includes acc1 and acc2
    nw_acc_ids = [a["account_id"] for a in data_acc["net_worth_series"][0]["account_balances"]]
    assert set(nw_acc_ids) == {acc1.id, acc2.id}

    # 2. Multi-category filter including Uncategorised (0): Groceries (cat1) + Uncategorised (0)
    res_cat = client.get(
        f"/api/analytics/analysis?preset=custom&start_date=2026-07-01&end_date=2026-08-31&interval=month&category_ids={cat1.id},0"
    )
    assert res_cat.status_code == 200
    data_cat = res_cat.json()
    assert data_cat["category_ids"] == [cat1.id, 0]
    assert data_cat["category_names"] == ["Groceries", "Uncategorised"]
    # Total expenses = £40 (Groceries) + £25 (Uncategorised) = £65 (6500 pence)
    assert data_cat["totals"]["expenses_pence"] == 6500
    assert len(data_cat["spending_matrix"]["rows"]) == 2

    # 3. Combined multi-account (acc1, acc2) AND multi-category (cat1, cat2)
    res_both = client.get(
        f"/api/analytics/analysis?preset=custom&start_date=2026-07-01&end_date=2026-08-31&interval=month&account_ids={acc1.id},{acc2.id}&category_ids={cat1.id},{cat2.id}"
    )
    assert res_both.status_code == 200
    data_both = res_both.json()
    # £40 (Groceries on acc1) + £60 (Dining on acc2) = £100 (10000 pence)
    assert data_both["totals"]["expenses_pence"] == 10000
    assert data_both["spending_matrix"]["grand_total_pence"] == 10000


def test_spending_matrix_and_table_csv_and_xlsx_exports(db_session, client):
    """
    Verifies local, profile-scoped CSV and XLSX exports for the Spending Matrix and other Analysis tables:
    - Includes clear report title, selected date range, group-by interval, and applied account/category filters.
    - Includes readable period and category names, row totals, column totals, and grand total.
    - For XLSX: numeric values are strictly stored as numbers (int/float, never formatted currency strings),
      frozen panes are configured (B9), auto-filters are applied, and column widths are sensible.
    """
    import io
    import csv
    from openpyxl import load_workbook

    acc1 = Account(name="Main Current", account_type=AccountType.CURRENT, currency="GBP", starting_balance_pence=250000)
    cat_food = Category(name="Groceries", default_expense_nature=ExpenseNature.VARIABLE, color="#10B981")
    cat_rent = Category(name="Rent", default_expense_nature=ExpenseNature.FIXED, color="#6366F1")
    db_session.add_all([acc1, cat_food, cat_rent])
    db_session.commit()

    db_session.add_all([
        Transaction(
            transaction_date=datetime(2026, 7, 5, 10, 0, tzinfo=timezone.utc),
            transaction_type=TransactionType.INCOME,
            amount_pence=300000,
            merchant="Employer",
            account_id=acc1.id,
        ),
        Transaction(
            transaction_date=datetime(2026, 7, 10, 12, 0, tzinfo=timezone.utc),
            transaction_type=TransactionType.EXPENSE,
            amount_pence=120000,
            merchant="Landlord",
            account_id=acc1.id,
            category_id=cat_rent.id,
            expense_nature=ExpenseNature.FIXED,
        ),
        Transaction(
            transaction_date=datetime(2026, 8, 12, 12, 0, tzinfo=timezone.utc),
            transaction_type=TransactionType.EXPENSE,
            amount_pence=4550,
            merchant="Supermarket",
            account_id=acc1.id,
            category_id=cat_food.id,
            expense_nature=ExpenseNature.VARIABLE,
        ),
    ])
    db_session.commit()

    # 1. Test Spending Matrix XLSX Export
    res_xlsx = client.get(
        f"/api/analytics/export?report_type=spending_matrix&format=xlsx&preset=custom&start_date=2026-07-01&end_date=2026-08-31&interval=month&account_ids={acc1.id}&category_ids={cat_food.id},{cat_rent.id}"
    )
    assert res_xlsx.status_code == 200
    assert "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" in res_xlsx.headers["content-type"]
    assert 'filename="finance_hub_spending_matrix_2026-07-01_to_2026-08-31.xlsx"' in res_xlsx.headers["content-disposition"]

    wb = load_workbook(io.BytesIO(res_xlsx.content))
    ws = wb.active
    assert ws.title == "Spending Matrix"
    assert ws.freeze_panes == "B9"
    assert ws.auto_filter.ref is not None

    # Metadata verification (rows 1..6)
    assert "Category Spending Matrix" in ws["A1"].value
    assert "2026-07-01 to 2026-08-31" in ws["B2"].value
    assert "Monthly" in ws["B3"].value
    assert "GBP" in ws["B4"].value
    assert ws["B5"].value == "Main Current"
    assert "Groceries" in ws["B6"].value and "Rent" in ws["B6"].value

    # Table headers on row 8
    headers = [ws.cell(row=8, column=col).value for col in range(1, 8)]
    assert headers == ["Category", "Expense Nature", "Jul 2026", "Aug 2026", "Row Total", "Share (%)", "Transactions"]

    # Data rows (rows 9 and 10: Rent £1,200.00, Groceries £45.50) and Total row (row 11)
    rent_row_vals = [ws.cell(row=9, column=col).value for col in range(1, 8)]
    assert rent_row_vals[0] == "Rent"
    assert rent_row_vals[1] == "Fixed"
    # Strictly numeric values (not strings!)
    assert isinstance(rent_row_vals[2], (int, float)) and rent_row_vals[2] == 1200.0
    assert isinstance(rent_row_vals[3], (int, float)) and rent_row_vals[3] == 0.0
    assert isinstance(rent_row_vals[4], (int, float)) and rent_row_vals[4] == 1200.0
    assert isinstance(rent_row_vals[6], int) and rent_row_vals[6] == 1
    assert "£" in ws.cell(row=9, column=3).number_format

    food_row_vals = [ws.cell(row=10, column=col).value for col in range(1, 8)]
    assert food_row_vals[0] == "Groceries"
    assert isinstance(food_row_vals[2], (int, float)) and food_row_vals[2] == 0.0
    assert isinstance(food_row_vals[3], (int, float)) and food_row_vals[3] == 45.5
    assert isinstance(food_row_vals[4], (int, float)) and food_row_vals[4] == 45.5

    # Total row on row 11
    total_row_vals = [ws.cell(row=11, column=col).value for col in range(1, 8)]
    assert "Period Total" in total_row_vals[0]
    assert isinstance(total_row_vals[2], (int, float)) and total_row_vals[2] == 1200.0
    assert isinstance(total_row_vals[3], (int, float)) and total_row_vals[3] == 45.5
    assert isinstance(total_row_vals[4], (int, float)) and total_row_vals[4] == 1245.5
    assert total_row_vals[6] == 2

    # 2. Test Spending Matrix CSV Export
    res_csv = client.get(
        f"/api/analytics/export?report_type=spending_matrix&format=csv&preset=custom&start_date=2026-07-01&end_date=2026-08-31&interval=month&account_ids={acc1.id}"
    )
    assert res_csv.status_code == 200
    assert "text/csv" in res_csv.headers["content-type"]
    csv_text = res_csv.content.decode("utf-8-sig")
    rows = list(csv.reader(io.StringIO(csv_text)))
    assert "Finance Hub — Category Spending Matrix by Period" in rows[0][0]
    assert rows[4] == ["Account Filter", "Main Current"]
    assert rows[7][:5] == ["Category", "Expense Nature", "Jul 2026", "Aug 2026", "Row Total"]
    assert rows[-1][0] == "Period Total / Grand Total"
    assert rows[-1][4] == "£1,245.50"

    # 3. Test Overview Cashflow, Net Worth, and Investments XLSX Exports
    for rtype in ("overview_cashflow", "spending_categories", "net_worth", "investments"):
        r = client.get(f"/api/analytics/export?report_type={rtype}&format=xlsx&preset=month")
        assert r.status_code == 200
        wb_r = load_workbook(io.BytesIO(r.content))
        assert wb_r.active.freeze_panes == "B9"


def test_export_currency_symbol_and_formatting_across_base_currencies(db_session, client):
    """
    Verifies that CSV and XLSX exports dynamically honor the active profile's configured
    base currency (e.g. USD '$', EUR '€', CHF 'CHF ', INR '₹', SEK 'kr ') rather than
    hard-coding '£'.
    """
    import io
    import csv
    from openpyxl import load_workbook

    # Configure profile base currency to USD first, and create accounts in USD, EUR, CHF, INR
    setting = db_session.query(SystemSetting).filter(SystemSetting.key == "base_currency").first()
    if setting:
        setting.value = "USD"
    else:
        db_session.add(SystemSetting(key="base_currency", value="USD"))
    db_session.commit()

    acc_usd = Account(name="US Checking", account_type=AccountType.CURRENT, currency="USD", starting_balance_pence=500000)
    acc_eur = Account(name="Euro Checking", account_type=AccountType.CURRENT, currency="EUR", starting_balance_pence=300000)
    acc_chf = Account(name="Swiss Checking", account_type=AccountType.CURRENT, currency="CHF", starting_balance_pence=400000)
    acc_inr = Account(name="India Checking", account_type=AccountType.CURRENT, currency="INR", starting_balance_pence=900000)
    cat_cloud = Category(name="Cloud Hosting", default_expense_nature=ExpenseNature.FIXED, color="#3B82F6")
    db_session.add_all([acc_usd, acc_eur, acc_chf, acc_inr, cat_cloud])
    db_session.commit()

    tx_date = datetime(2026, 8, 15, 12, 0, tzinfo=timezone.utc)
    db_session.add_all([
        Transaction(transaction_date=tx_date, transaction_type=TransactionType.EXPENSE, amount_pence=25000, merchant="AWS USD", account_id=acc_usd.id, category_id=cat_cloud.id),
        Transaction(transaction_date=tx_date, transaction_type=TransactionType.EXPENSE, amount_pence=18050, merchant="Hetzner EUR", account_id=acc_eur.id, category_id=cat_cloud.id),
        Transaction(transaction_date=tx_date, transaction_type=TransactionType.EXPENSE, amount_pence=32000, merchant="Proton CHF", account_id=acc_chf.id, category_id=cat_cloud.id),
        Transaction(transaction_date=tx_date, transaction_type=TransactionType.EXPENSE, amount_pence=99900, merchant="Server INR", account_id=acc_inr.id, category_id=cat_cloud.id),
    ])
    db_session.commit()

    cases = [
        ("USD", "$", '"$"#,##0.00;-"$"#,##0.00;"$"0.00', "$250.00"),
        ("EUR", "€", '"€"#,##0.00;-"€"#,##0.00;"€"0.00', "€180.50"),
        ("CHF", "CHF", '"CHF "#,##0.00;-"CHF "#,##0.00;"CHF "0.00', "CHF 320.00"),
        ("INR", "₹", '"₹"#,##0.00;-"₹"#,##0.00;"₹"0.00', "₹999.00"),
    ]

    for curr_code, expected_sym, expected_xlsx_fmt, expected_csv_total in cases:
        # 1. Verify XLSX currency metadata & cell number_format
        res_x = client.get(
            f"/api/analytics/export?report_type=spending_matrix&format=xlsx&preset=custom&start_date=2026-08-01&end_date=2026-08-31&interval=month&currency={curr_code}"
        )
        assert res_x.status_code == 200
        wb = load_workbook(io.BytesIO(res_x.content))
        ws = wb.active
        assert ws["B4"].value == f"{curr_code} ({expected_sym})"
        # Cell C9 is Aug 2026 spend, D9 is Row Total, C10 is Period Total, D10 is Grand Total
        for cell_coord in ("C9", "D9", "C10", "D10"):
            cell = ws[cell_coord]
            assert isinstance(cell.value, (int, float))
            assert cell.number_format == expected_xlsx_fmt
            assert "£" not in cell.number_format

        # 2. Verify CSV currency formatting
        res_c = client.get(
            f"/api/analytics/export?report_type=spending_matrix&format=csv&preset=custom&start_date=2026-08-01&end_date=2026-08-31&interval=month&currency={curr_code}"
        )
        assert res_c.status_code == 200
        csv_rows = list(csv.reader(io.StringIO(res_c.content.decode("utf-8-sig"))))
        assert csv_rows[3] == ["Currency", f"{curr_code} ({expected_sym})"]
        assert csv_rows[-1][3] == expected_csv_total
        assert "£" not in csv_rows[-1][3]


