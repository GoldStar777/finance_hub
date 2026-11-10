"""
Repeat Transaction Generation, Validation, and Atomic Batch Persistence.

Generates explicit occurrence dates from a user-selected schedule, validates shared fields
using the same business rules as single manual entry, enforces all-or-nothing atomicity,
and guards against duplicate creation on retries or double-submits via persistent
idempotency keys.
"""

import calendar
import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, List, Optional, Tuple

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.core.currency import (
    get_effective_base_currency,
    pounds_to_pence,
    validate_origin_amount,
)
from app.core.timezone import (
    get_app_timezone,
    get_midday_utc,
    get_now_utc,
    get_today_local,
)
from app.models import (
    Account,
    Category,
    ExpenseNature,
    RepeatSeriesBatch,
    Transaction,
    TransactionType,
)
from app.core.categories import CategoryValidationError, validate_category_for_transaction_type

MAX_REPEAT_OCCURRENCES = 366
VALID_REPEAT_FREQUENCIES = ("weekly", "biweekly", "monthly", "quarterly", "yearly")
VALID_REPEAT_END_MODES = ("end_date", "count")


@dataclass
class ResolvedTransactionFields:
    transaction_type: TransactionType
    amount_pence: int
    merchant: Optional[str]
    notes: Optional[str]
    account_id: Optional[int]
    destination_account_id: Optional[int]
    category_id: Optional[int]
    expense_nature: ExpenseNature
    original_amount: Optional[Decimal]
    original_currency: Optional[str]
    exchange_rate: Optional[Decimal]


def add_months_clamped(anchor_date: date, months_delta: int) -> date:
    """
    Adds `months_delta` calendar months to `anchor_date` without cumulative day-of-month drift.
    If `anchor_date.day` does not exist in the target month (e.g. 31st in February or April,
    or Feb 29 in a non-leap year), clamps to the last valid day of that target month.
    Subsequent occurrences continue using `anchor_date.day` as their target day.
    """
    total_months = (anchor_date.year * 12 + (anchor_date.month - 1)) + months_delta
    target_year = total_months // 12
    target_month = (total_months % 12) + 1
    max_day = calendar.monthrange(target_year, target_month)[1]
    return date(target_year, target_month, min(anchor_date.day, max_day))


def _compute_occurrence_date(first_date: date, frequency: str, index: int) -> date:
    if frequency == "weekly":
        return first_date + timedelta(days=7 * index)
    if frequency == "biweekly":
        return first_date + timedelta(days=14 * index)
    if frequency == "monthly":
        return add_months_clamped(first_date, index)
    if frequency == "quarterly":
        return add_months_clamped(first_date, 3 * index)
    if frequency == "yearly":
        return add_months_clamped(first_date, 12 * index)
    raise ValueError(f"Unsupported repeat frequency: '{frequency}'.")


def generate_repeat_occurrence_dates(
    first_date: date,
    frequency: str,
    end_mode: str,
    last_date: Optional[date] = None,
    occurrence_count: Optional[int] = None,
) -> List[date]:
    """
    Deterministically computes the exact ordered list of calendar dates for a repeat series.
    Raises ValueError with clear user-facing diagnostics if inputs are invalid or exceed limits.
    """
    clean_freq = (frequency or "").strip().lower()
    if clean_freq not in VALID_REPEAT_FREQUENCIES:
        raise ValueError(
            f"Unsupported repeat frequency '{frequency}'. "
            f"Choose one of: {', '.join(VALID_REPEAT_FREQUENCIES)}."
        )

    clean_mode = (end_mode or "").strip().lower()
    if clean_mode not in VALID_REPEAT_END_MODES:
        raise ValueError("End mode must be 'end_date' or 'count'.")

    dates: List[date] = []

    if clean_mode == "count":
        if occurrence_count is None:
            raise ValueError("Number of occurrences is required when using fixed count mode.")
        if occurrence_count < 1:
            raise ValueError("Number of occurrences must be at least 1.")
        if occurrence_count > MAX_REPEAT_OCCURRENCES:
            raise ValueError(f"Repeat series cannot exceed {MAX_REPEAT_OCCURRENCES} occurrences per batch.")
        for idx in range(occurrence_count):
            dates.append(_compute_occurrence_date(first_date, clean_freq, idx))
        return dates

    # end_mode == "end_date"
    if last_date is None:
        raise ValueError("Last occurrence date is required when using end-date mode.")
    if last_date < first_date:
        raise ValueError("Last occurrence date cannot be earlier than the first occurrence date.")

    idx = 0
    while True:
        candidate = _compute_occurrence_date(first_date, clean_freq, idx)
        if candidate > last_date:
            break
        if len(dates) >= MAX_REPEAT_OCCURRENCES:
            raise ValueError(
                f"Repeat series cannot exceed {MAX_REPEAT_OCCURRENCES} occurrences per batch. "
                "Please select an earlier end date."
            )
        dates.append(candidate)
        idx += 1

    return dates


def resolve_validated_transaction_fields(db: Session, payload: Any) -> ResolvedTransactionFields:
    """
    Shared validator and resolver for manual transaction creation (both single and repeat).
    Raises HTTPException 400/404 before any DB writes occur.
    """
    base_curr = get_effective_base_currency(db)
    source_acc = None

    if payload.account_id is not None:
        source_acc = db.query(Account).filter(Account.id == payload.account_id).first()
        if not source_acc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Account with ID {payload.account_id} not found."
            )
        acc_currency = source_acc.currency.upper()
    else:
        if payload.transaction_type == TransactionType.TRANSFER:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Source and destination accounts are required for transfers."
            )
        if payload.transaction_type == TransactionType.ADJUSTMENT:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="An account is required for reconciliation adjustments."
            )
        acc_currency = base_curr.upper()

    orig_amt_dec: Optional[Decimal] = None
    orig_curr_str: Optional[str] = None
    rate_dec: Optional[Decimal] = None
    amount_pence: int = 0

    if payload.original_currency:
        clean_orig = payload.original_currency.strip().upper()
        if clean_orig != acc_currency:
            orig_curr_str = clean_orig
            if payload.original_amount is None or payload.original_amount <= 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="original_amount must be strictly positive when original_currency is specified."
                )
            try:
                orig_amt_dec = validate_origin_amount(payload.original_amount, orig_curr_str)
            except ValueError as e:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

            if payload.amount is not None:
                amount_pence = pounds_to_pence(payload.amount)
                base_major_dec = Decimal(str(payload.amount))
                rate_dec = (base_major_dec / orig_amt_dec).quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP)
            elif payload.exchange_rate is not None:
                rate_dec = Decimal(str(payload.exchange_rate)).quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP)
                base_major_dec = orig_amt_dec * rate_dec
                amount_pence = pounds_to_pence(base_major_dec)
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Either base currency amount or exchange_rate must be provided for foreign transactions."
                )

    if not orig_curr_str:
        if payload.amount is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Transaction amount is required."
            )
        amount_pence = pounds_to_pence(payload.amount)

    if amount_pence <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Transaction amount must be strictly greater than zero."
        )

    dest_account = None
    if payload.transaction_type == TransactionType.TRANSFER:
        if orig_curr_str:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Foreign currency tracking is not supported on internal transfers. Transfers must be in base currency."
            )
        if not payload.destination_account_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Destination account is required for transfers."
            )
        if payload.account_id == payload.destination_account_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Source and destination accounts must be distinct."
            )
        dest_account = db.query(Account).filter(Account.id == payload.destination_account_id).first()
        if not dest_account:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Destination account with ID {payload.destination_account_id} not found."
            )
        if not source_acc or source_acc.currency != base_curr or dest_account.currency != base_curr:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Transfers are only supported between accounts using the base currency ({base_curr})."
            )

        merchant = (payload.merchant.strip() if payload.merchant else "") or f"Transfer to {dest_account.name}"
        if payload.category_id is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Transfers cannot be assigned a category.",
            )
        category_id = None
        expense_nature = ExpenseNature.UNCLASSIFIED
    else:
        merchant = payload.merchant.strip() if payload.merchant and payload.merchant.strip() else None

        category = None
        category_id = payload.category_id
        if category_id is not None:
            try:
                category = validate_category_for_transaction_type(db, category_id, payload.transaction_type)
            except CategoryValidationError as exc:
                raise HTTPException(status_code=exc.status_code, detail=str(exc))

        if payload.transaction_type == TransactionType.EXPENSE:
            if payload.expense_nature is not None:
                expense_nature = payload.expense_nature
            elif category is not None:
                expense_nature = category.default_expense_nature
            else:
                expense_nature = ExpenseNature.UNCLASSIFIED
        else:
            expense_nature = ExpenseNature.UNCLASSIFIED

    clean_notes = payload.notes.strip() if payload.notes and payload.notes.strip() else None

    return ResolvedTransactionFields(
        transaction_type=payload.transaction_type,
        amount_pence=amount_pence,
        merchant=merchant,
        notes=clean_notes,
        account_id=payload.account_id,
        destination_account_id=dest_account.id if dest_account else None,
        category_id=category_id,
        expense_nature=expense_nature,
        original_amount=orig_amt_dec,
        original_currency=orig_curr_str,
        exchange_rate=rate_dec,
    )


def compute_repeat_request_hash(
    resolved: ResolvedTransactionFields,
    frequency: str,
    first_date: date,
    end_mode: str,
    last_date: Optional[date],
    occurrence_count: Optional[int],
    occurrence_dates: List[date],
) -> str:
    """Computes a canonical SHA-256 fingerprint of the repeat transaction request."""
    canonical = {
        "transaction_type": resolved.transaction_type.value,
        "amount_pence": resolved.amount_pence,
        "merchant": resolved.merchant,
        "notes": resolved.notes,
        "account_id": resolved.account_id,
        "destination_account_id": resolved.destination_account_id,
        "category_id": resolved.category_id,
        "expense_nature": resolved.expense_nature.value,
        "original_amount": str(resolved.original_amount) if resolved.original_amount is not None else None,
        "original_currency": resolved.original_currency,
        "exchange_rate": str(resolved.exchange_rate) if resolved.exchange_rate is not None else None,
        "frequency": frequency.strip().lower(),
        "first_date": first_date.isoformat(),
        "end_mode": end_mode.strip().lower(),
        "last_date": last_date.isoformat() if last_date else None,
        "occurrence_count": occurrence_count,
        "occurrence_dates": [d.isoformat() for d in occurrence_dates],
    }
    return hashlib.sha256(json.dumps(canonical, sort_keys=True).encode("utf-8")).hexdigest()


def _load_batch_transactions(db: Session, batch: RepeatSeriesBatch) -> List[Transaction]:
    try:
        tx_ids = json.loads(batch.transaction_ids_json or "[]")
    except Exception:
        tx_ids = []
    if not tx_ids:
        return []
    rows = (
        db.query(Transaction)
        .options(
            joinedload(Transaction.account),
            joinedload(Transaction.destination_account),
            joinedload(Transaction.category),
        )
        .filter(Transaction.id.in_(tx_ids))
        .all()
    )
    by_id = {row.id: row for row in rows}
    return [by_id[tid] for tid in tx_ids if tid in by_id]


def create_repeat_transaction_series(
    db: Session,
    payload: Any,
    header_idempotency_key: Optional[str] = None,
) -> Tuple[RepeatSeriesBatch, List[Transaction], List[date], bool]:
    """
    Validates and atomically creates all occurrences of a repeat series in a single DB transaction.
    Returns (batch_record, created_or_replayed_transactions, resolved_dates, is_idempotent_replay).
    """
    if payload.transaction_type == TransactionType.ADJUSTMENT:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reconciliation adjustments cannot be created as repeating transactions."
        )

    resolved = resolve_validated_transaction_fields(db, payload)

    try:
        dates = generate_repeat_occurrence_dates(
            first_date=payload.first_date,
            frequency=payload.frequency,
            end_mode=payload.end_mode,
            last_date=payload.last_date,
            occurrence_count=payload.occurrence_count,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    raw_key = header_idempotency_key or getattr(payload, "idempotency_key", None)
    clean_idemp_key = raw_key.strip() if raw_key and str(raw_key).strip() else None

    request_hash = compute_repeat_request_hash(
        resolved=resolved,
        frequency=payload.frequency,
        first_date=payload.first_date,
        end_mode=payload.end_mode,
        last_date=payload.last_date,
        occurrence_count=payload.occurrence_count,
        occurrence_dates=dates,
    )

    if clean_idemp_key:
        existing = (
            db.query(RepeatSeriesBatch)
            .filter(RepeatSeriesBatch.idempotency_key == clean_idemp_key)
            .first()
        )
        if existing:
            if existing.request_hash != request_hash:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Idempotency key conflict: parameters differ from the original repeat submission."
                )
            existing_txs = _load_batch_transactions(db, existing)
            return existing, existing_txs, dates, True

    app_tz = get_app_timezone(db)
    today_local = get_today_local(app_tz)
    now_utc = get_now_utc()
    series_id = f"rep_{uuid.uuid4().hex[:12]}"
    effective_idemp_key = clean_idemp_key or f"auto_{uuid.uuid4().hex}"

    txs: List[Transaction] = []
    for occ_date in dates:
        tx_date_utc = get_midday_utc(occ_date, tz_str=app_tz)
        eff_ts_utc = now_utc if occ_date == today_local else tx_date_utc
        tx = Transaction(
            transaction_date=tx_date_utc,
            effective_timestamp=eff_ts_utc,
            created_at=now_utc,
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
            repeat_series_id=series_id,
        )
        txs.append(tx)

    try:
        db.add_all(txs)
        db.flush()

        batch = RepeatSeriesBatch(
            series_id=series_id,
            idempotency_key=effective_idemp_key,
            request_hash=request_hash,
            occurrence_count=len(txs),
            transaction_ids_json=json.dumps([t.id for t in txs]),
            created_at=now_utc,
        )
        db.add(batch)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if clean_idemp_key:
            winning = (
                db.query(RepeatSeriesBatch)
                .filter(RepeatSeriesBatch.idempotency_key == clean_idemp_key)
                .first()
            )
            if winning:
                if winning.request_hash != request_hash:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="Idempotency key conflict: parameters differ from the original repeat submission."
                    )
                return winning, _load_batch_transactions(db, winning), dates, True
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Atomic repeat transaction creation failed due to database constraint; no occurrences were created: {str(exc)}"
        )
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Atomic repeat transaction creation failed; no occurrences were created: {str(exc)}"
        )

    for tx in txs:
        db.refresh(tx)
    db.refresh(batch)
    return batch, txs, dates, False
