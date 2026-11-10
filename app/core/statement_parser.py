import csv
import io
import re
from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Dict, Any, Optional, Tuple
from dateutil import parser as date_parser

from app.core.currency import pounds_to_pence
from app.core.direction_inference import infer_statement_direction

COMMON_DATE_FORMATS = [
    "%d/%m/%Y", "%d/%m/%y",
    "%Y-%m-%d",
    "%m/%d/%Y", "%m/%d/%y",
    "%d-%b-%Y", "%d-%b-%y", "%d %b %Y",
    "%d.%m.%Y"
]

CURRENCY_SYMBOLS = {
    "£": "GBP",
    "$": "USD",
    "€": "EUR",
    "¥": "JPY",
    "₹": "INR"
}

def clean_amount_string(val_str: str) -> Tuple[Optional[Decimal], Optional[str], bool]:
    """
    Cleans raw monetary string.
    Returns (cleaned_decimal, detected_currency_symbol_or_code, is_parenthesized_negative).
    """
    if not val_str or not val_str.strip():
        return None, None, False

    raw = val_str.strip()
    detected_currency = None

    # Detect currency symbol
    for sym, code in CURRENCY_SYMBOLS.items():
        if sym in raw:
            detected_currency = code
            raw = raw.replace(sym, "")

    # Detect 3-letter currency code if present
    for code in ["GBP", "USD", "EUR", "CAD", "AUD", "CHF", "JPY", "KWD", "BHD", "OMR", "INR", "NZD", "SGD", "HKD", "SEK", "NOK", "DKK", "PLN", "ZAR", "KRW"]:
        if code in raw.upper():
            detected_currency = code
            raw = re.sub(rf"\b{code}\b", "", raw, flags=re.IGNORECASE)

    raw = raw.strip()

    # Check for accounting parentheses e.g. (12.50)
    is_paren = False
    if raw.startswith("(") and raw.endswith(")"):
        is_paren = True
        raw = raw[1:-1].strip()

    # Remove thousand commas
    raw = raw.replace(",", "")
    # Remove leading plus signs
    if raw.startswith("+"):
        raw = raw[1:].strip()

    try:
        val = Decimal(raw)
        if is_paren:
            val = -abs(val)
        return val, detected_currency, is_paren
    except Exception:
        return None, detected_currency, False

def parse_date_with_format(date_str: str, format_str: Optional[str] = None) -> Optional[datetime]:
    """Parses date string with explicit format or flexible fallback."""
    if not date_str or not date_str.strip():
        return None

    cleaned = date_str.strip()

    # Try explicit format first if provided
    if format_str and format_str not in ("auto", "auto_dayfirst", "auto_monthfirst"):
        # Map simple format names
        fmt = format_str
        if fmt == "DD/MM/YYYY":
            fmt = "%d/%m/%Y"
        elif fmt == "YYYY-MM-DD":
            fmt = "%Y-%m-%d"
        elif fmt == "MM/DD/YYYY":
            fmt = "%m/%d/%Y"
        elif fmt == "DD-Mon-YYYY":
            fmt = "%d-%b-%Y"
        elif fmt == "DD.MM.YYYY":
            fmt = "%d.%m.%Y"

        try:
            dt = datetime.strptime(cleaned, fmt)
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            pass

    # Try common formats
    for fmt in COMMON_DATE_FORMATS:
        try:
            dt = datetime.strptime(cleaned, fmt)
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            pass

    # Fallback to dateutil
    dayfirst = (format_str != "auto_monthfirst")
    try:
        dt = date_parser.parse(cleaned, dayfirst=dayfirst)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None

class StatementParser:
    """
    Provider-agnostic statement parser for CSV/TSV bank, card, and wallet exports.
    """

    @classmethod
    def parse_statement(
        cls,
        file_content: bytes,
        filename: str,
        mapping: Dict[str, Any],
        account_currency: str = "GBP"
    ) -> Dict[str, Any]:
        """
        Parses CSV/TSV statement content according to the provided mapping.
        Isolates malformed rows and returns a detailed execution summary.
        """
        # Decode file with tolerant fallback
        decoded = None
        for enc in ["utf-8-sig", "utf-8", "cp1252", "latin-1"]:
            try:
                decoded = file_content.decode(enc)
                break
            except UnicodeDecodeError:
                continue

        if decoded is None:
            raise ValueError(f"Could not decode {filename} with utf-8, cp1252, or latin-1.")

        delimiter = mapping.get("delimiter", "auto")
        if delimiter == "auto" or not delimiter:
            # Sniff delimiter
            sample = decoded[:2048]
            try:
                sniffer = csv.Sniffer()
                dialect = sniffer.sniff(sample, delimiters=",\t;|")
                delimiter = dialect.delimiter
            except Exception:
                delimiter = ","

        lines = decoded.splitlines()
        skip_rows = int(mapping.get("skip_rows", 0))
        if skip_rows > 0 and len(lines) > skip_rows:
            lines = lines[skip_rows:]

        reader = csv.reader(lines, delimiter=delimiter)
        raw_rows = list(reader)

        if not raw_rows:
            return {
                "source_filename": filename,
                "total_rows": 0,
                "staged_count": 0,
                "skipped_count": 0,
                "skipped_rows": [],
                "items": []
            }

        has_header = mapping.get("has_header", True)
        if has_header:
            header_row = [h.strip() for h in raw_rows[0]]
            data_rows = raw_rows[1:]
            header_index_map = {name.lower(): idx for idx, name in enumerate(header_row)}
        else:
            header_row = []
            data_rows = raw_rows
            header_index_map = {}

        def get_col_index(col_config: Any) -> Optional[int]:
            if col_config is None:
                return None
            if isinstance(col_config, int):
                return col_config
            col_str = str(col_config).strip()
            if col_str.isdigit():
                return int(col_str)
            if has_header:
                return header_index_map.get(col_str.lower())
            return None

        # Auto-detect column mapping if not explicitly configured
        auto_date_idx = None
        auto_merchant_idx = None
        auto_amount_idx = None
        auto_debit_idx = None
        auto_credit_idx = None
        auto_notes_idx = None
        auto_cat_idx = None

        if has_header:
            for idx, col_name in enumerate(header_row):
                cl = col_name.lower()
                if "date" in cl and auto_date_idx is None:
                    auto_date_idx = idx
                elif any(k in cl for k in ["merchant", "description", "payee", "narrative", "details", "memo", "name"]) and auto_merchant_idx is None:
                    auto_merchant_idx = idx
                elif any(k in cl for k in ["amount", "total", "value"]) and "balance" not in cl and auto_amount_idx is None:
                    auto_amount_idx = idx
                elif any(k in cl for k in ["debit", "paid out", "spent", "outflow", "withdrawal"]) and auto_debit_idx is None:
                    auto_debit_idx = idx
                elif any(k in cl for k in ["credit", "paid in", "income", "inflow", "deposit"]) and auto_credit_idx is None:
                    auto_credit_idx = idx
                elif any(k in cl for k in ["note", "reference"]) and auto_notes_idx is None:
                    auto_notes_idx = idx
                elif "category" in cl and auto_cat_idx is None:
                    auto_cat_idx = idx

        date_col_idx = get_col_index(mapping.get("date_column"))
        if date_col_idx is None:
            date_col_idx = auto_date_idx

        merchant_col_idx = get_col_index(mapping.get("merchant_column"))
        if merchant_col_idx is None:
            merchant_col_idx = auto_merchant_idx

        notes_col_idx = get_col_index(mapping.get("notes_column"))
        if notes_col_idx is None:
            notes_col_idx = auto_notes_idx

        category_col_idx = get_col_index(mapping.get("category_column"))
        if category_col_idx is None:
            category_col_idx = auto_cat_idx

        amount_col_idx = get_col_index(mapping.get("amount_column"))
        if amount_col_idx is None:
            amount_col_idx = auto_amount_idx

        debit_col_idx = get_col_index(mapping.get("debit_column"))
        if debit_col_idx is None:
            debit_col_idx = auto_debit_idx

        credit_col_idx = get_col_index(mapping.get("credit_column"))
        if credit_col_idx is None:
            credit_col_idx = auto_credit_idx

        amount_mode = mapping.get("amount_mode")

        date_format = mapping.get("date_format", "auto")

        # Run structural direction inference from headers and data rows
        direction_analysis = infer_statement_direction(
            headers=header_row,
            data_rows=data_rows,
            amount_col_idx=amount_col_idx,
            debit_col_idx=debit_col_idx,
            credit_col_idx=credit_col_idx,
            type_col_idx=None,
            balance_col_idx=None,
            is_card_context=False,
            filename=filename
        )

        parsed_items: List[Dict[str, Any]] = []
        skipped_rows: List[Dict[str, Any]] = []

        for data_idx, row in enumerate(data_rows):
            row_idx = data_idx + 1 + (1 if has_header else 0) + skip_rows
            dir_res = direction_analysis.row_results[data_idx] if data_idx < len(direction_analysis.row_results) else None

            # 1. Skip completely empty rows
            if not row or not any(cell.strip() for cell in row):
                continue

            # 2. Extract Date
            if date_col_idx is None or date_col_idx >= len(row):
                skipped_rows.append({
                    "line_number": row_idx,
                    "reason": "Date column missing or index out of range",
                    "raw": delimiter.join(row)
                })
                continue

            raw_date_str = row[date_col_idx].strip()
            parsed_dt = parse_date_with_format(raw_date_str, date_format)
            if not parsed_dt:
                skipped_rows.append({
                    "line_number": row_idx,
                    "reason": f"Could not parse valid date from '{raw_date_str}'",
                    "raw": delimiter.join(row)
                })
                continue

            # 3. Extract Merchant / Narrative
            merchant = "Unknown Merchant"
            if merchant_col_idx is not None and merchant_col_idx < len(row):
                m_val = row[merchant_col_idx].strip()
                if m_val:
                    merchant = m_val

            # Optional notes
            notes = None
            if notes_col_idx is not None and notes_col_idx < len(row):
                n_val = row[notes_col_idx].strip()
                if n_val:
                    notes = n_val

            # Optional category
            suggested_category = None
            if category_col_idx is not None and category_col_idx < len(row):
                c_val = row[category_col_idx].strip()
                if c_val:
                    suggested_category = c_val

            # 4. Extract Amount & Polarity
            amount_val: Optional[Decimal] = None
            detected_currency: Optional[str] = None
            tx_type = "expense"
            is_uncertain = False

            try:
                if amount_mode == "dual_debit_credit" or (not amount_mode and dir_res and dir_res.evidence_type == "debit_credit_columns"):
                    debit_str = row[debit_col_idx].strip() if debit_col_idx is not None and debit_col_idx < len(row) else ""
                    credit_str = row[credit_col_idx].strip() if credit_col_idx is not None and credit_col_idx < len(row) else ""

                    debit_dec, cur_d, _ = clean_amount_string(debit_str)
                    credit_dec, cur_c, _ = clean_amount_string(credit_str)

                    detected_currency = cur_d or cur_c

                    if debit_dec is not None and debit_dec != 0:
                        amount_val = abs(debit_dec)
                        tx_type = "expense"
                    elif credit_dec is not None and credit_dec != 0:
                        amount_val = abs(credit_dec)
                        tx_type = "income"
                    else:
                        skipped_rows.append({
                            "line_number": row_idx,
                            "reason": "Both debit and credit columns were empty or zero",
                            "raw": delimiter.join(row)
                        })
                        continue

                elif amount_mode == "single_inverted":
                    if amount_col_idx is None or amount_col_idx >= len(row):
                        skipped_rows.append({
                            "line_number": row_idx,
                            "reason": "Amount column missing or index out of range",
                            "raw": delimiter.join(row)
                        })
                        continue

                    raw_amt_str = row[amount_col_idx].strip()
                    amt_dec, detected_curr, _ = clean_amount_string(raw_amt_str)
                    detected_currency = detected_curr

                    if amt_dec is None or amt_dec == 0:
                        skipped_rows.append({
                            "line_number": row_idx,
                            "reason": f"Amount is empty or zero ('{raw_amt_str}')",
                            "raw": delimiter.join(row)
                        })
                        continue

                    amount_val = abs(amt_dec)
                    tx_type = "expense" if amt_dec > 0 else "income"

                elif amount_mode == "single_standard":
                    if amount_col_idx is None or amount_col_idx >= len(row):
                        skipped_rows.append({
                            "line_number": row_idx,
                            "reason": "Amount column missing or index out of range",
                            "raw": delimiter.join(row)
                        })
                        continue

                    raw_amt_str = row[amount_col_idx].strip()
                    amt_dec, detected_curr, _ = clean_amount_string(raw_amt_str)
                    detected_currency = detected_curr

                    if amt_dec is None or amt_dec == 0:
                        skipped_rows.append({
                            "line_number": row_idx,
                            "reason": f"Amount is empty or zero ('{raw_amt_str}')",
                            "raw": delimiter.join(row)
                        })
                        continue

                    amount_val = abs(amt_dec)
                    tx_type = "expense" if amt_dec < 0 else "income"

                else:
                    # Evidence-based direction from infer_statement_direction
                    if amount_col_idx is None or amount_col_idx >= len(row):
                        skipped_rows.append({
                            "line_number": row_idx,
                            "reason": "Amount column missing or index out of range",
                            "raw": delimiter.join(row)
                        })
                        continue

                    raw_amt_str = row[amount_col_idx].strip()
                    amt_dec, detected_curr, _ = clean_amount_string(raw_amt_str)
                    detected_currency = detected_curr

                    if amt_dec is None or amt_dec == 0:
                        skipped_rows.append({
                            "line_number": row_idx,
                            "reason": f"Amount is empty or zero ('{raw_amt_str}')",
                            "raw": delimiter.join(row)
                        })
                        continue

                    amount_val = abs(amt_dec)
                    if dir_res:
                        tx_type = dir_res.transaction_type
                        is_uncertain = dir_res.is_uncertain
                    else:
                        tx_type = "expense"
                        is_uncertain = True

            except Exception as e:
                skipped_rows.append({
                    "line_number": row_idx,
                    "reason": f"Amount calculation error: {str(e)}",
                    "raw": delimiter.join(row)
                })
                continue

            if amount_val is None or amount_val <= 0:
                skipped_rows.append({
                    "line_number": row_idx,
                    "reason": "Calculated amount must be strictly greater than zero",
                    "raw": delimiter.join(row)
                })
                continue

            # 5. Currency Check & Provenance
            currency_conflict = False
            currency_conflict_message = None
            original_amount_val: Optional[float] = None
            original_currency_val: Optional[str] = None
            requires_base = False
            amount_pence = None

            if detected_currency and detected_currency.upper() != account_currency.upper():
                # Primary amount was detected in a foreign currency
                original_currency_val = detected_currency.upper()
                original_amount_val = float(amount_val)
                amount_pence = None
                requires_base = True
                currency_conflict = True
                currency_conflict_message = (
                    f"Statement amount is in foreign currency ({detected_currency} {amount_val}). "
                    f"Enter the actual {account_currency} amount charged/credited by your bank to approve."
                )
            else:
                # Primary amount is in account currency (base currency)
                amount_pence = pounds_to_pence(amount_val)
                # Check narrative for reliable foreign purchase mention (e.g. "HOTEL PARIS 45.00 EUR")
                narrative = f"{merchant} {notes or ''}"
                foreign_match = re.search(r"(\b(?:USD|EUR|JPY|CAD|AUD|CHF|KWD)\b|[€$¥])\s*(\d+(?:[.,]\d+)?)", narrative, re.IGNORECASE)
                amt_str, code_str = None, None
                if foreign_match:
                    code_str, amt_str = foreign_match.group(1), foreign_match.group(2)
                else:
                    rev_match = re.search(r"(\d+(?:[.,]\d+)?)\s*(\b(?:USD|EUR|JPY|CAD|AUD|CHF|KWD)\b)", narrative, re.IGNORECASE)
                    if rev_match:
                        amt_str, code_str = rev_match.group(1), rev_match.group(2)

                if code_str and amt_str:
                    mapped_code = CURRENCY_SYMBOLS.get(code_str, code_str.upper())
                    if mapped_code != account_currency.upper():
                        try:
                            f_val = float(amt_str.replace(",", "."))
                            if f_val > 0:
                                original_currency_val = mapped_code
                                original_amount_val = f_val
                        except ValueError:
                            pass

            # Build candidate record
            candidate = {
                "line_number": row_idx,
                "source_filename": filename,
                "extracted_date": parsed_dt,
                "extracted_merchant": merchant,
                "extracted_amount_pence": amount_pence,
                "suggested_category_name": suggested_category,
                "transaction_type": tx_type,
                "direction_uncertain": is_uncertain,
                "direction_evidence": dir_res.evidence_type if dir_res else "unknown",
                "missing_fields": ["transaction_type"] if is_uncertain else [],
                "notes": notes,
                "currency": account_currency,
                "original_amount": original_amount_val,
                "original_currency": original_currency_val,
                "exchange_rate": None,
                "requires_base_amount": requires_base,
                "currency_conflict": currency_conflict,
                "currency_conflict_message": currency_conflict_message,
                "raw_row_data": delimiter.join(row)
            }
            parsed_items.append(candidate)

        return {
            "source_filename": filename,
            "total_rows": len(raw_rows) - (1 if has_header else 0),
            "staged_count": len(parsed_items),
            "skipped_count": len(skipped_rows),
            "skipped_rows": skipped_rows,
            "direction_summary": {
                "expense_count": direction_analysis.expense_count,
                "income_count": direction_analysis.income_count,
                "uncertain_count": direction_analysis.uncertain_count,
                "evidence_type": direction_analysis.evidence_type,
                "evidence_description": direction_analysis.evidence_description
            },
            "items": parsed_items
        }

