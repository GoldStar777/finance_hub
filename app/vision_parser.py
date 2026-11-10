import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List

try:
    import Quartz
    import Vision
except ImportError:
    Quartz = None
    Vision = None
from dateutil import parser as date_parser

class LocalVisionParser:
    @classmethod
    def _recognize_text_apple(cls, image_path: Path) -> List[str]:
        """
        Uses macOS Vision Framework on Apple Silicon Neural Engine.
        Decodes raw bytes directly via CoreGraphics/ImageIO to avoid 0x0 display proxies.
        """
        if Quartz is None or Vision is None:
            raise RuntimeError("Apple Vision OCR requires macOS pyobjc-framework-Quartz and pyobjc-framework-Vision.")
        # 1. Read raw image bytes from disk
        with open(image_path, "rb") as f:
            raw_bytes = f.read()

        # 2. Decode into CGImage using Quartz ImageIO
        data_provider = Quartz.CGDataProviderCreateWithData(None, raw_bytes, len(raw_bytes), None)
        if not data_provider:
            raise ValueError("Could not create CGDataProvider from image bytes.")

        # Try PNG first, fallback to generic image source
        cg_image = Quartz.CGImageCreateWithPNGDataProvider(data_provider, None, False, Quartz.kCGRenderingIntentDefault)
        if not cg_image:
            # Universal fallback for JPEG, HEIC, TIFF, WebP
            source = Quartz.CGImageSourceCreateWithData(raw_bytes, None)
            if source and Quartz.CGImageSourceGetCount(source) > 0:
                cg_image = Quartz.CGImageSourceCreateImageAtIndex(source, 0, None)

        if not cg_image:
            raise ValueError(f"Could not decode a valid CGImage bitmap from {image_path.name}")

        # 3. Configure Apple Vision OCR Request
        request = Vision.VNRecognizeTextRequest.alloc().init()
        request.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
        request.setUsesLanguageCorrection_(True)

        handler = Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(cg_image, None)
        success, error = handler.performRequests_error_([request], None)

        if not success:
            raise RuntimeError(f"Apple Vision OCR failed: {error}")

        results = request.results()
        extracted_lines = []
        if results:
            for observation in results:
                top_candidate = observation.topCandidates_(1)
                if top_candidate and len(top_candidate) > 0:
                    text = top_candidate[0].string().strip()
                    if text:
                        extracted_lines.append(text)

        return extracted_lines

    @classmethod
    def parse_receipt(cls, image_path: Path) -> Dict[str, Any]:
        """
        Runs Apple Vision OCR, then parses merchant, amount, date, and category.
        """
        try:
            lines = cls._recognize_text_apple(image_path)
            if not lines:
                raise ValueError("No text detected on receipt.")

            # 1. MERCHANT: Store name is usually within the top 4 non-header lines
            merchant = "Unknown Merchant"
            for line in lines[:5]:
                cleaned = line.strip()
                upper = cleaned.upper()
                if len(cleaned) > 2 and not any(k in upper for k in ["RECEIPT", "INVOICE", "WELCOME", "TEL:", "WWW.", "HTTP", "ORDER #", "SALE", "CUSTOMER"]):
                    merchant = cleaned
                    break

            # 2. AMOUNT: Look for explicit TOTAL / BALANCE keywords, or greatest monetary value
            amount = 0.0
            currency_pattern = re.compile(r"[£$€]?\s*(\d+[\.,]\d{2})")
            
            found_total = False
            for line in reversed(lines):
                upper_line = line.upper()
                if any(k in upper_line for k in ["TOTAL", "AMOUNT DUE", "BALANCE", "PAYMENT", "SUBTOTAL"]):
                    match = currency_pattern.search(line)
                    if match:
                        try:
                            val_str = match.group(1).replace(",", ".")
                            amount = float(val_str)
                            found_total = True
                            break
                        except ValueError:
                            pass

            if not found_total:
                all_amounts = []
                for line in lines:
                    matches = currency_pattern.findall(line)
                    for m in matches:
                        try:
                            all_amounts.append(float(m.replace(",", ".")))
                        except ValueError:
                            pass
                if all_amounts:
                    amount = max(all_amounts)

            # 3. DATE HEURISTIC: Prioritise bottom-up transaction dates and skip loyalty/expiry headers
            parsed_date = datetime.now(timezone.utc)
            
            # Matches formats like: 21/10/26, 21/10/2026, 21.10.26, 2026-10-21, 21 Oct 2026
            date_pattern = re.compile(
                r"(\b\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}\b|\b\d{4}[/.-]\d{1,2}[/.-]\d{1,2}\b|\b\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{2,4}\b)", 
                re.IGNORECASE
            )

            # Loyalty phrases that frequently carry misleading historical dates
            ignore_date_keywords = ["POINTS UP TO", "UP TO", "EXPIRY", "EXPIRES", "VALID", "MEMBER SINCE", "JOINED"]

            found_date = None
            # Scan from bottom to top (transaction timestamps live in the receipt footer)
            for line in reversed(lines):
                upper_line = line.upper()
                
                # Skip clubcard/points date lines
                if any(k in upper_line for k in ignore_date_keywords):
                    continue
                
                m = date_pattern.search(line)
                if m:
                    raw_date_str = m.group(0).replace(".", "/")
                    try:
                        # dayfirst=True ensures 21/10/26 is parsed as 21st Oct, not invalid 10th of month 21
                        candidate = date_parser.parse(raw_date_str, dayfirst=True).replace(tzinfo=timezone.utc)
                        # Sanity filter: Ignore dates far in the future or before 2000
                        if 2000 <= candidate.year <= datetime.now(timezone.utc).year + 1:
                            found_date = candidate
                            break
                    except Exception:
                        pass

            if found_date:
                parsed_date = found_date

            # 4. CATEGORY: handled by history-driven suggestion engine
            category = None

            return {
                "success": True,
                "merchant": merchant,
                "amount": amount,
                "date": parsed_date,
                "category": category,
                "confidence": 0.95,
                "raw_lines": lines
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "merchant": "Unreadable Receipt",
                "amount": 0.0,
                "date": datetime.now(timezone.utc),
                "category": "Miscellaneous",
                "confidence": 0.0
            }
