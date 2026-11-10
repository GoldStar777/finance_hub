import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
import pytest

from app.models import (
    Account, AccountType, Category, Transaction, TransactionType,
    ExpenseNature, StagingItem, StagingStatus
)
from app.core.staging import (
    ingest_statement_csv, ingest_receipt_image, update_staging_item,
    approve_staging_item, discard_staging_item, batch_approve_staging_items,
    save_mapping_profile, list_mapping_profiles, delete_mapping_profile
)
from app.core.timezone import ensure_utc

def test_statement_ingest_duplicate_flag_and_transfer_approval(db_session):
    # 1. Setup accounts
    current_acc = Account(name="Current Account", account_type=AccountType.CURRENT, starting_balance_pence=100000)
    savings_acc = Account(name="Savings Account", account_type=AccountType.SAVINGS, starting_balance_pence=50000)
    db_session.add_all([current_acc, savings_acc])
    db_session.commit()

    # Create an existing transaction in ledger to trigger duplicate match
    existing_tx = Transaction(
        transaction_date=datetime(2026, 10, 20, 10, 0, tzinfo=timezone.utc),
        transaction_type=TransactionType.EXPENSE,
        amount_pence=4550,
        merchant="Waitrose Supermarket",
        account_id=current_acc.id,
        expense_nature=ExpenseNature.VARIABLE
    )
    db_session.add(existing_tx)
    db_session.commit()

    # 2. Ingest CSV statement with two rows: one duplicate of Waitrose, one transfer to savings
    csv_bytes = """Date,Merchant,Amount
20/10/2026,Waitrose Supermarket,-45.50
21/10/2026,Transfer to Savings,-200.00
""".encode("utf-8")

    mapping = {
        "date_column": "Date",
        "date_format": "DD/MM/YYYY",
        "merchant_column": "Merchant",
        "amount_column": "Amount",
        "amount_mode": "single_standard"
    }

    import_res = ingest_statement_csv(
        db=db_session,
        file_content=csv_bytes,
        filename="bank_statement.csv",
        mapping=mapping,
        target_account_id=current_acc.id
    )

    assert import_res["staged_count"] == 2
    items = db_session.query(StagingItem).filter(StagingItem.status == StagingStatus.PENDING).all()
    assert len(items) == 2

    # Check Waitrose duplicate flag
    waitrose_item = next(i for i in items if "Waitrose" in i.extracted_merchant)
    payload_w = json.loads(waitrose_item.raw_payload_json)
    assert payload_w["is_potential_duplicate"] is True
    assert len(payload_w["duplicate_matches"]) == 1
    assert payload_w["duplicate_matches"][0]["id"] == existing_tx.id

    # Check that individual approval works even if flagged as duplicate (non-blocking)
    tx_w = approve_staging_item(db_session, waitrose_item.id)
    assert tx_w.id is not None
    assert tx_w.amount_pence == 4550
    assert waitrose_item.status == StagingStatus.APPROVED

    # Check Transfer conversion
    transfer_item = next(i for i in items if "Transfer to Savings" in i.extracted_merchant)
    update_staging_item(db_session, transfer_item.id, {
        "transaction_type": "transfer",
        "destination_account_id": savings_acc.id,
        "notes": "Monthly savings sweep"
    })

    tx_t = approve_staging_item(db_session, transfer_item.id)
    assert tx_t.transaction_type == TransactionType.TRANSFER
    assert tx_t.account_id == current_acc.id
    assert tx_t.destination_account_id == savings_acc.id
    assert tx_t.amount_pence == 20000

def test_receipt_ingest_blank_fields_and_recoverable_archival(db_session, tmp_path, monkeypatch):
    staging_dir = tmp_path / "staging_receipts"
    archive_dir = tmp_path / "receipts"
    staging_dir.mkdir(parents=True)
    archive_dir.mkdir(parents=True)

    # Force fallback parser so fields are blank (simulating unreadable/uncertain receipt)
    monkeypatch.setattr("app.core.staging.OCRFactory.get_parser", lambda: type("Dummy", (), {
        "parse_receipt": lambda self, path: type("Res", (), {
            "success": True,
            "confidence": 0.0,
            "merchant": None,
            "amount_pence": None,
            "transaction_date": None,
            "suggested_category_name": None,
            "raw_lines": [],
            "error_message": "Uncertain text"
        })()
    })())

    acc = Account(name="Current Account", account_type=AccountType.CURRENT, starting_balance_pence=5000)
    db_session.add(acc)
    db_session.commit()

    # Ingest receipt
    item = ingest_receipt_image(
        db=db_session,
        file_content=b"test receipt image content",
        original_filename="receipt_coffee.jpg",
        target_account_id=acc.id,
        staging_dir=staging_dir
    )

    assert item.status == StagingStatus.PENDING
    assert item.extracted_merchant is None
    assert item.extracted_amount_pence is None
    assert item.extracted_date is None

    # Approval MUST fail if mandatory fields (date, amount) are blank
    with pytest.raises(ValueError, match="Transaction date is required before approval"):
        approve_staging_item(db_session, item.id, staging_dir, archive_dir)

    # User fills in required fields
    update_staging_item(db_session, item.id, {
        "merchant": "Specialty Coffee Shop",
        "amount_pence": 380,
        "transaction_date": datetime(2026, 10, 21, 14, 0, tzinfo=timezone.utc),
        "account_id": acc.id
    })

    # Test recoverable archival failure: point archive_dir to an unwriteable path
    bad_archive_dir = tmp_path / "readonly_archive"
    bad_archive_dir.write_text("not a directory")  # Writing a file where directory is expected will cause mkdir to fail

    with pytest.raises(RuntimeError, match="Failed to archive receipt file"):
        approve_staging_item(db_session, item.id, staging_dir, bad_archive_dir)

    # Verify item remained pending and no transaction was created
    db_session.refresh(item)
    assert item.status == StagingStatus.PENDING
    assert db_session.query(Transaction).count() == 0

    # Now approve with valid archive_dir
    tx = approve_staging_item(db_session, item.id, staging_dir, archive_dir)
    assert tx.id is not None
    assert tx.amount_pence == 380
    assert tx.merchant == "Specialty Coffee Shop"
    assert item.status == StagingStatus.APPROVED
    assert (archive_dir / "2026" / "10").exists()

def test_batch_approval_excludes_duplicates_by_default(db_session):
    acc = Account(name="Current Account", account_type=AccountType.CURRENT, starting_balance_pence=100000)
    db_session.add(acc)
    db_session.commit()

    # Create 3 staging items: 2 clean, 1 marked as duplicate
    item_clean1 = StagingItem(
        status=StagingStatus.PENDING,
        extracted_amount_pence=1500,
        extracted_date=datetime(2026, 10, 21, tzinfo=timezone.utc),
        extracted_merchant="Merchant 1",
        suggested_account_id=acc.id,
        source_type="statement_csv",
        raw_payload_json=json.dumps({"is_potential_duplicate": False})
    )
    item_clean2 = StagingItem(
        status=StagingStatus.PENDING,
        extracted_amount_pence=2500,
        extracted_date=datetime(2026, 10, 21, tzinfo=timezone.utc),
        extracted_merchant="Merchant 2",
        suggested_account_id=acc.id,
        source_type="statement_csv",
        raw_payload_json=json.dumps({"is_potential_duplicate": False})
    )
    item_dup = StagingItem(
        status=StagingStatus.PENDING,
        extracted_amount_pence=5000,
        extracted_date=datetime(2026, 10, 21, tzinfo=timezone.utc),
        extracted_merchant="Merchant Dup",
        suggested_account_id=acc.id,
        source_type="statement_csv",
        raw_payload_json=json.dumps({"is_potential_duplicate": True})
    )
    db_session.add_all([item_clean1, item_clean2, item_dup])
    db_session.commit()

    # Batch approve without duplicates
    res = batch_approve_staging_items(db_session, include_duplicates=False)
    assert res["approved_count"] == 2
    assert res["excluded_duplicates_count"] == 1

    # item_dup should still be pending
    db_session.refresh(item_dup)
    assert item_dup.status == StagingStatus.PENDING

    # Now batch approve including duplicates
    res2 = batch_approve_staging_items(db_session, include_duplicates=True)
    assert res2["approved_count"] == 1
    db_session.refresh(item_dup)
    assert item_dup.status == StagingStatus.APPROVED

def test_mapping_profile_management(db_session):
    profile = {
        "name": "Barclays Checking",
        "config": {
            "date_column": "Date",
            "merchant_column": "Description",
            "amount_column": "Amount",
            "amount_mode": "single_standard"
        }
    }

    saved = save_mapping_profile(db_session, profile)
    assert "id" in saved
    profile_id = saved["id"]

    profiles = list_mapping_profiles(db_session)
    assert len(profiles) >= 1
    assert any(p["name"] == "Barclays Checking" for p in profiles)

    deleted = delete_mapping_profile(db_session, profile_id)
    assert deleted is True

    profiles_after = list_mapping_profiles(db_session)
    assert not any(p["id"] == profile_id for p in profiles_after)

def test_staging_api_endpoints(client, db_session):
    acc = Account(name="API Account", account_type=AccountType.CURRENT, starting_balance_pence=10000)
    db_session.add(acc)
    db_session.commit()

    # 1. Check initial count
    cnt_res = client.get("/api/staging/count")
    assert cnt_res.status_code == 200
    assert cnt_res.json()["pending_count"] == 0

    # 2. Import CSV via API
    csv_content = "Date,Merchant,Amount\n21/10/2026,API Coffee,-3.50\n"
    import_res = client.post(
        "/api/staging/import-csv",
        data={
            "account_id": str(acc.id),
            "mapping_config": json.dumps({
                "date_column": "Date",
                "date_format": "DD/MM/YYYY",
                "merchant_column": "Merchant",
                "amount_column": "Amount",
                "amount_mode": "single_standard"
            }),
            "profile_name_to_save": "Coffee Bank Profile"
        },
        files={"file": ("test.csv", csv_content.encode("utf-8"), "text/csv")}
    )
    assert import_res.status_code == 201
    assert import_res.json()["staged_count"] == 1

    # 3. Verify count and list
    list_res = client.get("/api/staging")
    assert list_res.status_code == 200
    items = list_res.json()
    assert len(items) == 1
    item_id = items[0]["id"]
    assert items[0]["extracted_merchant"] == "API Coffee"
    assert items[0]["amount_pounds"] == 3.50

    # 4. Update item via API
    upd_res = client.put(f"/api/staging/{item_id}", json={
        "merchant": "Special API Coffee",
        "amount": 4.00
    })
    assert upd_res.status_code == 200
    assert upd_res.json()["extracted_merchant"] == "Special API Coffee"
    assert upd_res.json()["amount_pounds"] == 4.00

    # 5. Approve item via API
    app_res = client.post(f"/api/staging/{item_id}/approve")
    assert app_res.status_code == 200
    assert app_res.json()["success"] is True

    # 6. Verify count is 0
    cnt_after = client.get("/api/staging/count")
    assert cnt_after.json()["pending_count"] == 0

def test_png_receipt_upload_api_and_created_at_validation(client, db_session, monkeypatch):
    # Mock OCR to return valid result
    monkeypatch.setattr("app.core.staging.OCRFactory.get_parser", lambda: type("Dummy", (), {
        "parse_receipt": lambda self, path: type("Res", (), {
            "success": True,
            "confidence": 0.85,
            "merchant": "PNG Bakery",
            "amount_pence": 650,
            "transaction_date": datetime(2026, 10, 21, 15, 0, tzinfo=timezone.utc),
            "suggested_category_name": "Groceries",
            "raw_lines": ["PNG Bakery", "TOTAL 6.50"],
            "error_message": None
        })()
    })())

    acc = Account(name="PNG Account", account_type=AccountType.CURRENT, starting_balance_pence=20000)
    db_session.add(acc)
    db_session.commit()

    # Valid 1x1 PNG bytes
    png_bytes = (
        b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01'
        b'\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\rIDATx\x9cc`\x00\x00'
        b'\x00\x02\x00\x01\x00\x00\x00\x00IEND\xaeB`\x82'
    )

    # Post PNG to upload endpoint
    upload_res = client.post(
        "/api/staging/upload-receipt",
        data={"account_id": str(acc.id)},
        files={"file": ("receipt.png", png_bytes, "image/png")}
    )

    assert upload_res.status_code == 201, f"Expected 201, got {upload_res.status_code}: {upload_res.text}"
    data = upload_res.json()
    assert data["source_type"] == "receipt_image"
    assert data["extracted_merchant"] == "PNG Bakery"
    assert data["amount_pounds"] == 6.50
    assert data["created_at"] is not None  # Regression: created_at must never be None

    # Verify listing staging items succeeds without validation error
    list_res = client.get("/api/staging?status=pending")
    assert list_res.status_code == 200
    assert any(i["extracted_merchant"] == "PNG Bakery" for i in list_res.json())

def test_unmapped_api_routes_return_404_json_not_html_or_405(client):
    # GET on unknown /api route must return 404 JSON, NOT 200 HTML
    get_res = client.get("/api/completely-unknown-route")
    assert get_res.status_code == 404
    assert get_res.headers["content-type"].startswith("application/json")
    assert "not found" in get_res.json()["detail"].lower()

    # POST on unknown /api route must return 404 JSON, NOT 405 Method Not Allowed
    post_res = client.post("/api/completely-unknown-route")
    assert post_res.status_code == 404
    assert post_res.headers["content-type"].startswith("application/json")
    assert "not found" in post_res.json()["detail"].lower()


def test_duplicate_exclusion_removes_from_queue_without_creating_transaction(db_session):
    """
    Verifies that excluding a detected duplicate:
    1. Removes it from the pending review queue (status = REJECTED).
    2. Does NOT create any ledger transaction.
    3. Leaves clean sibling items in the queue pending and eligible for approval.
    """
    # 1. Setup account and existing ledger transaction
    acc = Account(name="Current Account", account_type=AccountType.CURRENT, starting_balance_pence=100000)
    db_session.add(acc)
    db_session.commit()

    existing_tx = Transaction(
        transaction_date=datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc),
        transaction_type=TransactionType.EXPENSE,
        amount_pence=4550,
        merchant="Waitrose Supermarket",
        account_id=acc.id,
        expense_nature=ExpenseNature.VARIABLE
    )
    db_session.add(existing_tx)
    db_session.commit()
    initial_tx_count = db_session.query(Transaction).count()
    assert initial_tx_count == 1

    # 2. Ingest statement with two rows:
    # Row 1 is a duplicate of existing_tx (£45.50 Waitrose on 20/10/2026)
    # Row 2 is a separate new transaction (£15.00 Boots on 22/10/2026)
    csv_bytes = """Date,Merchant,Amount
20/10/2026,Waitrose Supermarket,-45.50
22/10/2026,Boots Pharmacy,-15.00
""".encode("utf-8")

    mapping = {
        "date_column": "Date",
        "date_format": "DD/MM/YYYY",
        "merchant_column": "Merchant",
        "amount_column": "Amount",
        "amount_mode": "single_standard"
    }

    import_res = ingest_statement_csv(
        db=db_session,
        file_content=csv_bytes,
        filename="bank_statement.csv",
        mapping=mapping,
        target_account_id=acc.id
    )
    assert import_res["staged_count"] == 2

    pending_items = db_session.query(StagingItem).filter(StagingItem.status == StagingStatus.PENDING).all()
    assert len(pending_items) == 2

    dup_item = next(i for i in pending_items if "Waitrose" in i.extracted_merchant)
    clean_item = next(i for i in pending_items if "Boots" in i.extracted_merchant)

    pl_dup = json.loads(dup_item.raw_payload_json)
    assert pl_dup["is_potential_duplicate"] is True

    # 3. User chooses "Exclude as duplicate" on dup_item:
    discard_success = discard_staging_item(db_session, dup_item.id)
    assert discard_success is True

    # 4. Verify dup_item is REJECTED and no longer pending
    db_session.refresh(dup_item)
    assert dup_item.status == StagingStatus.REJECTED

    remaining_pending = db_session.query(StagingItem).filter(StagingItem.status == StagingStatus.PENDING).all()
    assert len(remaining_pending) == 1
    assert remaining_pending[0].id == clean_item.id

    # Ledger transactions count unchanged: NO transaction was created from dup_item
    assert db_session.query(Transaction).count() == initial_tx_count

    # 5. Clean sibling item can subsequently be approved into the ledger
    approved_tx = approve_staging_item(db_session, clean_item.id)
    assert approved_tx is not None
    assert approved_tx.amount_pence == 1500
    assert approved_tx.merchant == "Boots Pharmacy"
    assert db_session.query(Transaction).count() == initial_tx_count + 1

    # Final pending queue is empty; dup_item was never approved
    assert db_session.query(StagingItem).filter(StagingItem.status == StagingStatus.PENDING).count() == 0


def test_multi_row_shared_source_file_lifecycle_with_duplicate_exclusion(db_session, tmp_path):
    """
    Verifies that excluding one row from a multi-row upload preserves the shared source file
    while sibling rows remain pending, and only cleans up after the last sibling is resolved.
    """
    staging_dir = tmp_path / "staging_receipts"
    archive_dir = tmp_path / "receipts"
    staging_dir.mkdir(parents=True)
    archive_dir.mkdir(parents=True)

    acc = Account(name="Checking", account_type=AccountType.CURRENT, starting_balance_pence=50000)
    db_session.add(acc)
    db_session.commit()

    # Create a shared multi-row screenshot / statement file on disk
    shared_file = staging_dir / "multi_row_statement.png"
    shared_file.write_bytes(b"FAKE_PNG_MULTI_ROW_CONTENT")
    assert shared_file.exists()

    # Create 3 staging items sharing this file path
    items = []
    for idx, (m, amt) in enumerate([("Dup Vendor", 2000), ("Clean Vendor A", 3500), ("Clean Vendor B", 1200)]):
        payload = {
            "source_filename": "multi_row_statement.png",
            "transaction_type": "expense",
            "notes": None,
            "currency": "GBP",
            "is_potential_duplicate": (idx == 0)
        }
        item = StagingItem(
            created_at=datetime.now(timezone.utc),
            status=StagingStatus.PENDING,
            extracted_amount_pence=amt,
            extracted_date=datetime(2026, 10, 22, 12, 0, tzinfo=timezone.utc),
            extracted_merchant=m,
            suggested_account_id=acc.id,
            suggested_expense_nature=ExpenseNature.VARIABLE,
            source_type="receipt_image",
            temp_file_path=str(shared_file),
            raw_payload_json=json.dumps(payload)
        )
        db_session.add(item)
        items.append(item)
    db_session.commit()

    dup_item, clean_a, clean_b = items

    # 1. Exclude the duplicate item (dup_item)
    discard_staging_item(db_session, dup_item.id, staging_dir=staging_dir)

    db_session.refresh(dup_item)
    assert dup_item.status == StagingStatus.REJECTED

    # CRITICAL: The shared source file MUST NOT be deleted because clean_a and clean_b are still PENDING!
    assert shared_file.exists(), "Shared source file was prematurely deleted while sibling rows were pending!"

    # 2. Approve clean_a
    tx_a = approve_staging_item(db_session, clean_a.id, staging_dir=staging_dir, archive_dir=archive_dir)
    assert tx_a.id is not None
    assert tx_a.receipt_path is not None

    # Shared file in staging is still preserved for clean_b
    assert shared_file.exists(), "Shared source file was prematurely deleted before last sibling was resolved!"

    # 3. Discard the final sibling clean_b
    discard_staging_item(db_session, clean_b.id, staging_dir=staging_dir)

    db_session.refresh(clean_b)
    assert clean_b.status == StagingStatus.REJECTED

    # Now all items are resolved (0 pending). Temporary file should now be cleanly removed!
    assert not shared_file.exists(), "Shared staging file was not cleaned up after the last sibling row was resolved!"


def test_manual_expense_splitting_validation(db_session, tmp_path):
    from app.core.staging import split_staging_item
    from app.schemas import StagingSplitRow

    acc = Account(name="Test Split Account", account_type=AccountType.CREDIT_CARD, currency="GBP")
    db_session.add(acc)
    db_session.commit()

    # 1. Reject non-expense item
    transfer_item = StagingItem(
        status=StagingStatus.PENDING,
        extracted_amount_pence=5000,
        extracted_date=datetime(2026, 10, 23, 16, 31, tzinfo=timezone.utc),
        extracted_merchant="Transfer Between Accounts",
        suggested_account_id=acc.id,
        source_type="statement",
        raw_payload_json=json.dumps({"transaction_type": "transfer", "destination_account_id": acc.id})
    )
    db_session.add(transfer_item)
    db_session.commit()

    with pytest.raises(ValueError, match="Only expense receipts can be split"):
        split_staging_item(
            db=db_session,
            item_id=transfer_item.id,
            splits=[
                StagingSplitRow(amount_pence=2500),
                StagingSplitRow(amount_pence=2500)
            ]
        )

    # 2. Expense item with sum mismatch
    expense_item = StagingItem(
        status=StagingStatus.PENDING,
        extracted_amount_pence=3795,  # £37.95
        extracted_date=datetime(2026, 10, 23, 16, 31, tzinfo=timezone.utc),
        extracted_merchant="High Street Foodhall",
        suggested_account_id=acc.id,
        source_type="receipt",
        raw_payload_json=json.dumps({"transaction_type": "expense"})
    )
    db_session.add(expense_item)
    db_session.commit()

    # < 2 splits
    with pytest.raises(ValueError, match="At least two split rows are required"):
        split_staging_item(
            db=db_session,
            item_id=expense_item.id,
            splits=[StagingSplitRow(amount_pence=3795)]
        )

    # Sum less than total
    with pytest.raises(ValueError, match="Split amounts sum to 3000 pence, but the receipt total is 3795 pence"):
        split_staging_item(
            db=db_session,
            item_id=expense_item.id,
            splits=[
                StagingSplitRow(amount_pence=2000),
                StagingSplitRow(amount_pence=1000)
            ]
        )

    # Sum more than total
    with pytest.raises(ValueError, match="Split amounts sum to 4000 pence, but the receipt total is 3795 pence"):
        split_staging_item(
            db=db_session,
            item_id=expense_item.id,
            splits=[
                StagingSplitRow(amount_pence=2000),
                StagingSplitRow(amount_pence=2000)
            ]
        )


def test_manual_expense_splitting_immediate_approval_atomic(db_session, tmp_path):
    from app.core.staging import split_staging_item
    from app.schemas import StagingSplitRow

    staging_dir = tmp_path / "staging_receipts"
    archive_dir = tmp_path / "archive_receipts"
    staging_dir.mkdir(parents=True, exist_ok=True)
    archive_dir.mkdir(parents=True, exist_ok=True)

    fake_receipt = staging_dir / "receipt_foodhall.jpg"
    fake_receipt.write_bytes(b"\xff\xd8\xff\xe0FAKE_SPLIT_IMAGE_BYTES")

    cat_groceries = Category(name="Groceries & Food", color="#10B981", default_expense_nature=ExpenseNature.VARIABLE)
    cat_household = Category(name="Household Supplies", color="#6366F1", default_expense_nature=ExpenseNature.FIXED)
    acc = Account(name="Credit Card", account_type=AccountType.CREDIT_CARD, currency="GBP", starting_balance_pence=0)
    db_session.add_all([cat_groceries, cat_household, acc])
    db_session.commit()

    receipt_dt = datetime(2026, 10, 23, 16, 31, tzinfo=timezone.utc)
    parent_item = StagingItem(
        status=StagingStatus.PENDING,
        extracted_amount_pence=3795,  # £37.95
        extracted_date=receipt_dt,
        extracted_merchant="High Street Foodhall",
        suggested_account_id=acc.id,
        suggested_expense_nature=ExpenseNature.VARIABLE,
        source_type="receipt",
        temp_file_path=str(fake_receipt),
        raw_payload_json=json.dumps({
            "transaction_type": "expense",
            "notes": "Weekly shop"
        })
    )
    db_session.add(parent_item)
    db_session.commit()

    # Split:
    # Row 1: £25.00 (2500p) -> Groceries, manual override to FIXED
    # Row 2: £12.95 (1295p) -> Household, defaults to FIXED
    splits = [
        StagingSplitRow(
            amount_pence=2500,
            category_id=cat_groceries.id,
            expense_nature=ExpenseNature.FIXED,  # Manual override
            notes="Pantry staples"
        ),
        StagingSplitRow(
            amount_pence=1295,
            category_id=cat_household.id,
            expense_nature=ExpenseNature.UNCLASSIFIED,  # Should default from cat_household
            notes="Cleaning detergent"
        )
    ]

    res = split_staging_item(
        db=db_session,
        item_id=parent_item.id,
        splits=splits,
        commit_to_ledger=True,
        staging_dir=staging_dir,
        archive_dir=archive_dir
    )

    assert res["success"] is True
    assert res["action"] == "approved"
    assert len(res["transaction_ids"]) == 2

    # 1. Verify parent staging item was NOT also approved
    db_session.refresh(parent_item)
    assert parent_item.status == StagingStatus.REJECTED
    parent_payload = json.loads(parent_item.raw_payload_json)
    assert parent_payload["split_into_tx_ids"] == res["transaction_ids"]

    # 2. Verify both transactions in the ledger
    tx1 = db_session.query(Transaction).filter(Transaction.id == res["transaction_ids"][0]).first()
    tx2 = db_session.query(Transaction).filter(Transaction.id == res["transaction_ids"][1]).first()

    assert tx1.amount_pence == 2500
    assert tx1.merchant == "High Street Foodhall"
    assert tx1.account_id == acc.id
    assert tx1.category_id == cat_groceries.id
    assert tx1.expense_nature == ExpenseNature.FIXED  # Manual override preserved
    assert tx1.notes == "Pantry staples"
    from app.core.timezone import ensure_utc
    assert ensure_utc(tx1.transaction_date) == receipt_dt
    assert tx1.entry_method == "receipt"
    assert tx1.receipt_path is not None

    assert tx2.amount_pence == 1295
    assert tx2.merchant == "High Street Foodhall"
    assert tx2.account_id == acc.id
    assert tx2.category_id == cat_household.id
    assert tx2.expense_nature == ExpenseNature.FIXED  # Defaulted from category
    assert tx2.notes == "Cleaning detergent"
    assert ensure_utc(tx2.transaction_date) == receipt_dt
    assert tx2.entry_method == "receipt"
    assert tx2.receipt_path == tx1.receipt_path  # Shared single archived file

    # Total ledger amount equals original receipt total exactly
    assert tx1.amount_pence + tx2.amount_pence == 3795

    # Check staging file cleaned up since 0 pending items remain
    assert not fake_receipt.exists()


def test_manual_expense_splitting_review_queue_persistence_and_progressive_approval(db_session, tmp_path):
    from app.core.staging import split_staging_item, approve_staging_item, discard_staging_item
    from app.schemas import StagingSplitRow

    staging_dir = tmp_path / "staging_receipts"
    archive_dir = tmp_path / "archive_receipts"
    staging_dir.mkdir(parents=True, exist_ok=True)
    archive_dir.mkdir(parents=True, exist_ok=True)

    fake_receipt = staging_dir / "receipt_multi_split.jpg"
    fake_receipt.write_bytes(b"\xff\xd8\xff\xe0MULTI_SPLIT_IMG")

    acc = Account(name="Current Account", account_type=AccountType.CURRENT, currency="GBP")
    cat_food = Category(name="Food", color="#F59E0B", default_expense_nature=ExpenseNature.VARIABLE)
    cat_clothes = Category(name="Clothing", color="#EC4899", default_expense_nature=ExpenseNature.VARIABLE)
    cat_books = Category(name="Books", color="#8B5CF6", default_expense_nature=ExpenseNature.VARIABLE)
    db_session.add_all([acc, cat_food, cat_clothes, cat_books])
    db_session.commit()

    receipt_dt = datetime(2026, 10, 23, 16, 31, tzinfo=timezone.utc)
    parent_item = StagingItem(
        status=StagingStatus.PENDING,
        extracted_amount_pence=4795,  # £47.95
        extracted_date=receipt_dt,
        extracted_merchant="Department Store",
        suggested_account_id=acc.id,
        source_type="receipt",
        temp_file_path=str(fake_receipt),
        raw_payload_json=json.dumps({"transaction_type": "expense"})
    )
    db_session.add(parent_item)
    db_session.commit()

    # Split into 3 queue items:
    # £20.00 (2000p), £17.95 (1795p), £10.00 (1000p) -> sum = 4795p
    splits = [
        StagingSplitRow(amount_pence=2000, category_id=cat_food.id, notes="Lunch"),
        StagingSplitRow(amount_pence=1795, category_id=cat_clothes.id, notes="Socks"),
        StagingSplitRow(amount_pence=1000, category_id=cat_books.id, notes="Paperback")
    ]

    res = split_staging_item(
        db=db_session,
        item_id=parent_item.id,
        splits=splits,
        commit_to_ledger=False,
        staging_dir=staging_dir,
        archive_dir=archive_dir
    )

    assert res["success"] is True
    assert res["action"] == "queued"
    assert len(res["created_item_ids"]) == 3

    # Parent is REJECTED (so it won't be approved or counted)
    db_session.refresh(parent_item)
    assert parent_item.status == StagingStatus.REJECTED

    child_ids = res["created_item_ids"]
    c1 = db_session.query(StagingItem).filter(StagingItem.id == child_ids[0]).first()
    c2 = db_session.query(StagingItem).filter(StagingItem.id == child_ids[1]).first()
    c3 = db_session.query(StagingItem).filter(StagingItem.id == child_ids[2]).first()

    assert c1.status == StagingStatus.PENDING
    assert c1.extracted_amount_pence == 2000
    assert c1.extracted_merchant == "Department Store"
    assert c1.suggested_account_id == acc.id
    assert c1.temp_file_path == str(fake_receipt)

    assert c2.status == StagingStatus.PENDING
    assert c2.extracted_amount_pence == 1795

    assert c3.status == StagingStatus.PENDING
    assert c3.extracted_amount_pence == 1000

    # Staging file is PRESERVED because all 3 are pending
    assert fake_receipt.exists()

    # 1. Approve c1 into ledger
    tx1 = approve_staging_item(db_session, c1.id, staging_dir=staging_dir, archive_dir=archive_dir)
    assert tx1.amount_pence == 2000
    assert fake_receipt.exists(), "Staging receipt must stay while c2 and c3 are pending!"

    # 2. Approve c2 into ledger
    tx2 = approve_staging_item(db_session, c2.id, staging_dir=staging_dir, archive_dir=archive_dir)
    assert tx2.amount_pence == 1795
    assert tx2.receipt_path == tx1.receipt_path, "Archived file must be shared between split siblings!"
    assert fake_receipt.exists(), "Staging receipt must stay while c3 is pending!"

    # 3. Discard c3
    discard_staging_item(db_session, c3.id, staging_dir=staging_dir, archive_dir=archive_dir)
    db_session.refresh(c3)
    assert c3.status == StagingStatus.REJECTED

    # Now all siblings are resolved -> staging file cleanly deleted
    assert not fake_receipt.exists(), "Temporary staging file must be removed when all siblings are resolved!"


def test_manual_expense_split_api_endpoints(client, db_session, tmp_path):
    acc = Account(name="Amex Gold", account_type=AccountType.CREDIT_CARD, currency="GBP")
    cat1 = Category(name="Dining", color="#F59E0B", default_expense_nature=ExpenseNature.VARIABLE)
    cat2 = Category(name="Entertainment", color="#6366F1", default_expense_nature=ExpenseNature.VARIABLE)
    db_session.add_all([acc, cat1, cat2])
    db_session.commit()

    receipt_item = StagingItem(
        status=StagingStatus.PENDING,
        extracted_amount_pence=5000,  # £50.00
        extracted_date=datetime(2026, 10, 23, 16, 31, tzinfo=timezone.utc),
        extracted_merchant="Dinner & Cinema",
        suggested_account_id=acc.id,
        source_type="receipt",
        raw_payload_json=json.dumps({"transaction_type": "expense"})
    )
    db_session.add(receipt_item)
    db_session.commit()

    # Split via API with commit_to_ledger=False (Queue)
    res = client.post(f"/api/staging/items/{receipt_item.id}/split", json={
        "splits": [
            {"amount_pence": 3500, "category_id": cat1.id, "expense_nature": "variable", "notes": "Dinner"},
            {"amount_pence": 1500, "category_id": cat2.id, "expense_nature": "variable", "notes": "Movie tickets"}
        ],
        "commit_to_ledger": False
    })
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["success"] is True
    assert data["action"] == "queued"
    assert len(data["created_items"]) == 2
    assert data["created_items"][0]["extracted_amount_pence"] == 3500
    assert data["created_items"][0]["is_split"] is True
    assert data["created_items"][1]["extracted_amount_pence"] == 1500

    # Immediate approve via API
    item2 = StagingItem(
        status=StagingStatus.PENDING,
        extracted_amount_pence=3000,
        extracted_date=datetime(2026, 10, 23, 16, 31, tzinfo=timezone.utc),
        extracted_merchant="Coffee & Bakery",
        suggested_account_id=acc.id,
        source_type="receipt",
        raw_payload_json=json.dumps({"transaction_type": "expense"})
    )
    db_session.add(item2)
    db_session.commit()

    res_app = client.post(f"/api/staging/{item2.id}/split", json={
        "splits": [
            {"amount_pence": 1800, "category_id": cat1.id, "notes": "Beans"},
            {"amount_pence": 1200, "category_id": cat2.id, "notes": "Pastries"}
        ],
        "commit_to_ledger": True
    })
    assert res_app.status_code == 200, res_app.text
    data_app = res_app.json()
    assert data_app["success"] is True
    assert data_app["action"] == "approved"
    assert len(data_app["transaction_ids"]) == 2


def test_split_staging_item_shared_fields_editing_and_account_preservation(client, db_session):
    """
    Verifies that manual expense splitting:
    1. Preserves and updates shared receipt details (account, date, merchant, notes).
    2. Corrects unassigned account to user-selected account.
    3. Queued split items inherit the updated shared account, date, and merchant.
    4. Approved split items create transactions with the updated shared account, date, and merchant.
    5. Parent item is REJECTED and never approved into the ledger.
    """
    acc1 = Account(name="Lloyds Checking", account_type=AccountType.CURRENT, starting_balance_pence=100000)
    acc2 = Account(name="Amex Rewards", account_type=AccountType.CREDIT_CARD, starting_balance_pence=0)
    cat_food = Category(name="Groceries", color="#10B981")
    cat_clothes = Category(name="Clothing", color="#F59E0B")
    db_session.add_all([acc1, acc2, cat_food, cat_clothes])
    db_session.commit()

    # 1. Staging item with unassigned account (suggested_account_id=None)
    item_unassigned = StagingItem(
        status=StagingStatus.PENDING,
        extracted_amount_pence=3795, # £37.95
        extracted_date=datetime(2026, 10, 19, 12, 0, tzinfo=timezone.utc),
        extracted_merchant="M&S OCR",
        suggested_account_id=None,
        source_type="receipt",
        raw_payload_json=json.dumps({"transaction_type": "expense"})
    )
    db_session.add(item_unassigned)
    db_session.commit()

    # Split to queue with corrected account, date, and merchant
    split_date_iso = "2026-10-23T16:31:00Z"
    split_date_dt = datetime(2026, 10, 23, 16, 31, tzinfo=timezone.utc)

    res_queue = client.post(f"/api/staging/items/{item_unassigned.id}/split", json={
        "account_id": acc2.id,
        "transaction_date": split_date_iso,
        "merchant": "Marks & Spencer",
        "notes": "Shared grocery and apparel purchase",
        "splits": [
            {"amount_pence": 2795, "category_id": cat_food.id, "expense_nature": "variable", "notes": "Food items"},
            {"amount_pence": 1000, "category_id": cat_clothes.id, "expense_nature": "variable", "notes": "Socks"}
        ],
        "commit_to_ledger": False
    })
    assert res_queue.status_code == 200, res_queue.text
    data_queue = res_queue.json()
    assert data_queue["success"] is True
    assert data_queue["action"] == "queued"
    assert len(data_queue["created_items"]) == 2

    # Check that children have inherited the edited shared fields
    child1 = db_session.query(StagingItem).filter(StagingItem.id == data_queue["created_item_ids"][0]).first()
    child2 = db_session.query(StagingItem).filter(StagingItem.id == data_queue["created_item_ids"][1]).first()
    assert child1.suggested_account_id == acc2.id
    assert child2.suggested_account_id == acc2.id
    assert child1.extracted_merchant == "Marks & Spencer"
    assert child2.extracted_merchant == "Marks & Spencer"
    assert ensure_utc(child1.extracted_date) == split_date_dt
    assert ensure_utc(child2.extracted_date) == split_date_dt

    # Parent must be rejected, not pending
    db_session.refresh(item_unassigned)
    assert item_unassigned.status == StagingStatus.REJECTED

    # 2. Split with commit_to_ledger=True
    item_approve = StagingItem(
        status=StagingStatus.PENDING,
        extracted_amount_pence=4500, # £45.00
        extracted_date=datetime(2026, 10, 20, 10, 0, tzinfo=timezone.utc),
        extracted_merchant="Old Merchant",
        suggested_account_id=acc1.id,
        source_type="receipt",
        raw_payload_json=json.dumps({"transaction_type": "expense"})
    )
    db_session.add(item_approve)
    db_session.commit()

    res_approve = client.post(f"/api/staging/items/{item_approve.id}/split", json={
        "account_id": acc2.id, # changed from acc1 to acc2
        "transaction_date": split_date_iso,
        "merchant": "Target Store",
        "notes": "Department store run",
        "splits": [
            {"amount_pence": 3000, "category_id": cat_food.id, "expense_nature": "variable", "notes": "Snacks"},
            {"amount_pence": 1500, "category_id": cat_clothes.id, "expense_nature": "variable", "notes": "T-shirt"}
        ],
        "commit_to_ledger": True
    })
    assert res_approve.status_code == 200, res_approve.text
    data_approve = res_approve.json()
    assert data_approve["success"] is True
    assert data_approve["action"] == "approved"
    assert len(data_approve["transaction_ids"]) == 2

    # Verify transactions in the database
    tx1 = db_session.query(Transaction).filter(Transaction.id == data_approve["transaction_ids"][0]).first()
    tx2 = db_session.query(Transaction).filter(Transaction.id == data_approve["transaction_ids"][1]).first()
    assert tx1.account_id == acc2.id
    assert tx2.account_id == acc2.id
    assert tx1.merchant == "Target Store"
    assert tx2.merchant == "Target Store"
    assert ensure_utc(tx1.transaction_date) == split_date_dt
    assert ensure_utc(tx2.transaction_date) == split_date_dt
    assert tx1.amount_pence + tx2.amount_pence == 4500

    db_session.refresh(item_approve)
    assert item_approve.status == StagingStatus.REJECTED


def test_split_staging_item_approved_with_no_account(client, db_session):
    """
    Verifies that unassigned expenses remain possible when splitting receipts:
    1. A split expense can be approved with account_id=None (Unassigned).
    2. Split transactions are created with account_id=None in the ledger.
    3. Parent item is REJECTED and unsplit receipt is not duplicated.
    """
    cat1 = Category(name="Household", color="#3B82F6")
    cat2 = Category(name="Pharmacy", color="#10B981")
    db_session.add_all([cat1, cat2])
    db_session.commit()

    item = StagingItem(
        status=StagingStatus.PENDING,
        extracted_amount_pence=3500,  # £35.00
        extracted_date=datetime(2026, 10, 23, 16, 31, tzinfo=timezone.utc),
        extracted_merchant="Local Market",
        suggested_account_id=None,
        source_type="receipt",
        raw_payload_json=json.dumps({"transaction_type": "expense"})
    )
    db_session.add(item)
    db_session.commit()

    split_date_iso = "2026-10-23T16:31:00Z"
    split_date_dt = datetime(2026, 10, 23, 16, 31, tzinfo=timezone.utc)

    res = client.post(f"/api/staging/items/{item.id}/split", json={
        "account_id": None, # explicitly unassigned
        "transaction_date": split_date_iso,
        "merchant": "Local Market",
        "notes": "Unassigned cash receipt split",
        "splits": [
            {"amount_pence": 2000, "category_id": cat1.id, "expense_nature": "variable", "notes": "Cleaning supplies"},
            {"amount_pence": 1500, "category_id": cat2.id, "expense_nature": "variable", "notes": "Vitamins"}
        ],
        "commit_to_ledger": True
    })
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["success"] is True
    assert data["action"] == "approved"
    assert len(data["transaction_ids"]) == 2

    # Verify created transactions have account_id == None
    tx1 = db_session.query(Transaction).filter(Transaction.id == data["transaction_ids"][0]).first()
    tx2 = db_session.query(Transaction).filter(Transaction.id == data["transaction_ids"][1]).first()
    assert tx1.account_id is None
    assert tx2.account_id is None
    assert tx1.merchant == "Local Market"
    assert tx2.merchant == "Local Market"
    assert ensure_utc(tx1.transaction_date) == split_date_dt
    assert ensure_utc(tx2.transaction_date) == split_date_dt
    assert tx1.amount_pence + tx2.amount_pence == 3500

    # Parent must be rejected
    db_session.refresh(item)
    assert item.status == StagingStatus.REJECTED



