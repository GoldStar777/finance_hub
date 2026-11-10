import io
import json
import pytest
from datetime import datetime, timezone
from pathlib import Path
from decimal import Decimal
import openpyxl

from app.models import (
    Account, AccountType, Category, Transaction, TransactionType,
    ExpenseNature, StagingItem, StagingStatus
)
from app.core.direction_inference import (
    infer_statement_direction, detect_statement_columns, StatementDirectionAnalysis
)
from app.core.statement_parser import StatementParser
from app.core.unified_importer import ingest_unified_file, parse_excel_statement
from app.core.staging import approve_staging_item, discard_staging_item


def test_detect_statement_columns():
    headers = ["Date", "Description", "Debit Amount", "Credit Amount", "Balance"]
    cols = detect_statement_columns(headers)
    assert cols["date"] == 0
    assert cols["merchant"] == 1
    assert cols["debit"] == 2
    assert cols["credit"] == 3
    assert cols["balance"] == 4


def test_direction_inference_separate_debit_credit():
    headers = ["Date", "Description", "Paid Out", "Paid In"]
    data = [
        ["2026-10-01", "Coffee Shop", "3.50", ""],
        ["2026-10-02", "Salary", "", "2500.00"],
        ["2026-10-03", "Supermarket", "45.20", None]
    ]
    analysis = infer_statement_direction(headers, data)
    assert analysis.evidence_type == "debit_credit_columns"
    assert analysis.expense_count == 2
    assert analysis.income_count == 1
    assert analysis.uncertain_count == 0
    assert analysis.row_results[0].transaction_type == "expense"
    assert analysis.row_results[1].transaction_type == "income"
    assert analysis.row_results[2].transaction_type == "expense"


def test_direction_inference_type_column():
    headers = ["Date", "Description", "Amount", "CR/DR"]
    data = [
        ["2026-10-01", "Bookstore", "15.00", "DR"],
        ["2026-10-02", "Refund", "15.00", "CR"],
        ["2026-10-03", "Stationery", "8.50", "DEBIT"]
    ]
    analysis = infer_statement_direction(headers, data)
    assert analysis.evidence_type == "type_column"
    assert analysis.expense_count == 2
    assert analysis.income_count == 1
    assert analysis.row_results[0].transaction_type == "expense"
    assert analysis.row_results[1].transaction_type == "income"
    assert analysis.row_results[2].transaction_type == "expense"


def test_direction_inference_running_balance():
    headers = ["Date", "Description", "Amount", "Balance"]
    # Starting balance 1000.
    # Row 1: 50 -> balance becomes 950 (decreased -> expense)
    # Row 2: 200 -> balance becomes 1150 (increased -> income)
    # Row 3: 30 -> balance becomes 1120 (decreased -> expense)
    # Row 4: 100 -> balance becomes 1020 (decreased -> expense)
    data = [
        ["2026-10-01", "Opening", "0", "1000.00"],
        ["2026-10-02", "Groceries", "50.00", "950.00"],
        ["2026-10-03", "Bonus", "200.00", "1150.00"],
        ["2026-10-04", "Dinner", "30.00", "1120.00"],
        ["2026-10-05", "Shopping", "100.00", "1020.00"]
    ]
    analysis = infer_statement_direction(headers, data)
    assert analysis.evidence_type == "running_balance"
    assert analysis.row_results[1].transaction_type == "expense"
    assert analysis.row_results[2].transaction_type == "income"
    assert analysis.row_results[3].transaction_type == "expense"
    assert analysis.row_results[4].transaction_type == "expense"


def test_direction_inference_credit_card_amex_structure():
    # Amex style: Charges are positive numbers (£8.49), Payments/credits are negative numbers (-£941.32)
    headers = ["Date", "Description", "Card Member", "Amount"]
    data = [
        ["2026-10-01", "APPLE STORE", "JOHN DOE", "899.00"],
        ["2026-10-02", "PRET A MANGER", "JOHN DOE", "4.50"],
        ["2026-10-05", "PAYMENT RECEIVED - THANK YOU", "JOHN DOE", "-903.50"]
    ]
    analysis = infer_statement_direction(headers, data, filename="Amex_October_2026.csv")
    assert analysis.evidence_type == "card_statement_context"
    assert analysis.expense_count == 2
    assert analysis.income_count == 1
    assert analysis.uncertain_count == 0
    assert analysis.row_results[0].transaction_type == "expense"
    assert analysis.row_results[1].transaction_type == "expense"
    assert analysis.row_results[2].transaction_type == "income"


def test_direction_inference_ambiguous_unsigned_never_defaults_to_income():
    # File with positive unsigned amounts, but NO debit/credit, NO type, NO balance, and NOT a card statement
    headers = ["Date", "Description", "Amount"]
    data = [
        ["2026-10-01", "Unknown Merchant 1", "25.00"],
        ["2026-10-02", "Unknown Merchant 2", "50.00"],
        ["2026-10-03", "Unknown Merchant 3", "12.50"]
    ]
    analysis = infer_statement_direction(headers, data, filename="generic_data.csv")
    assert analysis.evidence_type == "unsigned_ambiguous"
    assert analysis.income_count == 0
    assert analysis.uncertain_count == 3
    # Every row must be flagged uncertain for human review
    for res in analysis.row_results:
        assert res.is_uncertain is True


def test_statement_parser_csv_direction_integration():
    csv_content = (
        "Date,Description,Amount\n"
        "01/10/2026,Coffee Shop,-3.50\n"
        "02/10/2026,Salary,2500.00\n"
        "03/10/2026,Groceries,-65.00\n"
    ).encode("utf-8")

    parsed = StatementParser.parse_statement(
        file_content=csv_content,
        filename="bank_statement.csv",
        mapping={},
        account_currency="GBP"
    )

    assert parsed["staged_count"] == 3
    assert parsed["direction_summary"]["evidence_type"] == "signed_amounts"
    assert parsed["items"][0]["transaction_type"] == "expense"
    assert parsed["items"][1]["transaction_type"] == "income"
    assert parsed["items"][2]["transaction_type"] == "expense"
    assert parsed["items"][0]["direction_uncertain"] is False


def test_excel_card_statement_direction_parsing():
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Statement"
    ws.append(["Date", "Description", "Card Member", "Amount"])
    ws.append(["2026-10-01", "FLIGHT BOOKING", "HOLDER A", 450.00])
    ws.append(["2026-10-02", "HOTEL", "HOLDER A", 120.00])
    ws.append(["2026-10-03", "DIRECT DEBIT PAYMENT", "HOLDER A", -570.00])

    buf = io.BytesIO()
    wb.save(buf)
    file_bytes = buf.getvalue()

    parsed = parse_excel_statement(
        file_content=file_bytes,
        account_currency="GBP",
        filename="Amex_Statement.xlsx",
        is_card_context=True
    )

    assert len(parsed) == 3
    assert parsed.direction_summary["evidence_type"] == "card_statement_context"
    # Charges are expenses
    assert parsed[0]["transaction_type"] == "expense"
    assert parsed[1]["transaction_type"] == "expense"
    # Negative payment is income
    assert parsed[2]["transaction_type"] == "income"
    assert parsed[0]["direction_uncertain"] is False


def test_progressive_approval_preserves_sibling_staging_files(db_session, tmp_path):
    db = db_session
    staging_dir = tmp_path / "staging_receipts"
    archive_dir = tmp_path / "archive_receipts"
    staging_dir.mkdir(parents=True, exist_ok=True)
    archive_dir.mkdir(parents=True, exist_ok=True)

    acc = Account(name="Current Account", account_type=AccountType.CURRENT, currency="GBP", is_active=True)
    db.add(acc)
    db.commit()

    # Upload statement with 3 rows
    csv_bytes = (
        "Date,Description,Amount\n"
        "2026-10-01,Merchant A,10.00\n"
        "2026-10-02,Merchant B,20.00\n"
        "2026-10-03,Merchant C,30.00\n"
    ).encode("utf-8")

    res = ingest_unified_file(
        db=db,
        file_content=csv_bytes,
        original_filename="multi_row_statement.csv",
        target_account_id=acc.id,
        staging_dir=staging_dir
    )

    items = res["items"]
    assert len(items) == 3
    batch_id = res["batch_id"]

    # Verify all 3 items point to the same staging file
    stg1 = db.query(StagingItem).filter(StagingItem.id == items[0]["id"]).first()
    stg2 = db.query(StagingItem).filter(StagingItem.id == items[1]["id"]).first()
    stg3 = db.query(StagingItem).filter(StagingItem.id == items[2]["id"]).first()
    assert stg1.temp_file_path == stg2.temp_file_path == stg3.temp_file_path

    # The file exists in staging
    assert (staging_dir / Path(stg1.temp_file_path).name).exists()

    # Progressive step 1: approve row 1 only
    tx1 = approve_staging_item(db, stg1.id, staging_dir=staging_dir, archive_dir=archive_dir)
    assert tx1 is not None
    assert stg1.status == StagingStatus.APPROVED

    # Sibling items 2 and 3 remain pending
    assert stg2.status == StagingStatus.PENDING
    assert stg3.status == StagingStatus.PENDING

    # Shared staging file MUST still exist because siblings 2 and 3 remain pending!
    assert (staging_dir / Path(stg1.temp_file_path).name).exists()

    # Progressive step 2: exclude row 2
    discard_ok = discard_staging_item(db, stg2.id, staging_dir=staging_dir, archive_dir=archive_dir)
    assert discard_ok is True
    assert stg2.status == StagingStatus.REJECTED

    # Sibling 3 remains pending, so staging file must STILL exist!
    assert (staging_dir / Path(stg1.temp_file_path).name).exists()

    # Progressive step 3: approve row 3 (final pending item)
    tx3 = approve_staging_item(db, stg3.id, staging_dir=staging_dir, archive_dir=archive_dir)
    assert tx3 is not None
    assert stg3.status == StagingStatus.APPROVED

    # Now that 0 pending items remain, staging file has been cleaned up and archived safely
    assert not (staging_dir / Path(stg1.temp_file_path).name).exists()
    archived_files = list(archive_dir.rglob("*multi_row_statement.csv"))
    assert len(archived_files) == 1
    assert archived_files[0].exists()


def test_atomic_rollback_on_batch_validation_failure(db_session, client, tmp_path):
    db = db_session
    acc = Account(name="Test Account", account_type=AccountType.CURRENT, currency="GBP", is_active=True)
    db.add(acc)
    db.commit()

    csv_data = (
        "Date,Description,Amount\n"
        "2026-10-01,Valid Item 1,10.00\n"
        "2026-10-02,Valid Item 2,20.00\n"
    ).encode("utf-8")

    res = ingest_unified_file(
        db=db,
        file_content=csv_data,
        original_filename="batch_test.csv",
        target_account_id=acc.id,
        staging_dir=tmp_path / "staging"
    )

    items = res["items"]
    batch_id = res["batch_id"]

    # Initial ledger count is 0
    assert db.query(Transaction).count() == 0

    # Attempt to commit with an invalid transfer (missing destination_account_id)
    commit_payload = {
        "batch_id": batch_id,
        "action": "approve_selected",
        "items": [
            {
                "id": items[0]["id"],
                "merchant": "Valid Item 1",
                "amount": 10.00,
                "transaction_date": "2026-10-01T12:00:00Z",
                "account_id": acc.id,
                "transaction_type": "expense"
            },
            {
                "id": items[1]["id"],
                "merchant": "Invalid Transfer",
                "amount": 20.00,
                "transaction_date": "2026-10-02T12:00:00Z",
                "account_id": acc.id,
                "transaction_type": "transfer",
                "destination_account_id": None  # Invalid!
            }
        ]
    }

    response = client.post("/api/staging/import-commit", json=commit_payload)
    assert response.status_code == 400

    # Ensure NO transactions were added to ledger (atomic rollback)
    assert db.query(Transaction).count() == 0

    # Ensure staging items remain pending
    db.expire_all()
    stg1 = db.query(StagingItem).filter(StagingItem.id == items[0]["id"]).first()
    stg2 = db.query(StagingItem).filter(StagingItem.id == items[1]["id"]).first()
    assert stg1.status == StagingStatus.PENDING
    assert stg2.status == StagingStatus.PENDING
