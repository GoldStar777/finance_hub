"""
Core Financial Analysis & Multidimensional Reporting Engine.

Provides unified time-series aggregation, category spending breakdowns,
balance-anchor history, and portfolio valuation trajectory across:
1. Overview (Income, Expenses, Net Savings, Savings Velocity)
2. Cash Flow (Operating Surplus, Internal Transfer Exclusions, Reconciliation Net)
3. Spending (Category distributions, Fixed vs Variable vs Unclassified)
4. Balances & Net Worth (Historical period-end balance reconstruction, Inferred warnings, Reconciliation snapshots)
5. Investments (Dated portfolio valuation history, sparse checkpoint handling)

Strictly local, deterministic integer-pence math, GBP-canonical currency isolation.
"""

from datetime import datetime, date, time, timedelta, timezone
from typing import Dict, Any, List, Optional, Tuple, Set
import calendar
from zoneinfo import ZoneInfo
from sqlalchemy.orm import Session
from sqlalchemy import func, or_, and_, desc

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
)
from app.ledger import LedgerEngine
from app.core.timezone import get_app_timezone, get_now_utc, ensure_utc, get_today_local, get_end_of_day_utc
from app.core.currency import (
    format_pence,
    pence_to_pounds,
    get_effective_base_currency,
    get_currency_spec,
    get_excel_currency_number_format,
)
from app.core.cashflow import get_currency_symbol, get_available_currencies
from app.core.investments import get_account_holdings_breakdown

VALID_PRESETS = ["day", "week", "month", "3m", "6m", "year", "5y", "all", "custom"]
VALID_INTERVALS = ["day", "week", "month", "quarter", "year"]

def get_default_interval_for_preset(preset: str, start_d: Optional[date] = None, end_d: Optional[date] = None) -> str:
    """Returns a sensible default aggregation interval for a date range preset."""
    p = (preset or "month").strip().lower()
    if p in ("day", "week"):
        return "day"
    if p == "month":
        return "day"
    if p == "3m":
        return "week"
    if p in ("6m", "year"):
        return "month"
    if p == "5y":
        return "quarter"
    if p == "all":
        if start_d and end_d:
            span_days = (end_d - start_d).days
            if span_days <= 60:
                return "week"
            elif span_days <= 730:
                return "month"
            elif span_days <= 1825:
                return "quarter"
            else:
                return "year"
        return "month"
    if p == "custom" and start_d and end_d:
        span_days = (end_d - start_d).days
        if span_days <= 14:
            return "day"
        elif span_days <= 90:
            return "week"
        elif span_days <= 730:
            return "month"
        elif span_days <= 1825:
            return "quarter"
        else:
            return "year"
    return "month"

DEFAULT_CATEGORY_PALETTE = [
    "#6366F1",  # Indigo
    "#EC4899",  # Pink
    "#F59E0B",  # Amber
    "#10B981",  # Emerald
    "#3B82F6",  # Blue
    "#8B5CF6",  # Purple
    "#14B8A6",  # Teal
    "#F97316",  # Orange
    "#06B6D4",  # Cyan
    "#84CC16",  # Lime
    "#E11D48",  # Rose
    "#A855F7",  # Fuchsia
    "#D97706",  # Warm Amber
    "#059669",  # Dark Emerald
    "#2563EB",  # Royal Blue
    "#7C3AED",  # Violet
]

def resolve_category_color(cat: Optional[Category], fallback_index: Optional[int] = None) -> str:
    """
    Returns configured category color or a deterministic distinct palette color.
    Avoids uniform fallback colors across categories.
    """
    if cat and cat.color and cat.color.strip() and cat.color.strip().upper() not in ("#8B5CF6", "#94A3B8", ""):
        return cat.color.strip()
    idx = fallback_index if fallback_index is not None else (((cat.id - 1) if cat and cat.id else 0) % len(DEFAULT_CATEGORY_PALETTE))
    return DEFAULT_CATEGORY_PALETTE[idx % len(DEFAULT_CATEGORY_PALETTE)]

def resolve_date_range(
    db: Session,
    preset: Optional[str] = None,
    custom_start: Optional[str] = None,
    custom_end: Optional[str] = None,
    offset: Optional[int] = 0
) -> Tuple[str, date, date, datetime, datetime, ZoneInfo, int, bool, bool]:
    """
    Resolves range presets or custom inputs into:
    (clean_preset, start_date_local, end_date_local, start_dt_utc, end_dt_utc, tz, offset, can_navigate_previous, can_navigate_next).
    Shifts range by window duration when offset is provided, preventing navigation into future dates.
    """
    tz_str = get_app_timezone(db)
    tz = ZoneInfo(tz_str)
    now_local = datetime.now(tz)
    today = now_local.date()

    clean_preset = (preset or "month").strip().lower()
    if clean_preset == "1y":
        clean_preset = "year"
    if clean_preset not in VALID_PRESETS:
        clean_preset = "month"

    nav_offset = int(offset or 0)

    if clean_preset == "day":
        target_d = today + timedelta(days=nav_offset)
        if target_d > today:
            nav_offset = 0
            target_d = today
        start_d = target_d
        end_d = target_d
        can_navigate_next = (today + timedelta(days=nav_offset + 1) <= today)
        can_navigate_previous = True

    elif clean_preset == "week":
        # Monday to Sunday
        base_week_start = today - timedelta(days=today.weekday())
        start_d = base_week_start + timedelta(weeks=nav_offset)
        end_d = start_d + timedelta(days=6)
        if start_d > today:
            nav_offset = 0
            start_d = base_week_start
            end_d = start_d + timedelta(days=6)
        next_week_start = start_d + timedelta(weeks=1)
        can_navigate_next = (next_week_start <= today)
        can_navigate_previous = True

    elif clean_preset == "month":
        # 1st of target month to last day of target month
        cur_total_m = today.year * 12 + (today.month - 1) + nav_offset
        m_year = cur_total_m // 12
        m_month = (cur_total_m % 12) + 1
        start_d = date(m_year, m_month, 1)
        if start_d > today:
            nav_offset = 0
            start_d = date(today.year, today.month, 1)
        _, last_day = calendar.monthrange(start_d.year, start_d.month)
        end_d = date(start_d.year, start_d.month, last_day)

        next_total_m = start_d.year * 12 + (start_d.month - 1) + 1
        next_start = date(next_total_m // 12, (next_total_m % 12) + 1, 1)
        can_navigate_next = (next_start <= today)
        can_navigate_previous = True

    elif clean_preset == "3m":
        cur_end_m = today.year * 12 + (today.month - 1) + (nav_offset * 3)
        cur_start_m = cur_end_m - 2
        start_d = date(cur_start_m // 12, (cur_start_m % 12) + 1, 1)
        if start_d > today:
            nav_offset = 0
            cur_end_m = today.year * 12 + (today.month - 1)
            cur_start_m = cur_end_m - 2
            start_d = date(cur_start_m // 12, (cur_start_m % 12) + 1, 1)
        end_y = cur_end_m // 12
        end_m = (cur_end_m % 12) + 1
        _, last_day = calendar.monthrange(end_y, end_m)
        end_d = date(end_y, end_m, last_day)

        next_start_m = cur_start_m + 3
        next_start = date(next_start_m // 12, (next_start_m % 12) + 1, 1)
        can_navigate_next = (next_start <= today)
        can_navigate_previous = True

    elif clean_preset == "6m":
        cur_end_m = today.year * 12 + (today.month - 1) + (nav_offset * 6)
        cur_start_m = cur_end_m - 5
        start_d = date(cur_start_m // 12, (cur_start_m % 12) + 1, 1)
        if start_d > today:
            nav_offset = 0
            cur_end_m = today.year * 12 + (today.month - 1)
            cur_start_m = cur_end_m - 5
            start_d = date(cur_start_m // 12, (cur_start_m % 12) + 1, 1)
        end_y = cur_end_m // 12
        end_m = (cur_end_m % 12) + 1
        _, last_day = calendar.monthrange(end_y, end_m)
        end_d = date(end_y, end_m, last_day)

        next_start_m = cur_start_m + 6
        next_start = date(next_start_m // 12, (next_start_m % 12) + 1, 1)
        can_navigate_next = (next_start <= today)
        can_navigate_previous = True

    elif clean_preset == "year":
        y = today.year + nav_offset
        if y > today.year:
            nav_offset = 0
            y = today.year
        start_d = date(y, 1, 1)
        end_d = date(y, 12, 31)
        can_navigate_next = (date(y + 1, 1, 1) <= today)
        can_navigate_previous = True

    elif clean_preset == "5y":
        end_y = today.year + (nav_offset * 5)
        start_y = end_y - 4
        if start_y > today.year:
            nav_offset = 0
            end_y = today.year
            start_y = end_y - 4
        start_d = date(start_y, 1, 1)
        end_d = date(end_y, 12, 31)
        can_navigate_next = (date(start_y + 5, 1, 1) <= today)
        can_navigate_previous = True

    elif clean_preset == "all":
        nav_offset = 0
        earliest_tx = db.query(func.min(Transaction.transaction_date)).filter(Transaction.deleted_at.is_(None)).scalar()
        earliest_anchor = db.query(func.min(AccountBalanceAnchor.anchor_date)).scalar()
        candidates = [dt for dt in (earliest_tx, earliest_anchor) if dt is not None]
        if candidates:
            min_dt = min(candidates)
            local_min = min_dt.astimezone(tz) if min_dt.tzinfo else min_dt.replace(tzinfo=timezone.utc).astimezone(tz)
            start_d = local_min.date()
        else:
            start_d = date(today.year, 1, 1)
        _, last_day = calendar.monthrange(today.year, today.month)
        end_d = max(today, date(today.year, today.month, last_day))
        can_navigate_next = False
        can_navigate_previous = False

    elif clean_preset == "custom":
        try:
            base_start = date.fromisoformat(custom_start.strip()) if custom_start else date(today.year, today.month, 1)
        except Exception:
            base_start = date(today.year, today.month, 1)

        try:
            base_end = date.fromisoformat(custom_end.strip()) if custom_end else today
        except Exception:
            base_end = today

        if base_start > base_end:
            base_start, base_end = base_end, base_start

        duration_days = max(1, (base_end - base_start).days + 1)
        start_d = base_start + timedelta(days=nav_offset * duration_days)
        end_d = base_end + timedelta(days=nav_offset * duration_days)

        if start_d > today:
            nav_offset = 0
            start_d = base_start
            end_d = base_end

        next_start = start_d + timedelta(days=duration_days)
        can_navigate_next = (next_start <= today)
        can_navigate_previous = True

    # Convert start of start_d and end of end_d to UTC timestamps
    start_dt_utc = datetime.combine(start_d, time(0, 0, 0), tzinfo=tz).astimezone(timezone.utc)
    end_dt_utc = datetime.combine(end_d, time(23, 59, 59, 999999), tzinfo=tz).astimezone(timezone.utc)

    return clean_preset, start_d, end_d, start_dt_utc, end_dt_utc, tz, nav_offset, can_navigate_previous, can_navigate_next

def generate_intervals(
    start_d: date,
    end_d: date,
    interval_type: str,
    tz: ZoneInfo
) -> List[Dict[str, Any]]:
    """
    Generates deterministic, contiguous, non-overlapping intervals within [start_d, end_d]
    aligned to local calendar boundaries.
    """
    today_local = datetime.now(tz).date()
    buckets: List[Dict[str, Any]] = []

    cur_d = start_d
    clean_interval = (interval_type or "month").strip().lower()
    if clean_interval not in VALID_INTERVALS:
        clean_interval = "month"

    if clean_interval == "day":
        while cur_d <= end_d:
            b_start = cur_d
            b_end = cur_d
            key = cur_d.isoformat()
            label = cur_d.strftime("%d %b")
            is_partial = (cur_d >= today_local)
            partial_label = "Today" if cur_d == today_local else ("Future" if cur_d > today_local else None)

            start_utc = datetime.combine(b_start, time(0, 0, 0), tzinfo=tz).astimezone(timezone.utc)
            end_utc = datetime.combine(b_end, time(23, 59, 59, 999999), tzinfo=tz).astimezone(timezone.utc)
            as_of_utc = min(end_utc, get_now_utc()) if is_partial else end_utc

            buckets.append({
                "key": key,
                "label": label,
                "start_date": b_start.isoformat(),
                "end_date": b_end.isoformat(),
                "start_dt_utc": start_utc,
                "end_dt_utc": end_utc,
                "as_of_utc": as_of_utc,
                "is_partial": is_partial,
                "partial_label": partial_label,
            })
            cur_d += timedelta(days=1)

    elif clean_interval == "week":
        # Align to Monday
        first_monday = cur_d - timedelta(days=cur_d.weekday())
        w_start = first_monday
        while w_start <= end_d:
            w_end = w_start + timedelta(days=6)
            # Clip bounds to selected range for label/display clarity if desired, but keep week intact
            actual_start = max(w_start, start_d)
            actual_end = min(w_end, end_d)

            iso_year, iso_week, _ = w_start.isocalendar()
            key = f"{iso_year}-W{iso_week:02d}"
            label = f"{actual_start.strftime('%d %b')} - {actual_end.strftime('%d %b')}"

            is_partial = (w_start <= today_local <= w_end) or (w_start > today_local)
            partial_label = "Week to date" if (w_start <= today_local <= w_end) else ("Future" if w_start > today_local else None)

            start_utc = datetime.combine(actual_start, time(0, 0, 0), tzinfo=tz).astimezone(timezone.utc)
            end_utc = datetime.combine(actual_end, time(23, 59, 59, 999999), tzinfo=tz).astimezone(timezone.utc)
            as_of_utc = min(end_utc, get_now_utc()) if (w_start <= today_local <= w_end) else end_utc

            buckets.append({
                "key": key,
                "label": label,
                "start_date": actual_start.isoformat(),
                "end_date": actual_end.isoformat(),
                "start_dt_utc": start_utc,
                "end_dt_utc": end_utc,
                "as_of_utc": as_of_utc,
                "is_partial": is_partial,
                "partial_label": partial_label,
            })
            w_start += timedelta(days=7)

    elif clean_interval == "month":
        # 1st of month to last of month
        m_curr = date(cur_d.year, cur_d.month, 1)
        end_month_anchor = date(end_d.year, end_d.month, 1)
        while m_curr <= end_month_anchor:
            _, last_day = calendar.monthrange(m_curr.year, m_curr.month)
            m_end = date(m_curr.year, m_curr.month, last_day)

            actual_start = max(m_curr, start_d)
            actual_end = min(m_end, end_d)

            key = m_curr.strftime("%Y-%m")
            label = m_curr.strftime("%b %Y")

            is_partial = (m_curr.year == today_local.year and m_curr.month == today_local.month) or (m_curr > today_local)
            partial_label = "Month to date" if (m_curr.year == today_local.year and m_curr.month == today_local.month) else ("Future" if m_curr > today_local else None)

            start_utc = datetime.combine(actual_start, time(0, 0, 0), tzinfo=tz).astimezone(timezone.utc)
            end_utc = datetime.combine(actual_end, time(23, 59, 59, 999999), tzinfo=tz).astimezone(timezone.utc)
            as_of_utc = min(end_utc, get_now_utc()) if (m_curr.year == today_local.year and m_curr.month == today_local.month) else end_utc

            buckets.append({
                "key": key,
                "label": label,
                "start_date": actual_start.isoformat(),
                "end_date": actual_end.isoformat(),
                "start_dt_utc": start_utc,
                "end_dt_utc": end_utc,
                "as_of_utc": as_of_utc,
                "is_partial": is_partial,
                "partial_label": partial_label,
            })

            # Advance to next month
            if m_curr.month == 12:
                m_curr = date(m_curr.year + 1, 1, 1)
            else:
                m_curr = date(m_curr.year, m_curr.month + 1, 1)

    elif clean_interval == "quarter":
        # Q1: Jan-Mar, Q2: Apr-Jun, Q3: Jul-Sep, Q4: Oct-Dec
        q_start_month = ((cur_d.month - 1) // 3) * 3 + 1
        q_curr = date(cur_d.year, q_start_month, 1)
        end_q_month = ((end_d.month - 1) // 3) * 3 + 1
        end_q_anchor = date(end_d.year, end_q_month, 1)

        while q_curr <= end_q_anchor:
            q_num = ((q_curr.month - 1) // 3) + 1
            q_end_month = q_num * 3
            _, last_day = calendar.monthrange(q_curr.year, q_end_month)
            q_end = date(q_curr.year, q_end_month, last_day)

            actual_start = max(q_curr, start_d)
            actual_end = min(q_end, end_d)

            key = f"{q_curr.year}-Q{q_num}"
            label = f"Q{q_num} {q_curr.year}"

            is_partial = (q_curr <= today_local <= q_end) or (q_curr > today_local)
            partial_label = "Quarter to date" if (q_curr <= today_local <= q_end) else ("Future" if q_curr > today_local else None)

            start_utc = datetime.combine(actual_start, time(0, 0, 0), tzinfo=tz).astimezone(timezone.utc)
            end_utc = datetime.combine(actual_end, time(23, 59, 59, 999999), tzinfo=tz).astimezone(timezone.utc)
            as_of_utc = min(end_utc, get_now_utc()) if (q_curr <= today_local <= q_end) else end_utc

            buckets.append({
                "key": key,
                "label": label,
                "start_date": actual_start.isoformat(),
                "end_date": actual_end.isoformat(),
                "start_dt_utc": start_utc,
                "end_dt_utc": end_utc,
                "as_of_utc": as_of_utc,
                "is_partial": is_partial,
                "partial_label": partial_label,
            })

            # Advance to next quarter
            if q_end_month == 12:
                q_curr = date(q_curr.year + 1, 1, 1)
            else:
                q_curr = date(q_curr.year, q_end_month + 1, 1)

    elif clean_interval == "year":
        y_curr = cur_d.year
        y_end = end_d.year
        while y_curr <= y_end:
            year_start = date(y_curr, 1, 1)
            year_end = date(y_curr, 12, 31)

            actual_start = max(year_start, start_d)
            actual_end = min(year_end, end_d)

            key = str(y_curr)
            label = str(y_curr)

            is_partial = (y_curr == today_local.year) or (y_curr > today_local.year)
            partial_label = "Year to date" if (y_curr == today_local.year) else ("Future" if y_curr > today_local.year else None)

            start_utc = datetime.combine(actual_start, time(0, 0, 0), tzinfo=tz).astimezone(timezone.utc)
            end_utc = datetime.combine(actual_end, time(23, 59, 59, 999999), tzinfo=tz).astimezone(timezone.utc)
            as_of_utc = min(end_utc, get_now_utc()) if (y_curr == today_local.year) else end_utc

            buckets.append({
                "key": key,
                "label": label,
                "start_date": actual_start.isoformat(),
                "end_date": actual_end.isoformat(),
                "start_dt_utc": start_utc,
                "end_dt_utc": end_utc,
                "as_of_utc": as_of_utc,
                "is_partial": is_partial,
                "partial_label": partial_label,
            })
            y_curr += 1

    return buckets

def _normalize_id_list(
    single_id: Optional[int],
    multi_ids: Optional[List[int]]
) -> List[int]:
    """Normalizes single or multi-select filter IDs into a deduplicated list of ints."""
    result: List[int] = []
    if multi_ids:
        for val in multi_ids:
            if val is not None:
                iv = int(val)
                if iv not in result:
                    result.append(iv)
    elif single_id is not None:
        result.append(int(single_id))
    return result


def _build_category_breakdown_and_matrix(
    category_totals: Dict[Optional[int], Dict[str, Any]],
    grand_total_pence: int,
    time_series_buckets: List[Dict[str, Any]],
    bucket_detail_key: str,
    period_pence_key: str,
    period_pounds_key: str,
    period_fmt_key: str,
    curr_sym: str,
    category_type: str,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Builds a sorted category summary list and period matrix for spending or income."""
    category_list: List[Dict[str, Any]] = []
    for c_data in category_totals.values():
        tot = c_data["total_pence"]
        pct = round((tot / grand_total_pence * 100), 1) if grand_total_pence > 0 else 0.0
        category_list.append({
            "category_id": c_data["category_id"],
            "category_name": c_data["category_name"],
            "category_color": c_data["category_color"],
            "category_type": category_type,
            "expense_nature": c_data["expense_nature"],
            "total_pence": tot,
            "total_pounds": pence_to_pounds(tot),
            "formatted_total": format_pence(tot, curr_sym),
            "percentage": pct,
            "transaction_count": c_data["transaction_count"],
        })
    category_list.sort(key=lambda x: x["total_pence"], reverse=True)

    matrix_periods = [
        {
            "key": b["key"],
            "label": b["label"],
            "start_date": b["start_date"],
            "end_date": b["end_date"],
            "is_partial": b["is_partial"],
            "partial_label": b["partial_label"],
            "period_total_pence": b[period_pence_key],
            "period_total_pounds": b[period_pounds_key],
            "formatted_period_total": b[period_fmt_key],
        }
        for b in time_series_buckets
    ]

    matrix_rows: List[Dict[str, Any]] = []
    for c_data in category_list:
        c_id = c_data["category_id"]
        cells_map: Dict[str, Dict[str, Any]] = {}
        for b in time_series_buckets:
            cat_detail = next((item for item in b.get(bucket_detail_key, []) if item["category_id"] == c_id), None)
            amt = cat_detail["amount_pence"] if cat_detail else 0
            cnt = cat_detail["transaction_count"] if cat_detail else 0
            cells_map[b["key"]] = {
                "amount_pence": amt,
                "amount_pounds": pence_to_pounds(amt),
                "formatted_amount": format_pence(amt, curr_sym),
                "transaction_count": cnt,
            }
        matrix_rows.append({
            "category_id": c_id,
            "category_name": c_data["category_name"],
            "category_color": c_data["category_color"],
            "category_type": category_type,
            "expense_nature": c_data["expense_nature"],
            "is_uncategorized": (c_id is None),
            "row_total_pence": c_data["total_pence"],
            "row_total_pounds": c_data["total_pounds"],
            "formatted_row_total": c_data["formatted_total"],
            "percentage": c_data["percentage"],
            "transaction_count": c_data["transaction_count"],
            "cells": cells_map,
        })

    matrix = {
        "periods": matrix_periods,
        "rows": matrix_rows,
        "grand_total_pence": grand_total_pence,
        "grand_total_pounds": pence_to_pounds(grand_total_pence),
        "formatted_grand_total": format_pence(grand_total_pence, curr_sym),
    }
    return category_list, matrix


def compute_cashflow_and_spending(
    db: Session,
    buckets: List[Dict[str, Any]],
    currency: str,
    account_id: Optional[int] = None,
    category_id: Optional[int] = None,
    account_ids: Optional[List[int]] = None,
    category_ids: Optional[List[int]] = None,
) -> Tuple[Dict[str, Any], List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any]]:
    """
    Computes cash flow and category spending metrics for each bucket and across the entire range.
    Strictly excludes internal transfers (£0 impact).
    Separates reconciliation adjustments.
    Supports both single and multi-select account and category filters (where category ID 0 = Uncategorised).
    """
    totals, time_series_buckets, category_list, spending_matrix, _, _ = _compute_cashflow_and_categories_detailed(
        db=db,
        buckets=buckets,
        currency=currency,
        account_id=account_id,
        category_id=category_id,
        account_ids=account_ids,
        category_ids=category_ids,
    )
    return totals, time_series_buckets, category_list, spending_matrix


def _compute_cashflow_and_categories_detailed(
    db: Session,
    buckets: List[Dict[str, Any]],
    currency: str,
    account_id: Optional[int] = None,
    category_id: Optional[int] = None,
    account_ids: Optional[List[int]] = None,
    category_ids: Optional[List[int]] = None,
) -> Tuple[Dict[str, Any], List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any], List[Dict[str, Any]], Dict[str, Any]]:
    base_curr = get_effective_base_currency(db)
    curr_spec = get_currency_spec(currency)
    curr_sym = get_currency_symbol(currency)

    effective_account_ids = _normalize_id_list(account_id, account_ids)
    effective_category_ids = _normalize_id_list(category_id, category_ids)

    # 1. Fetch relevant categories for color and metadata
    all_categories_list = db.query(Category).order_by(Category.name.asc()).all()
    all_categories = {c.id: c for c in all_categories_list}
    category_colors = {}
    for idx, c in enumerate(all_categories_list):
        category_colors[c.id] = resolve_category_color(c, idx)
    category_colors[None] = "#94A3B8"

    # Initialize overall accumulators
    total_income_pence = 0
    total_fixed_expenses_pence = 0
    total_variable_expenses_pence = 0
    total_unclassified_expenses_pence = 0
    total_transfers_volume_pence = 0
    total_transfers_count = 0
    total_adjustments_inflow_pence = 0
    total_adjustments_outflow_pence = 0
    total_adjustments_count = 0

    category_totals: Dict[Optional[int], Dict[str, Any]] = {}
    income_category_totals: Dict[Optional[int], Dict[str, Any]] = {}

    time_series_buckets: List[Dict[str, Any]] = []
    running_cumulative_income_pence = 0
    running_cumulative_expenses_pence = 0
    running_cumulative_net_flow_pence = 0
    running_cumulative_net_savings_pence = 0
    all_planned_txs: List[Transaction] = []
    app_tz = get_app_timezone(db)
    today_local = get_today_local(app_tz)
    end_of_today_utc = get_end_of_day_utc(today_local, tz_str=app_tz)

    for b in buckets:
        # Build query for this bucket interval (strictly excluding soft-deleted records)
        query = db.query(Transaction).filter(Transaction.deleted_at.is_(None))
        if effective_account_ids:
            query = query.join(Account, Transaction.account_id == Account.id).filter(
                Account.currency == currency,
                Transaction.account_id.in_(effective_account_ids),
                Transaction.transaction_date >= b["start_dt_utc"],
                Transaction.transaction_date <= b["end_dt_utc"]
            )
        else:
            query = query.outerjoin(Account, Transaction.account_id == Account.id).filter(
                Transaction.transaction_date >= b["start_dt_utc"],
                Transaction.transaction_date <= b["end_dt_utc"],
                or_(
                    Account.currency == currency,
                    and_(Transaction.account_id.is_(None), currency == base_curr)
                )
            )

        if effective_category_ids:
            pos_cat_ids = [cid for cid in effective_category_ids if cid > 0]
            include_uncat = (0 in effective_category_ids)
            if pos_cat_ids and include_uncat:
                query = query.filter(
                    or_(
                        Transaction.category_id.in_(pos_cat_ids),
                        Transaction.category_id.is_(None)
                    )
                )
            elif pos_cat_ids:
                query = query.filter(Transaction.category_id.in_(pos_cat_ids))
            elif include_uncat:
                query = query.filter(Transaction.category_id.is_(None))

        txs = query.all()

        actual_txs = []
        planned_txs = []
        for tx in txs:
            eff_utc = ensure_utc(tx.effective_timestamp or tx.transaction_date)
            if eff_utc > end_of_today_utc:
                planned_txs.append(tx)
                all_planned_txs.append(tx)
            else:
                actual_txs.append(tx)

        b_income_pence = 0
        b_fixed_pence = 0
        b_variable_pence = 0
        b_unclassified_pence = 0
        b_transfers_pence = 0
        b_adj_inflow_pence = 0
        b_adj_outflow_pence = 0
        b_category_spending: Dict[str, int] = {}
        b_category_map: Dict[Optional[int], Dict[str, Any]] = {}
        b_income_category_map: Dict[Optional[int], Dict[str, Any]] = {}

        for tx in actual_txs:
            # Rule 1: Internal transfers contribute zero
            if tx.transaction_type == TransactionType.TRANSFER:
                b_transfers_pence += tx.amount_pence
                total_transfers_volume_pence += tx.amount_pence
                total_transfers_count += 1
                continue

            # Rule 2: Operating income from external sources
            if tx.transaction_type == TransactionType.INCOME:
                b_income_pence += tx.amount_pence
                total_income_pence += tx.amount_pence
                cat_obj = all_categories.get(tx.category_id)
                cat_name = cat_obj.name if cat_obj else "Uncategorised"
                c_id = tx.category_id
                if c_id not in b_income_category_map:
                    b_income_category_map[c_id] = {
                        "category_id": c_id,
                        "category_name": cat_name,
                        "category_color": category_colors.get(c_id, "#10B981" if c_id is not None else "#94A3B8"),
                        "category_type": "income",
                        "expense_nature": "unclassified",
                        "amount_pence": 0,
                        "transaction_count": 0,
                    }
                b_income_category_map[c_id]["amount_pence"] += tx.amount_pence
                b_income_category_map[c_id]["transaction_count"] += 1

                if c_id not in income_category_totals:
                    income_category_totals[c_id] = {
                        "category_id": c_id,
                        "category_name": cat_name,
                        "category_color": category_colors.get(c_id, "#10B981" if c_id is not None else "#94A3B8"),
                        "category_type": "income",
                        "expense_nature": "unclassified",
                        "total_pence": 0,
                        "transaction_count": 0,
                    }
                income_category_totals[c_id]["total_pence"] += tx.amount_pence
                income_category_totals[c_id]["transaction_count"] += 1
                continue

            # Rule 3: Operating expenses segmented by expense_nature
            if tx.transaction_type == TransactionType.EXPENSE:
                nature = tx.expense_nature or ExpenseNature.UNCLASSIFIED
                if nature == ExpenseNature.FIXED:
                    b_fixed_pence += tx.amount_pence
                    total_fixed_expenses_pence += tx.amount_pence
                elif nature == ExpenseNature.VARIABLE:
                    b_variable_pence += tx.amount_pence
                    total_variable_expenses_pence += tx.amount_pence
                else:
                    b_unclassified_pence += tx.amount_pence
                    total_unclassified_expenses_pence += tx.amount_pence

                cat_obj = all_categories.get(tx.category_id)
                cat_name = cat_obj.name if cat_obj else "Uncategorised"
                b_category_spending[cat_name] = b_category_spending.get(cat_name, 0) + tx.amount_pence

                c_id = tx.category_id
                if c_id not in b_category_map:
                    b_category_map[c_id] = {
                        "category_id": c_id,
                        "category_name": cat_name,
                        "category_color": category_colors.get(c_id, "#94A3B8"),
                        "expense_nature": (cat_obj.default_expense_nature.value if cat_obj else "unclassified"),
                        "amount_pence": 0,
                        "transaction_count": 0,
                    }
                b_category_map[c_id]["amount_pence"] += tx.amount_pence
                b_category_map[c_id]["transaction_count"] += 1

                if c_id not in category_totals:
                    category_totals[c_id] = {
                        "category_id": c_id,
                        "category_name": cat_name,
                        "category_color": category_colors.get(c_id, "#94A3B8"),
                        "expense_nature": (cat_obj.default_expense_nature.value if cat_obj else "unclassified"),
                        "total_pence": 0,
                        "transaction_count": 0,
                    }
                category_totals[c_id]["total_pence"] += tx.amount_pence
                category_totals[c_id]["transaction_count"] += 1
                continue

            # Rule 4: Reconciliation adjustments / manual corrections
            if tx.transaction_type == TransactionType.ADJUSTMENT:
                total_adjustments_count += 1
                is_pos = bool(tx.notes and "[Positive adjustment]" in tx.notes)
                if is_pos:
                    b_adj_inflow_pence += tx.amount_pence
                    total_adjustments_inflow_pence += tx.amount_pence
                else:
                    b_adj_outflow_pence += tx.amount_pence
                    total_adjustments_outflow_pence += tx.amount_pence

        b_planned_income_pence = 0
        b_planned_expenses_pence = 0
        for tx in planned_txs:
            if tx.transaction_type == TransactionType.INCOME:
                b_planned_income_pence += tx.amount_pence
            elif tx.transaction_type == TransactionType.EXPENSE:
                b_planned_expenses_pence += tx.amount_pence
        b_planned_net_pence = b_planned_income_pence - b_planned_expenses_pence

        b_total_expenses_pence = b_fixed_pence + b_variable_pence + b_unclassified_pence
        b_net_savings_pence = b_income_pence - b_total_expenses_pence
        running_cumulative_income_pence += b_income_pence
        running_cumulative_expenses_pence += b_total_expenses_pence
        running_cumulative_net_flow_pence += b_net_savings_pence
        running_cumulative_net_savings_pence += b_net_savings_pence
        b_adj_net_pence = b_adj_inflow_pence - b_adj_outflow_pence

        if b_income_pence > 0:
            b_savings_rate = round((b_net_savings_pence / b_income_pence) * 100, 1)
            b_is_savings_rate_applicable = True
        else:
            b_savings_rate = 0.0
            b_is_savings_rate_applicable = False

        b_category_details = []
        for c_id, c_info in b_category_map.items():
            amt = c_info["amount_pence"]
            pct = round((amt / b_total_expenses_pence * 100), 1) if b_total_expenses_pence > 0 else 0.0
            b_category_details.append({
                "category_id": c_id,
                "category_name": c_info["category_name"],
                "category_color": c_info["category_color"],
                "category_type": "expense",
                "expense_nature": c_info["expense_nature"],
                "amount_pence": amt,
                "amount_pounds": pence_to_pounds(amt),
                "formatted_amount": format_pence(amt, curr_sym),
                "percentage": pct,
                "transaction_count": c_info["transaction_count"],
            })
        b_category_details.sort(key=lambda x: x["amount_pence"], reverse=True)

        b_income_category_details = []
        for c_id, c_info in b_income_category_map.items():
            amt = c_info["amount_pence"]
            pct = round((amt / b_income_pence * 100), 1) if b_income_pence > 0 else 0.0
            b_income_category_details.append({
                "category_id": c_id,
                "category_name": c_info["category_name"],
                "category_color": c_info["category_color"],
                "category_type": "income",
                "expense_nature": "unclassified",
                "amount_pence": amt,
                "amount_pounds": pence_to_pounds(amt),
                "formatted_amount": format_pence(amt, curr_sym),
                "percentage": pct,
                "transaction_count": c_info["transaction_count"],
            })
        b_income_category_details.sort(key=lambda x: x["amount_pence"], reverse=True)

        b_nature_details = [
            {
                "nature": "fixed",
                "label": "Fixed",
                "color": "#6366F1",
                "amount_pence": b_fixed_pence,
                "amount_pounds": pence_to_pounds(b_fixed_pence),
                "formatted_amount": format_pence(b_fixed_pence, curr_sym),
                "percentage": round((b_fixed_pence / b_total_expenses_pence * 100), 1) if b_total_expenses_pence > 0 else 0.0,
            },
            {
                "nature": "variable",
                "label": "Variable",
                "color": "#F59E0B",
                "amount_pence": b_variable_pence,
                "amount_pounds": pence_to_pounds(b_variable_pence),
                "formatted_amount": format_pence(b_variable_pence, curr_sym),
                "percentage": round((b_variable_pence / b_total_expenses_pence * 100), 1) if b_total_expenses_pence > 0 else 0.0,
            },
            {
                "nature": "unclassified",
                "label": "Unclassified",
                "color": "#94A3B8",
                "amount_pence": b_unclassified_pence,
                "amount_pounds": pence_to_pounds(b_unclassified_pence),
                "formatted_amount": format_pence(b_unclassified_pence, curr_sym),
                "percentage": round((b_unclassified_pence / b_total_expenses_pence * 100), 1) if b_total_expenses_pence > 0 else 0.0,
            },
        ]

        time_series_buckets.append({
            "key": b["key"],
            "label": b["label"],
            "start_date": b["start_date"],
            "end_date": b["end_date"],
            "is_partial": b["is_partial"],
            "partial_label": b["partial_label"],
            "income_pence": b_income_pence,
            "income_pounds": pence_to_pounds(b_income_pence),
            "formatted_income": format_pence(b_income_pence, curr_sym),
            "expenses_pence": b_total_expenses_pence,
            "expenses_pounds": pence_to_pounds(b_total_expenses_pence),
            "formatted_expenses": format_pence(b_total_expenses_pence, curr_sym),
            "net_savings_pence": b_net_savings_pence,
            "net_savings_pounds": pence_to_pounds(b_net_savings_pence),
            "formatted_net_savings": format_pence(b_net_savings_pence, curr_sym),
            "cumulative_net_savings_pence": running_cumulative_net_flow_pence,
            "cumulative_net_savings_pounds": pence_to_pounds(running_cumulative_net_flow_pence),
            "formatted_cumulative_net_savings": format_pence(running_cumulative_net_flow_pence, curr_sym),
            "cumulative_income_pence": running_cumulative_income_pence,
            "cumulative_income_pounds": pence_to_pounds(running_cumulative_income_pence),
            "formatted_cumulative_income": format_pence(running_cumulative_income_pence, curr_sym),
            "cumulative_expenses_pence": running_cumulative_expenses_pence,
            "cumulative_expenses_pounds": pence_to_pounds(running_cumulative_expenses_pence),
            "formatted_cumulative_expenses": format_pence(running_cumulative_expenses_pence, curr_sym),
            "cumulative_net_flow_pence": running_cumulative_net_flow_pence,
            "cumulative_net_flow_pounds": pence_to_pounds(running_cumulative_net_flow_pence),
            "formatted_cumulative_net_flow": format_pence(running_cumulative_net_flow_pence, curr_sym),
            "savings_rate": b_savings_rate,
            "is_savings_rate_applicable": b_is_savings_rate_applicable,
            "transfers_volume_pence": b_transfers_pence,
            "formatted_transfers_volume": format_pence(b_transfers_pence, curr_sym),
            "adjustments_net_pence": b_adj_net_pence,
            "formatted_adjustments_net": format_pence(b_adj_net_pence, curr_sym),
            "fixed_expenses_pence": b_fixed_pence,
            "variable_expenses_pence": b_variable_pence,
            "unclassified_expenses_pence": b_unclassified_pence,
            "planned_income_pence": b_planned_income_pence,
            "planned_expenses_pence": b_planned_expenses_pence,
            "planned_net_pence": b_planned_net_pence,
            "category_spending": b_category_spending,
            "category_spending_details": b_category_details,
            "income_category_details": b_income_category_details,
            "nature_spending_details": b_nature_details,
        })

    # Overall totals across range
    total_expenses_pence = total_fixed_expenses_pence + total_variable_expenses_pence + total_unclassified_expenses_pence
    net_savings_pence = total_income_pence - total_expenses_pence
    total_adj_net_pence = total_adjustments_inflow_pence - total_adjustments_outflow_pence

    if total_income_pence > 0:
        overall_savings_rate = round((net_savings_pence / total_income_pence) * 100, 1)
        is_savings_rate_applicable = True
    else:
        overall_savings_rate = 0.0
        is_savings_rate_applicable = False

    totals = {
        "income_pence": total_income_pence,
        "income_pounds": pence_to_pounds(total_income_pence),
        "formatted_income": format_pence(total_income_pence, curr_sym),
        "expenses_pence": total_expenses_pence,
        "expenses_pounds": pence_to_pounds(total_expenses_pence),
        "formatted_expenses": format_pence(total_expenses_pence, curr_sym),
        "net_savings_pence": net_savings_pence,
        "net_savings_pounds": pence_to_pounds(net_savings_pence),
        "formatted_net_savings": format_pence(net_savings_pence, curr_sym),
        "cumulative_net_savings_pence": running_cumulative_net_flow_pence,
        "cumulative_net_savings_pounds": pence_to_pounds(running_cumulative_net_flow_pence),
        "formatted_cumulative_net_savings": format_pence(running_cumulative_net_flow_pence, curr_sym),
        "cumulative_income_pence": running_cumulative_income_pence,
        "cumulative_income_pounds": pence_to_pounds(running_cumulative_income_pence),
        "formatted_cumulative_income": format_pence(running_cumulative_income_pence, curr_sym),
        "cumulative_expenses_pence": running_cumulative_expenses_pence,
        "cumulative_expenses_pounds": pence_to_pounds(running_cumulative_expenses_pence),
        "formatted_cumulative_expenses": format_pence(running_cumulative_expenses_pence, curr_sym),
        "cumulative_net_flow_pence": running_cumulative_net_flow_pence,
        "cumulative_net_flow_pounds": pence_to_pounds(running_cumulative_net_flow_pence),
        "formatted_cumulative_net_flow": format_pence(running_cumulative_net_flow_pence, curr_sym),
        "savings_rate": overall_savings_rate,
        "is_savings_rate_applicable": is_savings_rate_applicable,
        "fixed_expenses_pence": total_fixed_expenses_pence,
        "formatted_fixed_expenses": format_pence(total_fixed_expenses_pence, curr_sym),
        "fixed_percentage": round((total_fixed_expenses_pence / total_expenses_pence * 100), 1) if total_expenses_pence > 0 else 0.0,
        "variable_expenses_pence": total_variable_expenses_pence,
        "formatted_variable_expenses": format_pence(total_variable_expenses_pence, curr_sym),
        "variable_percentage": round((total_variable_expenses_pence / total_expenses_pence * 100), 1) if total_expenses_pence > 0 else 0.0,
        "unclassified_expenses_pence": total_unclassified_expenses_pence,
        "formatted_unclassified_expenses": format_pence(total_unclassified_expenses_pence, curr_sym),
        "unclassified_percentage": round((total_unclassified_expenses_pence / total_expenses_pence * 100), 1) if total_expenses_pence > 0 else 0.0,
        "transfers_volume_pence": total_transfers_volume_pence,
        "formatted_transfers_volume": format_pence(total_transfers_volume_pence, curr_sym),
        "transfers_count": total_transfers_count,
        "adjustments_inflow_pence": total_adjustments_inflow_pence,
        "adjustments_outflow_pence": total_adjustments_outflow_pence,
        "adjustments_net_pence": total_adj_net_pence,
        "formatted_adjustments_net": format_pence(total_adj_net_pence, curr_sym),
        "adjustments_count": total_adjustments_count,
    }

    forecast_income_pence = sum(t.amount_pence for t in all_planned_txs if t.transaction_type == TransactionType.INCOME)
    forecast_expenses_pence = sum(t.amount_pence for t in all_planned_txs if t.transaction_type == TransactionType.EXPENSE)
    forecast_net_pence = forecast_income_pence - forecast_expenses_pence
    forecast_count = len(all_planned_txs)

    app_tz = get_app_timezone(db)
    app_zi = ZoneInfo(app_tz)
    acc_map = {a.id: a.name for a in db.query(Account).all()}

    planned_items = []
    for t in sorted(all_planned_txs, key=lambda x: (ensure_utc(x.effective_timestamp or x.transaction_date), x.id)):
        acc_name = acc_map.get(t.account_id, "Unassigned") if t.account_id else "Unassigned"
        cat_obj = all_categories.get(t.category_id)
        cat_name = cat_obj.name if cat_obj else "Uncategorised"
        tx_dt = ensure_utc(t.transaction_date).astimezone(app_zi)
        planned_items.append({
            "id": t.id,
            "date": tx_dt.strftime("%Y-%m-%d"),
            "transaction_type": t.transaction_type.value,
            "merchant": t.merchant or "",
            "account_name": acc_name,
            "category_name": cat_name,
            "expense_nature": (t.expense_nature.value if t.expense_nature else "unclassified"),
            "amount_pence": t.amount_pence,
            "amount_pounds": pence_to_pounds(t.amount_pence),
            "formatted_amount": format_pence(t.amount_pence, curr_sym),
            "notes": t.notes or "",
        })

    totals["forecast"] = {
        "has_planned_activity": forecast_count > 0,
        "planned_income_pence": forecast_income_pence,
        "planned_income_pounds": pence_to_pounds(forecast_income_pence),
        "formatted_planned_income": format_pence(forecast_income_pence, curr_sym),
        "planned_expenses_pence": forecast_expenses_pence,
        "planned_expenses_pounds": pence_to_pounds(forecast_expenses_pence),
        "formatted_planned_expenses": format_pence(forecast_expenses_pence, curr_sym),
        "planned_net_pence": forecast_net_pence,
        "planned_net_pounds": pence_to_pounds(forecast_net_pence),
        "formatted_planned_net": format_pence(forecast_net_pence, curr_sym),
        "planned_transactions_count": forecast_count,
        "items": planned_items,
    }

    category_list, spending_matrix = _build_category_breakdown_and_matrix(
        category_totals=category_totals,
        grand_total_pence=total_expenses_pence,
        time_series_buckets=time_series_buckets,
        bucket_detail_key="category_spending_details",
        period_pence_key="expenses_pence",
        period_pounds_key="expenses_pounds",
        period_fmt_key="formatted_expenses",
        curr_sym=curr_sym,
        category_type="expense",
    )

    income_category_list, income_matrix = _build_category_breakdown_and_matrix(
        category_totals=income_category_totals,
        grand_total_pence=total_income_pence,
        time_series_buckets=time_series_buckets,
        bucket_detail_key="income_category_details",
        period_pence_key="income_pence",
        period_pounds_key="income_pounds",
        period_fmt_key="formatted_income",
        curr_sym=curr_sym,
        category_type="income",
    )

    return totals, time_series_buckets, category_list, spending_matrix, income_category_list, income_matrix

def compute_balances_and_net_worth(
    db: Session,
    buckets: List[Dict[str, Any]],
    currency: str,
    account_id: Optional[int] = None,
    account_ids: Optional[List[int]] = None,
) -> List[Dict[str, Any]]:
    """
    Computes period-end account balances and net worth trajectory across buckets.
    - Honors balance-anchor cutoff and retrospective inference rules.
    - Marks inferred balances prior to earliest anchor with warning.
    - Captures observational reconciliation snapshots and discrepancies without distorting ledger.
    """
    curr_sym = get_currency_symbol(currency)
    effective_account_ids = _normalize_id_list(account_id, account_ids)

    # Fetch accounts to evaluate
    acc_query = db.query(Account).filter(Account.currency == currency, Account.is_active == True)
    if effective_account_ids:
        acc_query = acc_query.filter(Account.id.in_(effective_account_ids))
    accounts = acc_query.order_by(Account.account_type.asc(), Account.name.asc()).all()

    # Pre-fetch earliest anchor for each account to identify inferred history
    earliest_anchors: Dict[int, Optional[AccountBalanceAnchor]] = {}
    for acc in accounts:
        if acc.account_type != AccountType.INVESTMENT:
            a = db.query(AccountBalanceAnchor).filter(
                AccountBalanceAnchor.account_id == acc.id
            ).order_by(AccountBalanceAnchor.anchor_date.asc(), AccountBalanceAnchor.id.asc()).first()
            earliest_anchors[acc.id] = a
        else:
            earliest_anchors[acc.id] = None

    net_worth_buckets: List[Dict[str, Any]] = []

    for b in buckets:
        as_of = ensure_utc(b["as_of_utc"])

        account_balances: List[Dict[str, Any]] = []
        total_assets_pence = 0
        total_debt_pence = 0
        has_inferred = False

        for acc in accounts:
            bal_pence = LedgerEngine.get_account_balance(db, acc.id, as_of=as_of)
            e_anchor = earliest_anchors.get(acc.id)
            e_anchor_date = ensure_utc(e_anchor.anchor_date) if e_anchor else None

            is_inferred = False
            inferred_warning = None
            if e_anchor_date and as_of < e_anchor_date:
                is_inferred = True
                has_inferred = True
                inferred_warning = (
                    f"Calculated balance prior to opening balance anchor ({e_anchor_date.strftime('%d/%m/%Y')}); "
                    "inferred from reverse transactions."
                )

            # Check for reconciliation snapshot taken on or near this period end
            snap = db.query(AccountSnapshot).filter(
                AccountSnapshot.account_id == acc.id,
                AccountSnapshot.snapshot_date <= as_of
            ).order_by(AccountSnapshot.snapshot_date.desc(), AccountSnapshot.id.desc()).first()

            snap_disc_pence = None
            snap_actual_pence = None
            if snap:
                snap_dt = ensure_utc(snap.snapshot_date)
                if snap_dt and (as_of - snap_dt).total_seconds() < 86400 * 35:
                    # Found snapshot within reasonable proximity (trailing 35 days)
                    snap_disc_pence = snap.discrepancy_pence
                    snap_actual_pence = snap.actual_balance_pence

            # Aggregate assets vs debt
            if acc.account_type == AccountType.CREDIT_CARD:
                total_debt_pence += abs(bal_pence)
            else:
                total_assets_pence += bal_pence

            account_balances.append({
                "account_id": acc.id,
                "account_name": acc.name,
                "account_type": acc.account_type.value,
                "color": acc.color,
                "balance_pence": bal_pence,
                "balance_pounds": pence_to_pounds(bal_pence),
                "formatted_balance": format_pence(bal_pence, curr_sym),
                "is_inferred": is_inferred,
                "inferred_warning": inferred_warning,
                "reconciliation_discrepancy_pence": snap_disc_pence,
                "reconciliation_actual_pence": snap_actual_pence,
            })

        net_worth_pence = total_assets_pence - total_debt_pence

        net_worth_buckets.append({
            "key": b["key"],
            "label": b["label"],
            "date": b["end_date"],
            "is_partial": b["is_partial"],
            "partial_label": b["partial_label"],
            "total_assets_pence": total_assets_pence,
            "total_assets_pounds": pence_to_pounds(total_assets_pence),
            "formatted_total_assets": format_pence(total_assets_pence, curr_sym),
            "total_debt_pence": total_debt_pence,
            "total_debt_pounds": pence_to_pounds(total_debt_pence),
            "formatted_total_debt": format_pence(total_debt_pence, curr_sym),
            "net_worth_pence": net_worth_pence,
            "net_worth_pounds": pence_to_pounds(net_worth_pence),
            "formatted_net_worth": format_pence(net_worth_pence, curr_sym),
            "account_balances": account_balances,
            "has_inferred_balances": has_inferred,
        })

    return net_worth_buckets

def compute_portfolio_value_history(
    db: Session,
    buckets: List[Dict[str, Any]],
    currency: str,
    account_id: Optional[int] = None,
    account_ids: Optional[List[int]] = None,
) -> Tuple[List[Dict[str, Any]], bool, Optional[str]]:
    """
    Computes dated portfolio valuation history across buckets.
    - Strictly labeled as 'portfolio value history', not returns or performance.
    - Uses each holding's latest valuation on or before the period end.
    - Detects sparse valuation checkpoints and provides clear contextual explanation.
    """
    curr_sym = get_currency_symbol(currency)
    effective_account_ids = _normalize_id_list(account_id, account_ids)

    inv_query = db.query(Account).filter(
        Account.account_type == AccountType.INVESTMENT,
        Account.currency == currency,
        Account.is_active == True
    )
    if effective_account_ids:
        inv_query = inv_query.filter(Account.id.in_(effective_account_ids))
    inv_accounts = inv_query.order_by(Account.name.asc()).all()

    if not inv_accounts:
        return [], False, None

    inv_acc_ids = [a.id for a in inv_accounts]

    # Check valuation checkpoint frequency across holdings in these accounts
    total_valuations_count = db.query(HoldingValuation).join(
        Holding, HoldingValuation.holding_id == Holding.id
    ).filter(
        Holding.account_id.in_(inv_acc_ids)
    ).count()

    total_active_holdings_count = db.query(Holding).filter(
        Holding.account_id.in_(inv_acc_ids),
        Holding.is_active == True
    ).count()

    is_sparse = (total_valuations_count <= max(1, len(buckets) // 3))
    sparse_explanation = None
    if is_sparse and total_active_holdings_count > 0:
        sparse_explanation = (
            "Valuation checkpoints are infrequent or sparse. Holding values are carried forward from the latest "
            "recorded valuation on or before each period end."
        )

    portfolio_series: List[Dict[str, Any]] = []

    for b in buckets:
        as_of = ensure_utc(b["as_of_utc"])
        b_start_utc = ensure_utc(b["start_dt_utc"])

        bucket_valued_count = 0
        bucket_unvalued_count = 0
        account_details = []
        all_checkpoint_dates = []

        for acc in inv_accounts:
            bd = get_account_holdings_breakdown(db, acc.id, as_of_date=as_of)
            bucket_valued_count += bd["valued_count"]
            bucket_unvalued_count += bd["unvalued_count"]

            acc_checkpoint_dates = [
                ensure_utc(d["latest_valuation"].effective_date)
                for d in bd["details"]
                if d.get("latest_valuation") is not None
            ]
            all_checkpoint_dates.extend(acc_checkpoint_dates)

            if acc_checkpoint_dates:
                acc_latest_cp = max(acc_checkpoint_dates)
                acc_is_available = True
                acc_is_cf = (acc_latest_cp < b_start_utc)
                acc_val_date = acc_latest_cp.strftime("%d/%m/%Y")
                acc_cf_date = acc_val_date if acc_is_cf else None
                acc_val_pence = bd["total_pence"]
                acc_val_pounds = pence_to_pounds(bd["total_pence"])
                acc_fmt_val = format_pence(bd["total_pence"], curr_sym)
            else:
                acc_is_available = False
                acc_is_cf = False
                acc_val_date = None
                acc_cf_date = None
                acc_val_pence = None
                acc_val_pounds = None
                acc_fmt_val = "Unavailable"

            account_details.append({
                "account_id": acc.id,
                "account_name": acc.name,
                "is_available": acc_is_available,
                "is_carried_forward": acc_is_cf,
                "valuation_date": acc_val_date,
                "carried_forward_date": acc_cf_date,
                "valuation_pence": acc_val_pence,
                "valuation_pounds": acc_val_pounds,
                "formatted_valuation": acc_fmt_val,
                "holdings_count": bd["holdings_count"],
                "valued_count": bd["valued_count"],
                "unvalued_count": bd["unvalued_count"],
            })

        if all_checkpoint_dates:
            bucket_max_cp = max(all_checkpoint_dates)
            bucket_is_available = True
            bucket_is_cf = (bucket_max_cp < b_start_utc)
            bucket_val_date = bucket_max_cp.strftime("%d/%m/%Y")
            bucket_cf_date = bucket_val_date if bucket_is_cf else None
            bucket_total_pence = sum(acc["valuation_pence"] for acc in account_details if acc["valuation_pence"] is not None)
            bucket_total_pounds = pence_to_pounds(bucket_total_pence)
            bucket_fmt_val = format_pence(bucket_total_pence, curr_sym)
        else:
            bucket_is_available = False
            bucket_is_cf = False
            bucket_val_date = None
            bucket_cf_date = None
            bucket_total_pence = None
            bucket_total_pounds = None
            bucket_fmt_val = "Unavailable"

        portfolio_series.append({
            "key": b["key"],
            "label": b["label"],
            "date": b["end_date"],
            "is_partial": b["is_partial"],
            "partial_label": b["partial_label"],
            "is_available": bucket_is_available,
            "is_carried_forward": bucket_is_cf,
            "valuation_date": bucket_val_date,
            "carried_forward_date": bucket_cf_date,
            "total_valuation_pence": bucket_total_pence,
            "total_valuation_pounds": bucket_total_pounds,
            "formatted_total_valuation": bucket_fmt_val,
            "holdings_count": bucket_valued_count + bucket_unvalued_count,
            "valued_count": bucket_valued_count,
            "unvalued_count": bucket_unvalued_count,
            "has_unvalued_holdings": bucket_unvalued_count > 0,
            "accounts": account_details,
        })

    return portfolio_series, is_sparse, sparse_explanation

def get_comprehensive_analysis(
    db: Session,
    preset: Optional[str] = "month",
    custom_start: Optional[str] = None,
    custom_end: Optional[str] = None,
    interval: Optional[str] = None,
    currency_param: Optional[str] = None,
    account_id: Optional[int] = None,
    category_id: Optional[int] = None,
    offset: Optional[int] = 0,
    account_ids: Optional[List[int]] = None,
    category_ids: Optional[List[int]] = None,
) -> Dict[str, Any]:
    """
    Main orchestration endpoint delivering unified multidimensional analysis:
    - Date range resolution in application timezone with period navigation offsets
    - Automatic or explicit interval bucketing
    - Overview & Cash Flow (with zero transfer impact)
    - Spending analysis (Category & Nature breakdowns)
    - Balances & Net Worth (Anchor-aware, inferred-safe)
    - Investments (Portfolio value history, sparse-checkpoint aware)
    """
    # 1. Resolve currency
    base_curr = get_effective_base_currency(db)
    available_currencies = get_available_currencies(db)
    clean_curr = (currency_param or base_curr).strip().upper()
    if clean_curr not in available_currencies:
        clean_curr = base_curr

    effective_account_ids = _normalize_id_list(account_id, account_ids)
    effective_category_ids = _normalize_id_list(category_id, category_ids)

    # 2. Resolve date range
    clean_preset, start_d, end_d, start_dt_utc, end_dt_utc, tz, nav_offset, can_prev, can_next = resolve_date_range(
        db, preset=preset, custom_start=custom_start, custom_end=custom_end, offset=offset
    )

    # 3. Resolve aggregation interval
    if interval and interval.strip().lower() in VALID_INTERVALS:
        clean_interval = interval.strip().lower()
    else:
        clean_interval = get_default_interval_for_preset(clean_preset, start_d, end_d)

    # 4. Generate buckets
    buckets = generate_intervals(start_d, end_d, clean_interval, tz)

    # 5. Compute Cash Flow, Spending & Income Category Breakdowns
    totals, time_series_buckets, category_list, spending_matrix, income_category_list, income_matrix = (
        _compute_cashflow_and_categories_detailed(
            db,
            buckets,
            clean_curr,
            account_id=account_id,
            category_id=category_id,
            account_ids=effective_account_ids,
            category_ids=effective_category_ids,
        )
    )
    forecast_data = totals.pop("forecast", None)

    # 6. Compute Balances and Net Worth
    net_worth_series = compute_balances_and_net_worth(
        db, buckets, clean_curr, account_id=account_id, account_ids=effective_account_ids
    )

    # 7. Compute Investment Portfolio Value History
    portfolio_series, is_inv_sparse, inv_sparse_explanation = compute_portfolio_value_history(
        db, buckets, clean_curr, account_id=account_id, account_ids=effective_account_ids
    )

    # 8. Available accounts and categories for filtering
    all_active_accounts = db.query(Account).filter(Account.is_active == True).order_by(Account.name.asc()).all()
    active_accounts = [
        {
            "id": a.id,
            "name": a.name,
            "currency": a.currency,
            "account_type": a.account_type.value,
            "color": a.color or "#6B7280",
        }
        for a in all_active_accounts
    ]
    all_active_categories = db.query(Category).filter(Category.is_active == True).order_by(Category.name.asc()).all()
    active_categories = []
    for idx, c in enumerate(all_active_categories):
        cat_type_val = (c.category_type.value if getattr(c, "category_type", None) else "expense")
        active_categories.append({
            "id": c.id,
            "name": c.name,
            "color": resolve_category_color(c, idx),
            "default_nature": "unclassified" if cat_type_val == "income" else c.default_expense_nature.value,
            "category_type": cat_type_val,
        })

    acc_lookup = {a.id: a.name for a in db.query(Account).all()}
    selected_account_names = [acc_lookup[aid] for aid in effective_account_ids if aid in acc_lookup]
    resolved_single_account_id = effective_account_ids[0] if len(effective_account_ids) == 1 else account_id
    selected_account_name = (
        selected_account_names[0]
        if len(selected_account_names) == 1
        else (", ".join(selected_account_names) if selected_account_names else None)
    )

    cat_lookup = {c.id: c.name for c in db.query(Category).all()}
    cat_lookup[0] = "Uncategorised"
    selected_category_names = [cat_lookup[cid] for cid in effective_category_ids if cid in cat_lookup]
    resolved_single_category_id = effective_category_ids[0] if len(effective_category_ids) == 1 else category_id
    selected_category_name = (
        selected_category_names[0]
        if len(selected_category_names) == 1
        else (", ".join(selected_category_names) if selected_category_names else None)
    )

    return {
        "range_info": {
            "preset": clean_preset,
            "offset": nav_offset,
            "can_navigate_previous": can_prev,
            "can_navigate_next": can_next,
            "interval": clean_interval,
            "start_date": start_d.isoformat(),
            "end_date": end_d.isoformat(),
            "app_timezone": str(tz),
            "available_presets": VALID_PRESETS,
            "available_intervals": VALID_INTERVALS,
        },
        "currency": clean_curr,
        "currency_symbol": get_currency_symbol(clean_curr),
        "available_currencies": available_currencies,
        "account_id": resolved_single_account_id,
        "account_name": selected_account_name,
        "account_ids": effective_account_ids,
        "account_names": selected_account_names,
        "category_id": resolved_single_category_id,
        "category_name": selected_category_name,
        "category_ids": effective_category_ids,
        "category_names": selected_category_names,
        "available_accounts": active_accounts,
        "available_categories": active_categories,
        "totals": totals,
        "time_series": time_series_buckets,
        "categories": category_list,
        "spending_matrix": spending_matrix,
        "income_categories": income_category_list,
        "income_matrix": income_matrix,
        "net_worth_series": net_worth_series,
        "investments_series": portfolio_series,
        "is_investments_sparse": is_inv_sparse,
        "investments_sparse_explanation": inv_sparse_explanation,
        "forecast": forecast_data,
    }


VALID_EXPORT_FORMATS = ["csv", "xlsx"]
VALID_EXPORT_REPORTS = [
    "spending_matrix",
    "income_matrix",
    "overview_cashflow",
    "spending_categories",
    "income_categories",
    "net_worth",
    "investments",
]

PRESET_DISPLAY_LABELS = {
    "day": "Single Day",
    "week": "Weekly Window",
    "month": "Monthly Window",
    "3m": "3 Months",
    "6m": "6 Months",
    "year": "1 Year",
    "5y": "5 Years",
    "all": "All Time",
    "custom": "Custom Date Range",
}

INTERVAL_DISPLAY_LABELS = {
    "day": "Daily",
    "week": "Weekly",
    "month": "Monthly",
    "quarter": "Quarterly",
    "year": "Yearly",
}


def generate_analysis_export(
    db: Session,
    report_type: str = "spending_matrix",
    export_format: str = "xlsx",
    preset: Optional[str] = "month",
    custom_start: Optional[str] = None,
    custom_end: Optional[str] = None,
    interval: Optional[str] = None,
    currency_param: Optional[str] = None,
    account_id: Optional[int] = None,
    category_id: Optional[int] = None,
    offset: Optional[int] = 0,
    account_ids: Optional[List[int]] = None,
    category_ids: Optional[List[int]] = None,
) -> Tuple[bytes, str, str]:
    """
    Generates a profile-scoped CSV or XLSX export for an Analysis table.
    - Reflects the full current date range, group-by interval, and account/category filters.
    - Includes report title, selected date range, applied filters, readable period & category names,
      and row/column/grand totals.
    - For XLSX: produces a formatted workbook with frozen headers & first column, auto-filter,
      sensible column widths, styled totals, and strict numeric cell values (never currency strings).
    """
    import csv
    import io
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter

    clean_format = (export_format or "xlsx").strip().lower()
    if clean_format not in VALID_EXPORT_FORMATS:
        clean_format = "xlsx"

    clean_report = (report_type or "spending_matrix").strip().lower()
    if clean_report not in VALID_EXPORT_REPORTS:
        clean_report = "spending_matrix"

    data = get_comprehensive_analysis(
        db,
        preset=preset,
        custom_start=custom_start,
        custom_end=custom_end,
        interval=interval,
        currency_param=currency_param,
        account_id=account_id,
        category_id=category_id,
        offset=offset,
        account_ids=account_ids,
        category_ids=category_ids,
    )

    range_info = data["range_info"]
    curr = data["currency"]
    sym = data["currency_symbol"]
    start_str = range_info["start_date"]
    end_str = range_info["end_date"]
    preset_label = PRESET_DISPLAY_LABELS.get(range_info["preset"], range_info["preset"])
    interval_label = INTERVAL_DISPLAY_LABELS.get(range_info["interval"], range_info["interval"])
    tz_label = range_info["app_timezone"]

    acc_names = data.get("account_names") or []
    acc_filter_str = ", ".join(acc_names) if acc_names else f"All Accounts ({curr})"

    cat_names = data.get("category_names") or []
    cat_filter_str = ", ".join(cat_names) if cat_names else "All Categories"

    headers: List[str] = []
    col_types: List[str] = []
    data_rows: List[List[Any]] = []
    total_row: Optional[List[Any]] = None

    if clean_report in ("spending_matrix", "income_matrix"):
        is_income_rep = clean_report == "income_matrix"
        report_title = (
            "Finance Hub — Income Category Matrix by Period"
            if is_income_rep
            else "Finance Hub — Category Spending Matrix by Period"
        )
        sheet_name = "Income Matrix" if is_income_rep else "Spending Matrix"
        matrix = data["income_matrix"] if is_income_rep else data["spending_matrix"]
        periods = matrix["periods"]
        second_col = "Purpose" if is_income_rep else "Expense Nature"
        headers = ["Category", second_col] + [p["label"] for p in periods] + ["Row Total", "Share (%)", "Transactions"]
        col_types = ["text", "text"] + ["currency"] * len(periods) + ["currency", "percent", "integer"]

        for r in matrix["rows"]:
            second_val = "Income" if is_income_rep else (str(r.get("expense_nature") or "unclassified")).capitalize()
            p_vals = [
                round(r["cells"].get(p["key"], {}).get("amount_pence", 0) / 100.0, 2)
                for p in periods
            ]
            row_tot = round(r["row_total_pence"] / 100.0, 2)
            pct = float(r["percentage"])
            tx_cnt = int(r["transaction_count"])
            data_rows.append([r["category_name"], second_val] + p_vals + [row_tot, pct, tx_cnt])

        period_totals = [round(p["period_total_pence"] / 100.0, 2) for p in periods]
        grand_tot = round(matrix["grand_total_pence"] / 100.0, 2)
        total_tx = sum(int(r["transaction_count"]) for r in matrix["rows"])
        total_row = (
            ["Period Total / Grand Total", "All"]
            + period_totals
            + [grand_tot, 100.0 if grand_tot > 0 else 0.0, total_tx]
        )

    elif clean_report == "overview_cashflow":
        report_title = "Finance Hub — Cash Flow & Cumulative Trajectory by Period"
        sheet_name = "Cash Flow History"
        headers = [
            "Period",
            "Start Date",
            "End Date",
            "Status",
            "Operating Income",
            "Operating Spending",
            "Net Operating Savings",
            "Cumulative Income",
            "Cumulative Spending",
            "Cumulative Net Flow",
            "Savings Rate (%)",
            "Internal Transfers (Excluded)",
            "Reconciliation Adjustments",
        ]
        col_types = [
            "text", "text", "text", "text",
            "currency", "currency", "currency",
            "currency", "currency", "currency",
            "percent", "currency", "currency",
        ]
        for b in data["time_series"]:
            status = b["partial_label"] if (b.get("is_partial") and b.get("partial_label")) else ("Partial" if b.get("is_partial") else "Complete")
            data_rows.append([
                b["label"],
                b["start_date"],
                b["end_date"],
                status,
                round(b["income_pence"] / 100.0, 2),
                round(b["expenses_pence"] / 100.0, 2),
                round(b["net_savings_pence"] / 100.0, 2),
                round(b["cumulative_income_pence"] / 100.0, 2),
                round(b["cumulative_expenses_pence"] / 100.0, 2),
                round(b["cumulative_net_flow_pence"] / 100.0, 2),
                float(b["savings_rate"]) if b["is_savings_rate_applicable"] else None,
                round(b["transfers_volume_pence"] / 100.0, 2),
                round(b["adjustments_net_pence"] / 100.0, 2),
            ])
        t = data["totals"]
        total_row = [
            "Range Total",
            start_str,
            end_str,
            "Summary",
            round(t["income_pence"] / 100.0, 2),
            round(t["expenses_pence"] / 100.0, 2),
            round(t["net_savings_pence"] / 100.0, 2),
            round(t["cumulative_income_pence"] / 100.0, 2),
            round(t["cumulative_expenses_pence"] / 100.0, 2),
            round(t["cumulative_net_flow_pence"] / 100.0, 2),
            float(t["savings_rate"]) if t["is_savings_rate_applicable"] else None,
            round(t["transfers_volume_pence"] / 100.0, 2),
            round(t["adjustments_net_pence"] / 100.0, 2),
        ]

    elif clean_report in ("spending_categories", "income_categories"):
        is_income_rep = clean_report == "income_categories"
        report_title = (
            "Finance Hub — Income Category Summary"
            if is_income_rep
            else "Finance Hub — Category Outflow Summary"
        )
        sheet_name = "Income Breakdown" if is_income_rep else "Category Breakdown"
        second_col = "Purpose" if is_income_rep else "Expense Nature"
        cat_rows = data["income_categories"] if is_income_rep else data["categories"]
        headers = ["Category", second_col, "Transactions", "Total" if is_income_rep else "Total Spend", "Share (%)"]
        col_types = ["text", "text", "integer", "currency", "percent"]
        for c in cat_rows:
            data_rows.append([
                c["category_name"],
                "Income" if is_income_rep else (str(c.get("expense_nature") or "unclassified")).capitalize(),
                int(c["transaction_count"]),
                round(c["total_pence"] / 100.0, 2),
                float(c["percentage"]),
            ])
        t = data["totals"]
        total_tx = sum(int(c["transaction_count"]) for c in cat_rows)
        grand_pence = t["income_pence"] if is_income_rep else t["expenses_pence"]
        total_row = [
            "Grand Total",
            "All",
            total_tx,
            round(grand_pence / 100.0, 2),
            100.0 if grand_pence > 0 else 0.0,
        ]

    elif clean_report == "net_worth":
        report_title = "Finance Hub — Balances & Net Worth History by Period"
        sheet_name = "Balances & Net Worth"
        nw_series = data["net_worth_series"]
        acc_cols = nw_series[0]["account_balances"] if nw_series else []
        headers = (
            ["Period", "As of Date", "Provenance", "Gross Assets", "Total Liabilities", "Net Worth"]
            + [f"{a['account_name']} ({a['account_type']})" for a in acc_cols]
        )
        col_types = ["text", "text", "text", "currency", "currency", "currency"] + ["currency"] * len(acc_cols)
        for b in nw_series:
            prov = "Includes Inferred Pre-Anchor Balance" if b.get("has_inferred_balances") else "Anchor-Verified"
            acc_map_b = {ab["account_id"]: round(ab["balance_pence"] / 100.0, 2) for ab in b.get("account_balances", [])}
            acc_vals = [acc_map_b.get(a["account_id"], 0.0) for a in acc_cols]
            data_rows.append([
                b["label"],
                b["date"],
                prov,
                round(b["total_assets_pence"] / 100.0, 2),
                round(b["total_debt_pence"] / 100.0, 2),
                round(b["net_worth_pence"] / 100.0, 2),
            ] + acc_vals)
        if nw_series:
            last_b = nw_series[-1]
            last_acc_map = {ab["account_id"]: round(ab["balance_pence"] / 100.0, 2) for ab in last_b.get("account_balances", [])}
            total_row = [
                "Latest Period End",
                last_b["date"],
                "Closing Position",
                round(last_b["total_assets_pence"] / 100.0, 2),
                round(last_b["total_debt_pence"] / 100.0, 2),
                round(last_b["net_worth_pence"] / 100.0, 2),
            ] + [last_acc_map.get(a["account_id"], 0.0) for a in acc_cols]

    else:  # investments
        report_title = "Finance Hub — Investment Portfolio Valuation History by Period"
        sheet_name = "Investments History"
        inv_series = data["investments_series"]
        inv_acc_cols = inv_series[0]["accounts"] if inv_series else []
        headers = (
            ["Period", "As of Date", "Checkpoint Status", "Valued Holdings", "Total Holdings", "Total Portfolio Value"]
            + [a["account_name"] for a in inv_acc_cols]
        )
        col_types = ["text", "text", "text", "integer", "integer", "currency"] + ["currency"] * len(inv_acc_cols)
        for b in inv_series:
            if not b["is_available"]:
                status = "Unavailable (No Checkpoint)"
            elif b["is_carried_forward"]:
                status = f"Carried forward from {b['carried_forward_date']}"
            else:
                status = f"Checkpoint on {b['valuation_date']}"
            tot_val = round(b["total_valuation_pence"] / 100.0, 2) if (b["is_available"] and b["total_valuation_pence"] is not None) else None
            acc_map_b = {
                ia["account_id"]: (round(ia["valuation_pence"] / 100.0, 2) if ia["is_available"] and ia["valuation_pence"] is not None else None)
                for ia in b.get("accounts", [])
            }
            acc_vals = [acc_map_b.get(a["account_id"], None) for a in inv_acc_cols]
            data_rows.append([
                b["label"],
                b["date"],
                status,
                int(b["valued_count"]),
                int(b["holdings_count"]),
                tot_val,
            ] + acc_vals)
        if inv_series:
            last_b = inv_series[-1]
            last_tot = round(last_b["total_valuation_pence"] / 100.0, 2) if (last_b["is_available"] and last_b["total_valuation_pence"] is not None) else None
            last_acc_map = {
                ia["account_id"]: (round(ia["valuation_pence"] / 100.0, 2) if ia["is_available"] and ia["valuation_pence"] is not None else None)
                for ia in last_b.get("accounts", [])
            }
            total_row = [
                "Latest Period End",
                last_b["date"],
                "Closing Valuation",
                int(last_b["valued_count"]),
                int(last_b["holdings_count"]),
                last_tot,
            ] + [last_acc_map.get(a["account_id"], None) for a in inv_acc_cols]

    metadata_rows = [
        [report_title],
        ["Date Range", f"{start_str} to {end_str} ({preset_label})"],
        ["Group By Interval", f"{interval_label} (Timezone: {tz_label})"],
        ["Currency", f"{curr} ({sym})"],
        ["Account Filter", acc_filter_str],
        ["Category Filter", cat_filter_str],
        [],
    ]

    filename_base = f"finance_hub_{clean_report}_{start_str}_to_{end_str}"

    if clean_format == "csv":
        sio = io.StringIO()
        writer = csv.writer(sio)
        for mrow in metadata_rows:
            writer.writerow(mrow)
        writer.writerow(headers)

        def _format_csv_cell(val: Any, ctype: str) -> str:
            if val is None:
                return "Unavailable" if ctype == "currency" else "N/A"
            if ctype == "currency":
                pence_int = int(round(float(val) * 100))
                return format_pence(pence_int, sym)
            if ctype == "percent":
                return f"{float(val):.1f}%"
            return str(val)

        for drow in data_rows:
            writer.writerow([_format_csv_cell(v, col_types[i]) for i, v in enumerate(drow)])

        if total_row is not None:
            writer.writerow([_format_csv_cell(v, col_types[i]) for i, v in enumerate(total_row)])

        csv_bytes = sio.getvalue().encode("utf-8-sig")
        return csv_bytes, f"{filename_base}.csv", "text/csv; charset=utf-8"

    # Build polished XLSX workbook with openpyxl
    wb = Workbook()
    ws = wb.active
    ws.title = sheet_name[:31]

    title_font = Font(name="Calibri", size=13, bold=True, color="0F172A")
    meta_label_font = Font(name="Calibri", size=10, bold=True, color="475569")
    meta_val_font = Font(name="Calibri", size=10, bold=False, color="1E293B")
    header_font = Font(name="Calibri", size=10, bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid")
    data_font = Font(name="Calibri", size=10, bold=False, color="0F172A")
    first_col_font = Font(name="Calibri", size=10, bold=True, color="0F172A")
    total_font = Font(name="Calibri", size=10, bold=True, color="0F172A")
    total_fill = PatternFill(start_color="F1F5F9", end_color="F1F5F9", fill_type="solid")
    zebra_fill = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")

    thin_side = Side(border_style="thin", color="CBD5E1")
    double_side = Side(border_style="double", color="0F172A")
    top_thick_side = Side(border_style="thin", color="0F172A")

    data_border = Border(bottom=Side(border_style="thin", color="E2E8F0"))
    row_total_col_border = Border(
        left=Side(border_style="thin", color="CBD5E1"),
        right=Side(border_style="thin", color="CBD5E1"),
        bottom=Side(border_style="thin", color="E2E8F0"),
    )
    header_border = Border(top=thin_side, bottom=thin_side, left=thin_side, right=thin_side)
    total_border = Border(top=top_thick_side, bottom=double_side)

    currency_num_format = get_excel_currency_number_format(curr)
    percent_num_format = '0.0"%"'
    integer_num_format = '#,##0'

    # Write metadata rows (rows 1..7)
    title_cell = ws.cell(row=1, column=1, value=report_title)
    title_cell.font = title_font
    title_cell.alignment = Alignment(horizontal="left", vertical="center", wrap_text=True)
    ws.row_dimensions[1].height = 34

    for r_idx, mrow in enumerate(metadata_rows[1:6], start=2):
        c_lbl = ws.cell(row=r_idx, column=1, value=mrow[0])
        c_lbl.font = meta_label_font
        c_lbl.alignment = Alignment(horizontal="left", vertical="center")
        c_val = ws.cell(row=r_idx, column=2, value=mrow[1])
        c_val.font = meta_val_font
        c_val.alignment = Alignment(horizontal="left", vertical="center")
        ws.row_dimensions[r_idx].height = 19

    header_row_idx = 8
    for c_idx, h_text in enumerate(headers, start=1):
        cell = ws.cell(row=header_row_idx, column=c_idx, value=h_text)
        cell.font = header_font
        cell.fill = header_fill
        cell.border = header_border
        ctype = col_types[c_idx - 1]
        cell.alignment = Alignment(
            horizontal="left" if ctype == "text" else "right",
            vertical="center",
            wrap_text=False,
        )
    ws.row_dimensions[header_row_idx].height = 28

    current_row_idx = header_row_idx + 1
    for d_idx, drow in enumerate(data_rows):
        is_zebra = (d_idx % 2 == 1)
        for c_idx, val in enumerate(drow, start=1):
            ctype = col_types[c_idx - 1]
            is_row_total_col = (headers[c_idx - 1] == "Row Total")
            # Strictly preserve numeric types in XLSX
            if val is not None and ctype in ("currency", "percent"):
                clean_val: Any = float(val)
            elif val is not None and ctype == "integer":
                clean_val = int(val)
            else:
                clean_val = val

            cell = ws.cell(row=current_row_idx, column=c_idx, value=clean_val)
            cell.font = total_font if (c_idx == 1 or is_row_total_col) else data_font
            if is_row_total_col:
                cell.fill = total_fill
                cell.border = row_total_col_border
            else:
                if is_zebra:
                    cell.fill = zebra_fill
                cell.border = data_border
            if ctype == "currency":
                cell.number_format = currency_num_format
                cell.alignment = Alignment(horizontal="right", vertical="center")
            elif ctype == "percent":
                cell.number_format = percent_num_format
                cell.alignment = Alignment(horizontal="right", vertical="center")
            elif ctype == "integer":
                cell.number_format = integer_num_format
                cell.alignment = Alignment(horizontal="right", vertical="center")
            else:
                cell.alignment = Alignment(horizontal="left", vertical="center")
        ws.row_dimensions[current_row_idx].height = 21
        current_row_idx += 1

    last_data_row_idx = max(header_row_idx, current_row_idx - 1)

    if total_row is not None:
        for c_idx, val in enumerate(total_row, start=1):
            ctype = col_types[c_idx - 1]
            if val is not None and ctype in ("currency", "percent"):
                clean_val = float(val)
            elif val is not None and ctype == "integer":
                clean_val = int(val)
            else:
                clean_val = val

            cell = ws.cell(row=current_row_idx, column=c_idx, value=clean_val)
            cell.font = total_font
            cell.fill = total_fill
            cell.border = total_border
            if ctype == "currency":
                cell.number_format = currency_num_format
                cell.alignment = Alignment(horizontal="right", vertical="center")
            elif ctype == "percent":
                cell.number_format = percent_num_format
                cell.alignment = Alignment(horizontal="right", vertical="center")
            elif ctype == "integer":
                cell.number_format = integer_num_format
                cell.alignment = Alignment(horizontal="right", vertical="center")
            else:
                cell.alignment = Alignment(horizontal="left", vertical="center")
        ws.row_dimensions[current_row_idx].height = 24

    # Freeze top metadata + header rows AND first column (Category / Period)
    ws.freeze_panes = f"B{header_row_idx + 1}"

    # Apply auto-filter to the table header and data rows
    if headers:
        last_col_letter = get_column_letter(len(headers))
        ws.auto_filter.ref = f"A{header_row_idx}:{last_col_letter}{last_data_row_idx}"

    # Sensible auto-calculated column widths (accounting for Excel auto-filter dropdown icon)
    for c_idx in range(1, len(headers) + 1):
        col_letter = get_column_letter(c_idx)
        ctype = col_types[c_idx - 1]
        # Add extra padding on headers so Excel's auto-filter arrow never overlaps header text
        header_padded_len = len(str(headers[c_idx - 1])) + 6
        max_data_len = 0
        for r_idx in range(header_row_idx + 1, current_row_idx + 1):
            v = ws.cell(row=r_idx, column=c_idx).value
            if v is not None:
                if ctype == "currency" and isinstance(v, (int, float)):
                    v_str = format_pence(int(round(v * 100)), sym)
                elif ctype == "percent" and isinstance(v, (int, float)):
                    v_str = f"{v:.1f}%"
                else:
                    v_str = str(v)
                if len(v_str) > max_data_len:
                    max_data_len = len(v_str)
        min_w = 28 if c_idx == 1 else (15 if ctype == "currency" else 13)
        ws.column_dimensions[col_letter].width = max(min_w, min(max(header_padded_len, max_data_len + 4), 44))

    bio = io.BytesIO()
    wb.save(bio)
    xlsx_bytes = bio.getvalue()
    return (
        xlsx_bytes,
        f"{filename_base}.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

