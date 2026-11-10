from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.database import get_db
from app.models import Account, AccountType, AssetSnapshot, Holding, HoldingValuation
from app.schemas import (
    HoldingCreate, HoldingUpdate, HoldingResponse,
    HoldingValuationCreate, HoldingValuationUpdate, HoldingValuationResponse,
    AccountValuationModeUpdate, AccountHoldingsResponse,
    PortfolioSummaryResponse, CheckpointSyncRequest, CheckpointSyncResponse,
    AccountResponse
)
from app.core.investments import (
    get_holding_latest_valuation, get_account_holdings_breakdown,
    sync_account_checkpoint_snapshot, get_portfolio_summary, CHECKPOINT_TAG
)
from app.core.currency import pounds_to_pence, pence_to_pounds, format_pence, format_unit_price
from app.api.accounts import _to_account_response

router = APIRouter(prefix="/investments")

def _to_valuation_response(v: HoldingValuation, currency: str) -> HoldingValuationResponse:
    sym = "£" if currency == "GBP" else f"{currency} "
    if v.unit_price_pence is not None:
        up_dec = (Decimal(str(v.unit_price_pence)) / Decimal(100)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
        up_pounds = float(up_dec)
        fmt_up = format_unit_price(up_dec, sym.strip())
    else:
        up_pounds = None
        fmt_up = None

    val_pounds = pence_to_pounds(v.valuation_pence)
    fmt_val = format_pence(v.valuation_pence, currency_symbol=sym)

    return HoldingValuationResponse(
        id=v.id,
        holding_id=v.holding_id,
        effective_date=v.effective_date,
        quantity=float(v.quantity),
        unit_price_pence=float(v.unit_price_pence) if v.unit_price_pence is not None else None,
        unit_price_pounds=up_pounds,
        formatted_unit_price=fmt_up,
        valuation_pence=v.valuation_pence,
        valuation_pounds=val_pounds,
        formatted_valuation=fmt_val,
        currency=currency,
        notes=v.notes,
        created_at=v.created_at
    )

def _to_holding_response(db: Session, h: Holding) -> HoldingResponse:
    latest = get_holding_latest_valuation(db, h.id)
    currency = h.currency or (h.account.currency if h.account else "GBP")
    sym = "£" if currency == "GBP" else f"{currency} "

    if latest is not None:
        val_pounds = pence_to_pounds(latest.valuation_pence)
        fmt_val = format_pence(latest.valuation_pence, currency_symbol=sym)
        if latest.unit_price_pence is not None:
            up_dec = (Decimal(str(latest.unit_price_pence)) / Decimal(100)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
            up_pounds = float(up_dec)
            fmt_up = format_unit_price(up_dec, sym.strip())
        else:
            up_pounds = None
            fmt_up = None

        return HoldingResponse(
            id=h.id,
            account_id=h.account_id,
            name=h.name,
            ticker=h.ticker,
            asset_class=h.asset_class,
            currency=currency,
            is_active=h.is_active,
            notes=h.notes,
            created_at=h.created_at,
            is_valued=True,
            latest_quantity=float(latest.quantity),
            latest_unit_price_pounds=up_pounds,
            formatted_unit_price=fmt_up,
            latest_valuation_pence=latest.valuation_pence,
            latest_valuation_pounds=val_pounds,
            formatted_valuation=fmt_val,
            last_valuation_date=latest.effective_date
        )
    else:
        return HoldingResponse(
            id=h.id,
            account_id=h.account_id,
            name=h.name,
            ticker=h.ticker,
            asset_class=h.asset_class,
            currency=currency,
            is_active=h.is_active,
            notes=h.notes,
            created_at=h.created_at,
            is_valued=False,
            latest_quantity=None,
            latest_unit_price_pounds=None,
            formatted_unit_price=None,
            latest_valuation_pence=None,
            latest_valuation_pounds=None,
            formatted_valuation=None,
            last_valuation_date=None
        )

@router.get("/summary", response_model=PortfolioSummaryResponse)
def get_investments_summary(db: Session = Depends(get_db)):
    """Computes executive portfolio summary: total invested, account breakdown, asset allocation."""
    return get_portfolio_summary(db)

@router.get("/accounts/{account_id}/holdings", response_model=AccountHoldingsResponse)
def get_account_holdings(account_id: int, db: Session = Depends(get_db)):
    """Lists all holdings for an investment account with latest valuations and rollups."""
    account = db.query(Account).filter(Account.id == account_id).first()
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found.")
    if account.account_type != AccountType.INVESTMENT:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Account is not an investment account.")

    breakdown = get_account_holdings_breakdown(db, account_id)
    holdings = db.query(Holding).filter(
        Holding.account_id == account_id
    ).order_by(Holding.is_active.desc(), Holding.name.asc()).all()

    sym = "£" if account.currency == "GBP" else f"{account.currency} "
    return AccountHoldingsResponse(
        account_id=account.id,
        account_name=account.name,
        currency=account.currency,
        valuation_mode=account.valuation_mode or "snapshot",
        total_valuation_pence=breakdown["total_pence"],
        total_valuation_pounds=breakdown["total_pounds"],
        formatted_total_valuation=format_pence(breakdown["total_pence"], currency_symbol=sym),
        holdings_count=breakdown["holdings_count"],
        valued_count=breakdown["valued_count"],
        unvalued_count=breakdown["unvalued_count"],
        has_unvalued_holdings=breakdown["has_unvalued_holdings"],
        holdings=[_to_holding_response(db, h) for h in holdings]
    )

@router.post("/accounts/{account_id}/holdings", response_model=HoldingResponse, status_code=status.HTTP_201_CREATED)
def create_holding(account_id: int, payload: HoldingCreate, db: Session = Depends(get_db)):
    """Creates a new individual holding within an investment account."""
    account = db.query(Account).filter(Account.id == account_id).first()
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found.")
    if account.account_type != AccountType.INVESTMENT:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Account is not an investment account.")

    holding = Holding(
        account_id=account.id,
        name=payload.name.strip(),
        ticker=payload.ticker.strip().upper() if payload.ticker else None,
        asset_class=payload.asset_class.strip().lower() if payload.asset_class else "equity",
        currency=payload.currency.strip().upper() if payload.currency else account.currency,
        notes=payload.notes,
        is_active=True
    )
    db.add(holding)
    db.commit()
    db.refresh(holding)

    # Optional initial valuation
    if payload.initial_quantity is not None:
        qty = Decimal(str(payload.initial_quantity))
        eff_date = payload.initial_effective_date or datetime.now(timezone.utc)
        
        if payload.initial_valuation is not None:
            val_pence = pounds_to_pence(payload.initial_valuation)
            up_pence = (Decimal(val_pence) / qty).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP) if qty > 0 else None
        elif payload.initial_unit_price is not None:
            unit_price_pounds = Decimal(str(payload.initial_unit_price))
            up_pence = (unit_price_pounds * Decimal(100)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
            val_pence = int((qty * up_pence).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        else:
            val_pence = 0
            up_pence = None

        val = HoldingValuation(
            holding_id=holding.id,
            effective_date=eff_date,
            quantity=qty,
            unit_price_pence=up_pence,
            valuation_pence=val_pence,
            notes="Initial position valuation"
        )
        db.add(val)
        db.commit()
        db.refresh(holding)

    return _to_holding_response(db, holding)

@router.get("/holdings/{holding_id}", response_model=HoldingResponse)
def get_holding(holding_id: int, db: Session = Depends(get_db)):
    """Retrieves a single holding by ID."""
    holding = db.query(Holding).filter(Holding.id == holding_id).first()
    if not holding:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Holding not found.")
    return _to_holding_response(db, holding)

@router.put("/holdings/{holding_id}", response_model=HoldingResponse)
def update_holding(holding_id: int, payload: HoldingUpdate, db: Session = Depends(get_db)):
    """Updates holding metadata (name, ticker, asset class, account assignment, active status, notes)."""
    holding = db.query(Holding).filter(Holding.id == holding_id).first()
    if not holding:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Holding not found.")

    if payload.name is not None:
        clean_name = payload.name.strip()
        if not clean_name:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Holding name cannot be empty.")
        holding.name = clean_name
    if payload.ticker is not None:
        clean_ticker = payload.ticker.strip().upper() if payload.ticker else None
        holding.ticker = clean_ticker if clean_ticker else None
    if payload.asset_class is not None:
        holding.asset_class = payload.asset_class.strip().lower()
    if payload.account_id is not None and payload.account_id != holding.account_id:
        target_acc = db.query(Account).filter(Account.id == payload.account_id).first()
        if not target_acc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Target account not found.")
        if target_acc.account_type != AccountType.INVESTMENT:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Target account must be an investment account.")
        holding.account_id = target_acc.id
        holding.currency = target_acc.currency
    if payload.is_active is not None:
        holding.is_active = payload.is_active
    if payload.notes is not None:
        holding.notes = payload.notes

    db.commit()
    db.refresh(holding)
    return _to_holding_response(db, holding)

@router.delete("/holdings/{holding_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_holding(holding_id: int, db: Session = Depends(get_db)):
    """Permanently deletes a holding and its historical valuations."""
    holding = db.query(Holding).filter(Holding.id == holding_id).first()
    if not holding:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Holding not found.")
    db.delete(holding)
    db.commit()

@router.get("/holdings/{holding_id}/valuations", response_model=List[HoldingValuationResponse])
def list_holding_valuations(holding_id: int, db: Session = Depends(get_db)):
    """Lists historical dated valuations for a holding ordered by effective date desc."""
    holding = db.query(Holding).filter(Holding.id == holding_id).first()
    if not holding:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Holding not found.")
    
    currency = holding.currency or (holding.account.currency if holding.account else "GBP")
    valuations = db.query(HoldingValuation).filter(
        HoldingValuation.holding_id == holding_id
    ).order_by(desc(HoldingValuation.effective_date), desc(HoldingValuation.id)).all()

    return [_to_valuation_response(v, currency) for v in valuations]

@router.post("/holdings/{holding_id}/valuations", response_model=HoldingValuationResponse, status_code=status.HTTP_201_CREATED)
def record_holding_valuation(holding_id: int, payload: HoldingValuationCreate, db: Session = Depends(get_db)):
    """
    Records a dated valuation checkpoint for a holding.
    Computes total valuation in integer pence, supporting fractional units and zero valuations.
    """
    holding = db.query(Holding).filter(Holding.id == holding_id).first()
    if not holding:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Holding not found.")

    qty = Decimal(str(payload.quantity))
    eff_date = payload.effective_date or datetime.now(timezone.utc)

    if payload.valuation is not None:
        val_pence = pounds_to_pence(payload.valuation)
        up_pence = (Decimal(val_pence) / qty).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP) if qty > 0 else None
    elif payload.unit_price is not None:
        unit_price_pounds = Decimal(str(payload.unit_price))
        up_pence = (unit_price_pounds * Decimal(100)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
        val_pence = int((qty * up_pence).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    else:
        # Default zero value if quantity is 0 or neither price nor valuation specified
        val_pence = 0
        up_pence = None

    val = HoldingValuation(
        holding_id=holding.id,
        effective_date=eff_date,
        quantity=qty,
        unit_price_pence=up_pence,
        valuation_pence=val_pence,
        notes=payload.notes
    )
    db.add(val)
    db.commit()
    db.refresh(val)

    currency = holding.currency or (holding.account.currency if holding.account else "GBP")
    return _to_valuation_response(val, currency)

@router.put("/valuations/{valuation_id}", response_model=HoldingValuationResponse)
def update_holding_valuation(valuation_id: int, payload: HoldingValuationUpdate, db: Session = Depends(get_db)):
    """Updates / corrects an existing valuation entry."""
    val = db.query(HoldingValuation).filter(HoldingValuation.id == valuation_id).first()
    if not val:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Valuation not found.")

    holding = val.holding
    currency = holding.currency if holding else "GBP"

    if payload.effective_date is not None:
        val.effective_date = payload.effective_date
    if payload.quantity is not None:
        val.quantity = Decimal(str(payload.quantity))
    if payload.notes is not None:
        val.notes = payload.notes

    # Re-evaluate pricing if quantity, price, or valuation updated
    qty_dec = Decimal(str(val.quantity))
    if payload.valuation is not None:
        val.valuation_pence = pounds_to_pence(payload.valuation)
        val.unit_price_pence = (Decimal(val.valuation_pence) / qty_dec).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP) if qty_dec > 0 else None
    elif payload.unit_price is not None:
        unit_price_pounds = Decimal(str(payload.unit_price))
        val.unit_price_pence = (unit_price_pounds * Decimal(100)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
        val.valuation_pence = int((qty_dec * val.unit_price_pence).quantize(Decimal("1"), rounding=ROUND_HALF_UP))

    db.commit()
    db.refresh(val)
    return _to_valuation_response(val, currency)

@router.delete("/valuations/{valuation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_holding_valuation(valuation_id: int, db: Session = Depends(get_db)):
    """Deletes an erroneous valuation record, restoring previous valuation."""
    val = db.query(HoldingValuation).filter(HoldingValuation.id == valuation_id).first()
    if not val:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Valuation not found.")
    db.delete(val)
    db.commit()

@router.put("/accounts/{account_id}/valuation-mode", response_model=AccountResponse)
def update_account_valuation_mode(
    account_id: int, 
    payload: AccountValuationModeUpdate, 
    db: Session = Depends(get_db)
):
    """
    Explicitly changes valuation mode between 'snapshot' and 'holdings'.
    Ensures safe transition without silent balance changes.
    """
    account = db.query(Account).filter(Account.id == account_id).first()
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found.")
    if account.account_type != AccountType.INVESTMENT:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only investment accounts support valuation mode.")

    account.valuation_mode = payload.valuation_mode
    db.commit()
    db.refresh(account)
    return _to_account_response(db, account)

@router.post("/accounts/{account_id}/checkpoints", response_model=CheckpointSyncResponse)
def create_checkpoint_snapshot(
    account_id: int, 
    payload: Optional[CheckpointSyncRequest] = None, 
    db: Session = Depends(get_db)
):
    """
    Creates or synchronizes an account-level AssetSnapshot derived from active holdings.
    Sum matches the latest valuation for each active holding as of the specified date.
    """
    eff_date = payload.effective_date if (payload and payload.effective_date) else datetime.now(timezone.utc)
    notes = payload.notes if (payload and payload.notes) else CHECKPOINT_TAG

    try:
        snap = sync_account_checkpoint_snapshot(db, account_id, effective_date=eff_date, notes=notes)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    account = snap.account or db.query(Account).filter(Account.id == account_id).first()
    sym = "£" if (account and account.currency == "GBP") else (f"{account.currency} " if account else "£")

    return CheckpointSyncResponse(
        snapshot_id=snap.id,
        account_id=snap.account_id,
        effective_date=snap.effective_date,
        valuation_pence=snap.valuation_pence,
        valuation_pounds=pence_to_pounds(snap.valuation_pence),
        formatted_valuation=format_pence(snap.valuation_pence, currency_symbol=sym),
        notes=snap.notes
    )

