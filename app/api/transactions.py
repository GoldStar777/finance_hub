import uuid
from datetime import datetime, timezone, time
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, List, Union, Literal
from zoneinfo import ZoneInfo
from fastapi import APIRouter, Depends, HTTPException, Query, Header, status, Response
from sqlalchemy.orm import Session, joinedload, object_session
from sqlalchemy import or_

from app.database import get_db, get_current_profile
from app.core.profiles import ProfileMetadata
from app.core.receipts import (
    build_receipt_file_response,
    build_transaction_receipt_url,
    normalize_transfer_provenance_urls,
)
from app.models import Transaction, TransactionType, ExpenseNature, Account, Category, CategoryType
from app.core.categories import (
    CategoryValidationError,
    expected_category_type_for_transaction,
    validate_category_for_transaction_type,
)
from app.schemas import (
    TransactionCreate,
    TransactionUpdate,
    TransactionResponse,
    TransactionListResponse,
    MatchingTransactionIdsResponse,
    BulkTransactionUpdatePayload,
    BulkTransactionUpdateResult,
    BulkTransactionDeletePayload,
    BulkTransactionDeleteResult,
    RestoreTransactionsPayload,
    RestoreTransactionsResult,
    RecentlyDeletedSummary,
    RepeatTransactionCreatePayload,
    RepeatTransactionCreateResponse,
)
from app.core.currency import (
    pounds_to_pence, pence_to_pounds, format_pence,
    validate_origin_amount, format_origin_amount,
    get_currency_spec, get_effective_base_currency,
    get_base_currency_readonly, DEFAULT_BASE_CURRENCY,
    SUPPORTED_CURRENCIES
)
from app.core.timezone import (
    get_app_timezone, get_today_local, get_now_utc,
    get_midday_utc, parse_date_input, ensure_utc,
    get_end_of_day_utc
)
from app.core.transactions import build_transactions_query, normalize_filter_datetime, apply_transactions_sorting
from app.core.repeat_transactions import (
    resolve_validated_transaction_fields,
    create_repeat_transaction_series,
)
from app.core.ledger_export import generate_ledger_export

_build_transactions_query = build_transactions_query
_normalize_filter_datetime = normalize_filter_datetime

router = APIRouter(prefix="/transactions")

def _to_transaction_response(tx: Transaction) -> TransactionResponse:
    orig_amt_float = float(tx.original_amount) if tx.original_amount is not None else None
    orig_curr = tx.original_currency
    rate_float = float(tx.exchange_rate) if tx.exchange_rate is not None else None

    formatted_orig = None
    implied_label = None
    is_implied = False

    sess = object_session(tx)
    if tx.account:
        acc_curr = tx.account.currency
    elif sess is not None:
        acc_curr = get_base_currency_readonly(sess)
    else:
        acc_curr = DEFAULT_BASE_CURRENCY
    acc_spec = get_currency_spec(acc_curr)

    if orig_amt_float is not None and orig_curr:
        formatted_orig = format_origin_amount(orig_amt_float, orig_curr)
        if rate_float is not None:
            is_implied = True
            implied_label = f"1 {orig_curr} = {acc_spec.symbol}{rate_float:.8f} (implied effective rate)"

    app_tz = get_app_timezone(object_session(tx))
    today_local = get_today_local(app_tz)
    end_of_today_utc = get_end_of_day_utc(today_local, tz_str=app_tz)
    eff_utc = ensure_utc(tx.effective_timestamp or tx.transaction_date)
    is_planned = eff_utc > end_of_today_utc if eff_utc else False

    clean_merchant = tx.merchant.strip() if tx.merchant and tx.merchant.strip() else None
    display_merchant = clean_merchant or "Merchant not recorded"
    is_unassigned = tx.account_id is None
    receipt_url = build_transaction_receipt_url(tx.id, "source") if tx.receipt_path else None

    dest_tx_date = None
    dest_eff_ts = None
    dest_merchant = None
    dest_notes = None
    dest_entry_method = None
    dest_receipt_path = None
    dest_receipt_url = None
    transfer_prov = None

    if tx.transaction_type == TransactionType.TRANSFER:
        sess = object_session(tx)
        if sess is not None:
            from app.core.review_suggestions import get_transfer_provenance
            raw_prov = get_transfer_provenance(sess, tx.id)
            transfer_prov = normalize_transfer_provenance_urls(raw_prov, tx.id)
            if transfer_prov:
                dest_leg = transfer_prov.get("destination_leg") or {}
                if dest_leg.get("transaction_date"):
                    try:
                        dest_tx_date = datetime.fromisoformat(str(dest_leg["transaction_date"]))
                    except Exception:
                        dest_tx_date = None
                if dest_leg.get("effective_timestamp"):
                    try:
                        dest_eff_ts = datetime.fromisoformat(str(dest_leg["effective_timestamp"]))
                    except Exception:
                        dest_eff_ts = None
                dest_merchant = dest_leg.get("merchant")
                dest_notes = dest_leg.get("notes")
                dest_entry_method = dest_leg.get("entry_method")
                dest_receipt_path = dest_leg.get("receipt_path")
                dest_receipt_url = (
                    build_transaction_receipt_url(tx.id, "destination")
                    if dest_receipt_path
                    else None
                )

    return TransactionResponse(
        id=tx.id,
        transaction_date=tx.transaction_date,
        effective_timestamp=tx.effective_timestamp,
        created_at=tx.created_at,
        transaction_type=tx.transaction_type,
        amount_pence=tx.amount_pence,
        amount_pounds=pence_to_pounds(tx.amount_pence),
        formatted_amount=format_pence(tx.amount_pence, currency_symbol=acc_spec.symbol),
        merchant=clean_merchant,
        display_merchant=display_merchant,
        notes=tx.notes,
        entry_method=tx.entry_method or "manual",
        receipt_path=tx.receipt_path,
        receipt_url=receipt_url,
        account_id=tx.account_id,
        account_name=tx.account.name if tx.account else "Unassigned",
        account_color=tx.account.color if tx.account else "#9CA3AF",
        is_unassigned=is_unassigned,
        destination_account_id=tx.destination_account_id,
        destination_account_name=tx.destination_account.name if tx.destination_account else None,
        destination_account_color=tx.destination_account.color if tx.destination_account else None,
        destination_transaction_date=dest_tx_date,
        destination_effective_timestamp=dest_eff_ts,
        destination_merchant=dest_merchant,
        destination_notes=dest_notes,
        destination_entry_method=dest_entry_method,
        destination_receipt_path=dest_receipt_path,
        destination_receipt_url=dest_receipt_url,
        transfer_provenance=transfer_prov,
        category_id=tx.category_id,
        category_name=tx.category.name if tx.category else None,
        category_color=tx.category.color if tx.category else None,
        category_type=(getattr(tx.category, "category_type", None) or CategoryType.EXPENSE) if tx.category else None,
        expense_nature=tx.expense_nature or ExpenseNature.UNCLASSIFIED,
        original_amount=orig_amt_float,
        original_currency=orig_curr,
        exchange_rate=rate_float,
        formatted_original_amount=formatted_orig,
        is_implied_rate=is_implied,
        implied_effective_rate_label=implied_label,
        is_planned=is_planned,
        deleted_at=tx.deleted_at,
        deletion_batch_id=tx.deletion_batch_id,
        is_deleted=tx.deleted_at is not None,
        repeat_series_id=tx.repeat_series_id,
    )

@router.get("", response_model=TransactionListResponse)
def list_transactions(
    account_id: Optional[int] = Query(None, description="Filter by account (source or destination)"),
    account_ids: Optional[str] = Query(None, description="Comma-separated account IDs"),
    unassigned_only: Optional[bool] = Query(None, description="Filter for unassigned transactions"),
    category_id: Optional[str] = Query(None, description="Filter by category ID ('0' or 'uncategorized' for uncategorized)"),
    category_ids: Optional[str] = Query(None, description="Comma-separated category IDs (0 or uncategorized for uncategorized)"),
    uncategorized_only: Optional[bool] = Query(None, description="Filter for uncategorized transactions"),
    transaction_type: Optional[TransactionType] = Query(None, description="Filter by transaction type"),
    transaction_types: Optional[str] = Query(None, description="Comma-separated transaction types"),
    expense_nature: Optional[ExpenseNature] = Query(None, description="Filter by expense nature"),
    q: Optional[str] = Query(None, description="Search term across merchant or notes"),
    start_date: Optional[Union[str, datetime]] = Query(None, description="Transactions on or after this timestamp"),
    end_date: Optional[Union[str, datetime]] = Query(None, description="Transactions on or before this timestamp"),
    status: Optional[str] = Query(None, description="Filter by activity status: 'all', 'actual', or 'planned'"),
    date_preset: Optional[str] = Query(None, description="Date preset (day, week, month, 3m, 6m, year, 5y, all, custom)"),
    date_offset: Optional[int] = Query(0, description="Offset for preset navigation"),
    sort_by: Optional[str] = Query("date", description="Field to sort by: 'date', 'amount', 'category', 'account'"),
    sort_order: Optional[str] = Query("desc", description="Sort order: 'asc' or 'desc'"),
    limit: int = Query(50, ge=1, le=200, description="Items per page"),
    offset: int = Query(0, ge=0, description="Items to skip"),
    db: Session = Depends(get_db)
):
    """Lists transactions with rich filtering, search, sorting, and pagination."""
    query = _build_transactions_query(
        db=db,
        account_id=account_id,
        account_ids=account_ids,
        unassigned_only=unassigned_only,
        category_id=category_id,
        category_ids=category_ids,
        uncategorized_only=uncategorized_only,
        transaction_type=transaction_type,
        transaction_types=transaction_types,
        expense_nature=expense_nature,
        q=q,
        start_date=start_date,
        end_date=end_date,
        status=status,
        date_preset=date_preset,
        date_offset=date_offset,
    )

    total = query.count()

    sorted_query = apply_transactions_sorting(query, sort_by=sort_by, sort_order=sort_order)

    items = (
        sorted_query.options(
            joinedload(Transaction.account),
            joinedload(Transaction.destination_account),
            joinedload(Transaction.category)
        )
        .offset(offset)
        .limit(limit)
        .all()
    )

    range_start_date = None
    range_end_date = None
    can_nav_prev = None
    can_nav_next = None

    if start_date or end_date:
        norm_s = _normalize_filter_datetime(start_date, is_end=False, db=db)
        norm_e = _normalize_filter_datetime(end_date, is_end=True, db=db)
        zi = ZoneInfo(get_app_timezone(db))
        if norm_s:
            range_start_date = norm_s.astimezone(zi).date().isoformat()
        if norm_e:
            range_end_date = norm_e.astimezone(zi).date().isoformat()
        can_nav_prev = False
        can_nav_next = False
    elif date_preset:
        clean_p = date_preset.strip().lower()
        if clean_p == "1y":
            clean_p = "year"
        if clean_p not in ("all", "custom", ""):
            from app.core.analysis import resolve_date_range
            _, start_d, end_d, _, _, _, _, can_nav_prev, can_nav_next = resolve_date_range(
                db, preset=clean_p, offset=date_offset or 0
            )
            range_start_date = start_d.isoformat()
            range_end_date = end_d.isoformat()

    return TransactionListResponse(
        items=[_to_transaction_response(tx) for tx in items],
        total=total,
        limit=limit,
        offset=offset,
        range_start_date=range_start_date,
        range_end_date=range_end_date,
        can_navigate_previous=can_nav_prev,
        can_navigate_next=can_nav_next,
    )

@router.get("/matching-ids", response_model=MatchingTransactionIdsResponse)
def get_matching_transaction_ids(
    account_id: Optional[int] = Query(None, description="Filter by account (source or destination)"),
    account_ids: Optional[str] = Query(None, description="Comma-separated account IDs"),
    unassigned_only: Optional[bool] = Query(None, description="Filter for unassigned transactions"),
    category_id: Optional[str] = Query(None, description="Filter by category ID ('0' or 'uncategorized' for uncategorized)"),
    category_ids: Optional[str] = Query(None, description="Comma-separated category IDs"),
    uncategorized_only: Optional[bool] = Query(None, description="Filter for uncategorized transactions"),
    transaction_type: Optional[TransactionType] = Query(None, description="Filter by transaction type"),
    transaction_types: Optional[str] = Query(None, description="Comma-separated transaction types"),
    expense_nature: Optional[ExpenseNature] = Query(None, description="Filter by expense nature"),
    q: Optional[str] = Query(None, description="Search term across merchant or notes"),
    start_date: Optional[Union[str, datetime]] = Query(None, description="Transactions on or after this timestamp"),
    end_date: Optional[Union[str, datetime]] = Query(None, description="Transactions on or before this timestamp"),
    status: Optional[str] = Query(None, description="Filter by activity status: 'all', 'actual', or 'planned'"),
    date_preset: Optional[str] = Query(None, description="Date preset"),
    date_offset: Optional[int] = Query(0, description="Offset for preset navigation"),
    sort_by: Optional[str] = Query(None, description="Optional sort by"),
    sort_order: Optional[str] = Query(None, description="Optional sort order"),
    db: Session = Depends(get_db)
):
    """Returns all transaction IDs matching current filters across all pages."""
    query = _build_transactions_query(
        db=db,
        account_id=account_id,
        account_ids=account_ids,
        unassigned_only=unassigned_only,
        category_id=category_id,
        category_ids=category_ids,
        uncategorized_only=uncategorized_only,
        transaction_type=transaction_type,
        transaction_types=transaction_types,
        expense_nature=expense_nature,
        q=q,
        start_date=start_date,
        end_date=end_date,
        status=status,
        date_preset=date_preset,
        date_offset=date_offset,
    )
    sorted_query = apply_transactions_sorting(query, sort_by=sort_by, sort_order=sort_order)
    rows = sorted_query.with_entities(Transaction.id).all()
    ids = [r[0] for r in rows]
    return MatchingTransactionIdsResponse(ids=ids, total=len(ids))

@router.get("/export")
def export_transactions(
    format: str = Query("xlsx", description="Export format: 'xlsx' or 'csv'"),
    account_id: Optional[int] = Query(None, description="Filter by account"),
    account_ids: Optional[str] = Query(None, description="Comma-separated account IDs"),
    unassigned_only: Optional[bool] = Query(None, description="Filter for unassigned transactions"),
    category_id: Optional[str] = Query(None, description="Filter by category ID"),
    category_ids: Optional[str] = Query(None, description="Comma-separated category IDs"),
    uncategorized_only: Optional[bool] = Query(None, description="Filter for uncategorized transactions"),
    transaction_type: Optional[TransactionType] = Query(None, description="Filter by transaction type"),
    transaction_types: Optional[str] = Query(None, description="Comma-separated transaction types"),
    expense_nature: Optional[ExpenseNature] = Query(None, description="Filter by expense nature"),
    q: Optional[str] = Query(None, description="Search term"),
    start_date: Optional[Union[str, datetime]] = Query(None, description="Start date"),
    end_date: Optional[Union[str, datetime]] = Query(None, description="End date"),
    status: Optional[str] = Query(None, description="Activity status: 'all', 'actual', or 'planned'"),
    date_preset: Optional[str] = Query(None, description="Date preset"),
    date_offset: Optional[int] = Query(0, description="Offset for preset navigation"),
    sort_by: Optional[str] = Query("date", description="Field to sort by: 'date', 'amount', 'category', 'account'"),
    sort_order: Optional[str] = Query("desc", description="Sort order: 'asc' or 'desc'"),
    db: Session = Depends(get_db)
):
    """Exports all transactions matching current filters across all pages as CSV or XLSX."""
    file_bytes, filename, media_type = generate_ledger_export(
        db=db,
        export_format=format,
        account_id=account_id,
        account_ids=account_ids,
        unassigned_only=unassigned_only,
        category_id=category_id,
        category_ids=category_ids,
        uncategorized_only=uncategorized_only,
        transaction_type=transaction_type,
        transaction_types=transaction_types,
        expense_nature=expense_nature,
        q=q,
        start_date=start_date,
        end_date=end_date,
        status=status,
        date_preset=date_preset,
        date_offset=date_offset,
        sort_by=sort_by,
        sort_order=sort_order,
    )

    return Response(
        content=file_bytes,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        }
    )


@router.post("/bulk", response_model=BulkTransactionUpdateResult)
def bulk_update_transactions(payload: BulkTransactionUpdatePayload, db: Session = Depends(get_db)):
    """
    Safely applies bulk edits across selected transactions atomically.
    Validates all transactions before writing. If any row cannot accept the change,
    fails the entire batch without partial updates.
    """
    if not payload.transaction_ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No transaction IDs provided.")

    if not (payload.update_transaction_type or payload.update_category or payload.update_account):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No fields were selected for update.")

    # 1. Fetch all matching transactions in active profile
    txs = (
        db.query(Transaction)
        .options(
            joinedload(Transaction.account),
            joinedload(Transaction.destination_account),
            joinedload(Transaction.category)
        )
        .filter(Transaction.id.in_(payload.transaction_ids))
        .all()
    )

    found_ids = {t.id for t in txs}
    missing_ids = set(payload.transaction_ids) - found_ids
    if missing_ids:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Transactions not found in active workspace: {sorted(list(missing_ids))}"
        )

    deleted_ids = [t.id for t in txs if t.deleted_at is not None]
    if deleted_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot bulk edit deleted transactions: {sorted(deleted_ids)}. Restore them first."
        )

    # 2. Comprehensive Pre-validation
    errors = []

    # Validate Transaction Type Update
    if payload.update_transaction_type:
        if payload.transaction_type not in (TransactionType.INCOME, TransactionType.EXPENSE):
            errors.append("Transaction type can only be bulk updated to 'income' or 'expense'.")

        for tx in txs:
            if tx.transaction_type == TransactionType.TRANSFER:
                errors.append(f"Row #{tx.id} ('{tx.merchant or 'Transfer'}') is a Transfer and cannot be converted to {payload.transaction_type.value if payload.transaction_type else 'selected type'}.")
            elif tx.transaction_type == TransactionType.ADJUSTMENT:
                errors.append(f"Row #{tx.id} ('{tx.merchant or 'Adjustment'}') is a Reconciliation Adjustment and cannot be converted to {payload.transaction_type.value if payload.transaction_type else 'selected type'}.")
            elif not payload.update_category and tx.category_id is not None and tx.category is not None and payload.transaction_type in (TransactionType.INCOME, TransactionType.EXPENSE):
                cat_type = getattr(tx.category, "category_type", None) or CategoryType.EXPENSE
                expected = expected_category_type_for_transaction(payload.transaction_type)
                if expected and cat_type != expected:
                    errors.append(
                        f"Row #{tx.id} has {cat_type.value} category '{tx.category.name}' which is incompatible with {payload.transaction_type.value}. Also update Category (clear or choose an {expected.value} category)."
                    )

    # Validate Category Update
    target_category = None
    if payload.update_category:
        if payload.category_id is not None:
            target_category = db.query(Category).filter(Category.id == payload.category_id).first()
            if not target_category:
                errors.append(f"Target category with ID {payload.category_id} not found.")

        for tx in txs:
            if tx.transaction_type == TransactionType.TRANSFER:
                if target_category is not None:
                    t_purpose = getattr(target_category, "category_type", None) or CategoryType.EXPENSE
                    cat_kind = "spending category" if t_purpose == CategoryType.EXPENSE else "income category"
                else:
                    cat_kind = "category"
                errors.append(f"Row #{tx.id} is a Transfer and cannot be assigned a {cat_kind}.")
            elif tx.transaction_type == TransactionType.ADJUSTMENT:
                errors.append(f"Row #{tx.id} is a Reconciliation Adjustment and cannot be assigned a category.")
            elif target_category is not None:
                eff_type = (
                    payload.transaction_type
                    if (payload.update_transaction_type and payload.transaction_type is not None)
                    else tx.transaction_type
                )
                expected = expected_category_type_for_transaction(eff_type)
                actual = getattr(target_category, "category_type", None) or CategoryType.EXPENSE
                if expected is not None and actual != expected:
                    errors.append(
                        f"Row #{tx.id} ('{tx.merchant or eff_type.value}') is {eff_type.value} and cannot use {actual.value} category '{target_category.name}'."
                    )

    # Validate Account Update
    target_account = None
    if payload.update_account:
        if payload.account_id is not None:
            target_account = db.query(Account).filter(Account.id == payload.account_id).first()
            if not target_account:
                errors.append(f"Target account with ID {payload.account_id} not found.")

        for tx in txs:
            if payload.account_id is None:  # Explicit Unassigned
                if tx.transaction_type == TransactionType.TRANSFER:
                    errors.append(f"Row #{tx.id} is a Transfer and cannot be set to Unassigned (transfers require valid accounts).")
                elif tx.transaction_type == TransactionType.ADJUSTMENT:
                    errors.append(f"Row #{tx.id} is a Reconciliation Adjustment and cannot be set to Unassigned.")
            else:
                if tx.transaction_type == TransactionType.TRANSFER:
                    if tx.destination_account_id == payload.account_id:
                        errors.append(f"Transfer #{tx.id} cannot have the same source and destination account.")

    if errors:
        # Strict validation: abort without partial updates
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Bulk update validation failed: " + "; ".join(errors)
        )

    # 3. Apply changes atomically
    try:
        for tx in txs:
            # Type update
            if payload.update_transaction_type and payload.transaction_type is not None:
                tx.transaction_type = payload.transaction_type
                if payload.transaction_type == TransactionType.EXPENSE:
                    # If category is also being updated, nature will be set below; otherwise check current category
                    if not payload.update_category and tx.category and tx.expense_nature == ExpenseNature.UNCLASSIFIED:
                        tx.expense_nature = tx.category.default_expense_nature
                elif payload.transaction_type == TransactionType.INCOME:
                    tx.expense_nature = ExpenseNature.UNCLASSIFIED

            # Category update
            if payload.update_category:
                if payload.category_id is None:
                    tx.category_id = None
                    if tx.transaction_type == TransactionType.EXPENSE:
                        tx.expense_nature = ExpenseNature.UNCLASSIFIED
                else:
                    tx.category_id = payload.category_id
                    if tx.transaction_type == TransactionType.EXPENSE and target_category:
                        tx.expense_nature = target_category.default_expense_nature
                    elif tx.transaction_type == TransactionType.INCOME:
                        tx.expense_nature = ExpenseNature.UNCLASSIFIED

            # Account update
            if payload.update_account:
                tx.account_id = payload.account_id

        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Atomic bulk update failed: {str(e)}"
        )

    return BulkTransactionUpdateResult(
        updated_count=len(txs),
        message=f"Successfully updated {len(txs)} transactions.",
        affected_ids=[t.id for t in txs]
    )

@router.post("", response_model=TransactionResponse, status_code=status.HTTP_201_CREATED)
def create_transaction(payload: TransactionCreate, db: Session = Depends(get_db)):
    """Creates a new transaction (Expense, Income, Transfer, or Adjustment)."""
    resolved = resolve_validated_transaction_fields(db, payload)

    tx_date = payload.transaction_date or datetime.now(timezone.utc)
    app_tz = get_app_timezone(db)
    today_local = get_today_local(app_tz)

    if payload.effective_timestamp:
        effective_ts = payload.effective_timestamp
    elif not payload.transaction_date:
        effective_ts = get_now_utc()
    else:
        nominal_d = parse_date_input(tx_date)
        if nominal_d == today_local:
            effective_ts = get_now_utc()
        else:
            effective_ts = get_midday_utc(tx_date, tz_str=app_tz)

    tx = Transaction(
        transaction_date=tx_date,
        effective_timestamp=effective_ts,
        created_at=get_now_utc(),
        transaction_type=resolved.transaction_type,
        amount_pence=resolved.amount_pence,
        merchant=resolved.merchant,
        notes=resolved.notes,
        entry_method="manual",
        account_id=resolved.account_id,
        destination_account_id=resolved.destination_account_id,
        category_id=resolved.category_id,
        expense_nature=resolved.expense_nature,
        original_amount=resolved.original_amount,
        original_currency=resolved.original_currency,
        exchange_rate=resolved.exchange_rate,
    )
    db.add(tx)
    db.commit()
    db.refresh(tx)
    return _to_transaction_response(tx)


@router.post("/repeat", response_model=RepeatTransactionCreateResponse, status_code=status.HTTP_201_CREATED)
def create_repeat_transactions(
    payload: RepeatTransactionCreatePayload,
    response: Response,
    db: Session = Depends(get_db),
    idempotency_key_header: Optional[str] = Header(default=None, alias="Idempotency-Key"),
):
    """
    Atomically creates an explicit series of independent manual transactions from a
    repeat schedule (weekly, biweekly, monthly, quarterly, or yearly).
    Supports idempotency keys to protect against duplicate creation on retries or double-submits.
    """
    batch, txs, dates, is_replay = create_repeat_transaction_series(
        db=db,
        payload=payload,
        header_idempotency_key=idempotency_key_header,
    )
    response.status_code = status.HTTP_200_OK if is_replay else status.HTTP_201_CREATED
    items = [_to_transaction_response(tx) for tx in txs]
    first_iso = dates[0].isoformat() if dates else payload.first_date.isoformat()
    last_iso = dates[-1].isoformat() if dates else payload.first_date.isoformat()
    msg = (
        f"Returned existing repeat series ({len(items)} transactions) for idempotent retry."
        if is_replay
        else f"Created {len(items)} independent transactions from {first_iso} to {last_iso}."
    )
    return RepeatTransactionCreateResponse(
        series_id=batch.series_id,
        idempotency_key=batch.idempotency_key,
        frequency=payload.frequency,
        first_date=first_iso,
        last_date=last_iso,
        end_mode=payload.end_mode,
        created_count=len(items),
        idempotent_replay=is_replay,
        message=msg,
        items=items,
    )

@router.post("/bulk-delete", response_model=BulkTransactionDeleteResult)
def bulk_delete_transactions(payload: BulkTransactionDeletePayload, db: Session = Depends(get_db)):
    """
    Safely applies bulk soft-deletion across selected transactions atomically.
    Validates all transactions before writing. If any row is missing or already deleted,
    aborts the entire batch without partial updates.
    """
    if not payload.transaction_ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No transaction IDs provided for deletion.")

    txs = (
        db.query(Transaction)
        .filter(Transaction.id.in_(payload.transaction_ids))
        .all()
    )
    found_map = {t.id: t for t in txs}
    missing_ids = [tid for tid in payload.transaction_ids if tid not in found_map]
    if missing_ids:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Transactions not found in active workspace: {sorted(missing_ids)}"
        )

    already_deleted = [t.id for t in txs if t.deleted_at is not None]
    if already_deleted:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"The following transactions are already deleted: {sorted(already_deleted)}"
        )

    now = datetime.now(timezone.utc)
    batch_id = f"batch_{uuid.uuid4().hex[:10]}_{int(now.timestamp())}"
    transfers_count = sum(1 for t in txs if t.transaction_type == TransactionType.TRANSFER)
    receipts_count = sum(1 for t in txs if t.receipt_path)

    for t in txs:
        t.deleted_at = now
        t.deletion_batch_id = batch_id

    db.commit()

    return BulkTransactionDeleteResult(
        deleted_count=len(txs),
        batch_id=batch_id,
        affected_transfers_count=transfers_count,
        affected_receipts_count=receipts_count,
        affected_ids=[t.id for t in txs],
        message=f"Successfully moved {len(txs)} transaction(s) to Recently Deleted."
    )

@router.post("/restore", response_model=RestoreTransactionsResult)
def restore_transactions(payload: RestoreTransactionsPayload, db: Session = Depends(get_db)):
    """
    Restores previously soft-deleted transactions to the active ledger.
    Can restore by specific transaction IDs or by batch ID.
    Reinstates their original balances, dates, categories, accounts, and receipt links.
    """
    if not payload.transaction_ids and not payload.batch_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Must provide either transaction_ids or batch_id to restore.")

    query = db.query(Transaction).filter(Transaction.deleted_at.is_not(None))
    if payload.batch_id:
        query = query.filter(Transaction.deletion_batch_id == payload.batch_id)
    elif payload.transaction_ids:
        query = query.filter(Transaction.id.in_(payload.transaction_ids))

    txs = query.all()
    if not txs:
        return RestoreTransactionsResult(
            restored_count=0,
            restored_ids=[],
            message="No deleted transactions matched the restore criteria."
        )

    restored_ids = []
    for t in txs:
        t.deleted_at = None
        t.deletion_batch_id = None
        restored_ids.append(t.id)

    db.commit()

    return RestoreTransactionsResult(
        restored_count=len(restored_ids),
        restored_ids=restored_ids,
        message=f"Successfully restored {len(restored_ids)} transaction(s) to the active ledger."
    )

@router.post("/undo-delete", response_model=RestoreTransactionsResult)
def undo_last_delete(batch_id: Optional[str] = Query(None), db: Session = Depends(get_db)):
    """
    Restores the most recently deleted batch of transactions, or a specific batch by ID.
    """
    target_batch_id = batch_id
    if not target_batch_id:
        latest_deleted = (
            db.query(Transaction)
            .filter(Transaction.deleted_at.is_not(None))
            .order_by(Transaction.deleted_at.desc(), Transaction.id.desc())
            .first()
        )
        if not latest_deleted or not latest_deleted.deletion_batch_id:
            return RestoreTransactionsResult(
                restored_count=0,
                restored_ids=[],
                message="No recent deletions to undo."
            )
        target_batch_id = latest_deleted.deletion_batch_id

    txs = (
        db.query(Transaction)
        .filter(
            Transaction.deletion_batch_id == target_batch_id,
            Transaction.deleted_at.is_not(None)
        )
        .all()
    )
    if not txs:
        return RestoreTransactionsResult(
            restored_count=0,
            restored_ids=[],
            message="No deleted transactions found for the specified batch."
        )

    restored_ids = []
    for t in txs:
        t.deleted_at = None
        t.deletion_batch_id = None
        restored_ids.append(t.id)

    db.commit()

    return RestoreTransactionsResult(
        restored_count=len(restored_ids),
        restored_ids=restored_ids,
        message=f"Successfully undone deletion: restored {len(restored_ids)} transaction(s)."
    )

@router.get("/deleted/summary", response_model=RecentlyDeletedSummary)
def get_deleted_summary(db: Session = Depends(get_db)):
    """Provides summary statistics for all currently soft-deleted transactions in the active workspace."""
    deleted_txs = db.query(Transaction).filter(Transaction.deleted_at.is_not(None)).all()
    total_count = len(deleted_txs)
    total_pence = sum(t.amount_pence for t in deleted_txs)
    transfers = sum(1 for t in deleted_txs if t.transaction_type == TransactionType.TRANSFER)
    receipts = sum(1 for t in deleted_txs if t.receipt_path)
    base_curr = get_effective_base_currency(db)
    spec = get_currency_spec(base_curr)

    return RecentlyDeletedSummary(
        total_deleted=total_count,
        total_pence=total_pence,
        formatted_total=format_pence(total_pence, currency_symbol=spec.symbol),
        transfers_count=transfers,
        receipts_count=receipts
    )

@router.get("/deleted", response_model=TransactionListResponse)
def list_deleted_transactions(
    q: Optional[str] = Query(None, description="Search term across merchant or notes"),
    sort_by: Optional[str] = Query(None, description="Optional sort by field"),
    sort_order: Optional[str] = Query(None, description="Optional sort order"),
    limit: int = Query(50, ge=1, le=200, description="Items per page"),
    offset: int = Query(0, ge=0, description="Items to skip"),
    db: Session = Depends(get_db)
):
    """Lists soft-deleted transactions in the active workspace ordered newest deletion first or sorted."""
    query = db.query(Transaction).filter(Transaction.deleted_at.is_not(None))
    if q:
        term = q.strip()
        if term:
            query = query.filter(
                or_(
                    Transaction.merchant.ilike(f"%{term}%"),
                    Transaction.notes.ilike(f"%{term}%")
                )
            )

    total = query.count()

    if sort_by:
        query = apply_transactions_sorting(query, sort_by=sort_by, sort_order=sort_order)
    else:
        query = query.order_by(Transaction.deleted_at.desc(), Transaction.id.desc())

    items = (
        query.options(
            joinedload(Transaction.account),
            joinedload(Transaction.destination_account),
            joinedload(Transaction.category)
        )
        .offset(offset)
        .limit(limit)
        .all()
    )

    return TransactionListResponse(
        items=[_to_transaction_response(tx) for tx in items],
        total=total,
        limit=limit,
        offset=offset
    )

@router.get("/{transaction_id}", response_model=TransactionResponse)
def get_transaction(transaction_id: int, db: Session = Depends(get_db)):
    """Retrieves a single transaction by ID."""
    tx = (
        db.query(Transaction)
        .options(
            joinedload(Transaction.account),
            joinedload(Transaction.destination_account),
            joinedload(Transaction.category)
        )
        .filter(Transaction.id == transaction_id)
        .first()
    )
    if not tx:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Transaction with ID {transaction_id} not found."
        )
    return _to_transaction_response(tx)


@router.get("/{transaction_id}/receipt")
def serve_transaction_receipt(
    transaction_id: int,
    leg: Literal["source", "destination"] = Query("source"),
    download: bool = Query(False),
    db: Session = Depends(get_db),
    profile: ProfileMetadata = Depends(get_current_profile),
):
    """Stream or download the receipt file authorized by a profile's transaction or transfer leg."""
    tx = db.query(Transaction).filter(Transaction.id == transaction_id).first()
    if not tx:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Receipt attachment not found.",
        )

    target_raw_path: Optional[str] = None
    if leg == "destination":
        if tx.transaction_type == TransactionType.TRANSFER:
            from app.core.review_suggestions import get_transfer_provenance

            prov = get_transfer_provenance(db, tx.id) or {}
            dest_leg = prov.get("destination_leg") or {}
            target_raw_path = dest_leg.get("receipt_path")
    else:
        target_raw_path = tx.receipt_path
        if not target_raw_path and tx.transaction_type == TransactionType.TRANSFER:
            from app.core.review_suggestions import get_transfer_provenance

            prov = get_transfer_provenance(db, tx.id) or {}
            source_leg = prov.get("source_leg") or {}
            target_raw_path = source_leg.get("receipt_path")

    return build_receipt_file_response(target_raw_path, profile, download=download)

@router.put("/{transaction_id}", response_model=TransactionResponse)
def update_transaction(transaction_id: int, payload: TransactionUpdate, db: Session = Depends(get_db)):
    """Updates a transaction atomically."""
    tx = (
        db.query(Transaction)
        .options(
            joinedload(Transaction.account),
            joinedload(Transaction.destination_account),
            joinedload(Transaction.category)
        )
        .filter(Transaction.id == transaction_id)
        .first()
    )
    if not tx:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Transaction with ID {transaction_id} not found."
        )

    update_data = payload.model_dump(exclude_unset=True)

    target_type = payload.transaction_type if payload.transaction_type is not None else tx.transaction_type
    target_account_id = payload.account_id if "account_id" in update_data else tx.account_id

    source_acc = None
    base_curr = get_effective_base_currency(db)
    if target_account_id is not None:
        source_acc = db.query(Account).filter(Account.id == target_account_id).first()
        if not source_acc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found.")
        acc_currency = source_acc.currency.upper()
    else:
        if target_type == TransactionType.TRANSFER:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Source and destination accounts are required for transfers."
            )
        if target_type == TransactionType.ADJUSTMENT:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="An account is required for reconciliation adjustments."
            )
        acc_currency = base_curr.upper()

    if target_type == TransactionType.TRANSFER:
        target_dest_id = (
            payload.destination_account_id
            if payload.destination_account_id is not None
            else tx.destination_account_id
        )
        if not target_dest_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Destination account is required for transfers."
            )
        if target_dest_id == target_account_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Source and destination accounts must be distinct."
            )
        dest_acc = db.query(Account).filter(Account.id == target_dest_id).first()
        if not dest_acc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Destination account with ID {target_dest_id} not found."
            )

        if not source_acc or source_acc.currency != base_curr or dest_acc.currency != base_curr:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Transfers are only supported between accounts using the base currency ({base_curr})."
            )

        tx.destination_account_id = target_dest_id
        # Transfers cannot carry foreign currency origin
        tx.original_amount = None
        tx.original_currency = None
        tx.exchange_rate = None
    else:
        tx.destination_account_id = None

    tx.account_id = target_account_id
    tx.transaction_type = target_type

    # Handle Foreign Currency updates
    has_orig_update = any(k in update_data for k in ("original_currency", "original_amount", "exchange_rate"))
    if has_orig_update:
        target_orig_curr = payload.original_currency.strip().upper() if payload.original_currency else (
            tx.original_currency if "original_currency" not in update_data else None
        )
        if target_orig_curr and target_orig_curr != acc_currency:
            tx.original_currency = target_orig_curr
            target_orig_amt = payload.original_amount if payload.original_amount is not None else float(tx.original_amount or 0)
            if target_orig_amt <= 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="original_amount must be strictly positive."
                )
            try:
                orig_dec = validate_origin_amount(target_orig_amt, target_orig_curr)
            except ValueError as e:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
            tx.original_amount = orig_dec

            if "amount" in update_data and payload.amount is not None:
                amt_pence = pounds_to_pence(payload.amount)
                if amt_pence <= 0:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Amount must be positive.")
                tx.amount_pence = amt_pence
                tx.exchange_rate = (Decimal(str(payload.amount)) / orig_dec).quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP)
            elif "exchange_rate" in update_data and payload.exchange_rate is not None:
                rate_dec = Decimal(str(payload.exchange_rate)).quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP)
                tx.exchange_rate = rate_dec
                tx.amount_pence = pounds_to_pence(orig_dec * rate_dec)
            elif tx.exchange_rate is not None and "original_amount" in update_data:
                # Recalculate amount_pence with existing rate
                tx.amount_pence = pounds_to_pence(orig_dec * Decimal(str(tx.exchange_rate)))
        else:
            # Cleared foreign currency
            tx.original_currency = None
            tx.original_amount = None
            tx.exchange_rate = None
            if "amount" in update_data and payload.amount is not None:
                amt_pence = pounds_to_pence(payload.amount)
                if amt_pence <= 0:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Amount must be positive.")
                tx.amount_pence = amt_pence
    elif "amount" in update_data and payload.amount is not None:
        amt_pence = pounds_to_pence(payload.amount)
        if amt_pence <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Transaction amount must be strictly greater than zero."
            )
        tx.amount_pence = amt_pence
        if tx.original_currency and tx.original_amount:
            # Recompute implied effective rate
            tx.exchange_rate = (Decimal(str(payload.amount)) / Decimal(str(tx.original_amount))).quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP)

    if "merchant" in update_data:
        if payload.merchant and payload.merchant.strip():
            tx.merchant = payload.merchant.strip()
        elif target_type == TransactionType.TRANSFER:
            tx.merchant = "Internal Transfer"
        else:
            tx.merchant = None

    if "transaction_date" in update_data and payload.transaction_date is not None:
        tx.transaction_date = payload.transaction_date
        if "effective_timestamp" not in update_data:
            app_tz = get_app_timezone(db)
            today_local = get_today_local(app_tz)
            nominal_d = parse_date_input(payload.transaction_date)
            if nominal_d == today_local:
                tx.effective_timestamp = get_now_utc()
            else:
                tx.effective_timestamp = get_midday_utc(payload.transaction_date, tz_str=app_tz)

    if "effective_timestamp" in update_data:
        tx.effective_timestamp = payload.effective_timestamp

    if "notes" in update_data:
        tx.notes = payload.notes.strip() if payload.notes else None

    # Validate category against effective transaction type BEFORE saving
    if target_type in (TransactionType.TRANSFER, TransactionType.ADJUSTMENT):
        if "category_id" in update_data and payload.category_id is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Transactions of type '{target_type.value}' cannot be assigned a category.",
            )
    else:
        effective_category_id = payload.category_id if "category_id" in update_data else tx.category_id
        try:
            validated_cat = validate_category_for_transaction_type(db, effective_category_id, target_type)
        except CategoryValidationError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc))

    # Handle Category & Expense Nature
    if target_type in (TransactionType.TRANSFER, TransactionType.ADJUSTMENT):
        tx.category_id = None
        tx.expense_nature = ExpenseNature.UNCLASSIFIED
    elif "category_id" in update_data:
        if validated_cat is not None:
            tx.category_id = validated_cat.id
            if "expense_nature" not in update_data and target_type == TransactionType.EXPENSE:
                tx.expense_nature = validated_cat.default_expense_nature
        else:
            tx.category_id = None

    if "expense_nature" in update_data:
        tx.expense_nature = (
            ExpenseNature.UNCLASSIFIED
            if target_type != TransactionType.EXPENSE
            else (payload.expense_nature or ExpenseNature.UNCLASSIFIED)
        )
    elif target_type != TransactionType.EXPENSE:
        tx.expense_nature = ExpenseNature.UNCLASSIFIED

    db.commit()
    db.refresh(tx)
    return _to_transaction_response(tx)


@router.delete("/{transaction_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_transaction(transaction_id: int, db: Session = Depends(get_db)):
    """Soft-deletes a transaction atomically. For transfers, soft-deletes the single transfer record."""
    tx = db.query(Transaction).filter(Transaction.id == transaction_id, Transaction.deleted_at.is_(None)).first()
    if not tx:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Active transaction with ID {transaction_id} not found."
        )
    now = datetime.now(timezone.utc)
    batch_id = f"single_{tx.id}_{int(now.timestamp())}"
    tx.deleted_at = now
    tx.deletion_batch_id = batch_id
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)

