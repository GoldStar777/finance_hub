"""
Tests for the Unified Provider-Agnostic Financial Import Flow.
Validates:
1. File signature / MIME classification (not trusting file extensions alone).
2. Extraction routes: CSV/TSV, Excel (.xlsx), Single Receipt Image, Statement Screenshot (multi-row).
3. Unreadable and unsupported files (graceful degradation, manual entry path, source preservation).
4. Uncertain fields remaining blank (no invented values, foreign currency provenance).
5. Unassigned ordinary transactions vs account-enforced transfers.
6. Advisory duplicate detection (never blocking approval).
7. Commit actions: approve into ledger, queue for later, discard.
"""

import io
import json
import pytest
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from pathlib import Path
import openpyxl
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import (
    Base, Account, AccountType, Transaction, TransactionType,
    ExpenseNature, StagingItem, StagingStatus, AccountBalanceAnchor,
    Category
)
from app.config import DATA_DIR, STAGING_RECEIPTS_DIR, ARCHIVE_RECEIPTS_DIR
from app.core.file_classifier import inspect_file_signature, classify_uploaded_file
from app.ocr.base import OCRElement, BoundingBox
from app.core.unified_importer import (
    ingest_unified_file, parse_excel_statement, parse_screenshot_transactions,
    parse_screenshot_transactions_spatial,
    match_account_from_context, suggest_category_for_merchant, suggest_category_from_history,
    determine_transaction_direction, get_confirmed_account_associations,
    save_confirmed_account_association, delete_confirmed_account_association,
    list_confirmed_account_associations, get_local_semantic_embedding,
    extract_card_or_account_clues
)
from app.core.staging import approve_staging_item, discard_staging_item, update_staging_item
from app.ledger import LedgerEngine

@pytest.fixture
def isolated_db(tmp_path):
    db_file = tmp_path / "test_unified.db"
    engine = create_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    try:
        yield db, tmp_path
    finally:
        db.close()

# -------------------------------------------------------------------------
# 1. File Classification & Signature Inspection Tests
# -------------------------------------------------------------------------

def test_file_signature_inspection_does_not_trust_extension():
    # PNG disguised as .csv
    fake_csv_png = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    mime, ext, is_bin = inspect_file_signature(fake_csv_png, "transactions.csv")
    assert mime == "image/png"
    assert is_bin is True

    # Real CSV disguised as .pdf
    real_csv_bytes = b"Date,Merchant,Amount\n2026-10-14,Tesco,24.50\n2026-10-15,Boots,12.30\n"
    mime, ext, is_bin = inspect_file_signature(real_csv_bytes, "statement.pdf")
    assert mime == "text/csv"
    assert is_bin is False

    # PDF file
    pdf_bytes = b"%PDF-1.4\n%Fake PDF content for test\n"
    mime, ext, is_bin = inspect_file_signature(pdf_bytes, "document.dat")
    assert mime == "application/pdf"
    assert is_bin is True

    # Executable binary disguised as image
    fake_exe = b"MZ\x90\x00\x03\x00\x00\x00\x04\x00\x00\x00\xff\xff\x00\x00"
    mime, ext, is_bin = inspect_file_signature(fake_exe, "receipt.jpg")
    assert mime == "application/x-dosexec"
    assert is_bin is True

def test_classification_result_properties():
    # Excel .xlsx workbook
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Date", "Description", "Amount"])
    ws.append(["2026-10-14", "Waitrose", -35.20])
    buf = io.BytesIO()
    wb.save(buf)
    xlsx_bytes = buf.getvalue()

    result = classify_uploaded_file(xlsx_bytes, "october.bin")
    assert result.is_tabular is True
    assert result.mime_type == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert result.document_type == "statement"

# -------------------------------------------------------------------------
# 2. Excel (.xlsx) Extraction Tests
# -------------------------------------------------------------------------

def test_excel_statement_extraction(isolated_db):
    db, tmp_path = isolated_db
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Statement"
    # Metadata rows before header
    ws.append(["My Bank Statement"])
    ws.append(["Account Number: 12345678"])
    ws.append([])
    # Header row
    ws.append(["Date", "Description", "Debit", "Credit", "Balance"])
    ws.append(["2026-10-10", "Sainsbury's", 42.50, None, 1000.00])
    ws.append(["2026-10-12", "Salary Employer", None, 2500.00, 3500.00])
    ws.append(["2026-10-14", "Water Utility", 28.00, None, 3472.00])

    buf = io.BytesIO()
    wb.save(buf)
    file_bytes = buf.getvalue()

    res = ingest_unified_file(
        db=db,
        file_content=file_bytes,
        original_filename="bank_statement.xlsx",
        staging_dir=tmp_path / "staging_receipts"
    )

    assert res["document_type"] == "statement"
    assert len(res["items"]) == 3

    item1 = res["items"][0]
    assert "Sainsbury" in item1["extracted_merchant"]
    assert item1["extracted_amount_pence"] == 4250
    assert item1["transaction_type"] == "expense"

    item2 = res["items"][1]
    assert "Salary" in item2["extracted_merchant"]
    assert item2["extracted_amount_pence"] == 250000
    assert item2["transaction_type"] == "income"

# -------------------------------------------------------------------------
# 3. CSV / TSV Extraction Tests
# -------------------------------------------------------------------------

def test_csv_statement_extraction(isolated_db):
    db, tmp_path = isolated_db
    csv_content = (
        "Transaction Date,Merchant Name,Amount\n"
        "2026-10-15,Starbucks,4.85\n"
        "2026-10-16,Gym Membership,35.00\n"
    ).encode("utf-8")

    res = ingest_unified_file(
        db=db,
        file_content=csv_content,
        original_filename="card_activity.csv",
        staging_dir=tmp_path / "staging_receipts"
    )

    assert res["document_type"] == "statement"
    assert len(res["items"]) == 2
    assert res["items"][0]["extracted_merchant"] == "Starbucks"
    assert res["items"][0]["extracted_amount_pence"] == 485
    assert res["items"][1]["extracted_merchant"] == "Gym Membership"
    assert res["items"][1]["extracted_amount_pence"] == 3500

# -------------------------------------------------------------------------
# 4. Statement Screenshot (Multi-Row) Parsing Tests
# -------------------------------------------------------------------------

def test_statement_screenshot_multi_row_extraction():
    ocr_lines = [
        "Account Statement Activity",
        "Today",
        "Tesco Express",
        "Groceries",
        "-£14.20",
        "Pret A Manger",
        "Coffee",
        "-£3.95",
        "Yesterday",
        "Refund Amazon",
        "Shopping",
        "+£25.00",
        "Uber Trip",
        "-£18.50"
    ]

    items = parse_screenshot_transactions(ocr_lines, account_currency="GBP")
    assert len(items) == 4

    # Row 1: Tesco
    assert items[0]["extracted_merchant"] == "Tesco Express"
    assert items[0]["extracted_amount_pence"] == 1420
    assert items[0]["transaction_type"] == "expense"

    # Row 2: Pret
    assert items[1]["extracted_merchant"] == "Pret A Manger"
    assert items[1]["extracted_amount_pence"] == 395
    assert items[1]["transaction_type"] == "expense"

    # Row 3: Refund (Income)
    assert items[2]["extracted_merchant"] == "Refund Amazon"
    assert items[2]["extracted_amount_pence"] == 2500
    assert items[2]["transaction_type"] == "income"

    # Row 4: Uber
    assert items[3]["extracted_merchant"] == "Uber Trip"
    assert items[3]["extracted_amount_pence"] == 1850
    assert items[3]["transaction_type"] == "expense"

# -------------------------------------------------------------------------
# 5. Unsupported / Unreadable File Graceful Handling Tests
# -------------------------------------------------------------------------

def test_unsupported_file_preserves_source_and_allows_manual_entry(isolated_db):
    db, tmp_path = isolated_db
    # Arbitrary binary / proprietary file
    binary_payload = b"\x00\x01\x02\x03\x04\x05\x06\x07ProprietaryHeaderBinaryFormatData"
    staging_folder = tmp_path / "staging_receipts"

    res = ingest_unified_file(
        db=db,
        file_content=binary_payload,
        original_filename="receipt_scan.dat",
        staging_dir=staging_folder
    )

    assert res["document_type"] == "unsupported"
    assert len(res["items"]) == 1
    item = res["items"][0]

    # Uncertain fields remain blank
    assert item["extracted_amount_pence"] is None
    assert item["extracted_date"] is None
    assert item["extracted_merchant"] is None
    assert "amount" in item["missing_fields"]
    assert "transaction_date" in item["missing_fields"]

    # Source file was safely preserved
    assert item["temp_file_path"] is not None
    saved_file = DATA_DIR / item["temp_file_path"] if not Path(item["temp_file_path"]).is_absolute() else Path(item["temp_file_path"])
    assert saved_file.exists()
    assert saved_file.read_bytes() == binary_payload

# -------------------------------------------------------------------------
# 6. Uncertain Fields & Foreign Currency Provenance
# -------------------------------------------------------------------------

def test_foreign_currency_does_not_infer_unverified_base_charge(isolated_db):
    db, tmp_path = isolated_db
    # Create GBP account
    acc = Account(
        name="Main Account",
        account_type=AccountType.CURRENT,
        currency="GBP",
        color="#3B82F6",
        is_active=True
    )
    db.add(acc)
    db.commit()

    # Foreign EUR receipt
    ocr_lines = [
        "Cafe de Flore",
        "Paris, France",
        "14/10/2026",
        "TOTAL: €18.50"
    ]
    # Simulate screenshot/receipt extractor with detected EUR
    items = parse_screenshot_transactions(ocr_lines, account_currency="GBP")
    # In Cafe de Flore, EUR 18.50 is found
    assert len(items) >= 1
    eur_item = items[0]
    assert eur_item["currency"] == "EUR"
    assert eur_item["original_amount"] == 18.50

# -------------------------------------------------------------------------
# 7. Unassigned Ordinary Transactions vs Enforced Transfers
# -------------------------------------------------------------------------

def test_unassigned_ordinary_expense_approved_without_account(isolated_db):
    db, tmp_path = isolated_db
    csv_bytes = b"Date,Merchant,Amount\n2026-10-18,Local Corner Shop,15.00\n"

    res = ingest_unified_file(
        db=db,
        file_content=csv_bytes,
        original_filename="expenses.csv",
        target_account_id=None,  # Unassigned
        staging_dir=tmp_path / "staging_receipts"
    )

    item_id = res["items"][0]["id"]
    # Approve directly without assigning account
    tx = approve_staging_item(db, item_id)
    assert tx.id is not None
    assert tx.account_id is None  # Unassigned
    assert tx.amount_pence == 1500
    assert tx.merchant == "Local Corner Shop"

def test_unassigned_transfer_is_rejected(isolated_db):
    db, tmp_path = isolated_db
    stg = StagingItem(
        status=StagingStatus.PENDING,
        extracted_amount_pence=5000,
        extracted_date=datetime.now(timezone.utc),
        extracted_merchant="Transfer between banks",
        suggested_account_id=None,  # Unassigned!
        source_type="statement",
        raw_payload_json=json.dumps({
            "transaction_type": "transfer",
            "destination_account_id": None
        })
    )
    db.add(stg)
    db.commit()

    # Approving an unassigned transfer must fail
    with pytest.raises(ValueError, match="Target account is required for transfer"):
        approve_staging_item(db, stg.id)

# -------------------------------------------------------------------------
# 8. Advisory Duplicate Detection Never Blocks Approval
# -------------------------------------------------------------------------

def test_duplicate_matching_is_advisory_and_does_not_block(isolated_db):
    db, tmp_path = isolated_db
    acc = Account(
        name="Current Account",
        account_type=AccountType.CURRENT,
        currency="GBP",
        color="#3B82F6",
        is_active=True
    )
    db.add(acc)
    db.commit()

    existing_dt = datetime(2026, 10, 15, 12, 0, 0, tzinfo=timezone.utc)
    # Existing ledger transaction
    existing_tx = Transaction(
        transaction_date=existing_dt,
        transaction_type=TransactionType.EXPENSE,
        amount_pence=4500,
        merchant="Tesco Superstore",
        account_id=acc.id
    )
    db.add(existing_tx)
    db.commit()

    # Import duplicate candidate
    dup_csv = b"Date,Merchant,Amount\n2026-10-15,Tesco Superstore,45.00\n"
    res = ingest_unified_file(
        db=db,
        file_content=dup_csv,
        original_filename="tesco_statement.csv",
        target_account_id=acc.id,
        staging_dir=tmp_path / "staging_receipts"
    )

    item = res["items"][0]
    assert item["is_potential_duplicate"] is True
    assert len(item["duplicate_matches"]) == 1
    assert item["duplicate_matches"][0]["id"] == existing_tx.id

    # The user can still approve it without being blocked!
    new_tx = approve_staging_item(db, item["id"])
    assert new_tx.id is not None
    assert new_tx.id != existing_tx.id
    assert new_tx.amount_pence == 4500

# -------------------------------------------------------------------------
# 9. Source File Preservation & Lifecycle
# -------------------------------------------------------------------------

def test_source_file_lifecycle_preserved_in_staging_and_archived_on_approval(isolated_db):
    db, tmp_path = isolated_db
    staging_dir = tmp_path / "staging_receipts"
    archive_dir = tmp_path / "receipts"
    staging_dir.mkdir(parents=True, exist_ok=True)
    archive_dir.mkdir(parents=True, exist_ok=True)

    fake_receipt_img = b"\x89PNG\r\n\x1a\n\x00FakeReceiptDataForTest"
    res = ingest_unified_file(
        db=db,
        file_content=fake_receipt_img,
        original_filename="dinner_receipt.png",
        staging_dir=staging_dir
    )

    item = res["items"][0]
    saved_staged_path = DATA_DIR / item["temp_file_path"] if not Path(item["temp_file_path"]).is_absolute() else Path(item["temp_file_path"])
    assert saved_staged_path.exists()
    assert saved_staged_path.read_bytes() == fake_receipt_img

    # Fill missing fields before approving
    stg_record = db.query(StagingItem).filter(StagingItem.id == item["id"]).first()
    stg_record.extracted_amount_pence = 2850
    stg_record.extracted_date = datetime.now(timezone.utc)
    stg_record.extracted_merchant = "Italian Bistro"
    db.commit()

    # Approve item -> file is safely archived
    tx = approve_staging_item(db, item["id"], archive_dir=archive_dir)
    assert tx.receipt_path is not None
    archived_file = DATA_DIR / tx.receipt_path if not Path(tx.receipt_path).is_absolute() else Path(tx.receipt_path)
    assert archived_file.exists()
    assert archived_file.read_bytes() == fake_receipt_img


# -------------------------------------------------------------------------
# 10. API Endpoints: /import-file and /import-commit Tests
# -------------------------------------------------------------------------

def test_api_import_file_and_commit_flow(tmp_path):
    from fastapi.testclient import TestClient
    from app.main import app
    from app.database import get_db

    db_file = tmp_path / "api_unified.db"
    engine = create_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)

    def override_get_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)

    try:
        # Create an account
        acc_resp = client.post("/api/accounts", json={
            "name": "Checking Account",
            "account_type": "current",
            "starting_balance": 1000.0,
            "currency": "GBP"
        })
        assert acc_resp.status_code == 201
        acc_id = acc_resp.json()["id"]

        # 1. Upload CSV to /api/staging/import-file
        csv_content = b"Date,Merchant,Amount\n2026-10-18,Local Grocery,35.50\n2026-10-19,Coffee Shop,3.80\n"
        upload_resp = client.post(
            "/api/staging/import-file",
            files={"file": ("transactions.csv", csv_content, "text/csv")},
            data={"account_id": str(acc_id)}
        )
        assert upload_resp.status_code == 201
        import_data = upload_resp.json()
        assert import_data["document_type"] == "statement"
        assert len(import_data["items"]) == 2
        batch_id = import_data["batch_id"]

        item1 = import_data["items"][0]
        item2 = import_data["items"][1]
        assert item1["extracted_merchant"] == "Local Grocery"
        assert item1["extracted_amount_pounds"] == 35.50

        # 2. Commit decisions via /api/staging/import-commit with corrections and approve_all
        commit_payload = {
            "batch_id": batch_id,
            "action": "approve_all",
            "items": [
                {
                    "id": item1["id"],
                    "merchant": "Local Organic Grocery",
                    "amount": 35.50,
                    "transaction_date": "2026-10-18T10:00:00Z",
                    "account_id": acc_id,
                    "transaction_type": "expense",
                    "notes": "Verified organic store"
                },
                {
                    "id": item2["id"],
                    "merchant": "Coffee Shop",
                    "amount": 3.80,
                    "transaction_date": "2026-10-19T08:30:00Z",
                    "account_id": acc_id,
                    "transaction_type": "expense"
                }
            ]
        }
        commit_resp = client.post("/api/staging/import-commit", json=commit_payload)
        assert commit_resp.status_code == 200
        commit_result = commit_resp.json()
        assert commit_result["approved_count"] == 2
        assert len(commit_result["transaction_ids"]) == 2

        # 3. Verify transactions exist in ledger
        tx_list_resp = client.get("/api/transactions")
        assert tx_list_resp.status_code == 200
        tx_items = tx_list_resp.json()["items"]
        assert len(tx_items) == 2
        merchants = [t["merchant"] for t in tx_items]
        assert "Local Organic Grocery" in merchants
        assert "Coffee Shop" in merchants

    finally:
        app.dependency_overrides.clear()


# -------------------------------------------------------------------------
# 11. Multi-Row Shared Source-File Lifecycle Tests
# -------------------------------------------------------------------------

def test_multi_row_shared_source_file_lifecycle_with_discard_and_approval(isolated_db):
    """
    Lifecycle test for multi-row imports sharing a single uploaded source file:
    - 3 rows created from 1 source file in staging_receipts.
    - Discarding row 1 must NOT delete the source file while rows 2 & 3 are pending.
    - Approving row 2 copies source to receipts archive and links tx2.
    - Approving row 3 links tx3 to the EXACT SAME archive file (no duplicate copy).
    - As row 3 is the last pending item, the staging copy is cleaned up safely.
    """
    db, tmp_path = isolated_db
    staging_dir = tmp_path / "staging_receipts"
    archive_dir = tmp_path / "receipts"
    staging_dir.mkdir(parents=True, exist_ok=True)
    archive_dir.mkdir(parents=True, exist_ok=True)

    # 1. Create a simulated source file in staging
    fake_screenshot_bytes = b"\x89PNG\r\n\x1a\nMultiRowStatementScreenshotData"
    source_filename = "shared_statement_screenshot.png"
    staging_file_path = staging_dir / source_filename
    staging_file_path.write_bytes(fake_screenshot_bytes)

    rel_staging_path = str(staging_file_path.relative_to(DATA_DIR)) if DATA_DIR in staging_file_path.parents else str(staging_file_path)

    # Create account
    acc = Account(name="Current Account", account_type=AccountType.CURRENT, currency="GBP", color="#3B82F6", is_active=True)
    db.add(acc)
    db.commit()

    now_dt = datetime.now(timezone.utc)

    # Create 3 staging items sharing the exact same temp_file_path
    item1 = StagingItem(
        status=StagingStatus.PENDING,
        extracted_amount_pence=1200,
        extracted_date=now_dt,
        extracted_merchant="Cafe A",
        suggested_account_id=acc.id,
        source_type="statement_screenshot",
        temp_file_path=rel_staging_path,
        raw_payload_json=json.dumps({"transaction_type": "expense"})
    )
    item2 = StagingItem(
        status=StagingStatus.PENDING,
        extracted_amount_pence=2500,
        extracted_date=now_dt,
        extracted_merchant="Store B",
        suggested_account_id=acc.id,
        source_type="statement_screenshot",
        temp_file_path=rel_staging_path,
        raw_payload_json=json.dumps({"transaction_type": "expense"})
    )
    item3 = StagingItem(
        status=StagingStatus.PENDING,
        extracted_amount_pence=3800,
        extracted_date=now_dt,
        extracted_merchant="Bakery C",
        suggested_account_id=acc.id,
        source_type="statement_screenshot",
        temp_file_path=rel_staging_path,
        raw_payload_json=json.dumps({"transaction_type": "expense"})
    )
    db.add_all([item1, item2, item3])
    db.commit()

    # Step 1: Discard Item 1
    discard_success = discard_staging_item(db, item1.id, staging_dir=staging_dir)
    assert discard_success is True
    assert item1.status == StagingStatus.REJECTED

    # Source file MUST still exist in staging because Item 2 and Item 3 are still pending!
    assert staging_file_path.exists(), "Source file was prematurely deleted after discarding row 1 while rows 2 & 3 were still pending!"

    # Step 2: Approve Item 2
    tx2 = approve_staging_item(db, item2.id, archive_dir=archive_dir)
    assert tx2.id is not None
    assert tx2.receipt_path is not None

    archived_file_p = DATA_DIR / tx2.receipt_path if not Path(tx2.receipt_path).is_absolute() else Path(tx2.receipt_path)
    assert archived_file_p.exists()
    assert archived_file_p.read_bytes() == fake_screenshot_bytes

    # Source file MUST still exist in staging because Item 3 is still pending!
    assert staging_file_path.exists(), "Source file was prematurely deleted from staging while row 3 was still pending review!"

    # Step 3: Approve Item 3
    tx3 = approve_staging_item(db, item3.id, archive_dir=archive_dir)
    assert tx3.id is not None
    assert tx3.receipt_path is not None

    # tx2 and tx3 MUST share the EXACT SAME archived file path (zero duplicate files created)
    assert tx2.receipt_path == tx3.receipt_path

    # Verify that only 1 file exists in archive_dir
    archived_files = [f for f in archive_dir.rglob("*.png") if f.is_file()]
    assert len(archived_files) == 1, f"Expected exactly 1 shared archive file, but found {len(archived_files)}"

    # Since Item 3 was the last pending item sharing this source, the staging copy should now be safely cleaned up
    assert not staging_file_path.exists(), "Staging file was not cleaned up after the last pending item was approved"


# -------------------------------------------------------------------------
# 12. Batch Commit Pre-Validation & Atomic Integrity Tests
# -------------------------------------------------------------------------

def test_batch_commit_prevalidation_prevents_partial_commit(tmp_path):
    """
    Verifies that 'Add to Ledger Now' pre-validates all rows and rejects the entire batch
    if any row has an invalid or incomplete state, preventing partial commits.
    """
    from fastapi.testclient import TestClient
    from app.main import app
    from app.database import get_db

    db_file = tmp_path / "atomic_commit.db"
    engine = create_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)

    def override_get_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)

    try:
        # Create an account
        acc_resp = client.post("/api/accounts", json={
            "name": "Main Checking",
            "account_type": "current",
            "starting_balance": 500.0,
            "currency": "GBP"
        })
        acc_id = acc_resp.json()["id"]

        # Stage 2 items via unified import
        csv_bytes = b"Date,Merchant,Amount\n2026-10-20,Valid Merchant,20.00\n2026-10-21,Another Merchant,30.00\n"
        upload_resp = client.post(
            "/api/staging/import-file",
            files={"file": ("stmt.csv", csv_bytes, "text/csv")},
            data={"account_id": str(acc_id)}
        )
        data = upload_resp.json()
        item1_id = data["items"][0]["id"]
        item2_id = data["items"][1]["id"]
        batch_id = data["batch_id"]

        # Attempt to commit where item 1 is valid, but item 2 is set to invalid transfer (no destination account)
        invalid_commit = {
            "batch_id": batch_id,
            "action": "approve_all",
            "items": [
                {
                    "id": item1_id,
                    "merchant": "Valid Merchant",
                    "amount": 20.00,
                    "transaction_date": "2026-10-20T12:00:00Z",
                    "account_id": acc_id,
                    "transaction_type": "expense"
                },
                {
                    "id": item2_id,
                    "merchant": "Bad Transfer",
                    "amount": 30.00,
                    "transaction_date": "2026-10-21T12:00:00Z",
                    "account_id": acc_id,
                    "transaction_type": "transfer",
                    "destination_account_id": None  # Invalid!
                }
            ]
        }

        resp = client.post("/api/staging/import-commit", json=invalid_commit)
        assert resp.status_code == 400
        error_detail = resp.json()["detail"]
        assert "row_errors" in error_detail
        assert any(e["id"] == item2_id for e in error_detail["row_errors"])

        # Check ledger: ZERO transactions were created! (No partial commit!)
        tx_resp = client.get("/api/transactions")
        assert tx_resp.json()["total"] == 0

        # Check staging: both items remain PENDING for user correction
        stg_resp = client.get(f"/api/staging/{item1_id}")
        assert stg_resp.status_code == 200
        assert stg_resp.json()["status"] == "pending"

    finally:
        app.dependency_overrides.clear()


# -------------------------------------------------------------------------
# 13. Ambiguous & Unsupported Extraction Never Silently Approves
# -------------------------------------------------------------------------

def test_ambiguous_and_unsupported_files_never_silently_approve(isolated_db):
    """
    Confirms that unsupported or ambiguous extractions remain available for manual entry,
    and that attempting to approve an item with missing mandatory fields fails safely.
    """
    db, tmp_path = isolated_db
    # Binary file that cannot be parsed
    unsupported_bytes = b"\xff\xfe\xfd\xfcArbitraryBinaryDataWithoutDatesOrAmounts"
    res = ingest_unified_file(
        db=db,
        file_content=unsupported_bytes,
        original_filename="raw_document.bin",
        staging_dir=tmp_path / "staging_receipts"
    )

    assert res["document_type"] == "unsupported"
    item = res["items"][0]
    assert item["extracted_amount_pence"] is None
    assert item["extracted_date"] is None
    assert "amount" in item["missing_fields"]
    assert "transaction_date" in item["missing_fields"]

    # Attempting to approve without completing date and amount must fail with clear ValueError
    with pytest.raises(ValueError, match="Transaction date is required"):
        approve_staging_item(db, item["id"])

    # If user provides date but omits amount, approval still fails
    stg = db.query(StagingItem).filter(StagingItem.id == item["id"]).first()
    stg.extracted_date = datetime.now(timezone.utc)
    db.commit()

    with pytest.raises(ValueError, match="positive base-currency .* transaction amount is required"):
        approve_staging_item(db, item["id"])


# -------------------------------------------------------------------------
# 14. Filename Collision & Content Hash Provenance Tests
# -------------------------------------------------------------------------

def test_two_uploads_same_filename_different_content_point_to_correct_sources(isolated_db):
    """
    Tests that two separate uploads with the exact same generic filename (e.g. 'statement.csv')
    containing different data:
    1. Are archived to distinct, content-hashed files (e.g. {hash}_statement.csv).
    2. Each transaction strictly points to its own correct source file content.
    3. Neither file overwrites or collides with the other.
    """
    db, tmp_path = isolated_db
    staging_dir = tmp_path / "staging_receipts"
    archive_dir = tmp_path / "receipts"
    staging_dir.mkdir(parents=True, exist_ok=True)
    archive_dir.mkdir(parents=True, exist_ok=True)

    acc = Account(name="Main Account", account_type=AccountType.CURRENT, currency="GBP", color="#3B82F6", is_active=True)
    db.add(acc)
    db.commit()

    # Upload 1: October Batch
    content1 = b"Date,Merchant,Amount\n2026-10-10,First Batch October Merchant,10.50\n"
    res1 = ingest_unified_file(
        db=db,
        file_content=content1,
        original_filename="statement.csv",
        target_account_id=acc.id,
        staging_dir=staging_dir
    )
    item1_id = res1["items"][0]["id"]
    tx1 = approve_staging_item(db, item1_id, archive_dir=archive_dir)

    # Upload 2: November Batch with the EXACT SAME generic filename 'statement.csv'
    content2 = b"Date,Merchant,Amount\n2026-11-15,Second Batch November Merchant,25.80\n"
    res2 = ingest_unified_file(
        db=db,
        file_content=content2,
        original_filename="statement.csv",
        target_account_id=acc.id,
        staging_dir=staging_dir
    )
    item2_id = res2["items"][0]["id"]
    tx2 = approve_staging_item(db, item2_id, archive_dir=archive_dir)

    # 1. Verify transactions point to distinct archive paths
    assert tx1.receipt_path is not None
    assert tx2.receipt_path is not None
    assert tx1.receipt_path != tx2.receipt_path, (
        f"Filename collision! Both transactions point to the same path: {tx1.receipt_path}"
    )

    # 2. Verify each transaction points to its own correct content on disk
    file1_on_disk = DATA_DIR / tx1.receipt_path if not Path(tx1.receipt_path).is_absolute() else Path(tx1.receipt_path)
    file2_on_disk = DATA_DIR / tx2.receipt_path if not Path(tx2.receipt_path).is_absolute() else Path(tx2.receipt_path)

    assert file1_on_disk.exists(), f"File 1 missing: {file1_on_disk}"
    assert file2_on_disk.exists(), f"File 2 missing: {file2_on_disk}"

    assert file1_on_disk.read_bytes() == content1
    assert file2_on_disk.read_bytes() == content2

    assert b"First Batch October Merchant" in file1_on_disk.read_bytes()
    assert b"Second Batch November Merchant" in file2_on_disk.read_bytes()


# -------------------------------------------------------------------------
# 11. General Account Matching & Learned Local Associations Tests
# -------------------------------------------------------------------------

def test_general_account_matching_and_last4(isolated_db):
    db, tmp_path = isolated_db
    acc1 = Account(name="Personal American Express", account_type=AccountType.CREDIT_CARD, currency="GBP", color="#002663", is_active=True)
    acc2 = Account(name="Barclays Current 9876", account_type=AccountType.CURRENT, currency="GBP", color="#00AEEF", is_active=True)
    acc3 = Account(name="Revolut GBP", account_type=AccountType.CURRENT, currency="GBP", color="#000000", is_active=True)
    acc_prem = Account(name="Barclays Premium", account_type=AccountType.CURRENT, currency="GBP", is_active=True)
    db.add_all([acc1, acc2, acc3, acc_prem])
    db.commit()

    # Case A: Last-4 digits match with high confidence
    barclays_ocr_lines = [
        "Card ending in 9876",
        "Transactions",
        "Costa Coffee",
        "£3.80"
    ]
    acc_id, acc_name, reason = match_account_from_context(db, barclays_ocr_lines)
    assert acc_id == acc2.id
    assert acc_name == "Barclays Current 9876"
    assert "9876" in reason

    # Case B: Distinctive token match (Revolut)
    revolut_ocr_lines = [
        "Revolut Vault",
        "Activity",
        "£12.00"
    ]
    acc_id, acc_name, reason = match_account_from_context(db, revolut_ocr_lines)
    assert acc_id == acc3.id
    assert acc_name == "Revolut GBP"
    assert "revolut" in reason.lower()

    # Case C: Generic terms alone ('card', 'premium', 'account') do NOT produce a confident match
    generic_lines = ["Premium Card", "Recent Transactions", "£5.00"]
    acc_id, acc_name, reason = match_account_from_context(db, generic_lines)
    assert acc_id is None
    assert acc_name is None
    assert "no confident account match" in reason.lower()

    # Case D: Ambiguous matching between accounts with similar names
    ambig_lines = ["Barclays", "Statement", "£10.00"]
    acc_id, acc_name, reason = match_account_from_context(db, ambig_lines)
    assert acc_id is None
    assert acc_name is None
    assert "Ambiguous" in reason
    assert "Barclays Current 9876" in reason
    assert "Barclays Premium" in reason

def test_learned_account_associations_lifecycle(isolated_db):
    db, tmp_path = isolated_db
    acc_amex = Account(name="Personal American Express", account_type=AccountType.CREDIT_CARD, currency="GBP", is_active=True)
    db.add(acc_amex)
    db.commit()

    card_label = "Alex Avios Amex Premium"
    ocr_lines = [
        "Google Wallet",
        card_label,
        "Activity",
        "Tesco Stores",
        "£14.50"
    ]

    # 1. Before learning: no confirmed association exists, generic match is low confidence or unassigned
    assert get_confirmed_account_associations(db) == {}

    # 2. Ingesting / staging a file does NOT learn an unconfirmed association
    staging_folder = tmp_path / "staging"
    res = ingest_unified_file(
        db=db,
        file_content=b"Mock content",
        original_filename="screenshot.png",
        staging_dir=staging_folder
    )
    # Staging item remains pending; associations must still be empty!
    assert get_confirmed_account_associations(db) == {}

    # 3. Discarding does NOT learn
    stg_id = res["items"][0]["id"]
    discard_staging_item(db, stg_id)
    assert get_confirmed_account_associations(db) == {}

    # 4. Learning occurs ONLY upon explicit user approval with an account assigned
    stg_item = StagingItem(
        status=StagingStatus.PENDING,
        extracted_amount_pence=1450,
        extracted_date=datetime.now(timezone.utc),
        extracted_merchant="Tesco Stores",
        suggested_account_id=acc_amex.id,
        source_type="statement_screenshot",
        raw_payload_json=json.dumps({"extracted_card_label": card_label})
    )
    db.add(stg_item)
    db.commit()

    approve_staging_item(db, stg_item.id, archive_dir=tmp_path / "archive")

    # Now the confirmed association has been learned locally
    associations = get_confirmed_account_associations(db)
    assert len(associations) == 1
    assert "alex avios amex" in list(associations.keys())[0]

    # 5. Subsequent matching for this card label matches immediately with 1.0 confidence!
    acc_id, acc_name, reason = match_account_from_context(db, ocr_lines)
    assert acc_id == acc_amex.id
    assert acc_name == "Personal American Express"
    assert "user-confirmed association" in reason.lower()

    # 6. Management path: inspect and delete the learned association
    listed = list_confirmed_account_associations(db)
    assert len(listed) == 1
    assert listed[0]["account_id"] == acc_amex.id

    deleted = delete_confirmed_account_association(db, card_label)
    assert deleted is True
    assert get_confirmed_account_associations(db) == {}

    # Once deleted, matching falls back to unassigned
    acc_id, acc_name, reason = match_account_from_context(db, ocr_lines)
    assert acc_id is None

# -------------------------------------------------------------------------
# 12. Transaction Direction Detection Tests (Purchases vs Credits/Refunds)
# -------------------------------------------------------------------------

def test_screenshot_direction_detection():
    # 1. Purchase in wallet without sign -> default to expense
    dir1, amb1 = determine_transaction_direction("£14.50", is_neg=False, merchant_text="Tesco Stores", line_text="Tesco Stores £14.50")
    assert dir1 == "expense"
    assert amb1 is False

    # 2. Explicit plus -> income
    dir2, amb2 = determine_transaction_direction("+£25.00", is_neg=False, merchant_text="Amazon", line_text="+£25.00")
    assert dir2 == "income"
    assert amb2 is False

    # 3. Explicit minus -> expense
    dir3, amb3 = determine_transaction_direction("-£12.30", is_neg=True, merchant_text="Boots", line_text="-£12.30")
    assert dir3 == "expense"
    assert amb3 is False

    # 4. Keyword 'refund' -> income
    dir4, amb4 = determine_transaction_direction("£18.00", is_neg=False, merchant_text="Amazon Refund", line_text="Amazon Refund £18.00")
    assert dir4 == "income"
    assert amb4 is False

    # 5. Keyword 'cashback' -> income
    dir5, amb5 = determine_transaction_direction("£5.20", is_neg=False, merchant_text="TopCashback Payout", line_text="TopCashback Payout £5.20")
    assert dir5 == "income"
    assert amb5 is False

    # 6. Ambiguous narrative (e.g. bare "Transfer") -> flags ambiguous for review
    dir6, amb6 = determine_transaction_direction("£50.00", is_neg=False, merchant_text="Transfer", line_text="Transfer £50.00")
    assert amb6 is True

# -------------------------------------------------------------------------
# 13. Approved-History-Driven Category Suggestions Tests
# -------------------------------------------------------------------------

def test_approved_history_driven_category_learning(isolated_db):
    db, tmp_path = isolated_db
    cat_groc = Category(name="Groceries", color="#669c35", default_expense_nature=ExpenseNature.VARIABLE, is_active=True)
    cat_elec = Category(name="Electronics", color="#3B82F6", default_expense_nature=ExpenseNature.VARIABLE, is_active=True)
    db.add_all([cat_groc, cat_elec])
    db.commit()

    # 1. Initial state: vendor with no history is uncategorised (None), never invented
    c_id, c_name, nature, reason = suggest_category_from_history(db, "Blue Star Trading")
    assert c_id is None
    assert c_name is None
    assert nature == ExpenseNature.UNCLASSIFIED
    assert db.query(Category).count() == 2

    # 2. Record approved transaction history
    tx1 = Transaction(
        transaction_date=datetime.now(timezone.utc),
        transaction_type=TransactionType.EXPENSE,
        amount_pence=1500,
        merchant="Blue Star Trading",
        category_id=cat_groc.id,
        expense_nature=ExpenseNature.VARIABLE
    )
    db.add(tx1)
    db.commit()

    # Now exact vendor suggests Groceries
    c_id, c_name, nature, reason = suggest_category_from_history(db, "Blue Star Trading")
    assert c_id == cat_groc.id
    assert c_name == "Groceries"
    assert nature == ExpenseNature.VARIABLE

    # 3. OCR spelling variation and business suffixes match via normalized similarity
    # e.g. 'Blue Star Trading Ltd' or 'Blu Star Trading'
    c_id2, c_name2, _, _ = suggest_category_from_history(db, "Blue Star Trading Ltd")
    assert c_id2 == cat_groc.id

    c_id3, c_name3, _, _ = suggest_category_from_history(db, "Blu Star Trading")
    assert c_id3 == cat_groc.id

    # 4. Conflicting history: vendor categorized into multiple categories
    # Add history for 'Department Store X': 1 entry for Groceries (£15), 1 entry for Electronics (£350)
    tx_dept1 = Transaction(
        transaction_date=datetime.now(timezone.utc),
        transaction_type=TransactionType.EXPENSE,
        amount_pence=1500,
        merchant="Department Store X",
        category_id=cat_groc.id
    )
    tx_dept2 = Transaction(
        transaction_date=datetime.now(timezone.utc),
        transaction_type=TransactionType.EXPENSE,
        amount_pence=35000,
        merchant="Department Store X",
        category_id=cat_elec.id
    )
    db.add_all([tx_dept1, tx_dept2])
    db.commit()

    # If amount matches the £15 groceries pattern: amount disambiguates!
    c_id_amt, c_name_amt, _, reason_amt = suggest_category_from_history(
        db, "Department Store X", amount_pence=1500
    )
    assert c_id_amt == cat_groc.id
    assert "amount pattern" in reason_amt.lower()

    # If amount is unfamiliar or different (£80): history is split -> left uncategorised for review
    c_id_split, _, _, reason_split = suggest_category_from_history(
        db, "Department Store X", amount_pence=8000
    )
    assert c_id_split is None
    assert "conflicting history" in reason_split.lower()

    # 5. Amount alone cannot produce a category
    # Unknown vendor + amount matching past grocery transaction (£15) -> still None!
    c_id_alone, _, _, _ = suggest_category_from_history(
        db, "Completely Unknown Random Vendor", amount_pence=1500
    )
    assert c_id_alone is None

    # 6. Archived/Inactive categories are ignored
    cat_groc.is_active = False
    db.commit()

    c_id_archived, _, _, _ = suggest_category_from_history(db, "Green Grocer Village")
    assert c_id_archived is None  # Excluded because category is archived

# -------------------------------------------------------------------------
# 14. Category ID Persistence and Staging Update & Approval Flow
# -------------------------------------------------------------------------

def test_category_id_persisted_in_staging_update_and_approval(isolated_db):
    db, tmp_path = isolated_db
    cat = Category(name="Groceries", color="#669c35", default_expense_nature=ExpenseNature.VARIABLE, is_active=True)
    acc = Account(name="Personal American Express", account_type=AccountType.CREDIT_CARD, currency="GBP", is_active=True)
    db.add_all([cat, acc])
    db.commit()

    # Ingest a CSV with a transaction
    content = b"Date,Merchant,Amount\n2026-10-18,Sainsbury Local,15.40\n"
    res = ingest_unified_file(
        db=db,
        file_content=content,
        original_filename="card_activity.csv",
        target_account_id=acc.id,
        staging_dir=tmp_path / "staging"
    )

    stg_item = res["items"][0]
    stg_id = stg_item["id"]

    # Update item via update_staging_item passing category_id and overriding nature to FIXED
    updated = update_staging_item(db, stg_id, {
        "category_id": cat.id,
        "expense_nature": ExpenseNature.FIXED
    })
    assert updated.suggested_category_name == "Groceries"
    assert updated.suggested_expense_nature == ExpenseNature.FIXED

    # Approve into permanent ledger
    tx = approve_staging_item(db, stg_id, archive_dir=tmp_path / "archive")
    assert tx.category_id == cat.id
    assert tx.expense_nature == ExpenseNature.FIXED
    assert tx.merchant == "Sainsbury Local"
    assert tx.amount_pence == 1540

# -------------------------------------------------------------------------
# 15. Spatial OCR Layout & Semantic Suggestion Tests
# -------------------------------------------------------------------------

def test_first_transaction_dominos_not_mistaken_for_card_label(isolated_db):
    """
    Verifies that when a screenshot has no card header and the first visible line
    is a merchant like 'Domino's', it is NEVER misidentified as a card/account label.
    """
    db, tmp_path = isolated_db
    acc = Account(name="Personal American Express", account_type=AccountType.CREDIT_CARD, currency="GBP", is_active=True)
    db.add(acc)
    db.commit()

    ocr_lines = [
        "Domino's",
        "13 Oct",
        "£27.98",
        "Cannon Street Station",
        "7 Oct",
        "£10.00"
    ]

    cand_labels, last_4 = extract_card_or_account_clues(
        ocr_lines=ocr_lines,
        active_account_names=[acc.name]
    )
    assert cand_labels == [], f"Expected no card labels, but got {cand_labels}"
    assert last_4 is None

    matched_id, matched_name, reason = match_account_from_context(
        db=db,
        ocr_lines=ocr_lines
    )
    assert matched_id is None
    assert matched_name is None

def test_ten_transaction_rows_spatial_layout_association(isolated_db):
    """
    Verifies that 10 transaction rows across a 2-column mobile screenshot retain their
    exact date, merchant, and amount associations via 2D spatial window grouping,
    even when input elements are delivered out-of-order or in separate column blocks.
    """
    ten_records = [
        ("Domino's", "13 Oct", "£27.98", 2798),
        ("Bromley Sports Club", "16 Oct", "£4.40", 440),
        ("Cannon Street Station", "7 Oct", "£10.00", 1000),
        ("SE BICKLEY STATION SST", "70ct", "£10.00", 1000),  # OCR typo: 70ct -> 7 Oct
        ("Bluewater Shopping Centre", "2 Oct", "£20.00", 2000),
        ("Domino's", "26 Sept", "£32.58", 3258),
        ("VASANTHA VILAS", "26 Sept", "£24.98", 2498),
        ("Green Roof Cafe", "16 Sept", "£4.95", 495),
        ("COVENTRY TAXI DRIVER", "17 Aug", "£26.40", 2640),
        ("Tesco Express", "10 Aug", "£12.50", 1250)
    ]

    elements = []
    # Build spatial observations for 10 rows
    for i, (m, d, a_str, _) in enumerate(ten_records):
        y = 0.05 + 0.09 * i
        # Merchant (middle-left column)
        elements.append(OCRElement(
            text=m, confidence=0.98,
            bbox=BoundingBox(top_y=y, bot_y=y + 0.025, left_x=0.25, right_x=0.60, width=0.35, height=0.025)
        ))
        # Date (subtitle under merchant)
        elements.append(OCRElement(
            text=d, confidence=0.95,
            bbox=BoundingBox(top_y=y + 0.028, bot_y=y + 0.045, left_x=0.25, right_x=0.35, width=0.10, height=0.017)
        ))
        # Amount (right column)
        elements.append(OCRElement(
            text=a_str, confidence=0.99,
            bbox=BoundingBox(top_y=y, bot_y=y + 0.025, left_x=0.80, right_x=0.92, width=0.12, height=0.025)
        ))

    # Deliver elements shuffled (simulating non-linear Vision OCR reading blocks)
    import random
    shuffled = list(elements)
    random.seed(123)
    random.shuffle(shuffled)

    parsed_rows = parse_screenshot_transactions_spatial(shuffled, "GBP")
    assert len(parsed_rows) == 10, f"Expected 10 rows, got {len(parsed_rows)}"

    for idx, row in enumerate(parsed_rows):
        exp_m, exp_d, exp_a, exp_pence = ten_records[idx]
        assert row["extracted_merchant"] == exp_m, f"Row {idx+1} merchant mismatch: expected {exp_m}, got {row['extracted_merchant']}"
        assert row["extracted_amount_pence"] == exp_pence, f"Row {idx+1} amount mismatch: expected {exp_pence}, got {row['extracted_amount_pence']}"
        assert row["extracted_date"] is not None
        assert row["date_uncertain"] is False
        assert row["merchant_uncertain"] is False

    # Check specific critical rows
    assert parsed_rows[0]["extracted_merchant"] == "Domino's"
    assert parsed_rows[0]["extracted_amount_pence"] == 2798
    assert parsed_rows[8]["extracted_merchant"] == "COVENTRY TAXI DRIVER"
    assert parsed_rows[8]["extracted_amount_pence"] == 2640

def test_poor_ocr_or_ambiguous_layout_flagged_uncertain(isolated_db):
    """
    Verifies that ambiguous layout or missing fields are explicitly flagged as uncertain
    rather than shifting data across rows or guessing.
    """
    elements = [
        # Amount 1 with no merchant
        OCRElement(
            text="£15.00", confidence=0.99,
            bbox=BoundingBox(top_y=0.10, bot_y=0.125, left_x=0.80, right_x=0.92, width=0.12, height=0.025)
        ),
        # Amount 2 with low-confidence noise merchant
        OCRElement(
            text="£25.00", confidence=0.99,
            bbox=BoundingBox(top_y=0.30, bot_y=0.325, left_x=0.80, right_x=0.92, width=0.12, height=0.025)
        ),
        OCRElement(
            text="??", confidence=0.30,
            bbox=BoundingBox(top_y=0.30, bot_y=0.325, left_x=0.25, right_x=0.30, width=0.05, height=0.025)
        )
    ]

    rows = parse_screenshot_transactions_spatial(elements, "GBP")
    assert len(rows) == 2
    # Row 1 has no merchant -> flagged uncertain
    assert rows[0]["extracted_merchant"] is None
    assert rows[0]["merchant_uncertain"] is True
    # Row 2 has low confidence / 2-char noise -> flagged uncertain
    assert rows[1]["merchant_uncertain"] is True

def test_coventry_taxi_driver_semantic_suggestion_without_hardcoded_rule(isolated_db):
    """
    Verifies that 'COVENTRY TAXI DRIVER' receives a Transport category suggestion
    via on-device local semantic embeddings without any merchant-specific hardcoded keyword rules.
    Also verifies that an uncertain vendor stays uncategorised.
    """
    db, tmp_path = isolated_db
    cat_transport = Category(name="Transport", is_active=True, default_expense_nature=ExpenseNature.VARIABLE)
    cat_groceries = Category(name="Groceries", is_active=True, default_expense_nature=ExpenseNature.VARIABLE)
    cat_dining = Category(name="Dining Out", is_active=True, default_expense_nature=ExpenseNature.VARIABLE)
    cat_entertainment = Category(name="Entertainment", is_active=True, default_expense_nature=ExpenseNature.VARIABLE)
    db.add_all([cat_transport, cat_groceries, cat_dining, cat_entertainment])
    db.commit()

    # 1. Semantic suggestion for COVENTRY TAXI DRIVER
    cid, cname, nature, reason = suggest_category_from_history(db, "COVENTRY TAXI DRIVER")
    emb = get_local_semantic_embedding()
    if emb is not None:
        # On macOS with Apple NaturalLanguage available, Transport is ranked #1 with affinity
        assert cid == cat_transport.id
        assert cname == "Transport"
        assert nature == ExpenseNature.VARIABLE
        assert "semantic" in reason.lower()
    else:
        # On platforms without the framework, must stay uncategorised (no hardcoded guessing)
        assert cid is None

    # 2. Uncertain / low-affinity vendor stays uncategorised
    cid_none, cname_none, _, reason_none = suggest_category_from_history(db, "XYZ99 GLOBAL VENTURES")
    assert cid_none is None
    assert cname_none is None

def test_no_network_or_hosted_ai_dependency_in_import_path():
    """
    AST audit of all importer and OCR modules to guarantee 100% offline local processing.
    """
    import ast
    files = [
        "app/core/unified_importer.py",
        "app/core/staging.py",
        "app/api/staging.py",
        "app/ocr/apple_vision.py",
        "app/ocr/base.py",
        "app/ocr/fallback.py",
        "app/vision_parser.py"
    ]
    disallowed = {"requests", "httpx", "urllib", "http.client", "socket", "aiohttp", "openai", "anthropic", "boto3", "google.generativeai"}
    for file_path in files:
        with open(file_path, "r", encoding="utf-8") as f:
            tree = ast.parse(f.read(), filename=file_path)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    for d in disallowed:
                        assert not (alias.name == d or alias.name.startswith(d + ".")), f"Disallowed import {alias.name} found in {file_path}"
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                for d in disallowed:
                    assert not (mod == d or mod.startswith(d + ".")), f"Disallowed from-import {mod} found in {file_path}"


# -------------------------------------------------------------------------
# 16. Synthetic Hair Studio Receipt Regression Suite (Account & Category Isolation)
# -------------------------------------------------------------------------

HEADMASTERS_RECEIPT_OCR_LINES = [
    "SYNTHETIC HAIR",
    "Example Hair Studio",
    "Creative, Modern, Confidence-Boosting Hair",
    "01632 960123",
    "MID: ******6590",
    "TID: ****6927",
    "AID: A000000025010801",
    "RECEIPT NO: 31232",
    "APP SEQ: 00",
    "TOTAL £ 92.00",
    "AUTH CODE: 842262",
    "RESPONSE CODE: 00",
    "CONTACTLESS",
    "**CARDHOLDER COPY**",
    "AMERICAN EXPRESS",
    "***********4321",
    "PLEASE RETAIN RECEIPTS"
]

def test_headmasters_ocr_clue_extraction_filters_terminal_noise():
    """
    Regression Test:
    Ensures MID, TID, AID, AUTH CODE, and receipt numbers are NEVER treated as card labels.
    Ensures payment method 'AMERICAN EXPRESS' and last-4 '4321' are accurately extracted.
    """
    cand_labels, last_4 = extract_card_or_account_clues(
        ocr_lines=HEADMASTERS_RECEIPT_OCR_LINES,
        active_account_names=["Jordan American Express", "Taylor American Express"],
        merchant_name="Example Hair Studio"
    )

    # Must extract AMERICAN EXPRESS and last 4 '4321'
    assert cand_labels == ["AMERICAN EXPRESS"], f"Expected ['AMERICAN EXPRESS'], got {cand_labels}"
    assert last_4 == "4321", f"Expected '4321', got {last_4}"

    # Must NOT extract terminal or merchant identifiers
    for noise in ["MID", "TID", "PID", "AID", "AUTH", "6590", "6927", "31232", "842262", "SYNTHETIC"]:
        assert not any(noise.lower() in c.lower() for c in cand_labels), f"Noise '{noise}' found in card candidates: {cand_labels}"
        assert last_4 != noise

def test_headmasters_account_matching_single_amex(isolated_db):
    """
    When only one American Express account exists, matches unambiguously with distinctive token evidence.
    """
    db, tmp_path = isolated_db
    amex_acc = Account(name="Personal American Express", account_type=AccountType.CREDIT_CARD, currency="GBP", is_active=True)
    db.add(amex_acc)
    db.commit()

    matched_id, matched_name, reason = match_account_from_context(
        db=db,
        ocr_lines=HEADMASTERS_RECEIPT_OCR_LINES,
        merchant_name="Example Hair Studio"
    )

    assert matched_id == amex_acc.id
    assert matched_name == "Personal American Express"
    assert "matched card 'american express'" in reason.lower()

def test_headmasters_account_matching_ambiguous_dual_amex(isolated_db):
    """
    When two Amex accounts exist and neither contains 4321, flags ambiguity and leaves unassigned.
    """
    db, tmp_path = isolated_db
    acc_jordan = Account(name="Jordan American Express", account_type=AccountType.CREDIT_CARD, currency="GBP", is_active=True)
    acc_taylor = Account(name="Taylor American Express", account_type=AccountType.CREDIT_CARD, currency="GBP", is_active=True)
    db.add_all([acc_jordan, acc_taylor])
    db.commit()

    matched_id, matched_name, reason = match_account_from_context(
        db=db,
        ocr_lines=HEADMASTERS_RECEIPT_OCR_LINES,
        merchant_name="Example Hair Studio"
    )

    assert matched_id is None
    assert matched_name is None
    assert "ambiguous match" in reason.lower()
    assert "jordan american express" in reason.lower()
    assert "taylor american express" in reason.lower()

def test_headmasters_account_matching_account_with_last_4_in_name(isolated_db):
    """
    When account name explicitly contains the card's last-4 digits ('4321'), matches confidently.
    """
    db, tmp_path = isolated_db
    acc_jordan_4321 = Account(name="Jordan Amex 4321", account_type=AccountType.CREDIT_CARD, currency="GBP", is_active=True)
    acc_taylor_8765 = Account(name="Taylor Amex 8765", account_type=AccountType.CREDIT_CARD, currency="GBP", is_active=True)
    db.add_all([acc_jordan_4321, acc_taylor_8765])
    db.commit()

    matched_id, matched_name, reason = match_account_from_context(
        db=db,
        ocr_lines=HEADMASTERS_RECEIPT_OCR_LINES,
        merchant_name="Example Hair Studio"
    )

    assert matched_id == acc_jordan_4321.id
    assert matched_name == "Jordan Amex 4321"
    assert "4321" in reason

def test_headmasters_user_confirmed_association_learning_and_profile_isolation(isolated_db):
    """
    Proves that:
    1. Before user confirmation, dual Amex accounts produce an ambiguous match.
    2. User confirmation for 'AMERICAN EXPRESS' ending in '4321' is saved locally to that profile.
    3. Future imports of Amex 4321 in that profile immediately match the confirmed account.
    4. Amex receipts with different card numbers do NOT wrongly match.
    5. A separate isolated profile database does NOT receive this association.
    """
    db, tmp_path = isolated_db
    acc_jordan = Account(name="Jordan American Express", account_type=AccountType.CREDIT_CARD, currency="GBP", is_active=True)
    acc_taylor = Account(name="Taylor American Express", account_type=AccountType.CREDIT_CARD, currency="GBP", is_active=True)
    db.add_all([acc_jordan, acc_taylor])
    db.commit()

    # 1. Before confirmation: ambiguous
    mid_before, _, _ = match_account_from_context(db=db, ocr_lines=HEADMASTERS_RECEIPT_OCR_LINES)
    assert mid_before is None

    # 2. User confirms Jordan American Express (acc_jordan.id) during review
    save_confirmed_account_association(db, "AMERICAN EXPRESS", acc_jordan.id, last_4="4321")

    # 3. Future import with Amex 4321 now resolves to Jordan American Express
    mid_after, mname_after, reason_after = match_account_from_context(db=db, ocr_lines=HEADMASTERS_RECEIPT_OCR_LINES)
    assert mid_after == acc_jordan.id
    assert mname_after == "Jordan American Express"
    assert "user-confirmed" in reason_after.lower()

    # 4. Amex receipt with different card number (e.g. 9999) remains ambiguous rather than falsely routing to acc_jordan
    other_lines = list(HEADMASTERS_RECEIPT_OCR_LINES)
    other_lines[15] = "***********9999"
    mid_diff, _, reason_diff = match_account_from_context(db=db, ocr_lines=other_lines)
    assert mid_diff is None
    assert "ambiguous" in reason_diff.lower()

    # 5. In a separate isolated database (simulating another profile), no association exists
    db_file_2 = tmp_path / "second_profile.db"
    engine_2 = create_engine(f"sqlite:///{db_file_2}")
    Base.metadata.create_all(engine_2)
    SessionLocal_2 = sessionmaker(bind=engine_2)
    db_2 = SessionLocal_2()
    try:
        acc_other_jordan = Account(name="Jordan American Express", account_type=AccountType.CREDIT_CARD, currency="GBP", is_active=True)
        acc_other_taylor = Account(name="Taylor American Express", account_type=AccountType.CREDIT_CARD, currency="GBP", is_active=True)
        db_2.add_all([acc_other_jordan, acc_other_taylor])
        db_2.commit()

        mid_profile_2, _, reason_profile_2 = match_account_from_context(db=db_2, ocr_lines=HEADMASTERS_RECEIPT_OCR_LINES)
        assert mid_profile_2 is None
        assert "ambiguous" in reason_profile_2.lower()
    finally:
        db_2.close()

def test_headmasters_category_suggestion_from_receipt_context_hair(isolated_db):
    """
    Ensures 'Hair' from the tagline suggests the user's hair-related category:
    'C8: Parlour, Hair Cut, Gym, Massage, Glasses' via context token matching
    without ANY vendor-specific rule for Example Hair Studio.
    """
    db, tmp_path = isolated_db
    cat_hair = Category(name="C8: Parlour, Hair Cut, Gym, Massage, Glasses", is_active=True, default_expense_nature=ExpenseNature.VARIABLE)
    cat_groceries = Category(name="Groceries", is_active=True, default_expense_nature=ExpenseNature.VARIABLE)
    cat_transport = Category(name="Transport", is_active=True, default_expense_nature=ExpenseNature.VARIABLE)
    db.add_all([cat_hair, cat_groceries, cat_transport])
    db.commit()

    cid, cname, nature, reason = suggest_category_from_history(
        db=db,
        merchant="Example Hair Studio",
        amount_pence=9200,
        ocr_lines=HEADMASTERS_RECEIPT_OCR_LINES
    )

    assert cid == cat_hair.id
    assert cname == "C8: Parlour, Hair Cut, Gym, Massage, Glasses"
    assert "receipt context" in reason.lower()
    assert "hair" in reason.lower()

def test_headmasters_category_suggestion_via_category_description(isolated_db):
    """
    Ensures that when a category is named generically ('Personal Care'), a user-defined description
    containing keywords (e.g. 'Hair, haircuts, salon, grooming') enables matching from receipt context.
    """
    from app.core.categories import save_category_description
    db, tmp_path = isolated_db
    cat_personal = Category(name="Personal Care", is_active=True, default_expense_nature=ExpenseNature.VARIABLE)
    cat_groceries = Category(name="Groceries", is_active=True, default_expense_nature=ExpenseNature.VARIABLE)
    db.add_all([cat_personal, cat_groceries])
    db.commit()

    # Save description in profile metadata
    save_category_description(db, cat_personal.id, "Hair, haircuts, styling, salon, grooming")

    cid, cname, nature, reason = suggest_category_from_history(
        db=db,
        merchant="Example Hair Studio",
        amount_pence=9200,
        ocr_lines=HEADMASTERS_RECEIPT_OCR_LINES
    )

    assert cid == cat_personal.id
    assert cname == "Personal Care"
    assert "category description" in reason.lower()
    assert "hair" in reason.lower()

def test_category_suggestion_ambiguity_and_low_confidence_safeguards(isolated_db):
    """
    1. If two categories tie with similar confidence on receipt context tokens, flags ambiguity.
    2. If vendor and context have no matching evidence, stays uncategorised (no hallucinated guess).
    """
    db, tmp_path = isolated_db
    cat1 = Category(name="Hair Styling", is_active=True)
    cat2 = Category(name="Hair Salon", is_active=True)
    cat_groceries = Category(name="Groceries", is_active=True)
    db.add_all([cat1, cat2, cat_groceries])
    db.commit()

    # 1. Ambiguous context match between Hair Styling and Hair Salon
    cid_amb, cname_amb, _, reason_amb = suggest_category_from_history(
        db=db,
        merchant="Example Hair Studio",
        ocr_lines=HEADMASTERS_RECEIPT_OCR_LINES
    )
    assert cid_amb is None
    assert cname_amb is None
    assert "ambiguous" in reason_amb.lower()

    # 2. No matching evidence stays uncategorised
    random_lines = ["UNKNOWN CORP", "10 Oct 2026", "TOTAL £50.00", "INV-999"]
    cid_none, cname_none, _, reason_none = suggest_category_from_history(
        db=db,
        merchant="UNKNOWN CORP",
        ocr_lines=random_lines
    )
    assert cid_none is None
    assert cname_none is None

def test_confirmed_associations_read_is_strictly_non_mutating(isolated_db):
    """
    Verifies that calling get_confirmed_account_associations:
    1. Filters out corrupt terminal keys ('mid') in-memory during matching.
    2. Does NOT mutate or delete the raw setting in system_settings during a read.
    3. Explicit cleanup_invalid_account_associations cleanly prunes the corrupt key when invoked.
    """
    from app.core.backup import get_system_setting, set_system_setting
    from app.core.unified_importer import (
        ACCOUNT_ALIASES_SETTING_KEY, cleanup_invalid_account_associations,
        get_raw_confirmed_account_associations
    )

    db, tmp_path = isolated_db
    # Seed raw setting with both corrupt 'mid' and valid 'amex 4321'
    initial_raw = {
        "mid": 11,
        "amex 4321": 11
    }
    set_system_setting(db, ACCOUNT_ALIASES_SETTING_KEY, json.dumps(initial_raw))

    # 1. Read through get_confirmed_account_associations
    filtered = get_confirmed_account_associations(db)
    assert "mid" not in filtered
    assert filtered.get("amex 4321") == 11

    # 2. Verify raw database value was NOT mutated by read
    raw_after_read = get_system_setting(db, ACCOUNT_ALIASES_SETTING_KEY)
    raw_dict_after = json.loads(raw_after_read)
    assert "mid" in raw_dict_after, "Read operation mutated system_settings! It must be strictly non-mutating."
    assert raw_dict_after["mid"] == 11

    # 3. Explicit cleanup action prunes 'mid'
    pruned = cleanup_invalid_account_associations(db)
    assert "mid" in pruned

    # 4. Now system_settings has 'mid' removed
    cleaned_raw = json.loads(get_system_setting(db, ACCOUNT_ALIASES_SETTING_KEY))
    assert "mid" not in cleaned_raw
    assert cleaned_raw.get("amex 4321") == 11

def test_custom_issuer_matching_without_static_card_schemes(isolated_db):
    """
    Proves that account matching does not rely on a static list of card schemes
    (American Express, Visa, Mastercard). Any arbitrary issuer (e.g. Cotswold Community Bank)
    is recognized from the adjacent structural line and matched against active accounts.
    """
    db, tmp_path = isolated_db
    cotswold_acc = Account(name="Cotswold Community Bank Current", account_type=AccountType.CURRENT, currency="GBP", is_active=True)
    db.add(cotswold_acc)
    db.commit()

    custom_receipt_lines = [
        "COTSWOLD ORGANIC BAKERY",
        "12 HIGH STREET",
        "TOTAL: £14.50",
        "COTSWOLD COMMUNITY BANK",
        "************9876",
        "THANK YOU FOR SHOPPING"
    ]

    cand_labels, last_4 = extract_card_or_account_clues(
        ocr_lines=custom_receipt_lines,
        active_account_names=[cotswold_acc.name],
        merchant_name="COTSWOLD ORGANIC BAKERY"
    )

    assert "COTSWOLD COMMUNITY BANK" in cand_labels
    assert last_4 == "9876"

    matched_id, matched_name, reason = match_account_from_context(
        db=db,
        ocr_lines=custom_receipt_lines,
        merchant_name="COTSWOLD ORGANIC BAKERY"
    )

    assert matched_id == cotswold_acc.id
    assert matched_name == "Cotswold Community Bank Current"
    assert "cotswold" in reason.lower()


# -------------------------------------------------------------------------
# 16. Multi-Item Retail Receipt Classification & Settlement Total Extraction
# -------------------------------------------------------------------------

def test_multi_item_retail_receipt_stages_single_expense_with_final_payable_amount(isolated_db, monkeypatch):
    """
    Regression test for multi-item retail receipts with:
    - 15+ product lines with 8-digit SKU codes and right-aligned prices
    - Pre-discount subtotal ('Balance before Saving £47.95')
    - Loyalty discount ('£10 off loyalty reward £10.00')
    - Final payable ('Balance to Pay £37.95') and tender ('Card Tendered £37.95')
    - Bottom savings summary ('Your total saving today is £10.00')
    - Thermal receipt OCR misreading some '£' symbols as '€'
    - Card terminal metadata ('CREDIT CARD', '****0411', 'CARDHOLDER COPY')

    Verifies:
    1. Document is classified as 'receipt' (never 'statement_screenshot').
    2. Exactly ONE staged expense candidate is created (item rows do not become separate transactions).
    3. Amount is £37.95 (3795 pence), NOT £47.95 (subtotal) and NOT £10.00 (saving).
    4. Thermal '€' OCR misreads are resolved to GBP via document-level GBP/VAT evidence.
    """
    from app.ocr.base import ReceiptParseResult, extract_receipt_fields_from_lines
    from app.core.staging import OCRFactory

    db, tmp_path = isolated_db
    acc1 = Account(name="Primary Card A", account_type=AccountType.CREDIT_CARD, currency="GBP", is_active=True)
    acc2 = Account(name="Secondary Card B", account_type=AccountType.CREDIT_CARD, currency="GBP", is_active=True)
    cat_fees = Category(name="Credit Card Fees", is_active=True, default_expense_nature=ExpenseNature.VARIABLE)
    cat_groceries = Category(name="Groceries & Food", is_active=True, default_expense_nature=ExpenseNature.VARIABLE)
    db.add_all([acc1, acc2, cat_fees, cat_groceries])
    db.commit()

    # Construct 2D spatial OCR elements where top of receipt is y=0.05 down to y=0.90 (AppleVision normalized top-down)
    raw_rows = [
        (0.05, "HIGH STREET FOODHALL", None),
        (0.08, "124 HIGH STREET LONDON", None),
        (0.11, "VAT REG NO. GB 123 4567 89", None),
        (0.15, "08341120 ORGANIC MILK", "£1.65"),
        (0.18, "29104412 SOURDOUGH LOAF", "€2.40"),
        (0.21, "71829301 FREE RANGE EGGS", "£3.10"),
        (0.24, "55412098 ROAST CHICKEN", "€8.50"),
        (0.27, "00918273 OLIVE OIL 500ML", "£7.25"),
        (0.30, "44192837 FRESH BERRIES", "€4.00"),
        (0.33, "99182736 CHEDDAR CHEESE", "£3.85"),
        (0.36, "33192844 SALMON FILLETS", "€6.50"),
        (0.39, "11293847 PASTA SAUCE", "£2.70"),
        (0.42, "66543210 GROUND COFFEE", "€5.00"),
        (0.45, "77889900 DARK CHOCOLATE", "£3.00"),
        (0.50, "Balance before Saving", "£47.95"),
        (0.54, "£10 off loyalty reward**", "€10.00"),
        (0.58, "Balance to Pay", "£37.95"),
        (0.62, "Card Tendered", "€37.95"),
        (0.67, "CREDIT CARD", None),
        (0.70, "************0411", None),
        (0.73, "19 OCT 2026 14:22", None),
        (0.76, "AUTH CODE: 084129", None),
        (0.79, "AID: A000000025010801", None),
        (0.82, "CARDHOLDER COPY", None),
        (0.86, "Your total saving today is", "€10.00"),
        (0.90, "PLEASE RETAIN FOR YOUR RECORDS", None),
    ]

    ocr_elements = []
    raw_lines = []
    for y_val, left_text, right_text in raw_rows:
        ocr_elements.append(
            OCRElement(
                text=left_text,
                confidence=0.95,
                bbox=BoundingBox(top_y=y_val - 0.01, bot_y=y_val + 0.01, left_x=0.05, right_x=0.60, width=0.55, height=0.02)
            )
        )
        raw_lines.append(left_text)
        if right_text:
            ocr_elements.append(
                OCRElement(
                    text=right_text,
                    confidence=0.95,
                    bbox=BoundingBox(top_y=y_val - 0.01, bot_y=y_val + 0.01, left_x=0.78, right_x=0.93, width=0.15, height=0.02)
                )
            )
            raw_lines.append(right_text)

    extracted = extract_receipt_fields_from_lines(raw_lines, ocr_elements)

    assert extracted["amount_pence"] == 3795
    assert extracted["amount_uncertain"] is False
    assert extracted["detected_currency"] == "GBP"
    assert extracted["merchant"] == "HIGH STREET FOODHALL"
    assert extracted["transaction_date"] is not None
    assert extracted["transaction_date"].year == 2026
    assert extracted["transaction_date"].month == 10
    assert extracted["transaction_date"].day == 19

    class DummyReceiptParser:
        def recognize_text_with_layout(self, image_path):
            return ocr_elements

        def parse_receipt(self, image_path, tz_str=None):
            return ReceiptParseResult(
                success=True,
                confidence=0.95,
                merchant=extracted["merchant"],
                transaction_date=extracted["transaction_date"],
                amount_pence=extracted["amount_pence"],
                original_amount=extracted["original_amount"],
                detected_currency=extracted["detected_currency"],
                raw_lines=raw_lines,
                ocr_elements=ocr_elements,
                amount_uncertain=extracted["amount_uncertain"],
                date_uncertain=extracted["date_uncertain"],
                merchant_uncertain=extracted["merchant_uncertain"],
            )

    monkeypatch.setattr(OCRFactory, "get_parser", lambda: DummyReceiptParser())

    fake_jpeg = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00H\x00H\x00\x00\xff\xdb\x00C\x00"
    res = ingest_unified_file(
        db=db,
        file_content=fake_jpeg,
        original_filename="retail_receipt.jpg",
        staging_dir=tmp_path / "staging_receipts"
    )

    assert res["document_type"] == "receipt"
    assert len(res["items"]) == 1, f"Expected 1 receipt candidate, got {len(res['items'])}"
    item = res["items"][0]
    assert item["extracted_amount_pence"] == 3795
    assert item["extracted_amount_pounds"] == 37.95
    assert item["extracted_merchant"] == "HIGH STREET FOODHALL"
    assert item["transaction_type"] == "expense"
    assert item["currency"] == "GBP"
    assert item["currency_conflict"] is False
    # Ensure 'CREDIT CARD' terminal line did NOT trigger a false category match to 'Credit Card Fees'
    assert item["suggested_category_id"] != cat_fees.id
    assert item["suggested_category_id"] == cat_groceries.id


def test_ambiguous_receipt_without_total_produces_single_uncertain_candidate(isolated_db, monkeypatch):
    """
    When a receipt image has multiple item prices and receipt headers/metadata
    but the bottom total/payable section is missing or unreadable, the importer must:
    1. Classify the document as a single 'receipt' (not split items into a batch).
    2. Stage ONE candidate with extracted_amount_pence=None and 'amount' in missing_fields,
       rather than guessing max(all_amounts) or creating multiple false rows.
    """
    from app.ocr.base import ReceiptParseResult, extract_receipt_fields_from_lines
    from app.core.staging import OCRFactory

    db, tmp_path = isolated_db
    raw_lines = [
        "LOCAL HARDWARE STORE",
        "VAT REG NO GB 987 6543 21",
        "20 OCT 2026 11:15",
        "01928374 PAINT BRUSH SET £8.99",
        "09182736 SANDPAPER PACK £4.50",
        "05647382 WOOD PRIMER 1L £14.25",
        "CARDHOLDER COPY",
        "AUTH CODE 77123",
    ]
    ocr_elements = [
        OCRElement(
            text=line,
            confidence=0.9,
            bbox=BoundingBox(top_y=0.05 + idx * 0.08, bot_y=0.08 + idx * 0.08, left_x=0.05, right_x=0.85, width=0.8, height=0.03)
        )
        for idx, line in enumerate(raw_lines)
    ]

    extracted = extract_receipt_fields_from_lines(raw_lines, ocr_elements)
    assert extracted["amount_pence"] is None
    assert extracted["amount_uncertain"] is True

    class DummyTornReceiptParser:
        def recognize_text_with_layout(self, image_path):
            return ocr_elements

        def parse_receipt(self, image_path, tz_str=None):
            return ReceiptParseResult(
                success=True,
                confidence=0.85,
                merchant=extracted["merchant"],
                transaction_date=extracted["transaction_date"],
                amount_pence=extracted["amount_pence"],
                original_amount=extracted["original_amount"],
                detected_currency=extracted["detected_currency"],
                raw_lines=raw_lines,
                ocr_elements=ocr_elements,
                amount_uncertain=extracted["amount_uncertain"],
                date_uncertain=extracted["date_uncertain"],
                merchant_uncertain=extracted["merchant_uncertain"],
            )

    monkeypatch.setattr(OCRFactory, "get_parser", lambda: DummyTornReceiptParser())

    fake_jpeg = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00H\x00H\x00\x00\xff\xdb\x00C\x00"
    res = ingest_unified_file(
        db=db,
        file_content=fake_jpeg,
        original_filename="torn_receipt.jpg",
        staging_dir=tmp_path / "staging_receipts"
    )

    assert res["document_type"] == "receipt"
    assert len(res["items"]) == 1
    item = res["items"][0]
    assert item["extracted_amount_pence"] is None
    assert "amount" in item["missing_fields"]
    assert item["extracted_merchant"] == "LOCAL HARDWARE STORE"


def test_receipt_discounts_cash_tender_and_change_due_selects_payable_total():
    """
    Verifies that when a receipt shows Subtotal (£62.00), Discount (-£12.00),
    Total to Pay (£50.00), Cash Tendered (£60.00), and Change Due (£10.00),
    the extractor selects £50.00 (5000 pence) rather than the £62.00 subtotal
    or £60.00 cash tendered.
    """
    from app.ocr.base import extract_receipt_fields_from_lines

    lines = [
        "CITY BOOKSHOP LTD",
        "18/10/2026",
        "HARDCOVER NOVEL £22.00",
        "ART HISTORY ATLAS £40.00",
        "Subtotal £62.00",
        "Member Voucher Discount -£12.00",
        "Total to Pay £50.00",
        "Cash Tendered £60.00",
        "Change Due £10.00",
        "Total Saving Today £12.00",
    ]
    res = extract_receipt_fields_from_lines(lines)
    assert res["amount_pence"] == 5000
    assert res["amount_uncertain"] is False
    assert res["detected_currency"] == "GBP"


def test_receipt_card_pan_vs_split_mid_tid_and_timestamp_extraction(isolated_db, monkeypatch):
    """
    Regression test for multi-element POS receipt layout where:
    - Top of receipt has low-confidence/lowercase reverse thermal bleed-through ('evol voy 2p') before 'ACME MART'.
    - Settlement block has 'Balance before Saving £47.95', '**£10 off with Loyalty** -£10.00',
      'Balance to Pay £37.95', and 'Card Tendered £37.95'.
    - POS block has 'AMEX CREDIT®', split elements ('TID: ****9749', '*******0411', 'MID:'),
      and ('• 0050', 'AUTH:', 'CARD: 370000XXXXX4242 ot').
    - Bottom footer has '23/10/26 17:31' alongside a barcode string '05866119 75988 715 4747'.
    Verifies:
    1. Merchant is 'ACME MART' (thermal bleed-through ignored).
    2. Final amount is 3795 pence (£37.95), subtotal is 4795 pence, discount is 1000 pence.
    3. Nominal date is 2026-10-23 17:31:00 UTC (date_uncertain=False).
    4. Card last_4 is '4242' and card label is 'AMEX CREDIT®'; '0411' (MID) and '9749' (TID) are blocked.
    5. With two Amex accounts ('Jordan American Express' and 'Taylor American Express') and no prior association for 4242,
       suggested_account_id is conservatively left as None for manual review.
    """
    from app.ocr.base import ReceiptParseResult, extract_receipt_fields_from_lines
    from app.core.staging import OCRFactory
    from app.core.unified_importer import (
        extract_card_or_account_clues,
        save_confirmed_account_association,
        get_confirmed_account_associations,
    )

    db, tmp_path = isolated_db
    acc_amex_1 = Account(name="Jordan American Express", account_type=AccountType.CREDIT_CARD, currency="GBP", is_active=True)
    acc_amex_2 = Account(name="Taylor American Express", account_type=AccountType.CREDIT_CARD, currency="GBP", is_active=True)
    db.add_all([acc_amex_1, acc_amex_2])
    db.commit()

    ocr_elements = [
        OCRElement(text="evol voy 2p", confidence=0.50, bbox=BoundingBox(top_y=0.062, bot_y=0.072, left_x=0.35, right_x=0.45, width=0.10, height=0.010)),
        OCRElement(text="ACME MART", confidence=1.00, bbox=BoundingBox(top_y=0.130, bot_y=0.166, left_x=0.41, right_x=0.58, width=0.17, height=0.036)),
        OCRElement(text="VAT NO. GB000000000", confidence=1.00, bbox=BoundingBox(top_y=0.232, bot_y=0.244, left_x=0.36, right_x=0.61, width=0.25, height=0.012)),
        OCRElement(text="00000001 SAMPLE PRODUCT", confidence=1.00, bbox=BoundingBox(top_y=0.275, bot_y=0.285, left_x=0.25, right_x=0.55, width=0.30, height=0.010)),
        OCRElement(text="£14.00<", confidence=1.00, bbox=BoundingBox(top_y=0.274, bot_y=0.284, left_x=0.63, right_x=0.73, width=0.10, height=0.010)),
        OCRElement(text="€47.95", confidence=1.00, bbox=BoundingBox(top_y=0.476, bot_y=0.487, left_x=0.63, right_x=0.71, width=0.08, height=0.011)),
        OCRElement(text="Balance before Saving", confidence=1.00, bbox=BoundingBox(top_y=0.479, bot_y=0.489, left_x=0.27, right_x=0.54, width=0.27, height=0.010)),
        OCRElement(text="-£10.00", confidence=1.00, bbox=BoundingBox(top_y=0.490, bot_y=0.500, left_x=0.61, right_x=0.71, width=0.10, height=0.010)),
        OCRElement(text="**£10 off with Loyalty**", confidence=1.00, bbox=BoundingBox(top_y=0.491, bot_y=0.501, left_x=0.27, right_x=0.56, width=0.29, height=0.010)),
        OCRElement(text="£37.95", confidence=1.00, bbox=BoundingBox(top_y=0.503, bot_y=0.513, left_x=0.63, right_x=0.71, width=0.08, height=0.010)),
        OCRElement(text="Balance to Pay", confidence=1.00, bbox=BoundingBox(top_y=0.503, bot_y=0.514, left_x=0.37, right_x=0.55, width=0.18, height=0.011)),
        OCRElement(text="Items: 14", confidence=1.00, bbox=BoundingBox(top_y=0.506, bot_y=0.516, left_x=0.20, right_x=0.31, width=0.11, height=0.010)),
        OCRElement(text="£37.95", confidence=1.00, bbox=BoundingBox(top_y=0.529, bot_y=0.540, left_x=0.63, right_x=0.71, width=0.08, height=0.011)),
        OCRElement(text="Card Tendered", confidence=1.00, bbox=BoundingBox(top_y=0.531, bot_y=0.541, left_x=0.38, right_x=0.55, width=0.17, height=0.010)),
        OCRElement(text="AMEX CREDIT®", confidence=1.00, bbox=BoundingBox(top_y=0.583, bot_y=0.593, left_x=0.28, right_x=0.38, width=0.10, height=0.010)),
        OCRElement(text="TID: ****9749", confidence=1.00, bbox=BoundingBox(top_y=0.593, bot_y=0.603, left_x=0.51, right_x=0.63, width=0.12, height=0.010)),
        OCRElement(text="*******0411", confidence=0.50, bbox=BoundingBox(top_y=0.595, bot_y=0.604, left_x=0.32, right_x=0.42, width=0.10, height=0.009)),
        OCRElement(text="MID:", confidence=1.00, bbox=BoundingBox(top_y=0.597, bot_y=0.607, left_x=0.27, right_x=0.31, width=0.04, height=0.010)),
        OCRElement(text="• 0050", confidence=1.00, bbox=BoundingBox(top_y=0.606, bot_y=0.616, left_x=0.56, right_x=0.61, width=0.05, height=0.010)),
        OCRElement(text="AUTH:", confidence=1.00, bbox=BoundingBox(top_y=0.608, bot_y=0.617, left_x=0.51, right_x=0.56, width=0.05, height=0.009)),
        OCRElement(text="CARD: 370000XXXXX4242 ot", confidence=0.50, bbox=BoundingBox(top_y=0.609, bot_y=0.619, left_x=0.27, right_x=0.48, width=0.21, height=0.010)),
        OCRElement(text="05866119 75988 715 4747", confidence=1.00, bbox=BoundingBox(top_y=0.940, bot_y=0.950, left_x=0.44, right_x=0.77, width=0.33, height=0.010)),
        OCRElement(text="23/10/26 17:31", confidence=1.00, bbox=BoundingBox(top_y=0.941, bot_y=0.951, left_x=0.22, right_x=0.41, width=0.19, height=0.010)),
    ]
    raw_lines = [e.text for e in ocr_elements]

    extracted = extract_receipt_fields_from_lines(raw_lines, ocr_elements, tz_str="Europe/London")
    assert extracted["merchant"] == "ACME MART"
    assert extracted["amount_pence"] == 3795
    assert extracted["subtotal_pence"] == 4795
    assert extracted["discount_pence"] == 1000
    assert extracted["tendered_pence"] == 3795
    # Unzoned 17:31 BST (British Summer Time, UTC+1) on 23 October 2026 converts to 16:31 UTC for storage
    assert extracted["transaction_date"] == datetime(2026, 10, 23, 16, 31, tzinfo=timezone.utc)
    from zoneinfo import ZoneInfo
    assert extracted["transaction_date"].astimezone(ZoneInfo("Europe/London")).date() == datetime(2026, 10, 23).date()
    assert extracted["date_uncertain"] is False

    # Check card clue extraction in both 2D (with ocr_elements) and 1D (raw_lines only)
    clues_2d, last4_2d = extract_card_or_account_clues(raw_lines, ocr_elements=ocr_elements, merchant_name="ACME MART")
    assert last4_2d == "4242"
    assert clues_2d == ["AMEX CREDIT®"]

    clues_1d, last4_1d = extract_card_or_account_clues(raw_lines, ocr_elements=None, merchant_name="ACME MART")
    assert last4_1d == "4242"
    assert "AMEX CREDIT®" in clues_1d
    assert "0411" not in (last4_2d, last4_1d)
    assert "9749" not in (last4_2d, last4_1d)

    # Verify terminal IDs cannot be learned as confirmed account associations
    save_confirmed_account_association(db, "MID: *******0411", acc_amex_1.id, last_4="0411")
    save_confirmed_account_association(db, "TID: ****9749", acc_amex_1.id, last_4="9749")
    assert get_confirmed_account_associations(db) == {}

    class DummyPOSReceiptParser:
        def recognize_text_with_layout(self, image_path):
            return ocr_elements

        def parse_receipt(self, image_path, tz_str=None):
            return ReceiptParseResult(
                success=True,
                confidence=0.9,
                merchant=extracted["merchant"],
                transaction_date=extracted["transaction_date"],
                amount_pence=extracted["amount_pence"],
                original_amount=extracted["original_amount"],
                detected_currency=extracted["detected_currency"],
                raw_lines=raw_lines,
                ocr_elements=ocr_elements,
                amount_uncertain=extracted["amount_uncertain"],
                date_uncertain=extracted["date_uncertain"],
                merchant_uncertain=extracted["merchant_uncertain"],
                subtotal_pence=extracted["subtotal_pence"],
                discount_pence=extracted["discount_pence"],
                tendered_pence=extracted["tendered_pence"],
            )

    monkeypatch.setattr(OCRFactory, "get_parser", lambda: DummyPOSReceiptParser())

    fake_jpeg = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00H\x00H\x00\x00\xff\xdb\x00C\x00"
    res = ingest_unified_file(
        db=db,
        file_content=fake_jpeg,
        original_filename="pos_receipt.jpg",
        staging_dir=tmp_path / "staging_receipts"
    )
    assert res["document_type"] == "receipt"
    assert len(res["items"]) == 1
    item = res["items"][0]
    assert item["extracted_merchant"] == "ACME MART"
    assert item["extracted_amount_pence"] == 3795
    assert item["extracted_date"].startswith("2026-10-23T16:31:00")
    assert item["date_uncertain"] is False
    # Ambiguous across 2 Amex accounts because 4242 is not yet associated -> left None for review
    assert item["suggested_account_id"] is None
    assert "ending in 4242" in (item["suggested_account_match_reason"] or "")
    assert "Jordan American Express" in (item["suggested_account_match_reason"] or "")
    assert "Taylor American Express" in (item["suggested_account_match_reason"] or "")

    # Anchor ordering regression test:
    # 17:31 BST is 16:31 UTC. Verify anchor comparison ordering:
    # An anchor at 16:00 UTC (17:00 BST) is strictly before the transaction (transaction adjusts forward).
    # An anchor at 17:00 UTC (18:00 BST) is strictly after the transaction (transaction already reflected).
    from app.ledger import LedgerEngine
    from app.models import AccountBalanceAnchor
    anchor_before = AccountBalanceAnchor(
        account_id=acc_amex_1.id,
        anchor_date=datetime(2026, 10, 23, 16, 0, tzinfo=timezone.utc),
        balance_pence=-5000,
        notes="Card statement anchor at 17:00 BST"
    )
    db.add(anchor_before)
    db.commit()

    # Commit the receipt transaction on acc_amex_1
    tx_rec = Transaction(
        transaction_date=extracted["transaction_date"],
        effective_timestamp=extracted["transaction_date"],
        transaction_type=TransactionType.EXPENSE,
        amount_pence=3795,
        merchant="ACME MART",
        account_id=acc_amex_1.id,
    )
    db.add(tx_rec)
    db.commit()

    # Since 16:31 UTC > 16:00 UTC anchor, the £37.95 expense is counted: -5000 - 3795 = -8795
    assert LedgerEngine.get_account_balance(db, acc_amex_1.id) == -8795

    # If anchor is updated to 17:00 UTC (18:00 BST), transaction at 16:31 UTC is on or before anchor
    anchor_before.anchor_date = datetime(2026, 10, 23, 17, 0, tzinfo=timezone.utc)
    anchor_before.balance_pence = -8795
    db.commit()
    # Transaction is on or before the 17:00 UTC anchor, so anchor balance is used directly: -8795
    assert LedgerEngine.get_account_balance(db, acc_amex_1.id) == -8795








