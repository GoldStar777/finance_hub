"""
Profile-Isolated Data Quality & Review Engine

Provides strictly read-only, offline, explainable analysis across committed Ledger records,
pending Queue (Staging) items, accounts, categories, anchors, and holdings:
1. Transactions without a category (`uncategorised`)
2. Transactions without an account where expected (`unassigned_account`)
3. Potential duplicates (`potential_duplicate`, reusing Queue + indexed Ledger pairs)
4. Possible unpaired transfers (`possible_transfer`, reusing Queue + ambiguity-safe scoring)
5. Uncertain or incomplete imported fields (`uncertain_import`)
6. Archived account/category links (`archived_reference`)
7. Concrete structural & relational integrity issues (`integrity_issue`)

Scanning never mutates financial records. Dismissals are stored per profile in SQLite
system_settings and remain fully reversible (`dismiss` / `restore`).
"""

from bisect import bisect_left, bisect_right
from collections import Counter, defaultdict
import difflib
import json
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Set, Tuple, Union
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.core.backup import get_system_setting
from app.core.categories import expected_category_type_for_transaction
from app.core.currency import format_pence, get_base_currency_readonly, get_currency_spec
from app.core.review_suggestions import (
    SUGGESTION_DATE_WINDOW_DAYS,
    _merchant_tokens_overlap,
    get_dismissed_suggestion_ids,
    get_review_queue_suggestions,
)
from app.core.timezone import ensure_utc, get_app_timezone
from app.core.unified_importer import CATEGORY_CONFIDENCE_THRESHOLDS, normalize_vendor_name
from app.models import (
    Account,
    AccountBalanceAnchor,
    Category,
    CategoryType,
    Holding,
    HoldingValuation,
    StagingItem,
    StagingStatus,
    Transaction,
    TransactionType,
)

ALL_FINDING_TYPES = (
    "uncategorised",
    "unassigned_account",
    "potential_duplicate",
    "possible_transfer",
    "uncertain_import",
    "archived_reference",
    "integrity_issue",
)

ALL_SEVERITIES = ("integrity", "review", "suggestion")

_SEVERITY_ORDER = {"integrity": 0, "review": 1, "suggestion": 2}
_DUPLICATE_WINDOW_CAP = 12


def _local_date_str(dt: Optional[datetime], app_zi: ZoneInfo) -> Optional[str]:
    if not dt:
        return None
    utc_dt = ensure_utc(dt)
    if not utc_dt:
        return None
    return utc_dt.astimezone(app_zi).strftime("%Y-%m-%d")


def _build_ledger_route(params: Dict[str, Any]) -> str:
    clean = {k: str(v) for k, v in params.items() if v is not None and str(v) != ""}
    if not clean:
        return "/ledger"
    return f"/ledger?{urlencode(clean)}"


def _build_queue_route(params: Dict[str, Any]) -> str:
    clean = {k: str(v) for k, v in params.items() if v is not None and str(v) != ""}
    if not clean:
        return "/queue"
    return f"/queue?{urlencode(clean)}"


def _build_category_history_index(
    txs: List[Transaction],
    active_categories: Dict[int, Category],
    target_tx_type: Optional[TransactionType] = None,
) -> Tuple[Dict[str, Counter], List[Tuple[str, Counter]]]:
    """
    Indexes categorized active transactions by normalized merchant once per scan.
    When target_tx_type is given, history is strictly scoped to that direction/purpose.
    Strictly derived from approved profile transactions with zero hardcoded rules.
    """
    exact_map: Dict[str, Counter] = defaultdict(Counter)
    allowed_types = (target_tx_type,) if target_tx_type is not None else (TransactionType.EXPENSE, TransactionType.INCOME)
    for tx in txs:
        if tx.category_id not in active_categories:
            continue
        if tx.transaction_type not in allowed_types:
            continue
        if not tx.merchant:
            continue
        norm_m = normalize_vendor_name(tx.merchant)
        if len(norm_m) < 2:
            continue
        exact_map[norm_m][tx.category_id] += 1

    hist_entries = list(exact_map.items())
    return exact_map, hist_entries


def _suggest_category_from_history(
    merchant: Optional[str],
    exact_map: Dict[str, Counter],
    hist_entries: List[Tuple[str, Counter]],
    active_categories: Dict[int, Category],
    confidence_level: str,
) -> Optional[Dict[str, Any]]:
    """
    Finds an unambiguous category suggestion from existing approved history in the same profile.
    Respects per-profile `import_confidence_category`. Returns None if ambiguous or weak.
    """
    if not merchant or not active_categories or not hist_entries:
        return None
    norm_m = normalize_vendor_name(merchant)
    if len(norm_m) < 2:
        return None

    threshold = CATEGORY_CONFIDENCE_THRESHOLDS.get(str(confidence_level or "balanced").strip().lower(), 0.45)

    combined = Counter()
    match_strength = 0.0

    if norm_m in exact_map:
        combined.update(exact_map[norm_m])
        match_strength = 1.0
    elif len(norm_m) >= 4:
        min_ratio = max(0.82, threshold)
        # Inspect candidate pool efficiently up to reasonable prefix/substring matches
        for h_norm, counts in hist_entries:
            if len(h_norm) >= 4 and (norm_m in h_norm or h_norm in norm_m):
                combined.update(counts)
                match_strength = max(match_strength, 0.90)
            elif abs(len(h_norm) - len(norm_m)) <= 4:
                ratio = difflib.SequenceMatcher(None, norm_m, h_norm).ratio()
                if ratio >= min_ratio:
                    combined.update(counts)
                    match_strength = max(match_strength, ratio)

    if not combined or match_strength < threshold:
        return None

    total = sum(combined.values())
    top_cat_id, top_count = combined.most_common(1)[0]
    cat = active_categories.get(top_cat_id)
    if not cat:
        return None

    if len(combined) == 1:
        reason = f"Matches {total} approved transaction(s) for '{merchant}' -> {cat.name}"
    elif (top_count / total) >= 0.75:
        reason = f"Matches {top_count} of {total} similar approved entries -> {cat.name}"
    else:
        return None

    return {
        "category_id": cat.id,
        "category_name": cat.name,
        "confidence": "high" if match_strength >= 0.90 and len(combined) == 1 else "medium",
        "reason": reason,
    }


def _scan_ledger_duplicates(
    txs: List[Transaction],
    acc_map: Dict[int, Account],
    base_curr: str,
    base_symbol: str,
    app_zi: ZoneInfo,
    dismissed: Set[str],
    confidence_level: str,
    include_dismissed: bool,
) -> List[Dict[str, Any]]:
    """
    Amount-bucketed, date-sorted scan for potential committed ledger-vs-ledger duplicates.
    Runs in near-linear time even across thousands of transactions.
    Safeguards:
    - Excludes deleted rows and non-positive amounts
    - Ignores opposite transaction types (handled by Transfer detection)
    - Suppresses receipt split siblings sharing identical receipt_path
    - Suppresses repeat-series rows on distinct calendar days
    - Requires strong narrative or same-account+same-day agreement; avoids pairing unrelated merchants
    """
    clean_conf = str(confidence_level or "balanced").strip().lower()
    buckets: Dict[Tuple[str, int], List[Tuple[date, Transaction]]] = defaultdict(list)

    for tx in txs:
        if tx.amount_pence is None or tx.amount_pence <= 0 or not tx.transaction_date:
            continue
        dt_utc = ensure_utc(tx.transaction_date)
        if not dt_utc:
            continue
        local_d = dt_utc.astimezone(app_zi).date()
        buckets[(tx.transaction_type.value, tx.amount_pence)].append((local_d, tx))

    findings: List[Dict[str, Any]] = []
    seen_pairs: Set[str] = set()

    for (_, amt_pence), bucket in buckets.items():
        if len(bucket) < 2:
            continue
        bucket.sort(key=lambda item: (item[0], item[1].id))
        dates = [item[0] for item in bucket]

        for i in range(len(bucket)):
            d_a, a = bucket[i]
            hi = bisect_right(dates, d_a + timedelta(days=SUGGESTION_DATE_WINDOW_DAYS), lo=i + 1)
            # Guard against quadratic explosion on synthetic runs of identical recurring amounts
            window_slice = bucket[i + 1 : min(hi, i + 1 + _DUPLICATE_WINDOW_CAP)]

            acc_a = acc_map.get(a.account_id) if a.account_id else None
            curr_a = (acc_a.currency if acc_a else base_curr).upper()
            spec_a = get_currency_spec(curr_a)

            for d_b, b in window_slice:
                if a.id == b.id:
                    continue
                pair_id = f"dup_ledger_ledger_{min(a.id, b.id)}_{max(a.id, b.id)}"
                if pair_id in seen_pairs or (not include_dismissed and pair_id in dismissed):
                    continue

                # Skip split allocations originating from the exact same receipt file
                if a.receipt_path and b.receipt_path and a.receipt_path == b.receipt_path:
                    continue

                day_diff = abs((d_b - d_a).days)
                if day_diff > SUGGESTION_DATE_WINDOW_DAYS:
                    continue

                # Skip intentional repeat series siblings on different dates
                if a.repeat_series_id and a.repeat_series_id == b.repeat_series_id and day_diff >= 1:
                    continue

                # Transfers must also share destination account to be candidate duplicates
                if a.transaction_type == TransactionType.TRANSFER:
                    if a.destination_account_id != b.destination_account_id:
                        continue

                acc_b = acc_map.get(b.account_id) if b.account_id else None
                curr_b = (acc_b.currency if acc_b else base_curr).upper()
                if curr_a != curr_b:
                    continue

                same_account = (a.account_id == b.account_id) and (a.account_id is not None)
                compat_account = same_account or (
                    clean_conf != "cautious" and (a.account_id is None or b.account_id is None)
                )
                if not compat_account:
                    continue

                m_a = (a.merchant or "").strip()
                m_b = (b.merchant or "").strip()
                both_named = bool(m_a and m_b)
                merchant_match = _merchant_tokens_overlap(m_a, m_b) if both_named else False

                # Reject pairs where both entries name unrelated merchants
                if both_named and not merchant_match:
                    continue

                # Require either matching narrative or same-account same/close-day without conflicting names
                if clean_conf == "cautious":
                    if not (merchant_match or (same_account and day_diff == 0 and not both_named)):
                        continue
                else:
                    if not same_account and not merchant_match:
                        continue
                    if same_account and day_diff > 1 and not merchant_match:
                        continue

                seen_pairs.add(pair_id)
                acc_name_a = acc_a.name if acc_a else "Unassigned"
                acc_name_b = acc_b.name if acc_b else "Unassigned"
                reasons = [f"Exact amount: {format_pence(amt_pence, spec_a.symbol)}"]
                reasons.append("Exact same date" if day_diff == 0 else f"Dates {day_diff} day{'s' if day_diff > 1 else ''} apart")
                if same_account:
                    reasons.append(f"Same account: {acc_name_a}")
                else:
                    reasons.append("Compatible unassigned account")
                if merchant_match:
                    reasons.append(f"Matching merchant: '{m_a}' ~ '{m_b}'")
                elif not m_a and not m_b:
                    reasons.append("Both entries lack a recorded merchant")

                is_high_conf = same_account and day_diff == 0 and (merchant_match or (not m_a and not m_b))
                newer, older = (b, a) if (d_b, b.id) >= (d_a, a.id) else (a, b)
                d_min = min(d_a, d_b).isoformat()
                d_max = max(d_a, d_b).isoformat()

                rec_a_obj = {
                    "id": a.id,
                    "kind": "ledger",
                    "date": d_a.isoformat(),
                    "amount_pence": a.amount_pence,
                    "formatted_amount": format_pence(a.amount_pence, spec_a.symbol),
                    "merchant": m_a or "Merchant not recorded",
                    "account_id": a.account_id,
                    "account_name": acc_name_a,
                    "source_type": a.entry_method or "manual",
                    "source_filename": a.receipt_path,
                }
                rec_b_obj = {
                    "id": b.id,
                    "kind": "ledger",
                    "date": d_b.isoformat(),
                    "amount_pence": b.amount_pence,
                    "formatted_amount": format_pence(b.amount_pence, spec_a.symbol),
                    "merchant": m_b or "Merchant not recorded",
                    "account_id": b.account_id,
                    "account_name": acc_name_b,
                    "source_type": b.entry_method or "manual",
                    "source_filename": b.receipt_path,
                }

                findings.append({
                    "id": pair_id,
                    "finding_type": "potential_duplicate",
                    "severity": "review" if is_high_conf else "suggestion",
                    "confidence": "high" if is_high_conf else "medium",
                    "title": f"Possible duplicate ledger entry ({format_pence(amt_pence, spec_a.symbol)})",
                    "summary": (
                        f"Ledger #{a.id} ({d_a.isoformat()}) and Ledger #{b.id} ({d_b.isoformat()}) "
                        f"share the same amount and compatible details."
                    ),
                    "reasons": reasons,
                    "source": "ledger",
                    "subtype": "ledger_ledger",
                    "record_kind": "ledger",
                    "transaction_id": newer.id,
                    "related_transaction_id": older.id,
                    "date": d_max,
                    "amount_pence": amt_pence,
                    "formatted_amount": format_pence(amt_pence, spec_a.symbol),
                    "merchant": m_a or m_b or None,
                    "account_id": a.account_id or b.account_id,
                    "account_name": acc_name_a if a.account_id else acc_name_b,
                    "category_id": a.category_id or b.category_id,
                    "category_name": None,
                    "can_dismiss": True,
                    "is_dismissed": pair_id in dismissed,
                    "ledger_url": _build_ledger_route({
                        "date_preset": "custom",
                        "start_date": d_min,
                        "end_date": d_max,
                        "q": (m_a if m_a == m_b and m_a else None),
                    }),
                    "queue_url": None,
                    "suggested_action": "delete_duplicate_ledger",
                    "suggested_category_id": None,
                    "suggested_category_name": None,
                    "action_explanation": (
                        f"You can inspect both transactions and optionally move Ledger #{newer.id} "
                        "to Recently Deleted (recoverable via Undo)."
                    ),
                    "comparison": {
                        "record_a": rec_a_obj,
                        "record_b": rec_b_obj,
                    },
                })

    return findings


def _matches_filters(
    finding: Dict[str, Any],
    finding_types: Optional[Set[str]],
    severities: Optional[Set[str]],
    q: Optional[str],
    account_id_filter: Optional[str],
    category_id_filter: Optional[str],
    start_date: Optional[str],
    end_date: Optional[str],
) -> bool:
    if finding_types and finding["finding_type"] not in finding_types:
        return False
    if severities and finding["severity"] not in severities:
        return False

    f_date = finding.get("date")
    if start_date and (not f_date or f_date < start_date):
        return False
    if end_date and (not f_date or f_date > end_date):
        return False

    if account_id_filter is not None:
        clean_acc = str(account_id_filter).strip().lower()
        comp = finding.get("comparison") or {}
        rec_a = comp.get("record_a") or comp.get("source_record") or {}
        rec_b = comp.get("record_b") or comp.get("destination_record") or {}
        related_accs = {finding.get("account_id"), finding.get("destination_account_id"), rec_a.get("account_id"), rec_b.get("account_id")}
        if clean_acc in ("unassigned", "0"):
            if finding.get("finding_type") != "unassigned_account" and None not in related_accs:
                return False
        elif clean_acc.isdigit():
            if int(clean_acc) not in related_accs:
                return False

    if category_id_filter is not None:
        clean_cat = str(category_id_filter).strip().lower()
        if clean_cat in ("uncategorized", "uncategorised", "0"):
            if finding.get("finding_type") != "uncategorised" and finding.get("category_id") is not None:
                return False
        elif clean_cat.isdigit():
            if finding.get("category_id") != int(clean_cat):
                return False

    if q:
        term = q.strip().lower()
        if term:
            haystack = " ".join([
                str(finding.get("title") or ""),
                str(finding.get("summary") or ""),
                str(finding.get("merchant") or ""),
                str(finding.get("account_name") or ""),
                str(finding.get("category_name") or ""),
                " ".join(finding.get("reasons") or []),
            ]).lower()
            if term not in haystack:
                return False

    return True


def get_data_quality_report(
    db: Session,
    profile_id: str = "default",
    finding_type: Optional[str] = None,
    severity: Optional[str] = None,
    q: Optional[str] = None,
    account_id: Optional[Union[int, str]] = None,
    category_id: Optional[Union[int, str]] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    include_dismissed: bool = False,
) -> Dict[str, Any]:
    """
    Runs a strictly non-mutating, profile-isolated scan across ledger records, pending Queue items,
    accounts, categories, anchors, and holdings.
    """
    app_tz = get_app_timezone(db)
    app_zi = ZoneInfo(app_tz)
    base_curr = get_base_currency_readonly(db)
    base_spec = get_currency_spec(base_curr)

    conf_category = get_system_setting(db, "import_confidence_category", "balanced")
    conf_account = get_system_setting(db, "import_confidence_account", "balanced")
    dismissed = get_dismissed_suggestion_ids(db)

    accounts = db.query(Account).all()
    acc_map = {a.id: a for a in accounts}

    categories = db.query(Category).all()
    cat_map = {c.id: c for c in categories}
    active_expense_cat_map = {
        c.id: c for c in categories
        if c.is_active and (getattr(c, "category_type", None) or CategoryType.EXPENSE) == CategoryType.EXPENSE
    }
    active_income_cat_map = {
        c.id: c for c in categories
        if c.is_active and (getattr(c, "category_type", None) or CategoryType.EXPENSE) == CategoryType.INCOME
    }
    has_active_income_categories = len(active_income_cat_map) > 0

    # Single scan of all non-deleted transactions in active workspace
    txs = (
        db.query(Transaction)
        .filter(Transaction.deleted_at.is_(None))
        .order_by(Transaction.transaction_date.desc(), Transaction.id.desc())
        .all()
    )

    pending_staging = (
        db.query(StagingItem)
        .filter(StagingItem.status == StagingStatus.PENDING)
        .order_by(StagingItem.extracted_date.desc(), StagingItem.id.desc())
        .all()
    )

    expense_exact_hist_map, expense_hist_entries = _build_category_history_index(
        txs, active_expense_cat_map, target_tx_type=TransactionType.EXPENSE
    )
    income_exact_hist_map, income_hist_entries = _build_category_history_index(
        txs, active_income_cat_map, target_tx_type=TransactionType.INCOME
    )

    all_findings: List[Dict[str, Any]] = []

    # ------------------------------------------------------------------
    # 1. Reuse existing Queue suggestions (duplicates & all transfers)
    # ------------------------------------------------------------------
    queue_sugs = get_review_queue_suggestions(db, include_dismissed=True)
    for dup in queue_sugs.get("duplicate_suggestions", []):
        sug_id = dup["id"]
        is_dism = bool(dup.get("is_dismissed"))
        if not include_dismissed and is_dism:
            continue
        rec_a = dup["record_a"]
        rec_b = dup["record_b"]
        subtype = dup.get("subtype", "staging_staging")
        d_min = min(rec_a.get("date") or "", rec_b.get("date") or "")
        d_max = max(rec_a.get("date") or "", rec_b.get("date") or "")

        all_findings.append({
            "id": sug_id,
            "finding_type": "potential_duplicate",
            "severity": "review",
            "confidence": "medium",
            "title": f"Potential duplicate queued import ({rec_a.get('formatted_amount')})",
            "summary": (
                f"Queued item #{rec_a['id']} ('{rec_a.get('merchant') or 'No merchant'}') "
                f"resembles {'Ledger #' + str(rec_b['id']) if rec_b['kind'] == 'ledger' else 'Staging #' + str(rec_b['id'])}."
            ),
            "reasons": dup.get("reasons", []),
            "source": "queue",
            "subtype": subtype,
            "record_kind": "staging",
            "staging_id": rec_a["id"],
            "transaction_id": rec_b["id"] if rec_b["kind"] == "ledger" else None,
            "date": d_max or rec_a.get("date"),
            "amount_pence": rec_a.get("amount_pence"),
            "formatted_amount": rec_a.get("formatted_amount"),
            "merchant": rec_a.get("merchant"),
            "account_id": rec_a.get("account_id") or rec_b.get("account_id"),
            "account_name": rec_a.get("account_name") or rec_b.get("account_name"),
            "category_id": None,
            "category_name": None,
            "can_dismiss": True,
            "is_dismissed": is_dism,
            "queue_url": _build_queue_route({"tab": "duplicates", "highlight_id": sug_id}),
            "ledger_url": (
                _build_ledger_route({"date_preset": "custom", "start_date": d_min, "end_date": d_max})
                if rec_b["kind"] == "ledger" and d_min and d_max
                else None
            ),
            "suggested_action": "exclude_duplicate_staging",
            "suggested_category_id": None,
            "suggested_category_name": None,
            "action_explanation": (
                f"Confirming will discard candidate Staging #{rec_a['id']} from the queue while keeping "
                "any source files needed by other pending entries."
            ),
            "comparison": {
                "record_a": rec_a,
                "record_b": rec_b,
            },
        })

    for trf in queue_sugs.get("transfer_suggestions", []):
        sug_id = trf["id"]
        is_dism = bool(trf.get("is_dismissed"))
        if not include_dismissed and is_dism:
            continue
        src = trf["source_record"]
        dst = trf["destination_record"]
        subtype = trf.get("subtype", "ledger_ledger")
        d_min = min(src.get("date") or "", dst.get("date") or "")
        d_max = max(src.get("date") or "", dst.get("date") or "")
        has_staging = src["kind"] == "staging" or dst["kind"] == "staging"

        all_findings.append({
            "id": sug_id,
            "finding_type": "possible_transfer",
            "severity": "review",
            "confidence": "medium",
            "title": f"Possible unpaired transfer ({src.get('formatted_amount')})",
            "summary": (
                f"Outgoing {src.get('account_name')} matches incoming {dst.get('account_name')} "
                f"within the transfer window."
            ),
            "reasons": trf.get("reasons", []),
            "source": "queue" if has_staging else "ledger",
            "subtype": subtype,
            "record_kind": "staging" if has_staging else "ledger",
            "staging_id": src["id"] if src["kind"] == "staging" else (dst["id"] if dst["kind"] == "staging" else None),
            "transaction_id": src["id"] if src["kind"] == "ledger" else (dst["id"] if dst["kind"] == "ledger" else None),
            "account_id": src.get("account_id"),
            "destination_account_id": dst.get("account_id"),
            "account_name": f"{src.get('account_name')} -> {dst.get('account_name')}",
            "date": d_max or src.get("date"),
            "amount_pence": src.get("amount_pence"),
            "formatted_amount": src.get("formatted_amount"),
            "merchant": src.get("merchant"),
            "category_id": None,
            "category_name": None,
            "can_dismiss": True,
            "is_dismissed": is_dism,
            "queue_url": _build_queue_route({"tab": "transfers", "highlight_id": sug_id}),
            "ledger_url": (
                _build_ledger_route({"date_preset": "custom", "start_date": d_min, "end_date": d_max})
                if (src["kind"] == "ledger" or dst["kind"] == "ledger") and d_min and d_max
                else None
            ),
            "suggested_action": "pair_transfer",
            "suggested_category_id": None,
            "suggested_category_name": None,
            "action_explanation": trf.get("action_explanation"),
            "comparison": {
                "source_record": src,
                "destination_record": dst,
            },
        })

    # ------------------------------------------------------------------
    # 2. Ledger-vs-Ledger duplicates (amount-bucketed)
    # ------------------------------------------------------------------
    all_findings.extend(
        _scan_ledger_duplicates(
            txs=txs,
            acc_map=acc_map,
            base_curr=base_curr,
            base_symbol=base_spec.symbol,
            app_zi=app_zi,
            dismissed=dismissed,
            confidence_level=conf_account,
            include_dismissed=include_dismissed,
        )
    )

    # ------------------------------------------------------------------
    # 3. Transaction-level quality, archived links, and integrity scan
    # ------------------------------------------------------------------
    for tx in txs:
        acc = acc_map.get(tx.account_id) if tx.account_id is not None else None
        dest_acc = acc_map.get(tx.destination_account_id) if tx.destination_account_id is not None else None
        cat = cat_map.get(tx.category_id) if tx.category_id is not None else None
        curr_code = (acc.currency if acc else base_curr).upper()
        curr_spec = get_currency_spec(curr_code)
        tx_date_str = _local_date_str(tx.transaction_date, app_zi)
        fmt_amount = format_pence(tx.amount_pence or 0, curr_spec.symbol) if tx.amount_pence is not None else "N/A"
        clean_merchant = (tx.merchant or "").strip() or None

        expected_cat_type = expected_category_type_for_transaction(tx.transaction_type)
        actual_cat_type = (getattr(cat, "category_type", None) or CategoryType.EXPENSE) if cat is not None else None

        # A. Integrity Issues (non-dismissible)
        integrity_reasons: List[str] = []
        if tx.account_id is not None and acc is None:
            integrity_reasons.append(f"References missing account ID #{tx.account_id}")
        if tx.destination_account_id is not None and dest_acc is None:
            integrity_reasons.append(f"References missing destination account ID #{tx.destination_account_id}")
        if tx.category_id is not None and cat is None:
            integrity_reasons.append(f"References missing category ID #{tx.category_id}")
        elif cat is not None:
            if expected_cat_type is None:
                integrity_reasons.append(
                    f"{tx.transaction_type.value.capitalize()} record should not link to category '{cat.name}'"
                )
            elif actual_cat_type != expected_cat_type:
                integrity_reasons.append(
                    f"{tx.transaction_type.value.capitalize()} transaction references {actual_cat_type.value} category '{cat.name}'"
                )
        if tx.amount_pence is None or tx.amount_pence <= 0:
            integrity_reasons.append(f"Invalid transaction amount ({tx.amount_pence} pence)")
        if tx.transaction_date is None:
            integrity_reasons.append("Missing transaction date")
        if tx.transaction_type == TransactionType.TRANSFER:
            if tx.account_id is None or tx.destination_account_id is None:
                integrity_reasons.append("Transfer is missing source or destination account")
            elif tx.account_id == tx.destination_account_id:
                integrity_reasons.append("Transfer uses the identical account for source and destination")
            elif acc and dest_acc and (acc.currency != base_curr or dest_acc.currency != base_curr):
                integrity_reasons.append(f"Transfer currency mismatch ({acc.currency} -> {dest_acc.currency} vs base {base_curr})")
        elif tx.transaction_type == TransactionType.ADJUSTMENT and tx.account_id is None:
            integrity_reasons.append("Reconciliation adjustment has no linked account")

        if tx.original_currency:
            clean_orig = tx.original_currency.strip().upper()
            if clean_orig == curr_code:
                integrity_reasons.append(f"Redundant foreign currency '{clean_orig}' matches account currency")
            elif tx.original_amount is None or float(tx.original_amount) <= 0:
                integrity_reasons.append(f"Foreign currency '{clean_orig}' has invalid original amount")
            elif tx.exchange_rate is not None and float(tx.exchange_rate) <= 0:
                integrity_reasons.append(f"Foreign currency '{clean_orig}' has non-positive exchange rate")

        if integrity_reasons:
            fid = f"dq_integrity_tx_{tx.id}"
            all_findings.append({
                "id": fid,
                "finding_type": "integrity_issue",
                "severity": "integrity",
                "confidence": "high",
                "title": f"Data integrity check needed for Ledger #{tx.id}",
                "summary": "; ".join(integrity_reasons),
                "reasons": integrity_reasons,
                "source": "ledger",
                "subtype": "ledger_integrity",
                "record_kind": "ledger",
                "transaction_id": tx.id,
                "date": tx_date_str,
                "amount_pence": tx.amount_pence,
                "formatted_amount": fmt_amount,
                "merchant": clean_merchant,
                "account_id": tx.account_id,
                "destination_account_id": tx.destination_account_id,
                "account_name": acc.name if acc else ("Unassigned" if tx.account_id is None else f"Missing (#{tx.account_id})"),
                "category_id": tx.category_id,
                "category_name": cat.name if cat else None,
                "category_type": actual_cat_type.value if actual_cat_type else None,
                "expected_category_type": expected_cat_type.value if expected_cat_type else None,
                "can_dismiss": False,
                "is_dismissed": False,
                "ledger_url": _build_ledger_route({
                    "date_preset": "custom" if tx_date_str else "all",
                    "start_date": tx_date_str,
                    "end_date": tx_date_str,
                    "q": clean_merchant,
                }),
                "queue_url": None,
                "suggested_action": "open_ledger",
                "suggested_category_id": None,
                "suggested_category_name": None,
                "action_explanation": "Inspect this record in the Ledger to repair invalid or missing relational fields.",
            })

        # B. Uncategorised Expense / Income (only flag Income when active Income categories exist)
        should_flag_uncat = (
            tx.category_id is None
            and (
                tx.transaction_type == TransactionType.EXPENSE
                or (tx.transaction_type == TransactionType.INCOME and has_active_income_categories)
            )
        )
        if should_flag_uncat:
            fid = f"dq_uncat_tx_{tx.id}"
            is_dism = fid in dismissed
            if include_dismissed or not is_dism:
                is_income_tx = tx.transaction_type == TransactionType.INCOME
                hist_hint = _suggest_category_from_history(
                    merchant=clean_merchant,
                    exact_map=income_exact_hist_map if is_income_tx else expense_exact_hist_map,
                    hist_entries=income_hist_entries if is_income_tx else expense_hist_entries,
                    active_categories=active_income_cat_map if is_income_tx else active_expense_cat_map,
                    confidence_level=conf_category,
                )
                reasons = [
                    f"{tx.transaction_type.value.capitalize()} transaction has no {expected_cat_type.value if expected_cat_type else ''} category assigned".replace("  ", " "),
                    "Excluded from income category breakdown" if is_income_tx else "Excluded from category budgets and spending breakdown",
                ]
                if hist_hint:
                    reasons.append(hist_hint["reason"])

                all_findings.append({
                    "id": fid,
                    "finding_type": "uncategorised",
                    "severity": "suggestion",
                    "confidence": hist_hint["confidence"] if hist_hint else "medium",
                    "title": f"Uncategorised {tx.transaction_type.value}: {clean_merchant or fmt_amount}",
                    "summary": (
                        f"Ledger #{tx.id} ({tx_date_str or 'no date'}, {fmt_amount}) needs an {expected_cat_type.value} category."
                    ),
                    "reasons": reasons,
                    "source": "ledger",
                    "subtype": "missing_category",
                    "record_kind": "ledger",
                    "transaction_id": tx.id,
                    "transaction_type": tx.transaction_type.value,
                    "date": tx_date_str,
                    "amount_pence": tx.amount_pence,
                    "formatted_amount": fmt_amount,
                    "merchant": clean_merchant,
                    "account_id": tx.account_id,
                    "account_name": acc.name if acc else "Unassigned",
                    "category_id": None,
                    "category_name": "Uncategorised",
                    "category_type": None,
                    "expected_category_type": expected_cat_type.value if expected_cat_type else None,
                    "can_dismiss": True,
                    "is_dismissed": is_dism,
                    "ledger_url": _build_ledger_route({
                        "date_preset": "all",
                        "category_id": "uncategorized",
                        "q": clean_merchant,
                    }),
                    "queue_url": None,
                    "suggested_action": "assign_category",
                    "suggested_category_id": hist_hint["category_id"] if hist_hint else None,
                    "suggested_category_name": hist_hint["category_name"] if hist_hint else None,
                    "action_explanation": (
                        f"Assign an active {expected_cat_type.value} category explicitly."
                        if is_income_tx
                        else "Assign an active expense category explicitly; Expense Nature defaults if currently unclassified."
                    ),
                })

        # C. Unassigned Account (Expense / Income where an account is expected)
        if tx.account_id is None and tx.transaction_type in (TransactionType.EXPENSE, TransactionType.INCOME):
            fid = f"dq_unassigned_tx_{tx.id}"
            is_dism = fid in dismissed
            if include_dismissed or not is_dism:
                all_findings.append({
                    "id": fid,
                    "finding_type": "unassigned_account",
                    "severity": "suggestion",
                    "confidence": "medium",
                    "title": f"Unassigned account: {clean_merchant or fmt_amount}",
                    "summary": (
                        f"Ledger #{tx.id} ({tx_date_str or 'no date'}, {fmt_amount}) has no bank or card account."
                    ),
                    "reasons": [
                        "No source or destination account linked to this entry",
                        "Unassigned entries are omitted from individual account balance reconciliations",
                    ],
                    "source": "ledger",
                    "subtype": "missing_account",
                    "record_kind": "ledger",
                    "transaction_id": tx.id,
                    "transaction_type": tx.transaction_type.value,
                    "date": tx_date_str,
                    "amount_pence": tx.amount_pence,
                    "formatted_amount": fmt_amount,
                    "merchant": clean_merchant,
                    "account_id": None,
                    "account_name": "Unassigned",
                    "category_id": tx.category_id,
                    "category_name": cat.name if cat else "Uncategorised",
                    "can_dismiss": True,
                    "is_dismissed": is_dism,
                    "ledger_url": _build_ledger_route({
                        "date_preset": "all",
                        "account_ids": "unassigned",
                        "q": clean_merchant,
                    }),
                    "queue_url": None,
                    "suggested_action": "assign_account",
                    "suggested_category_id": None,
                    "suggested_category_name": None,
                    "action_explanation": "Assign the account used for this transaction so balance tracking reflects it accurately.",
                })

        # D. Archived Account or Category references on active transactions
        archived_reasons: List[str] = []
        if acc is not None and not acc.is_active:
            archived_reasons.append(f"Uses archived account '{acc.name}'")
        if dest_acc is not None and not dest_acc.is_active:
            archived_reasons.append(f"Transfer destination uses archived account '{dest_acc.name}'")
        if cat is not None and not cat.is_active:
            archived_reasons.append(f"Uses archived category '{cat.name}'")

        if archived_reasons:
            fid = f"dq_archived_tx_{tx.id}"
            is_dism = fid in dismissed
            if include_dismissed or not is_dism:
                can_fix_cat = bool(cat is not None and not cat.is_active and tx.transaction_type in (TransactionType.EXPENSE, TransactionType.INCOME))
                can_fix_acc = bool(acc is not None and not acc.is_active)
                all_findings.append({
                    "id": fid,
                    "finding_type": "archived_reference",
                    "severity": "suggestion",
                    "confidence": "high",
                    "title": f"Linked to archived account/category: {clean_merchant or fmt_amount}",
                    "summary": "; ".join(archived_reasons),
                    "reasons": archived_reasons + [
                        "Archived items are hidden from active dropdowns and default active-account reports",
                    ],
                    "source": "ledger",
                    "subtype": "archived_cat" if can_fix_cat and not can_fix_acc else "archived_acc" if can_fix_acc and not can_fix_cat else "archived_both",
                    "record_kind": "ledger",
                    "transaction_id": tx.id,
                    "transaction_type": tx.transaction_type.value,
                    "date": tx_date_str,
                    "amount_pence": tx.amount_pence,
                    "formatted_amount": fmt_amount,
                    "merchant": clean_merchant,
                    "account_id": tx.account_id,
                    "account_name": acc.name if acc else "Unassigned",
                    "category_id": tx.category_id,
                    "category_name": cat.name if cat else None,
                    "category_type": actual_cat_type.value if actual_cat_type else None,
                    "expected_category_type": expected_cat_type.value if expected_cat_type else None,
                    "can_dismiss": True,
                    "is_dismissed": is_dism,
                    "ledger_url": _build_ledger_route({
                        "date_preset": "all",
                        "account_ids": tx.account_id if (acc and not acc.is_active) else None,
                        "category_ids": tx.category_id if (cat and not cat.is_active and not (acc and not acc.is_active)) else None,
                    }),
                    "queue_url": None,
                    "suggested_action": "reassign_category" if can_fix_cat and not can_fix_acc else "assign_account" if can_fix_acc and not can_fix_cat else "open_ledger",
                    "suggested_category_id": None,
                    "suggested_category_name": None,
                    "action_explanation": "Reassign to an active category/account if this belongs in ongoing active reporting, or hide if historical.",
                })

        # E. Imported Ledger records lacking descriptive narrative
        entry_m = (tx.entry_method or "manual").strip().lower()
        if (
            entry_m != "manual"
            and tx.transaction_type in (TransactionType.EXPENSE, TransactionType.INCOME)
            and not clean_merchant
            and not (tx.notes or "").strip()
        ):
            fid = f"dq_incomplete_tx_{tx.id}"
            is_dism = fid in dismissed
            if include_dismissed or not is_dism:
                all_findings.append({
                    "id": fid,
                    "finding_type": "uncertain_import",
                    "severity": "suggestion",
                    "confidence": "medium",
                    "title": f"Imported entry lacks merchant narrative ({fmt_amount})",
                    "summary": f"Imported Ledger #{tx.id} ({tx_date_str or 'no date'}, source '{entry_m}') has blank merchant and notes.",
                    "reasons": [
                        f"Imported via '{entry_m}' without a merchant name or description",
                        "Adding a clear merchant improves future search and categorization accuracy",
                    ],
                    "source": "ledger",
                    "subtype": "missing_narrative",
                    "record_kind": "ledger",
                    "transaction_id": tx.id,
                    "transaction_type": tx.transaction_type.value,
                    "date": tx_date_str,
                    "amount_pence": tx.amount_pence,
                    "formatted_amount": fmt_amount,
                    "merchant": None,
                    "account_id": tx.account_id,
                    "account_name": acc.name if acc else "Unassigned",
                    "category_id": tx.category_id,
                    "category_name": cat.name if cat else None,
                    "category_type": actual_cat_type.value if actual_cat_type else None,
                    "expected_category_type": expected_cat_type.value if expected_cat_type else None,
                    "can_dismiss": True,
                    "is_dismissed": is_dism,
                    "ledger_url": _build_ledger_route({
                        "date_preset": "custom" if tx_date_str else "all",
                        "start_date": tx_date_str,
                        "end_date": tx_date_str,
                        "account_ids": tx.account_id,
                    }),
                    "queue_url": None,
                    "suggested_action": "open_ledger",
                    "suggested_category_id": None,
                    "suggested_category_name": None,
                    "action_explanation": "Open in Ledger to edit the merchant or attach a receipt/description.",
                })

    # ------------------------------------------------------------------
    # 4. Pending Staging items with retained uncertainty / incomplete fields & integrity checks
    # ------------------------------------------------------------------
    for stg in pending_staging:
        payload = {}
        try:
            payload = json.loads(stg.raw_payload_json or "{}")
        except Exception:
            payload = {}

        stg_acc_id = stg.suggested_account_id
        stg_dest_id = payload.get("destination_account_id")
        stg_acc = acc_map.get(stg_acc_id) if stg_acc_id is not None else None
        stg_curr = (stg_acc.currency if stg_acc else payload.get("currency", base_curr)).upper()
        stg_spec = get_currency_spec(stg_curr)
        stg_date_str = _local_date_str(stg.extracted_date, app_zi)
        stg_amt_str = (
            format_pence(stg.extracted_amount_pence, stg_spec.symbol)
            if stg.extracted_amount_pence and stg.extracted_amount_pence > 0
            else "Needs amount"
        )

        # Staging broken references -> integrity_issue
        stg_integrity = []
        if stg_acc_id is not None and stg_acc is None:
            stg_integrity.append(f"Queued Staging #{stg.id} references deleted account ID #{stg_acc_id}")
        if stg_dest_id is not None and int(stg_dest_id) not in acc_map:
            stg_integrity.append(f"Queued Staging #{stg.id} references deleted destination account ID #{stg_dest_id}")
        if stg_integrity:
            all_findings.append({
                "id": f"dq_integrity_staging_{stg.id}",
                "finding_type": "integrity_issue",
                "severity": "integrity",
                "confidence": "high",
                "title": f"Queued Staging #{stg.id} has an invalid account link",
                "summary": "; ".join(stg_integrity),
                "reasons": stg_integrity,
                "source": "queue",
                "subtype": "staging_integrity",
                "record_kind": "staging",
                "staging_id": stg.id,
                "date": stg_date_str,
                "amount_pence": stg.extracted_amount_pence,
                "formatted_amount": stg_amt_str,
                "merchant": stg.extracted_merchant,
                "account_id": None,
                "account_name": "Invalid Reference",
                "category_id": None,
                "category_name": stg.suggested_category_name,
                "can_dismiss": False,
                "is_dismissed": False,
                "queue_url": _build_queue_route({"status": "pending", "item_id": stg.id}),
                "ledger_url": None,
                "suggested_action": "open_queue",
                "suggested_category_id": None,
                "suggested_category_name": None,
                "action_explanation": "Open in Review Queue and assign a valid account or discard this queued candidate.",
            })

        uncertain_reasons: List[str] = []
        has_review_blocker = False

        if payload.get("direction_uncertain") or payload.get("is_ambiguous_direction"):
            has_review_blocker = True
            uncertain_reasons.append("Transaction direction (income vs expense) could not be confirmed automatically")
        orig_curr = payload.get("original_currency")
        if payload.get("currency_conflict") or payload.get("requires_base_amount") or (
            orig_curr and orig_curr.upper() != stg_curr
        ):
            has_review_blocker = True
            uncertain_reasons.append(
                payload.get("currency_conflict_message")
                or f"Foreign currency ({orig_curr or 'mismatch'}) requires base currency ({stg_curr}) verification"
            )
        if not stg.extracted_date:
            has_review_blocker = True
            uncertain_reasons.append("Extracted transaction date is missing")
        if stg.extracted_amount_pence is None or stg.extracted_amount_pence <= 0:
            has_review_blocker = True
            uncertain_reasons.append("Extracted amount is missing or non-positive")
        if stg.suggested_account_id is None:
            uncertain_reasons.append("Imported candidate has no matched account yet")
        stg_tx_type_str = str(payload.get("transaction_type", "expense")).strip().lower()
        needs_stg_cat = stg_tx_type_str == "expense" or (stg_tx_type_str == "income" and has_active_income_categories)
        if not stg.suggested_category_name and needs_stg_cat:
            uncertain_reasons.append("Imported candidate has no suggested category yet")

        if uncertain_reasons:
            fid = f"dq_uncertain_staging_{stg.id}"
            is_dism = fid in dismissed
            if include_dismissed or not is_dism:
                all_findings.append({
                    "id": fid,
                    "finding_type": "uncertain_import",
                    "severity": "review" if has_review_blocker else "suggestion",
                    "confidence": "medium",
                    "title": f"Queued import needs review: {stg.extracted_merchant or f'Staging #{stg.id}'}",
                    "summary": uncertain_reasons[0] if len(uncertain_reasons) == 1 else f"{len(uncertain_reasons)} uncertain or incomplete fields retained in Queue.",
                    "reasons": uncertain_reasons,
                    "source": "queue",
                    "subtype": "staging_uncertain",
                    "record_kind": "staging",
                    "staging_id": stg.id,
                    "date": stg_date_str,
                    "amount_pence": stg.extracted_amount_pence,
                    "formatted_amount": stg_amt_str,
                    "merchant": stg.extracted_merchant,
                    "account_id": stg.suggested_account_id,
                    "account_name": stg_acc.name if stg_acc else "Unassigned",
                    "category_id": None,
                    "category_name": stg.suggested_category_name or "Uncategorised",
                    "can_dismiss": True,
                    "is_dismissed": is_dism,
                    "queue_url": _build_queue_route({"status": "pending", "item_id": stg.id}),
                    "ledger_url": None,
                    "suggested_action": "open_queue",
                    "suggested_category_id": None,
                    "suggested_category_name": None,
                    "action_explanation": "Inspect, edit missing fields, or discard this candidate safely in the Queue before approval.",
                })

    # ------------------------------------------------------------------
    # 5. Anchor & Holding parent integrity checks
    # ------------------------------------------------------------------
    anchors = db.query(AccountBalanceAnchor).all()
    for anc in anchors:
        if anc.account_id not in acc_map:
            all_findings.append({
                "id": f"dq_integrity_anchor_{anc.id}",
                "finding_type": "integrity_issue",
                "severity": "integrity",
                "confidence": "high",
                "title": f"Orphaned balance anchor #{anc.id}",
                "summary": f"Balance anchor #{anc.id} references missing account ID #{anc.account_id}.",
                "reasons": [f"Account ID #{anc.account_id} does not exist"],
                "source": "ledger",
                "subtype": "anchor_integrity",
                "record_kind": "anchor",
                "date": _local_date_str(anc.anchor_date, app_zi),
                "amount_pence": anc.balance_pence,
                "formatted_amount": format_pence(anc.balance_pence or 0, base_spec.symbol),
                "merchant": anc.notes or "Balance anchor",
                "account_id": None,
                "account_name": f"Missing (#{anc.account_id})",
                "category_id": None,
                "category_name": None,
                "can_dismiss": False,
                "is_dismissed": False,
                "ledger_url": None,
                "queue_url": None,
                "suggested_action": "inspect_only",
                "suggested_category_id": None,
                "suggested_category_name": None,
                "action_explanation": "Structural anchor reference requires database inspection.",
            })

    holdings = db.query(Holding).all()
    holding_ids = {h.id for h in holdings}
    for h in holdings:
        if h.account_id not in acc_map:
            all_findings.append({
                "id": f"dq_integrity_holding_{h.id}",
                "finding_type": "integrity_issue",
                "severity": "integrity",
                "confidence": "high",
                "title": f"Orphaned holding '{h.name}' (#{h.id})",
                "summary": f"Holding #{h.id} references missing account ID #{h.account_id}.",
                "reasons": [f"Account ID #{h.account_id} does not exist"],
                "source": "portfolio",
                "subtype": "holding_integrity",
                "record_kind": "holding",
                "date": None,
                "amount_pence": None,
                "formatted_amount": None,
                "merchant": h.name,
                "account_id": None,
                "account_name": f"Missing (#{h.account_id})",
                "category_id": None,
                "category_name": None,
                "can_dismiss": False,
                "is_dismissed": False,
                "ledger_url": None,
                "queue_url": None,
                "suggested_action": "inspect_only",
                "suggested_category_id": None,
                "suggested_category_name": None,
                "action_explanation": "Structural holding reference requires inspection.",
            })

    valuations = db.query(HoldingValuation).all()
    for val in valuations:
        if val.holding_id not in holding_ids:
            all_findings.append({
                "id": f"dq_integrity_valuation_{val.id}",
                "finding_type": "integrity_issue",
                "severity": "integrity",
                "confidence": "high",
                "title": f"Orphaned holding valuation #{val.id}",
                "summary": f"Valuation #{val.id} references missing holding ID #{val.holding_id}.",
                "reasons": [f"Holding ID #{val.holding_id} does not exist"],
                "source": "portfolio",
                "subtype": "valuation_integrity",
                "record_kind": "holding_valuation",
                "date": _local_date_str(val.effective_date, app_zi),
                "amount_pence": val.valuation_pence,
                "formatted_amount": format_pence(val.valuation_pence or 0, base_spec.symbol),
                "merchant": val.notes or "Holding valuation",
                "account_id": None,
                "account_name": None,
                "category_id": None,
                "category_name": None,
                "can_dismiss": False,
                "is_dismissed": False,
                "ledger_url": None,
                "queue_url": None,
                "suggested_action": "inspect_only",
                "suggested_category_id": None,
                "suggested_category_name": None,
                "action_explanation": "Structural valuation reference requires inspection.",
            })

    # Compute workspace active counts BEFORE applying UI filter criteria
    active_findings = [f for f in all_findings if not f.get("is_dismissed")]
    by_type = {ft: 0 for ft in ALL_FINDING_TYPES}
    by_severity = {sev: 0 for sev in ALL_SEVERITIES}
    for f in active_findings:
        by_type[f["finding_type"]] = by_type.get(f["finding_type"], 0) + 1
        by_severity[f["severity"]] = by_severity.get(f["severity"], 0) + 1

    # Apply requested filter parameters
    type_set = {t.strip().lower() for t in finding_type.split(",") if t.strip()} if finding_type else None
    sev_set = {s.strip().lower() for s in severity.split(",") if s.strip()} if severity else None
    acc_filter_str = str(account_id) if account_id is not None and str(account_id).strip() != "" else None
    cat_filter_str = str(category_id) if category_id is not None and str(category_id).strip() != "" else None
    start_str = start_date.strip()[:10] if start_date and start_date.strip() else None
    end_str = end_date.strip()[:10] if end_date and end_date.strip() else None

    filtered = [
        f for f in all_findings
        if _matches_filters(
            finding=f,
            finding_types=type_set,
            severities=sev_set,
            q=q,
            account_id_filter=acc_filter_str,
            category_id_filter=cat_filter_str,
            start_date=start_str,
            end_date=end_str,
        )
    ]

    # Deterministic priority order: active before dismissed -> severity -> newest date -> ID
    def _sort_key(item: Dict[str, Any]):
        d_str = item.get("date") or "0000-00-00"
        inv_date = tuple(-ord(ch) for ch in d_str)
        return (
            1 if item.get("is_dismissed") else 0,
            _SEVERITY_ORDER.get(item.get("severity", "suggestion"), 9),
            inv_date,
            item.get("id", ""),
        )

    filtered.sort(key=_sort_key)

    return {
        "profile_id": profile_id,
        "app_timezone": app_tz,
        "base_currency": base_curr,
        "confidence_settings": {
            "category": conf_category,
            "account": conf_account,
        },
        "summary": {
            "total_active": len(active_findings),
            "dismissed_count": len(dismissed),
            "by_type": by_type,
            "by_severity": by_severity,
            "scanned_transactions_count": len(txs),
            "scanned_staging_count": len(pending_staging),
        },
        "filtered_count": len(filtered),
        "findings": filtered,
    }
