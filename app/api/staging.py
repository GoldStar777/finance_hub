import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form, status, Response
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.database import get_db, get_current_profile
from app.core.profiles import ProfileMetadata
from app.config import STAGING_RECEIPTS_DIR, ARCHIVE_RECEIPTS_DIR, DATA_DIR
from app.models import StagingItem, StagingStatus, Account, ExpenseNature
from app.schemas import (
    StagingItemResponse, StagingItemUpdate, CSVImportResponse,
    StagingBatchApprovePayload, StagingBatchRejectPayload, StagingBatchApproveResponse,
    StagingCountResponse, StatementMappingProfile, StatementMappingProfileCreate,
    UnifiedImportResponse, UnifiedImportCommitPayload, UnifiedImportCommitResponse,
    ReviewSuggestionsResponse, ConfirmDuplicateSuggestionPayload,
    ConfirmTransferSuggestionPayload, DismissSuggestionPayload,
    StagingSplitRequest, StagingSplitResponse
)
from app.core.currency import pence_to_pounds, format_pence, pounds_to_pence
from app.core.staging import (
    ingest_statement_csv, ingest_receipt_image, update_staging_item,
    approve_staging_item, discard_staging_item, batch_approve_staging_items,
    batch_reject_staging_items, list_mapping_profiles, save_mapping_profile,
    delete_mapping_profile, split_staging_item
)
from app.core.unified_importer import (
    ingest_unified_file, list_confirmed_account_associations,
    save_confirmed_account_association, delete_confirmed_account_association,
    cleanup_invalid_account_associations
)
from app.core.review_suggestions import (
    get_review_queue_suggestions, confirm_duplicate_suggestion,
    confirm_transfer_suggestion, unpair_transfer_transaction,
    add_dismissed_suggestion_id
)

router = APIRouter(prefix="/staging")

def _to_staging_response(item: StagingItem, db: Session) -> StagingItemResponse:
    payload = json.loads(item.raw_payload_json or "{}")

    # Account info
    acc_name = None
    acc_color = None
    if item.suggested_account_id:
        acc = db.query(Account).filter(Account.id == item.suggested_account_id).first()
        if acc:
            acc_name = acc.name
            acc_color = acc.color

    # Destination account info (for transfers)
    dest_name = None
    dest_id = payload.get("destination_account_id")
    if dest_id:
        dest_acc = db.query(Account).filter(Account.id == dest_id).first()
        if dest_acc:
            dest_name = dest_acc.name

    # Monetary representation
    amt_pounds = pence_to_pounds(item.extracted_amount_pence) if item.extracted_amount_pence is not None else None
    formatted_amt = format_pence(item.extracted_amount_pence) if item.extracted_amount_pence is not None else None

    # Receipt URL
    receipt_url = None
    if item.temp_file_path:
        fname = Path(item.temp_file_path).name
        receipt_url = f"/api/staging/receipts/{fname}"

    orig_amt = payload.get("original_amount")
    orig_curr = payload.get("original_currency")
    rate = payload.get("exchange_rate")
    req_base = payload.get("requires_base_amount", False) or (item.extracted_amount_pence is None and orig_curr is not None)

    formatted_orig = None
    if orig_amt is not None and orig_curr:
        from app.core.currency import format_origin_amount
        formatted_orig = format_origin_amount(orig_amt, orig_curr)

    anchor_status = None
    anchor_explanation = None
    if item.suggested_account_id and item.extracted_date:
        acc = db.query(Account).filter(Account.id == item.suggested_account_id).first()
        if acc and acc.latest_anchor:
            from app.core.timezone import parse_date_input, get_app_timezone
            from zoneinfo import ZoneInfo
            anchor_dt = acc.latest_anchor.anchor_date
            app_tz = get_app_timezone(db)
            anchor_local_dt = anchor_dt.astimezone(ZoneInfo(app_tz)) if anchor_dt.tzinfo else anchor_dt
            item_d = parse_date_input(item.extracted_date)
            anchor_d = parse_date_input(anchor_local_dt)
            if item_d < anchor_d:
                anchor_status = "prior_to_anchor"
                anchor_explanation = f"Dated before {acc.name}'s balance anchor ({anchor_local_dt.strftime('%d/%m/%Y')}). Will be recorded as already reflected unless toggled."
            elif item_d == anchor_d:
                anchor_status = "same_day_as_anchor"
                anchor_explanation = f"Dated on the same day as {acc.name}'s balance anchor ({anchor_local_dt.strftime('%d/%m/%Y')}). Confirm whether already reflected in the anchor balance."
            else:
                anchor_status = "after_anchor"
                anchor_explanation = f"Dated after {acc.name}'s balance anchor ({anchor_local_dt.strftime('%d/%m/%Y')}). Will adjust the ledger balance forward."

    match_reason = payload.get("account_match_reason")
    cat_id = payload.get("category_id")
    if not cat_id and item.suggested_category_name:
        from app.models import Category
        cat = db.query(Category).filter(Category.name.ilike(item.suggested_category_name.strip())).first()
        if cat:
            cat_id = cat.id

    return StagingItemResponse(
        id=item.id,
        created_at=item.created_at or datetime.now(timezone.utc),
        status=item.status.value,
        extracted_amount_pence=item.extracted_amount_pence,
        amount_pounds=amt_pounds,
        formatted_amount=formatted_amt,
        extracted_date=item.extracted_date,
        extracted_merchant=item.extracted_merchant,
        suggested_category_name=item.suggested_category_name,
        suggested_category_id=cat_id,
        suggested_account_id=item.suggested_account_id,
        suggested_account_name=acc_name,
        suggested_account_color=acc_color,
        suggested_account_match_reason=match_reason,
        suggested_expense_nature=item.suggested_expense_nature or ExpenseNature.UNCLASSIFIED,
        source_type=item.source_type,
        temp_file_path=item.temp_file_path,
        receipt_url=receipt_url,
        transaction_type=payload.get("transaction_type", "expense"),
        destination_account_id=dest_id,
        destination_account_name=dest_name,
        notes=payload.get("notes"),
        currency=payload.get("currency", "GBP"),
        original_amount=orig_amt,
        original_currency=orig_curr,
        exchange_rate=rate,
        formatted_original_amount=formatted_orig,
        requires_base_amount=req_base,
        currency_conflict=payload.get("currency_conflict", False),
        currency_conflict_message=payload.get("currency_conflict_message"),
        is_potential_duplicate=payload.get("is_potential_duplicate", False),
        duplicate_matches=payload.get("duplicate_matches", []),
        source_filename=payload.get("source_filename"),
        line_number=payload.get("line_number"),
        ocr_confidence=payload.get("ocr_confidence"),
        ocr_error=payload.get("ocr_error"),
        date_uncertain=payload.get("date_uncertain", False),
        merchant_uncertain=payload.get("merchant_uncertain", False),
        category_match_reason=payload.get("category_match_reason"),
        anchor_status=anchor_status,
        anchor_explanation=anchor_explanation,
        anchor_mode=getattr(item, "anchor_mode", "auto") or "auto",
        effective_timestamp=item.effective_timestamp,
        is_split=payload.get("is_split", False),
        split_parent_id=payload.get("split_parent_id"),
        split_index=payload.get("split_index"),
        split_total=payload.get("split_total")
    )

@router.get("", response_model=List[StagingItemResponse])
def list_staging_items(
    status: Optional[str] = Query("pending", description="Filter by status (pending, approved, rejected, all)"),
    source_type: Optional[str] = Query(None, description="Filter by source (statement_csv, receipt_image)"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db)
):
    """Lists staging review queue items."""
    query = db.query(StagingItem)
    if status and status.lower() != "all":
        try:
            st = StagingStatus(status.lower())
            query = query.filter(StagingItem.status == st)
        except ValueError:
            pass

    if source_type:
        query = query.filter(StagingItem.source_type == source_type)

    items = query.order_by(StagingItem.created_at.desc(), StagingItem.id.desc()).offset(offset).limit(limit).all()
    return [_to_staging_response(i, db) for i in items]

@router.get("/count", response_model=StagingCountResponse)
def get_pending_staging_count(db: Session = Depends(get_db)):
    """Returns the total number of pending review items for the badge indicator."""
    count = db.query(StagingItem).filter(StagingItem.status == StagingStatus.PENDING).count()
    return StagingCountResponse(pending_count=count)

@router.post("/import-csv", response_model=CSVImportResponse, status_code=status.HTTP_201_CREATED)
async def import_statement_csv_endpoint(
    file: UploadFile = File(...),
    account_id: Optional[int] = Form(None),
    mapping_config: str = Form(..., description="JSON-serialized StatementMappingConfig"),
    profile_name_to_save: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    """
    Imports a CSV or TSV statement using configurable column/date mappings.
    Parses transactions into the staging review queue with malformed row reporting.
    """
    content = await file.read()
    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded statement file is empty."
        )

    try:
        mapping = json.loads(mapping_config)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid mapping configuration JSON: {str(e)}"
        )

    try:
        result = ingest_statement_csv(
            db=db,
            file_content=content,
            filename=file.filename or "statement.csv",
            mapping=mapping,
            target_account_id=account_id
        )

        # Optionally save mapping profile if requested
        if profile_name_to_save and profile_name_to_save.strip():
            save_mapping_profile(db, {
                "name": profile_name_to_save.strip(),
                "config": mapping,
                "default_account_id": account_id
            })

        return CSVImportResponse(**result)

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@router.post("/upload-receipt", response_model=StagingItemResponse, status_code=status.HTTP_201_CREATED)
async def upload_receipt_endpoint(
    file: UploadFile = File(...),
    account_id: Optional[int] = Form(None),
    db: Session = Depends(get_db),
    profile: ProfileMetadata = Depends(get_current_profile)
):
    """
    Uploads a receipt image, applies pluggable OCR extraction, and queues for review.
    Uncertain or unreadable fields remain blank for human manual entry.
    """
    content = await file.read()
    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded receipt file is empty."
        )

    try:
        item = ingest_receipt_image(
            db=db,
            file_content=content,
            original_filename=file.filename or "receipt.jpg",
            target_account_id=account_id,
            staging_dir=profile.staging_receipts_dir
        )
        return _to_staging_response(item, db)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process receipt: {str(e)}"
        )

@router.post("/import-file", response_model=UnifiedImportResponse, status_code=status.HTTP_201_CREATED)
async def import_file_endpoint(
    file: UploadFile = File(...),
    account_id: Optional[int] = Form(None),
    db: Session = Depends(get_db),
    profile: ProfileMetadata = Depends(get_current_profile)
):
    """
    Unified, provider-agnostic file import endpoint:
    Accepts receipts, statements (CSV/TSV/Excel), screenshots, PDFs, and general financial files.
    Classifies by file signature/MIME, applies local extractors, and stages pending items for review.
    """
    content = await file.read()
    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty."
        )

    try:
        result = ingest_unified_file(
            db=db,
            file_content=content,
            original_filename=file.filename or "uploaded_file",
            target_account_id=account_id,
            staging_dir=profile.staging_receipts_dir
        )
        return UnifiedImportResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Import failed: {str(e)}")

@router.post("/import-commit", response_model=UnifiedImportCommitResponse)
def import_commit_endpoint(
    payload: UnifiedImportCommitPayload,
    db: Session = Depends(get_db),
    profile: ProfileMetadata = Depends(get_current_profile)
):
    """
    Commits decisions made in the unified import review pop-up:
    Applies any corrections made by the user, and either adds items directly to the ledger,
    queues them for later review, or discards them.
    """
    if payload.action in ("approve_all", "approve_selected", "queue_all"):
        for item_update in payload.items:
            updates = {}
            if item_update.merchant is not None:
                updates["merchant"] = item_update.merchant
            if item_update.amount is not None:
                amt_p = pounds_to_pence(item_update.amount)
                if amt_p <= 0:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Amount for item {item_update.id} must be positive.")
                updates["amount_pence"] = amt_p
            if item_update.original_amount is not None:
                updates["original_amount"] = item_update.original_amount
            if item_update.original_currency is not None:
                updates["original_currency"] = item_update.original_currency
            if item_update.exchange_rate is not None:
                updates["exchange_rate"] = item_update.exchange_rate
            if item_update.transaction_date is not None:
                updates["transaction_date"] = item_update.transaction_date
            if item_update.account_id is not None:
                updates["account_id"] = item_update.account_id
            if item_update.destination_account_id is not None:
                updates["destination_account_id"] = item_update.destination_account_id
            if item_update.transaction_type is not None:
                updates["transaction_type"] = item_update.transaction_type.value
            if item_update.category_id is not None:
                updates["category_id"] = item_update.category_id
            if item_update.category_name is not None:
                updates["category_name"] = item_update.category_name
            if item_update.expense_nature is not None:
                updates["expense_nature"] = item_update.expense_nature
            if item_update.notes is not None:
                updates["notes"] = item_update.notes
            if item_update.anchor_mode is not None:
                updates["anchor_mode"] = item_update.anchor_mode
            if item_update.effective_timestamp is not None:
                updates["effective_timestamp"] = item_update.effective_timestamp

            if updates:
                try:
                    update_staging_item(db, item_update.id, updates)
                except ValueError as e:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    approved_count = 0
    queued_count = 0
    discarded_count = 0
    already_committed_count = 0
    commit_message = None
    tx_ids = []

    if payload.action in ("approve_all", "approve_selected"):
        item_ids_to_approve = [item.id for item in payload.items]

        # Pre-validate all items before approving to avoid partial commits
        validation_errors = []
        staged_items = []
        for item_id in item_ids_to_approve:
            stg = db.query(StagingItem).filter(StagingItem.id == item_id).first()
            if not stg:
                validation_errors.append({"id": item_id, "error": f"Staging item {item_id} not found."})
                continue
            if stg.status != StagingStatus.PENDING:
                validation_errors.append({"id": item_id, "error": f"Staging item {item_id} is already {stg.status.value}."})
                continue
            if not stg.extracted_date:
                validation_errors.append({"id": item_id, "error": "Transaction date is required."})
                continue
            if not stg.extracted_amount_pence or stg.extracted_amount_pence <= 0:
                validation_errors.append({"id": item_id, "error": "A positive transaction amount is required."})
                continue

            pl = json.loads(stg.raw_payload_json or "{}")
            raw_t = pl.get("transaction_type", "expense").lower()
            if raw_t == "transfer":
                if not stg.suggested_account_id:
                    validation_errors.append({"id": item_id, "error": "Source account is required for transfers."})
                dest_acc_id = pl.get("destination_account_id")
                if not dest_acc_id:
                    validation_errors.append({"id": item_id, "error": "Destination account is required for transfers."})
                elif dest_acc_id == stg.suggested_account_id:
                    validation_errors.append({"id": item_id, "error": "Source and destination accounts must be distinct."})

            staged_items.append(stg)

        if validation_errors:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "message": "One or more items could not be approved due to validation errors. No items were committed.",
                    "row_errors": validation_errors
                }
            )

        # All items are valid: approve in a single atomic transaction
        try:
            for stg in staged_items:
                tx = approve_staging_item(
                    db,
                    stg.id,
                    staging_dir=profile.staging_receipts_dir,
                    archive_dir=profile.receipts_dir
                )
                tx_ids.append(tx.id)
                approved_count += 1
        except Exception as e:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Atomic batch approval failed: {str(e)}"
            )

    elif payload.action == "queue_all":
        queued_count = len(payload.items)
        commit_message = f"Sent {queued_count} candidate(s) to Review Queue."

    elif payload.action == "discard_all":
        candidate_ids = []
        if payload.items:
            candidate_ids = [item.id for item in payload.items]
        elif payload.batch_id:
            batch_items = db.query(StagingItem).filter(
                StagingItem.raw_payload_json.like(f'%"batch_id": "{payload.batch_id}"%')
            ).all()
            candidate_ids = [bi.id for bi in batch_items]

        already_committed_ids = []
        for c_id in candidate_ids:
            stg = db.query(StagingItem).filter(StagingItem.id == c_id).first()
            if not stg:
                continue
            if stg.status == StagingStatus.APPROVED:
                already_committed_ids.append(stg.id)
            elif stg.status == StagingStatus.PENDING:
                if discard_staging_item(
                    db,
                    stg.id,
                    staging_dir=profile.staging_receipts_dir,
                    archive_dir=profile.receipts_dir
                ):
                    discarded_count += 1
            elif stg.status == StagingStatus.REJECTED:
                discarded_count += 1

        already_committed_count = len(already_committed_ids)
        if already_committed_count > 0:
            commit_message = (
                f"Discarded {discarded_count} unresolved candidates. "
                f"{already_committed_count} candidate(s) were previously committed to the ledger and remain intact."
            )
        else:
            commit_message = f"Discarded all {discarded_count} candidate(s) from import."

    return UnifiedImportCommitResponse(
        action=payload.action,
        batch_id=payload.batch_id,
        approved_count=approved_count,
        queued_count=queued_count,
        discarded_count=discarded_count,
        already_committed_count=already_committed_count,
        transaction_ids=tx_ids,
        errors=[],
        message=commit_message
    )

@router.get("/receipts/{filename}")
def serve_staging_receipt(filename: str, profile: ProfileMetadata = Depends(get_current_profile)):
    """Serves a staged or archived receipt image file for preview."""
    safe_name = Path(filename).name
    file_path = profile.staging_receipts_dir / safe_name
    if not file_path.exists() or not file_path.is_file():
        file_path = profile.receipts_dir / safe_name
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Receipt file not found.")
    return FileResponse(file_path)

# --- Mapping Profile Endpoints (Registered before /{item_id} to avoid int parsing collisions) ---

@router.get("/profiles", response_model=List[StatementMappingProfile])
def list_profiles_endpoint(db: Session = Depends(get_db)):
    """Lists saved statement mapping profiles."""
    profiles = list_mapping_profiles(db)
    return [StatementMappingProfile(**p) for p in profiles]

@router.post("/profiles", response_model=StatementMappingProfile, status_code=status.HTTP_201_CREATED)
def create_profile_endpoint(
    payload: StatementMappingProfileCreate,
    db: Session = Depends(get_db)
):
    """Saves a new statement mapping profile."""
    profile_data = {
        "name": payload.name,
        "config": payload.config.model_dump(),
        "default_account_id": payload.default_account_id
    }
    saved = save_mapping_profile(db, profile_data)
    return StatementMappingProfile(**saved)

@router.delete("/profiles/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_profile_endpoint(profile_id: str, db: Session = Depends(get_db)):
    """Deletes a saved statement mapping profile."""
    success = delete_mapping_profile(db, profile_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)

# --- Confirmed Account Association Management Endpoints ---

@router.get("/account-associations")
def list_account_associations_endpoint(db: Session = Depends(get_db)):
    """Lists all user-confirmed card-label to account associations (100% local, inspectable)."""
    return list_confirmed_account_associations(db)

@router.post("/account-associations", status_code=status.HTTP_200_OK)
def save_account_association_endpoint(
    card_label: str = Query(..., description="Card or document header label"),
    account_id: int = Query(..., description="Target account ID"),
    last_4: Optional[str] = Query(None, description="Optional card last 4 digits"),
    db: Session = Depends(get_db)
):
    """Saves or updates a user-confirmed card-label to account association."""
    save_confirmed_account_association(db, card_label, account_id, last_4=last_4)
    return {"success": True, "card_label": card_label, "account_id": account_id, "last_4": last_4}

@router.delete("/account-associations/{label}", status_code=status.HTTP_204_NO_CONTENT)
def delete_account_association_endpoint(label: str, db: Session = Depends(get_db)):
    """Deletes a user-confirmed card-label to account association."""
    success = delete_confirmed_account_association(db, label)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Association not found.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)

@router.post("/account-associations/cleanup", status_code=status.HTTP_200_OK)
def cleanup_account_associations_endpoint(db: Session = Depends(get_db)):
    """
    Explicitly prunes invalid terminal noise associations (e.g. 'mid') from system_settings.
    Auditable: returns the list of pruned keys.
    """
    pruned = cleanup_invalid_account_associations(db)
    return {"success": True, "pruned_keys": pruned}

# --- Advisory Review Suggestions Endpoints ---

@router.get("/suggestions", response_model=ReviewSuggestionsResponse)
def get_review_suggestions_endpoint(
    db: Session = Depends(get_db),
    profile: ProfileMetadata = Depends(get_current_profile)
):
    """
    Returns explainable advisory duplicate and transfer suggestions for the Review Queue.
    Strictly local and profile-scoped.
    """
    return get_review_queue_suggestions(db)

@router.post("/suggestions/confirm-duplicate")
def confirm_duplicate_suggestion_endpoint(
    payload: ConfirmDuplicateSuggestionPayload,
    db: Session = Depends(get_db),
    profile: ProfileMetadata = Depends(get_current_profile)
):
    """
    Confirms duplicate exclusion: safely discards the staging candidate,
    preserves sibling source files, and records dismissal.
    """
    success = confirm_duplicate_suggestion(
        db=db,
        duplicate_staging_id=payload.duplicate_staging_id,
        suggestion_id=payload.suggestion_id,
        staging_dir=profile.staging_receipts_dir,
        archive_dir=profile.receipts_dir
    )
    if not success:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Failed to exclude duplicate staging item.")
    return {"success": True, "discarded_id": payload.duplicate_staging_id}

@router.post("/suggestions/confirm-transfer")
def confirm_transfer_suggestion_endpoint(
    payload: ConfirmTransferSuggestionPayload,
    db: Session = Depends(get_db),
    profile: ProfileMetadata = Depends(get_current_profile)
):
    """
    Confirms transfer pairing: creates or converts to a dual-account transfer,
    marks staging approved, keeps operating cash flow neutral (£0 impact).
    """
    try:
        tx = confirm_transfer_suggestion(
            db=db,
            source_id=payload.source_id,
            source_kind=payload.source_kind,
            destination_id=payload.destination_id,
            destination_kind=payload.destination_kind,
            suggestion_id=payload.suggestion_id,
            staging_dir=profile.staging_receipts_dir,
            archive_dir=profile.receipts_dir
        )
        return {"success": True, "transaction_id": tx.id}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

@router.post("/suggestions/unpair-transfer/{transaction_id}")
def unpair_transfer_suggestion_endpoint(
    transaction_id: int,
    db: Session = Depends(get_db),
    profile: ProfileMetadata = Depends(get_current_profile)
):
    """
    Atomically reverses a paired transfer transaction back into its original constituent records
    using its stored transfer provenance snapshot.
    """
    try:
        result = unpair_transfer_transaction(db=db, transaction_id=transaction_id)
        return {"success": True, **result}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

@router.post("/suggestions/dismiss")
def dismiss_suggestion_endpoint(
    payload: DismissSuggestionPayload,
    db: Session = Depends(get_db),
    profile: ProfileMetadata = Depends(get_current_profile)
):
    """
    Dismisses an advisory suggestion for this profile.
    """
    add_dismissed_suggestion_id(db, payload.suggestion_id)
    return {"success": True, "dismissed_id": payload.suggestion_id}

# --- Item Specific Endpoints ---

@router.get("/{item_id}", response_model=StagingItemResponse)
def get_staging_item(item_id: int, db: Session = Depends(get_db)):
    """Retrieves a single staging review item."""
    item = db.query(StagingItem).filter(StagingItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Staging item not found.")
    return _to_staging_response(item, db)

@router.put("/{item_id}", response_model=StagingItemResponse)
def update_staging_item_endpoint(
    item_id: int,
    payload: StagingItemUpdate,
    db: Session = Depends(get_db)
):
    """Updates fields of a pending staging review item."""
    updates = {}
    if payload.merchant is not None:
        updates["merchant"] = payload.merchant
    if payload.amount is not None:
        amt_p = pounds_to_pence(payload.amount)
        if amt_p <= 0:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Amount must be positive.")
        updates["amount_pence"] = amt_p
    if payload.transaction_date is not None:
        updates["transaction_date"] = payload.transaction_date
    if payload.account_id is not None:
        updates["account_id"] = payload.account_id
    if payload.destination_account_id is not None:
        updates["destination_account_id"] = payload.destination_account_id
    if payload.transaction_type is not None:
        updates["transaction_type"] = payload.transaction_type.value
    if "category_id" in payload.model_fields_set:
        updates["category_id"] = payload.category_id
    if payload.category_name is not None:
        updates["category_name"] = payload.category_name
    if payload.expense_nature is not None:
        updates["expense_nature"] = payload.expense_nature
    if payload.notes is not None:
        updates["notes"] = payload.notes
    if payload.anchor_mode is not None:
        updates["anchor_mode"] = payload.anchor_mode
    if payload.effective_timestamp is not None:
        updates["effective_timestamp"] = payload.effective_timestamp

    try:
        updated = update_staging_item(db, item_id, updates)
        return _to_staging_response(updated, db)
    except ValueError as e:
        raise HTTPException(
            status_code=getattr(e, "status_code", status.HTTP_400_BAD_REQUEST),
            detail=str(e),
        )

@router.post("/{item_id}/approve", status_code=status.HTTP_200_OK)
def approve_staging_item_endpoint(
    item_id: int,
    db: Session = Depends(get_db),
    profile: ProfileMetadata = Depends(get_current_profile)
):
    """
    Approves a staging item into the permanent ledger.
    Guarantees recoverable atomic file archival: if moving the receipt fails,
    the item remains in review and no misleading transaction is created.
    """
    try:
        tx = approve_staging_item(
            db,
            item_id,
            staging_dir=profile.staging_receipts_dir,
            archive_dir=profile.receipts_dir
        )
        return {"success": True, "transaction_id": tx.id}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@router.post("/items/{item_id}/split", response_model=StagingSplitResponse)
@router.post("/{item_id}/split", response_model=StagingSplitResponse)
def split_staging_item_endpoint(
    item_id: int,
    payload: StagingSplitRequest,
    db: Session = Depends(get_db),
    profile: ProfileMetadata = Depends(get_current_profile)
):
    """
    Manually divides a single expense receipt candidate into two or more categorized expense rows.
    Supports either immediate atomic approval into the permanent ledger or queuing as pending review items.
    """
    try:
        res = split_staging_item(
            db=db,
            item_id=item_id,
            splits=payload.splits,
            commit_to_ledger=payload.commit_to_ledger,
            account_id=payload.account_id,
            transaction_date=payload.transaction_date,
            merchant=payload.merchant,
            notes=payload.notes,
            staging_dir=profile.staging_receipts_dir,
            archive_dir=profile.receipts_dir
        )
        created_items_resp = [_to_staging_response(c, db) for c in res.get("created_items", [])]
        return StagingSplitResponse(
            success=res["success"],
            action=res["action"],
            parent_id=res["parent_id"],
            created_item_ids=res.get("created_item_ids", []),
            created_items=created_items_resp,
            transaction_ids=res.get("transaction_ids", []),
            message=res["message"]
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Split failed: {str(e)}")

@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def discard_staging_item_endpoint(
    item_id: int,
    db: Session = Depends(get_db),
    profile: ProfileMetadata = Depends(get_current_profile)
):
    """Discards / rejects a staging item and deletes its temporary receipt file."""
    stg = db.query(StagingItem).filter(StagingItem.id == item_id).first()
    if not stg:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Staging item not found.")
    if stg.status == StagingStatus.APPROVED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot discard an item that has already been approved and committed to the ledger."
        )
    success = discard_staging_item(
        db,
        item_id,
        staging_dir=profile.staging_receipts_dir,
        archive_dir=profile.receipts_dir
    )
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Staging item not found.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)

@router.post("/batch-approve", response_model=StagingBatchApproveResponse)
def batch_approve_staging_items_endpoint(
    payload: StagingBatchApprovePayload,
    db: Session = Depends(get_db),
    profile: ProfileMetadata = Depends(get_current_profile)
):
    """
    Batch approves pending items.
    Excludes potential duplicates by default unless include_duplicates=True.
    """
    result = batch_approve_staging_items(
        db=db,
        item_ids=payload.item_ids,
        include_duplicates=payload.include_duplicates,
        staging_dir=profile.staging_receipts_dir,
        archive_dir=profile.receipts_dir
    )
    return StagingBatchApproveResponse(**result)

@router.post("/batch-reject", status_code=status.HTTP_200_OK)
def batch_reject_staging_items_endpoint(
    payload: StagingBatchRejectPayload,
    db: Session = Depends(get_db),
    profile: ProfileMetadata = Depends(get_current_profile)
):
    """Batch rejects / discards selected staging items."""
    result = batch_reject_staging_items(
        db=db,
        item_ids=payload.item_ids,
        staging_dir=profile.staging_receipts_dir,
        archive_dir=profile.receipts_dir
    )
    return result

