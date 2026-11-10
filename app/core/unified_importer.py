import io
import json
import os
import re
import sys
import shutil
import uuid
import difflib
from collections import Counter
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

import openpyxl
from sqlalchemy.orm import Session

from app.config import STAGING_RECEIPTS_DIR, ARCHIVE_RECEIPTS_DIR, DATA_DIR
from app.models import (
    StagingItem, StagingStatus, Transaction, TransactionType,
    ExpenseNature, Account, AccountType, Category, CategoryType
)
from app.core.categories import expected_category_type_for_transaction
from app.core.file_classifier import classify_uploaded_file, FileClassificationResult
from app.core.statement_parser import StatementParser, clean_amount_string, parse_date_with_format
from app.core.direction_inference import infer_statement_direction
from app.ocr.factory import OCRFactory
from app.ocr.base import OCRElement, BoundingBox, extract_receipt_fields_from_lines, reconstruct_visual_lines
from app.core.currency import get_effective_base_currency, pounds_to_pence
from app.core.timezone import get_app_timezone
from app.core.staging import evaluate_duplicates, approve_staging_item, discard_staging_item
from app.core.backup import get_system_setting, set_system_setting

MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB limit

CURRENCY_SYMBOLS = {
    "£": "GBP",
    "$": "USD",
    "€": "EUR",
    "¥": "JPY",
    "₹": "INR"
}

# Generic financial & statement layout clues (strictly provider-agnostic)
GENERIC_FINANCIAL_SIGNALS = [
    "transactions", "activity", "statement", "balance", "opening balance",
    "closing balance", "payment", "transfer", "deposit", "withdrawal",
    "spent", "received", "paid", "debit", "credit", "account", "card ending",
    "money in", "money out", "cleared", "posted"
]

def _extract_amounts_from_text(text: str) -> List[Tuple[str, Optional[str], Decimal, bool]]:
    """
    Finds all monetary amounts in a block of text.
    Returns [(matched_substring, detected_currency, decimal_value, is_negative)].
    """
    pattern = r'(?i)([-+]?\s*[$£€¥₹]?\s*\d{1,3}(?:,\d{3})*(?:\.\d{1,2})|\(\s*[$£€¥₹]?\s*\d{1,3}(?:,\d{3})*(?:\.\d{1,2})\s*\))'
    matches = []
    for m in re.finditer(pattern, text):
        raw_str = m.group(1).strip()
        dec, curr, is_paren = clean_amount_string(raw_str)
        if dec is not None and abs(dec) > 0:
            is_neg = is_paren or raw_str.startswith("-") or "-" in raw_str
            matches.append((raw_str, curr, dec, is_neg))
    return matches

def _extract_dates_from_text(text: str) -> List[Tuple[str, datetime]]:
    """
    Finds dates in a block of text.
    Handles 'Today', 'Yesterday', '14 Oct', '14/10/2026', '2026-10-14', etc.
    """
    results = []
    now_utc = datetime.now(timezone.utc)

    # Relative dates
    if re.search(r'\btoday\b', text, re.IGNORECASE):
        results.append(("Today", now_utc))
    if re.search(r'\byesterday\b', text, re.IGNORECASE):
        results.append(("Yesterday", now_utc - timedelta(days=1)))

    # Standard date patterns
    date_patterns = [
        r'\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b',
        r'\b\d{4}[/-]\d{1,2}[/-]\d{1,2}\b',
        r'\b\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*(?:\s+\d{2,4})?\b',
        r'\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2}(?:,?\s+\d{2,4})?\b',
    ]
    for pat in date_patterns:
        for m in re.finditer(pat, text, re.IGNORECASE):
            raw_d = m.group(0).strip()
            parsed = parse_date_with_format(raw_d)
            if parsed:
                results.append((raw_d, parsed))
    return results

ACCOUNT_ALIASES_SETTING_KEY = "account_confirmed_aliases"

# Generic terms that do NOT constitute strong evidence of account identity
GENERIC_ACCOUNT_TOKENS = {
    "card", "account", "premium", "debit", "credit", "platinum", "gold",
    "current", "savings", "cash", "pass", "passes", "wallet", "the",
    "and", "of", "in", "for", "a", "an", "p", "sd", "uk", "bank", "banking"
}

# Real masked PAN pattern: supports optional CARD:/PAN: prefix and optional 4-6 digit BIN prefix
# followed by 3-14 mask characters (or explicit "ending in") and 4 trailing digits.
MASKED_PAN_PATTERN = re.compile(
    r'(?:'
    r'(?:\b(?:card(?:\s*(?:no|number|#))?|pan)\s*[:#]?\s*)?(?:\d{4,6}[\s\-]?)?(?:[\*\•\·xX]{3,14}[\s\-]?)+'
    r'|\b(?:ending\s+in|ending|card\s+ending\s+in|card\s+ending)\s*'
    r')(\d{4})\b',
    re.IGNORECASE
)

# Inline terminal/POS segment pattern (strips MID/TID/PID/AID/AUTH/STAN/SEQ tokens when joined on the same visual line)
INLINE_TERMINAL_SEGMENT_RE = re.compile(
    r'\b(?:'
    r'(?:mid|tid|pid|aid|stan|tvr|tsi)\s*[:#]?\s*[\*\•\·xX\dA-Fa-f\-]+'
    r'|(?:merchant|terminal|pos|application|app)\s+id\s*[:#]?\s*[\*\•\·xX\dA-Fa-f\-]+'
    r'|(?:auth(?:orisation|orization)?(?:\s*(?:code|no|#))?|approval\s+code)\s*[:#]?\s*[\*\•\·xX\dA-Za-z\s\-]*?\b\d{3,8}\b'
    r'|(?:app\s+seq|pan\s+seq|seq(?:uence)?)\s*(?:no|#|number)?\s*[:#]?\s*\d+'
    r')',
    re.IGNORECASE
)

_STANDALONE_TERMINAL_LABEL_RE = re.compile(
    r'^(?:mid|tid|pid|aid|stan|auth|auth\s+code|merchant\s+id|terminal\s+id|pos\s+id|app\s+id)\s*[:#]?$',
    re.IGNORECASE
)

def is_terminal_or_receipt_noise(line: str) -> bool:
    """
    Identifies terminal, POS, transaction, and receipt metadata that must NEVER be
    treated as a payment-instrument or card clue, nor searched for masked PANs.
    Covers MID, TID, PID, AID, STAN, auth codes, receipt numbers, sequence numbers,
    POS transaction modes, tender settlement labels, and receipt copy declarations.
    """
    line_clean = line.strip().lower()
    if not line_clean:
        return True

    if line_clean in {
        "mid", "tid", "pid", "aid", "stan", "auth", "total", "subtotal", "vat",
        "sale", "purchase", "refund", "contactless"
    }:
        return True

    terminal_prefixes = (
        "mid:", "mid ", "merchant id", "tid:", "tid ", "terminal id",
        "pid:", "pid ", "pos id", "aid:", "aid ", "application id", "app id",
        "auth code", "auth no", "authorisation code", "authorization code", "auth:", "approval code",
        "receipt no", "receipt #", "rec no", "rec #", "stan:", "stan ",
        "app seq", "pan seq", "seq no", "seq #", "sequence no", "sequence #",
        "response code", "resp code", "batch no", "batch #",
        "trans no", "transaction no", "txn no", "txn id", "transaction id",
        "invoice no", "inv no", "inv #", "ref no", "reference no", "order no", "order #",
        "entry method:", "cryptogram:", "tvr:", "tsi:", "read:", "verified by",
        "card tendered", "amount tendered", "cash tendered", "change due", "change given",
        "cardholder receipt", "cardholder copy", "customer receipt", "customer copy", "merchant copy",
        "please keep", "please retain", "retain this", "payment approved"
    )
    for pfx in terminal_prefixes:
        if line_clean.startswith(pfx):
            return True

    noise_patterns = [
        r'^(?:mid|tid|pid|aid|stan)\s*[:#\s]',
        r'^(?:merchant|terminal|pos|application)\s+id\b',
        r'^(?:auth(?:orisation|orization)?\s*(?:code|no|#)?|approval\s+code)\b',
        r'^(?:receipt|rec|invoice|inv|order|trans(?:action)?|txn|batch|seq(?:uence)?)\s*(?:no|#|id|number)?\s*[:#\s]',
        r'^(?:app\s+seq|pan\s+seq)\b',
        r'^(?:response\s+code|resp\s+code)\b',
        r'^(?:contactless|chip\s*&\s*pin|swipe|pin\s+verified|signature\s+verified|verified\s+by\s+device|no\s+cardholder\s+verification)\b',
        r'\b(?:expresspay\s+contactless|read:\s*contactless)\b',
        r'^(?:\*{1,4}\s*)?(?:cardholder|customer|merchant)\s+(?:copy|receipt)(?:\s*\*{1,4})?\b',
        r'\b(?:cardholder\s+receipt|cardholder\s+copy|customer\s+copy|merchant\s+copy)\b',
        r'\b(?:card\s+tendered|amount\s+tendered|cash\s+tendered|balance\s+to\s+pay|balance\s+before\s+saving)\b',
        r'^(?:please\s+keep|please\s+retain|retain\s+this|thank\s+you|welcome|visit\s+again)\b',
        r'^(?:start\s+date|expiry\s+date|exp\s+date)\b',
    ]
    return any(re.search(pat, line_clean) for pat in noise_patterns)

def get_raw_confirmed_account_associations(db: Session) -> Dict[str, int]:
    """
    Retrieves the raw user-confirmed card-label to account-id associations from local system_settings.
    100% read-only and non-mutating.
    """
    raw = get_system_setting(db, ACCOUNT_ALIASES_SETTING_KEY, "{}")
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}

def get_confirmed_account_associations(db: Session, filter_invalid: bool = True) -> Dict[str, int]:
    """
    Retrieves user-confirmed card-label to account-id associations from local system_settings.
    100% read-only and strictly non-mutating (never modifies system_settings during read).
    When filter_invalid=True (default for matching), ignores terminal noise / invalid keys in-memory.
    """
    raw_dict = get_raw_confirmed_account_associations(db)
    if not filter_invalid:
        return raw_dict
    cleaned = {}
    for k, v in raw_dict.items():
        k_clean = str(k).strip().lower()
        if not k_clean or len(k_clean) < 2:
            continue
        if is_terminal_or_receipt_noise(k_clean) or k_clean in {"mid", "tid", "pid", "aid", "stan", "auth", "total"}:
            continue
        try:
            cleaned[k_clean] = int(v)
        except (ValueError, TypeError):
            continue
    return cleaned

def cleanup_invalid_account_associations(db: Session) -> List[str]:
    """
    Explicit, auditable cleanup action that removes terminal noise and corrupt keys
    (such as 'mid', 'tid', etc.) from system_settings for the active profile database.
    Only mutates system_settings when explicitly called by user/admin action.
    Returns the list of pruned keys.
    """
    raw_dict = get_raw_confirmed_account_associations(db)
    pruned_keys = []
    valid_dict = {}

    for k, v in raw_dict.items():
        k_clean = str(k).strip().lower()
        if not k_clean or len(k_clean) < 2 or is_terminal_or_receipt_noise(k_clean) or k_clean in {"mid", "tid", "pid", "aid", "stan", "auth", "total"}:
            pruned_keys.append(k)
        else:
            try:
                valid_dict[k_clean] = int(v)
            except (ValueError, TypeError):
                pruned_keys.append(k)

    if pruned_keys:
        set_system_setting(db, ACCOUNT_ALIASES_SETTING_KEY, json.dumps(valid_dict, indent=2))

    return pruned_keys

def _expand_card_issuer_tokens(tokens: set) -> set:
    expanded = set(tokens)
    if "amex" in expanded or ("american" in expanded and "express" in expanded):
        expanded.update({"amex", "american", "express"})
    return expanded

def save_confirmed_account_association(
    db: Session,
    card_label: str,
    account_id: int,
    last_4: Optional[str] = None
) -> None:
    """
    Saves a user-confirmed association between a card/statement label and an account ID.
    Learns only from user confirmations/approvals, never from unconfirmed suggestions.
    Scrubs terminal/receipt noise and stores both card label and card-number-specific association.
    """
    if not card_label or not card_label.strip() or not account_id:
        return
    scrubbed_label = INLINE_TERMINAL_SEGMENT_RE.sub(' ', card_label)
    norm_label = re.sub(r'[^a-z0-9\s]', ' ', scrubbed_label.lower()).strip()
    norm_label = re.sub(r'\s+', ' ', norm_label)
    if not norm_label or len(norm_label) < 2:
        return
    if is_terminal_or_receipt_noise(norm_label) or norm_label in {"mid", "tid", "pid", "aid", "stan", "auth", "total"}:
        return
    if re.search(r'\b(?:mid|tid|pid|aid|stan)\b', norm_label):
        return

    # Verify account exists
    acc = db.query(Account).filter(Account.id == account_id).first()
    if not acc:
        return

    associations = get_raw_confirmed_account_associations(db)

    # If last_4 is provided, save card-specific association: e.g. "american express 4321" -> acc.id
    if last_4 and re.fullmatch(r'\d{4}', str(last_4).strip()):
        clean_last_4 = str(last_4).strip()
        associations[f"{norm_label} {clean_last_4}"] = account_id
        associations[f"card {clean_last_4}"] = account_id

    # Check if this card_label is ambiguous across active accounts:
    # If multiple active accounts match this label (e.g. 2 Amex accounts), do NOT save the bare label
    # without digits, because that would override the other account for cards without digits!
    active_accounts = db.query(Account).filter(Account.is_active == True).all()
    label_tokens = _expand_card_issuer_tokens(set(norm_label.split()))
    matching_accounts = []
    for a in active_accounts:
        a_tokens = _expand_card_issuer_tokens(set(re.sub(r'[^a-z0-9\s]', ' ', a.name.lower()).split()))
        shared = {t for t in (label_tokens & a_tokens) if t not in GENERIC_ACCOUNT_TOKENS and len(t) >= 2}
        if shared:
            matching_accounts.append(a)

    if len(matching_accounts) <= 1 or not last_4:
        # Bare label is safe to save if there's only 1 matching account or no last-4 was provided
        associations[norm_label] = account_id

    set_system_setting(db, ACCOUNT_ALIASES_SETTING_KEY, json.dumps(associations, indent=2))

def delete_confirmed_account_association(db: Session, card_label: str) -> bool:
    """
    Removes a user-confirmed association by card label (supports removing invalid or noise keys as well).
    """
    norm_label = re.sub(r'[^a-z0-9\s]', ' ', card_label.lower()).strip()
    norm_label = re.sub(r'\s+', ' ', norm_label)
    raw_label = card_label.strip()
    associations = get_raw_confirmed_account_associations(db)
    
    # Try exact match, norm_label, or lowercase
    key_to_del = None
    for k in [raw_label, norm_label, raw_label.lower()]:
        if k in associations:
            key_to_del = k
            break
            
    if key_to_del:
        del associations[key_to_del]
        set_system_setting(db, ACCOUNT_ALIASES_SETTING_KEY, json.dumps(associations, indent=2))
        return True
    return False

def list_confirmed_account_associations(db: Session, include_invalid: bool = True) -> List[Dict[str, Any]]:
    """
    Returns an inspectable list of confirmed associations with account details and validity annotation.
    100% read-only and non-mutating.
    """
    associations = get_raw_confirmed_account_associations(db)
    results = []
    for label, acc_id in associations.items():
        label_clean = str(label).strip().lower()
        is_invalid = (
            not label_clean or len(label_clean) < 2 or
            is_terminal_or_receipt_noise(label_clean) or
            label_clean in {"mid", "tid", "pid", "aid", "stan", "auth", "total"}
        )
        if not include_invalid and is_invalid:
            continue
        acc = db.query(Account).filter(Account.id == acc_id).first()
        results.append({
            "card_label": label,
            "account_id": acc_id,
            "account_name": acc.name if acc else "Unknown Account",
            "account_currency": acc.currency if acc else "GBP",
            "is_valid": not is_invalid,
            "validation_note": "Terminal/POS noise; ignored during matching" if is_invalid else "Active confirmed association"
        })
    return results

def determine_transaction_direction(
    matched_amount_str: str,
    is_neg: bool,
    merchant_text: Optional[str] = None,
    line_text: Optional[str] = None,
    context: str = "screenshot"
) -> Tuple[str, bool]:
    """
    Determines transaction direction ('expense' vs 'income') and whether it is ambiguous.
    Uses signs (+ vs -), directional keywords, and context clues.
    In wallet / statement screenshots, default unmarked entries are expenses.
    """
    raw_str = (matched_amount_str or "").strip()
    m_text = (merchant_text or "").lower()
    l_text = (line_text or "").lower()
    combined_text = f"{m_text} {l_text}"

    # 1. Explicit sign on amount string
    if "+" in raw_str:
        return "income", False
    if is_neg or "-" in raw_str or (raw_str.startswith("(") and raw_str.endswith(")")):
        return "expense", False

    # 2. Strong directional keywords
    clean_credit_text = re.sub(r'\bcredit\s+card\b', '', combined_text)
    credit_keywords = [
        "refund", "cashback", "reversal", "reward", "rebate", "money in",
        "paid in", "deposit", "salary", "payroll", "received from", "payment from"
    ]
    if any(kw in clean_credit_text for kw in credit_keywords) or any(re.search(r'\b' + re.escape(kw) + r'\b', clean_credit_text) for kw in ["credit", "interest"]):
        return "income", False

    clean_debit_text = re.sub(r'\bdebit\s+card\b', '', combined_text)
    debit_keywords = [
        "purchase", "spent", "paid out", "money out", "payment to",
        "charge", "fee", "withdrawal", "pos purchase", "direct debit", "standing order"
    ]
    if any(kw in clean_debit_text for kw in debit_keywords) or re.search(r'\bdebit\b', clean_debit_text):
        return "expense", False

    # 3. Contextual defaults
    if context in ("screenshot", "receipt"):
        # Flag ambiguous entries (e.g. transfer or adjustment without direction clues)
        if any(re.search(r'\b' + re.escape(w) + r'\b', combined_text) for w in ["transfer", "adjustment"]):
            return "expense", True
        return "expense", False

    return "expense", False

def is_merchant_line(line: str, merchant_name: Optional[str]) -> bool:
    """
    Checks if an OCR line substantially represents the detected merchant name.
    Uses normalized vendor matching and sequence similarity to avoid false positives
    from single shared geographic or generic words.
    """
    if not line or not merchant_name:
        return False
    norm_line = normalize_vendor_name(line)
    norm_merchant = normalize_vendor_name(merchant_name)
    if not norm_line or not norm_merchant:
        return False
    if norm_line == norm_merchant:
        return True
    if len(norm_line) >= 4 and len(norm_merchant) >= 4:
        if norm_line in norm_merchant or norm_merchant in norm_line:
            return True
        ratio = difflib.SequenceMatcher(None, norm_line, norm_merchant).ratio()
        if ratio >= 0.80:
            return True
    return False

def extract_card_or_account_clues(
    ocr_lines: List[str],
    active_account_names: Optional[List[str]] = None,
    ocr_elements: Optional[List[Any]] = None,
    merchant_name: Optional[str] = None,
    confirmed_association_labels: Optional[List[str]] = None
) -> Tuple[List[str], Optional[str]]:
    """
    Extracts candidate card/account label strings and visible last-4 digits from OCR lines.
    Distinguishes payment-instrument evidence from merchant, terminal, transaction, and receipt identifiers:
    1. Reconstructs 2D visual lines when bounding boxes are available so split labels (e.g. 'MID:' + '*******0411')
       are rejoined before classification.
    2. Filters out terminal and receipt noise (MID, TID, PID, AID, STAN, auth codes, receipt numbers, etc.)
       and blocks any 4-digit suffix associated with a terminal/merchant ID from ever being treated as a card number.
    3. Identifies genuine masked payment-card PANs (e.g. CARD: 370000XXXXX4242, ***********4321, ending in 4321)
       and extracts last 4 digits.
    4. Associates adjacent issuer text directly with the masked number, or identifies account clues matching
       active account names or confirmed local associations.
    5. Never treats merchant names, transaction amounts, or terminal IDs as card labels.
    """
    candidates: List[str] = []
    last_4: Optional[str] = None

    account_structural_words = {
        "card", "account", "debit", "credit",
        "current", "savings", "pass", "passes", "bank", "banking"
    }

    ignore_patterns = [
        r'^\d{1,2}:\d{2}', r'^\d{1,3}%', r'^(?:lte|5g|4g|wifi|volte)\b',
        r'^(?:google|apple)\s+wallet\b', r'^(?:activity|recent activity|transactions|passes|cards|history)\b',
        r'^(?:done|close|back|cancel|edit|search|settings|details)\b',
        r'^(?:today|yesterday)\b', r'^check\s+your\s+bank\s+statement\b'
    ]

    raw_cleaned: List[str] = [l.strip() for l in (ocr_lines or []) if l and l.strip()]
    visual_lines = reconstruct_visual_lines(ocr_elements, raw_cleaned) if ocr_elements else []
    cleaned_lines: List[str] = [l.strip() for l in (visual_lines if visual_lines else raw_cleaned) if l and l.strip()]

    # Collect 4-digit suffixes belonging to terminal/merchant/auth identifiers so they can NEVER be used as card last_4
    terminal_blocked_last4: set = set()
    for idx_r, r_line in enumerate(raw_cleaned):
        for seg_m in INLINE_TERMINAL_SEGMENT_RE.finditer(r_line):
            for d4 in re.findall(r'(\d{4})\b', seg_m.group(0)):
                terminal_blocked_last4.add(d4)
        if is_terminal_or_receipt_noise(r_line):
            for d4 in re.findall(r'(\d{4})\b', r_line):
                terminal_blocked_last4.add(d4)
        # Check if a bare masked-digits token in raw_lines is immediately adjacent to a standalone MID:/TID:/PID:/AID: label
        if re.fullmatch(r'[\*\•\·xX\s\-]*\d{4}', r_line):
            prev_r = raw_cleaned[idx_r - 1] if idx_r > 0 else ""
            next_r = raw_cleaned[idx_r + 1] if idx_r + 1 < len(raw_cleaned) else ""
            if (
                _STANDALONE_TERMINAL_LABEL_RE.match(prev_r)
                or _STANDALONE_TERMINAL_LABEL_RE.match(next_r)
                or is_terminal_or_receipt_noise(prev_r)
            ):
                for d4 in re.findall(r'(\d{4})\b', r_line):
                    terminal_blocked_last4.add(d4)

    for v_line in cleaned_lines:
        for seg_m in INLINE_TERMINAL_SEGMENT_RE.finditer(v_line):
            for d4 in re.findall(r'(\d{4})\b', seg_m.group(0)):
                terminal_blocked_last4.add(d4)
        if is_terminal_or_receipt_noise(v_line):
            for d4 in re.findall(r'(\d{4})\b', v_line):
                terminal_blocked_last4.add(d4)

    # Pass 1: Scan for real masked PAN and last 4 (prioritize explicit CARD:/PAN:/ending lines first)
    masked_pan_line_idx = -1
    explicit_card_indices = [
        i for i, l in enumerate(cleaned_lines)
        if re.search(r'\b(?:card|pan|ending)\b', l, re.IGNORECASE)
    ]
    other_indices = [i for i in range(len(cleaned_lines)) if i not in explicit_card_indices]

    for idx in explicit_card_indices + other_indices:
        line = cleaned_lines[idx]
        if is_terminal_or_receipt_noise(line):
            continue
        if any(re.search(pat, line, re.IGNORECASE) for pat in ignore_patterns):
            continue

        # Strip inline terminal segments (e.g. 'AUTH: • 0050' on the same visual row as 'CARD: 370000XXXXX4242')
        line_without_terminal = INLINE_TERMINAL_SEGMENT_RE.sub(' ', line).strip()
        if not line_without_terminal or is_terminal_or_receipt_noise(line_without_terminal):
            continue

        # Also skip bare masked numbers in 1D raw_lines if immediately adjacent to a standalone MID:/TID: label
        if not ocr_elements and re.fullmatch(r'[\*\•\·xX\s\-]*\d{4}', line_without_terminal):
            prev_l = cleaned_lines[idx - 1] if idx > 0 else ""
            next_l = cleaned_lines[idx + 1] if idx + 1 < len(cleaned_lines) else ""
            if _STANDALONE_TERMINAL_LABEL_RE.match(prev_l) or _STANDALONE_TERMINAL_LABEL_RE.match(next_l):
                continue

        pan_match = MASKED_PAN_PATTERN.search(line_without_terminal)
        if pan_match:
            cand_last_4 = pan_match.group(1)
            if cand_last_4 in terminal_blocked_last4:
                continue
            last_4 = cand_last_4
            masked_pan_line_idx = idx
            # If the same line has card label text alongside masked PAN:
            remainder = MASKED_PAN_PATTERN.sub('', line_without_terminal).strip()
            remainder = re.sub(r'^\b(?:card(?:\s*(?:no|number|#))?|pan)\b\s*[:#]?\s*', '', remainder, flags=re.IGNORECASE).strip()
            remainder = re.sub(r'^[•\-\*\s:]+|[•\-\*\s:]+$', '', remainder).strip()
            if (
                len(remainder) >= 3
                and not remainder.isdigit()
                and not _extract_amounts_from_text(remainder)
                and not is_terminal_or_receipt_noise(remainder)
            ):
                candidates.append(remainder)
            break

    # If masked PAN was on a line without card label text (e.g. "CARD: 370000XXXXX4242" or "***********4321"):
    # Associate directly with adjacent non-noise issuer text (preceding lines first, then succeeding line)
    if masked_pan_line_idx >= 0 and not candidates:
        for offset in [-1, -2, -3, 1, 2]:
            adj_idx = masked_pan_line_idx + offset
            if 0 <= adj_idx < len(cleaned_lines):
                adj_line = INLINE_TERMINAL_SEGMENT_RE.sub(' ', cleaned_lines[adj_idx]).strip()
                if not adj_line or is_terminal_or_receipt_noise(adj_line):
                    continue
                if any(re.search(pat, adj_line, re.IGNORECASE) for pat in ignore_patterns):
                    continue
                if _extract_amounts_from_text(adj_line) or _extract_dates_from_text(adj_line):
                    continue
                if is_merchant_line(adj_line, merchant_name):
                    continue
                if re.fullmatch(r'[\*\•\·xX\d\s\-:]+', adj_line):
                    continue

                cleaned_adj = re.sub(r'^[•\-\*\s:]+|[•\-\*\s:]+$', '', adj_line).strip()
                if len(cleaned_adj) >= 3 and not cleaned_adj.isdigit() and re.search(r'[a-zA-Z]{2,}', cleaned_adj):
                    candidates.append(cleaned_adj)
                    break

    # Pass 2: Scan remaining lines for card clues if none found or to supplement
    for line in cleaned_lines:
        line_scrubbed = INLINE_TERMINAL_SEGMENT_RE.sub(' ', line).strip()
        if not line_scrubbed or is_terminal_or_receipt_noise(line_scrubbed):
            continue
        if any(re.search(pat, line_scrubbed, re.IGNORECASE) for pat in ignore_patterns):
            continue
        if _extract_amounts_from_text(line_scrubbed) or _extract_dates_from_text(line_scrubbed):
            continue
        if is_merchant_line(line_scrubbed, merchant_name):
            continue

        line_lower = line_scrubbed.lower()
        line_tokens = set(re.sub(r'[^a-z0-9\s]', ' ', line_lower).split())

        has_account_words = any(re.search(r'\b' + re.escape(w) + r'\b', line_lower) for w in account_structural_words)
        matches_existing_account = False
        if active_account_names:
            for acc_name in active_account_names:
                acc_tokens = set(re.sub(r'[^a-z0-9\s]', ' ', acc_name.lower()).split())
                shared_tokens = {t for t in (line_tokens & acc_tokens) if t not in GENERIC_ACCOUNT_TOKENS and len(t) >= 2}
                if shared_tokens:
                    matches_existing_account = True
                    break

        is_confirmed = False
        if confirmed_association_labels:
            line_norm = re.sub(r'[^a-z0-9\s]', ' ', line_lower).strip()
            line_norm = re.sub(r'\s+', ' ', line_norm)
            for cal in confirmed_association_labels:
                if cal == line_norm or cal in line_norm or line_norm in cal:
                    is_confirmed = True
                    break

        if has_account_words or matches_existing_account or is_confirmed:
            cleaned = MASKED_PAN_PATTERN.sub('', line_scrubbed).strip()
            cleaned = re.sub(r'^\b(?:card(?:\s*(?:no|number|#))?|pan)\b\s*[:#]?\s*', '', cleaned, flags=re.IGNORECASE).strip()
            cleaned = re.sub(r'^[•\-\*\s:]+|[•\-\*\s:]+$', '', cleaned).strip()
            if (
                len(cleaned) >= 3
                and not cleaned.isdigit()
                and not is_terminal_or_receipt_noise(cleaned)
                and cleaned not in candidates
            ):
                candidates.append(cleaned)

    return candidates, last_4

ACCOUNT_CONFIDENCE_THRESHOLDS = {
    "cautious": 0.90,    # Very cautious: only prefill confirmed associations (1.0), card last-4 digits (0.95), or exact distinctive token matches (>=0.90)
    "balanced": 0.75,    # Balanced: clear, reasonably strong distinctive token matches (>=0.75)
    "permissive": 0.60,  # More suggestions: allow broader distinctive token overlap (>=0.60), clearly marked for review
}

def match_account_from_context(
    db: Session,
    ocr_lines: List[str],
    original_filename: str = "",
    ocr_elements: Optional[List[Any]] = None,
    merchant_name: Optional[str] = None,
    confidence_level: Optional[str] = None
) -> Tuple[Optional[int], Optional[str], Optional[str]]:
    """
    Matches an active Account from extracted OCR lines or filename using general, explainable evidence:
    1. User-confirmed local associations (learned from past user approvals).
    2. Extracted card identifiers and visible last-4 digits.
    3. Distinctive normalized token similarity (generic terms like 'card', 'account', 'premium' are excluded).
    Requires the configured confidence threshold (Very Cautious=0.90, Balanced=0.75, More Suggestions=0.60)
    and strictly rejects ambiguous matches across all thresholds.
    Never auto-creates, renames, or silently selects accounts on weak matches.
    """
    active_accounts = db.query(Account).filter(Account.is_active == True).all()
    if not active_accounts:
        return None, None, None

    if not confidence_level:
        confidence_level = get_system_setting(db, "import_confidence_account", "balanced")
    confidence_threshold = ACCOUNT_CONFIDENCE_THRESHOLDS.get(str(confidence_level).strip().lower(), 0.75)

    active_account_names = [a.name for a in active_accounts]
    confirmed_associations = get_confirmed_account_associations(db)
    confirmed_labels = list(confirmed_associations.keys())

    cand_labels, last_4 = extract_card_or_account_clues(
        ocr_lines=ocr_lines,
        active_account_names=active_account_names,
        ocr_elements=ocr_elements,
        merchant_name=merchant_name,
        confirmed_association_labels=confirmed_labels
    )
    if not cand_labels and original_filename:
        stem = Path(original_filename).stem
        if len(stem) >= 3 and not is_terminal_or_receipt_noise(stem):
            cand_labels.append(stem)

    # 1. User-confirmed local associations (highest confidence = 1.0)
    confirmed_associations = get_confirmed_account_associations(db)

    # If last-4 digits were extracted, check card-number-specific association first
    if last_4:
        for cand in cand_labels:
            norm_cand_last4 = re.sub(r'[^a-z0-9\s]', ' ', f"{cand} {last_4}".lower()).strip()
            norm_cand_last4 = re.sub(r'\s+', ' ', norm_cand_last4)
            for assoc_label, acc_id in confirmed_associations.items():
                if assoc_label == norm_cand_last4 or assoc_label in norm_cand_last4 or norm_cand_last4 in assoc_label:
                    acc = db.query(Account).filter(Account.id == acc_id, Account.is_active == True).first()
                    if acc:
                        return acc.id, acc.name, f"Matched user-confirmed association '{assoc_label}' -> '{acc.name}'"

        card_last4_key = f"card {last_4}"
        if card_last4_key in confirmed_associations:
            acc_id = confirmed_associations[card_last4_key]
            acc = db.query(Account).filter(Account.id == acc_id, Account.is_active == True).first()
            if acc:
                return acc.id, acc.name, f"Matched user-confirmed card last-4 '{last_4}' -> '{acc.name}'"

    # Check bare candidate labels against confirmed associations
    for cand in cand_labels:
        norm_cand = re.sub(r'[^a-z0-9\s]', ' ', cand.lower()).strip()
        norm_cand = re.sub(r'\s+', ' ', norm_cand)
        for assoc_label, acc_id in confirmed_associations.items():
            if assoc_label == norm_cand:
                acc = db.query(Account).filter(Account.id == acc_id, Account.is_active == True).first()
                if acc:
                    return acc.id, acc.name, f"Matched user-confirmed association '{assoc_label}' -> '{acc.name}'"

    # 2. Match by visible last-4 digits / card identifiers (confidence = 0.95)
    if last_4:
        digit_matches = [acc for acc in active_accounts if last_4 in acc.name]
        if len(digit_matches) == 1:
            acc = digit_matches[0]
            return acc.id, acc.name, f"Matched card last-4 digits '{last_4}' to account '{acc.name}'"
        elif len(digit_matches) > 1:
            names = ", ".join(a.name for a in digit_matches)
            return None, None, f"Ambiguous match: multiple accounts contain last-4 digits '{last_4}' ({names})"

    # 3. Match by distinctive token similarity
    for cand in cand_labels:
        cand_norm = re.sub(r'[^a-z0-9\s]', ' ', cand.lower())
        cand_tokens = _expand_card_issuer_tokens(set(cand_norm.split()))
        cand_distinctive = {t for t in cand_tokens if t not in GENERIC_ACCOUNT_TOKENS and len(t) >= 2}

        if not cand_distinctive:
            # Only generic words were present (e.g. 'card', 'premium') -> do not match on weak generic evidence
            continue

        scored_candidates: List[Tuple[Account, float, str]] = []
        for acc in active_accounts:
            acc_norm = re.sub(r'[^a-z0-9\s]', ' ', acc.name.lower())
            acc_tokens = _expand_card_issuer_tokens(set(acc_norm.split()))
            acc_distinctive = {t for t in acc_tokens if t not in GENERIC_ACCOUNT_TOKENS and len(t) >= 2}

            if not acc_distinctive:
                continue

            shared = cand_distinctive & acc_distinctive
            if not shared:
                # Check for distinctive multi-character substring match (>= 4 chars)
                if any(len(d) >= 4 and (d in cand_norm or cand_norm in d) for d in acc_distinctive):
                    score = 0.80
                    scored_candidates.append((acc, score, "distinctive name match in card label"))
                continue

            # Score based on exactness and distinctive token overlap
            if cand_norm.strip() == acc_norm.strip():
                score = 0.95
            elif acc_tokens.issubset(cand_tokens):
                score = 0.90
            elif len(shared) >= 2:
                score = 0.85
            else:
                score = 0.75

            scored_candidates.append((acc, score, f"shared distinctive tokens ({', '.join(sorted(shared))})"))

        if scored_candidates:
            scored_candidates.sort(key=lambda x: x[1], reverse=True)
            top_score = scored_candidates[0][1]

            if top_score < confidence_threshold:
                # Weak evidence below profile confidence threshold; leave unassigned for review
                continue

            # Check for ambiguity: if runner-up is within 0.05 margin, reject match
            top_matches = [x for x in scored_candidates if x[1] >= top_score - 0.05]
            if len(top_matches) == 1:
                best_acc, _, reason = top_matches[0]
                return best_acc.id, best_acc.name, f"Matched card '{cand}' to account '{best_acc.name}' ({reason})"
            else:
                names = ", ".join(x[0].name for x in top_matches)
                last4_suffix = f" (ending in {last_4})" if last_4 else ""
                return None, None, f"Ambiguous match: multiple accounts matched card '{cand}'{last4_suffix} with similar confidence ({names})"

    if cand_labels:
        last4_suffix = f" (ending in {last_4})" if last_4 else ""
        return None, None, f"Detected card label '{cand_labels[0]}'{last4_suffix} but no confident account match met the '{confidence_level}' confidence threshold."

    return None, None, None

COMMERCE_NOISE_TOKENS = {
    "ltd", "limited", "inc", "llc", "plc", "co", "corp", "corporation",
    "stores", "store", "supermarket", "express", "local", "uk", "online",
    "retail", "shop", "com", "gb", "london", "vendor", "services", "service",
    "group", "holdings", "enterprises", "direct", "bill", "billing"
}

def normalize_vendor_name(merchant: str) -> str:
    """
    Normalizes a merchant/vendor name:
    1. Lowercases and strips punctuation.
    2. Strips common business entity suffixes (Ltd, Inc, LLC, Store, Stores, Express, Local, Online, etc.).
    3. Collapses whitespace.
    """
    if not merchant:
        return ""
    text = re.sub(r'[^a-z0-9\s]', ' ', merchant.lower())
    tokens = text.split()
    cleaned_tokens = [t for t in tokens if t not in COMMERCE_NOISE_TOKENS]
    return " ".join(cleaned_tokens if cleaned_tokens else tokens)

def get_local_semantic_embedding():
    """
    Returns macOS NaturalLanguage framework's NLEmbedding for English if available.
    100% offline, on-device Apple Silicon embedding model.
    Returns None on non-macOS or if unavailable.
    """
    if sys.platform != "darwin":
        return None
    try:
        import objc
        from Foundation import NSBundle
        bundle = NSBundle.bundleWithPath_("/System/Library/Frameworks/NaturalLanguage.framework")
        if bundle and bundle.load():
            NLEmbedding = objc.lookUpClass("NLEmbedding")
            if NLEmbedding:
                return NLEmbedding.wordEmbeddingForLanguage_("en")
    except Exception:
        pass
    return None

CATEGORY_CONFIDENCE_THRESHOLDS = {
    "cautious": 0.85,    # Very cautious: prefill only high-confidence matches (past history >=0.85, exact category name in merchant 0.95, or exact context tokens)
    "balanced": 0.45,    # Balanced: clear, reasonably strong matches (>=0.45, including standard on-device semantic embeddings)
    "permissive": 0.35,  # More suggestions: allow weaker semantic embeddings and context associations (>=0.35), clearly marked for review
}

def suggest_category_from_history(
    db: Session,
    merchant: Optional[str],
    amount_pence: Optional[int] = None,
    tx_type: str = "expense",
    ocr_lines: Optional[List[str]] = None,
    context_text: Optional[str] = None,
    confidence_level: Optional[str] = None
) -> Tuple[Optional[int], Optional[str], ExpenseNature, Optional[str]]:
    """
    Suggests an active Category using:
    1. Primary learning source: approved transactions in the database with active categories.
    2. Normalized vendor similarity (difflib SequenceMatcher >= threshold) to tolerate small OCR typos.
    3. Direct category name in merchant string.
    4. Receipt context tokens (from tagline, item descriptions, etc.) matched against category
       names and user-editable category descriptions via token matching and on-device
       semantic embeddings (Apple NaturalLanguage framework).
    5. Leaves uncategorised for user review if ambiguous or confidence < threshold.
       Never infers category from amount alone. Strictly no hardcoded merchant rules.
    """
    try:
        tx_type_enum = tx_type if isinstance(tx_type, TransactionType) else TransactionType(str(tx_type or "expense").strip().lower())
    except ValueError:
        tx_type_enum = TransactionType.EXPENSE

    expected_cat_type = expected_category_type_for_transaction(tx_type_enum)
    if expected_cat_type is None:
        return None, None, ExpenseNature.UNCLASSIFIED, None

    active_categories = {
        c.id: c
        for c in db.query(Category)
        .filter(Category.is_active == True, Category.category_type == expected_cat_type)
        .all()
    }
    if not active_categories:
        return None, None, ExpenseNature.UNCLASSIFIED, None

    def _effective_nature(cat_obj: Category) -> ExpenseNature:
        if expected_cat_type == CategoryType.INCOME:
            return ExpenseNature.UNCLASSIFIED
        return cat_obj.default_expense_nature or ExpenseNature.UNCLASSIFIED

    if not confidence_level:
        confidence_level = get_system_setting(db, "import_confidence_category", "balanced")
    confidence_threshold = CATEGORY_CONFIDENCE_THRESHOLDS.get(str(confidence_level).strip().lower(), 0.45)

    cand_norm = normalize_vendor_name(merchant) if merchant else ""

    # 1. Historical approved transactions match (scoped strictly to matching transaction direction & non-deleted rows)
    if cand_norm and len(cand_norm) >= 2:
        approved_txs = (
            db.query(Transaction)
            .filter(
                Transaction.deleted_at.is_(None),
                Transaction.transaction_type == tx_type_enum,
                Transaction.merchant.isnot(None),
                Transaction.category_id.isnot(None),
            )
            .order_by(Transaction.id.desc())
            .all()
        )
        valid_history = [tx for tx in approved_txs if tx.category_id in active_categories]

        matches: List[Tuple[Transaction, float]] = []
        for tx in valid_history:
            hist_norm = normalize_vendor_name(tx.merchant)
            if not hist_norm:
                continue

            if cand_norm == hist_norm:
                matches.append((tx, 1.0))
                continue

            if len(cand_norm) >= 4 and len(hist_norm) >= 4:
                if cand_norm in hist_norm or hist_norm in cand_norm:
                    matches.append((tx, 0.90))
                    continue

            ratio = difflib.SequenceMatcher(None, cand_norm, hist_norm).ratio()
            min_ratio = max(0.80, confidence_threshold)
            if ratio >= min_ratio:
                matches.append((tx, ratio))

        if matches:
            cat_counts = Counter(tx.category_id for tx, _ in matches)
            total_matches = len(matches)

            if len(cat_counts) == 1:
                best_cat_id = list(cat_counts.keys())[0]
                cat = active_categories[best_cat_id]
                return cat.id, cat.name, _effective_nature(cat), f"Learned from {total_matches} approved past transaction(s) ({tx_type_enum.value})"

            if amount_pence is not None:
                amount_matched_cats = Counter()
                for tx, _ in matches:
                    if tx.amount_pence and abs(tx.amount_pence - amount_pence) <= max(50, int(0.10 * tx.amount_pence)):
                        amount_matched_cats[tx.category_id] += 1

                if len(amount_matched_cats) == 1:
                    best_cat_id = list(amount_matched_cats.keys())[0]
                    cat = active_categories[best_cat_id]
                    return cat.id, cat.name, _effective_nature(cat), f"Learned from past transactions ({tx_type_enum.value}) matching amount pattern (£{amount_pence/100:.2f})"

            top_cat_id, top_count = cat_counts.most_common(1)[0]
            if (top_count / total_matches) >= 0.75:
                cat = active_categories[top_cat_id]
                return cat.id, cat.name, _effective_nature(cat), f"Learned from majority of past transactions ({top_count}/{total_matches}, {tx_type_enum.value})"

            return None, None, ExpenseNature.UNCLASSIFIED, f"Conflicting history across past transactions ({total_matches} {tx_type_enum.value} entries split). Left for manual review."

    # 2. Direct active category name in merchant string
    if cand_norm:
        for cat in active_categories.values():
            cat_lower = cat.name.lower()
            if len(cat_lower) >= 3 and re.search(r'\b' + re.escape(cat_lower) + r'\b', cand_norm):
                return cat.id, cat.name, _effective_nature(cat), f"Matched {expected_cat_type.value} category name in merchant '{merchant}'"

    # 3. Contextual Token and Semantic Matching from Receipt Context (Taglines, Items, Descriptions)
    context_lines = []
    if merchant:
        context_lines.append(merchant)
    if ocr_lines:
        context_lines.extend(ocr_lines)
    if context_text:
        context_lines.extend(context_text.splitlines())

    EXCLUDE_CONTEXT_WORDS = {
        "total", "subtotal", "amount", "balance", "change", "due", "cash", "payment",
        "card", "date", "time", "vat", "tax", "gbp", "usd", "eur", "visa", "amex",
        "mastercard", "tel", "telephone", "phone", "copy", "customer", "merchant",
        "receipt", "invoice", "statement", "order", "item", "qty", "price", "net",
        "gross", "paid", "bill", "billing", "welcome", "please", "thank", "you",
        "reap", "points", "reward", "rewards", "visit", "again", "store", "stores",
        "services", "service", "limited", "ltd", "inc", "llc", "plc", "co", "corp",
        "the", "and", "for", "with", "from", "your", "our", "all", "are", "have",
        "today", "yesterday", "done", "close", "back", "cancel", "edit", "details",
        "credit", "debit", "tendered", "saving", "saved", "savings", "discount",
        "contactless", "chip", "pin", "auth", "terminal", "cardholder", "account",
        "before", "retain", "records", "reg", "off"
    }

    context_tokens = []
    for line in context_lines:
        if is_terminal_or_receipt_noise(line):
            continue
        if _extract_amounts_from_text(line) and not re.search(r'[a-zA-Z]{4,}', line):
            continue
        raw_words = re.sub(r'[^a-z0-9\s]', ' ', line.lower()).split()
        for w in raw_words:
            if len(w) >= 3 and w not in EXCLUDE_CONTEXT_WORDS and w not in COMMERCE_NOISE_TOKENS and not w.isdigit():
                if w not in context_tokens:
                    context_tokens.append(w)

    if context_tokens:
        from app.core.categories import get_category_descriptions
        category_descriptions = get_category_descriptions(db)

        scored_cats: List[Tuple[Category, float, str]] = []
        emb = get_local_semantic_embedding()

        for cat in active_categories.values():
            cat_desc = category_descriptions.get(cat.id, "")
            if hasattr(cat, "description") and cat.description:
                cat_desc = f"{cat.description} {cat_desc}".strip()

            cat_name_words = [w for w in re.sub(r'[^a-z0-9\s]', ' ', cat.name.lower()).split() if len(w) >= 3 and w not in EXCLUDE_CONTEXT_WORDS]
            cat_desc_words = [w for w in re.sub(r'[^a-z0-9\s]', ' ', cat_desc.lower()).split() if len(w) >= 3 and w not in EXCLUDE_CONTEXT_WORDS]

            best_cat_score = 0.0
            best_cat_evidence = ""

            # Exact or prefix token match in category name
            for c_tok in context_tokens:
                for nw in cat_name_words:
                    if c_tok == nw:
                        score = 1.00
                        if score > best_cat_score:
                            best_cat_score = score
                            best_cat_evidence = f"receipt context ('{c_tok}')"
                    elif len(c_tok) >= 4 and len(nw) >= 4 and (c_tok.startswith(nw) or nw.startswith(c_tok)):
                        score = 0.85
                        if score > best_cat_score:
                            best_cat_score = score
                            best_cat_evidence = f"receipt context ('{c_tok}' ~ '{nw}')"

            # Exact or prefix token match in category description
            for c_tok in context_tokens:
                for dw in cat_desc_words:
                    if c_tok == dw:
                        score = 0.95
                        if score > best_cat_score:
                            best_cat_score = score
                            best_cat_evidence = f"receipt context ('{c_tok}') via category description"
                    elif len(c_tok) >= 4 and len(dw) >= 4 and (c_tok.startswith(dw) or dw.startswith(c_tok)):
                        score = 0.80
                        if score > best_cat_score:
                            best_cat_score = score
                            best_cat_evidence = f"receipt context ('{c_tok}' ~ '{dw}') via category description"

            # Local semantic embedding matching
            if emb is not None:
                all_cat_words = set(cat_name_words + cat_desc_words)
                for c_tok in context_tokens:
                    for cw in all_cat_words:
                        try:
                            d = emb.distanceBetweenString_andString_distanceType_(c_tok, cw, 0)
                            sim = max(0.0, 1.0 - (d / 2.0))
                            if sim >= 0.45 and sim > best_cat_score:
                                best_cat_score = sim
                                via = " via category description" if cw in cat_desc_words and cw not in cat_name_words else ""
                                best_cat_evidence = f"local semantic match ('{c_tok}' ~ '{cw}'{via}) via Apple NaturalLanguage embedding"
                        except Exception:
                            pass

            if best_cat_score >= confidence_threshold:
                scored_cats.append((cat, best_cat_score, best_cat_evidence))

        if scored_cats:
            scored_cats.sort(key=lambda x: x[1], reverse=True)
            top_cat, top_score, top_evidence = scored_cats[0]
            runner_score = scored_cats[1][1] if len(scored_cats) > 1 else 0.0
            margin = top_score - runner_score

            if len(scored_cats) > 1 and margin < 0.05:
                runner_cat = scored_cats[1][0]
                return None, None, ExpenseNature.UNCLASSIFIED, f"Context match ambiguous between '{top_cat.name}' and '{runner_cat.name}'; left for manual assignment."

            return (
                top_cat.id,
                top_cat.name,
                _effective_nature(top_cat),
                f"Matched category '{top_cat.name}' ({expected_cat_type.value}) from {top_evidence}"
            )

    return None, None, ExpenseNature.UNCLASSIFIED, None

def suggest_category_for_merchant(
    db: Session,
    merchant: Optional[str],
    tx_type: str = "expense",
    amount_pence: Optional[int] = None,
    ocr_lines: Optional[List[str]] = None,
    context_text: Optional[str] = None,
    confidence_level: Optional[str] = None
) -> Tuple[Optional[int], Optional[str], ExpenseNature]:
    """
    Backwards-compatible wrapper around suggest_category_from_history.
    """
    cat_id, cat_name, nature, _ = suggest_category_from_history(
        db=db,
        merchant=merchant,
        amount_pence=amount_pence,
        tx_type=tx_type,
        ocr_lines=ocr_lines,
        context_text=context_text,
        confidence_level=confidence_level
    )
    return cat_id, cat_name, nature

class ParsedStatementList(list):
    def __init__(self, items, direction_summary=None):
        super().__init__(items)
        self.direction_summary = direction_summary

def parse_excel_statement(
    file_content: bytes,
    account_currency: str = "GBP",
    filename: Optional[str] = None,
    is_card_context: bool = False
) -> ParsedStatementList:
    """
    Extracts transactions from an Excel (.xlsx) workbook using evidence-based direction inference.
    Scans the first sheet for a header row containing Date, Merchant/Description, and Amount.
    """
    wb = openpyxl.load_workbook(io.BytesIO(file_content), data_only=True, read_only=True)
    sheet = wb.active
    if not sheet:
        return ParsedStatementList([])

    rows = list(sheet.iter_rows(values_only=True))
    if not rows:
        return ParsedStatementList([])

    # Find header row in first 15 rows
    header_idx = -1
    date_col = -1
    desc_col = -1
    amt_col = -1
    debit_col = -1
    credit_col = -1

    for idx, row in enumerate(rows[:15]):
        if not row:
            continue
        row_str = [str(c or "").strip().lower() for c in row]
        for c_idx, val in enumerate(row_str):
            if any(k in val for k in ["date", "transaction date", "booking date", "value date"]):
                date_col = c_idx
            elif any(k in val for k in ["description", "merchant", "payee", "narrative", "details", "memo", "name"]):
                desc_col = c_idx
            elif any(k in val for k in ["amount", "total", "value"]) and "balance" not in val:
                amt_col = c_idx
            elif any(k in val for k in ["debit", "paid out", "spent", "outflow", "withdrawal"]):
                debit_col = c_idx
            elif any(k in val for k in ["credit", "paid in", "income", "inflow", "deposit"]):
                credit_col = c_idx

        if date_col >= 0 and (amt_col >= 0 or (debit_col >= 0 and credit_col >= 0)):
            header_idx = idx
            break

    if header_idx < 0 or date_col < 0:
        return ParsedStatementList([])

    header_row = [str(c or "").strip() for c in rows[header_idx]]
    data_rows = rows[header_idx + 1:]

    # Run structural direction inference from evidence
    direction_analysis = infer_statement_direction(
        headers=header_row,
        data_rows=data_rows,
        amount_col_idx=amt_col if amt_col >= 0 else None,
        debit_col_idx=debit_col if debit_col >= 0 else None,
        credit_col_idx=credit_col if credit_col >= 0 else None,
        type_col_idx=None,
        balance_col_idx=None,
        is_card_context=is_card_context,
        filename=filename
    )

    transactions = []
    for data_idx, row in enumerate(data_rows):
        r_idx = header_idx + 1 + data_idx
        if not row or all(c is None for c in row):
            continue

        raw_date = row[date_col] if date_col < len(row) else None
        if raw_date is None:
            continue

        # Parse date
        tx_date = None
        if isinstance(raw_date, datetime):
            tx_date = raw_date.replace(tzinfo=timezone.utc) if raw_date.tzinfo is None else raw_date
        elif hasattr(raw_date, "strftime"):
            tx_date = datetime.combine(raw_date, datetime.min.time()).replace(tzinfo=timezone.utc)
        elif isinstance(raw_date, str):
            tx_date = parse_date_with_format(raw_date)

        if not tx_date:
            continue

        # Parse merchant
        merchant = ""
        if desc_col >= 0 and desc_col < len(row) and row[desc_col]:
            merchant = str(row[desc_col]).strip()

        # Parse amount & directional evidence
        dir_res = direction_analysis.row_results[data_idx] if data_idx < len(direction_analysis.row_results) else None
        tx_type = dir_res.transaction_type if dir_res else "expense"
        is_uncertain = dir_res.is_uncertain if dir_res else False
        evidence_type = dir_res.evidence_type if dir_res else "unknown"

        dec_amt = None
        if debit_col >= 0 and credit_col >= 0:
            raw_deb = row[debit_col] if debit_col < len(row) else None
            raw_cred = row[credit_col] if credit_col < len(row) else None
            if raw_cred not in (None, "", 0):
                d_c, _, _ = clean_amount_string(str(raw_cred))
                if d_c and d_c > 0:
                    dec_amt = d_c
            elif raw_deb not in (None, "", 0):
                d_d, _, _ = clean_amount_string(str(raw_deb))
                if d_d:
                    dec_amt = abs(d_d)
        elif amt_col >= 0 and amt_col < len(row):
            raw_val = row[amt_col]
            if raw_val is not None:
                d, _, _ = clean_amount_string(str(raw_val))
                if d is not None:
                    dec_amt = abs(d)

        amt_pence = pounds_to_pence(float(dec_amt)) if dec_amt is not None else None

        transactions.append({
            "line_number": r_idx + 1,
            "extracted_date": tx_date,
            "extracted_amount_pence": amt_pence,
            "extracted_merchant": merchant or None,
            "transaction_type": tx_type,
            "direction_uncertain": is_uncertain,
            "direction_evidence": evidence_type,
            "missing_fields": ["transaction_type"] if is_uncertain else [],
            "currency": account_currency,
            "original_amount": None,
            "original_currency": None,
            "suggested_category_name": None,
            "notes": f"Imported from Excel row {r_idx + 1}"
        })

    dir_summary_dict = {
        "expense_count": direction_analysis.expense_count,
        "income_count": direction_analysis.income_count,
        "uncertain_count": direction_analysis.uncertain_count,
        "evidence_type": direction_analysis.evidence_type,
        "evidence_description": direction_analysis.evidence_description
    }
    return ParsedStatementList(transactions, direction_summary=dir_summary_dict)

def parse_screenshot_transactions_spatial(
    ocr_elements: List[Any],
    account_currency: str = "GBP"
) -> List[Dict[str, Any]]:
    """
    Reconstructs transaction rows from 2D OCR layout observations (Apple Vision).
    Each transaction row is formed by finding an amount and grouping the horizontally aligned
    merchant and subtitle/inline date into a unified row window.
    """
    if not ocr_elements:
        return []

    # Sort all elements top-to-bottom by center_y
    elements = sorted(ocr_elements, key=lambda e: e.bbox.center_y)

    # 1. Normalize OCR typos in text for element copies
    normalized_elements = []
    for e in elements:
        t = e.text
        # Common OCR letter/digit misreadings in dates, e.g. '70ct' -> '7 Oct', '26Sept' -> '26 Sep'
        t_norm = re.sub(r'\b(\d{1,2})0ct\b', r'\1 Oct', t, flags=re.IGNORECASE)
        t_norm = re.sub(r'\b(\d{1,2})Sept\b', r'\1 Sep', t_norm, flags=re.IGNORECASE)
        normalized_elements.append({
            "orig": e,
            "text": t,
            "text_norm": t_norm,
            "bbox": e.bbox,
            "center_y": e.bbox.center_y,
            "center_x": e.bbox.center_x,
            "left_x": e.bbox.left_x,
            "right_x": e.bbox.right_x,
            "conf": e.confidence
        })

    # 2. Extract monetary amount elements
    currency_pattern = re.compile(
        r'([-+]?\s*[$£€¥₹]?\s*\d{1,3}(?:,\d{3})*(?:\.\d{1,2})|\(\s*[$£€¥₹]?\s*\d{1,3}(?:,\d{3})*(?:\.\d{1,2})\s*\))'
    )
    date_pattern = re.compile(
        r'(\b\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*(?:\s+\d{2,4})?|\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b|\b\d{4}[/-]\d{1,2}[/-]\d{1,2}\b)',
        re.IGNORECASE
    )

    amount_elements = []
    for item in normalized_elements:
        amt_matches = _extract_amounts_from_text(item["text_norm"])
        if amt_matches:
            matched_str, detected_curr, dec_amt, is_neg = amt_matches[0]
            if dec_amt is not None and abs(dec_amt) > 0:
                item["amt_data"] = (matched_str, detected_curr, dec_amt, is_neg)
                amount_elements.append(item)

    if not amount_elements:
        return []

    # Sort amount elements from top to bottom
    amount_elements.sort(key=lambda item: item["center_y"])

    # Track any preceding section dates found at higher y
    section_dates = []
    for item in normalized_elements:
        if "amt_data" not in item:
            d_matches = _extract_dates_from_text(item["text_norm"])
            if d_matches:
                section_dates.append((item["center_y"], d_matches[0][1]))

    now_utc = datetime.now(timezone.utc)
    current_year = now_utc.year
    transactions = []

    for idx, amt_item in enumerate(amount_elements):
        matched_str, detected_curr, dec_amt, is_neg = amt_item["amt_data"]
        amt_y = amt_item["center_y"]

        # Calculate row vertical window boundaries
        prev_y = amount_elements[idx - 1]["center_y"] if idx > 0 else 0.0
        next_y = amount_elements[idx + 1]["center_y"] if idx + 1 < len(amount_elements) else 1.0

        top_limit = max(prev_y + (amt_y - prev_y) * 0.45, amt_y - 0.05) if idx > 0 else amt_y - 0.04
        bot_limit = min(next_y - (next_y - amt_y) * 0.45, amt_y + 0.05) if idx + 1 < len(amount_elements) else amt_y + 0.04

        # Elements in this row window
        row_items = [
            it for it in normalized_elements
            if top_limit <= it["center_y"] <= bot_limit and it != amt_item
        ]

        # 1. Date extraction for this row
        row_date = None
        date_uncertain = False
        dt_item = None
        for it in row_items:
            m = date_pattern.search(it["text_norm"])
            if m:
                dt_item = it
                parsed = parse_date_with_format(m.group(0))
                if parsed:
                    if parsed.year < 2000:
                        parsed = parsed.replace(year=current_year)
                    row_date = parsed
                    date_uncertain = False
                break

        if not row_date:
            prior_dates = [d for y_val, d in section_dates if y_val < amt_y]
            if prior_dates:
                row_date = prior_dates[-1]
                date_uncertain = True
            else:
                row_date = None
                date_uncertain = True

        # 2. Merchant extraction for this row
        inline_merchant = amt_item["text_norm"].replace(matched_str, "").strip()
        inline_merchant = re.sub(r'^[•\-\*\s]+', '', inline_merchant).strip()

        merchant_val = None
        merchant_uncertain = False

        if len(inline_merchant) >= 3:
            merchant_val = inline_merchant
            merchant_uncertain = False
        else:
            merch_candidates = [
                it for it in row_items
                if it != dt_item
                and not (it["left_x"] < 0.22 and len(it["text"]) <= 2)
                and not currency_pattern.search(it["text_norm"])
            ]
            merch_candidates.sort(key=lambda it: abs(it["center_y"] - amt_y))
            if merch_candidates:
                best_cand = merch_candidates[0]["text"]
                cleaned = re.sub(r'^[•\-\*\s]+', '', best_cand).strip()
                if len(cleaned) >= 2:
                    merchant_val = cleaned
                    merchant_uncertain = (merch_candidates[0]["conf"] < 0.60)
                else:
                    merchant_uncertain = True
            else:
                merchant_uncertain = True

        if not merchant_val:
            merchant_uncertain = True

        # 3. Transaction direction
        tx_type, is_ambig = determine_transaction_direction(
            matched_amount_str=matched_str,
            is_neg=is_neg,
            merchant_text=merchant_val,
            line_text=amt_item["text_norm"],
            context="screenshot"
        )
        amt_pence = pounds_to_pence(float(abs(dec_amt)))

        transactions.append({
            "line_number": idx + 1,
            "extracted_date": row_date,
            "date_uncertain": date_uncertain,
            "extracted_amount_pence": amt_pence,
            "extracted_merchant": merchant_val,
            "merchant_uncertain": merchant_uncertain,
            "transaction_type": tx_type,
            "is_ambiguous_direction": is_ambig,
            "currency": detected_curr or account_currency,
            "original_amount": float(abs(dec_amt)) if detected_curr and detected_curr != account_currency else None,
            "original_currency": detected_curr if detected_curr and detected_curr != account_currency else None,
            "notes": f"Extracted from statement screenshot row {idx + 1}"
        })

    return transactions

def parse_screenshot_transactions(
    ocr_lines: List[str],
    account_currency: str = "GBP"
) -> List[Dict[str, Any]]:
    """
    1D fallback parser when spatial OCR bounding boxes are not available.
    Parses multiple transactions from text lines with explicit uncertainty tracking.
    """
    if not ocr_lines:
        return []

    transactions = []
    current_date = None
    date_is_uncertain = True

    # First pass: check if lines contain date headers or inline transactions
    for idx, line in enumerate(ocr_lines):
        line_clean = line.strip()
        if not line_clean:
            continue

        # 1. Check if line is a date header
        date_matches = _extract_dates_from_text(line_clean)
        amt_in_line = _extract_amounts_from_text(line_clean)
        if date_matches and not amt_in_line:
            current_date = date_matches[0][1]
            date_is_uncertain = False
            continue

        # 2. Check if line contains an amount
        if amt_in_line:
            matched_str, detected_curr, dec_amt, is_neg = amt_in_line[0]

            # Date: check if date is in this line, else use current_date
            if date_matches:
                tx_date = date_matches[0][1]
                row_date_uncertain = False
            else:
                tx_date = current_date
                row_date_uncertain = date_is_uncertain

            # Merchant: remove amount from line to see if merchant text remains
            merchant_candidate = line_clean.replace(matched_str, "").strip()
            category_candidate = None
            merchant_uncertain = False

            # If no merchant in this line, look backwards 1-2 lines for merchant
            if not merchant_candidate or len(merchant_candidate) < 2:
                candidates = []
                for back_offset in (1, 2):
                    if idx - back_offset >= 0:
                        prev_line = ocr_lines[idx - back_offset].strip()
                        # Avoid taking previous amounts or date headers as merchant
                        if not _extract_amounts_from_text(prev_line) and not _extract_dates_from_text(prev_line):
                            if not any(k in prev_line.lower() for k in ["activity", "transactions", "today", "yesterday", "balance"]):
                                candidates.append(prev_line)

                if len(candidates) >= 2:
                    merchant_candidate = candidates[1]
                    category_candidate = candidates[0]
                elif len(candidates) == 1:
                    merchant_candidate = candidates[0]
                else:
                    merchant_uncertain = True

            # Clean merchant
            merchant_candidate = re.sub(r'^[•\-\*\s]+', '', merchant_candidate).strip()
            merchant_val = merchant_candidate if len(merchant_candidate) > 1 else None
            if not merchant_val:
                merchant_uncertain = True

            # Transaction direction: determine from signs, keywords, and screenshot context
            tx_type, is_ambig = determine_transaction_direction(
                matched_amount_str=matched_str,
                is_neg=is_neg,
                merchant_text=merchant_val,
                line_text=line_clean,
                context="screenshot"
            )
            amt_pence = pounds_to_pence(float(abs(dec_amt)))

            transactions.append({
                "line_number": idx + 1,
                "extracted_date": tx_date,
                "date_uncertain": row_date_uncertain,
                "extracted_amount_pence": amt_pence,
                "extracted_merchant": merchant_val,
                "merchant_uncertain": merchant_uncertain,
                "transaction_type": tx_type,
                "is_ambiguous_direction": is_ambig,
                "currency": detected_curr or account_currency,
                "original_amount": float(abs(dec_amt)) if detected_curr and detected_curr != account_currency else None,
                "original_currency": detected_curr if detected_curr and detected_curr != account_currency else None,
                "suggested_category_name": category_candidate,
                "notes": f"Extracted from statement screenshot line {idx + 1}"
            })

    return transactions


_RECEIPT_SETTLEMENT_PATTERNS = [
    re.compile(r"\b(?:balance\s+to\s+pay|total\s+to\s+pay|amount\s+to\s+pay|amount\s+due|total\s+due|balance\s+due)\b", re.IGNORECASE),
    re.compile(r"\b(?:sub[\s\-]?total|balance\s+before|total\s+before|before\s+sav(?:ing|ings|ed))\b", re.IGNORECASE),
    re.compile(r"\b(?:card\s+tendered|amount\s+tendered|cash\s+tendered|change\s+due|change\s+given)\b", re.IGNORECASE),
    re.compile(r"\b(?:you\s+have\s+saved|total\s+sav(?:ing|ings)|your\s+total\s+saving|off\s+with)\b", re.IGNORECASE),
    re.compile(r"\b(?:cardholder\s+copy|customer\s+copy|merchant\s+copy|please\s+retain)\b", re.IGNORECASE),
    re.compile(r"\b(?:auth(?:orisation|orization)?\s*(?:code|no)|aid\s*:|tid\s*:|mid\s*:|pan\s+seq|app\s+seq)\b", re.IGNORECASE),
    re.compile(r"\b(?:vat\s*(?:no|reg|number|rate|amount)|tax\s+invoice|receipt\s*(?:no|#))\b", re.IGNORECASE),
]

_STATEMENT_HEADER_PATTERNS = [
    re.compile(r"\b(?:recent\s+activity|account\s+activity|statement\s+activity|activity)\b", re.IGNORECASE),
    re.compile(r"\b(?:transactions|recent\s+transactions|pending\s+transactions)\b", re.IGNORECASE),
    re.compile(r"\b(?:opening\s+balance|closing\s+balance|available\s+balance|statement\s+period|running\s+balance)\b", re.IGNORECASE),
    re.compile(r"\b(?:money\s+in|money\s+out|direct\s+debit|standing\s+order|faster\s+payment)\b", re.IGNORECASE),
]

_IGNORE_DATE_LINE_RE = re.compile(
    r"\b(?:points\s+up\s+to|up\s+to|expiry|expires|valid|member\s+since|joined)\b",
    re.IGNORECASE
)
_SKU_CODE_RE = re.compile(r"^\s*\d{6,13}\b")


def classify_image_document_type(
    ocr_lines: List[str],
    ocr_elements: Optional[List[Any]] = None
) -> Dict[str, Any]:
    """
    Provider-agnostic structural classifier distinguishing a single receipt ('receipt')
    from a multi-transaction statement or wallet screenshot ('statement_screenshot').

    Uses layout and structural evidence:
    - Receipt evidence: settlement/total/subtotal/discount/tender summary block, POS/terminal metadata,
      VAT/tax/receipt headers, itemized product SKU codes, and single document date.
    - Statement evidence: multiple transaction dates across rows (or date section headers like
      'Today', 'Yesterday', '13 Oct', '7 Oct') paired with distinct transaction rows, and statement/activity headers.
    - Safe default: if ambiguous or uncertain, defaults to 'receipt' (staging one candidate for review)
      rather than splitting into many fabricated transactions.
    """
    visual_lines = reconstruct_visual_lines(ocr_elements, ocr_lines)
    all_lines = visual_lines if visual_lines else [l.strip() for l in (ocr_lines or []) if l and l.strip()]
    joined_text = " ".join(all_lines)

    amounts_found = _extract_amounts_from_text(joined_text)

    # Count receipt structural signals
    receipt_settlement_hits = 0
    for pat in _RECEIPT_SETTLEMENT_PATTERNS:
        if pat.search(joined_text):
            receipt_settlement_hits += 1

    sku_code_lines = sum(1 for l in (ocr_lines or []) if _SKU_CODE_RE.search(l.strip()))
    if sku_code_lines == 0:
        sku_code_lines = sum(1 for l in all_lines if _SKU_CODE_RE.search(l.strip()))

    # Count statement header signals
    statement_header_hits = 0
    for pat in _STATEMENT_HEADER_PATTERNS:
        if pat.search(joined_text):
            statement_header_hits += 1

    # Count distinct lines with transaction dates (excluding loyalty/expiry dates)
    dated_line_count = 0
    for l in all_lines:
        if _IGNORE_DATE_LINE_RE.search(l):
            continue
        # Normalize common OCR date typos like '70ct' -> '7 Oct', '26Sept' -> '26 Sep'
        l_norm = re.sub(r"\b(\d{1,2})0ct\b", r"\1 Oct", l, flags=re.IGNORECASE)
        l_norm = re.sub(r"\b(\d{1,2})Sept\b", r"\1 Sep", l_norm, flags=re.IGNORECASE)
        if _extract_dates_from_text(l_norm):
            dated_line_count += 1

    reasons: List[str] = []
    if receipt_settlement_hits > 0:
        reasons.append(f"receipt_settlement_signals={receipt_settlement_hits}")
    if sku_code_lines > 0:
        reasons.append(f"product_sku_lines={sku_code_lines}")
    if statement_header_hits > 0:
        reasons.append(f"statement_headers={statement_header_hits}")
    if dated_line_count > 0:
        reasons.append(f"dated_lines={dated_line_count}")

    # 1. Strong receipt structure (settlement block, tender, discounts, POS metadata, or SKU item codes)
    if receipt_settlement_hits >= 1 or sku_code_lines >= 2:
        # Only override to statement_screenshot if there are many dated rows AND explicit statement headers AND zero receipt signals
        is_statement = (
            receipt_settlement_hits == 0
            and sku_code_lines == 0
            and dated_line_count >= 3
            and statement_header_hits >= 1
        )
        return {
            "document_type": "statement_screenshot" if is_statement else "receipt",
            "is_uncertain": False,
            "receipt_score": receipt_settlement_hits + sku_code_lines,
            "statement_score": dated_line_count + statement_header_hits,
            "reasons": reasons,
        }

    # 2. Positive statement-screenshot structure requires >= 2 amounts AND repeated dates (or statement header + date)
    if len(amounts_found) >= 2 and (
        dated_line_count >= 2 or (statement_header_hits >= 1 and dated_line_count >= 1)
    ):
        return {
            "document_type": "statement_screenshot",
            "is_uncertain": False,
            "receipt_score": 0,
            "statement_score": dated_line_count + statement_header_hits,
            "reasons": reasons,
        }

    # 3. Default / ambiguous fallback: treat as a single receipt (never fabricate a multi-row batch from uncertain text)
    is_uncertain = len(amounts_found) != 1
    return {
        "document_type": "receipt",
        "is_uncertain": is_uncertain,
        "receipt_score": receipt_settlement_hits,
        "statement_score": dated_line_count + statement_header_hits,
        "reasons": reasons,
    }


def ingest_unified_file(
    db: Session,
    file_content: bytes,
    original_filename: str,
    target_account_id: Optional[int] = None,
    staging_dir: Path = STAGING_RECEIPTS_DIR
) -> Dict[str, Any]:
    """
    Unified entry point for financial imports:
    1. Inspects file signature and MIME type safely.
    2. Persists source file into staging receipts folder.
    3. Runs appropriate extractor (CSV/TSV, Excel, OCR Receipt, Statement Screenshot, or Unsupported).
    4. Evaluates duplicate advisories and flags uncertain/missing fields without inventing values.
    5. Stages pending items in DB and returns review payload for the modal.
    """
    if len(file_content) > MAX_FILE_SIZE_BYTES:
        raise ValueError(f"Uploaded file exceeds maximum limit of {MAX_FILE_SIZE_BYTES // (1024 * 1024)}MB.")

    # 1. Classify
    classification = classify_uploaded_file(file_content, original_filename)

    import hashlib
    file_hash = hashlib.sha256(file_content).hexdigest()

    # 2. Persist source file safely in staging directory
    staging_dir.mkdir(parents=True, exist_ok=True)
    safe_name = f"{uuid.uuid4().hex[:10]}_{Path(original_filename).name}"
    target_path = staging_dir / safe_name
    with open(target_path, "wb") as f:
        f.write(file_content)

    try:
        relative_source_path = str(target_path.relative_to(DATA_DIR))
    except ValueError:
        relative_source_path = str(target_path)

    # Target account & currency resolution
    target_acc = db.query(Account).filter(Account.id == target_account_id).first() if target_account_id else None
    account_currency = target_acc.currency if target_acc else get_effective_base_currency(db)

    batch_id = str(uuid.uuid4())
    candidate_items: List[Dict[str, Any]] = []
    final_doc_type = classification.document_type
    doc_label = classification.type_label
    summary = ""
    file_direction_summary: Optional[Dict[str, Any]] = None

    # Determine if target account is credit card context
    is_card_ctx = (target_acc.account_type == AccountType.CREDIT_CARD) if target_acc else False

    # 3. Extraction Routing
    # ROUTE A: Excel Spreadsheet (.xlsx)
    if classification.mime_type == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet":
        try:
            excel_items = parse_excel_statement(
                file_content,
                account_currency=account_currency,
                filename=original_filename,
                is_card_context=is_card_ctx
            )
            if excel_items:
                candidate_items = excel_items
                file_direction_summary = getattr(excel_items, "direction_summary", None)
                final_doc_type = "statement"
                doc_label = f"Excel Statement ({len(excel_items)} rows)"
                summary = f"Successfully parsed {len(excel_items)} transactions from Excel spreadsheet."
            else:
                final_doc_type = "unsupported"
                doc_label = "Spreadsheet (No Tabular Header Found)"
                summary = "Could not identify standard transaction headers (Date, Description, Amount) in spreadsheet. Source preserved for manual entry."
        except Exception as e:
            final_doc_type = "unsupported"
            summary = f"Error reading Excel file: {str(e)}. Source preserved for manual entry."

    # ROUTE B: Delimited Text (CSV / TSV)
    elif classification.mime_type in ("text/csv", "text/tab-separated-values"):
        try:
            parsed = StatementParser.parse_statement(
                file_content=file_content,
                filename=original_filename,
                mapping={},  # auto-sniff
                account_currency=account_currency
            )
            file_direction_summary = parsed.get("direction_summary")
            for item in parsed["items"]:
                candidate_items.append({
                    "line_number": item["line_number"],
                    "extracted_date": item["extracted_date"],
                    "extracted_amount_pence": item["extracted_amount_pence"],
                    "extracted_merchant": item["extracted_merchant"],
                    "transaction_type": item["transaction_type"],
                    "direction_uncertain": item.get("direction_uncertain", False),
                    "direction_evidence": item.get("direction_evidence", "unknown"),
                    "currency": item["currency"],
                    "original_amount": item.get("original_amount"),
                    "original_currency": item.get("original_currency"),
                    "exchange_rate": item.get("exchange_rate"),
                    "suggested_category_name": item.get("suggested_category_name"),
                    "notes": item.get("notes") or f"Imported from statement line {item['line_number']}"
                })
            final_doc_type = "statement"
            doc_label = f"Bank / Card Statement ({len(candidate_items)} rows)"
            summary = f"Successfully parsed {len(candidate_items)} statement records."
        except Exception as e:
            final_doc_type = "unsupported"
            summary = f"Could not parse delimited file: {str(e)}. Source preserved for manual entry."

    # ROUTE C: Image (Receipt vs Screenshot)
    elif classification.is_image:
        app_tz = get_app_timezone(db)
        parser = OCRFactory.get_parser()
        try:
            ocr_result = parser.parse_receipt(target_path, tz_str=app_tz)
        except TypeError:
            ocr_result = parser.parse_receipt(target_path)
        ocr_lines = getattr(ocr_result, "raw_lines", []) or []
        ocr_elements = getattr(ocr_result, "ocr_elements", []) or []

        # Detect whether image is a Statement Screenshot or a Single Receipt using provider-agnostic structural evidence
        doc_class = classify_image_document_type(ocr_lines, ocr_elements)
        is_screenshot = (doc_class["document_type"] == "statement_screenshot")

        if is_screenshot:
            if ocr_elements:
                screenshot_items = parse_screenshot_transactions_spatial(ocr_elements, account_currency=account_currency)
            else:
                screenshot_items = parse_screenshot_transactions(ocr_lines, account_currency=account_currency)

            if screenshot_items:
                candidate_items = screenshot_items
                final_doc_type = "statement_screenshot"
                doc_label = f"Statement Screenshot ({len(screenshot_items)} items)"
                summary = f"Detected multi-transaction statement screenshot and extracted {len(screenshot_items)} transaction candidates."
            else:
                # Fallback to single receipt parsing if multi-row extraction produced 0 rows
                is_screenshot = False

        if not is_screenshot:
            final_doc_type = "receipt"
            doc_label = "Receipt"

            if ocr_lines or ocr_elements:
                parsed_rec = extract_receipt_fields_from_lines(ocr_lines, ocr_elements, tz_str=app_tz)
                amt = parsed_rec["amount_pence"]
                orig_amt = parsed_rec["original_amount"]
                detected_curr = parsed_rec["detected_currency"] or getattr(ocr_result, "detected_currency", None) or account_currency
                rec_date = parsed_rec["transaction_date"] or getattr(ocr_result, "transaction_date", None)
                rec_merchant = parsed_rec["merchant"] or getattr(ocr_result, "merchant", None)
                date_unc = bool(parsed_rec["date_uncertain"] or (rec_date is None))
                merch_unc = bool(parsed_rec["merchant_uncertain"] or (not rec_merchant))
                amt_unc = parsed_rec["amount_uncertain"]
                subtotal_p = parsed_rec.get("subtotal_pence")
                discount_p = parsed_rec.get("discount_pence")
            else:
                detected_curr = getattr(ocr_result, "detected_currency", None) or account_currency
                amt = getattr(ocr_result, "amount_pence", None)
                orig_amt = getattr(ocr_result, "original_amount", None)
                rec_date = getattr(ocr_result, "transaction_date", None)
                rec_merchant = getattr(ocr_result, "merchant", None)
                date_unc = getattr(ocr_result, "date_uncertain", rec_date is None)
                merch_unc = getattr(ocr_result, "merchant_uncertain", not rec_merchant)
                amt_unc = getattr(ocr_result, "amount_uncertain", amt is None)
                subtotal_p = getattr(ocr_result, "subtotal_pence", None)
                discount_p = getattr(ocr_result, "discount_pence", None)

            orig_curr = None
            if detected_curr and detected_curr.upper() != account_currency.upper():
                orig_curr = detected_curr.upper()
                amt = None  # Base amount uncertain; require user to provide actual base charge

            note_parts = ["Extracted via OCR from receipt image"]
            if subtotal_p and discount_p and amt:
                note_parts.append(
                    f"(Subtotal £{subtotal_p / 100:.2f}, Discount £{discount_p / 100:.2f}, Paid £{amt / 100:.2f})"
                )
            elif amt_unc or doc_class.get("is_uncertain"):
                note_parts.append("(Uncertain amount/details flagged for manual review)")

            candidate_items.append({
                "line_number": 1,
                "extracted_date": rec_date,
                "date_uncertain": date_unc,
                "extracted_amount_pence": amt,
                "extracted_merchant": rec_merchant,
                "merchant_uncertain": merch_unc,
                "transaction_type": "expense",
                "currency": account_currency,
                "original_amount": orig_amt,
                "original_currency": orig_curr,
                "suggested_category_name": getattr(ocr_result, "suggested_category_name", None),
                "notes": " ".join(note_parts)
            })
            summary = "Parsed receipt image via local OCR."
            if subtotal_p and discount_p and amt:
                summary = f"Parsed single receipt via local OCR: Paid £{amt / 100:.2f} (Subtotal £{subtotal_p / 100:.2f}, Discount £{discount_p / 100:.2f})."
            elif amt is None:
                summary = "Parsed receipt image via local OCR. Final paid amount could not be confidently determined and is flagged for review."

    # ROUTE D: PDF Document
    elif classification.is_pdf:
        # Check text in PDF or run OCR if available
        # On macOS, Apple Vision / Quartz can process image or PDF
        app_tz = get_app_timezone(db)
        parser = OCRFactory.get_parser()
        try:
            try:
                ocr_result = parser.parse_receipt(target_path, tz_str=app_tz)
            except TypeError:
                ocr_result = parser.parse_receipt(target_path)
            ocr_lines = getattr(ocr_result, "raw_lines", []) or []
            ocr_elements = getattr(ocr_result, "ocr_elements", []) or []
            doc_class = classify_image_document_type(ocr_lines, ocr_elements)

            if doc_class["document_type"] == "statement_screenshot":
                if ocr_elements:
                    pdf_items = parse_screenshot_transactions_spatial(ocr_elements, account_currency=account_currency)
                else:
                    pdf_items = parse_screenshot_transactions(ocr_lines, account_currency=account_currency)

                if pdf_items:
                    candidate_items = pdf_items
                    final_doc_type = "statement"
                    doc_label = f"PDF Statement ({len(pdf_items)} items)"
                    summary = f"Extracted {len(pdf_items)} transactions from PDF statement."
            if not candidate_items:
                final_doc_type = "receipt"
                doc_label = "PDF Invoice / Receipt"
                if ocr_lines or ocr_elements:
                    parsed_rec = extract_receipt_fields_from_lines(ocr_lines, ocr_elements, tz_str=app_tz)
                    amt = parsed_rec["amount_pence"]
                    orig_amt = parsed_rec["original_amount"]
                    detected_curr = parsed_rec["detected_currency"] or getattr(ocr_result, "detected_currency", None)
                    rec_date = parsed_rec["transaction_date"] or getattr(ocr_result, "transaction_date", None)
                    rec_merchant = parsed_rec["merchant"] or getattr(ocr_result, "merchant", None)
                else:
                    amt = getattr(ocr_result, "amount_pence", None)
                    orig_amt = getattr(ocr_result, "original_amount", None)
                    detected_curr = getattr(ocr_result, "detected_currency", None)
                    rec_date = getattr(ocr_result, "transaction_date", None)
                    rec_merchant = getattr(ocr_result, "merchant", None)

                orig_curr = detected_curr.upper() if detected_curr and detected_curr.upper() != account_currency.upper() else None
                if orig_curr:
                    amt = None

                candidate_items.append({
                    "line_number": 1,
                    "extracted_date": rec_date,
                    "extracted_amount_pence": amt,
                    "extracted_merchant": rec_merchant,
                    "transaction_type": "expense",
                    "currency": account_currency,
                    "original_amount": orig_amt,
                    "original_currency": orig_curr,
                    "suggested_category_name": getattr(ocr_result, "suggested_category_name", None),
                    "notes": "Extracted from PDF document"
                })
                summary = "Processed PDF document with local OCR."
        except Exception as e:
            final_doc_type = "unsupported"
            summary = f"Could not extract text from PDF: {str(e)}. File preserved for manual entry."

    # ROUTE E: Unsupported / Unreadable Fallback
    if not candidate_items:
        final_doc_type = "unsupported"
        doc_label = "Unsupported / Manual Attachment"
        summary = (
            f"File format ({classification.mime_type or 'unknown'}) cannot be automatically extracted. "
            f"The file has been safely preserved; enter transaction details manually below to record it with this file attached."
        )
        candidate_items.append({
            "line_number": 1,
            "extracted_date": None,
            "extracted_amount_pence": None,
            "extracted_merchant": None,
            "transaction_type": "expense",
            "currency": account_currency,
            "original_amount": None,
            "original_currency": None,
            "suggested_category_name": None,
            "notes": f"Manual entry from attached file {original_filename}"
        })

    # Resolve suggested account from context if target_account_id was not explicitly supplied
    suggested_acc_id = None
    suggested_acc_name = None
    account_match_reason = None
    ocr_lines_ctx = ocr_lines if 'ocr_lines' in locals() and ocr_lines else []
    ocr_elements_ctx = ocr_elements if 'ocr_elements' in locals() and ocr_elements else []
    active_acc_names = [a.name for a in db.query(Account).filter(Account.is_active == True).all()]
    first_merchant = candidate_items[0].get("extracted_merchant") if candidate_items else None
    confirmed_associations = get_confirmed_account_associations(db)
    confirmed_labels = list(confirmed_associations.keys())
    extracted_card_labels, extracted_card_last_4 = extract_card_or_account_clues(
        ocr_lines=ocr_lines_ctx,
        active_account_names=active_acc_names,
        ocr_elements=ocr_elements_ctx,
        merchant_name=first_merchant,
        confirmed_association_labels=confirmed_labels
    )
    extracted_card_label = extracted_card_labels[0] if extracted_card_labels else None

    if target_account_id:
        target_acc = db.query(Account).filter(Account.id == target_account_id).first()
        if target_acc:
            suggested_acc_id = target_acc.id
            suggested_acc_name = target_acc.name
            account_match_reason = "Manually selected target account"
    else:
        suggested_acc_id, suggested_acc_name, account_match_reason = match_account_from_context(
            db=db,
            ocr_lines=ocr_lines_ctx,
            original_filename=original_filename,
            ocr_elements=ocr_elements_ctx,
            merchant_name=first_merchant
        )
        if suggested_acc_id:
            matched_acc = db.query(Account).filter(Account.id == suggested_acc_id).first()
            if matched_acc:
                account_currency = matched_acc.currency

    # 4. Stage items in DB & Evaluate Advisory Duplicates
    staged_results = []
    for item in candidate_items:
        amt = item["extracted_amount_pence"]
        dt = item["extracted_date"]
        merchant = item["extracted_merchant"]

        # Duplicate evaluation
        is_dup, dup_matches = evaluate_duplicates(
            db=db,
            amount_pence=amt,
            tx_date=dt,
            merchant=merchant,
            target_account_id=suggested_acc_id or target_account_id
        )

        missing_fields = []
        if amt is None:
            missing_fields.append("amount")
        if dt is None:
            missing_fields.append("transaction_date")
        is_dir_uncertain = bool(item.get("direction_uncertain") or item.get("is_ambiguous_direction"))
        if is_dir_uncertain:
            missing_fields.append("transaction_type")

        # Currency conflict
        orig_curr = item.get("original_currency")
        orig_amt = item.get("original_amount")
        curr_conflict = False
        curr_msg = None
        req_base = False

        if orig_curr and orig_curr.upper() != account_currency.upper():
            curr_conflict = True
            req_base = (amt is None)
            curr_msg = (
                f"Transaction is in foreign currency ({orig_curr} {orig_amt or ''}). "
                f"Enter the actual {account_currency} amount charged to your card/bank before approving."
            )

        payload = {
            "batch_id": batch_id,
            "source_filename": original_filename,
            "source_file_hash": file_hash,
            "line_number": item.get("line_number", 1),
            "document_type": final_doc_type,
            "transaction_type": item.get("transaction_type", "expense"),
            "direction_uncertain": is_dir_uncertain,
            "direction_evidence": item.get("direction_evidence"),
            "destination_account_id": None,
            "notes": item.get("notes"),
            "currency": item.get("currency") or account_currency,
            "original_amount": orig_amt,
            "original_currency": orig_curr,
            "exchange_rate": item.get("exchange_rate"),
            "requires_base_amount": req_base,
            "currency_conflict": curr_conflict,
            "currency_conflict_message": curr_msg,
            "is_potential_duplicate": is_dup,
            "duplicate_matches": dup_matches,
            "missing_fields": missing_fields,
            "extracted_card_label": extracted_card_label,
            "extracted_card_last_4": extracted_card_last_4,
            "date_uncertain": item.get("date_uncertain", False),
            "merchant_uncertain": item.get("merchant_uncertain", False)
        }

        # Auto-match category from approved history filtered by transaction direction/purpose
        try:
            item_tx_type_enum = TransactionType(str(item.get("transaction_type", "expense")).strip().lower())
        except ValueError:
            item_tx_type_enum = TransactionType.EXPENSE
        expected_item_cat_type = expected_category_type_for_transaction(item_tx_type_enum)

        cat_id = None
        suggested_cat_name = None
        suggested_nature = ExpenseNature.UNCLASSIFIED
        cat_explanation = None

        candidate_cat = item.get("suggested_category_name")
        if candidate_cat and expected_item_cat_type is not None:
            cat = (
                db.query(Category)
                .filter(
                    Category.is_active == True,
                    Category.category_type == expected_item_cat_type,
                    Category.name.ilike(candidate_cat.strip()),
                )
                .first()
            )
            if cat:
                cat_id = cat.id
                suggested_cat_name = cat.name
                suggested_nature = (
                    ExpenseNature.UNCLASSIFIED
                    if expected_item_cat_type == CategoryType.INCOME
                    else (cat.default_expense_nature or ExpenseNature.UNCLASSIFIED)
                )

        if not cat_id and expected_item_cat_type is not None:
            cat_id, suggested_cat_name, suggested_nature, cat_explanation = suggest_category_from_history(
                db=db,
                merchant=merchant,
                amount_pence=amt,
                tx_type=item_tx_type_enum.value,
                ocr_lines=ocr_lines_ctx
            )

        payload["category_id"] = cat_id
        payload["account_match_reason"] = account_match_reason
        payload["category_match_reason"] = cat_explanation

        stg = StagingItem(
            created_at=datetime.now(timezone.utc),
            status=StagingStatus.PENDING,
            extracted_amount_pence=amt,
            extracted_date=dt,
            extracted_merchant=merchant,
            suggested_category_name=suggested_cat_name,
            suggested_account_id=suggested_acc_id or target_account_id,
            suggested_expense_nature=suggested_nature,
            source_type=final_doc_type,
            temp_file_path=relative_source_path,
            raw_payload_json=json.dumps(payload)
        )
        db.add(stg)
        staged_results.append((stg, payload))

    db.commit()

    # Build response payload
    response_items = []
    for stg, payload in staged_results:
        db.refresh(stg)
        cat_id = payload.get("category_id")
        response_items.append({
            "id": stg.id,
            "batch_id": batch_id,
            "line_number": payload.get("line_number", 1),
            "extracted_date": stg.extracted_date.isoformat() if stg.extracted_date else None,
            "extracted_amount_pence": stg.extracted_amount_pence,
            "extracted_amount_pounds": (stg.extracted_amount_pence / 100.0) if stg.extracted_amount_pence is not None else None,
            "extracted_merchant": stg.extracted_merchant,
            "suggested_account_id": stg.suggested_account_id,
            "suggested_account_name": suggested_acc_name,
            "suggested_account_match_reason": account_match_reason,
            "suggested_category_id": cat_id,
            "suggested_category_name": stg.suggested_category_name,
            "suggested_expense_nature": stg.suggested_expense_nature.value if stg.suggested_expense_nature else "unclassified",
            "transaction_type": payload.get("transaction_type", "expense"),
            "direction_uncertain": payload.get("direction_uncertain", False),
            "direction_evidence": payload.get("direction_evidence"),
            "currency": payload.get("currency", account_currency),
            "original_amount": payload.get("original_amount"),
            "original_currency": payload.get("original_currency"),
            "currency_conflict": payload.get("currency_conflict", False),
            "currency_conflict_message": payload.get("currency_conflict_message"),
            "is_potential_duplicate": payload.get("is_potential_duplicate", False),
            "duplicate_matches": payload.get("duplicate_matches", []),
            "missing_fields": payload.get("missing_fields", []),
            "source_type": stg.source_type,
            "temp_file_path": stg.temp_file_path,
            "notes": payload.get("notes"),
            "date_uncertain": payload.get("date_uncertain", False),
            "merchant_uncertain": payload.get("merchant_uncertain", False),
            "category_match_reason": payload.get("category_match_reason")
        })

    return {
        "batch_id": batch_id,
        "filename": original_filename,
        "file_hash": file_hash,
        "file_size_bytes": len(file_content),
        "mime_type": classification.mime_type,
        "document_type": final_doc_type,
        "document_type_label": doc_label,
        "summary": summary,
        "direction_summary": file_direction_summary,
        "items": response_items
    }
