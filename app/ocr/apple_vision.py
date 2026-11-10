import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional
from dateutil import parser as date_parser

from app.core.currency import pounds_to_pence
from app.ocr.base import (
    BaseReceiptParser, ReceiptParseResult, OCRElement, BoundingBox,
    extract_receipt_fields_from_lines
)

class AppleVisionParser(BaseReceiptParser):
    """
    macOS Apple Silicon Neural Engine OCR parser using PyObjC Vision framework.
    Dynamically imported and safely handles non-macOS or missing dependencies.
    """

    @classmethod
    def is_available(cls) -> bool:
        if sys.platform != "darwin":
            return False
        try:
            import Quartz
            import Vision
            return True
        except ImportError:
            return False

    def recognize_text_with_layout(self, image_path: Path) -> List[OCRElement]:
        """
        Extracts recognized text elements with bounding box spatial metadata.
        Returns elements sorted top-to-bottom in visual reading order.
        """
        import Quartz
        import Vision

        with open(image_path, "rb") as f:
            raw_bytes = f.read()

        data_provider = Quartz.CGDataProviderCreateWithData(None, raw_bytes, len(raw_bytes), None)
        if not data_provider:
            raise ValueError("Could not create CGDataProvider from image bytes.")

        cg_image = Quartz.CGImageCreateWithPNGDataProvider(data_provider, None, False, Quartz.kCGRenderingIntentDefault)
        if not cg_image:
            source = Quartz.CGImageSourceCreateWithData(raw_bytes, None)
            if source and Quartz.CGImageSourceGetCount(source) > 0:
                cg_image = Quartz.CGImageSourceCreateImageAtIndex(source, 0, None)

        if not cg_image:
            raise ValueError(f"Could not decode a valid CGImage bitmap from {image_path.name}")

        request = Vision.VNRecognizeTextRequest.alloc().init()
        request.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
        request.setUsesLanguageCorrection_(True)

        handler = Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(cg_image, None)
        success, error = handler.performRequests_error_([request], None)

        if not success:
            raise RuntimeError(f"Apple Vision OCR failed: {error}")

        results = request.results()
        elements = []
        if results:
            for observation in results:
                top_candidate = observation.topCandidates_(1)
                if top_candidate and len(top_candidate) > 0:
                    text = top_candidate[0].string().strip()
                    if text:
                        bbox = observation.boundingBox()
                        top_y = 1.0 - (bbox.origin.y + bbox.size.height)
                        bot_y = 1.0 - bbox.origin.y
                        left_x = bbox.origin.x
                        right_x = bbox.origin.x + bbox.size.width
                        elements.append(OCRElement(
                            text=text,
                            confidence=float(top_candidate[0].confidence()),
                            bbox=BoundingBox(
                                top_y=top_y,
                                bot_y=bot_y,
                                left_x=left_x,
                                right_x=right_x,
                                width=bbox.size.width,
                                height=bbox.size.height
                            )
                        ))

        # Sort elements in top-to-bottom reading order by center_y
        elements.sort(key=lambda e: e.bbox.center_y)
        return elements

    def _recognize_text_apple(self, image_path: Path) -> List[str]:
        elements = self.recognize_text_with_layout(image_path)
        return [e.text for e in elements]

    def parse_receipt(self, image_path: Path, tz_str: Optional[str] = None) -> ReceiptParseResult:
        if not self.is_available():
            return ReceiptParseResult(
                success=False,
                confidence=0.0,
                merchant=None,
                amount_pence=None,
                transaction_date=None,
                error_message="Apple Vision OCR is not available on this platform."
            )

        try:
            elements = self.recognize_text_with_layout(image_path)
            lines = [e.text for e in elements]
            if not lines:
                return ReceiptParseResult(
                    success=True,
                    confidence=0.0,
                    merchant=None,
                    amount_pence=None,
                    transaction_date=None,
                    raw_lines=[],
                    ocr_elements=[],
                    error_message="No readable text detected on receipt.",
                    amount_uncertain=True,
                    date_uncertain=True,
                    merchant_uncertain=True
                )

            extracted = extract_receipt_fields_from_lines(lines, elements, tz_str=tz_str)

            return ReceiptParseResult(
                success=True,
                confidence=extracted["confidence"],
                merchant=extracted["merchant"],
                amount_pence=extracted["amount_pence"],
                detected_currency=extracted["detected_currency"],
                original_amount=extracted["original_amount"],
                transaction_date=extracted["transaction_date"],
                suggested_category_name=None,
                raw_lines=lines,
                ocr_elements=elements,
                error_message=None,
                amount_uncertain=extracted["amount_uncertain"],
                date_uncertain=extracted["date_uncertain"],
                merchant_uncertain=extracted["merchant_uncertain"],
                subtotal_pence=extracted["subtotal_pence"],
                discount_pence=extracted["discount_pence"],
                tendered_pence=extracted["tendered_pence"]
            )

        except Exception as e:
            return ReceiptParseResult(
                success=False,
                confidence=0.0,
                merchant=None,
                amount_pence=None,
                transaction_date=None,
                raw_lines=[],
                error_message=str(e)
            )

