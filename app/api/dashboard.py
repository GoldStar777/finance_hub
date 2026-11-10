from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.ledger import LedgerEngine
from app.schemas import DashboardSummaryResponse

router = APIRouter(prefix="/dashboard")

@router.get("/summary", response_model=DashboardSummaryResponse)
def get_dashboard_summary(db: Session = Depends(get_db)):
    """Computes executive net worth, liquid reserves, debt, and investments."""
    return LedgerEngine.get_dashboard_summary(db)

