"""
Review Queue Advisory Refinement Suggestions Engine

Provides strictly local, profile-scoped advisory suggestions in the Review Queue:
1. Likely duplicate transactions (intra-staging or staging-vs-ledger)
2. Likely transfers (outgoing expense paired with incoming income across distinct accounts)

All suggestions are explainable and purely advisory: they never mutate, discard,
or block records until the user explicitly confirms an action.
"""

from bisect import bisect_left, bisect_right
from collections import defaultdict
import hashlib
import json
import re
import shutil
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any, Tuple
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import and_, or_

from app.config import STAGING_RECEIPTS_DIR, ARCHIVE_RECEIPTS_DIR, DATA_DIR
from app.models import (
    StagingItem, StagingStatus, Transaction, TransactionType,
    Account, AccountType, Category, ExpenseNature
)
from app.core.currency import pence_to_pounds, format_pence, get_currency_spec, get_base_currency_readonly, get_effective_base_currency
from app.core.timezone import get_app_timezone, parse_date_input, ensure_utc, get_now_utc
from app.core.staging import discard_staging_item, approve_staging_item
from app.core.backup import get_system_setting, set_system_setting

DISMISSED_SUGGESTIONS_SETTING_KEY = "dismissed_review_suggestions"
SUGGESTION_DATE_WINDOW_DAYS = 3

_TRANSFER_NARRATIVE_KEYWORDS = (
    "transfer", "tfr", "faster payment", "payment received", "thank you",
    "direct debit", "standing order", "card payment", "bill payment",
    "top up", "topup", "internal", "move", "repayment", "paid in", "paid out"
)


def _normalize_text(s: Optional[str]) -> str:
    if not s:
        return ""
    # Lowercase, replace punctuation with spaces, collapse spaces
    cleaned = re.sub(r"[^\w\s]", " ", s.lower())
    return " ".join(cleaned.split())


def _merchant_tokens_overlap(m1: Optional[str], m2: Optional[str]) -> bool:
    norm1 = _normalize_text(m1)
    norm2 = _normalize_text(m2)
    if not norm1 or not norm2:
        return False
    if norm1 in norm2 or norm2 in norm1:
        return True
    tokens1 = set(norm1.split())
    tokens2 = set(norm2.split())
    # Filter out trivial common words
    stop_words = {"the", "ltd", "limited", "co", "uk", "card", "payment", "purchase", "direct", "debit"}
    t1 = tokens1 - stop_words
    t2 = tokens2 - stop_words
    if not t1 or not t2:
        return False
    return len(t1.intersection(t2)) > 0


def _has_transfer_narrative(text: Optional[str]) -> bool:
    norm = _normalize_text(text)
    if not norm:
        return False
    return any(kw in norm for kw in _TRANSFER_NARRATIVE_KEYWORDS)


def _mentions_account_name(text: Optional[str], account_name: Optional[str]) -> bool:
    norm_text = _normalize_text(text)
    norm_acc = _normalize_text(account_name)
    if not norm_text or not norm_acc:
        return False
    if norm_acc in norm_text:
        return True
    ignore = {"account", "card", "current", "savings", "credit", "debit", "bank", "the", "uk", "gbp"}
    acc_tokens = [t for t in norm_acc.split() if len(t) >= 3 and t not in ignore]
    text_tokens = set(norm_text.split())
    return any(t in text_tokens for t in acc_tokens)


def _score_transfer_pair(
    day_diff: int,
    out_merchant: Optional[str],
    out_notes: Optional[str],
    out_acc: Account,
    in_merchant: Optional[str],
    in_notes: Optional[str],
    in_acc: Account,
) -> Tuple[bool, float, List[str]]:
    """
    Evaluates the strength of evidence for an opposite-direction, equal-amount pair
    across two distinct, currency-compatible accounts.
    Returns (is_plausible, score, extra_reasons).
    """
    extra_reasons: List[str] = []
    score = 0.0

    if day_diff == 0:
        score += 3.0
    elif day_diff == 1:
        score += 1.5
    else:
        score += 0.5

    combined_out = f"{out_merchant or ''} {out_notes or ''}".strip()
    combined_in = f"{in_merchant or ''} {in_notes or ''}".strip()

    has_tfr_words = _has_transfer_narrative(combined_out) or _has_transfer_narrative(combined_in)
    if has_tfr_words:
        score += 2.5
        extra_reasons.append("Transfer/payment narrative")

    mentions_counterpart = (
        _mentions_account_name(combined_out, in_acc.name)
        or _mentions_account_name(combined_in, out_acc.name)
    )
    if mentions_counterpart:
        score += 3.0
        extra_reasons.append("References counterpart account")

    narrative_overlap = _merchant_tokens_overlap(out_merchant, in_merchant)
    if narrative_overlap:
        score += 2.0
        extra_reasons.append(f"Matching narrative: '{out_merchant}' ~ '{in_merchant}'")

    is_cc_repayment = (
        out_acc.account_type in (AccountType.CURRENT, AccountType.SAVINGS, AccountType.CASH)
        and in_acc.account_type == AccountType.CREDIT_CARD
    )
    if is_cc_repayment:
        score += 1.5
        extra_reasons.append(f"Credit card payment flow ({out_acc.name} → {in_acc.name})")

    out_m_clean = _normalize_text(out_merchant)
    in_m_clean = _normalize_text(in_merchant)
    either_blank = (not out_m_clean) or (not in_m_clean)

    # Plausibility filter:
    # If not on the same day (day_diff >= 1) and both entries have non-empty, completely unrelated
    # third-party narratives with no transfer/payment keywords and no account mention, reject as weak.
    if day_diff >= 1 and not (has_tfr_words or mentions_counterpart or narrative_overlap or either_blank):
        return False, score, extra_reasons

    return True, score, extra_reasons


def _filter_ambiguous_transfer_candidates(candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Removes ambiguous 1-to-many or many-to-1 transfer candidates where a single record
    matches multiple opposite-direction counterparts with tied top evidence scores.
    """
    if len(candidates) <= 1:
        return candidates

    by_src: Dict[str, List[Dict[str, Any]]] = {}
    by_dst: Dict[str, List[Dict[str, Any]]] = {}
    for c in candidates:
        s_key = f"{c['source_record']['kind']}_{c['source_record']['id']}"
        d_key = f"{c['destination_record']['kind']}_{c['destination_record']['id']}"
        by_src.setdefault(s_key, []).append(c)
        by_dst.setdefault(d_key, []).append(c)

    ambiguous_ids = set()
    for group in list(by_src.values()) + list(by_dst.values()):
        if len(group) > 1:
            sorted_g = sorted(group, key=lambda x: x.get("_score", 0.0), reverse=True)
            if abs(sorted_g[0].get("_score", 0.0) - sorted_g[1].get("_score", 0.0)) < 0.5:
                for item in group:
                    ambiguous_ids.add(item["id"])

    filtered = []
    for c in candidates:
        if c["id"] not in ambiguous_ids:
            c_clean = dict(c)
            c_clean.pop("_score", None)
            filtered.append(c_clean)
    return filtered


def get_dismissed_suggestion_ids(db: Session) -> set:
    raw = get_system_setting(db, DISMISSED_SUGGESTIONS_SETTING_KEY, "[]")
    try:
        data = json.loads(raw)
        return set(data) if isinstance(data, list) else set()
    except Exception:
        return set()


def add_dismissed_suggestion_id(db: Session, suggestion_id: str) -> None:
    dismissed = get_dismissed_suggestion_ids(db)
    dismissed.add(suggestion_id)
    set_system_setting(db, DISMISSED_SUGGESTIONS_SETTING_KEY, json.dumps(sorted(dismissed)))


def remove_dismissed_suggestion_id(db: Session, suggestion_id: str) -> bool:
    dismissed = get_dismissed_suggestion_ids(db)
    if suggestion_id not in dismissed:
        return False
    dismissed.remove(suggestion_id)
    set_system_setting(db, DISMISSED_SUGGESTIONS_SETTING_KEY, json.dumps(sorted(dismissed)))
    return True


def restore_all_dismissed_suggestions(db: Session) -> int:
    dismissed = get_dismissed_suggestion_ids(db)
    count = len(dismissed)
    if count > 0:
        set_system_setting(db, DISMISSED_SUGGESTIONS_SETTING_KEY, "[]")
    return count


def get_review_queue_suggestions(db: Session, include_dismissed: bool = False) -> Dict[str, Any]:
    """
    Evaluates current pending staging items and existing ledger records to find:
    - Candidate duplicate pairs (staging-vs-staging, staging-vs-ledger)
    - Candidate transfer pairs (staging-vs-staging, staging-vs-ledger, ledger-vs-ledger)
    Returns clean, explainable suggestions.
    """
    dismissed = get_dismissed_suggestion_ids(db)
    base_curr = get_base_currency_readonly(db)
    base_spec = get_currency_spec(base_curr)

    # 1. Fetch pending staging items
    pending_items = (
        db.query(StagingItem)
        .filter(StagingItem.status == StagingStatus.PENDING)
        .order_by(StagingItem.extracted_date.desc(), StagingItem.id.desc())
        .all()
    )

    duplicate_suggestions: List[Dict[str, Any]] = []
    raw_transfer_candidates: List[Dict[str, Any]] = []

    # Pre-parse pending item metadata
    parsed_items = []
    earliest_date = None
    latest_date = None

    for item in pending_items:
        payload = json.loads(item.raw_payload_json or "{}")
        tx_type = payload.get("transaction_type", "expense").lower()
        d = item.extracted_date
        if d:
            d_utc = ensure_utc(d)
            if earliest_date is None or d_utc < earliest_date:
                earliest_date = d_utc
            if latest_date is None or d_utc > latest_date:
                latest_date = d_utc
        else:
            d_utc = None

        acc = None
        if item.suggested_account_id:
            acc = db.query(Account).filter(Account.id == item.suggested_account_id).first()

        orig_curr = payload.get("original_currency")
        curr_conflict = bool(
            payload.get("currency_conflict")
            or payload.get("requires_base_amount")
            or (orig_curr and orig_curr.upper() != (acc.currency.upper() if acc else base_curr.upper()))
        )
        dir_uncertain = bool(payload.get("direction_uncertain") or payload.get("is_ambiguous_direction"))

        parsed_items.append({
            "item": item,
            "payload": payload,
            "tx_type": tx_type,
            "direction_uncertain": dir_uncertain,
            "currency_conflict": curr_conflict,
            "original_currency": orig_curr,
            "date": d_utc,
            "account": acc,
            "account_id": item.suggested_account_id,
            "account_name": acc.name if acc else "Unassigned",
            "currency": (acc.currency if acc else payload.get("currency", base_curr)).upper(),
            "amount_pence": item.extracted_amount_pence or 0,
            "merchant": item.extracted_merchant or "",
            "notes": payload.get("notes") or "",
        })

    # Fetch ledger transactions in the overlapping date window for staging comparisons
    ledger_txs: List[Transaction] = []
    ledger_by_amount: Dict[int, List[Transaction]] = defaultdict(list)
    if earliest_date and latest_date:
        w_start = earliest_date - timedelta(days=SUGGESTION_DATE_WINDOW_DAYS)
        w_end = latest_date + timedelta(days=SUGGESTION_DATE_WINDOW_DAYS)
        ledger_txs = (
            db.query(Transaction)
            .options(joinedload(Transaction.account))
            .filter(
                Transaction.deleted_at.is_(None),
                Transaction.transaction_date >= w_start,
                Transaction.transaction_date <= w_end
            )
            .order_by(Transaction.transaction_date.desc())
            .all()
        )
        for ltx in ledger_txs:
            if ltx.amount_pence and ltx.amount_pence > 0:
                ledger_by_amount[ltx.amount_pence].append(ltx)

    # -------------------------------------------------------------
    # A. DUPLICATE SUGGESTIONS
    # -------------------------------------------------------------
    # 1. Intra-staging duplicates (two pending items in staging)
    seen_dup_pairs = set()

    for i in range(len(parsed_items)):
        a = parsed_items[i]
        if a["amount_pence"] <= 0 or not a["date"]:
            continue

        for j in range(i + 1, len(parsed_items)):
            b = parsed_items[j]
            if b["amount_pence"] <= 0 or not b["date"]:
                continue

            pair_id = f"dup_staging_{min(a['item'].id, b['item'].id)}_{max(a['item'].id, b['item'].id)}"
            if (not include_dismissed and pair_id in dismissed) or pair_id in seen_dup_pairs:
                continue

            # Amount must match exactly
            if a["amount_pence"] != b["amount_pence"]:
                continue

            # Dates must be within window
            day_diff = abs((a["date"].date() - b["date"].date()).days)
            if day_diff > SUGGESTION_DATE_WINDOW_DAYS:
                continue

            # Account compatibility: same account or one/both unassigned
            same_account = (a["account_id"] == b["account_id"]) and (a["account_id"] is not None)
            compat_account = same_account or (a["account_id"] is None) or (b["account_id"] is None)
            if not compat_account:
                continue

            # Merchant similarity
            merchant_match = _merchant_tokens_overlap(a["merchant"], b["merchant"])
            if not same_account and not merchant_match:
                continue

            # Build explainable match reasons
            reasons = [f"Exact amount: {format_pence(a['amount_pence'], base_spec.symbol)}"]
            if day_diff == 0:
                reasons.append("Exact same date")
            else:
                reasons.append(f"Dates {day_diff} day{'s' if day_diff > 1 else ''} apart")

            if same_account:
                reasons.append(f"Same account: {a['account_name']}")
            elif a["account_id"] is None or b["account_id"] is None:
                reasons.append("Compatible unassigned account")

            if merchant_match:
                reasons.append(f"Matching narrative: '{a['merchant']}' ~ '{b['merchant']}'")

            seen_dup_pairs.add(pair_id)
            duplicate_suggestions.append({
                "id": pair_id,
                "type": "duplicate",
                "subtype": "staging_staging",
                "is_dismissed": pair_id in dismissed,
                "reasons": reasons,
                "record_a": {
                    "id": a["item"].id,
                    "kind": "staging",
                    "date": a["date"].strftime("%Y-%m-%d"),
                    "amount_pence": a["amount_pence"],
                    "formatted_amount": format_pence(a["amount_pence"], base_spec.symbol),
                    "merchant": a["merchant"],
                    "account_name": a["account_name"],
                    "account_id": a["account_id"],
                    "source_type": a["item"].source_type,
                    "source_filename": a["payload"].get("source_filename"),
                },
                "record_b": {
                    "id": b["item"].id,
                    "kind": "staging",
                    "date": b["date"].strftime("%Y-%m-%d"),
                    "amount_pence": b["amount_pence"],
                    "formatted_amount": format_pence(b["amount_pence"], base_spec.symbol),
                    "merchant": b["merchant"],
                    "account_name": b["account_name"],
                    "account_id": b["account_id"],
                    "source_type": b["item"].source_type,
                    "source_filename": b["payload"].get("source_filename"),
                }
            })

    # 2. Staging vs Ledger duplicates (bucketed by exact amount_pence for O(N) scan)
    for a in parsed_items:
        if a["amount_pence"] <= 0 or not a["date"]:
            continue

        for ltx in ledger_by_amount.get(a["amount_pence"], ()):
            pair_id = f"dup_staging_ledger_{a['item'].id}_{ltx.id}"
            if (not include_dismissed and pair_id in dismissed) or pair_id in seen_dup_pairs:
                continue

            ltx_date = ensure_utc(ltx.transaction_date)
            if not ltx_date:
                continue

            day_diff = abs((a["date"].date() - ltx_date.date()).days)
            if day_diff > SUGGESTION_DATE_WINDOW_DAYS:
                continue

            same_account = (a["account_id"] == ltx.account_id) and (a["account_id"] is not None)
            compat_account = same_account or (a["account_id"] is None)
            if not compat_account:
                continue

            merchant_match = _merchant_tokens_overlap(a["merchant"], ltx.merchant)
            if not same_account and not merchant_match:
                continue

            reasons = [f"Exact amount: {format_pence(a['amount_pence'], base_spec.symbol)}"]
            if day_diff == 0:
                reasons.append("Exact same date")
            else:
                reasons.append(f"Dates {day_diff} day{'s' if day_diff > 1 else ''} apart")

            ltx_acc_name = ltx.account.name if ltx.account else "Unassigned"
            if same_account:
                reasons.append(f"Same account: {a['account_name']}")
            elif a["account_id"] is None:
                reasons.append(f"Compatible with ledger account '{ltx_acc_name}'")

            if merchant_match:
                reasons.append(f"Matching narrative: '{a['merchant']}' ~ '{ltx.merchant}'")

            seen_dup_pairs.add(pair_id)
            duplicate_suggestions.append({
                "id": pair_id,
                "type": "duplicate",
                "subtype": "staging_ledger",
                "is_dismissed": pair_id in dismissed,
                "reasons": reasons,
                "record_a": {
                    "id": a["item"].id,
                    "kind": "staging",
                    "date": a["date"].strftime("%Y-%m-%d"),
                    "amount_pence": a["amount_pence"],
                    "formatted_amount": format_pence(a["amount_pence"], base_spec.symbol),
                    "merchant": a["merchant"],
                    "account_name": a["account_name"],
                    "account_id": a["account_id"],
                    "source_type": a["item"].source_type,
                    "source_filename": a["payload"].get("source_filename"),
                },
                "record_b": {
                    "id": ltx.id,
                    "kind": "ledger",
                    "date": ltx_date.strftime("%Y-%m-%d"),
                    "amount_pence": ltx.amount_pence,
                    "formatted_amount": format_pence(ltx.amount_pence, base_spec.symbol),
                    "merchant": ltx.merchant,
                    "account_name": ltx_acc_name,
                    "account_id": ltx.account_id,
                    "source_type": ltx.entry_method or "ledger",
                    "source_filename": ltx.receipt_path,
                }
            })

    # -------------------------------------------------------------
    # B. TRANSFER SUGGESTIONS
    # -------------------------------------------------------------
    seen_transfer_pairs = set()

    # 1. Intra-staging transfer candidates:
    # One is expense (money out from Acc A), one is income (money in to Acc B)
    for i in range(len(parsed_items)):
        a = parsed_items[i]
        if (
            a["amount_pence"] <= 0
            or not a["date"]
            or not a["account_id"]
            or not a["account"]
            or a["direction_uncertain"]
            or a["currency_conflict"]
        ):
            continue

        for j in range(len(parsed_items)):
            if i == j:
                continue
            b = parsed_items[j]
            if (
                b["amount_pence"] <= 0
                or not b["date"]
                or not b["account_id"]
                or not b["account"]
                or b["direction_uncertain"]
                or b["currency_conflict"]
            ):
                continue

            # Need distinct accounts
            if a["account_id"] == b["account_id"]:
                continue

            # Currencies must be identical and match base currency
            if a["currency"] != b["currency"] or a["currency"] != base_curr.upper():
                continue

            # Exactly one must be expense (source) and one must be income (dest)
            if not (a["tx_type"] == "expense" and b["tx_type"] == "income"):
                continue

            # Amounts must be equal in pence
            if a["amount_pence"] != b["amount_pence"]:
                continue

            # Close dates (within window)
            day_diff = abs((a["date"].date() - b["date"].date()).days)
            if day_diff > SUGGESTION_DATE_WINDOW_DAYS:
                continue

            pair_id = f"transfer_staging_{a['item'].id}_{b['item'].id}"
            if (not include_dismissed and pair_id in dismissed) or pair_id in seen_transfer_pairs:
                continue

            is_plausible, score, extra_reasons = _score_transfer_pair(
                day_diff=day_diff,
                out_merchant=a["merchant"],
                out_notes=a["notes"],
                out_acc=a["account"],
                in_merchant=b["merchant"],
                in_notes=b["notes"],
                in_acc=b["account"],
            )
            if not is_plausible:
                continue

            reasons = [
                f"Equal amount: {format_pence(a['amount_pence'], base_spec.symbol)}",
                f"Distinct accounts: {a['account_name']} (out) → {b['account_name']} (in)",
                "Same day" if day_diff == 0 else f"{day_diff} day{'s' if day_diff > 1 else ''} apart",
            ] + extra_reasons

            seen_transfer_pairs.add(pair_id)
            raw_transfer_candidates.append({
                "id": pair_id,
                "type": "transfer",
                "subtype": "staging_staging",
                "reasons": reasons,
                "action_explanation": (
                    f"Confirming will create one dual-account Transfer ({a['account_name']} → {b['account_name']}) "
                    f"in the Ledger and mark both Staging #{a['item'].id} and Staging #{b['item'].id} as approved, "
                    f"archiving and preserving their source files and audit trail."
                ),
                "_score": score,
                "source_record": {
                    "id": a["item"].id,
                    "kind": "staging",
                    "date": a["date"].strftime("%Y-%m-%d"),
                    "amount_pence": a["amount_pence"],
                    "formatted_amount": format_pence(a["amount_pence"], base_spec.symbol),
                    "merchant": a["merchant"],
                    "account_name": a["account_name"],
                    "account_id": a["account_id"],
                    "direction": "Outgoing (Staging)",
                    "source_type": a["item"].source_type,
                    "source_filename": a["payload"].get("source_filename"),
                },
                "destination_record": {
                    "id": b["item"].id,
                    "kind": "staging",
                    "date": b["date"].strftime("%Y-%m-%d"),
                    "amount_pence": b["amount_pence"],
                    "formatted_amount": format_pence(b["amount_pence"], base_spec.symbol),
                    "merchant": b["merchant"],
                    "account_name": b["account_name"],
                    "account_id": b["account_id"],
                    "direction": "Incoming (Staging)",
                    "source_type": b["item"].source_type,
                    "source_filename": b["payload"].get("source_filename"),
                }
            })

    # 2. Staging vs Ledger transfer candidates:
    # Staged expense matching existing unlinked ledger income, or staged income matching existing unlinked ledger expense
    for a in parsed_items:
        if (
            a["amount_pence"] <= 0
            or not a["date"]
            or not a["account_id"]
            or not a["account"]
            or a["direction_uncertain"]
            or a["currency_conflict"]
        ):
            continue

        for ltx in ledger_by_amount.get(a["amount_pence"], ()):
            # Skip existing ledger transfers or adjustments
            if ltx.transaction_type not in (TransactionType.EXPENSE, TransactionType.INCOME):
                continue
            if not ltx.account_id or not ltx.account:
                continue
            if a["account_id"] == ltx.account_id:
                continue

            ltx_curr = (ltx.account.currency or base_curr).upper()
            if a["currency"] != ltx_curr or ltx_curr != base_curr.upper():
                continue

            # Never pair across foreign original currencies without verified conversion
            if ltx.original_currency and ltx.original_currency.upper() != ltx_curr:
                continue

            ltx_date = ensure_utc(ltx.transaction_date)
            if not ltx_date:
                continue

            day_diff = abs((a["date"].date() - ltx_date.date()).days)
            if day_diff > SUGGESTION_DATE_WINDOW_DAYS:
                continue

            # Case A: Staged is outgoing expense, Ledger is incoming income
            if a["tx_type"] == "expense" and ltx.transaction_type == TransactionType.INCOME:
                pair_id = f"transfer_staging_ledger_{a['item'].id}_{ltx.id}"
                if (not include_dismissed and pair_id in dismissed) or pair_id in seen_transfer_pairs:
                    continue

                is_plausible, score, extra_reasons = _score_transfer_pair(
                    day_diff=day_diff,
                    out_merchant=a["merchant"],
                    out_notes=a["notes"],
                    out_acc=a["account"],
                    in_merchant=ltx.merchant,
                    in_notes=ltx.notes,
                    in_acc=ltx.account,
                )
                if not is_plausible:
                    continue

                reasons = [
                    f"Equal amount: {format_pence(a['amount_pence'], base_spec.symbol)}",
                    f"Distinct accounts: {a['account_name']} (out) → {ltx.account.name} (in)",
                    "Same day" if day_diff == 0 else f"{day_diff} day{'s' if day_diff > 1 else ''} apart",
                ] + extra_reasons

                seen_transfer_pairs.add(pair_id)
                raw_transfer_candidates.append({
                    "id": pair_id,
                    "type": "transfer",
                    "subtype": "staging_out_ledger_in",
                    "reasons": reasons,
                    "action_explanation": (
                        f"Confirming will convert existing Ledger #{ltx.id} ({ltx.account.name}) into a "
                        f"dual-account Transfer ({a['account_name']} → {ltx.account.name}) and mark "
                        f"Staging #{a['item'].id} as approved, preserving both records' dates, notes, and source files."
                    ),
                    "_score": score,
                    "source_record": {
                        "id": a["item"].id,
                        "kind": "staging",
                        "date": a["date"].strftime("%Y-%m-%d"),
                        "amount_pence": a["amount_pence"],
                        "formatted_amount": format_pence(a["amount_pence"], base_spec.symbol),
                        "merchant": a["merchant"],
                        "account_name": a["account_name"],
                        "account_id": a["account_id"],
                        "direction": "Outgoing (Staging)",
                        "source_type": a["item"].source_type,
                        "source_filename": a["payload"].get("source_filename"),
                    },
                    "destination_record": {
                        "id": ltx.id,
                        "kind": "ledger",
                        "date": ltx_date.strftime("%Y-%m-%d"),
                        "amount_pence": ltx.amount_pence,
                        "formatted_amount": format_pence(ltx.amount_pence, base_spec.symbol),
                        "merchant": ltx.merchant or "Merchant not recorded",
                        "account_name": ltx.account.name,
                        "account_id": ltx.account_id,
                        "direction": "Incoming (Ledger)",
                        "source_type": ltx.entry_method or "ledger",
                        "source_filename": ltx.receipt_path,
                    }
                })

            # Case B: Staged is incoming income, Ledger is outgoing expense
            elif a["tx_type"] == "income" and ltx.transaction_type == TransactionType.EXPENSE:
                pair_id = f"transfer_ledger_staging_{ltx.id}_{a['item'].id}"
                if (not include_dismissed and pair_id in dismissed) or pair_id in seen_transfer_pairs:
                    continue

                is_plausible, score, extra_reasons = _score_transfer_pair(
                    day_diff=day_diff,
                    out_merchant=ltx.merchant,
                    out_notes=ltx.notes,
                    out_acc=ltx.account,
                    in_merchant=a["merchant"],
                    in_notes=a["notes"],
                    in_acc=a["account"],
                )
                if not is_plausible:
                    continue

                reasons = [
                    f"Equal amount: {format_pence(a['amount_pence'], base_spec.symbol)}",
                    f"Distinct accounts: {ltx.account.name} (out) → {a['account_name']} (in)",
                    "Same day" if day_diff == 0 else f"{day_diff} day{'s' if day_diff > 1 else ''} apart",
                ] + extra_reasons

                seen_transfer_pairs.add(pair_id)
                raw_transfer_candidates.append({
                    "id": pair_id,
                    "type": "transfer",
                    "subtype": "ledger_out_staging_in",
                    "reasons": reasons,
                    "action_explanation": (
                        f"Confirming will convert existing Ledger #{ltx.id} ({ltx.account.name}) into a "
                        f"dual-account Transfer ({ltx.account.name} → {a['account_name']}) and mark "
                        f"Staging #{a['item'].id} as approved, preserving both records' dates, notes, and source files."
                    ),
                    "_score": score,
                    "source_record": {
                        "id": ltx.id,
                        "kind": "ledger",
                        "date": ltx_date.strftime("%Y-%m-%d"),
                        "amount_pence": ltx.amount_pence,
                        "formatted_amount": format_pence(ltx.amount_pence, base_spec.symbol),
                        "merchant": ltx.merchant or "Merchant not recorded",
                        "account_name": ltx.account.name,
                        "account_id": ltx.account_id,
                        "direction": "Outgoing (Ledger)",
                        "source_type": ltx.entry_method or "ledger",
                        "source_filename": ltx.receipt_path,
                    },
                    "destination_record": {
                        "id": a["item"].id,
                        "kind": "staging",
                        "date": a["date"].strftime("%Y-%m-%d"),
                        "amount_pence": a["amount_pence"],
                        "formatted_amount": format_pence(a["amount_pence"], base_spec.symbol),
                        "merchant": a["merchant"],
                        "account_name": a["account_name"],
                        "account_id": a["account_id"],
                        "direction": "Incoming (Staging)",
                        "source_type": a["item"].source_type,
                        "source_filename": a["payload"].get("source_filename"),
                    }
                })

    # 3. Ledger vs Ledger transfer candidates (amount-bucketed + binary-searched by date for O(N log N) scaling)
    # Unlinked outgoing EXPENSE on Account A paired with unlinked incoming INCOME on distinct Account B
    base_curr_upper = base_curr.upper()
    unlinked_ledger_txs = (
        db.query(Transaction)
        .options(joinedload(Transaction.account))
        .filter(
            Transaction.deleted_at.is_(None),
            Transaction.transaction_type.in_([TransactionType.EXPENSE, TransactionType.INCOME]),
            Transaction.account_id.isnot(None),
            Transaction.amount_pence > 0,
        )
        .order_by(Transaction.transaction_date.desc(), Transaction.id.desc())
        .all()
    )

    outgoing_ledger = [t for t in unlinked_ledger_txs if t.transaction_type == TransactionType.EXPENSE and t.account]
    incoming_buckets: Dict[Tuple[str, int], List[Tuple[Any, Transaction, datetime]]] = defaultdict(list)

    for in_tx in unlinked_ledger_txs:
        if in_tx.transaction_type != TransactionType.INCOME or not in_tx.account:
            continue
        in_curr = (in_tx.account.currency or base_curr).upper()
        if in_curr != base_curr_upper:
            continue
        if in_tx.original_currency and in_tx.original_currency.upper() != in_curr:
            continue
        in_date = ensure_utc(in_tx.transaction_date)
        if not in_date:
            continue
        incoming_buckets[(in_curr, in_tx.amount_pence)].append((in_date.date(), in_tx, in_date))

    incoming_bucket_dates: Dict[Tuple[str, int], List[Any]] = {}
    for bucket_key, bucket_items in incoming_buckets.items():
        bucket_items.sort(key=lambda entry: (entry[0], entry[1].id))
        incoming_bucket_dates[bucket_key] = [entry[0] for entry in bucket_items]

    for out_tx in outgoing_ledger:
        out_date = ensure_utc(out_tx.transaction_date)
        if not out_date:
            continue
        out_curr = (out_tx.account.currency or base_curr).upper()
        if out_curr != base_curr_upper:
            continue
        if out_tx.original_currency and out_tx.original_currency.upper() != out_curr:
            continue

        bucket_key = (out_curr, out_tx.amount_pence)
        bucket_items = incoming_buckets.get(bucket_key)
        if not bucket_items:
            continue

        date_index = incoming_bucket_dates[bucket_key]
        out_d = out_date.date()
        lo = bisect_left(date_index, out_d - timedelta(days=SUGGESTION_DATE_WINDOW_DAYS))
        hi = bisect_right(date_index, out_d + timedelta(days=SUGGESTION_DATE_WINDOW_DAYS))

        for _, in_tx, in_date in bucket_items[lo:hi]:
            if out_tx.id == in_tx.id or out_tx.account_id == in_tx.account_id:
                continue

            day_diff = abs((out_d - in_date.date()).days)
            if day_diff > SUGGESTION_DATE_WINDOW_DAYS:
                continue

            pair_id = f"transfer_ledger_ledger_{out_tx.id}_{in_tx.id}"
            if (not include_dismissed and pair_id in dismissed) or pair_id in seen_transfer_pairs:
                continue

            is_plausible, score, extra_reasons = _score_transfer_pair(
                day_diff=day_diff,
                out_merchant=out_tx.merchant,
                out_notes=out_tx.notes,
                out_acc=out_tx.account,
                in_merchant=in_tx.merchant,
                in_notes=in_tx.notes,
                in_acc=in_tx.account,
            )
            if not is_plausible:
                continue

            reasons = [
                f"Equal amount: {format_pence(out_tx.amount_pence, base_spec.symbol)}",
                f"Opposite directions across distinct accounts: {out_tx.account.name} (Expense) → {in_tx.account.name} (Income)",
                "Same day" if day_diff == 0 else f"{day_diff} day{'s' if day_diff > 1 else ''} apart",
            ] + extra_reasons

            seen_transfer_pairs.add(pair_id)
            raw_transfer_candidates.append({
                "id": pair_id,
                "type": "transfer",
                "subtype": "ledger_ledger",
                "reasons": reasons,
                "action_explanation": (
                    f"Confirming will convert Ledger #{out_tx.id} ({out_tx.account.name}, {out_date.strftime('%Y-%m-%d')}) "
                    f"into a single dual-account Transfer ({out_tx.account.name} → {in_tx.account.name}) and merge "
                    f"counterpart Ledger #{in_tx.id} ({in_tx.account.name}, {in_date.strftime('%Y-%m-%d')}) into it, "
                    f"preserving both original dates, narratives, notes, and archived source files in the audit trail."
                ),
                "_score": score,
                "source_record": {
                    "id": out_tx.id,
                    "kind": "ledger",
                    "date": out_date.strftime("%Y-%m-%d"),
                    "amount_pence": out_tx.amount_pence,
                    "formatted_amount": format_pence(out_tx.amount_pence, base_spec.symbol),
                    "merchant": out_tx.merchant or "Merchant not recorded",
                    "account_name": out_tx.account.name,
                    "account_id": out_tx.account_id,
                    "direction": "Outgoing (Ledger Expense)",
                    "source_type": out_tx.entry_method or "ledger",
                    "source_filename": out_tx.receipt_path,
                },
                "destination_record": {
                    "id": in_tx.id,
                    "kind": "ledger",
                    "date": in_date.strftime("%Y-%m-%d"),
                    "amount_pence": in_tx.amount_pence,
                    "formatted_amount": format_pence(in_tx.amount_pence, base_spec.symbol),
                    "merchant": in_tx.merchant or "Merchant not recorded",
                    "account_name": in_tx.account.name,
                    "account_id": in_tx.account_id,
                    "direction": "Incoming (Ledger Income)",
                    "source_type": in_tx.entry_method or "ledger",
                    "source_filename": in_tx.receipt_path,
                }
            })

    transfer_suggestions = _filter_ambiguous_transfer_candidates(raw_transfer_candidates)
    if include_dismissed:
        for item in transfer_suggestions:
            item["is_dismissed"] = item["id"] in dismissed
    else:
        for item in transfer_suggestions:
            item["is_dismissed"] = False

    return {
        "duplicate_suggestions": duplicate_suggestions,
        "transfer_suggestions": transfer_suggestions,
        "summary": {
            "duplicates_count": len([d for d in duplicate_suggestions if not d.get("is_dismissed")]),
            "transfers_count": len([t for t in transfer_suggestions if not t.get("is_dismissed")]),
        }
    }


def confirm_duplicate_suggestion(
    db: Session,
    duplicate_staging_id: int,
    suggestion_id: Optional[str] = None,
    staging_dir: Optional[Path] = None,
    archive_dir: Optional[Path] = None
) -> bool:
    """
    Excludes the duplicate candidate from staging safely while preserving source files
    needed by pending siblings.
    """
    kwargs = {}
    if staging_dir is not None:
        kwargs["staging_dir"] = staging_dir
    if archive_dir is not None:
        kwargs["archive_dir"] = archive_dir
    success = discard_staging_item(db, duplicate_staging_id, **kwargs)
    if success:
        db.commit()
        if suggestion_id:
            add_dismissed_suggestion_id(db, suggestion_id)
    return success


def _archive_staging_file_for_transfer(
    item: StagingItem,
    archive_dir: Path = ARCHIVE_RECEIPTS_DIR
) -> Tuple[Optional[str], Optional[Path], Optional[Path]]:
    """
    Archives a staging item's source file into archive_dir using content hashing (SHA-256).
    Returns (archived_relative_path, staged_file_to_cleanup, newly_copied_archive_file).
    """
    if not item.temp_file_path:
        return None, None, None

    p = Path(item.temp_file_path)
    source_file = p if p.is_absolute() else DATA_DIR / item.temp_file_path
    if not (source_file.exists() and source_file.is_file()):
        return item.temp_file_path, None, None

    source_bytes = source_file.read_bytes()
    source_hash = hashlib.sha256(source_bytes).hexdigest()
    clean_name = re.sub(r'^[a-f0-9]{8,16}_', '', source_file.name)
    archive_filename = f"{source_hash[:12]}_{clean_name}"

    tx_dt = item.extracted_date or datetime.now(timezone.utc)
    target_folder = archive_dir / f"{tx_dt.year:04d}" / f"{tx_dt.month:02d}"
    target_archive_path = target_folder / archive_filename

    existing_archived_file = None
    if target_archive_path.exists() and hashlib.sha256(target_archive_path.read_bytes()).hexdigest() == source_hash:
        existing_archived_file = target_archive_path
    elif archive_dir.exists():
        for cand in archive_dir.rglob(archive_filename):
            if cand.is_file() and hashlib.sha256(cand.read_bytes()).hexdigest() == source_hash:
                existing_archived_file = cand
                break

    copied_archive_file: Optional[Path] = None
    if existing_archived_file:
        target_archive_path = existing_archived_file
    else:
        target_folder.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_file, target_archive_path)
        copied_archive_file = target_archive_path

    try:
        archived_rel = str(target_archive_path.relative_to(DATA_DIR))
    except ValueError:
        archived_rel = str(target_archive_path)

    return archived_rel, source_file, copied_archive_file


def _cleanup_staged_file_if_unreferenced(db: Session, temp_file_path: Optional[str], source_file: Optional[Path]) -> None:
    if not temp_file_path or not source_file or not source_file.exists():
        return
    remaining_pending = db.query(StagingItem).filter(
        StagingItem.status == StagingStatus.PENDING,
        StagingItem.temp_file_path == temp_file_path
    ).count()
    if remaining_pending == 0:
        try:
            source_file.unlink()
        except OSError:
            pass


TRANSFER_PROVENANCE_SETTING_KEY = "transfer_provenance_registry"


def get_transfer_provenance_map(db: Session) -> Dict[str, Dict[str, Any]]:
    """
    Returns the profile-scoped dictionary of paired transfer provenance records keyed by str(transaction_id).
    100% read-only.
    """
    raw = get_system_setting(db, TRANSFER_PROVENANCE_SETTING_KEY, "{}")
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            return {str(k): v for k, v in data.items() if isinstance(v, dict)}
        return {}
    except Exception:
        return {}


def get_transfer_provenance(db: Session, transaction_id: int) -> Optional[Dict[str, Any]]:
    """
    Returns the structured pre-pairing provenance snapshot for a paired transfer transaction, if any.
    """
    if not transaction_id:
        return None
    return get_transfer_provenance_map(db).get(str(transaction_id))


def _save_transfer_provenance_in_session(db: Session, transaction_id: int, provenance: Dict[str, Any]) -> None:
    """
    Updates the transfer_provenance_registry setting in the current DB session without a separate commit,
    so provenance is persisted atomically alongside the transfer transaction.
    """
    from app.models import SystemSetting
    from app.core.receipts import normalize_transfer_provenance_urls
    current_map = get_transfer_provenance_map(db)
    current_map[str(transaction_id)] = normalize_transfer_provenance_urls(provenance, transaction_id)
    serialized = json.dumps(current_map, indent=2)
    setting = db.query(SystemSetting).filter(SystemSetting.key == TRANSFER_PROVENANCE_SETTING_KEY).first()
    if setting:
        setting.value = serialized
        setting.updated_at = datetime.now(timezone.utc)
    else:
        setting = SystemSetting(
            key=TRANSFER_PROVENANCE_SETTING_KEY,
            value=serialized,
            updated_at=datetime.now(timezone.utc)
        )
        db.add(setting)


def _remove_transfer_provenance_in_session(db: Session, transaction_id: int) -> None:
    from app.models import SystemSetting
    current_map = get_transfer_provenance_map(db)
    tx_key = str(transaction_id)
    if tx_key in current_map:
        del current_map[tx_key]
        serialized = json.dumps(current_map, indent=2)
        setting = db.query(SystemSetting).filter(SystemSetting.key == TRANSFER_PROVENANCE_SETTING_KEY).first()
        if setting:
            setting.value = serialized
            setting.updated_at = datetime.now(timezone.utc)


def _resolve_staging_effective_timestamp(db: Session, item: StagingItem, account: Optional[Account]) -> datetime:
    """
    Resolves the anchor-aware effective_timestamp for a staging item on its target account,
    matching the exact semantics of approve_staging_item.
    """
    from datetime import timedelta
    from app.core.timezone import get_app_timezone, get_today_local, get_midday_utc, parse_date_input
    if item.effective_timestamp:
        return ensure_utc(item.effective_timestamp)
    tx_dt = item.extracted_date or get_now_utc()
    latest_anchor = account.latest_anchor if account else None
    latest_anchor_date = ensure_utc(latest_anchor.anchor_date) if latest_anchor else None
    app_tz = get_app_timezone(db)
    today_local = get_today_local(app_tz)
    item_d = parse_date_input(tx_dt)
    mode = (getattr(item, "anchor_mode", "auto") or "auto").strip().lower()

    if mode in ("already_reflected", "prior_to_anchor"):
        if latest_anchor_date:
            return latest_anchor_date - timedelta(seconds=1)
        return get_midday_utc(tx_dt, tz_str=app_tz)
    elif mode == "after_anchor":
        if latest_anchor_date:
            return max(get_now_utc(), latest_anchor_date + timedelta(seconds=1))
        return get_now_utc()
    else:
        if latest_anchor_date:
            anchor_d = parse_date_input(latest_anchor_date)
            if item_d > anchor_d:
                return get_now_utc() if item_d == today_local else get_midday_utc(tx_dt, tz_str=app_tz)
            return latest_anchor_date - timedelta(seconds=1)
        return get_now_utc() if item_d == today_local else get_midday_utc(tx_dt, tz_str=app_tz)


def _snapshot_ledger_leg(tx: Transaction, account: Account, surviving_on_tx: bool) -> Dict[str, Any]:
    tx_dt = ensure_utc(tx.transaction_date) if tx.transaction_date else None
    eff_dt = ensure_utc(tx.effective_timestamp or tx.transaction_date) if (tx.effective_timestamp or tx.transaction_date) else None
    created_dt = ensure_utc(tx.created_at) if tx.created_at else None
    return {
        "original_kind": "ledger",
        "original_id": tx.id,
        "surviving_on_tx": surviving_on_tx,
        "account_id": account.id,
        "account_name": account.name,
        "transaction_date": tx_dt.isoformat() if tx_dt else None,
        "effective_timestamp": eff_dt.isoformat() if eff_dt else None,
        "created_at": created_dt.isoformat() if created_dt else None,
        "transaction_type": tx.transaction_type.value if tx.transaction_type else "expense",
        "amount_pence": tx.amount_pence,
        "merchant": tx.merchant,
        "notes": tx.notes,
        "entry_method": tx.entry_method or "manual",
        "receipt_path": tx.receipt_path,
        "receipt_url": None,
        "category_id": tx.category_id,
        "expense_nature": tx.expense_nature.value if tx.expense_nature else "unclassified",
        "original_amount": str(tx.original_amount) if tx.original_amount is not None else None,
        "original_currency": tx.original_currency,
        "exchange_rate": str(tx.exchange_rate) if tx.exchange_rate is not None else None,
    }


def _snapshot_staging_leg(
    db: Session,
    item: StagingItem,
    account: Account,
    archived_rel_path: Optional[str],
    tx_type_str: str
) -> Dict[str, Any]:
    payload = json.loads(item.raw_payload_json or "{}")
    tx_dt = ensure_utc(item.extracted_date) if item.extracted_date else get_now_utc()
    eff_dt = _resolve_staging_effective_timestamp(db, item, account)
    created_dt = ensure_utc(item.created_at) if item.created_at else get_now_utc()
    return {
        "original_kind": "staging",
        "original_id": item.id,
        "surviving_on_tx": False,
        "account_id": account.id,
        "account_name": account.name,
        "transaction_date": tx_dt.isoformat() if tx_dt else None,
        "effective_timestamp": eff_dt.isoformat() if eff_dt else None,
        "created_at": created_dt.isoformat() if created_dt else None,
        "transaction_type": tx_type_str,
        "amount_pence": item.extracted_amount_pence,
        "merchant": item.extracted_merchant,
        "notes": payload.get("notes"),
        "entry_method": item.source_type or "staging",
        "receipt_path": archived_rel_path,
        "receipt_url": None,
        "category_id": payload.get("category_id"),
        "expense_nature": item.suggested_expense_nature.value if item.suggested_expense_nature else "unclassified",
        "original_amount": str(payload["original_amount"]) if payload.get("original_amount") is not None else None,
        "original_currency": payload.get("original_currency"),
        "exchange_rate": str(payload["exchange_rate"]) if payload.get("exchange_rate") is not None else None,
        "staging_temp_file_path": item.temp_file_path,
        "staging_raw_payload_json": item.raw_payload_json,
        "staging_suggested_category_name": item.suggested_category_name,
    }


def confirm_transfer_suggestion(
    db: Session,
    source_id: int,
    source_kind: str,
    destination_id: int,
    destination_kind: str,
    suggestion_id: Optional[str] = None,
    staging_dir: Optional[Path] = None,
    archive_dir: Optional[Path] = None
) -> Transaction:
    """
    Atomically creates or completes a transfer between the two records while preserving
    100% of both records' provenance (dates, effective timestamps, merchants/narratives,
    notes, entry methods, and archived receipt/source files) and full reversibility:
    - Primary Transaction fields (transaction_date, effective_timestamp, merchant, entry_method, receipt_path)
      always reflect the outgoing (source) leg, so the source account evaluates its balance against
      the source leg's exact timestamp.
    - Destination-leg fields (destination_transaction_date, destination_effective_timestamp,
      destination_merchant, destination_notes, destination_entry_method, destination_receipt_path)
      and full pre-pairing snapshots of both legs are stored in transfer_provenance_registry
      and evaluated by LedgerEngine.get_account_balance for the destination account.
    - Never alters operating cash flow totals (transfer impact remains £0).
    """
    eff_archive_dir = archive_dir or ARCHIVE_RECEIPTS_DIR
    base_curr = get_effective_base_currency(db).upper()

    if source_kind == "staging" and destination_kind == "staging":
        src_item = db.query(StagingItem).filter(StagingItem.id == source_id).first()
        dest_item = db.query(StagingItem).filter(StagingItem.id == destination_id).first()
        if not src_item or not dest_item:
            raise ValueError("One or both staging items not found.")
        if src_item.id == dest_item.id:
            raise ValueError("Cannot pair a staging item with itself.")

        if src_item.status != StagingStatus.PENDING or dest_item.status != StagingStatus.PENDING:
            raise ValueError("Both items must be pending to pair as a transfer.")

        if not src_item.suggested_account_id or not dest_item.suggested_account_id:
            raise ValueError("Both items must have assigned accounts to create a transfer.")

        if src_item.suggested_account_id == dest_item.suggested_account_id:
            raise ValueError("Source and destination accounts must be distinct.")

        if (
            not src_item.extracted_amount_pence
            or not dest_item.extracted_amount_pence
            or src_item.extracted_amount_pence <= 0
            or src_item.extracted_amount_pence != dest_item.extracted_amount_pence
        ):
            raise ValueError("Both staging items must have matching positive amounts.")

        amount_pence = src_item.extracted_amount_pence

        src_acc = db.query(Account).filter(Account.id == src_item.suggested_account_id).first()
        dest_acc = db.query(Account).filter(Account.id == dest_item.suggested_account_id).first()
        if not src_acc or not dest_acc:
            raise ValueError("Account records not found.")

        src_curr = (src_acc.currency or base_curr).upper()
        dest_curr = (dest_acc.currency or base_curr).upper()
        if src_curr != dest_curr or src_curr != base_curr:
            raise ValueError("Cross-currency transfers cannot be paired without a verified conversion.")

        src_payload = json.loads(src_item.raw_payload_json or "{}")
        dest_payload = json.loads(dest_item.raw_payload_json or "{}")
        if src_payload.get("currency_conflict") or dest_payload.get("currency_conflict"):
            raise ValueError("Cannot pair staging items with unresolved foreign currency conflicts.")

        src_arch_rel, src_cleanup, src_copied = _archive_staging_file_for_transfer(src_item, eff_archive_dir)
        dest_arch_rel, dest_cleanup, dest_copied = _archive_staging_file_for_transfer(dest_item, eff_archive_dir)

        try:
            src_snap = _snapshot_staging_leg(db, src_item, src_acc, src_arch_rel, "expense")
            dest_snap = _snapshot_staging_leg(db, dest_item, dest_acc, dest_arch_rel, "income")

            src_dt = ensure_utc(src_item.extracted_date) if src_item.extracted_date else (
                ensure_utc(dest_item.extracted_date) if dest_item.extracted_date else get_now_utc()
            )
            src_eff_ts = _resolve_staging_effective_timestamp(db, src_item, src_acc)
            src_dt_str = src_dt.strftime("%Y-%m-%d")
            dest_dt_str = ensure_utc(dest_item.extracted_date).strftime("%Y-%m-%d") if dest_item.extracted_date else src_dt_str

            provenance_parts = [
                f"Transfer from {src_acc.name} to {dest_acc.name}",
                f"Paired from Review Queue: Outgoing Staging #{src_item.id} ({src_dt_str}, '{src_item.extracted_merchant or 'N/A'}') "
                f"and Incoming Staging #{dest_item.id} ({dest_dt_str}, '{dest_item.extracted_merchant or 'N/A'}')"
            ]
            if src_payload.get("notes"):
                provenance_parts.append(f"Source notes: {src_payload['notes']}")
            if dest_payload.get("notes"):
                provenance_parts.append(f"Destination notes: {dest_payload['notes']}")
            if src_arch_rel and dest_arch_rel and src_arch_rel != dest_arch_rel:
                provenance_parts.append(f"Destination source file: {dest_arch_rel}")

            notes = " | ".join(provenance_parts)
            primary_merchant = (
                (src_item.extracted_merchant or "").strip()
                or (dest_item.extracted_merchant or "").strip()
                or f"Transfer: {src_acc.name} → {dest_acc.name}"
            )

            tx = Transaction(
                transaction_date=src_dt,
                effective_timestamp=src_eff_ts,
                created_at=get_now_utc(),
                transaction_type=TransactionType.TRANSFER,
                amount_pence=amount_pence,
                merchant=primary_merchant,
                notes=notes,
                entry_method=src_item.source_type or "review_transfer_pair",
                receipt_path=src_arch_rel or dest_arch_rel,
                account_id=src_acc.id,
                destination_account_id=dest_acc.id,
                category_id=None,
                expense_nature=ExpenseNature.UNCLASSIFIED,
            )
            db.add(tx)
            src_item.status = StagingStatus.APPROVED
            dest_item.status = StagingStatus.APPROVED
            db.flush()

            provenance_record = {
                "transaction_id": tx.id,
                "pair_kind": "staging_staging",
                "paired_at": get_now_utc().isoformat(),
                "reversible": True,
                "source_leg": src_snap,
                "destination_leg": dest_snap,
            }
            _save_transfer_provenance_in_session(db, tx.id, provenance_record)

            db.commit()
            db.refresh(tx)

            _cleanup_staged_file_if_unreferenced(db, src_item.temp_file_path, src_cleanup)
            _cleanup_staged_file_if_unreferenced(db, dest_item.temp_file_path, dest_cleanup)

            if suggestion_id:
                add_dismissed_suggestion_id(db, suggestion_id)
            return tx
        except Exception as e:
            db.rollback()
            for copied in (src_copied, dest_copied):
                if copied and copied.exists():
                    try:
                        copied.unlink()
                    except OSError:
                        pass
            raise e

    elif source_kind == "staging" and destination_kind == "ledger":
        src_item = db.query(StagingItem).filter(StagingItem.id == source_id).first()
        dest_tx = db.query(Transaction).filter(Transaction.id == destination_id).first()
        if not src_item or not dest_tx:
            raise ValueError("Staging or Ledger record not found.")

        if src_item.status != StagingStatus.PENDING:
            raise ValueError("Staging item is no longer pending.")
        if dest_tx.transaction_type != TransactionType.INCOME:
            raise ValueError("Counterpart ledger transaction must be an unlinked incoming record.")

        src_acc = db.query(Account).filter(Account.id == src_item.suggested_account_id).first()
        dest_acc = dest_tx.account
        if not src_acc or not dest_acc:
            raise ValueError("Valid accounts required on both sides.")

        if src_acc.id == dest_acc.id:
            raise ValueError("Source and destination accounts must be distinct.")

        if not src_item.extracted_amount_pence or src_item.extracted_amount_pence != dest_tx.amount_pence:
            raise ValueError("Staging and Ledger amounts must match.")

        src_curr = (src_acc.currency or base_curr).upper()
        dest_curr = (dest_acc.currency or base_curr).upper()
        if src_curr != dest_curr or src_curr != base_curr:
            raise ValueError("Cross-currency transfers cannot be paired without a verified conversion.")

        src_payload = json.loads(src_item.raw_payload_json or "{}")
        if src_payload.get("currency_conflict") or (dest_tx.original_currency and dest_tx.original_currency.upper() != dest_curr):
            raise ValueError("Cannot pair records with foreign currency conflicts.")

        src_arch_rel, src_cleanup, src_copied = _archive_staging_file_for_transfer(src_item, eff_archive_dir)

        try:
            src_snap = _snapshot_staging_leg(db, src_item, src_acc, src_arch_rel, "expense")
            dest_snap = _snapshot_ledger_leg(dest_tx, dest_acc, surviving_on_tx=True)

            src_dt = ensure_utc(src_item.extracted_date) if src_item.extracted_date else ensure_utc(dest_tx.transaction_date)
            src_eff_ts = _resolve_staging_effective_timestamp(db, src_item, src_acc)
            src_dt_str = src_dt.strftime("%Y-%m-%d") if src_dt else "unknown"
            dest_dt_str = ensure_utc(dest_tx.transaction_date).strftime("%Y-%m-%d") if dest_tx.transaction_date else "unknown"

            provenance_parts = []
            if src_payload.get("notes"):
                provenance_parts.append(f"Source notes: {src_payload['notes']}")
            if dest_tx.notes:
                provenance_parts.append(f"Destination notes: {dest_tx.notes}")
            provenance_parts.append(
                f"Paired as Transfer ({src_acc.name} → {dest_acc.name}): "
                f"Outgoing Staging #{src_item.id} ({src_dt_str}, '{src_item.extracted_merchant or 'N/A'}') "
                f"+ Incoming Ledger #{dest_tx.id} ({dest_dt_str}, '{dest_tx.merchant or 'N/A'}')"
            )
            if dest_tx.receipt_path and src_arch_rel and dest_tx.receipt_path != src_arch_rel:
                provenance_parts.append(f"Destination source file: {dest_tx.receipt_path}")

            primary_merchant = (
                (src_item.extracted_merchant or "").strip()
                or (dest_tx.merchant or "").strip()
                or f"Transfer: {src_acc.name} → {dest_acc.name}"
            )

            dest_tx.transaction_date = src_dt
            dest_tx.effective_timestamp = src_eff_ts
            dest_tx.transaction_type = TransactionType.TRANSFER
            dest_tx.account_id = src_acc.id
            dest_tx.destination_account_id = dest_acc.id
            dest_tx.category_id = None
            dest_tx.expense_nature = ExpenseNature.UNCLASSIFIED
            dest_tx.merchant = primary_merchant
            dest_tx.entry_method = src_item.source_type or dest_tx.entry_method or "manual"
            dest_tx.notes = " | ".join(provenance_parts)
            dest_tx.receipt_path = src_arch_rel or dest_tx.receipt_path
            src_item.status = StagingStatus.APPROVED

            provenance_record = {
                "transaction_id": dest_tx.id,
                "pair_kind": "staging_ledger",
                "paired_at": get_now_utc().isoformat(),
                "reversible": True,
                "source_leg": src_snap,
                "destination_leg": dest_snap,
            }
            _save_transfer_provenance_in_session(db, dest_tx.id, provenance_record)

            db.commit()
            db.refresh(dest_tx)
            _cleanup_staged_file_if_unreferenced(db, src_item.temp_file_path, src_cleanup)

            if suggestion_id:
                add_dismissed_suggestion_id(db, suggestion_id)
            return dest_tx
        except Exception as e:
            db.rollback()
            if src_copied and src_copied.exists():
                try:
                    src_copied.unlink()
                except OSError:
                    pass
            raise e

    elif source_kind == "ledger" and destination_kind == "staging":
        src_tx = db.query(Transaction).filter(Transaction.id == source_id).first()
        dest_item = db.query(StagingItem).filter(StagingItem.id == destination_id).first()
        if not src_tx or not dest_item:
            raise ValueError("Ledger or Staging record not found.")

        if dest_item.status != StagingStatus.PENDING:
            raise ValueError("Staging item is no longer pending.")
        if src_tx.transaction_type != TransactionType.EXPENSE:
            raise ValueError("Source ledger transaction must be an unlinked outgoing record.")

        src_acc = src_tx.account
        dest_acc = db.query(Account).filter(Account.id == dest_item.suggested_account_id).first()
        if not src_acc or not dest_acc:
            raise ValueError("Valid accounts required on both sides.")

        if src_acc.id == dest_acc.id:
            raise ValueError("Source and destination accounts must be distinct.")

        if not dest_item.extracted_amount_pence or src_tx.amount_pence != dest_item.extracted_amount_pence:
            raise ValueError("Ledger and Staging amounts must match.")

        src_curr = (src_acc.currency or base_curr).upper()
        dest_curr = (dest_acc.currency or base_curr).upper()
        if src_curr != dest_curr or src_curr != base_curr:
            raise ValueError("Cross-currency transfers cannot be paired without a verified conversion.")

        dest_payload = json.loads(dest_item.raw_payload_json or "{}")
        if dest_payload.get("currency_conflict") or (src_tx.original_currency and src_tx.original_currency.upper() != src_curr):
            raise ValueError("Cannot pair records with foreign currency conflicts.")

        dest_arch_rel, dest_cleanup, dest_copied = _archive_staging_file_for_transfer(dest_item, eff_archive_dir)

        try:
            src_snap = _snapshot_ledger_leg(src_tx, src_acc, surviving_on_tx=True)
            dest_snap = _snapshot_staging_leg(db, dest_item, dest_acc, dest_arch_rel, "income")

            src_dt_str = ensure_utc(src_tx.transaction_date).strftime("%Y-%m-%d") if src_tx.transaction_date else "unknown"
            dest_dt_str = ensure_utc(dest_item.extracted_date).strftime("%Y-%m-%d") if dest_item.extracted_date else "unknown"

            provenance_parts = []
            if src_tx.notes:
                provenance_parts.append(f"Source notes: {src_tx.notes}")
            if dest_payload.get("notes"):
                provenance_parts.append(f"Destination notes: {dest_payload['notes']}")
            provenance_parts.append(
                f"Paired as Transfer ({src_acc.name} → {dest_acc.name}): "
                f"Outgoing Ledger #{src_tx.id} ({src_dt_str}, '{src_tx.merchant or 'N/A'}') "
                f"+ Incoming Staging #{dest_item.id} ({dest_dt_str}, '{dest_item.extracted_merchant or 'N/A'}')"
            )
            if src_tx.receipt_path and dest_arch_rel and src_tx.receipt_path != dest_arch_rel:
                provenance_parts.append(f"Destination source file: {dest_arch_rel}")

            primary_merchant = (
                (src_tx.merchant or "").strip()
                or (dest_item.extracted_merchant or "").strip()
                or f"Transfer: {src_acc.name} → {dest_acc.name}"
            )

            # Preserve src_tx's exact transaction_date, effective_timestamp, and entry_method
            src_tx.transaction_type = TransactionType.TRANSFER
            src_tx.destination_account_id = dest_acc.id
            src_tx.category_id = None
            src_tx.expense_nature = ExpenseNature.UNCLASSIFIED
            src_tx.merchant = primary_merchant
            src_tx.notes = " | ".join(provenance_parts)
            src_tx.receipt_path = src_tx.receipt_path or dest_arch_rel
            dest_item.status = StagingStatus.APPROVED

            provenance_record = {
                "transaction_id": src_tx.id,
                "pair_kind": "ledger_staging",
                "paired_at": get_now_utc().isoformat(),
                "reversible": True,
                "source_leg": src_snap,
                "destination_leg": dest_snap,
            }
            _save_transfer_provenance_in_session(db, src_tx.id, provenance_record)

            db.commit()
            db.refresh(src_tx)
            _cleanup_staged_file_if_unreferenced(db, dest_item.temp_file_path, dest_cleanup)

            if suggestion_id:
                add_dismissed_suggestion_id(db, suggestion_id)
            return src_tx
        except Exception as e:
            db.rollback()
            if dest_copied and dest_copied.exists():
                try:
                    dest_copied.unlink()
                except OSError:
                    pass
            raise e

    elif source_kind == "ledger" and destination_kind == "ledger":
        src_tx = db.query(Transaction).filter(Transaction.id == source_id).first()
        dest_tx = db.query(Transaction).filter(Transaction.id == destination_id).first()
        if not src_tx or not dest_tx:
            raise ValueError("One or both ledger records not found.")
        if src_tx.id == dest_tx.id:
            raise ValueError("Cannot pair a ledger transaction with itself.")

        if src_tx.transaction_type != TransactionType.EXPENSE or dest_tx.transaction_type != TransactionType.INCOME:
            raise ValueError("Source must be an unlinked Expense and destination must be an unlinked Income.")

        src_acc = src_tx.account
        dest_acc = dest_tx.account
        if not src_acc or not dest_acc:
            raise ValueError("Valid accounts required on both ledger records.")

        if src_acc.id == dest_acc.id:
            raise ValueError("Source and destination accounts must be distinct.")

        if src_tx.amount_pence <= 0 or src_tx.amount_pence != dest_tx.amount_pence:
            raise ValueError("Both ledger records must have matching positive amounts.")

        src_curr = (src_acc.currency or base_curr).upper()
        dest_curr = (dest_acc.currency or base_curr).upper()
        if src_curr != dest_curr or src_curr != base_curr:
            raise ValueError("Cross-currency transfers cannot be paired without a verified conversion.")

        if (src_tx.original_currency and src_tx.original_currency.upper() != src_curr) or (
            dest_tx.original_currency and dest_tx.original_currency.upper() != dest_curr
        ):
            raise ValueError("Cannot pair ledger records with foreign currency conversion metadata.")

        try:
            src_snap = _snapshot_ledger_leg(src_tx, src_acc, surviving_on_tx=True)
            dest_snap = _snapshot_ledger_leg(dest_tx, dest_acc, surviving_on_tx=False)

            src_dt_str = ensure_utc(src_tx.transaction_date).strftime("%Y-%m-%d") if src_tx.transaction_date else "unknown"
            dest_dt_str = ensure_utc(dest_tx.transaction_date).strftime("%Y-%m-%d") if dest_tx.transaction_date else "unknown"

            provenance_parts = []
            if src_tx.notes:
                provenance_parts.append(f"Source notes: {src_tx.notes}")
            if dest_tx.notes:
                provenance_parts.append(f"Destination notes: {dest_tx.notes}")
            provenance_parts.append(
                f"Paired from Review Queue: Outgoing Ledger #{src_tx.id} ({src_acc.name}, {src_dt_str}, "
                f"'{src_tx.merchant or 'N/A'}', entry={src_tx.entry_method or 'manual'}) "
                f"+ Incoming Ledger #{dest_tx.id} ({dest_acc.name}, {dest_dt_str}, "
                f"'{dest_tx.merchant or 'N/A'}', entry={dest_tx.entry_method or 'manual'})"
            )
            if src_tx.receipt_path and dest_tx.receipt_path and src_tx.receipt_path != dest_tx.receipt_path:
                provenance_parts.append(f"Destination source file: {dest_tx.receipt_path}")

            primary_merchant = (
                (src_tx.merchant or "").strip()
                or (dest_tx.merchant or "").strip()
                or f"Transfer: {src_acc.name} → {dest_acc.name}"
            )

            # Strictly preserve src_tx's own transaction_date, effective_timestamp, and entry_method
            # (dest_tx's timestamp is stored in provenance_record["destination_leg"] and evaluated by LedgerEngine)
            src_tx.transaction_type = TransactionType.TRANSFER
            src_tx.account_id = src_acc.id
            src_tx.destination_account_id = dest_acc.id
            src_tx.category_id = None
            src_tx.expense_nature = ExpenseNature.UNCLASSIFIED
            src_tx.merchant = primary_merchant
            src_tx.notes = " | ".join(provenance_parts)
            src_tx.receipt_path = src_tx.receipt_path or dest_tx.receipt_path
            src_tx.entry_method = src_tx.entry_method or "manual"

            provenance_record = {
                "transaction_id": src_tx.id,
                "pair_kind": "ledger_ledger",
                "paired_at": get_now_utc().isoformat(),
                "reversible": True,
                "source_leg": src_snap,
                "destination_leg": dest_snap,
            }
            _save_transfer_provenance_in_session(db, src_tx.id, provenance_record)

            db.delete(dest_tx)
            db.commit()
            db.refresh(src_tx)

            if suggestion_id:
                add_dismissed_suggestion_id(db, suggestion_id)
            return src_tx
        except Exception as e:
            db.rollback()
            raise e

    else:
        raise ValueError("Invalid record kinds for transfer pairing.")


def _restore_ledger_attributes_from_snapshot(tx: Transaction, snap: Dict[str, Any]) -> None:
    from decimal import Decimal
    if snap.get("transaction_date"):
        tx.transaction_date = ensure_utc(datetime.fromisoformat(str(snap["transaction_date"])))
    if snap.get("effective_timestamp"):
        tx.effective_timestamp = ensure_utc(datetime.fromisoformat(str(snap["effective_timestamp"])))
    if snap.get("created_at"):
        tx.created_at = ensure_utc(datetime.fromisoformat(str(snap["created_at"])))
    tx.transaction_type = TransactionType(snap.get("transaction_type", "expense"))
    tx.amount_pence = int(snap["amount_pence"])
    tx.merchant = snap.get("merchant")
    tx.notes = snap.get("notes")
    tx.entry_method = snap.get("entry_method") or "manual"
    tx.receipt_path = snap.get("receipt_path")
    tx.account_id = snap.get("account_id")
    tx.destination_account_id = None
    tx.category_id = snap.get("category_id")
    try:
        tx.expense_nature = ExpenseNature(snap.get("expense_nature") or "unclassified")
    except ValueError:
        tx.expense_nature = ExpenseNature.UNCLASSIFIED
    tx.original_amount = Decimal(str(snap["original_amount"])) if snap.get("original_amount") is not None else None
    tx.original_currency = snap.get("original_currency")
    tx.exchange_rate = Decimal(str(snap["exchange_rate"])) if snap.get("exchange_rate") is not None else None


def _restore_staging_item_from_snapshot(db: Session, snap: Dict[str, Any]) -> StagingItem:
    orig_id = int(snap["original_id"])
    stg = db.query(StagingItem).filter(StagingItem.id == orig_id).first()
    temp_path = snap.get("staging_temp_file_path")
    arch_rel = snap.get("receipt_path")

    # If the original staging file was cleaned up after archiving, copy the archived file back so temp_file_path exists
    if temp_path and arch_rel:
        src_p = Path(temp_path) if Path(temp_path).is_absolute() else DATA_DIR / temp_path
        arch_p = Path(arch_rel) if Path(arch_rel).is_absolute() else DATA_DIR / arch_rel
        if not src_p.exists() and arch_p.exists():
            try:
                src_p.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(arch_p, src_p)
            except OSError:
                temp_path = arch_rel

    if stg:
        stg.status = StagingStatus.PENDING
        if temp_path:
            stg.temp_file_path = temp_path
        if snap.get("staging_raw_payload_json"):
            stg.raw_payload_json = snap["staging_raw_payload_json"]
        return stg

    tx_dt = ensure_utc(datetime.fromisoformat(str(snap["transaction_date"]))) if snap.get("transaction_date") else None
    eff_dt = ensure_utc(datetime.fromisoformat(str(snap["effective_timestamp"]))) if snap.get("effective_timestamp") else None
    created_dt = ensure_utc(datetime.fromisoformat(str(snap["created_at"]))) if snap.get("created_at") else get_now_utc()
    try:
        nature = ExpenseNature(snap.get("expense_nature") or "unclassified")
    except ValueError:
        nature = ExpenseNature.UNCLASSIFIED

    stg = StagingItem(
        id=orig_id,
        created_at=created_dt,
        status=StagingStatus.PENDING,
        extracted_amount_pence=int(snap["amount_pence"]),
        extracted_date=tx_dt,
        effective_timestamp=eff_dt,
        extracted_merchant=snap.get("merchant"),
        suggested_category_name=snap.get("staging_suggested_category_name"),
        suggested_account_id=snap.get("account_id"),
        suggested_expense_nature=nature,
        source_type=snap.get("entry_method") or "staging",
        temp_file_path=temp_path or arch_rel,
        raw_payload_json=snap.get("staging_raw_payload_json") or "{}",
    )
    db.add(stg)
    return stg


def unpair_transfer_transaction(db: Session, transaction_id: int) -> Dict[str, Any]:
    """
    Atomically reverses a paired transfer transaction back into its original constituent records
    using the stored pre-pairing snapshots in transfer_provenance_registry.
    Restores original IDs, dates, effective timestamps, transaction types, categories,
    expense natures, merchants, notes, entry methods, and receipt/source files.
    """
    tx = db.query(Transaction).filter(Transaction.id == transaction_id).first()
    if not tx:
        raise ValueError(f"Transaction #{transaction_id} not found.")
    if tx.transaction_type != TransactionType.TRANSFER:
        raise ValueError(f"Transaction #{transaction_id} is not a transfer.")

    prov = get_transfer_provenance(db, transaction_id)
    if not prov:
        raise ValueError(
            f"Transfer #{transaction_id} was not created by pairing two records or has no stored provenance to unpair."
        )

    pair_kind = prov.get("pair_kind")
    src_snap = prov.get("source_leg") or {}
    dest_snap = prov.get("destination_leg") or {}

    restored_transaction_ids: List[int] = []
    restored_staging_ids: List[int] = []

    try:
        if pair_kind == "ledger_ledger":
            # Restore src_tx (which is tx itself)
            _restore_ledger_attributes_from_snapshot(tx, src_snap)
            restored_transaction_ids.append(tx.id)

            # Recreate dest_tx with its original ID if available
            orig_dest_id = int(dest_snap["original_id"])
            existing_conflict = db.query(Transaction).filter(Transaction.id == orig_dest_id).first()
            dest_tx = Transaction(id=orig_dest_id if not existing_conflict else None)
            _restore_ledger_attributes_from_snapshot(dest_tx, dest_snap)
            db.add(dest_tx)
            db.flush()
            restored_transaction_ids.append(dest_tx.id)

        elif pair_kind == "ledger_staging":
            _restore_ledger_attributes_from_snapshot(tx, src_snap)
            restored_transaction_ids.append(tx.id)
            stg = _restore_staging_item_from_snapshot(db, dest_snap)
            db.flush()
            restored_staging_ids.append(stg.id)

        elif pair_kind == "staging_ledger":
            _restore_ledger_attributes_from_snapshot(tx, dest_snap)
            restored_transaction_ids.append(tx.id)
            stg = _restore_staging_item_from_snapshot(db, src_snap)
            db.flush()
            restored_staging_ids.append(stg.id)

        elif pair_kind == "staging_staging":
            stg_src = _restore_staging_item_from_snapshot(db, src_snap)
            stg_dest = _restore_staging_item_from_snapshot(db, dest_snap)
            db.delete(tx)
            db.flush()
            restored_staging_ids.extend([stg_src.id, stg_dest.id])

        else:
            raise ValueError(f"Unsupported transfer pair_kind '{pair_kind}'.")

        _remove_transfer_provenance_in_session(db, transaction_id)
        db.commit()

        return {
            "unpaired_transaction_id": transaction_id,
            "pair_kind": pair_kind,
            "restored_transaction_ids": restored_transaction_ids,
            "restored_staging_ids": restored_staging_ids,
            "message": f"Successfully unpaired transfer #{transaction_id} and restored original records.",
        }
    except Exception as e:
        db.rollback()
        raise e
