import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
from dateutil import parser as date_parser

from app.core.currency import pounds_to_pence

@dataclass
class BoundingBox:
    top_y: float
    bot_y: float
    left_x: float
    right_x: float
    width: float
    height: float

    @property
    def center_y(self) -> float:
        return (self.top_y + self.bot_y) / 2.0

    @property
    def center_x(self) -> float:
        return (self.left_x + self.right_x) / 2.0

@dataclass
class OCRElement:
    text: str
    confidence: float
    bbox: BoundingBox

@dataclass
class ReceiptParseResult:
    success: bool
    confidence: float
    merchant: Optional[str] = None
    amount_pence: Optional[int] = None
    detected_currency: Optional[str] = None
    original_amount: Optional[float] = None
    transaction_date: Optional[datetime] = None
    suggested_category_name: Optional[str] = None
    raw_lines: List[str] = field(default_factory=list)
    ocr_elements: List[OCRElement] = field(default_factory=list)
    error_message: Optional[str] = None
    amount_uncertain: bool = False
    date_uncertain: bool = False
    merchant_uncertain: bool = False
    subtotal_pence: Optional[int] = None
    discount_pence: Optional[int] = None
    tendered_pence: Optional[int] = None


def reconstruct_visual_lines(
    ocr_elements: Optional[List[OCRElement]] = None,
    fallback_lines: Optional[List[str]] = None
) -> List[str]:
    """
    Groups 2D OCRElements that share the same horizontal reading line into single strings
    ordered left-to-right, so left-aligned labels (e.g. 'Balance to Pay') and right-aligned
    amounts (e.g. '£37.95') are joined into a unified visual row.
    Falls back to fallback_lines when spatial elements are unavailable.
    """
    if not ocr_elements:
        return [l.strip() for l in (fallback_lines or []) if l and l.strip()]

    sorted_elems = sorted(
        [
            e for e in ocr_elements
            if e.text and e.text.strip()
            and getattr(e, "confidence", 1.0) >= 0.35
            and not re.search(r"[\u0400-\u04FF]", e.text)
        ],
        key=lambda e: e.bbox.center_y
    )
    if not sorted_elems:
        return [l.strip() for l in (fallback_lines or []) if l and l.strip()]

    rows: List[List[OCRElement]] = []
    for elem in sorted_elems:
        if not rows:
            rows.append([elem])
            continue

        last_row = rows[-1]
        avg_y = sum(e.bbox.center_y for e in last_row) / len(last_row)
        avg_h = sum(e.bbox.height for e in last_row) / len(last_row)
        y_tol = max(0.0045, min(0.0085, avg_h * 0.55))

        # Check vertical alignment and lack of horizontal overlap
        overlaps_x = any(
            (min(elem.bbox.right_x, existing.bbox.right_x) - max(elem.bbox.left_x, existing.bbox.left_x)) > 0.05
            for existing in last_row
        )
        if abs(elem.bbox.center_y - avg_y) <= y_tol and not overlaps_x:
            last_row.append(elem)
        else:
            rows.append([elem])

    visual_lines: List[str] = []
    for row in rows:
        row.sort(key=lambda e: e.bbox.left_x)
        joined = " ".join(e.text.strip() for e in row if e.text.strip())
        if joined:
            visual_lines.append(joined)

    return visual_lines


_DECIMAL_AMOUNT_PATTERN = re.compile(
    r"([-+]?\s*(?:[£$€¥₹]|USD|EUR|GBP|JPY|INR)?\s*\d{1,3}(?:,\d{3})*[\.,]\d{2})\b",
    re.IGNORECASE
)
_STANDALONE_AMOUNT_LINE_PATTERN = re.compile(
    r"^\s*[-+]?\s*(?:[£$€¥₹]|USD|EUR|GBP|JPY|INR)?\s*\d{1,3}(?:,\d{3})*[\.,]\d{2}\s*[-+*]*\s*$",
    re.IGNORECASE
)

_SUBTOTAL_LINE_RE = re.compile(
    r"\b(?:sub[\s\-]?total|balance\s+before(?:\s+sav(?:ing|ings|ed))?|total\s+before(?:\s+sav(?:ing|ings|ed)|\s+discount)?|before\s+sav(?:ing|ings|ed)|before\s+discount|items\s+total|goods\s+total)\b",
    re.IGNORECASE
)
_DISCOUNT_LINE_RE = re.compile(
    r"\b(?:sav(?:ing|ings|ed)|you\s+have\s+saved|total\s+saving|your\s+total\s+saving|discount(?:s)?|promo(?:tion|tional)?|voucher|coupon|reward(?:s)?|loyalty|points|deduction|member\s+saving)\b"
    r"|(?:[£$€¥₹]\s*\d+(?:[\.,]\d{2})?\s+off\b|\b\d+(?:\.\d+)?%\s+off\b|\boff\s+with\b)",
    re.IGNORECASE
)
_CHANGE_LINE_RE = re.compile(
    r"\b(?:change\s+due|change\s+given|change|cashback)\b",
    re.IGNORECASE
)
_CASH_TENDER_LINE_RE = re.compile(
    r"\bcash\s+(?:tendered|paid)\b",
    re.IGNORECASE
)
_TOTAL_INC_TAX_RE = re.compile(
    r"\btotal\s+(?:inc(?:l|luding)?\.?|with)\s+(?:vat|tax)\b",
    re.IGNORECASE
)
_TAX_BREAKDOWN_LINE_RE = re.compile(
    r"\b(?:vat|tax|sales\s+tax|gst)\b",
    re.IGNORECASE
)
_TIER1_PAYABLE_LINE_RE = re.compile(
    r"\b(?:balance\s+to\s+pay|total\s+to\s+pay|amount\s+to\s+pay|to\s+pay|amount\s+due|total\s+due|balance\s+due|grand\s+total|net\s+total|total\s+paid|amount\s+paid|total\s+payable)\b",
    re.IGNORECASE
)
_TIER2_TENDER_LINE_RE = re.compile(
    r"\b(?:card\s+tendered|(?:credit|debit|amex|american\s+express|visa|mastercard|contactless)\s+tendered|amount\s+tendered|tendered|card\s+payment|payment\s+received|charged\s+to\s+card)\b",
    re.IGNORECASE
)
_TIER3_GENERIC_TOTAL_LINE_RE = re.compile(
    r"\b(?:total|balance|payment|sale\s+amount)\b",
    re.IGNORECASE
)


def _normalize_currency_symbol(sym: Optional[str]) -> Optional[str]:
    if not sym:
        return None
    s = sym.strip().upper()
    if s in ("£", "GBP"):
        return "GBP"
    if s in ("$", "USD"):
        return "USD"
    if s in ("€", "EUR"):
        return "EUR"
    if s in ("¥", "JPY"):
        return "JPY"
    if s in ("₹", "INR"):
        return "INR"
    return None


def _extract_line_amounts(line: str) -> List[Tuple[float, Optional[str], int]]:
    """
    Returns [(float_val, normalized_currency, amount_pence)] for decimal currency amounts on a line.
    """
    results: List[Tuple[float, Optional[str], int]] = []
    sym_pat = re.compile(r"([£$€¥₹]|USD|EUR|GBP|JPY|INR)?\s*(\d{1,3}(?:,\d{3})*[\.,]\d{2})\b", re.IGNORECASE)
    for m in sym_pat.finditer(line):
        raw_sym = m.group(1)
        raw_num = m.group(2)
        # Normalise thousand separators vs decimal point
        if "," in raw_num and "." in raw_num:
            num_clean = raw_num.replace(",", "")
        else:
            num_clean = raw_num.replace(",", ".")
        try:
            val = float(num_clean)
            if val > 0:
                curr = _normalize_currency_symbol(raw_sym)
                pence = pounds_to_pence(val)
                results.append((val, curr, pence))
        except Exception:
            pass
    return results


def extract_receipt_fields_from_lines(
    raw_lines: List[str],
    ocr_elements: Optional[List[OCRElement]] = None,
    tz_str: Optional[str] = None
) -> Dict[str, Any]:
    """
    Provider-agnostic single-receipt field extractor.
    1. Reconstructs horizontal visual rows from 2D bounding boxes and/or pairs adjacent label+price lines.
    2. Distinguishes item rows, pre-discount subtotals, discounts/savings, change/tax lines,
       and final payable / card-tendered amounts.
    3. Resolves thermal-receipt £/€ OCR symbol misreads using document-wide currency evidence.
    4. Flags uncertainty (`amount_uncertain=True`, `amount_pence=None`) when multiple item prices exist
       without an identifiable total/payable/tendered amount, or when final totals conflict.
    """
    visual_lines = reconstruct_visual_lines(ocr_elements, raw_lines)

    # Build 1D label+standalone-amount combined lines ONLY when 2D spatial elements were not provided
    effective_lines: List[str] = list(visual_lines)
    if not ocr_elements:
        raw_clean = [l.strip() for l in (raw_lines or []) if l and l.strip()]
        i = 0
        while i < len(raw_clean):
            curr_line = raw_clean[i]
            curr_amts = _extract_line_amounts(curr_line)
            if not curr_amts and i + 1 < len(raw_clean) and _STANDALONE_AMOUNT_LINE_PATTERN.match(raw_clean[i + 1]):
                combined = f"{curr_line} {raw_clean[i + 1]}"
                if combined not in effective_lines:
                    effective_lines.append(combined)
                i += 2
                continue
            i += 1

    all_text_joined = " ".join(effective_lines)

    # 1. Dominant receipt currency resolution (prevent single-line £ -> € OCR misread on GBP receipts)
    has_gbp_evidence = bool(
        re.search(r"£|\bGBP\b|\bVAT\b", all_text_joined, re.IGNORECASE)
    )
    has_explicit_eur_code = bool(re.search(r"\bEUR\b", all_text_joined, re.IGNORECASE))

    def resolve_curr(c: Optional[str]) -> Optional[str]:
        if c == "EUR" and has_gbp_evidence and not has_explicit_eur_code:
            return "GBP"
        return c

    # 2. Merchant extraction from header lines
    merchant: Optional[str] = None
    merchant_uncertain = False
    header_ignore_keywords = (
        "RECEIPT", "INVOICE", "WELCOME", "TEL:", "TEL ", "TELEPHONE", "WWW.", "HTTP",
        "ORDER #", "ORDER NO", "SALE", "CUSTOMER", "VAT NO", "VAT REG", "TAX INVOICE",
        "CARDHOLDER COPY", "CUSTOMER COPY", "PLEASE RETAIN", "THANK YOU", "MID:", "TID:", "AID:",
        "AUTH CODE", "AUTH:", "AUTHORISATION", "BALANCE", "TOTAL", "SUBTOTAL", "TENDERED", "SAVING", "DISCOUNT"
    )
    uk_postcode_re = re.compile(r"\b[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}\b", re.IGNORECASE)
    sku_line_re = re.compile(r"^\s*\d{6,14}\b")

    for line in visual_lines[:7]:
        cleaned = line.strip()
        if len(cleaned) <= 2:
            continue
        upper = cleaned.upper()
        if any(k in upper for k in header_ignore_keywords):
            continue
        if sku_line_re.search(cleaned):
            continue
        if _extract_line_amounts(cleaned):
            continue
        if uk_postcode_re.search(cleaned):
            continue
        if re.search(r"[\u0400-\u04FF]", cleaned):
            continue
        # Reject all-lowercase bleed-through noise (real receipt merchant headers contain uppercase/title-case letters)
        if not any(ch.isupper() for ch in cleaned):
            continue
        # Skip lines that are mostly digits/phone numbers/dates
        alpha_chars = sum(1 for ch in cleaned if ch.isalpha())
        if alpha_chars < 2:
            continue
        merchant = cleaned
        break

    if not merchant:
        merchant_uncertain = True

    # 3. Amount classification across receipt lines
    has_change_line = any(_CHANGE_LINE_RE.search(l) for l in effective_lines)

    subtotal_candidates: List[Tuple[int, float, Optional[str]]] = []
    discount_candidates: List[Tuple[int, float, Optional[str]]] = []
    tier1_payable: List[Tuple[int, float, Optional[str]]] = []
    tier2_tender: List[Tuple[int, float, Optional[str]]] = []
    tier3_total: List[Tuple[int, float, Optional[str]]] = []
    unlabeled_amounts: List[Tuple[int, float, Optional[str]]] = []

    for line in effective_lines:
        amts = _extract_line_amounts(line)
        if not amts:
            continue
        # Use the rightmost amount on the line (on receipts, the line total is on the right)
        val_float, raw_curr, pence = amts[-1]
        curr = resolve_curr(raw_curr)

        # Classification order:
        # 1) Pre-discount subtotal ('Balance before Saving', 'Subtotal')
        if _SUBTOTAL_LINE_RE.search(line):
            subtotal_candidates.append((pence, val_float, curr))
            continue

        # 2) Discount / savings / loyalty ('£10 off with Loyalty', 'Your total saving today is', 'You have saved')
        if _DISCOUNT_LINE_RE.search(line):
            discount_candidates.append((pence, val_float, curr))
            continue

        # 3) Change due / cashback
        if _CHANGE_LINE_RE.search(line):
            continue

        # 4) Tax / VAT breakdown (unless 'Total inc VAT')
        if _TAX_BREAKDOWN_LINE_RE.search(line) and not _TOTAL_INC_TAX_RE.search(line):
            continue

        # 5) Cash tendered when change is also present
        if _CASH_TENDER_LINE_RE.search(line) and has_change_line:
            continue

        # 6) Tier 1: Explicit final payable ('Balance to Pay', 'Total to Pay', 'Amount Due', 'Total inc VAT')
        if _TIER1_PAYABLE_LINE_RE.search(line) or _TOTAL_INC_TAX_RE.search(line):
            tier1_payable.append((pence, val_float, curr))
            continue

        # 7) Tier 2: Card / payment tendered ('Card Tendered', 'Amount Tendered')
        if _TIER2_TENDER_LINE_RE.search(line):
            tier2_tender.append((pence, val_float, curr))
            continue

        # 8) Tier 3: Generic 'Total' / 'Balance' / 'Payment'
        if _TIER3_GENERIC_TOTAL_LINE_RE.search(line):
            tier3_total.append((pence, val_float, curr))
            continue

        # 9) Otherwise, item price or unlabeled row
        unlabeled_amounts.append((pence, val_float, curr))

    subtotal_pence = subtotal_candidates[-1][0] if subtotal_candidates else None
    discount_pence = discount_candidates[0][0] if discount_candidates else None
    tendered_pence = tier2_tender[-1][0] if tier2_tender else None

    expected_after_discount: Optional[int] = None
    if subtotal_pence is not None and discount_pence is not None and subtotal_pence > discount_pence:
        expected_after_discount = subtotal_pence - discount_pence

    amount_pence: Optional[int] = None
    original_amount: Optional[float] = None
    detected_currency: Optional[str] = None
    amount_uncertain = False

    def _select_from_tier(
        candidates: List[Tuple[int, float, Optional[str]]],
        corroborating_values: set
    ) -> Tuple[Optional[int], Optional[float], Optional[str], bool]:
        distinct_pence = {c[0] for c in candidates}
        if len(distinct_pence) == 1:
            p, vf, c = candidates[-1]
            return p, vf, c, False
        # Multiple distinct values in the same tier: check if one is corroborated
        for p, vf, c in reversed(candidates):
            if p in corroborating_values:
                return p, vf, c, False
        # Otherwise conflicting totals -> uncertain!
        return None, None, None, True

    corroborators = set()
    if expected_after_discount is not None:
        corroborators.add(expected_after_discount)
    for p, _, _ in tier2_tender:
        corroborators.add(p)
    for p, _, _ in tier1_payable:
        corroborators.add(p)

    if tier1_payable:
        t1_corroborators = {p for p, _, _ in tier2_tender}
        if expected_after_discount is not None:
            t1_corroborators.add(expected_after_discount)
        amount_pence, original_amount, detected_currency, amount_uncertain = _select_from_tier(
            tier1_payable, t1_corroborators
        )
    elif tier2_tender:
        t2_corroborators = {p for p, _, _ in tier3_total}
        if expected_after_discount is not None:
            t2_corroborators.add(expected_after_discount)
        amount_pence, original_amount, detected_currency, amount_uncertain = _select_from_tier(
            tier2_tender, t2_corroborators
        )
    elif tier3_total:
        t3_corroborators = set()
        if expected_after_discount is not None:
            t3_corroborators.add(expected_after_discount)
        if unlabeled_amounts:
            item_sum = sum(p for p, _, _ in unlabeled_amounts)
            if item_sum > 0:
                t3_corroborators.add(item_sum)
                if discount_pence is not None and item_sum > discount_pence:
                    t3_corroborators.add(item_sum - discount_pence)
        amount_pence, original_amount, detected_currency, amount_uncertain = _select_from_tier(
            tier3_total, t3_corroborators
        )
    elif expected_after_discount is not None:
        amount_pence = expected_after_discount
        original_amount = round(expected_after_discount / 100.0, 2)
        detected_currency = subtotal_candidates[-1][2] if subtotal_candidates else None
        amount_uncertain = False
    elif subtotal_candidates and not discount_candidates:
        amount_pence, original_amount, detected_currency = subtotal_candidates[-1]
        amount_uncertain = False
    else:
        # No labeled total/payable/tendered/subtotal found at all
        distinct_unlabeled = {c[0] for c in unlabeled_amounts}
        if len(unlabeled_amounts) == 1 and len(distinct_unlabeled) == 1:
            amount_pence, original_amount, detected_currency = unlabeled_amounts[0]
            amount_uncertain = False
        else:
            # Multiple unlabeled item amounts or zero amounts -> uncertain; do NOT fabricate or guess max()
            amount_pence = None
            original_amount = None
            amount_uncertain = True

    if not detected_currency and has_gbp_evidence:
        detected_currency = "GBP"

    # 4. Date extraction
    parsed_date: Optional[datetime] = None
    date_uncertain = False
    date_pattern = re.compile(
        r"(\b\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}(?:\s+\d{1,2}:\d{2}(?::\d{2})?)?\b"
        r"|\b\d{4}[/.-]\d{1,2}[/.-]\d{1,2}(?:\s+\d{1,2}:\d{2}(?::\d{2})?)?\b"
        r"|\b\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\s+\d{2,4}(?:\s+\d{1,2}:\d{2}(?::\d{2})?)?\b)",
        re.IGNORECASE
    )
    ignore_date_keywords = ["POINTS UP TO", "UP TO", "EXPIRY", "EXPIRES", "VALID", "MEMBER SINCE", "JOINED"]

    effective_tz_str = tz_str
    if not effective_tz_str:
        try:
            from app.core.timezone import get_app_timezone
            effective_tz_str = get_app_timezone()
        except Exception:
            effective_tz_str = "Europe/London"

    found_dates: List[datetime] = []
    for line in reversed(effective_lines):
        upper_line = line.upper()
        if any(k in upper_line for k in ignore_date_keywords):
            continue
        m = date_pattern.search(line)
        if m:
            raw_date_str = m.group(0).replace(".", "/")
            try:
                candidate = date_parser.parse(raw_date_str, dayfirst=True)
                if candidate.tzinfo is None:
                    has_time = bool(re.search(r'\b\d{1,2}:\d{2}(?::\d{2})?\b', raw_date_str))
                    if has_time:
                        from zoneinfo import ZoneInfo
                        loc_tz = ZoneInfo(effective_tz_str)
                        loc_dt = candidate.replace(tzinfo=loc_tz)
                        candidate = loc_dt.astimezone(timezone.utc)
                    else:
                        candidate = candidate.replace(tzinfo=timezone.utc)
                else:
                    candidate = candidate.astimezone(timezone.utc)

                now_year = datetime.now(timezone.utc).year
                if 2000 <= candidate.year <= now_year + 1:
                    found_dates.append(candidate)
            except Exception:
                pass

    if found_dates:
        distinct_days = {d.date() for d in found_dates}
        if len(distinct_days) == 1:
            parsed_date = found_dates[0]
            date_uncertain = False
        else:
            # Multiple conflicting dates on the same receipt -> flag for user review rather than guessing
            parsed_date = found_dates[0]
            date_uncertain = True
    else:
        parsed_date = None
        date_uncertain = True

    confidence = 0.9 if (merchant and amount_pence and parsed_date and not amount_uncertain) else 0.5

    return {
        "merchant": merchant,
        "merchant_uncertain": merchant_uncertain,
        "amount_pence": amount_pence,
        "original_amount": original_amount,
        "detected_currency": detected_currency,
        "amount_uncertain": amount_uncertain,
        "transaction_date": parsed_date,
        "date_uncertain": date_uncertain,
        "confidence": confidence,
        "subtotal_pence": subtotal_pence,
        "discount_pence": discount_pence,
        "tendered_pence": tendered_pence,
        "visual_lines": visual_lines,
    }


class BaseReceiptParser(ABC):
    @abstractmethod
    def parse_receipt(self, image_path: Path, tz_str: Optional[str] = None) -> ReceiptParseResult:
        """
        Parses receipt image into structured fields.
        Returns a ReceiptParseResult.
        """
        pass

    def recognize_text_with_layout(self, image_path: Path) -> List[OCRElement]:
        """
        Returns recognized text elements with bounding box layout info.
        Defaults to returning empty list if parser does not support layout.
        """
        return []


