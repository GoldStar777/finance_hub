from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.data_quality import get_data_quality_report
from app.core.profiles import ProfileMetadata
from app.core.review_suggestions import (
    add_dismissed_suggestion_id,
    remove_dismissed_suggestion_id,
    restore_all_dismissed_suggestions,
)
from app.database import get_current_profile, get_db
from app.schemas import (
    DataQualityDismissPayload,
    DataQualityReportResponse,
    DataQualityRestorePayload,
)

router = APIRouter(prefix="/review")


@router.get("/findings", response_model=DataQualityReportResponse)
def get_review_findings(
    finding_type: Optional[str] = Query(None, description="Comma-separated finding types to filter"),
    severity: Optional[str] = Query(None, description="Comma-separated severities ('integrity', 'review', 'suggestion')"),
    q: Optional[str] = Query(None, description="Text search across merchant, title, summary, or evidence"),
    account_id: Optional[str] = Query(None, description="Account ID or 'unassigned'"),
    category_id: Optional[str] = Query(None, description="Category ID or 'uncategorized'"),
    start_date: Optional[str] = Query(None, description="Start local date YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="End local date YYYY-MM-DD"),
    include_dismissed: bool = Query(False, description="Whether to include dismissed suggestions"),
    db: Session = Depends(get_db),
    profile: ProfileMetadata = Depends(get_current_profile),
):
    """
    Scans the active profile's ledger, pending staging queue, accounts, categories,
    anchors, and holdings to surface explainable review suggestions and data-integrity checks.
    Strictly read-only and never modifies financial records.
    """
    return get_data_quality_report(
        db=db,
        profile_id=profile.id,
        finding_type=finding_type,
        severity=severity,
        q=q,
        account_id=account_id,
        category_id=category_id,
        start_date=start_date,
        end_date=end_date,
        include_dismissed=include_dismissed,
    )


@router.post("/dismiss")
def dismiss_review_finding(
    payload: DataQualityDismissPayload,
    db: Session = Depends(get_db),
    profile: ProfileMetadata = Depends(get_current_profile),
):
    """
    Hides an advisory review suggestion for the active profile.
    Structural integrity issues cannot be dismissed until resolved.
    """
    clean_id = payload.finding_id.strip()
    if clean_id.startswith("dq_integrity_"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Structural integrity findings cannot be dismissed until the underlying record is fixed."
        )
    add_dismissed_suggestion_id(db, clean_id)
    return {"success": True, "dismissed_id": clean_id}


@router.post("/restore-dismissed")
def restore_dismissed_review_finding(
    payload: DataQualityRestorePayload,
    db: Session = Depends(get_db),
    profile: ProfileMetadata = Depends(get_current_profile),
):
    """
    Restores one dismissed review suggestion or clears all hidden suggestions for the active profile.
    """
    if payload.restore_all or not payload.finding_id:
        restored = restore_all_dismissed_suggestions(db)
        return {"success": True, "restored_count": restored}

    clean_id = payload.finding_id.strip()
    removed = remove_dismissed_suggestion_id(db, clean_id)
    return {"success": True, "restored_count": 1 if removed else 0, "restored_id": clean_id}
