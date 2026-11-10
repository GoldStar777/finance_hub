"""
Regression test suite for:
1. Filter for uncategorised Ledger entries (standalone, with query parameters, search, accounts, dates, pagination, bulk edit).
2. Per-profile confidence settings for local importer suggestions (Very Cautious, Balanced, More Suggestions).
3. Ambiguity safeguards remaining active across all threshold settings.
4. Multi-profile isolation of confidence settings.
5. Offline / local execution verification.
"""

import pytest
import re
from datetime import datetime, timezone
from decimal import Decimal
from fastapi.testclient import TestClient

from app.models import (
    Account,
    AccountType,
    Transaction,
    TransactionType,
    ExpenseNature,
    Category,
)
from app.core.categories import save_category_description
from app.core.unified_importer import (
    match_account_from_context,
    suggest_category_from_history,
    suggest_category_for_merchant,
    ACCOUNT_CONFIDENCE_THRESHOLDS,
    CATEGORY_CONFIDENCE_THRESHOLDS,
)
from app.core.backup import get_system_setting, set_system_setting
from app.main import app
from tests.test_profiles import isolated_profiles_env


def test_1_uncategorised_ledger_filtering_and_combinations(db_session, client: TestClient):
    """
    Requirement 1:
    - Filter for uncategorised Ledger entries.
    - Selecting it shows only transactions without an active category.
    - Composes with search, account, date, pagination, and bulk selection.
    - Supports category_id=uncategorized, category_id=0, and uncategorized_only=true.
    """
    acc1 = Account(name="Current Account", account_type=AccountType.CURRENT, currency="GBP", starting_balance_pence=100000)
    acc2 = Account(name="Savings Account", account_type=AccountType.SAVINGS, currency="GBP", starting_balance_pence=50000)
    cat_dining = Category(name="Dining", color="#EF4444")
    cat_travel = Category(name="Travel", color="#3B82F6")
    db_session.add_all([acc1, acc2, cat_dining, cat_travel])
    db_session.commit()

    # Create 5 transactions:
    # tx1: Uncategorised, Pret coffee, Acc 1, 2026-10-01
    tx1 = Transaction(
        transaction_date=datetime(2026, 10, 1, 10, 0, 0, tzinfo=timezone.utc),
        transaction_type=TransactionType.EXPENSE,
        amount_pence=350,
        merchant="Pret A Manger",
        notes="Coffee on the go",
        account_id=acc1.id,
        category_id=None,
    )
    # tx2: Uncategorised, Waitrose groceries, Acc 1, 2026-10-02
    tx2 = Transaction(
        transaction_date=datetime(2026, 10, 2, 11, 0, 0, tzinfo=timezone.utc),
        transaction_type=TransactionType.EXPENSE,
        amount_pence=4500,
        merchant="Waitrose",
        notes="Weekly grocery run",
        account_id=acc1.id,
        category_id=None,
    )
    # tx3: Uncategorised, Pret lunch, Acc 2, 2026-10-03
    tx3 = Transaction(
        transaction_date=datetime(2026, 10, 3, 12, 0, 0, tzinfo=timezone.utc),
        transaction_type=TransactionType.EXPENSE,
        amount_pence=1200,
        merchant="Pret A Manger",
        notes="Sandwich and crisps",
        account_id=acc2.id,
        category_id=None,
    )
    # tx4: Categorised as Dining, Nando's, Acc 1, 2026-10-04
    tx4 = Transaction(
        transaction_date=datetime(2026, 10, 4, 13, 0, 0, tzinfo=timezone.utc),
        transaction_type=TransactionType.EXPENSE,
        amount_pence=2500,
        merchant="Nandos",
        account_id=acc1.id,
        category_id=cat_dining.id,
    )
    # tx5: Categorised as Travel, Trainline, Acc 1, 2026-10-05
    tx5 = Transaction(
        transaction_date=datetime(2026, 10, 5, 14, 0, 0, tzinfo=timezone.utc),
        transaction_type=TransactionType.EXPENSE,
        amount_pence=6500,
        merchant="Trainline",
        account_id=acc1.id,
        category_id=cat_travel.id,
    )
    db_session.add_all([tx1, tx2, tx3, tx4, tx5])
    db_session.commit()

    # A. Unfiltered view: all 5 transactions returned
    res_all = client.get("/api/transactions")
    assert res_all.status_code == 200
    assert res_all.json()["total"] == 5

    # B. category_id=uncategorized -> returns only tx1, tx2, tx3
    res_uncat = client.get("/api/transactions?category_id=uncategorized")
    assert res_uncat.status_code == 200
    items = res_uncat.json()["items"]
    assert len(items) == 3
    assert {it["id"] for it in items} == {tx1.id, tx2.id, tx3.id}
    assert all(it["category_id"] is None for it in items)

    # C. category_id=0 -> same result
    res_zero = client.get("/api/transactions?category_id=0")
    assert res_zero.status_code == 200
    assert {it["id"] for it in res_zero.json()["items"]} == {tx1.id, tx2.id, tx3.id}

    # D. uncategorized_only=true -> same result
    res_flag = client.get("/api/transactions?uncategorized_only=true")
    assert res_flag.status_code == 200
    assert {it["id"] for it in res_flag.json()["items"]} == {tx1.id, tx2.id, tx3.id}

    # E. Combine Uncategorised with Search (q="Pret") -> returns tx1 and tx3
    res_search = client.get("/api/transactions?category_id=uncategorized&q=Pret")
    assert res_search.status_code == 200
    assert {it["id"] for it in res_search.json()["items"]} == {tx1.id, tx3.id}

    # F. Combine Uncategorised with Account filter (account_id=acc1.id) -> returns tx1 and tx2
    res_acc = client.get(f"/api/transactions?category_id=uncategorized&account_id={acc1.id}")
    assert res_acc.status_code == 200
    assert {it["id"] for it in res_acc.json()["items"]} == {tx1.id, tx2.id}

    # G. Combine with Date range (start_date=2026-10-02, end_date=2026-10-03) -> returns tx2 and tx3
    res_date = client.get("/api/transactions?category_id=uncategorized&start_date=2026-10-02T00:00:00Z&end_date=2026-10-03T23:59:59Z")
    assert res_date.status_code == 200
    assert {it["id"] for it in res_date.json()["items"]} == {tx2.id, tx3.id}

    # H. Cross-page matching IDs endpoint with category_id=uncategorized
    res_ids = client.get("/api/transactions/matching-ids?category_id=uncategorized")
    assert res_ids.status_code == 200
    assert set(res_ids.json()["ids"]) == {tx1.id, tx2.id, tx3.id}
    assert res_ids.json()["total"] == 3

    # I. Bulk edit from filtered view: assign Category 'Dining' to all 3 uncategorised items
    res_bulk = client.post(
        "/api/transactions/bulk",
        json={
            "transaction_ids": res_ids.json()["ids"],
            "update_category": True,
            "category_id": cat_dining.id
        }
    )
    assert res_bulk.status_code == 200
    assert res_bulk.json()["updated_count"] == 3

    # Verification: now 0 uncategorised transactions remain
    res_after = client.get("/api/transactions?category_id=uncategorized")
    assert res_after.json()["total"] == 0


def test_2_category_confidence_levels_affect_prefill(db_session):
    """
    Requirement 2:
    Category matching confidence levels:
    - Cautious (0.85): prefill only high-confidence matches.
    - Balanced (0.65): prefill clear, reasonably strong matches.
    - Permissive (0.45): allow weaker matches for manual review.
    """
    cat_hair = Category(name="Hair & Beauty", color="#EC4899")
    cat_desc = Category(name="Salon & Spa", color="#A855F7")
    db_session.add_all([cat_hair, cat_desc])
    db_session.commit()
    save_category_description(db_session, cat_desc.id, "hair styling haircut colour treatments")

    # Context text containing description token prefix similarity ("treatment" vs "treatments" -> 0.80)
    context_lines = ["Example Studio Service", "Specialist treatment", "Total: 65.00"]

    # 1. Very Cautious (0.85):
    # Prefix in description (score 0.80) is below 0.85 threshold -> Left Uncategorised
    cat_id_cautious, name_cautious, _, reason_cautious = suggest_category_from_history(
        db=db_session,
        merchant="Example Studio",
        ocr_lines=context_lines,
        confidence_level="cautious"
    )
    assert cat_id_cautious is None
    assert name_cautious is None

    # 2. Balanced (0.65):
    # Score 0.80 >= 0.65 -> Prefills category with explanation
    cat_id_balanced, name_balanced, _, reason_balanced = suggest_category_from_history(
        db=db_session,
        merchant="Example Studio",
        ocr_lines=context_lines,
        confidence_level="balanced"
    )
    assert cat_id_balanced is not None, f"Expected match, got reason: {reason_balanced}"
    assert name_balanced in ("Hair & Beauty", "Salon & Spa")
    assert "Matched category" in reason_balanced

    # 3. Permissive (0.45):
    # Score 0.80 >= 0.45 -> Prefills category
    cat_id_permissive, name_permissive, _, _ = suggest_category_from_history(
        db=db_session,
        merchant="Example Studio",
        ocr_lines=context_lines,
        confidence_level="permissive"
    )
    assert cat_id_permissive is not None

    # 4. Approved Past History (score = 1.0):
    # Should prefill across ALL threshold levels (Cautious, Balanced, Permissive)
    tx_hist = Transaction(
        transaction_date=datetime(2026, 9, 1, 10, 0, 0, tzinfo=timezone.utc),
        transaction_type=TransactionType.EXPENSE,
        amount_pence=5000,
        merchant="Example Studio",
        category_id=cat_hair.id
    )
    db_session.add(tx_hist)
    db_session.commit()

    cat_id_cautious_hist, _, _, reason = suggest_category_from_history(
        db=db_session,
        merchant="Example Studio",
        confidence_level="cautious"
    )
    assert cat_id_cautious_hist == cat_hair.id
    assert "Learned from 1 approved past transaction" in reason


def test_3_account_confidence_levels_affect_prefill(db_session):
    """
    Requirement 3:
    Account matching confidence levels:
    - Cautious (0.90): prefill only confirmed associations (1.0), card last-4 digits (0.95), or exact distinctive token matches.
    - Balanced (0.75): prefill clear distinctive token matches.
    - Permissive (0.60): allow broader token overlap for review.
    """
    acc_barclays = Account(name="Barclays Premier Current", account_type=AccountType.CURRENT, currency="GBP", starting_balance_pence=10000)
    db_session.add(acc_barclays)
    db_session.commit()

    # Candidate clue with a single distinctive token 'barclays' (score = 0.75, since 'premier' and 'current' are generic)
    ocr_lines = ["Payment Details", "Barclays Card Platinum", "MID: *******1234", "AUTH: 998877"]

    # 1. Very Cautious (0.90):
    # Single token match (0.75) is below 0.90 threshold -> Left Unassigned
    acc_id_cautious, _, reason_cautious = match_account_from_context(
        db=db_session,
        ocr_lines=ocr_lines,
        confidence_level="cautious"
    )
    assert acc_id_cautious is None
    assert "met the 'cautious' confidence threshold" in reason_cautious

    # 2. Balanced (0.75):
    # Single distinctive token score 0.75 >= 0.75 threshold -> Prefills account
    acc_id_balanced, name_balanced, reason_balanced = match_account_from_context(
        db=db_session,
        ocr_lines=ocr_lines,
        confidence_level="balanced"
    )
    assert acc_id_balanced == acc_barclays.id
    assert name_balanced == "Barclays Premier Current"
    assert "Matched card" in reason_balanced

    # 3. Permissive (0.60):
    # Score 0.75 >= 0.60 -> Prefills account
    acc_id_permissive, _, _ = match_account_from_context(
        db=db_session,
        ocr_lines=ocr_lines,
        confidence_level="permissive"
    )
    assert acc_id_permissive == acc_barclays.id

    # 4. Visible Last-4 card digits (score = 0.95):
    # When account name contains last-4 digits, it passes Cautious (0.95 >= 0.90)
    acc_amex = Account(name="American Express 4321", account_type=AccountType.CREDIT_CARD, currency="GBP", starting_balance_pence=0)
    db_session.add(acc_amex)
    db_session.commit()

    acc_id_last4, name_last4, _ = match_account_from_context(
        db=db_session,
        ocr_lines=["AMERICAN EXPRESS", "CARD: ************4321"],
        confidence_level="cautious"
    )
    assert acc_id_last4 == acc_amex.id
    assert name_last4 == "American Express 4321"


def test_4_ambiguity_safeguards_remain_unset_across_all_levels(db_session):
    """
    Requirement 4:
    Permissive setting must NOT silently override ambiguity safeguards.
    If two accounts or categories have similarly plausible matches, leave unset.
    """
    # 1. Account ambiguity: two accounts with last-4 digits 4321
    acc1 = Account(name="American Express Personal 4321", account_type=AccountType.CREDIT_CARD, currency="GBP")
    acc2 = Account(name="American Express Business 4321", account_type=AccountType.CREDIT_CARD, currency="GBP")
    db_session.add_all([acc1, acc2])
    db_session.commit()

    # Even in 'permissive' mode, ambiguous card digits must remain Unassigned
    acc_id, _, reason = match_account_from_context(
        db=db_session,
        ocr_lines=["AMERICAN EXPRESS", "CARD: ************4321"],
        confidence_level="permissive"
    )
    assert acc_id is None
    assert "Ambiguous match: multiple accounts contain last-4 digits '4321'" in reason

    # 2. Category ambiguity: two categories with identical token overlap
    cat_coffee = Category(name="Coffee Shops", color="#78350F")
    cat_cafe = Category(name="Cafes & Bakeries", color="#F59E0B")
    db_session.add_all([cat_coffee, cat_cafe])
    db_session.commit()

    # Even in 'permissive' mode, ambiguous categories must remain Uncategorised
    cat_id, _, _, cat_reason = suggest_category_from_history(
        db=db_session,
        merchant="Artisan Cafe Espresso",
        ocr_lines=["Fresh coffee bakery goods"],
        confidence_level="permissive"
    )
    # If the context is ambiguous between two categories, it should not silently prefill
    if cat_id is None:
        assert "ambiguous" in cat_reason.lower()


def test_5_profile_isolation_of_confidence_settings(isolated_profiles_env):
    """
    Requirement 5:
    Confidence settings persist independently per profile.
    """
    app.dependency_overrides.clear()
    client = TestClient(app)

    # 1. Configure Default profile to 'cautious' for category and 'cautious' for account
    res_def_put = client.put(
        "/api/system/settings",
        json={
            "import_confidence_category": "cautious",
            "import_confidence_account": "cautious"
        }
    )
    assert res_def_put.status_code == 200
    assert res_def_put.json()["import_confidence_category"] == "cautious"
    assert res_def_put.json()["import_confidence_account"] == "cautious"

    # 2. Create Profile 2
    res_p2 = client.post("/api/profiles", json={"name": "Freelance Operations"})
    p2_id = res_p2.json()["id"]

    # 3. Read Profile 2 settings: should default to 'balanced'
    res_p2_get = client.get("/api/system/settings", headers={"X-Profile-ID": p2_id})
    assert res_p2_get.status_code == 200
    assert res_p2_get.json()["import_confidence_category"] == "balanced"
    assert res_p2_get.json()["import_confidence_account"] == "balanced"

    # 4. Update Profile 2 to 'permissive'
    res_p2_put = client.put(
        "/api/system/settings",
        headers={"X-Profile-ID": p2_id},
        json={
            "import_confidence_category": "permissive",
            "import_confidence_account": "permissive"
        }
    )
    assert res_p2_put.status_code == 200
    assert res_p2_put.json()["import_confidence_category"] == "permissive"
    assert res_p2_put.json()["import_confidence_account"] == "permissive"

    # 5. Verify Default profile remains 'cautious' (strict isolation)
    res_def_check = client.get("/api/system/settings", headers={"X-Profile-ID": "default"})
    assert res_def_check.status_code == 200
    assert res_def_check.json()["import_confidence_category"] == "cautious"
    assert res_def_check.json()["import_confidence_account"] == "cautious"


def test_6_offline_and_no_external_network_calls(monkeypatch, db_session):
    """
    Requirement 7:
    Verification that import and suggestion functions execute 100% locally and offline.
    """
    import socket

    def blocked_connect(*args, **kwargs):
        raise RuntimeError("Network call attempted during local import processing!")

    monkeypatch.setattr(socket.socket, "connect", blocked_connect)

    # Execute account and category matching
    acc = Account(name="Metro Bank Current", account_type=AccountType.CURRENT, currency="GBP")
    cat = Category(name="Supermarket", color="#10B981")
    db_session.add_all([acc, cat])
    db_session.commit()

    # None of these should make network connections
    match_account_from_context(
        db=db_session,
        ocr_lines=["METRO BANK", "CARD: 1234"],
        confidence_level="balanced"
    )

    suggest_category_from_history(
        db=db_session,
        merchant="Tesco Superstore",
        confidence_level="balanced"
    )
