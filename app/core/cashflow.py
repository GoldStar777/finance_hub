"""
Core Cash Flow & Inflow/Outflow Analytics Engine.

Provides deterministic, multi-currency cash flow metrics for selected months and historical trends:
- Inflow (Income) from external sources.
- Outflow (Expenses) segmented by expense nature (Fixed, Variable, Unclassified).
- Internal Transfers strictly excluded (contribute £0 to income and expenses).
- Reconciliation Adjustments and refunds tracked distinctly from operating cash flows.
- Multi-currency isolation: amounts in different currencies are never combined.
- Safe division guards: handles zero-income months gracefully.
- Spending aggregated by category with percentage contributions.
- Historical trend across recent trailing months.
"""

from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple
from decimal import Decimal
from sqlalchemy.orm import Session
from sqlalchemy import func, or_, and_

from app.models import (
    Transaction,
    TransactionType,
    ExpenseNature,
    Account,
    Category,
)
from app.core.currency import format_pence, pence_to_pounds, get_effective_base_currency, get_currency_spec
from app.core.timezone import get_now_utc, ensure_utc, get_app_timezone, get_today_local, get_end_of_day_utc

def get_currency_symbol(curr: str) -> str:
    """Returns standard display symbol for currency code from the central ISO 4217 registry."""
    return get_currency_spec(curr).symbol

def parse_month_range(month_str: Optional[str] = None) -> Tuple[datetime, datetime, int, int, str, str, str, str]:
    """
    Parses 'YYYY-MM' into:
    (start_dt, end_dt, year, month, selected_month, month_name, prev_month, next_month).
    Falls back to current UTC month if input is missing or malformed.
    """
    now = datetime.now(timezone.utc)
    year = now.year
    month = now.month

    if month_str:
        clean = month_str.strip()
        parts = clean.split("-")
        if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
            y_val, m_val = int(parts[0]), int(parts[1])
            if 1900 <= y_val <= 2100 and 1 <= m_val <= 12:
                year, month = y_val, m_val

    start_dt = datetime(year, month, 1, 0, 0, 0, tzinfo=timezone.utc)
    if month == 12:
        end_dt = datetime(year + 1, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        next_month = f"{year + 1}-01"
    else:
        end_dt = datetime(year, month + 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        next_month = f"{year}-{month + 1:02d}"

    if month == 1:
        prev_month = f"{year - 1}-12"
    else:
        prev_month = f"{year}-{month - 1:02d}"

    selected_month = f"{year}-{month:02d}"
    month_name = start_dt.strftime("%B %Y")

    return start_dt, end_dt, year, month, selected_month, month_name, prev_month, next_month

def get_available_currencies(db: Session) -> List[str]:
    """Returns sorted distinct currencies configured on accounts, defaulting to ['GBP']."""
    raw_currencies = db.query(Account.currency).distinct().all()
    currencies = sorted(list({c[0].upper() for c in raw_currencies if c[0]}))
    if not currencies:
        return ["GBP"]
    if "GBP" in currencies:
        # Keep GBP primary if present
        currencies.remove("GBP")
        return ["GBP"] + currencies
    return currencies

def get_available_months(db: Session, currency: str, account_id: Optional[int] = None) -> List[str]:
    """Returns sorted descending list of YYYY-MM strings for all transactions in this currency/account."""
    base_curr = get_effective_base_currency(db)
    if account_id is not None:
        query = (
            db.query(Transaction.transaction_date)
            .join(Account, Transaction.account_id == Account.id)
            .filter(
                Transaction.deleted_at.is_(None),
                Account.currency == currency,
                Transaction.account_id == account_id
            )
        )
    else:
        query = (
            db.query(Transaction.transaction_date)
            .outerjoin(Account, Transaction.account_id == Account.id)
            .filter(
                Transaction.deleted_at.is_(None),
                or_(
                    Account.currency == currency,
                    and_(Transaction.account_id.is_(None), currency == base_curr)
                )
            )
        )

    dates = query.all()
    months_set = {d[0].strftime("%Y-%m") for d in dates if d[0]}
    
    # Always include current month in options for easy navigation
    current_m = datetime.now(timezone.utc).strftime("%Y-%m")
    months_set.add(current_m)

    return sorted(list(months_set), reverse=True)

def compute_month_metrics(
    db: Session,
    start_dt: datetime,
    end_dt: datetime,
    currency: str,
    account_id: Optional[int] = None
) -> Dict[str, Any]:
    """
    Computes cash flow aggregates for a given date window, strictly filtered by currency/account.
    Unassigned transactions are included in base-currency cash flow when viewing overall cash flow.
    """
    base_curr = get_effective_base_currency(db)
    if account_id is not None:
        query = (
            db.query(Transaction)
            .join(Account, Transaction.account_id == Account.id)
            .filter(
                Transaction.deleted_at.is_(None),
                Account.currency == currency,
                Transaction.account_id == account_id,
                Transaction.transaction_date >= start_dt,
                Transaction.transaction_date < end_dt
            )
        )
    else:
        query = (
            db.query(Transaction)
            .outerjoin(Account, Transaction.account_id == Account.id)
            .filter(
                Transaction.deleted_at.is_(None),
                Transaction.transaction_date >= start_dt,
                Transaction.transaction_date < end_dt,
                or_(
                    Account.currency == currency,
                    and_(Transaction.account_id.is_(None), currency == base_curr)
                )
            )
        )

    txs = query.all()

    income_pence = 0
    income_count = 0

    fixed_expenses_pence = 0
    fixed_count = 0

    variable_expenses_pence = 0
    variable_count = 0

    unclassified_expenses_pence = 0
    unclassified_count = 0

    transfers_volume_pence = 0
    transfers_count = 0

    adjustments_inflow_pence = 0
    adjustments_outflow_pence = 0
    adjustments_count = 0

    category_buckets: Dict[Optional[int], Dict[str, Any]] = {}

    app_tz = get_app_timezone(db)
    today_local = get_today_local(app_tz)
    end_of_today_utc = get_end_of_day_utc(today_local, tz_str=app_tz)

    actual_txs = []
    planned_txs = []
    for tx in txs:
        eff_utc = ensure_utc(tx.effective_timestamp or tx.transaction_date)
        if eff_utc > end_of_today_utc:
            planned_txs.append(tx)
        else:
            actual_txs.append(tx)

    for tx in actual_txs:
        # Rule 1: Internal transfers contribute zero to income or expenses
        if tx.transaction_type == TransactionType.TRANSFER:
            transfers_volume_pence += tx.amount_pence
            transfers_count += 1
            continue

        # Rule 2: Operating income from external sources
        if tx.transaction_type == TransactionType.INCOME:
            income_pence += tx.amount_pence
            income_count += 1
            continue

        # Rule 3: Operating expenses segmented by row-level expense_nature
        if tx.transaction_type == TransactionType.EXPENSE:
            nature = tx.expense_nature or ExpenseNature.UNCLASSIFIED
            if nature == ExpenseNature.FIXED:
                fixed_expenses_pence += tx.amount_pence
                fixed_count += 1
            elif nature == ExpenseNature.VARIABLE:
                variable_expenses_pence += tx.amount_pence
                variable_count += 1
            else:
                unclassified_expenses_pence += tx.amount_pence
                unclassified_count += 1

            cat_id = tx.category_id
            if cat_id not in category_buckets:
                category_buckets[cat_id] = {
                    "total_pence": 0,
                    "count": 0,
                    "nature": nature
                }
            category_buckets[cat_id]["total_pence"] += tx.amount_pence
            category_buckets[cat_id]["count"] += 1
            continue

        # Rule 4: Reconciliation adjustments / manual corrections
        if tx.transaction_type == TransactionType.ADJUSTMENT:
            adjustments_count += 1
            is_positive = bool(tx.notes and "[Positive adjustment]" in tx.notes)
            if is_positive:
                adjustments_inflow_pence += tx.amount_pence
            else:
                adjustments_outflow_pence += tx.amount_pence

    total_expenses_pence = fixed_expenses_pence + variable_expenses_pence + unclassified_expenses_pence
    expenses_count = fixed_count + variable_count + unclassified_count

    adjustments_net_pence = adjustments_inflow_pence - adjustments_outflow_pence
    operating_surplus_pence = income_pence - total_expenses_pence
    net_surplus_pence = operating_surplus_pence + adjustments_net_pence

    # Expense nature percentages
    if total_expenses_pence > 0:
        fixed_percentage = round((fixed_expenses_pence / total_expenses_pence) * 100, 1)
        variable_percentage = round((variable_expenses_pence / total_expenses_pence) * 100, 1)
        unclassified_percentage = round((unclassified_expenses_pence / total_expenses_pence) * 100, 1)
    else:
        fixed_percentage = 0.0
        variable_percentage = 0.0
        unclassified_percentage = 0.0

    # Rule 5: Savings rate with zero-income guard
    if income_pence > 0:
        savings_rate = round((net_surplus_pence / income_pence) * 100, 1)
        is_savings_rate_applicable = True
        formatted_savings_rate = f"{savings_rate:.1f}%"
    else:
        savings_rate = 0.0
        is_savings_rate_applicable = False
        formatted_savings_rate = "N/A"

    # Planned activity calculations
    planned_income_pence = 0
    planned_expenses_pence = 0
    for tx in planned_txs:
        if tx.transaction_type == TransactionType.INCOME:
            planned_income_pence += tx.amount_pence
        elif tx.transaction_type == TransactionType.EXPENSE:
            planned_expenses_pence += tx.amount_pence
    planned_net_pence = planned_income_pence - planned_expenses_pence
    planned_count = len(planned_txs)

    return {
        "income_pence": income_pence,
        "income_count": income_count,
        "fixed_expenses_pence": fixed_expenses_pence,
        "fixed_expenses_count": fixed_count,
        "fixed_percentage": fixed_percentage,
        "variable_expenses_pence": variable_expenses_pence,
        "variable_expenses_count": variable_count,
        "variable_percentage": variable_percentage,
        "unclassified_expenses_pence": unclassified_expenses_pence,
        "unclassified_expenses_count": unclassified_count,
        "unclassified_percentage": unclassified_percentage,
        "total_expenses_pence": total_expenses_pence,
        "expenses_count": expenses_count,
        "transfers_volume_pence": transfers_volume_pence,
        "transfers_count": transfers_count,
        "adjustments_inflow_pence": adjustments_inflow_pence,
        "adjustments_outflow_pence": adjustments_outflow_pence,
        "adjustments_net_pence": adjustments_net_pence,
        "adjustments_count": adjustments_count,
        "operating_surplus_pence": operating_surplus_pence,
        "net_surplus_pence": net_surplus_pence,
        "savings_rate": savings_rate,
        "is_savings_rate_applicable": is_savings_rate_applicable,
        "formatted_savings_rate": formatted_savings_rate,
        "category_buckets": category_buckets,
        "planned_income_pence": planned_income_pence,
        "planned_expenses_pence": planned_expenses_pence,
        "planned_net_pence": planned_net_pence,
        "planned_count": planned_count,
        "formatted_planned_net": format_pence(planned_net_pence, get_currency_symbol(currency)),
        "total_transactions_count": len(txs),
        "has_data": len(txs) > 0,
    }

def get_trailing_months(year: int, month: int, count: int = 6) -> List[Tuple[int, int]]:
    """Returns list of (year, month) tuples ending at the given year/month in chronological order."""
    months: List[Tuple[int, int]] = []
    curr_y = year
    curr_m = month
    for _ in range(count):
        months.append((curr_y, curr_m))
        curr_m -= 1
        if curr_m == 0:
            curr_m = 12
            curr_y -= 1
    months.reverse()
    return months

def get_cashflow_summary(
    db: Session,
    month_str: Optional[str] = None,
    currency_param: Optional[str] = None,
    account_id: Optional[int] = None
) -> Dict[str, Any]:
    """
    Main entry point for Cash Flow Analytics.
    Returns comprehensive metrics for the selected month, category breakdown, and historical trend.
    """
    # 1. Resolve Account & Currency
    account_name = None
    available_currencies = get_available_currencies(db)

    if account_id is not None:
        acc = db.query(Account).filter(Account.id == account_id).first()
        if not acc:
            raise ValueError(f"Account with ID {account_id} not found.")
        account_name = acc.name
        currency = acc.currency.upper()
    elif currency_param:
        currency = currency_param.strip().upper()
    else:
        currency = available_currencies[0]

    currency_symbol = get_currency_symbol(currency)

    # 2. Parse Date Range
    (
        start_dt,
        end_dt,
        year,
        month,
        selected_month,
        month_name,
        prev_month,
        next_month
    ) = parse_month_range(month_str)

    # 3. Compute Metrics for Selected Month
    metrics = compute_month_metrics(db, start_dt, end_dt, currency, account_id)
    available_months = get_available_months(db, currency, account_id)

    # 4. Resolve Categories with Details
    category_buckets = metrics.pop("category_buckets")
    categories_list: List[Dict[str, Any]] = []

    # Pre-fetch all categories for fast mapping
    all_categories = {c.id: c for c in db.query(Category).all()}

    total_expenses_pence = metrics["total_expenses_pence"]
    for cat_id, bucket in category_buckets.items():
        if cat_id is not None and cat_id in all_categories:
            cat = all_categories[cat_id]
            cat_name = cat.name
            cat_color = cat.color or "#8B5CF6"
            nature = cat.default_expense_nature
            cat_type = getattr(cat, "category_type", None)
        elif cat_id is not None:
            cat_name = f"Category #{cat_id}"
            cat_color = "#8B5CF6"
            nature = bucket.get("nature", ExpenseNature.UNCLASSIFIED)
            cat_type = None
        else:
            cat_name = "Uncategorized"
            cat_color = "#94A3B8"
            nature = ExpenseNature.UNCLASSIFIED
            cat_type = None

        pence = bucket["total_pence"]
        pct = round((pence / total_expenses_pence) * 100, 1) if total_expenses_pence > 0 else 0.0

        categories_list.append({
            "category_id": cat_id,
            "category_name": cat_name,
            "category_color": cat_color,
            "category_type": cat_type.value if cat_type else "expense",
            "expense_nature": nature,
            "total_pence": pence,
            "total_pounds": pence_to_pounds(pence),
            "formatted_total": format_pence(pence, currency_symbol),
            "transaction_count": bucket["count"],
            "percentage": pct,
        })

    # Sort categories descending by spend
    categories_list.sort(key=lambda x: x["total_pence"], reverse=True)

    # 5. Compute Historical Trend (Trailing 6 Months)
    trailing_pairs = get_trailing_months(year, month, count=6)
    historical_trend: List[Dict[str, Any]] = []

    for y, m in trailing_pairs:
        t_start = datetime(y, m, 1, 0, 0, 0, tzinfo=timezone.utc)
        if m == 12:
            t_end = datetime(y + 1, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        else:
            t_end = datetime(y, m + 1, 1, 0, 0, 0, tzinfo=timezone.utc)

        t_metrics = compute_month_metrics(db, t_start, t_end, currency, account_id)
        t_month_str = f"{y}-{m:02d}"
        t_month_name = t_start.strftime("%b %Y")

        historical_trend.append({
            "month": t_month_str,
            "month_name": t_month_name,
            "income_pence": t_metrics["income_pence"],
            "income_pounds": pence_to_pounds(t_metrics["income_pence"]),
            "formatted_income": format_pence(t_metrics["income_pence"], currency_symbol),
            "fixed_expenses_pence": t_metrics["fixed_expenses_pence"],
            "variable_expenses_pence": t_metrics["variable_expenses_pence"],
            "unclassified_expenses_pence": t_metrics["unclassified_expenses_pence"],
            "total_expenses_pence": t_metrics["total_expenses_pence"],
            "total_expenses_pounds": pence_to_pounds(t_metrics["total_expenses_pence"]),
            "formatted_total_expenses": format_pence(t_metrics["total_expenses_pence"], currency_symbol),
            "net_surplus_pence": t_metrics["net_surplus_pence"],
            "net_surplus_pounds": pence_to_pounds(t_metrics["net_surplus_pence"]),
            "formatted_net_surplus": format_pence(t_metrics["net_surplus_pence"], currency_symbol),
            "savings_rate": t_metrics["savings_rate"],
            "is_savings_rate_applicable": t_metrics["is_savings_rate_applicable"],
        })

    # 6. Format Return Structure
    return {
        "selected_month": selected_month,
        "month_name": month_name,
        "prev_month": prev_month,
        "next_month": next_month,
        "currency": currency,
        "currency_symbol": currency_symbol,
        "available_currencies": available_currencies,
        "available_months": available_months,
        "account_id": account_id,
        "account_name": account_name,

        # Income
        "income_pence": metrics["income_pence"],
        "income_pounds": pence_to_pounds(metrics["income_pence"]),
        "formatted_income": format_pence(metrics["income_pence"], currency_symbol),
        "income_count": metrics["income_count"],

        # Fixed Expenses
        "fixed_expenses_pence": metrics["fixed_expenses_pence"],
        "fixed_expenses_pounds": pence_to_pounds(metrics["fixed_expenses_pence"]),
        "formatted_fixed_expenses": format_pence(metrics["fixed_expenses_pence"], currency_symbol),
        "fixed_expenses_count": metrics["fixed_expenses_count"],
        "fixed_percentage": metrics["fixed_percentage"],

        # Variable Expenses
        "variable_expenses_pence": metrics["variable_expenses_pence"],
        "variable_expenses_pounds": pence_to_pounds(metrics["variable_expenses_pence"]),
        "formatted_variable_expenses": format_pence(metrics["variable_expenses_pence"], currency_symbol),
        "variable_expenses_count": metrics["variable_expenses_count"],
        "variable_percentage": metrics["variable_percentage"],

        # Unclassified Expenses
        "unclassified_expenses_pence": metrics["unclassified_expenses_pence"],
        "unclassified_expenses_pounds": pence_to_pounds(metrics["unclassified_expenses_pence"]),
        "formatted_unclassified_expenses": format_pence(metrics["unclassified_expenses_pence"], currency_symbol),
        "unclassified_expenses_count": metrics["unclassified_expenses_count"],
        "unclassified_percentage": metrics["unclassified_percentage"],

        # Total Expenses
        "total_expenses_pence": metrics["total_expenses_pence"],
        "total_expenses_pounds": pence_to_pounds(metrics["total_expenses_pence"]),
        "formatted_total_expenses": format_pence(metrics["total_expenses_pence"], currency_symbol),
        "expenses_count": metrics["expenses_count"],

        # Internal Transfers (Audit / Zero Effect)
        "transfers_volume_pence": metrics["transfers_volume_pence"],
        "transfers_volume_pounds": pence_to_pounds(metrics["transfers_volume_pence"]),
        "formatted_transfers_volume": format_pence(metrics["transfers_volume_pence"], currency_symbol),
        "transfers_count": metrics["transfers_count"],

        # Adjustments
        "adjustments_inflow_pence": metrics["adjustments_inflow_pence"],
        "adjustments_outflow_pence": metrics["adjustments_outflow_pence"],
        "adjustments_net_pence": metrics["adjustments_net_pence"],
        "adjustments_net_pounds": pence_to_pounds(metrics["adjustments_net_pence"]),
        "formatted_adjustments_net": format_pence(metrics["adjustments_net_pence"], currency_symbol),
        "adjustments_count": metrics["adjustments_count"],

        # Net
        "operating_surplus_pence": metrics["operating_surplus_pence"],
        "operating_surplus_pounds": pence_to_pounds(metrics["operating_surplus_pence"]),
        "formatted_operating_surplus": format_pence(metrics["operating_surplus_pence"], currency_symbol),

        "net_surplus_pence": metrics["net_surplus_pence"],
        "net_surplus_pounds": pence_to_pounds(metrics["net_surplus_pence"]),
        "formatted_net_surplus": format_pence(metrics["net_surplus_pence"], currency_symbol),

        # Savings Rate
        "savings_rate": metrics["savings_rate"],
        "is_savings_rate_applicable": metrics["is_savings_rate_applicable"],
        "formatted_savings_rate": metrics["formatted_savings_rate"],

        # Breakdowns
        "categories": categories_list,
        "historical_trend": historical_trend,

        # Planned
        "planned_income_pence": metrics["planned_income_pence"],
        "planned_expenses_pence": metrics["planned_expenses_pence"],
        "planned_net_pence": metrics["planned_net_pence"],
        "planned_count": metrics["planned_count"],
        "formatted_planned_net": metrics["formatted_planned_net"],

        # Meta
        "total_transactions_count": metrics["total_transactions_count"],
        "has_data": metrics["has_data"],
    }

