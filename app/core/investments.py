from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.models import Account, AccountType, AssetSnapshot, Holding, HoldingValuation
from app.core.currency import format_pence, pence_to_pounds

CHECKPOINT_TAG = "[Holdings Rollup Checkpoint]"

def get_holding_latest_valuation(
    db: Session, 
    holding_id: int, 
    as_of_date: Optional[datetime] = None
) -> Optional[HoldingValuation]:
    """
    Returns the latest valuation for a holding, optionally constrained by an as-of date.
    Deterministic ordering: effective_date DESC, id DESC.
    """
    query = db.query(HoldingValuation).filter(HoldingValuation.holding_id == holding_id)
    if as_of_date is not None:
        query = query.filter(HoldingValuation.effective_date <= as_of_date)
    return query.order_by(desc(HoldingValuation.effective_date), desc(HoldingValuation.id)).first()

def get_account_holdings_breakdown(
    db: Session, 
    account_id: int, 
    as_of_date: Optional[datetime] = None
) -> Dict[str, Any]:
    """
    Calculates total valuation across all active holdings for an account.
    Distinguishes explicit 0-value holdings from unvalued holdings.
    """
    active_holdings = db.query(Holding).filter(
        Holding.account_id == account_id,
        Holding.is_active == True
    ).order_by(Holding.name.asc()).all()

    total_pence = 0
    valued_count = 0
    unvalued_count = 0
    holdings_details = []

    for h in active_holdings:
        latest = get_holding_latest_valuation(db, h.id, as_of_date=as_of_date)
        if latest is not None:
            valued_count += 1
            total_pence += latest.valuation_pence
            holdings_details.append({
                "holding": h,
                "latest_valuation": latest,
                "is_valued": True,
                "valuation_pence": latest.valuation_pence
            })
        else:
            unvalued_count += 1
            holdings_details.append({
                "holding": h,
                "latest_valuation": None,
                "is_valued": False,
                "valuation_pence": 0
            })

    return {
        "total_pence": total_pence,
        "total_pounds": pence_to_pounds(total_pence),
        "holdings_count": len(active_holdings),
        "valued_count": valued_count,
        "unvalued_count": unvalued_count,
        "has_unvalued_holdings": unvalued_count > 0,
        "details": holdings_details
    }

def sync_account_checkpoint_snapshot(
    db: Session,
    account_id: int,
    effective_date: datetime,
    notes: Optional[str] = None
) -> AssetSnapshot:
    """
    Enforces the checkpoint-sync rule:
    Creates or updates an AssetSnapshot for the given date whose valuation_pence
    equals the sum of the latest valuations for each active holding on or before that date.
    Tagged with CHECKPOINT_TAG to avoid ambiguity with manual account snapshots.
    """
    account = db.query(Account).filter(Account.id == account_id).first()
    if not account:
        raise ValueError(f"Account with ID {account_id} not found.")

    breakdown = get_account_holdings_breakdown(db, account_id, as_of_date=effective_date)
    checkpoint_pence = breakdown["total_pence"]

    # Look for existing snapshot for this account on the same effective date
    existing_snap = db.query(AssetSnapshot).filter(
        AssetSnapshot.account_id == account_id,
        AssetSnapshot.effective_date == effective_date
    ).first()

    tag_note = notes or CHECKPOINT_TAG
    if existing_snap:
        existing_snap.valuation_pence = checkpoint_pence
        if tag_note not in (existing_snap.notes or ""):
            existing_snap.notes = tag_note
        db.commit()
        db.refresh(existing_snap)
        return existing_snap
    else:
        new_snap = AssetSnapshot(
            account_id=account_id,
            valuation_pence=checkpoint_pence,
            effective_date=effective_date,
            notes=tag_note
        )
        db.add(new_snap)
        db.commit()
        db.refresh(new_snap)
        return new_snap

def get_portfolio_summary(db: Session) -> Dict[str, Any]:
    """
    Computes portfolio executive summary:
    Total invested value, account breakdown, and asset class allocation.
    """
    from app.ledger import LedgerEngine

    accounts = db.query(Account).filter(
        Account.account_type == AccountType.INVESTMENT,
        Account.is_active == True
    ).order_by(Account.name.asc()).all()

    total_invested_pence = 0
    accounts_data = []
    asset_class_map: Dict[str, int] = {}

    for acc in accounts:
        bal_pence = LedgerEngine.get_account_balance(db, acc.id)
        total_invested_pence += bal_pence

        breakdown = get_account_holdings_breakdown(db, acc.id)
        
        # Accumulate asset class allocation strictly from active holdings
        for item in breakdown["details"]:
            if item["is_valued"]:
                ac = item["holding"].asset_class or "other"
                asset_class_map[ac] = asset_class_map.get(ac, 0) + item["valuation_pence"]

        accounts_data.append({
            "account_id": acc.id,
            "account_name": acc.name,
            "currency": acc.currency,
            "color": acc.color,
            "valuation_mode": acc.valuation_mode,
            "balance_pence": bal_pence,
            "balance_pounds": pence_to_pounds(bal_pence),
            "formatted_balance": format_pence(bal_pence, currency_symbol=acc.currency + " " if acc.currency != "GBP" else "£"),
            "holdings_count": breakdown["holdings_count"],
            "valued_count": breakdown["valued_count"],
            "unvalued_count": breakdown["unvalued_count"],
            "has_unvalued_holdings": breakdown["has_unvalued_holdings"]
        })

    allocation_list = [
        {
            "asset_class": k,
            "total_pence": v,
            "total_pounds": pence_to_pounds(v),
            "percentage": round((v / total_invested_pence * 100), 2) if total_invested_pence > 0 else 0.0
        }
        for k, v in sorted(asset_class_map.items(), key=lambda x: x[1], reverse=True)
    ]

    return {
        "total_invested_pence": total_invested_pence,
        "total_invested_pounds": pence_to_pounds(total_invested_pence),
        "formatted_total_invested": format_pence(total_invested_pence),
        "accounts": accounts_data,
        "asset_allocation": allocation_list
    }


def convert_snapshot_histories_to_holdings(db: Session) -> Dict[str, Any]:
    """
    One-time idempotent migration step:
    For any investment account with AssetSnapshot history but no holdings,
    converts that history into a single synthetic holding ('Portfolio Valuation')
    with quantity 1.0 and matching dated valuations.
    For accounts that already have holdings, leaves them untouched.
    """
    investment_accounts = db.query(Account).filter(Account.account_type == AccountType.INVESTMENT).all()
    
    converted_accounts = 0
    created_holdings = 0
    created_valuations = 0

    for acc in investment_accounts:
        # Check if account already has holdings
        existing_holdings_count = db.query(Holding).filter(Holding.account_id == acc.id).count()
        if existing_holdings_count > 0:
            # Already has holdings: do not create synthetic holding
            continue

        # Check if account has asset snapshots
        snapshots = db.query(AssetSnapshot).filter(
            AssetSnapshot.account_id == acc.id
        ).order_by(AssetSnapshot.effective_date.asc(), AssetSnapshot.id.asc()).all()

        if not snapshots:
            continue

        # Check idempotency: check if synthetic holding already exists
        synthetic = db.query(Holding).filter(
            Holding.account_id == acc.id,
            Holding.name == "Portfolio Valuation"
        ).first()

        if not synthetic:
            synthetic = Holding(
                account_id=acc.id,
                name="Portfolio Valuation",
                ticker=None,
                asset_class="portfolio",
                currency=acc.currency,
                is_active=True,
                notes="Synthetic holding migrated from historical account snapshots"
            )
            db.add(synthetic)
            db.flush()
            created_holdings += 1

        # Check existing valuations on this synthetic holding to avoid duplicates
        existing_val_dates = {
            v.effective_date for v in db.query(HoldingValuation).filter(HoldingValuation.holding_id == synthetic.id).all()
        }

        for snap in snapshots:
            if snap.effective_date not in existing_val_dates:
                val = HoldingValuation(
                    holding_id=synthetic.id,
                    effective_date=snap.effective_date,
                    quantity=Decimal("1.0"),
                    unit_price_pence=Decimal(str(snap.valuation_pence)),
                    valuation_pence=snap.valuation_pence,
                    notes=snap.notes or "Migrated from asset snapshot"
                )
                db.add(val)
                existing_val_dates.add(snap.effective_date)
                created_valuations += 1

        converted_accounts += 1

    db.commit()
    return {
        "converted_accounts": converted_accounts,
        "created_holdings": created_holdings,
        "created_valuations": created_valuations
    }


