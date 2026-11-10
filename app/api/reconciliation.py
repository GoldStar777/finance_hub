from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import (
    ReconciliationSummaryResponse,
    ReconciliationSnapshotCreate,
    ReconciliationResultResponse,
    AccountSnapshotItem,
)
from app.core.reconciliation import (
    get_reconciliation_summary,
    create_reconciliation_snapshot,
    list_reconciliation_snapshots,
    delete_reconciliation_snapshot,
)
from app.core.currency import pounds_to_pence

router = APIRouter(prefix="/accounts/{account_id}/reconciliation")

@router.get("", response_model=ReconciliationSummaryResponse)
def get_account_reconciliation(account_id: int, db: Session = Depends(get_db)):
    """
    Returns the reconciliation status for an account:
    - Current calculated balance
    - Last reconciliation timestamp and snapshot details
    - Total snapshot count
    """
    try:
        summary = get_reconciliation_summary(db=db, account_id=account_id)
        return summary
    except ValueError as e:
        err_status = getattr(e, "status_code", None)
        if not err_status:
            err_status = status.HTTP_400_BAD_REQUEST if "Investment" in str(e) else status.HTTP_404_NOT_FOUND
        raise HTTPException(
            status_code=err_status,
            detail=str(e)
        )

@router.get("/snapshots", response_model=List[AccountSnapshotItem])
def list_snapshots(
    account_id: int,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db)
):
    """Lists historical reconciliation verification snapshots for an account."""
    try:
        return list_reconciliation_snapshots(db=db, account_id=account_id, limit=limit, offset=offset)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

@router.post("/snapshots", response_model=ReconciliationResultResponse, status_code=status.HTTP_201_CREATED)
def record_snapshot(
    account_id: int,
    payload: ReconciliationSnapshotCreate,
    db: Session = Depends(get_db)
):
    """
    Atomically saves an observational reconciliation snapshot and sets a ground-truth balance anchor
    as of the resolved timestamp (Now or past date).
    Optionally records a missing transaction with effective timestamp <= anchor date for cash-flow reporting
    without altering the confirmed balance.
    """
    try:
        actual_pence = pounds_to_pence(payload.actual_balance)
        result = create_reconciliation_snapshot(
            db=db,
            account_id=account_id,
            actual_balance_pence=actual_pence,
            as_of_mode=payload.as_of_mode,
            as_of_date=payload.as_of_date,
            snapshot_date=payload.snapshot_date,
            notes=payload.notes,
            missing_transaction=payload.missing_transaction,
            create_adjustment=payload.create_adjustment,
            adjustment_notes=payload.adjustment_notes,
        )
        return result
    except ValueError as e:
        err_status = getattr(e, "status_code", None)
        if not err_status:
            err_status = status.HTTP_400_BAD_REQUEST if "Investment" in str(e) else status.HTTP_404_NOT_FOUND
        raise HTTPException(
            status_code=err_status,
            detail=str(e)
        )

@router.delete("/snapshots/{snapshot_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_snapshot(
    account_id: int,
    snapshot_id: int,
    db: Session = Depends(get_db)
):
    """
    Deletes an erroneous reconciliation snapshot.
    Does NOT alter or delete any transactions.
    """
    try:
        delete_reconciliation_snapshot(db=db, account_id=account_id, snapshot_id=snapshot_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

