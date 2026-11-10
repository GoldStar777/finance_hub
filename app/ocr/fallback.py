from pathlib import Path
from typing import Optional
from app.ocr.base import BaseReceiptParser, ReceiptParseResult

class FallbackReceiptParser(BaseReceiptParser):
    """
    Fallback receipt parser when Apple Vision or local OCR is unavailable.
    Leaves extracted fields blank (None) so the user is required to complete them manually.
    """
    def parse_receipt(self, image_path: Path, tz_str: Optional[str] = None) -> ReceiptParseResult:
        return ReceiptParseResult(
            success=True,
            confidence=0.0,
            merchant=None,
            amount_pence=None,
            transaction_date=None,
            suggested_category_name=None,
            raw_lines=[],
            error_message="OCR unavailable on this system. Manual review required."
        )

