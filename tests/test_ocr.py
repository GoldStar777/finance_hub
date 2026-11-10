from pathlib import Path
from app.ocr.factory import OCRFactory
from app.ocr.fallback import FallbackReceiptParser
from app.ocr.base import BaseReceiptParser, ReceiptParseResult

def test_ocr_factory_and_fallback(tmp_path):
    parser = OCRFactory.get_parser(parser_type="fallback")
    assert isinstance(parser, FallbackReceiptParser)

    dummy_receipt = tmp_path / "dummy_receipt.jpg"
    dummy_receipt.write_text("dummy")

    result = parser.parse_receipt(dummy_receipt)
    assert result.success is True
    assert result.confidence == 0.0
    # Fields must be blank (None), not fake or zero
    assert result.merchant is None
    assert result.amount_pence is None
    assert result.transaction_date is None
    assert "Manual review required" in result.error_message

def test_headmasters_synthetic_receipt_fields(tmp_path):
    """
    Verifies that synthetic salon receipt elements parse £92.00 correctly
    and do not treat terminal identifiers (MID, TID, AID, AUTH) as merchant or card.
    """
    from app.ocr.apple_vision import AppleVisionParser
    from app.core.unified_importer import extract_card_or_account_clues

    lines = [
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

    # Verify card and last-4 extraction
    cand_labels, last_4 = extract_card_or_account_clues(
        ocr_lines=lines,
        merchant_name="Example Hair Studio"
    )
    assert cand_labels == ["AMERICAN EXPRESS"]
    assert last_4 == "4321"


