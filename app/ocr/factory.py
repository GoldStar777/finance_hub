from typing import Optional
from app.ocr.base import BaseReceiptParser
from app.ocr.apple_vision import AppleVisionParser
from app.ocr.fallback import FallbackReceiptParser

class OCRFactory:
    """Factory to retrieve appropriate OCR parser based on system environment and preferences."""

    @classmethod
    def get_parser(cls, parser_type: Optional[str] = "auto") -> BaseReceiptParser:
        if parser_type == "fallback":
            return FallbackReceiptParser()

        if AppleVisionParser.is_available():
            return AppleVisionParser()

        return FallbackReceiptParser()

