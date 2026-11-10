import json
import os
import re
import shutil
import uuid
import hashlib
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

from app.config import STAGING_RECEIPTS_DIR, ARCHIVE_RECEIPTS_DIR, DATA_DIR
from app.models import (
    StagingItem, StagingStatus, Transaction, TransactionType, 
    ExpenseNature, Account, Category, CategoryType
)
from app.core.categories import (
    CategoryValidationError,
    expected_category_type_for_transaction,
    validate_category_for_transaction_type,
)
from app.core.statement_parser import StatementParser
from app.ocr.factory import OCRFactory
from app.core.backup import get_system_setting, set_system_setting
from app.core.currency import get_effective_base_currency

DUPLICATE_DATE_WINDOW_DAYS = 4
PROFILES_SETTING_KEY = "statement_mapping_profiles"

def _normalize_text(text: Optional[str]) -> str:
    if not text:
        return ""
    return "".join(c.lower() for c in text if c.isalnum() or c.isspace()).strip()

def evaluate_duplicates(
    db: Session,
    amount_pence: Optional[int],
    tx_date: Optional[datetime],
    merchant: Optional[str],
    target_account_id: Optional[int] = None
) -> Tuple[bool, List[Dict[str, Any]]]:
    """
    Evaluates whether a candidate record matches any existing transaction in the ledger.
    Strictly advisory: returns (is_potential_duplicate, matches_list).
    """
    if amount_pence is None or tx_date is None:
        return False, []

    window_start = tx_date - timedelta(days=DUPLICATE_DATE_WINDOW_DAYS)
    window_end = tx_date + timedelta(days=DUPLICATE_DATE_WINDOW_DAYS)

    # Filter transactions by exact amount and date window
    query = db.query(Transaction).filter(
        and_(
            Transaction.amount_pence == amount_pence,
            Transaction.transaction_date >= window_start,
            Transaction.transaction_date <= window_end
        )
    )

    if target_account_id is not None:
        query = query.filter(
            or_(
                Transaction.account_id == target_account_id,
                Transaction.destination_account_id == target_account_id
            )
        )

    candidates = query.all()
    if not candidates:
        return False, []

    matches: List[Dict[str, Any]] = []
    norm_candidate_merchant = _normalize_text(merchant)

    for tx in candidates:
        match_reasons = [f"Exact amount: {amount_pence / 100:.2f}"]
        
        day_diff = abs((tx.transaction_date.date() - tx_date.date()).days) if tx.transaction_date and tx_date else 0
        if day_diff == 0:
            match_reasons.append("Exact same day")
        else:
            match_reasons.append(f"Within {day_diff} day{'s' if day_diff > 1 else ''}")

        norm_tx_merchant = _normalize_text(tx.merchant)
        if norm_candidate_merchant and norm_tx_merchant:
            if norm_candidate_merchant in norm_tx_merchant or norm_tx_merchant in norm_candidate_merchant:
                match_reasons.append(f"Matching merchant: '{tx.merchant}'")

        account_name = tx.account.name if tx.account else "Unknown"

        matches.append({
            "id": tx.id,
            "transaction_date": tx.transaction_date.isoformat(),
            "amount_pence": tx.amount_pence,
            "merchant": tx.merchant,
            "account_id": tx.account_id,
            "account_name": account_name,
            "transaction_type": tx.transaction_type.value,
            "match_reasons": match_reasons
        })

    return len(matches) > 0, matches

# --- Mapping Profile Management ---

def list_mapping_profiles(db: Session) -> List[Dict[str, Any]]:
    """Retrieves saved statement mapping profiles from system_settings."""
    raw = get_system_setting(db, PROFILES_SETTING_KEY, "[]")
    try:
        profiles = json.loads(raw)
        return profiles if isinstance(profiles, list) else []
    except Exception:
        return []

def save_mapping_profile(db: Session, profile: Dict[str, Any]) -> Dict[str, Any]:
    """Saves or updates a statement mapping profile."""
    profiles = list_mapping_profiles(db)
    profile_id = profile.get("id") or str(uuid.uuid4())[:8]
    profile["id"] = profile_id
    profile["updated_at"] = datetime.now(timezone.utc).isoformat()
    if "created_at" not in profile:
        profile["created_at"] = profile["updated_at"]
    if "version" not in profile:
        profile["version"] = 1

    existing_idx = next((i for i, p in enumerate(profiles) if p.get("id") == profile_id or p.get("name") == profile.get("name")), None)
    if existing_idx is not None:
        profiles[existing_idx] = profile
    else:
        profiles.append(profile)

    set_system_setting(db, PROFILES_SETTING_KEY, json.dumps(profiles, indent=2))
    return profile

def delete_mapping_profile(db: Session, profile_id: str) -> bool:
    """Deletes a saved mapping profile by ID."""
    profiles = list_mapping_profiles(db)
    filtered = [p for p in profiles if p.get("id") != profile_id]
    if len(filtered) != len(profiles):
        set_system_setting(db, PROFILES_SETTING_KEY, json.dumps(filtered, indent=2))
        return True
    return False

# --- Statement & Receipt Ingestion ---

def ingest_statement_csv(
    db: Session,
    file_content: bytes,
    filename: str,
    mapping: Dict[str, Any],
    target_account_id: Optional[int] = None
) -> Dict[str, Any]:
    """
    Parses and queues statement rows into staging_items with non-blocking duplicate detection.
    """
    if target_account_id:
        target_acc = db.query(Account).filter(Account.id == target_account_id).first()
        if not target_acc:
            raise ValueError(f"Account with ID {target_account_id} not found.")
        account_currency = target_acc.currency or "GBP"
    else:
        target_acc = None
        account_currency = get_effective_base_currency(db)

    parse_result = StatementParser.parse_statement(
        file_content=file_content,
        filename=filename,
        mapping=mapping,
        account_currency=account_currency
    )

    batch_id = str(uuid.uuid4())
    staged_items: List[StagingItem] = []

    for item in parse_result["items"]:
        amt = item["extracted_amount_pence"]
        dt = item["extracted_date"]
        merchant = item["extracted_merchant"]

        is_dup, dup_matches = evaluate_duplicates(
            db=db,
            amount_pence=amt,
            tx_date=dt,
            merchant=merchant,
            target_account_id=target_account_id
        )

        payload = {
            "batch_id": batch_id,
            "source_filename": filename,
            "line_number": item["line_number"],
            "transaction_type": item["transaction_type"],
            "destination_account_id": None,
            "notes": item["notes"],
            "currency": item["currency"],
            "original_amount": item.get("original_amount"),
            "original_currency": item.get("original_currency"),
            "exchange_rate": item.get("exchange_rate"),
            "requires_base_amount": item.get("requires_base_amount", False),
            "currency_conflict": item["currency_conflict"],
            "currency_conflict_message": item["currency_conflict_message"],
            "is_potential_duplicate": is_dup,
            "duplicate_matches": dup_matches,
            "raw_row_data": item["raw_row_data"]
        }

        # Attempt to match suggested category strictly within expected transaction purpose
        try:
            row_tx_type = TransactionType(str(item.get("transaction_type") or "expense").strip().lower())
        except ValueError:
            row_tx_type = TransactionType.EXPENSE
        expected_cat_type = expected_category_type_for_transaction(row_tx_type)
        cat_id = None
        matched_cat_name = None
        if expected_cat_type is not None and item.get("suggested_category_name"):
            cat = (
                db.query(Category)
                .filter(
                    Category.category_type == expected_cat_type,
                    Category.name.ilike(item["suggested_category_name"].strip()),
                )
                .first()
            )
            if cat:
                cat_id = cat.id
                matched_cat_name = cat.name
                payload["category_id"] = cat.id

        staging_item = StagingItem(
            created_at=datetime.now(timezone.utc),
            status=StagingStatus.PENDING,
            extracted_amount_pence=amt,
            extracted_date=dt,
            extracted_merchant=merchant,
            suggested_category_name=matched_cat_name,
            suggested_account_id=target_account_id,
            suggested_expense_nature=ExpenseNature.UNCLASSIFIED,
            source_type="statement_csv",
            temp_file_path=None,
            raw_payload_json=json.dumps(payload)
        )
        db.add(staging_item)
        staged_items.append(staging_item)

    db.commit()

    return {
        "batch_id": batch_id,
        "source_filename": filename,
        "total_rows": parse_result["total_rows"],
        "staged_count": len(staged_items),
        "skipped_count": parse_result["skipped_count"],
        "skipped_rows": parse_result["skipped_rows"]
    }

def ingest_receipt_image(
    db: Session,
    file_content: bytes,
    original_filename: str,
    target_account_id: Optional[int] = None,
    staging_dir: Path = STAGING_RECEIPTS_DIR
) -> StagingItem:
    """
    Saves receipt to staging_receipts, runs OCR adapter, and creates a staging item.
    Leaves uncertain fields blank (None) when OCR is unreadable or uncertain.
    """
    staging_dir.mkdir(parents=True, exist_ok=True)
    safe_name = f"{uuid.uuid4().hex[:10]}_{Path(original_filename).name}"
    target_path = staging_dir / safe_name

    with open(target_path, "wb") as f:
        f.write(file_content)

    # Pluggable OCR Parser
    from app.core.timezone import get_app_timezone
    app_tz = get_app_timezone(db)
    parser = OCRFactory.get_parser()
    try:
        ocr_result = parser.parse_receipt(target_path, tz_str=app_tz)
    except TypeError:
        ocr_result = parser.parse_receipt(target_path)

    target_acc = db.query(Account).filter(Account.id == target_account_id).first() if target_account_id else None
    from app.core.currency import get_effective_base_currency, pounds_to_pence
    account_currency = target_acc.currency if target_acc else get_effective_base_currency(db)
    detected_curr = getattr(ocr_result, "detected_currency", None) or account_currency

    amt = getattr(ocr_result, "amount_pence", None)
    orig_amt = getattr(ocr_result, "original_amount", None)
    orig_curr = None
    curr_conflict = False
    curr_msg = None
    req_base = False

    if detected_curr and detected_curr.upper() != account_currency.upper():
        # Foreign receipt detected!
        # Do not infer or calculate base charge. Leave extracted_amount_pence = None
        orig_curr = detected_curr.upper()
        orig_amt = getattr(ocr_result, "original_amount", None) or (amt / 100.0 if amt else None)
        amt = None
        curr_conflict = True
        req_base = True
        curr_msg = (
            f"Receipt is in foreign currency ({orig_curr} {orig_amt}). "
            f"Enter the actual {account_currency} amount charged to your card/bank before approving."
        )

    dt = getattr(ocr_result, "transaction_date", None)
    merchant = getattr(ocr_result, "merchant", None)

    is_dup, dup_matches = False, []
    if amt and dt:
        is_dup, dup_matches = evaluate_duplicates(
            db=db,
            amount_pence=amt,
            tx_date=dt,
            merchant=merchant,
            target_account_id=target_account_id
        )

    # Relative path from DATA_DIR if within DATA_DIR, else absolute path
    try:
        relative_temp_path = str(target_path.relative_to(DATA_DIR))
    except ValueError:
        relative_temp_path = str(target_path)

    payload = {
        "source_filename": original_filename,
        "transaction_type": "expense",
        "destination_account_id": None,
        "notes": None,
        "currency": account_currency,
        "original_amount": orig_amt,
        "original_currency": orig_curr,
        "exchange_rate": None,
        "requires_base_amount": req_base,
        "currency_conflict": curr_conflict,
        "currency_conflict_message": curr_msg,
        "is_potential_duplicate": is_dup,
        "duplicate_matches": dup_matches,
        "ocr_confidence": ocr_result.confidence,
        "ocr_raw_lines": ocr_result.raw_lines,
        "ocr_error": ocr_result.error_message
    }

    staging_item = StagingItem(
        created_at=datetime.now(timezone.utc),
        status=StagingStatus.PENDING,
        extracted_amount_pence=amt,
        extracted_date=dt,
        extracted_merchant=merchant,
        suggested_category_name=ocr_result.suggested_category_name,
        suggested_account_id=target_account_id,
        suggested_expense_nature=ExpenseNature.VARIABLE if amt else ExpenseNature.UNCLASSIFIED,
        source_type="receipt_image",
        temp_file_path=relative_temp_path,
        raw_payload_json=json.dumps(payload)
    )
    db.add(staging_item)
    db.commit()
    db.refresh(staging_item)
    return staging_item

# --- Review & Lifecycle Operations ---

def update_staging_item(
    db: Session,
    item_id: int,
    updates: Dict[str, Any]
) -> StagingItem:
    """Updates fields of a pending staging item."""
    item = db.query(StagingItem).filter(StagingItem.id == item_id).first()
    if not item:
        raise ValueError(f"Staging item with ID {item_id} not found.")

    if item.status != StagingStatus.PENDING:
        raise ValueError(f"Cannot edit staging item with status {item.status}.")

    payload = json.loads(item.raw_payload_json or "{}")

    if "merchant" in updates:
        item.extracted_merchant = updates["merchant"].strip() if updates["merchant"] else None
    if "amount" in updates and updates["amount"] is not None:
        from app.core.currency import pounds_to_pence
        item.extracted_amount_pence = pounds_to_pence(updates["amount"])
        if payload.get("original_amount"):
            from decimal import Decimal, ROUND_HALF_UP
            orig_dec = Decimal(str(payload["original_amount"]))
            base_dec = Decimal(str(updates["amount"]))
            payload["exchange_rate"] = float((base_dec / orig_dec).quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP))
        payload["requires_base_amount"] = False
        payload["currency_conflict"] = False
        payload["currency_conflict_message"] = None
    elif "amount_pence" in updates:
        item.extracted_amount_pence = updates["amount_pence"]
    if "original_amount" in updates and updates["original_amount"] is not None:
        payload["original_amount"] = float(updates["original_amount"])
    if "original_currency" in updates and updates["original_currency"]:
        payload["original_currency"] = updates["original_currency"].strip().upper()
    if "exchange_rate" in updates and updates["exchange_rate"] is not None:
        payload["exchange_rate"] = float(updates["exchange_rate"])
    if "transaction_date" in updates:
        item.extracted_date = updates["transaction_date"]
    if "account_id" in updates:
        item.suggested_account_id = updates["account_id"]
    if "transaction_type" in updates:
        payload["transaction_type"] = updates["transaction_type"]

    effective_type_str = str(payload.get("transaction_type") or "expense").strip().lower()
    try:
        effective_tx_type = TransactionType(effective_type_str)
    except ValueError:
        effective_tx_type = TransactionType.EXPENSE
    expected_cat_type = expected_category_type_for_transaction(effective_tx_type)

    if "category_id" in updates:
        if updates["category_id"] is not None:
            cat = validate_category_for_transaction_type(db, updates["category_id"], effective_tx_type)
            payload["category_id"] = cat.id
            item.suggested_category_name = cat.name
            if "expense_nature" not in updates and effective_tx_type == TransactionType.EXPENSE:
                item.suggested_expense_nature = cat.default_expense_nature or ExpenseNature.UNCLASSIFIED
        else:
            payload["category_id"] = None
            item.suggested_category_name = None
    elif "category_name" in updates:
        raw_name = (updates["category_name"] or "").strip()
        if not raw_name:
            payload["category_id"] = None
            item.suggested_category_name = None
        else:
            if expected_cat_type is None:
                raise CategoryValidationError(
                    f"Transactions of type '{effective_tx_type.value}' cannot be assigned a category.",
                    status_code=400,
                )
            cat = db.query(Category).filter(Category.name.ilike(raw_name)).first()
            if cat:
                cat = validate_category_for_transaction_type(db, cat.id, effective_tx_type)
                payload["category_id"] = cat.id
                item.suggested_category_name = cat.name
            else:
                payload["category_id"] = None
                item.suggested_category_name = raw_name
    elif "transaction_type" in updates:
        # Switching transaction type must not silently retain an incompatible category
        if expected_cat_type is None:
            payload["category_id"] = None
            item.suggested_category_name = None
        else:
            existing_cat = None
            if payload.get("category_id"):
                existing_cat = db.query(Category).filter(Category.id == payload["category_id"]).first()
            elif item.suggested_category_name:
                existing_cat = db.query(Category).filter(Category.name.ilike(item.suggested_category_name.strip())).first()
            if existing_cat and (existing_cat.category_type or CategoryType.EXPENSE) != expected_cat_type:
                payload["category_id"] = None
                item.suggested_category_name = None

    if effective_tx_type != TransactionType.EXPENSE:
        item.suggested_expense_nature = ExpenseNature.UNCLASSIFIED
    elif "expense_nature" in updates:
        item.suggested_expense_nature = updates["expense_nature"]

    if "destination_account_id" in updates:
        payload["destination_account_id"] = updates["destination_account_id"]
    if "notes" in updates:
        payload["notes"] = updates["notes"]
    if "anchor_mode" in updates and updates["anchor_mode"] is not None:
        item.anchor_mode = updates["anchor_mode"]
    if "effective_timestamp" in updates and updates["effective_timestamp"] is not None:
        item.effective_timestamp = updates["effective_timestamp"]

    # Re-evaluate duplicate status if date or amount changed
    is_dup, dup_matches = evaluate_duplicates(
        db=db,
        amount_pence=item.extracted_amount_pence,
        tx_date=item.extracted_date,
        merchant=item.extracted_merchant,
        target_account_id=item.suggested_account_id
    )
    payload["is_potential_duplicate"] = is_dup
    payload["duplicate_matches"] = dup_matches

    item.raw_payload_json = json.dumps(payload)
    db.commit()
    db.refresh(item)
    return item

def approve_staging_item(
    db: Session,
    item_id: int,
    staging_dir: Path = STAGING_RECEIPTS_DIR,
    archive_dir: Path = ARCHIVE_RECEIPTS_DIR
) -> Transaction:
    """
    Atomically approves a staging item into the permanent ledger.
    Guarantees recoverable two-phase file archival: if moving the receipt fails,
    no transaction is created and the staging item remains reviewable.
    """
    item = db.query(StagingItem).filter(StagingItem.id == item_id).first()
    if not item:
        raise ValueError(f"Staging item with ID {item_id} not found.")

    if item.status != StagingStatus.PENDING:
        raise ValueError(f"Staging item {item_id} is already {item.status.value}.")

    # Validate required fields
    clean_merchant = item.extracted_merchant.strip() if item.extracted_merchant and item.extracted_merchant.strip() else None

    if not item.extracted_date:
        raise ValueError("Transaction date is required before approval.")

    payload = json.loads(item.raw_payload_json or "{}")
    raw_tx_type = payload.get("transaction_type", "expense").lower()

    if raw_tx_type == "income":
        tx_type = TransactionType.INCOME
    elif raw_tx_type == "transfer":
        tx_type = TransactionType.TRANSFER
    elif raw_tx_type == "adjustment":
        tx_type = TransactionType.ADJUSTMENT
    else:
        tx_type = TransactionType.EXPENSE

    base_curr = get_effective_base_currency(db)
    account = None
    if item.suggested_account_id:
        account = db.query(Account).filter(Account.id == item.suggested_account_id).first()
        if not account:
            raise ValueError(f"Account with ID {item.suggested_account_id} not found.")
        curr_name = account.currency
    else:
        if tx_type in (TransactionType.TRANSFER, TransactionType.ADJUSTMENT):
            raise ValueError(f"Target account is required for {tx_type.value} before approval.")
        curr_name = base_curr

    if not item.extracted_amount_pence or item.extracted_amount_pence <= 0:
        raise ValueError(f"A positive base-currency ({curr_name}) transaction amount is required before approval.")

    dest_account_id = payload.get("destination_account_id")
    if tx_type == TransactionType.TRANSFER:
        if not dest_account_id:
            raise ValueError("Destination account is required for transfers.")
        if dest_account_id == item.suggested_account_id:
            raise ValueError("Source and destination accounts must be distinct.")
        dest_acc = db.query(Account).filter(Account.id == dest_account_id).first()
        if not dest_acc:
            raise ValueError(f"Destination account with ID {dest_account_id} not found.")

    # Match & validate Category against transaction type
    expected_cat_type = expected_category_type_for_transaction(tx_type)
    category_id = None
    if expected_cat_type is not None:
        if payload.get("category_id"):
            cat = validate_category_for_transaction_type(db, payload["category_id"], tx_type)
            category_id = cat.id
        elif item.suggested_category_name:
            cat = (
                db.query(Category)
                .filter(
                    Category.category_type == expected_cat_type,
                    Category.name.ilike(item.suggested_category_name.strip()),
                )
                .first()
            )
            if cat:
                category_id = cat.id

    # Handle Receipt File Archiving with Content Hashing (SHA-256) and Multi-Row Reference Counting
    archived_receipt_relative_path: Optional[str] = None
    staged_file_to_cleanup: Optional[Path] = None
    copied_archive_file: Optional[Path] = None

    if item.temp_file_path:
        p = Path(item.temp_file_path)
        source_file = p if p.is_absolute() else DATA_DIR / item.temp_file_path

        if source_file.exists() and source_file.is_file():
            import hashlib
            source_bytes = source_file.read_bytes()
            source_hash = hashlib.sha256(source_bytes).hexdigest()

            # Clean name without prior hex prefix to keep name clean
            clean_name = re.sub(r'^[a-f0-9]{8,16}_', '', source_file.name)
            archive_filename = f"{source_hash[:12]}_{clean_name}"

            tx_dt = item.extracted_date or datetime.now(timezone.utc)
            year_str = f"{tx_dt.year:04d}"
            month_str = f"{tx_dt.month:02d}"
            target_folder = archive_dir / year_str / month_str
            target_archive_path = target_folder / archive_filename

            # Reuse requires matching file content (SHA-256 hash)
            existing_archived_file = None
            if target_archive_path.exists() and hashlib.sha256(target_archive_path.read_bytes()).hexdigest() == source_hash:
                existing_archived_file = target_archive_path
            elif archive_dir.exists():
                for cand in archive_dir.rglob(archive_filename):
                    if cand.is_file() and hashlib.sha256(cand.read_bytes()).hexdigest() == source_hash:
                        existing_archived_file = cand
                        break

            if existing_archived_file:
                target_archive_path = existing_archived_file
                staged_file_to_cleanup = source_file
                try:
                    archived_receipt_relative_path = str(target_archive_path.relative_to(DATA_DIR))
                except ValueError:
                    archived_receipt_relative_path = str(target_archive_path)
            else:
                try:
                    target_folder.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source_file, target_archive_path)
                    copied_archive_file = target_archive_path
                    staged_file_to_cleanup = source_file
                    try:
                        archived_receipt_relative_path = str(target_archive_path.relative_to(DATA_DIR))
                    except ValueError:
                        archived_receipt_relative_path = str(target_archive_path)
                except Exception as e:
                    # File copy failed; abort approval cleanly
                    raise RuntimeError(f"Failed to archive receipt file: {str(e)}. Staging item remains pending.")

    try:
        from decimal import Decimal, ROUND_HALF_UP
        from datetime import timedelta
        from app.core.timezone import (
            get_app_timezone, get_today_local, get_now_utc,
            get_midday_utc, parse_date_input, ensure_utc
        )
        orig_amt = Decimal(str(payload["original_amount"])) if payload.get("original_amount") is not None else None
        orig_curr = payload.get("original_currency")
        rate = Decimal(str(payload["exchange_rate"])) if payload.get("exchange_rate") is not None else None

        if orig_curr and orig_amt and not rate and item.extracted_amount_pence:
            rate = ((Decimal(item.extracted_amount_pence) / Decimal(100)) / orig_amt).quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP)

        # Resolve effective_timestamp against account anchors
        latest_anchor = account.latest_anchor if account else None
        latest_anchor_date = ensure_utc(latest_anchor.anchor_date) if latest_anchor else None
        effective_ts = item.effective_timestamp
        if not effective_ts:
            app_tz = get_app_timezone(db)
            today_local = get_today_local(app_tz)
            item_d = parse_date_input(item.extracted_date)
            mode = (getattr(item, "anchor_mode", "auto") or "auto").strip().lower()

            if mode in ("already_reflected", "prior_to_anchor"):
                if latest_anchor_date:
                    effective_ts = latest_anchor_date - timedelta(seconds=1)
                else:
                    effective_ts = get_midday_utc(item.extracted_date, tz_str=app_tz)
            elif mode == "after_anchor":
                if latest_anchor_date:
                    effective_ts = max(get_now_utc(), latest_anchor_date + timedelta(seconds=1))
                else:
                    effective_ts = get_now_utc()
            else:  # mode == "auto"
                if latest_anchor_date:
                    anchor_d = parse_date_input(latest_anchor_date)
                    if item_d > anchor_d:
                        effective_ts = get_now_utc() if item_d == today_local else get_midday_utc(item.extracted_date, tz_str=app_tz)
                    else:
                        effective_ts = latest_anchor_date - timedelta(seconds=1)
                else:
                    effective_ts = get_now_utc() if item_d == today_local else get_midday_utc(item.extracted_date, tz_str=app_tz)

        tx = Transaction(
            transaction_date=item.extracted_date,
            effective_timestamp=effective_ts,
            created_at=item.created_at or get_now_utc(),
            transaction_type=tx_type,
            amount_pence=item.extracted_amount_pence,
            merchant=clean_merchant,
            notes=payload.get("notes"),
            entry_method=item.source_type or "staging",
            receipt_path=archived_receipt_relative_path,
            account_id=item.suggested_account_id,
            destination_account_id=dest_account_id if tx_type == TransactionType.TRANSFER else None,
            category_id=category_id,
            expense_nature=(
                (item.suggested_expense_nature or ExpenseNature.UNCLASSIFIED)
                if tx_type == TransactionType.EXPENSE
                else ExpenseNature.UNCLASSIFIED
            ),
            original_amount=orig_amt,
            original_currency=orig_curr,
            exchange_rate=rate
        )
        db.add(tx)
        item.status = StagingStatus.APPROVED
        db.commit()
        db.refresh(tx)

        # DB commit succeeded -> remove source staging file safely only when no other pending items reference it
        if staged_file_to_cleanup and staged_file_to_cleanup.exists():
            remaining_pending = db.query(StagingItem).filter(
                StagingItem.id != item.id,
                StagingItem.status == StagingStatus.PENDING,
                StagingItem.temp_file_path == item.temp_file_path
            ).count()
            if remaining_pending == 0:
                try:
                    staged_file_to_cleanup.unlink()
                except OSError:
                    pass

        # Learn confirmed card-to-account association if card label was extracted and account was assigned/approved
        extracted_card_label = payload.get("extracted_card_label")
        extracted_card_last_4 = payload.get("extracted_card_last_4")
        if extracted_card_label and item.suggested_account_id:
            from app.core.unified_importer import save_confirmed_account_association
            save_confirmed_account_association(
                db,
                extracted_card_label,
                item.suggested_account_id,
                last_4=extracted_card_last_4
            )

        return tx

    except Exception as e:
        db.rollback()
        # Clean up copied archive file if DB failed
        if copied_archive_file and copied_archive_file.exists():
            try:
                copied_archive_file.unlink()
            except OSError:
                pass
        raise e

def discard_staging_item(
    db: Session,
    item_id: int,
    staging_dir: Path = STAGING_RECEIPTS_DIR,
    archive_dir: Optional[Path] = None
) -> bool:
    """
    Discards / rejects a staging item.
    - If the item was already approved into the ledger, it is not modified (preserves ledger integrity).
    - Preserves shared source staging files as long as any sibling items remain pending.
    - Cleans up staging file only when no remaining pending items reference it.
    - Never deletes archived files or committed records.
    """
    item = db.query(StagingItem).filter(StagingItem.id == item_id).first()
    if not item:
        return False

    # Never discard an item that has already been approved and committed to the ledger
    if item.status == StagingStatus.APPROVED:
        return False

    if item.status == StagingStatus.REJECTED:
        return True

    if item.temp_file_path:
        remaining_pending = db.query(StagingItem).filter(
            StagingItem.id != item.id,
            StagingItem.status == StagingStatus.PENDING,
            StagingItem.temp_file_path == item.temp_file_path
        ).count()
        if remaining_pending == 0:
            p = Path(item.temp_file_path)
            file_path = None
            if p.is_absolute() and p.is_file():
                file_path = p
            elif (DATA_DIR / item.temp_file_path).is_file():
                file_path = DATA_DIR / item.temp_file_path
            elif (staging_dir / p.name).is_file():
                file_path = staging_dir / p.name

            # Guard: ensure we NEVER delete an archived receipt file
            is_archived = False
            if file_path and archive_dir and archive_dir.exists():
                try:
                    file_path.resolve().relative_to(archive_dir.resolve())
                    is_archived = True
                except ValueError:
                    pass

            if file_path and not is_archived and file_path.exists() and file_path.is_file():
                try:
                    file_path.unlink()
                except OSError:
                    pass

    item.status = StagingStatus.REJECTED
    db.commit()
    return True

def batch_approve_staging_items(
    db: Session,
    item_ids: Optional[List[int]] = None,
    include_duplicates: bool = False,
    staging_dir: Path = STAGING_RECEIPTS_DIR,
    archive_dir: Path = ARCHIVE_RECEIPTS_DIR
) -> Dict[str, Any]:
    """
    Batch approves pending staging items.
    Excludes potential duplicates by default unless include_duplicates=True.
    """
    query = db.query(StagingItem).filter(StagingItem.status == StagingStatus.PENDING)
    if item_ids:
        query = query.filter(StagingItem.id.in_(item_ids))

    items = query.all()

    approved_count = 0
    excluded_duplicates_count = 0
    errors: List[Dict[str, Any]] = []

    for item in items:
        payload = json.loads(item.raw_payload_json or "{}")
        is_dup = payload.get("is_potential_duplicate", False)

        if is_dup and not include_duplicates:
            excluded_duplicates_count += 1
            continue

        try:
            approve_staging_item(db, item.id, staging_dir, archive_dir)
            approved_count += 1
        except Exception as e:
            errors.append({"id": item.id, "error": str(e)})

    return {
        "approved_count": approved_count,
        "excluded_duplicates_count": excluded_duplicates_count,
        "error_count": len(errors),
        "errors": errors
    }

def batch_reject_staging_items(
    db: Session,
    item_ids: List[int],
    staging_dir: Path = STAGING_RECEIPTS_DIR,
    archive_dir: Optional[Path] = None
) -> Dict[str, Any]:
    """Batch rejects / discards a list of staging items."""
    rejected_count = 0
    for i_id in item_ids:
        if discard_staging_item(db, i_id, staging_dir, archive_dir):
            rejected_count += 1

    return {"rejected_count": rejected_count}


def split_staging_item(
    db: Session,
    item_id: int,
    splits: List[Any],
    commit_to_ledger: bool = False,
    account_id: Optional[int] = None,
    transaction_date: Optional[datetime] = None,
    merchant: Optional[str] = None,
    notes: Optional[str] = None,
    staging_dir: Path = STAGING_RECEIPTS_DIR,
    archive_dir: Path = ARCHIVE_RECEIPTS_DIR
) -> Dict[str, Any]:
    """
    Manually splits a single expense receipt candidate into two or more categorized expense rows.
    Validates that:
    1. Parent item is a pending expense receipt.
    2. At least two split rows are provided.
    3. Every split amount is positive minor units (pence).
    4. Sum of split amounts equals the parent receipt total exactly (no rounding drift).
    5. Shared receipt fields (account, transaction date, merchant, notes) are preserved or edited.
    6. When commit_to_ledger=True, archives receipt once and creates transactions atomically.
    7. When commit_to_ledger=False, creates new pending StagingItems and replaces the parent.
    8. Shared receipt file lifecycle is preserved until all split siblings are resolved.
    """
    item = db.query(StagingItem).filter(StagingItem.id == item_id).first()
    if not item:
        raise ValueError(f"Staging item with ID {item_id} not found.")

    if item.status != StagingStatus.PENDING:
        raise ValueError(f"Staging item {item_id} is already {item.status.value}.")

    payload = json.loads(item.raw_payload_json or "{}")
    raw_tx_type = payload.get("transaction_type", "expense").lower()
    if raw_tx_type != "expense":
        raise ValueError(f"Only expense receipts can be split. Item {item_id} has type '{raw_tx_type}'.")

    if not item.extracted_amount_pence or item.extracted_amount_pence <= 0:
        raise ValueError("Parent receipt must have a positive amount to split.")

    if not splits or len(splits) < 2:
        raise ValueError("At least two split rows are required to split an expense receipt.")

    # Resolve shared values
    if account_id is not None:
        if account_id > 0:
            target_account = db.query(Account).filter(Account.id == account_id).first()
            if not target_account:
                raise ValueError(f"Account with ID {account_id} not found.")
            effective_account_id = target_account.id
        else:
            target_account = None
            effective_account_id = None
    else:
        effective_account_id = item.suggested_account_id
        target_account = db.query(Account).filter(Account.id == effective_account_id).first() if effective_account_id else None

    if transaction_date is not None:
        effective_date = transaction_date
    else:
        effective_date = item.extracted_date

    if merchant is not None:
        effective_merchant = merchant.strip() if merchant.strip() else None
    else:
        effective_merchant = item.extracted_merchant.strip() if item.extracted_merchant and item.extracted_merchant.strip() else None

    if notes is not None:
        effective_notes = notes.strip() if notes.strip() else None
    else:
        effective_notes = payload.get("notes")

    # Validate amounts and exact sum
    total_split_pence = 0
    resolved_splits = []
    for s in splits:
        amt = int(s.amount_pence if hasattr(s, "amount_pence") else s["amount_pence"])
        if amt <= 0:
            raise ValueError("Each split row must have a positive minor-unit amount.")
        total_split_pence += amt

        cat_id = s.category_id if hasattr(s, "category_id") else s.get("category_id")
        cat_name = s.category_name if hasattr(s, "category_name") else s.get("category_name")
        nature = s.expense_nature if hasattr(s, "expense_nature") else s.get("expense_nature")
        row_notes = s.notes if hasattr(s, "notes") else s.get("notes")

        if isinstance(nature, str):
            try:
                nature = ExpenseNature(nature.lower())
            except ValueError:
                nature = ExpenseNature.UNCLASSIFIED

        cat = None
        if cat_id:
            cat = validate_category_for_transaction_type(db, cat_id, TransactionType.EXPENSE)
        elif cat_name:
            found_cat = db.query(Category).filter(Category.name.ilike(cat_name.strip())).first()
            if found_cat:
                cat = validate_category_for_transaction_type(db, found_cat.id, TransactionType.EXPENSE)

        if cat:
            cat_id = cat.id
            cat_name = cat.name
            if not nature or nature == ExpenseNature.UNCLASSIFIED:
                nature = cat.default_expense_nature

        resolved_splits.append({
            "amount_pence": amt,
            "category_id": cat_id,
            "category_name": cat_name,
            "expense_nature": nature or ExpenseNature.UNCLASSIFIED,
            "notes": (row_notes.strip() if row_notes and row_notes.strip() else None)
        })

    if total_split_pence != item.extracted_amount_pence:
        raise ValueError(
            f"Split amounts sum to {total_split_pence} pence, but the receipt total is "
            f"{item.extracted_amount_pence} pence. Split amounts must match the receipt total exactly."
        )

    from decimal import Decimal, ROUND_HALF_UP
    from datetime import timedelta
    from app.core.timezone import (
        get_app_timezone, get_today_local, get_now_utc,
        get_midday_utc, parse_date_input, ensure_utc
    )

    if commit_to_ledger:
        if not effective_date:
            raise ValueError("Transaction date is required before approval.")

        account = target_account

        # Handle Receipt Archiving with SHA-256 hash deduplication
        archived_receipt_relative_path: Optional[str] = None
        staged_file_to_cleanup: Optional[Path] = None
        copied_archive_file: Optional[Path] = None

        if item.temp_file_path:
            p = Path(item.temp_file_path)
            source_file = p if p.is_absolute() else DATA_DIR / item.temp_file_path

            if source_file.exists() and source_file.is_file():
                import hashlib
                source_bytes = source_file.read_bytes()
                source_hash = hashlib.sha256(source_bytes).hexdigest()

                clean_name = re.sub(r'^[a-f0-9]{8,16}_', '', source_file.name)
                archive_filename = f"{source_hash[:12]}_{clean_name}"

                tx_dt = effective_date or datetime.now(timezone.utc)
                year_str = f"{tx_dt.year:04d}"
                month_str = f"{tx_dt.month:02d}"
                target_folder = archive_dir / year_str / month_str
                target_archive_path = target_folder / archive_filename

                existing_archived_file = None
                if target_archive_path.exists() and hashlib.sha256(target_archive_path.read_bytes()).hexdigest() == source_hash:
                    existing_archived_file = target_archive_path
                elif archive_dir.exists():
                    for cand in archive_dir.rglob(archive_filename):
                        if cand.is_file() and hashlib.sha256(cand.read_bytes()).hexdigest() == source_hash:
                            existing_archived_file = cand
                            break

                if existing_archived_file:
                    target_archive_path = existing_archived_file
                    staged_file_to_cleanup = source_file
                    try:
                        archived_receipt_relative_path = str(target_archive_path.relative_to(DATA_DIR))
                    except ValueError:
                        archived_receipt_relative_path = str(target_archive_path)
                else:
                    try:
                        target_folder.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(source_file, target_archive_path)
                        copied_archive_file = target_archive_path
                        staged_file_to_cleanup = source_file
                        try:
                            archived_receipt_relative_path = str(target_archive_path.relative_to(DATA_DIR))
                        except ValueError:
                            archived_receipt_relative_path = str(target_archive_path)
                    except Exception as e:
                        raise RuntimeError(f"Failed to archive receipt file: {str(e)}")

        try:
            # Resolve effective_timestamp against account anchors
            latest_anchor = account.latest_anchor if account else None
            latest_anchor_date = ensure_utc(latest_anchor.anchor_date) if latest_anchor else None
            effective_ts = item.effective_timestamp
            if not effective_ts:
                app_tz = get_app_timezone(db)
                today_local = get_today_local(app_tz)
                item_d = parse_date_input(effective_date)
                mode = (getattr(item, "anchor_mode", "auto") or "auto").strip().lower()

                if mode in ("already_reflected", "prior_to_anchor"):
                    if latest_anchor_date:
                        effective_ts = latest_anchor_date - timedelta(seconds=1)
                    else:
                        effective_ts = get_midday_utc(effective_date, tz_str=app_tz)
                elif mode == "after_anchor":
                    if latest_anchor_date:
                        effective_ts = max(get_now_utc(), latest_anchor_date + timedelta(seconds=1))
                    else:
                        effective_ts = get_now_utc()
                else:  # mode == "auto"
                    if latest_anchor_date:
                        anchor_d = parse_date_input(latest_anchor_date)
                        if item_d > anchor_d:
                            effective_ts = get_now_utc() if item_d == today_local else get_midday_utc(effective_date, tz_str=app_tz)
                        else:
                            effective_ts = latest_anchor_date - timedelta(seconds=1)
                    else:
                        effective_ts = get_now_utc() if item_d == today_local else get_midday_utc(effective_date, tz_str=app_tz)

            rate = Decimal(str(payload["exchange_rate"])) if payload.get("exchange_rate") is not None else None
            orig_curr = payload.get("original_currency")

            created_txs = []
            for s in resolved_splits:
                split_orig_amt = None
                if payload.get("original_amount") is not None:
                    parent_orig = Decimal(str(payload["original_amount"]))
                    split_orig_amt = ((Decimal(s["amount_pence"]) / Decimal(item.extracted_amount_pence)) * parent_orig).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

                tx = Transaction(
                    transaction_date=effective_date,
                    effective_timestamp=effective_ts,
                    created_at=item.created_at or get_now_utc(),
                    transaction_type=TransactionType.EXPENSE,
                    amount_pence=s["amount_pence"],
                    merchant=effective_merchant,
                    notes=s["notes"] or effective_notes,
                    entry_method=item.source_type or "receipt",
                    receipt_path=archived_receipt_relative_path,
                    account_id=effective_account_id,
                    destination_account_id=None,
                    category_id=s["category_id"],
                    expense_nature=s["expense_nature"],
                    original_amount=split_orig_amt,
                    original_currency=orig_curr,
                    exchange_rate=rate
                )
                db.add(tx)
                created_txs.append(tx)

            db.flush()

            # Mark parent as rejected (replaced by split)
            item.status = StagingStatus.REJECTED
            payload["split_into_tx_ids"] = [tx.id for tx in created_txs]
            payload["split_account_id"] = effective_account_id
            payload["split_merchant"] = effective_merchant
            if effective_date:
                payload["split_transaction_date"] = effective_date.isoformat()
            if effective_notes:
                payload["split_notes"] = effective_notes
            item.raw_payload_json = json.dumps(payload)

            # Cleanup staging file if no other pending items reference it
            if staged_file_to_cleanup and staged_file_to_cleanup.exists():
                remaining_pending = db.query(StagingItem).filter(
                    StagingItem.id != item.id,
                    StagingItem.status == StagingStatus.PENDING,
                    StagingItem.temp_file_path == item.temp_file_path
                ).count()
                if remaining_pending == 0:
                    try:
                        staged_file_to_cleanup.unlink()
                    except OSError:
                        pass

            db.commit()
            for tx in created_txs:
                db.refresh(tx)

            return {
                "success": True,
                "action": "approved",
                "parent_id": item.id,
                "created_item_ids": [],
                "created_items": [],
                "transaction_ids": [tx.id for tx in created_txs],
                "message": f"Successfully approved {len(created_txs)} split transactions into the ledger."
            }
        except Exception as e:
            db.rollback()
            if copied_archive_file and copied_archive_file.exists():
                try:
                    copied_archive_file.unlink()
                except OSError:
                    pass
            raise e

    else:
        # Save split rows as separate pending candidates in the Review Queue
        try:
            created_stg_items = []
            for idx, s in enumerate(resolved_splits):
                child_payload = dict(payload)
                child_payload["notes"] = s["notes"] or effective_notes
                child_payload["shared_notes"] = effective_notes
                child_payload["category_id"] = s["category_id"]
                child_payload["category_name"] = s["category_name"]
                child_payload["account_id"] = effective_account_id
                child_payload["merchant"] = effective_merchant
                if effective_date:
                    child_payload["transaction_date"] = effective_date.isoformat()
                child_payload["split_parent_id"] = item.id
                child_payload["split_index"] = idx + 1
                child_payload["split_total"] = len(resolved_splits)
                child_payload["is_split"] = True

                if payload.get("original_amount") is not None:
                    parent_orig = Decimal(str(payload["original_amount"]))
                    split_orig_amt = ((Decimal(s["amount_pence"]) / Decimal(item.extracted_amount_pence)) * parent_orig).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                    child_payload["original_amount"] = float(split_orig_amt)

                child = StagingItem(
                    created_at=item.created_at or get_now_utc(),
                    status=StagingStatus.PENDING,
                    extracted_amount_pence=s["amount_pence"],
                    extracted_date=effective_date,
                    extracted_merchant=effective_merchant,
                    suggested_category_name=s["category_name"],
                    suggested_account_id=effective_account_id,
                    suggested_expense_nature=s["expense_nature"],
                    source_type=item.source_type or "receipt",
                    temp_file_path=item.temp_file_path,
                    raw_payload_json=json.dumps(child_payload),
                    effective_timestamp=item.effective_timestamp,
                    anchor_mode=getattr(item, "anchor_mode", "auto") or "auto"
                )
                db.add(child)
                created_stg_items.append(child)

            db.flush()

            # Mark parent as rejected (replaced by split items)
            item.status = StagingStatus.REJECTED
            payload["split_children_ids"] = [c.id for c in created_stg_items]
            payload["split_account_id"] = effective_account_id
            payload["split_merchant"] = effective_merchant
            if effective_date:
                payload["split_transaction_date"] = effective_date.isoformat()
            if effective_notes:
                payload["split_notes"] = effective_notes
            item.raw_payload_json = json.dumps(payload)

            db.commit()

            for c in created_stg_items:
                db.refresh(c)

            return {
                "success": True,
                "action": "queued",
                "parent_id": item.id,
                "created_item_ids": [c.id for c in created_stg_items],
                "created_items": created_stg_items,
                "transaction_ids": [],
                "message": f"Successfully split receipt into {len(created_stg_items)} pending review items."
            }
        except Exception as e:
            db.rollback()
            raise e

