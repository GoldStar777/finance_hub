"""
Core transactions query builder and temporal filter normalizer.
"""

from datetime import datetime, timezone, time
from typing import Optional, List, Union
from zoneinfo import ZoneInfo
from sqlalchemy.orm import Session
from sqlalchemy import or_, func, case

from app.models import Transaction, TransactionType, ExpenseNature
from app.core.timezone import get_app_timezone, get_now_utc, get_today_local, get_end_of_day_utc


def normalize_filter_datetime(
    dt_val: Optional[Union[str, datetime]],
    is_end: bool = False,
    db: Optional[Session] = None
) -> Optional[datetime]:
    if not dt_val:
        return None
    app_tz = get_app_timezone(db)
    zi = ZoneInfo(app_tz)
    if isinstance(dt_val, str):
        raw = dt_val.strip()
        if not raw:
            return None
        if len(raw) == 10 and raw.count("-") == 2:
            try:
                d = datetime.strptime(raw, "%Y-%m-%d").date()
                t = time(23, 59, 59, 999999) if is_end else time(0, 0, 0)
                local_dt = datetime.combine(d, t, tzinfo=zi)
                return local_dt.astimezone(timezone.utc)
            except Exception:
                return None
        else:
            try:
                parsed = datetime.fromisoformat(raw)
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=zi)
                if is_end and parsed.time() == time(0, 0, 0):
                    parsed = parsed.replace(hour=23, minute=59, second=59, microsecond=999999)
                return parsed.astimezone(timezone.utc)
            except Exception:
                return None
    elif isinstance(dt_val, datetime):
        parsed = dt_val
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=zi)
        if is_end and parsed.time() == time(0, 0, 0):
            parsed = parsed.replace(hour=23, minute=59, second=59, microsecond=999999)
        return parsed.astimezone(timezone.utc)
    return None


def build_transactions_query(
    db: Session,
    account_id: Optional[int] = None,
    account_ids: Optional[str] = None,
    unassigned_only: Optional[bool] = None,
    category_id: Optional[Union[int, str]] = None,
    category_ids: Optional[str] = None,
    uncategorized_only: Optional[bool] = None,
    transaction_type: Optional[TransactionType] = None,
    transaction_types: Optional[str] = None,
    expense_nature: Optional[ExpenseNature] = None,
    q: Optional[str] = None,
    start_date: Optional[Union[str, datetime]] = None,
    end_date: Optional[Union[str, datetime]] = None,
    status: Optional[str] = None,
    include_deleted: bool = False,
    is_deleted_only: bool = False,
    date_preset: Optional[str] = None,
    date_offset: Optional[int] = 0,
):
    query = db.query(Transaction)

    clean_status = status.strip().lower() if status else None
    if is_deleted_only or clean_status in ("deleted", "recently_deleted"):
        query = query.filter(Transaction.deleted_at.is_not(None))
    elif not include_deleted:
        query = query.filter(Transaction.deleted_at.is_(None))

    # Multi-account or single account filtering
    if unassigned_only:
        query = query.filter(Transaction.account_id.is_(None))
    elif account_ids:
        parts = [x.strip() for x in account_ids.split(",") if x.strip()]
        numeric_acc_ids = [int(p) for p in parts if p.isdigit()]
        include_unassigned = ("unassigned" in [p.lower() for p in parts]) or (0 in numeric_acc_ids)
        acc_conditions = []
        if numeric_acc_ids:
            acc_conditions.append(Transaction.account_id.in_(numeric_acc_ids))
            acc_conditions.append(Transaction.destination_account_id.in_(numeric_acc_ids))
        if include_unassigned:
            acc_conditions.append(Transaction.account_id.is_(None))
        if acc_conditions:
            query = query.filter(or_(*acc_conditions))
    elif account_id is not None:
        query = query.filter(
            or_(
                Transaction.account_id == account_id,
                Transaction.destination_account_id == account_id
            )
        )

    # Multi-category or single category filtering (including uncategorised)
    cat_id_list = []
    include_uncat = False
    if uncategorized_only:
        include_uncat = True
    elif category_ids:
        parts = [x.strip().lower() for x in category_ids.split(",") if x.strip()]
        for p in parts:
            if p in ("0", "uncategorized", "uncategorised"):
                include_uncat = True
            elif p.isdigit():
                cat_id_list.append(int(p))
    elif category_id is not None:
        cat_str = str(category_id).strip().lower()
        if cat_str in ("0", "uncategorized", "uncategorised"):
            include_uncat = True
        elif cat_str.isdigit():
            cat_id_list.append(int(cat_str))

    cat_conditions = []
    if cat_id_list:
        cat_conditions.append(Transaction.category_id.in_(cat_id_list))
    if include_uncat:
        cat_conditions.append(Transaction.category_id.is_(None))
    if cat_conditions:
        query = query.filter(or_(*cat_conditions))

    # Multi-type or single type filtering
    if transaction_types:
        parsed_types = []
        for t in transaction_types.split(","):
            t_str = t.strip().lower()
            try:
                parsed_types.append(TransactionType(t_str))
            except ValueError:
                pass
        if parsed_types:
            query = query.filter(Transaction.transaction_type.in_(parsed_types))
    elif transaction_type is not None:
        query = query.filter(Transaction.transaction_type == transaction_type)

    if expense_nature is not None:
        query = query.filter(Transaction.expense_nature == expense_nature)

    if q is not None:
        term = q.strip()
        if term:
            query = query.filter(
                or_(
                    Transaction.merchant.ilike(f"%{term}%"),
                    Transaction.notes.ilike(f"%{term}%")
                )
            )

    norm_start = normalize_filter_datetime(start_date, is_end=False, db=db)
    if norm_start is not None:
        query = query.filter(Transaction.transaction_date >= norm_start)

    norm_end = normalize_filter_datetime(end_date, is_end=True, db=db)
    if norm_end is not None:
        query = query.filter(Transaction.transaction_date <= norm_end)

    # If no explicit start/end dates were supplied, resolve date_preset if provided
    if norm_start is None and norm_end is None and date_preset:
        clean_preset = date_preset.strip().lower()
        if clean_preset == "1y":
            clean_preset = "year"
        if clean_preset not in ("all", "custom", ""):
            from app.core.analysis import resolve_date_range
            _, _, _, start_utc, end_utc, _, _, _, _ = resolve_date_range(
                db, preset=clean_preset, offset=date_offset or 0
            )
            query = query.filter(
                Transaction.transaction_date >= start_utc,
                Transaction.transaction_date <= end_utc
            )

    if status is not None:
        clean_status = status.strip().lower()
        app_tz = get_app_timezone(db)
        today_local = get_today_local(app_tz)
        end_of_today_utc = get_end_of_day_utc(today_local, tz_str=app_tz)
        effective_dt_col = func.coalesce(Transaction.effective_timestamp, Transaction.transaction_date)
        if clean_status in ("actual", "actuals", "completed", "past"):
            query = query.filter(effective_dt_col <= end_of_today_utc)
        elif clean_status in ("planned", "future"):
            query = query.filter(effective_dt_col > end_of_today_utc)

    return query


def apply_transactions_sorting(
    query,
    sort_by: Optional[str] = "date",
    sort_order: Optional[str] = "desc"
):
    """
    Applies deterministic, multi-level sorting with stable tie-breakers.
    Supports sorting by:
    - date (desc / asc)
    - amount (asc = lowest first, desc = highest first)
    - category (asc = A-Z, desc = Z-A)
    - account (asc = A-Z, desc = Z-A)
    All branches conclude with stable tie-breakers (transaction_date and transaction.id)
    so pagination across pages remains strictly deterministic.
    """
    clean_by = (sort_by or "date").strip().lower()
    clean_order = (sort_order or "desc").strip().lower()
    if clean_order not in ("asc", "desc"):
        clean_order = "desc"

    if clean_by == "amount":
        if clean_order == "asc":
            return query.order_by(
                Transaction.amount_pence.asc(),
                Transaction.transaction_date.desc(),
                Transaction.id.desc()
            )
        else:
            return query.order_by(
                Transaction.amount_pence.desc(),
                Transaction.transaction_date.desc(),
                Transaction.id.desc()
            )

    elif clean_by == "category":
        from app.models import Category
        query = query.outerjoin(Category, Transaction.category_id == Category.id)
        # Uncategorised records (category_name is None) sort at the end
        null_flag = case((Category.name.is_(None), 1), else_=0)
        if clean_order == "asc":
            return query.order_by(
                null_flag.asc(),
                func.lower(Category.name).asc(),
                Category.name.asc(),
                Transaction.transaction_date.desc(),
                Transaction.id.desc()
            )
        else:
            return query.order_by(
                null_flag.asc(),
                func.lower(Category.name).desc(),
                Category.name.desc(),
                Transaction.transaction_date.desc(),
                Transaction.id.desc()
            )

    elif clean_by == "account":
        from app.models import Account
        query = query.outerjoin(Account, Transaction.account_id == Account.id)
        # Unassigned records (account_name is None) sort at the end
        null_flag = case((Account.name.is_(None), 1), else_=0)
        if clean_order == "asc":
            return query.order_by(
                null_flag.asc(),
                func.lower(Account.name).asc(),
                Account.name.asc(),
                Transaction.transaction_date.desc(),
                Transaction.id.desc()
            )
        else:
            return query.order_by(
                null_flag.asc(),
                func.lower(Account.name).desc(),
                Account.name.desc(),
                Transaction.transaction_date.desc(),
                Transaction.id.desc()
            )

    else:  # Default: date
        if clean_order == "asc":
            return query.order_by(
                Transaction.transaction_date.asc(),
                Transaction.id.asc()
            )
        else:
            return query.order_by(
                Transaction.transaction_date.desc(),
                Transaction.id.desc()
            )


