from typing import List, Optional
from zoneinfo import ZoneInfo
from fastapi import APIRouter, Depends, HTTPException, status, Response
from sqlalchemy.orm import Session
from sqlalchemy import or_, func

from app.database import get_db
from app.models import (
    Account, AccountType, Transaction, AccountSnapshot, 
    AssetSnapshot, Holding, HoldingValuation, StagingItem,
    AccountBalanceAnchor, TransactionType
)
from app.schemas import (
    AccountCreate, AccountUpdate, AccountResponse, AccountDeletionImpact,
    AccountBalanceAnchorCreate, AccountBalanceAnchorResponse,
    AccountBreakdownResponse, AccountBreakdownAnchor, AccountBreakdownMovement,
    AccountBreakdownLiability, AccountBreakdownInvestment, AccountBreakdownRecentTx,
    AccountSnapshotItem
)
from app.ledger import LedgerEngine
from app.core.currency import (
    pence_to_pounds, format_pence, pounds_to_pence, 
    get_effective_base_currency, get_currency_spec
)
from app.core.timezone import (
    resolve_anchor_datetime, get_app_timezone, ensure_utc,
    get_now_utc, get_today_local, get_end_of_day_utc
)

router = APIRouter(prefix="/accounts")

def _to_account_response(db: Session, account: Account) -> AccountResponse:
    info = LedgerEngine.get_account_balance_info(db, account.id)
    current_balance_pence = info["current_balance_pence"]
    holdings_count = 0
    has_unvalued = False
    val_mode = getattr(account, "valuation_mode", "snapshot") or "snapshot"

    last_reconciled_at = None
    last_reconciled_discrepancy_pence = None

    if account.account_type == AccountType.INVESTMENT:
        from app.core.investments import get_account_holdings_breakdown
        breakdown = get_account_holdings_breakdown(db, account.id)
        holdings_count = breakdown["holdings_count"]
        has_unvalued = breakdown["has_unvalued_holdings"]
    else:
        latest_snap = (
            db.query(AccountSnapshot)
            .filter(AccountSnapshot.account_id == account.id)
            .order_by(AccountSnapshot.snapshot_date.desc(), AccountSnapshot.id.desc())
            .first()
        )
        if latest_snap:
            last_reconciled_at = latest_snap.snapshot_date
            last_reconciled_discrepancy_pence = latest_snap.discrepancy_pence

    curr_spec = get_currency_spec(account.currency)
    formatted_bal = format_pence(current_balance_pence, currency_symbol=curr_spec.symbol)

    return AccountResponse(
        id=account.id,
        name=account.name,
        account_type=account.account_type,
        currency=account.currency,
        color=account.color,
        is_active=account.is_active,
        created_at=account.created_at,
        valuation_mode=val_mode,
        holdings_count=holdings_count,
        has_unvalued_holdings=has_unvalued,
        last_reconciled_at=last_reconciled_at,
        last_reconciled_discrepancy_pence=last_reconciled_discrepancy_pence,
        starting_balance_pence=account.starting_balance_pence,
        starting_balance_pounds=pence_to_pounds(account.starting_balance_pence),
        current_balance_pence=current_balance_pence,
        current_balance_pounds=pence_to_pounds(current_balance_pence),
        formatted_balance=formatted_bal,
        anchor_label=info["anchor_label"],
        anchor_date=info["anchor_date"],
        anchor_balance_pence=info["anchor_balance_pence"],
        delta_since_anchor_pence=info["delta_since_anchor_pence"],
        is_opening_anchor=info["is_opening"],
        planned_delta_pence=info.get("planned_delta_pence", 0),
        formatted_planned_delta=info.get("formatted_planned_delta", "£0.00"),
        projected_balance_pence=info.get("projected_balance_pence"),
        formatted_projected_balance=info.get("formatted_projected_balance"),
    )

@router.get("", response_model=List[AccountResponse])
def list_accounts(include_inactive: bool = False, db: Session = Depends(get_db)):
    """List all accounts with their dynamically calculated ledger balance."""
    query = db.query(Account)
    if not include_inactive:
        query = query.filter(Account.is_active == True)
    accounts = query.order_by(Account.created_at.asc(), Account.id.asc()).all()
    return [_to_account_response(db, acc) for acc in accounts]

@router.post("", response_model=AccountResponse, status_code=status.HTTP_201_CREATED)
def create_account(payload: AccountCreate, db: Session = Depends(get_db)):
    """Creates a new financial account, enforcing the configured base currency."""
    clean_name = payload.name.strip()
    existing = db.query(Account).filter(Account.name.ilike(clean_name)).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"An account named '{clean_name}' already exists."
        )

    base_curr = get_effective_base_currency(db)
    if payload.currency:
        clean_curr = payload.currency.strip().upper()
        if clean_curr != base_curr:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Account currency '{payload.currency}' does not match the configured base currency '{base_curr}'. "
                    f"In this milestone, all financial accounts must use the base currency ({base_curr}). "
                    f"Foreign transactions must be recorded on base currency accounts with transaction-level origin metadata."
                )
            )
    else:
        clean_curr = base_curr

    if payload.account_type == AccountType.INVESTMENT:
        val_mode = "holdings"
        starting_pence = 0
        starting_dt = None
    else:
        val_mode = payload.valuation_mode or "snapshot"
        starting_pence = pounds_to_pence(payload.starting_balance)
        starting_dt = resolve_anchor_datetime(
            as_of_mode=payload.as_of_mode or "now",
            as_of_date=payload.as_of_date,
            tz_str=get_app_timezone(db)
        )

    account = Account(
        name=clean_name,
        account_type=payload.account_type,
        currency=clean_curr,
        color=payload.color or "#3B82F6",
        starting_balance_pence=starting_pence,
        starting_balance_date=starting_dt,
        valuation_mode=val_mode,
        is_active=True
    )
    db.add(account)
    db.commit()
    db.refresh(account)
    return _to_account_response(db, account)

@router.get("/{account_id}", response_model=AccountResponse)
def get_account(account_id: int, db: Session = Depends(get_db)):
    """Retrieves an account by ID."""
    account = db.query(Account).filter(Account.id == account_id).first()
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found.")
    return _to_account_response(db, account)

@router.get("/{account_id}/breakdown", response_model=AccountBreakdownResponse)
def get_account_breakdown(account_id: int, db: Session = Depends(get_db)):
    """
    Returns an extensive financial breakdown for an account:
    - Current balance and starting balance
    - Account grouping (Depository, Credit Liabilities, Investment Portfolios)
    - Ground-truth anchor details vs post-anchor ledger movements
    - Inflows, outflows, transfers satisfying: anchor + movement = current_balance
    - Credit card liability explanation and owed balance
    - Investment holdings and valuation breakdown
    - 10 most recent transactions
    - Ground-truth anchors vs observational snapshots separation
    """
    account = db.query(Account).filter(Account.id == account_id).first()
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found.")

    info = LedgerEngine.get_account_balance_info(db, account.id)
    curr_bal_pence = info["current_balance_pence"]
    curr_spec = get_currency_spec(account.currency)
    app_tz = get_app_timezone(db)

    # Grouping
    if account.account_type in (AccountType.CURRENT, AccountType.SAVINGS):
        account_group = "Depository Accounts"
    elif account.account_type == AccountType.CASH:
        account_group = "Cash Accounts"
    elif account.account_type == AccountType.CREDIT_CARD:
        account_group = "Credit Liabilities"
    elif account.account_type == AccountType.INVESTMENT:
        account_group = "Investment Portfolios"
    else:
        account_group = "Depository Accounts"

    # Latest ground-truth anchor (opening balance anchor or confirmed statement anchor)
    latest_anchor = db.query(AccountBalanceAnchor).filter(
        AccountBalanceAnchor.account_id == account.id
    ).order_by(
        AccountBalanceAnchor.anchor_date.desc(),
        AccountBalanceAnchor.id.desc()
    ).first()

    if latest_anchor:
        try:
            local_dt = ensure_utc(latest_anchor.anchor_date).astimezone(ZoneInfo(app_tz))
            anchor_date_local = local_dt.strftime("%d/%m/%Y %H:%M %Z")
            anchor_type_str = "Opening balance anchor" if latest_anchor.is_opening else "Confirmed anchor"
            anchor_label = f"{anchor_type_str} as of {local_dt.strftime('%d/%m/%Y %H:%M')}"
        except Exception:
            anchor_date_local = str(latest_anchor.anchor_date)
            anchor_type_str = "Opening balance anchor" if latest_anchor.is_opening else "Confirmed anchor"
            anchor_label = f"{anchor_type_str} as of {latest_anchor.anchor_date}"

        anchor_anchor = AccountBreakdownAnchor(
            has_anchor=True,
            anchor_id=latest_anchor.id,
            balance_pence=latest_anchor.balance_pence,
            formatted_balance=format_pence(latest_anchor.balance_pence, currency_symbol=curr_spec.symbol),
            anchor_date=latest_anchor.anchor_date,
            anchor_date_local=anchor_date_local,
            is_opening=latest_anchor.is_opening,
            notes=latest_anchor.notes,
            label=anchor_label
        )
        base_balance_pence = latest_anchor.balance_pence
        cutoff_dt = latest_anchor.anchor_date
    else:
        anchor_anchor = AccountBreakdownAnchor(
            has_anchor=False,
            anchor_id=None,
            balance_pence=None,
            formatted_balance=None,
            anchor_date=None,
            anchor_date_local=None,
            is_opening=False,
            notes=None,
            label="No ground-truth anchor set (calculated from opening balance)"
        )
        base_balance_pence = account.starting_balance_pence
        cutoff_dt = None

    # Post-anchor movement breakdown
    net_movement_pence = curr_bal_pence - base_balance_pence

    today_local = get_today_local(app_tz)
    end_of_today_utc = get_end_of_day_utc(today_local, tz_str=app_tz)

    effective_dt_col = func.coalesce(Transaction.effective_timestamp, Transaction.transaction_date)
    tx_q = db.query(Transaction).filter(
        Transaction.deleted_at.is_(None),
        or_(
            Transaction.account_id == account.id,
            Transaction.destination_account_id == account.id
        )
    )
    if cutoff_dt:
        tx_q = tx_q.filter(effective_dt_col > cutoff_dt)

    post_anchor_txs = tx_q.all()

    actual_txs = [t for t in post_anchor_txs if ensure_utc(t.effective_timestamp or t.transaction_date) <= end_of_today_utc]
    planned_txs = [t for t in post_anchor_txs if ensure_utc(t.effective_timestamp or t.transaction_date) > end_of_today_utc]

    inflows_pence = 0
    outflows_pence = 0
    transfers_in_pence = 0
    transfers_out_pence = 0
    adjustments_net_pence = 0

    for t in actual_txs:
        amt = t.amount_pence or 0
        if t.transaction_type == TransactionType.INCOME:
            if t.account_id == account.id:
                inflows_pence += amt
        elif t.transaction_type == TransactionType.EXPENSE:
            if t.account_id == account.id:
                outflows_pence += amt
        elif t.transaction_type == TransactionType.TRANSFER:
            if t.destination_account_id == account.id:
                transfers_in_pence += amt
            if t.account_id == account.id:
                transfers_out_pence += amt
        elif t.transaction_type == TransactionType.ADJUSTMENT:
            if t.account_id == account.id:
                if t.notes and "[Positive adjustment]" in t.notes:
                    adjustments_net_pence += amt
                else:
                    adjustments_net_pence -= amt

    movement = AccountBreakdownMovement(
        inflows_pence=inflows_pence,
        formatted_inflows=format_pence(inflows_pence, currency_symbol=curr_spec.symbol),
        outflows_pence=outflows_pence,
        formatted_outflows=format_pence(outflows_pence, currency_symbol=curr_spec.symbol),
        transfers_in_pence=transfers_in_pence,
        formatted_transfers_in=format_pence(transfers_in_pence, currency_symbol=curr_spec.symbol),
        transfers_out_pence=transfers_out_pence,
        formatted_transfers_out=format_pence(transfers_out_pence, currency_symbol=curr_spec.symbol),
        adjustments_net_pence=adjustments_net_pence,
        formatted_adjustments_net=format_pence(adjustments_net_pence, currency_symbol=curr_spec.symbol),
        net_movement_pence=net_movement_pence,
        formatted_net_movement=format_pence(net_movement_pence, currency_symbol=curr_spec.symbol),
        transaction_count=len(actual_txs)
    )

    planned_movement = None
    if planned_txs:
        p_inflows_pence = 0
        p_outflows_pence = 0
        p_transfers_in_pence = 0
        p_transfers_out_pence = 0
        p_adjustments_net_pence = 0

        for t in planned_txs:
            amt = t.amount_pence or 0
            if t.transaction_type == TransactionType.INCOME:
                if t.account_id == account.id:
                    p_inflows_pence += amt
            elif t.transaction_type == TransactionType.EXPENSE:
                if t.account_id == account.id:
                    p_outflows_pence += amt
            elif t.transaction_type == TransactionType.TRANSFER:
                if t.destination_account_id == account.id:
                    p_transfers_in_pence += amt
                if t.account_id == account.id:
                    p_transfers_out_pence += amt
            elif t.transaction_type == TransactionType.ADJUSTMENT:
                if t.account_id == account.id:
                    if t.notes and "[Positive adjustment]" in t.notes:
                        p_adjustments_net_pence += amt
                    else:
                        p_adjustments_net_pence -= amt

        p_net_pence = (p_inflows_pence + p_transfers_in_pence + p_adjustments_net_pence) - (p_outflows_pence + p_transfers_out_pence)
        planned_movement = AccountBreakdownMovement(
            inflows_pence=p_inflows_pence,
            formatted_inflows=format_pence(p_inflows_pence, currency_symbol=curr_spec.symbol),
            outflows_pence=p_outflows_pence,
            formatted_outflows=format_pence(p_outflows_pence, currency_symbol=curr_spec.symbol),
            transfers_in_pence=p_transfers_in_pence,
            formatted_transfers_in=format_pence(p_transfers_in_pence, currency_symbol=curr_spec.symbol),
            transfers_out_pence=p_transfers_out_pence,
            formatted_transfers_out=format_pence(p_transfers_out_pence, currency_symbol=curr_spec.symbol),
            adjustments_net_pence=p_adjustments_net_pence,
            formatted_adjustments_net=format_pence(p_adjustments_net_pence, currency_symbol=curr_spec.symbol),
            net_movement_pence=p_net_pence,
            formatted_net_movement=format_pence(p_net_pence, currency_symbol=curr_spec.symbol),
            transaction_count=len(planned_txs)
        )

    projected_bal_pence = curr_bal_pence + (planned_movement.net_movement_pence if planned_movement else 0)
    formatted_projected_bal = format_pence(projected_bal_pence, currency_symbol=curr_spec.symbol)

    # Liability details for Credit Cards
    liability = None
    if account.account_type == AccountType.CREDIT_CARD:
        owed_pence = abs(curr_bal_pence) if curr_bal_pence < 0 else 0
        liability = AccountBreakdownLiability(
            is_liability=True,
            amount_owed_pence=owed_pence,
            formatted_amount_owed=format_pence(owed_pence, currency_symbol=curr_spec.symbol),
            explanation="Credit card balances are tracked as liabilities. A negative balance (e.g. -£150.00) indicates an outstanding balance owed on the card. Payments to the card reduce this liability."
        )

    # Investment details
    investment = None
    if account.account_type == AccountType.INVESTMENT:
        from app.core.investments import get_account_holdings_breakdown
        breakdown = get_account_holdings_breakdown(db, account.id)
        latest_val_dt = None
        for d in breakdown.get("details", []):
            val = d.get("latest_valuation")
            if val and val.effective_date:
                if latest_val_dt is None or val.effective_date > latest_val_dt:
                    latest_val_dt = val.effective_date

        val_date_str = None
        if latest_val_dt:
            try:
                local_val_dt = ensure_utc(latest_val_dt).astimezone(ZoneInfo(app_tz))
                val_date_str = local_val_dt.strftime("%d/%m/%Y")
            except Exception:
                val_date_str = str(latest_val_dt)[:10]

        investment = AccountBreakdownInvestment(
            is_investment=True,
            valuation_mode=getattr(account, "valuation_mode", "snapshot") or "snapshot",
            holdings_count=breakdown["holdings_count"],
            valued_count=breakdown["valued_count"],
            unvalued_count=breakdown["unvalued_count"],
            has_unvalued_holdings=breakdown["has_unvalued_holdings"],
            latest_valuation_date=latest_val_dt,
            latest_valuation_date_formatted=val_date_str,
            explanation="Investment account valuation derives directly from active security holdings and their latest market valuations, rather than ground-truth cash anchors."
        )

    # 10 Most Recent Transactions (excluding soft-deleted)
    recent_txs = db.query(Transaction).filter(
        Transaction.deleted_at.is_(None),
        or_(
            Transaction.account_id == account.id,
            Transaction.destination_account_id == account.id
        )
    ).order_by(
        func.coalesce(Transaction.effective_timestamp, Transaction.transaction_date).desc(),
        Transaction.id.desc()
    ).limit(10).all()

    recent_items = []
    for t in recent_txs:
        cat_name = t.category.name if t.category else None
        cat_color = t.category.color if t.category else None
        eff_utc = ensure_utc(t.effective_timestamp or t.transaction_date)
        is_planned = eff_utc > end_of_today_utc if eff_utc else False
        recent_items.append(AccountBreakdownRecentTx(
            id=t.id,
            transaction_date=t.transaction_date,
            effective_timestamp=t.effective_timestamp,
            transaction_type=t.transaction_type.value,
            amount_pence=t.amount_pence,
            formatted_amount=format_pence(t.amount_pence, currency_symbol=curr_spec.symbol),
            merchant=t.merchant,
            notes=t.notes,
            category_name=cat_name,
            category_color=cat_color,
            is_planned=is_planned,
        ))

    # All Ground-Truth Anchors
    all_anchors = db.query(AccountBalanceAnchor).filter(
        AccountBalanceAnchor.account_id == account.id
    ).order_by(
        AccountBalanceAnchor.anchor_date.desc(),
        AccountBalanceAnchor.id.desc()
    ).all()

    anchors_resp = [
        AccountBalanceAnchorResponse(
            id=a.id,
            account_id=a.account_id,
            balance_pence=a.balance_pence,
            balance_pounds=pence_to_pounds(a.balance_pence),
            formatted_balance=format_pence(a.balance_pence, curr_spec.symbol),
            anchor_date=a.anchor_date,
            is_opening=a.is_opening,
            notes=a.notes,
            created_at=a.created_at
        )
        for a in all_anchors
    ]

    # All Observational Snapshots
    from app.core.reconciliation import list_reconciliation_snapshots
    snapshots_data = list_reconciliation_snapshots(db=db, account_id=account.id, limit=50)
    snapshots_resp = [AccountSnapshotItem(**s) for s in snapshots_data]

    return AccountBreakdownResponse(
        account_id=account.id,
        account_name=account.name,
        account_type=account.account_type.value,
        account_group=account_group,
        currency=account.currency,
        currency_symbol=curr_spec.symbol,
        color=account.color or "#3B82F6",
        is_active=account.is_active,
        current_balance_pence=curr_bal_pence,
        formatted_current_balance=format_pence(curr_bal_pence, currency_symbol=curr_spec.symbol),
        current_balance_pounds=pence_to_pounds(curr_bal_pence),
        starting_balance_pence=account.starting_balance_pence,
        formatted_starting_balance=format_pence(account.starting_balance_pence, currency_symbol=curr_spec.symbol),
        anchor=anchor_anchor,
        movement=movement,
        planned_movement=planned_movement,
        projected_balance_pence=projected_bal_pence,
        formatted_projected_balance=formatted_projected_bal,
        liability=liability,
        investment=investment,
        recent_transactions=recent_items,
        anchors=anchors_resp,
        snapshots=snapshots_resp,
        app_timezone=app_tz
    )

@router.put("/{account_id}", response_model=AccountResponse)
def update_account(account_id: int, payload: AccountUpdate, db: Session = Depends(get_db)):
    """Updates account metadata, strictly enforcing base currency."""
    account = db.query(Account).filter(Account.id == account_id).first()
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found.")

    base_curr = get_effective_base_currency(db)
    if payload.currency is not None:
        clean_curr = payload.currency.strip().upper()
        if clean_curr != base_curr:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Cannot change account currency to '{payload.currency}'. "
                    f"In this milestone, all financial accounts must use the configured base currency ({base_curr})."
                )
            )

    if payload.name is not None:
        clean_name = payload.name.strip()
        existing = db.query(Account).filter(Account.name.ilike(clean_name), Account.id != account_id).first()
        if existing:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Account '{clean_name}' already exists.")
        account.name = clean_name

    if payload.account_type is not None:
        account.account_type = payload.account_type
    if payload.color is not None:
        account.color = payload.color
    if payload.is_active is not None:
        account.is_active = payload.is_active
    if payload.valuation_mode is not None:
        account.valuation_mode = payload.valuation_mode

    if payload.starting_balance is not None:
        bal_pence = pounds_to_pence(payload.starting_balance)
        opening_anchor = account.opening_anchor
        if opening_anchor:
            opening_anchor.balance_pence = bal_pence
            if payload.as_of_mode or payload.as_of_date:
                opening_anchor.anchor_date = resolve_anchor_datetime(
                    as_of_mode=payload.as_of_mode or "now",
                    as_of_date=payload.as_of_date,
                    tz_str=get_app_timezone(db)
                )
        else:
            anchor_dt = resolve_anchor_datetime(
                as_of_mode=payload.as_of_mode or "now",
                as_of_date=payload.as_of_date,
                tz_str=get_app_timezone(db)
            )
            new_anchor = AccountBalanceAnchor(
                account_id=account.id,
                balance_pence=bal_pence,
                anchor_date=anchor_dt,
                is_opening=True,
                notes="Opening balance anchor"
            )
            db.add(new_anchor)

    db.commit()
    db.refresh(account)
    return _to_account_response(db, account)

@router.get("/{account_id}/anchors", response_model=List[AccountBalanceAnchorResponse])
def list_account_anchors(account_id: int, db: Session = Depends(get_db)):
    """Lists all dated balance anchors for an account."""
    account = db.query(Account).filter(Account.id == account_id).first()
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found.")

    anchors = (
        db.query(AccountBalanceAnchor)
        .filter(AccountBalanceAnchor.account_id == account_id)
        .order_by(AccountBalanceAnchor.anchor_date.desc(), AccountBalanceAnchor.id.desc())
        .all()
    )
    curr_spec = get_currency_spec(account.currency)
    return [
        AccountBalanceAnchorResponse(
            id=a.id,
            account_id=a.account_id,
            balance_pence=a.balance_pence,
            balance_pounds=pence_to_pounds(a.balance_pence),
            formatted_balance=format_pence(a.balance_pence, currency_symbol=curr_spec.symbol),
            anchor_date=a.anchor_date,
            is_opening=a.is_opening,
            notes=a.notes,
            created_at=a.created_at
        )
        for a in anchors
    ]

@router.post("/{account_id}/anchors", response_model=AccountBalanceAnchorResponse, status_code=status.HTTP_201_CREATED)
def create_account_anchor(account_id: int, payload: AccountBalanceAnchorCreate, db: Session = Depends(get_db)):
    """Records a new dated balance anchor checkpoint or updates an existing anchor on the same date."""
    account = db.query(Account).filter(Account.id == account_id).first()
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found.")

    anchor_dt = resolve_anchor_datetime(
        as_of_mode=payload.as_of_mode,
        as_of_date=payload.as_of_date,
        tz_str=get_app_timezone(db)
    )
    bal_pence = pounds_to_pence(payload.balance)

    # Check if an anchor already exists at this exact anchor_date
    existing = db.query(AccountBalanceAnchor).filter(
        AccountBalanceAnchor.account_id == account_id,
        AccountBalanceAnchor.anchor_date == anchor_dt
    ).first()

    if existing:
        existing.balance_pence = bal_pence
        if payload.notes is not None:
            existing.notes = payload.notes.strip() if payload.notes else None
        anchor = existing
    else:
        anchor = AccountBalanceAnchor(
            account_id=account_id,
            balance_pence=bal_pence,
            anchor_date=anchor_dt,
            is_opening=False,
            notes=payload.notes.strip() if payload.notes else None
        )
        db.add(anchor)

    db.commit()
    db.refresh(anchor)

    curr_spec = get_currency_spec(account.currency)
    return AccountBalanceAnchorResponse(
        id=anchor.id,
        account_id=anchor.account_id,
        balance_pence=anchor.balance_pence,
        balance_pounds=pence_to_pounds(anchor.balance_pence),
        formatted_balance=format_pence(anchor.balance_pence, currency_symbol=curr_spec.symbol),
        anchor_date=anchor.anchor_date,
        is_opening=anchor.is_opening,
        notes=anchor.notes,
        created_at=anchor.created_at
    )

@router.delete("/{account_id}/anchors/{anchor_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_account_anchor(account_id: int, anchor_id: int, db: Session = Depends(get_db)):
    """Deletes an account balance checkpoint. The opening anchor cannot be deleted."""
    account = db.query(Account).filter(Account.id == account_id).first()
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found.")

    anchor = db.query(AccountBalanceAnchor).filter(
        AccountBalanceAnchor.id == anchor_id,
        AccountBalanceAnchor.account_id == account_id
    ).first()
    if not anchor:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Balance anchor not found.")

    if anchor.is_opening:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete the opening balance anchor. You can update its value by editing the account."
        )

    db.delete(anchor)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)

@router.get("/{account_id}/deletion-impact", response_model=AccountDeletionImpact)
def get_account_deletion_impact(account_id: int, db: Session = Depends(get_db)):
    """Computes the full destructive impact of permanently deleting an account."""
    account = db.query(Account).filter(Account.id == account_id).first()
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found.")

    # Standard transactions where this is the primary account (excluding transfers)
    std_tx_count = (
        db.query(Transaction)
        .filter(Transaction.account_id == account_id, Transaction.destination_account_id == None)
        .count()
    )

    # Transfers where this account is either source or destination
    transfer_count = (
        db.query(Transaction)
        .filter(
            (Transaction.account_id == account_id) & (Transaction.destination_account_id != None) |
            (Transaction.destination_account_id == account_id)
        )
        .count()
    )

    # Snapshots (reconciliation snapshots + asset snapshots)
    snap_count = db.query(AccountSnapshot).filter(AccountSnapshot.account_id == account_id).count()
    asset_snap_count = db.query(AssetSnapshot).filter(AssetSnapshot.account_id == account_id).count()
    total_snapshots = snap_count + asset_snap_count

    # Holdings and valuations
    holdings = db.query(Holding).filter(Holding.account_id == account_id).all()
    holding_count = len(holdings)
    holding_ids = [h.id for h in holdings]
    val_count = (
        db.query(HoldingValuation)
        .filter(HoldingValuation.holding_id.in_(holding_ids))
        .count()
        if holding_ids else 0
    )

    return AccountDeletionImpact(
        account_id=account.id,
        account_name=account.name,
        currency=account.currency,
        transaction_count=std_tx_count,
        transfer_count=transfer_count,
        snapshot_count=total_snapshots,
        holding_count=holding_count,
        holding_valuation_count=val_count,
    )

@router.delete("/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_account(account_id: int, permanent: bool = False, db: Session = Depends(get_db)):
    """Soft-deletes (archives) or permanently deletes an account and all linked records."""
    account = db.query(Account).filter(Account.id == account_id).first()
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found.")

    if not permanent:
        account.is_active = False
        db.commit()
        return None

    # Permanent deletion: atomic destruction of account and linked records
    try:
        # 1. Delete all transactions involving this account (source or destination)
        db.query(Transaction).filter(
            (Transaction.account_id == account_id) | (Transaction.destination_account_id == account_id)
        ).delete(synchronize_session=False)

        # 2. Delete reconciliation snapshots & asset snapshots
        db.query(AccountSnapshot).filter(AccountSnapshot.account_id == account_id).delete(synchronize_session=False)
        db.query(AssetSnapshot).filter(AssetSnapshot.account_id == account_id).delete(synchronize_session=False)

        # 3. Delete holding valuations and holdings
        holdings = db.query(Holding).filter(Holding.account_id == account_id).all()
        holding_ids = [h.id for h in holdings]
        if holding_ids:
            db.query(HoldingValuation).filter(HoldingValuation.holding_id.in_(holding_ids)).delete(synchronize_session=False)
            db.query(Holding).filter(Holding.account_id == account_id).delete(synchronize_session=False)

        # 4. Clear staging references if any
        db.query(StagingItem).filter(StagingItem.suggested_account_id == account_id).update(
            {"suggested_account_id": None}, synchronize_session=False
        )

        # 5. Delete account
        db.delete(account)
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to permanently delete account: {str(exc)}"
        )

    return None

