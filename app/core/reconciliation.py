"""
Core Account Reconciliation & Ground-Truth Balance Verification Engine.

Provides unified, deterministic balance reconciliation for depository and credit accounts:
- Confirmed statement balance atomically creates a new ground-truth AccountBalanceAnchor.
- Logs an observational AccountSnapshot preserving pre-reconciliation calculated balance,
  confirmed statement balance, discrepancy, and explanation notes.
- Guarantees strict atomicity: if either the snapshot or anchor write fails, both are rolled back.
- Transactions after the anchor affect balances forward from it.
- Transactions on or before the anchor cutoff are treated as already reflected.
- Allows recording an optional missing transaction for cash-flow/spending reporting with
  effective_timestamp <= anchor cutoff, ensuring it does not alter or double-deduct from
  the confirmed anchor balance.
- Prevents investment accounts from using depository reconciliation (they use Portfolio Valuations).
"""

from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional, Union
from sqlalchemy.orm import Session

from app.models import (
    Account,
    AccountType,
    AccountSnapshot,
    AccountBalanceAnchor,
    CategoryType,
    Transaction,
    TransactionType,
    ExpenseNature,
)
from app.core.categories import validate_category_for_transaction_type
from app.ledger import LedgerEngine
from app.core.currency import format_pence, pence_to_pounds, pounds_to_pence
from app.core.cashflow import get_currency_symbol
from app.core.timezone import (
    get_app_timezone,
    resolve_anchor_datetime,
    get_now_utc,
    ensure_utc,
    parse_date_input,
    get_midday_utc,
)

def _format_snapshot_item(snap: AccountSnapshot, currency: str) -> Dict[str, Any]:
    sym = get_currency_symbol(currency)
    disc = snap.discrepancy_pence
    if disc == 0:
        direction = "exact"
    elif disc > 0:
        direction = "actual_higher"
    else:
        direction = "actual_lower"

    return {
        "id": snap.id,
        "account_id": snap.account_id,
        "snapshot_date": snap.snapshot_date,
        "actual_balance_pence": snap.actual_balance_pence,
        "actual_balance_pounds": pence_to_pounds(snap.actual_balance_pence),
        "formatted_actual_balance": format_pence(snap.actual_balance_pence, sym),
        "calculated_balance_pence": snap.calculated_balance_pence,
        "calculated_balance_pounds": pence_to_pounds(snap.calculated_balance_pence),
        "formatted_calculated_balance": format_pence(snap.calculated_balance_pence, sym),
        "discrepancy_pence": disc,
        "discrepancy_pounds": pence_to_pounds(disc),
        "formatted_discrepancy": format_pence(disc, sym),
        "discrepancy_direction": direction,
        "notes": snap.notes,
    }

def _format_anchor_item(anchor: Optional[AccountBalanceAnchor], currency: str) -> Optional[Dict[str, Any]]:
    if not anchor:
        return None
    sym = get_currency_symbol(currency)
    created = anchor.created_at or anchor.anchor_date
    return {
        "id": anchor.id,
        "account_id": anchor.account_id,
        "balance_pence": anchor.balance_pence,
        "balance_pounds": pence_to_pounds(anchor.balance_pence),
        "formatted_balance": format_pence(anchor.balance_pence, sym),
        "anchor_date": anchor.anchor_date,
        "is_opening": anchor.is_opening,
        "notes": anchor.notes,
        "created_at": created,
    }

def get_reconciliation_summary(db: Session, account_id: int) -> Dict[str, Any]:
    """
    Returns current live calculated balance, currency info, latest reconciliation status,
    and active ground-truth anchor checkpoint.
    Raises ValueError if account not found or if it's an investment account.
    """
    account = db.query(Account).filter(Account.id == account_id).first()
    if not account:
        raise ValueError(f"Account with ID {account_id} not found.")

    if account.account_type == AccountType.INVESTMENT:
        raise ValueError(
            "Investment accounts use the Portfolios and Holdings valuation workflow rather than balance reconciliation."
        )

    calculated_pence = LedgerEngine.get_account_balance(db, account_id)
    sym = get_currency_symbol(account.currency)
    app_tz = get_app_timezone(db)

    latest_snap = (
        db.query(AccountSnapshot)
        .filter(AccountSnapshot.account_id == account_id)
        .order_by(AccountSnapshot.snapshot_date.desc(), AccountSnapshot.id.desc())
        .first()
    )

    snapshots_count = (
        db.query(AccountSnapshot)
        .filter(AccountSnapshot.account_id == account_id)
        .count()
    )

    latest_anchor = (
        db.query(AccountBalanceAnchor)
        .filter(AccountBalanceAnchor.account_id == account_id)
        .order_by(AccountBalanceAnchor.anchor_date.desc(), AccountBalanceAnchor.id.desc())
        .first()
    )

    return {
        "account_id": account.id,
        "account_name": account.name,
        "account_type": account.account_type,
        "currency": account.currency,
        "currency_symbol": sym,
        "calculated_balance_pence": calculated_pence,
        "calculated_balance_pounds": pence_to_pounds(calculated_pence),
        "formatted_calculated_balance": format_pence(calculated_pence, sym),
        "last_reconciled_at": latest_snap.snapshot_date if latest_snap else None,
        "last_snapshot": _format_snapshot_item(latest_snap, account.currency) if latest_snap else None,
        "last_anchor": _format_anchor_item(latest_anchor, account.currency),
        "snapshots_count": snapshots_count,
        "app_timezone": app_tz,
    }

def create_reconciliation_snapshot(
    db: Session,
    account_id: int,
    actual_balance_pence: int,
    as_of_mode: str = "now",
    as_of_date: Optional[str] = None,
    snapshot_date: Optional[datetime] = None,
    notes: Optional[str] = None,
    missing_transaction: Optional[Any] = None,
    create_adjustment: bool = False,
    adjustment_notes: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Atomically records:
    1. An observational AccountSnapshot preserving pre-reconciliation calculated balance,
       confirmed statement balance, discrepancy, and notes.
    2. A new ground-truth AccountBalanceAnchor with the confirmed statement balance
       as of the resolved effective timestamp.
    3. If missing_transaction is provided, records a Transaction with effective_timestamp <= anchor_date
       so it is reflected in cash-flow and spending analysis without altering the confirmed balance.

    Rolls back both writes if either fails.
    """
    account = db.query(Account).filter(Account.id == account_id).first()
    if not account:
        raise ValueError(f"Account with ID {account_id} not found.")

    if account.account_type == AccountType.INVESTMENT:
        raise ValueError(
            "Investment accounts use the Portfolios and Holdings valuation workflow rather than balance reconciliation."
        )

    sym = get_currency_symbol(account.currency)
    app_tz = get_app_timezone(db)

    # 1. Resolve anchor date / time
    if snapshot_date is not None:
        anchor_dt = ensure_utc(snapshot_date)
    else:
        anchor_dt = resolve_anchor_datetime(
            as_of_mode=as_of_mode or "now",
            as_of_date=as_of_date,
            tz_str=app_tz,
        )

    # 2. Compute pre-reconciliation calculated balance as of the resolved anchor cutoff
    calculated_pence = LedgerEngine.get_account_balance(db, account_id, as_of=anchor_dt)
    discrepancy_pence = actual_balance_pence - calculated_pence
    clean_notes = notes.strip() if notes else None

    # Explanation message
    if discrepancy_pence == 0:
        explanation = f"Perfect match! Statement balance matches calculated ledger balance exactly ({format_pence(actual_balance_pence, sym)}). Ground-truth anchor confirmed."
    elif discrepancy_pence > 0:
        explanation = f"Confirmed statement balance of {format_pence(actual_balance_pence, sym)} as ground truth ({format_pence(discrepancy_pence, sym)} higher than previous calculated balance)."
    else:
        explanation = f"Confirmed statement balance of {format_pence(actual_balance_pence, sym)} as ground truth ({format_pence(abs(discrepancy_pence), sym)} lower than previous calculated balance)."

    # 3. Atomic Database Operations
    try:
        # A. Create Observational Snapshot
        snapshot = AccountSnapshot(
            account_id=account_id,
            snapshot_date=anchor_dt,
            actual_balance_pence=actual_balance_pence,
            calculated_balance_pence=calculated_pence,
            discrepancy_pence=discrepancy_pence,
            notes=clean_notes,
        )
        db.add(snapshot)

        # B. Create or Update AccountBalanceAnchor
        existing_anchor = (
            db.query(AccountBalanceAnchor)
            .filter(
                AccountBalanceAnchor.account_id == account_id,
                AccountBalanceAnchor.anchor_date == anchor_dt
            )
            .first()
        )
        if existing_anchor:
            existing_anchor.balance_pence = actual_balance_pence
            if clean_notes:
                existing_anchor.notes = clean_notes
            anchor = existing_anchor
        else:
            anchor = AccountBalanceAnchor(
                account_id=account_id,
                balance_pence=actual_balance_pence,
                anchor_date=anchor_dt,
                is_opening=False,
                notes=clean_notes,
            )
            db.add(anchor)

        # C. Optional Missing Transaction for Cash-Flow & Spending Reporting
        missing_tx_created = False
        missing_tx_id = None
        if missing_transaction:
            if isinstance(missing_transaction, dict):
                raw_tx_date = missing_transaction.get("transaction_date")
                tx_type = missing_transaction.get("transaction_type", TransactionType.EXPENSE)
                if isinstance(tx_type, str):
                    tx_type = TransactionType(tx_type)
                tx_amount_pounds = float(missing_transaction.get("amount", 0.0))
                tx_merchant = missing_transaction.get("merchant", "Missing Transaction")
                tx_category_id = missing_transaction.get("category_id")
                tx_notes = missing_transaction.get("notes")
            else:
                raw_tx_date = getattr(missing_transaction, "transaction_date", None)
                tx_type = getattr(missing_transaction, "transaction_type", TransactionType.EXPENSE)
                if isinstance(tx_type, str):
                    tx_type = TransactionType(tx_type)
                tx_amount_pounds = float(getattr(missing_transaction, "amount", 0.0))
                tx_merchant = getattr(missing_transaction, "merchant", "Missing Transaction")
                tx_category_id = getattr(missing_transaction, "category_id", None)
                tx_notes = getattr(missing_transaction, "notes", None)

            if raw_tx_date:
                nominal_date = get_midday_utc(raw_tx_date, tz_str=app_tz)
            else:
                nominal_date = anchor_dt

            # Validate category matches transaction type (clears if transfer/adjustment)
            validated_cat = validate_category_for_transaction_type(db, tx_category_id, tx_type) if tx_category_id is not None else None
            effective_nature = (
                (validated_cat.default_expense_nature if validated_cat and validated_cat.default_expense_nature != ExpenseNature.UNCLASSIFIED else ExpenseNature.VARIABLE)
                if tx_type == TransactionType.EXPENSE
                else ExpenseNature.UNCLASSIFIED
            )

            # Effective timestamp strictly before or at anchor_dt so ledger engine excludes from post-anchor delta
            effective_cutoff = anchor_dt - timedelta(seconds=1)

            missing_tx = Transaction(
                transaction_date=nominal_date,
                effective_timestamp=effective_cutoff,
                created_at=get_now_utc(),
                transaction_type=tx_type,
                amount_pence=pounds_to_pence(tx_amount_pounds),
                merchant=tx_merchant or "Reconciliation Missing Transaction",
                category_id=validated_cat.id if validated_cat else None,
                notes=tx_notes,
                account_id=account_id,
                entry_method="reconciliation_missing_tx",
                expense_nature=effective_nature,
            )
            db.add(missing_tx)
            db.flush()
            missing_tx_created = True
            missing_tx_id = missing_tx.id

        # D. Backward-compatibility: create_adjustment if requested and no missing tx
        adjustment_created = False
        adjustment_tx_id = None
        if create_adjustment and discrepancy_pence != 0 and not missing_transaction:
            adj_extra = (adjustment_notes or "").strip()
            custom_part = f" Note: {adj_extra}" if adj_extra else (f" Note: {clean_notes}" if clean_notes else "")
            if discrepancy_pence > 0:
                adj_tx_notes = f"[Positive adjustment] Reconciliation adjustment: actual {format_pence(actual_balance_pence, sym)} vs calculated {format_pence(calculated_pence, sym)}.{custom_part}".strip()
            else:
                adj_tx_notes = f"Reconciliation adjustment: actual {format_pence(actual_balance_pence, sym)} vs calculated {format_pence(calculated_pence, sym)}.{custom_part}".strip()

            effective_ts = anchor_dt - timedelta(seconds=1)
            adj_tx = Transaction(
                transaction_date=anchor_dt,
                effective_timestamp=effective_ts,
                created_at=get_now_utc(),
                transaction_type=TransactionType.ADJUSTMENT,
                amount_pence=abs(discrepancy_pence),
                merchant="Balance Reconciliation Adjustment",
                notes=adj_tx_notes,
                entry_method="reconciliation",
                account_id=account_id,
                expense_nature=ExpenseNature.UNCLASSIFIED,
            )
            db.add(adj_tx)
            db.flush()
            adjustment_created = True
            adjustment_tx_id = adj_tx.id

        db.commit()
        db.refresh(snapshot)
        db.refresh(anchor)
    except Exception:
        db.rollback()
        raise

    # 4. Final Calculated Balance
    new_calculated_pence = LedgerEngine.get_account_balance(db, account_id)

    return {
        "snapshot": _format_snapshot_item(snapshot, account.currency),
        "anchor": _format_anchor_item(anchor, account.currency),
        "explanation": explanation,
        "missing_transaction_created": missing_tx_created,
        "missing_transaction_id": missing_tx_id,
        "adjustment_created": adjustment_created,
        "adjustment_transaction_id": adjustment_tx_id,
        "new_calculated_balance_pence": new_calculated_pence,
        "new_calculated_balance_pounds": pence_to_pounds(new_calculated_pence),
        "formatted_new_calculated_balance": format_pence(new_calculated_pence, sym),
    }

def list_reconciliation_snapshots(
    db: Session,
    account_id: int,
    limit: int = 50,
    offset: int = 0
) -> List[Dict[str, Any]]:
    """Lists historical reconciliation snapshots for an account in reverse chronological order."""
    account = db.query(Account).filter(Account.id == account_id).first()
    if not account:
        raise ValueError(f"Account with ID {account_id} not found.")

    snapshots = (
        db.query(AccountSnapshot)
        .filter(AccountSnapshot.account_id == account_id)
        .order_by(AccountSnapshot.snapshot_date.desc(), AccountSnapshot.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    return [_format_snapshot_item(s, account.currency) for s in snapshots]

def delete_reconciliation_snapshot(db: Session, account_id: int, snapshot_id: int) -> None:
    """Deletes a historical reconciliation snapshot without altering any ledger transactions or balance anchors."""
    snap = (
        db.query(AccountSnapshot)
        .filter(
            AccountSnapshot.id == snapshot_id,
            AccountSnapshot.account_id == account_id
        )
        .first()
    )
    if not snap:
        raise ValueError(f"Reconciliation snapshot with ID {snapshot_id} not found for account {account_id}.")

    db.delete(snap)
    db.commit()
