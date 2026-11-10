from datetime import datetime, timezone
import pytest
from app.core.statement_parser import StatementParser, clean_amount_string, parse_date_with_format

def test_clean_amount_string_and_currency():
    from decimal import Decimal
    # Standard pound with comma
    val, cur, is_p = clean_amount_string("£1,250.50")
    assert val == Decimal("1250.50")
    assert cur == "GBP"
    assert is_p is False

    # Negative accounting parentheses with dollar
    val, cur, is_p = clean_amount_string("($45.99)")
    assert val == Decimal("-45.99")
    assert cur == "USD"
    assert is_p is True

    # Euro with space
    val, cur, is_p = clean_amount_string(" 19.95 € ")
    assert val == Decimal("19.95")
    assert cur == "EUR"

    # Empty / whitespace
    val, cur, is_p = clean_amount_string("")
    assert val is None

def test_parse_date_with_format():
    # DD/MM/YYYY
    dt1 = parse_date_with_format("21/10/2026", "DD/MM/YYYY")
    assert dt1 == datetime(2026, 10, 21, tzinfo=timezone.utc)

    # YYYY-MM-DD
    dt2 = parse_date_with_format("2026-10-21", "YYYY-MM-DD")
    assert dt2 == datetime(2026, 10, 21, tzinfo=timezone.utc)

    # DD-Mon-YYYY
    dt3 = parse_date_with_format("21-Oct-2026", "DD-Mon-YYYY")
    assert dt3 == datetime(2026, 10, 21, tzinfo=timezone.utc)

    # Invalid date
    dt4 = parse_date_with_format("Total Summary")
    assert dt4 is None

def test_parse_csv_single_standard_polarity():
    csv_data = """Date,Description,Amount,Category
21/10/2026,Waitrose Supermarket,-45.50,Groceries
20/10/2026,Salary Employer Ltd,+2500.00,Income
""".encode("utf-8")

    mapping = {
        "delimiter": ",",
        "has_header": True,
        "date_column": "Date",
        "date_format": "DD/MM/YYYY",
        "merchant_column": "Description",
        "amount_column": "Amount",
        "category_column": "Category",
        "amount_mode": "single_standard"
    }

    result = StatementParser.parse_statement(csv_data, "test.csv", mapping, "GBP")
    assert result["staged_count"] == 2
    assert result["skipped_count"] == 0

    items = result["items"]
    # Row 1: expense
    assert items[0]["extracted_merchant"] == "Waitrose Supermarket"
    assert items[0]["extracted_amount_pence"] == 4550
    assert items[0]["transaction_type"] == "expense"
    assert items[0]["suggested_category_name"] == "Groceries"

    # Row 2: income
    assert items[1]["extracted_merchant"] == "Salary Employer Ltd"
    assert items[1]["extracted_amount_pence"] == 250000
    assert items[1]["transaction_type"] == "income"

def test_parse_csv_single_inverted_credit_card():
    # Credit cards often list charges as positive and payments as negative
    csv_data = """Trans Date,Merchant,Amount
2026-10-18,Apple Store,999.00
2026-10-19,Payment Received,-999.00
""".encode("utf-8")

    mapping = {
        "delimiter": ",",
        "has_header": True,
        "date_column": "Trans Date",
        "date_format": "YYYY-MM-DD",
        "merchant_column": "Merchant",
        "amount_column": "Amount",
        "amount_mode": "single_inverted"
    }

    result = StatementParser.parse_statement(csv_data, "card.csv", mapping, "GBP")
    assert result["staged_count"] == 2

    # Apple Store: positive in card csv -> expense
    assert result["items"][0]["transaction_type"] == "expense"
    assert result["items"][0]["extracted_amount_pence"] == 99900

    # Payment Received: negative in card csv -> income / payment
    assert result["items"][1]["transaction_type"] == "income"
    assert result["items"][1]["extracted_amount_pence"] == 99900

def test_parse_tsv_dual_debit_credit():
    tsv_data = "Date\tPayee\tDebit\tCredit\n21/10/2026\tCouncil Tax\t185.00\t\n22/10/2026\tClient Refund\t\t50.00\n".encode("utf-8")

    mapping = {
        "delimiter": "\t",
        "has_header": True,
        "date_column": "Date",
        "merchant_column": "Payee",
        "debit_column": "Debit",
        "credit_column": "Credit",
        "amount_mode": "dual_debit_credit"
    }

    result = StatementParser.parse_statement(tsv_data, "statement.tsv", mapping, "GBP")
    assert result["staged_count"] == 2
    assert result["items"][0]["transaction_type"] == "expense"
    assert result["items"][0]["extracted_amount_pence"] == 18500
    assert result["items"][1]["transaction_type"] == "income"
    assert result["items"][1]["extracted_amount_pence"] == 5000

def test_parse_malformed_rows_and_currency_conflict():
    csv_data = """Date,Narrative,Amount
Account Number: 12345678,,
21/10/2026,Uber Ride,$15.20
Malformed Date Row,Test Shop,10.00
22/10/2026,Trainline,£28.50
Total Spend: £43.70,,
""".encode("utf-8")

    mapping = {
        "has_header": True,
        "date_column": "Date",
        "merchant_column": "Narrative",
        "amount_column": "Amount",
        "amount_mode": "single_standard"
    }

    result = StatementParser.parse_statement(csv_data, "mixed.csv", mapping, account_currency="GBP")
    
    # 2 valid transactions: Uber Ride ($15.20) and Trainline (£28.50)
    assert result["staged_count"] == 2
    assert result["skipped_count"] >= 3

    # Check currency conflict and foreign origin on Uber ($15.20 in GBP account)
    uber_item = result["items"][0]
    assert uber_item["extracted_merchant"] == "Uber Ride"
    assert uber_item["extracted_amount_pence"] is None
    assert uber_item["original_amount"] == 15.20
    assert uber_item["original_currency"] == "USD"
    assert uber_item["currency_conflict"] is True
    assert "foreign currency" in uber_item["currency_conflict_message"].lower()

    # Check Trainline has no conflict
    train_item = result["items"][1]
    assert train_item["currency_conflict"] is False
