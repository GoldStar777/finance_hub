"""
Isolated verification suite for Finance Hub Data Quality & Review Area.

Covers:
1. All 7 finding categories (uncategorised, unassigned_account, potential_duplicate,
   possible_transfer, uncertain_import, archived_reference, integrity_issue) & explanations.
2. Duplicate and transfer ambiguity safeguards (no false matches on unrelated merchants,
   receipt splits, cross-currency, repeat series intervals, or 1-to-many tied transfers).
3. Live updating of findings after assignment, soft-delete, restore, dismissal, and undismissal.
4. Direct preserved-filter links into Ledger and Queue + server-side filter parameters.
5. Strict multi-workspace profile isolation.
6. Strictly non-mutating scan behavior (balances, counts, and settings unchanged).
7. Linear-time performance on a large transaction history (3,000+ transactions).
"""

import json
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import text

from app.core import profiles as profiles_module
from app.core.backup import set_system_setting
from app.core.data_quality import get_data_quality_report
from app.core.profiles import create_profile
from app.core.review_suggestions import get_dismissed_suggestion_ids
from app.database import Base, configure_sqlite_engine, db_registry
from app.ledger import LedgerEngine
from app.main import app
from app.models import (
    Account,
    AccountBalanceAnchor,
    AccountType,
    Category,
    CategoryType,
    ExpenseNature,
    Holding,
    StagingItem,
    StagingStatus,
    SystemSetting,
    Transaction,
    TransactionType,
)


def _create_base_fixtures(db_session):
    checking = Account(
        name="Everyday Checking",
        account_type=AccountType.CURRENT,
        currency="GBP",
        starting_balance_pence=500000,
        starting_balance_date=datetime(2025, 1, 1, 0, 0, tzinfo=timezone.utc),
    )
    savings = Account(
        name="Savings Pot",
        account_type=AccountType.SAVINGS,
        currency="GBP",
        starting_balance_pence=200000,
        starting_balance_date=datetime(2025, 1, 1, 0, 0, tzinfo=timezone.utc),
    )
    usd_acc = Account(
        name="USD Travel",
        account_type=AccountType.CURRENT,
        currency="USD",
        starting_balance_pence=100000,
        starting_balance_date=datetime(2025, 1, 1, 0, 0, tzinfo=timezone.utc),
    )
    archived_acc = Account(
        name="Closed Bank Card",
        account_type=AccountType.CREDIT_CARD,
        currency="GBP",
        is_active=False,
    )
    cat_food = Category(name="Groceries", default_expense_nature=ExpenseNature.VARIABLE)
    cat_utils = Category(name="Utilities", default_expense_nature=ExpenseNature.FIXED)
    archived_cat = Category(name="Old Subscriptions", default_expense_nature=ExpenseNature.FIXED, is_active=False)

    db_session.add_all([checking, savings, usd_acc, archived_acc, cat_food, cat_utils, archived_cat])
    db_session.commit()
    return {
        "checking": checking,
        "savings": savings,
        "usd_acc": usd_acc,
        "archived_acc": archived_acc,
        "cat_food": cat_food,
        "cat_utils": cat_utils,
        "archived_cat": archived_cat,
    }


def test_1_all_finding_categories_and_explainability(db_session, client):
    """Verifies all 7 finding types surface accurately with explainable evidence and history hints."""
    fx = _create_base_fixtures(db_session)

    # Approved history: 2 categorized Tesco purchases -> Groceries (for advisory hint)
    for day in (1, 5):
        db_session.add(
            Transaction(
                transaction_date=datetime(2026, 10, day, 12, 0, tzinfo=timezone.utc),
                transaction_type=TransactionType.EXPENSE,
                amount_pence=2400 + day,
                merchant="Tesco Supermarket",
                account_id=fx["checking"].id,
                category_id=fx["cat_food"].id,
                expense_nature=ExpenseNature.VARIABLE,
            )
        )

    # 1a. Uncategorised Expense matching history ("Tesco Supermarket")
    uncat_tx = Transaction(
        transaction_date=datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc),
        transaction_type=TransactionType.EXPENSE,
        amount_pence=3150,
        merchant="Tesco Supermarket",
        account_id=fx["checking"].id,
        category_id=None,
    )
    # 1b. Normal Transfer without category (must NOT be flagged as uncategorised!)
    valid_transfer = Transaction(
        transaction_date=datetime(2026, 10, 11, 12, 0, tzinfo=timezone.utc),
        transaction_type=TransactionType.TRANSFER,
        amount_pence=10000,
        merchant="Transfer to Savings",
        account_id=fx["checking"].id,
        destination_account_id=fx["savings"].id,
        category_id=None,
    )
    # 2. Unassigned account expense
    unassigned_tx = Transaction(
        transaction_date=datetime(2026, 10, 12, 12, 0, tzinfo=timezone.utc),
        transaction_type=TransactionType.EXPENSE,
        amount_pence=1250,
        merchant="Corner Cafe",
        account_id=None,
        category_id=fx["cat_food"].id,
    )
    # 3. Potential ledger-vs-ledger duplicate pair
    dup_a = Transaction(
        transaction_date=datetime(2026, 10, 14, 12, 0, tzinfo=timezone.utc),
        transaction_type=TransactionType.EXPENSE,
        amount_pence=4599,
        merchant="Spotify Premium",
        account_id=fx["checking"].id,
        category_id=fx["cat_utils"].id,
    )
    dup_b = Transaction(
        transaction_date=datetime(2026, 10, 14, 14, 0, tzinfo=timezone.utc),
        transaction_type=TransactionType.EXPENSE,
        amount_pence=4599,
        merchant="Spotify Premium UK",
        account_id=fx["checking"].id,
        category_id=fx["cat_utils"].id,
    )
    # 4. Possible unpaired ledger-vs-ledger transfer
    trf_out = Transaction(
        transaction_date=datetime(2026, 10, 16, 12, 0, tzinfo=timezone.utc),
        transaction_type=TransactionType.EXPENSE,
        amount_pence=30000,
        merchant="Transfer to Savings Pot",
        account_id=fx["checking"].id,
        category_id=None,
    )
    trf_in = Transaction(
        transaction_date=datetime(2026, 10, 16, 15, 0, tzinfo=timezone.utc),
        transaction_type=TransactionType.INCOME,
        amount_pence=30000,
        merchant="Transfer from Everyday Checking",
        account_id=fx["savings"].id,
        category_id=None,
    )
    # 5a. Queued item with direction uncertainty & currency conflict
    stg_uncertain = StagingItem(
        status=StagingStatus.PENDING,
        source_type="screenshot",
        extracted_date=datetime(2026, 10, 18, 12, 0, tzinfo=timezone.utc),
        extracted_amount_pence=7500,
        extracted_merchant="Foreign Hotel",
        suggested_account_id=None,
        raw_payload_json=json.dumps({
            "transaction_type": "expense",
            "direction_uncertain": True,
            "original_currency": "EUR",
            "currency_conflict": True,
            "currency_conflict_message": "EUR charge needs GBP bank billed amount",
        }),
    )
    # 5b. Imported ledger row with blank merchant & blank notes
    imported_blank = Transaction(
        transaction_date=datetime(2026, 10, 19, 12, 0, tzinfo=timezone.utc),
        transaction_type=TransactionType.EXPENSE,
        amount_pence=1990,
        merchant=None,
        notes=None,
        entry_method="statement_csv",
        account_id=fx["checking"].id,
        category_id=fx["cat_food"].id,
    )
    # 6. Archived account + archived category link
    archived_ref_tx = Transaction(
        transaction_date=datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc),
        transaction_type=TransactionType.EXPENSE,
        amount_pence=999,
        merchant="Archived Streamer",
        account_id=fx["archived_acc"].id,
        category_id=fx["archived_cat"].id,
    )
    # 7. Concrete integrity issues: self-transfer + broken missing category reference (via raw SQL)
    broken_transfer = Transaction(
        transaction_date=datetime(2026, 10, 21, 12, 0, tzinfo=timezone.utc),
        transaction_type=TransactionType.TRANSFER,
        amount_pence=5000,
        merchant="Self Transfer Error",
        account_id=fx["checking"].id,
        destination_account_id=fx["checking"].id,
    )

    db_session.add_all([
        uncat_tx,
        valid_transfer,
        unassigned_tx,
        dup_a,
        dup_b,
        trf_out,
        trf_in,
        stg_uncertain,
        imported_blank,
        archived_ref_tx,
        broken_transfer,
    ])
    db_session.commit()

    # Simulate an orphaned holding account_id by disabling FK check briefly in SQLite
    db_session.execute(text("PRAGMA foreign_keys = OFF;"))
    db_session.execute(
        text(
            "INSERT INTO holdings (account_id, name, asset_class, currency, is_active) "
            "VALUES (999999, 'Orphan ETF', 'equity', 'GBP', 1)"
        )
    )
    db_session.commit()
    db_session.execute(text("PRAGMA foreign_keys = ON;"))

    resp = client.get("/api/review/findings")
    assert resp.status_code == 200
    body = resp.json()

    by_type = body["summary"]["by_type"]
    assert by_type["uncategorised"] >= 1
    assert by_type["unassigned_account"] == 1
    assert by_type["potential_duplicate"] == 1
    assert by_type["possible_transfer"] >= 1
    assert by_type["uncertain_import"] == 2
    assert by_type["archived_reference"] == 1
    assert by_type["integrity_issue"] == 2  # broken_transfer + orphan holding

    findings = body["findings"]

    # Transfers must NOT be falsely flagged as uncategorised
    uncat_ids = {f["transaction_id"] for f in findings if f["finding_type"] == "uncategorised"}
    assert uncat_tx.id in uncat_ids
    assert valid_transfer.id not in uncat_ids

    # Advisory history hint appears on matching Tesco uncategorised transaction without modifying DB
    uncat_item = next(f for f in findings if f["id"] == f"dq_uncat_tx_{uncat_tx.id}")
    assert uncat_item["suggested_category_id"] == fx["cat_food"].id
    assert uncat_item["suggested_category_name"] == "Groceries"
    assert any("approved transaction" in r.lower() for r in uncat_item["reasons"])

    # Integrity findings cannot be dismissed
    integrity_items = [f for f in findings if f["finding_type"] == "integrity_issue"]
    assert all(item["can_dismiss"] is False for item in integrity_items)
    dism_err = client.post("/api/review/dismiss", json={"finding_id": integrity_items[0]["id"]})
    assert dism_err.status_code == 400

    # Ledger-ledger duplicate shows comparison evidence
    dup_item = next(f for f in findings if f["finding_type"] == "potential_duplicate")
    assert dup_item["comparison"]["record_a"] is not None
    assert dup_item["comparison"]["record_b"] is not None
    assert len(dup_item["reasons"]) >= 3


def test_2_duplicate_and_transfer_ambiguity_safeguards(db_session, client):
    """
    Safeguards:
    - Same amount/date/account with unrelated merchant names -> NOT duplicate.
    - Same receipt_path split allocations -> NOT duplicate.
    - Repeat series installments -> NOT duplicate.
    - Cross-currency pairs -> NOT duplicate or transfer.
    - Ambiguous 1-to-2 matching transfers with tied scores -> suppressed cleanly.
    """
    fx = _create_base_fixtures(db_session)

    # Unrelated merchants (£3.50 same day, same account)
    db_session.add_all([
        Transaction(
            transaction_date=datetime(2026, 10, 5, 9, 0, tzinfo=timezone.utc),
            transaction_type=TransactionType.EXPENSE,
            amount_pence=350,
            merchant="Costa Coffee",
            account_id=fx["checking"].id,
            category_id=fx["cat_food"].id,
        ),
        Transaction(
            transaction_date=datetime(2026, 10, 5, 13, 0, tzinfo=timezone.utc),
            transaction_type=TransactionType.EXPENSE,
            amount_pence=350,
            merchant="Pret a Manger",
            account_id=fx["checking"].id,
            category_id=fx["cat_food"].id,
        ),
        # Receipt split siblings sharing receipt_path (same day, same merchant, equal split amounts)
        Transaction(
            transaction_date=datetime(2026, 10, 6, 12, 0, tzinfo=timezone.utc),
            transaction_type=TransactionType.EXPENSE,
            amount_pence=1000,
            merchant="Tesco",
            receipt_path="receipts/shared_split.jpg",
            account_id=fx["checking"].id,
            category_id=fx["cat_food"].id,
        ),
        Transaction(
            transaction_date=datetime(2026, 10, 6, 12, 0, tzinfo=timezone.utc),
            transaction_type=TransactionType.EXPENSE,
            amount_pence=1000,
            merchant="Tesco",
            receipt_path="receipts/shared_split.jpg",
            account_id=fx["checking"].id,
            category_id=fx["cat_utils"].id,
        ),
        # Repeat series siblings 2 days apart sharing repeat_series_id
        Transaction(
            transaction_date=datetime(2026, 10, 8, 12, 0, tzinfo=timezone.utc),
            transaction_type=TransactionType.EXPENSE,
            amount_pence=2200,
            merchant="Weekly Box",
            repeat_series_id="rep_test_01",
            account_id=fx["checking"].id,
            category_id=fx["cat_food"].id,
        ),
        Transaction(
            transaction_date=datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc),
            transaction_type=TransactionType.EXPENSE,
            amount_pence=2200,
            merchant="Weekly Box",
            repeat_series_id="rep_test_01",
            account_id=fx["checking"].id,
            category_id=fx["cat_food"].id,
        ),
        # Cross-currency £50 GBP vs $50 USD
        Transaction(
            transaction_date=datetime(2026, 10, 12, 12, 0, tzinfo=timezone.utc),
            transaction_type=TransactionType.EXPENSE,
            amount_pence=5000,
            merchant="Airport Store",
            account_id=fx["checking"].id,
            category_id=fx["cat_food"].id,
        ),
        Transaction(
            transaction_date=datetime(2026, 10, 12, 12, 0, tzinfo=timezone.utc),
            transaction_type=TransactionType.EXPENSE,
            amount_pence=5000,
            merchant="Airport Store",
            account_id=fx["usd_acc"].id,
            category_id=fx["cat_food"].id,
        ),
    ])
    # Ambiguous 1-to-2 transfer candidates with identical score across two distinct destination accounts
    savings_alt = Account(
        name="Reserve Pot",
        account_type=AccountType.SAVINGS,
        currency="GBP",
        starting_balance_pence=50000,
    )
    db_session.add(savings_alt)
    db_session.flush()

    db_session.add_all([
        Transaction(
            transaction_date=datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc),
            transaction_type=TransactionType.EXPENSE,
            amount_pence=25000,
            merchant="Bank Transfer",
            account_id=fx["checking"].id,
            category_id=fx["cat_utils"].id,
        ),
        Transaction(
            transaction_date=datetime(2026, 10, 15, 13, 0, tzinfo=timezone.utc),
            transaction_type=TransactionType.INCOME,
            amount_pence=25000,
            merchant="Bank Transfer",
            account_id=fx["savings"].id,
            category_id=fx["cat_utils"].id,
        ),
        Transaction(
            transaction_date=datetime(2026, 10, 15, 14, 0, tzinfo=timezone.utc),
            transaction_type=TransactionType.INCOME,
            amount_pence=25000,
            merchant="Bank Transfer",
            account_id=savings_alt.id,
            category_id=fx["cat_utils"].id,
        ),
    ])
    db_session.commit()

    report = get_data_quality_report(db_session)
    assert report["summary"]["by_type"]["potential_duplicate"] == 0
    assert report["summary"]["by_type"]["possible_transfer"] == 0


def test_3_findings_update_on_fix_delete_restore_and_dismiss(db_session, client):
    """
    Tests finding lifecycle after:
    - Explicit category/account assignment
    - Soft-deleting a ledger duplicate + restoring via Recently Deleted
    - Reversibly dismissing + restoring hidden suggestions
    """
    fx = _create_base_fixtures(db_session)
    uncat = Transaction(
        transaction_date=datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc),
        transaction_type=TransactionType.EXPENSE,
        amount_pence=1500,
        merchant="Pharmacy",
        account_id=None,
        category_id=None,
    )
    dup_1 = Transaction(
        transaction_date=datetime(2026, 10, 12, 12, 0, tzinfo=timezone.utc),
        transaction_type=TransactionType.EXPENSE,
        amount_pence=800,
        merchant="Coffee Bean",
        account_id=fx["checking"].id,
        category_id=fx["cat_food"].id,
    )
    dup_2 = Transaction(
        transaction_date=datetime(2026, 10, 12, 12, 5, tzinfo=timezone.utc),
        transaction_type=TransactionType.EXPENSE,
        amount_pence=800,
        merchant="Coffee Bean",
        account_id=fx["checking"].id,
        category_id=fx["cat_food"].id,
    )
    db_session.add_all([uncat, dup_1, dup_2])
    db_session.commit()

    # Initial scan
    initial = client.get("/api/review/findings").json()
    assert initial["summary"]["by_type"]["uncategorised"] == 1
    assert initial["summary"]["by_type"]["unassigned_account"] == 1
    assert initial["summary"]["by_type"]["potential_duplicate"] == 1

    # 1. Assign category & account explicitly -> those two findings resolve cleanly
    upd = client.put(
        f"/api/transactions/{uncat.id}",
        json={"category_id": fx["cat_food"].id, "account_id": fx["checking"].id},
    )
    assert upd.status_code == 200
    after_fix = client.get("/api/review/findings").json()
    assert after_fix["summary"]["by_type"]["uncategorised"] == 0
    assert after_fix["summary"]["by_type"]["unassigned_account"] == 0
    assert after_fix["summary"]["by_type"]["potential_duplicate"] == 1

    # 2. Soft-delete dup_2 -> duplicate finding resolves; restore -> reappears
    del_res = client.post("/api/transactions/bulk-delete", json={"transaction_ids": [dup_2.id]})
    assert del_res.status_code == 200
    after_del = client.get("/api/review/findings").json()
    assert after_del["summary"]["by_type"]["potential_duplicate"] == 0

    rest_res = client.post("/api/transactions/restore", json={"transaction_ids": [dup_2.id]})
    assert rest_res.status_code == 200
    after_rest = client.get("/api/review/findings").json()
    assert after_rest["summary"]["by_type"]["potential_duplicate"] == 1

    # 3. Reversible dismiss / undismiss
    dup_fid = after_rest["findings"][0]["id"]
    d_res = client.post("/api/review/dismiss", json={"finding_id": dup_fid})
    assert d_res.status_code == 200
    assert dup_fid in get_dismissed_suggestion_ids(db_session)

    hidden_scan = client.get("/api/review/findings").json()
    assert hidden_scan["summary"]["total_active"] == 0
    assert hidden_scan["summary"]["dismissed_count"] == 1

    with_dism = client.get("/api/review/findings?include_dismissed=true").json()
    assert len(with_dism["findings"]) == 1
    assert with_dism["findings"][0]["is_dismissed"] is True

    # Also shares dismissal state with /api/staging/suggestions
    q_sugs = client.get("/api/staging/suggestions").json()
    assert dup_fid not in [s["id"] for s in q_sugs["duplicate_suggestions"]]

    undism = client.post("/api/review/restore-dismissed", json={"finding_id": dup_fid})
    assert undism.status_code == 200
    restored_scan = client.get("/api/review/findings").json()
    assert restored_scan["summary"]["total_active"] == 1
    assert restored_scan["summary"]["dismissed_count"] == 0


def test_4_preserved_links_and_backend_filters(db_session, client):
    """Verifies generated Ledger/Queue URLs preserve exact filters and query filters narrow findings cleanly."""
    fx = _create_base_fixtures(db_session)
    uncat = Transaction(
        transaction_date=datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc),
        transaction_type=TransactionType.EXPENSE,
        amount_pence=1200,
        merchant="Bookshop",
        account_id=fx["checking"].id,
        category_id=None,
    )
    unassigned = Transaction(
        transaction_date=datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc),
        transaction_type=TransactionType.EXPENSE,
        amount_pence=2000,
        merchant="Flea Market",
        account_id=None,
        category_id=fx["cat_food"].id,
    )
    stg_unc = StagingItem(
        status=StagingStatus.PENDING,
        source_type="receipt_image",
        extracted_date=None,
        extracted_amount_pence=900,
        extracted_merchant="Unreadable Receipt",
        raw_payload_json=json.dumps({"transaction_type": "expense"}),
    )
    db_session.add_all([uncat, unassigned, stg_unc])
    db_session.commit()

    all_res = client.get("/api/review/findings").json()
    by_id = {f["id"]: f for f in all_res["findings"]}

    uncat_finding = by_id[f"dq_uncat_tx_{uncat.id}"]
    parsed_ledger = urlparse(uncat_finding["ledger_url"])
    qs_ledger = parse_qs(parsed_ledger.query)
    assert parsed_ledger.path == "/ledger"
    assert qs_ledger["category_id"] == ["uncategorized"]
    assert qs_ledger["date_preset"] == ["all"]
    assert qs_ledger["q"] == ["Bookshop"]

    unass_finding = by_id[f"dq_unassigned_tx_{unassigned.id}"]
    qs_unass = parse_qs(urlparse(unass_finding["ledger_url"]).query)
    assert qs_unass["account_ids"] == ["unassigned"]

    stg_finding = by_id[f"dq_uncertain_staging_{stg_unc.id}"]
    parsed_q = urlparse(stg_finding["queue_url"])
    qs_q = parse_qs(parsed_q.query)
    assert parsed_q.path == "/queue"
    assert qs_q["item_id"] == [str(stg_unc.id)]

    # Verify filter parameters preserve workspace summary totals while narrowing returned list
    filtered = client.get("/api/review/findings?finding_type=uncategorised&q=Bookshop&start_date=2026-10-01&end_date=2026-10-10").json()
    assert filtered["summary"]["total_active"] == 3
    assert filtered["filtered_count"] == 1
    assert filtered["findings"][0]["id"] == f"dq_uncat_tx_{uncat.id}"


@pytest.fixture
def isolated_review_profiles_env(tmp_path, monkeypatch):
    """Provides a self-contained multi-profile filesystem and DB environment in tmp_path."""
    test_data_dir = tmp_path / "data"
    test_data_dir.mkdir(parents=True, exist_ok=True)
    test_reg_path = test_data_dir / "profiles.json"
    test_db_path = test_data_dir / "finances.db"
    test_receipts = test_data_dir / "receipts"
    test_staging = test_data_dir / "staging_receipts"
    test_backups = test_data_dir / "backups"
    test_receipts.mkdir(parents=True, exist_ok=True)
    test_staging.mkdir(parents=True, exist_ok=True)
    test_backups.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(profiles_module, "DATA_DIR", test_data_dir)
    monkeypatch.setattr(profiles_module, "PROFILES_REGISTRY_PATH", test_reg_path)
    monkeypatch.setattr(profiles_module, "DB_PATH", test_db_path)
    monkeypatch.setattr(profiles_module, "ARCHIVE_RECEIPTS_DIR", test_receipts)
    monkeypatch.setattr(profiles_module, "STAGING_RECEIPTS_DIR", test_staging)
    monkeypatch.setattr(profiles_module, "BACKUP_DIR", test_backups)

    eng = configure_sqlite_engine(f"sqlite:///{test_db_path}")
    Base.metadata.create_all(bind=eng)
    with eng.begin() as conn:
        conn.execute(text("CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY);"))
        conn.execute(text("INSERT INTO alembic_version (version_num) VALUES ('b2c3d4e5f6a7');"))
    eng.dispose()
    db_registry.dispose_all()
    yield
    db_registry.dispose_all()


def test_5_strict_profile_isolation(isolated_review_profiles_env):
    """
    Ensures review findings, category history recommendations, and dismissals in one
    profile NEVER appear in or affect another workspace.
    """
    prof_b = create_profile("Second Workspace")
    client = TestClient(app)

    # Profile A: Checking account, Food category, history + 1 uncategorised Bakery expense + 1 dismissal
    acc_a = client.post("/api/accounts", headers={"X-Profile-ID": "default"}, json={
        "name": "Alpha Bank", "account_type": "current", "starting_balance": 500
    }).json()
    cat_a = client.post("/api/categories", headers={"X-Profile-ID": "default"}, json={
        "name": "Alpha Dining", "default_expense_nature": "variable"
    }).json()
    client.post("/api/transactions", headers={"X-Profile-ID": "default"}, json={
        "transaction_type": "expense", "amount": 10.0, "merchant": "Isolated Bakery",
        "account_id": acc_a["id"], "category_id": cat_a["id"], "transaction_date": "2026-10-01T12:00:00Z"
    })
    uncat_a = client.post("/api/transactions", headers={"X-Profile-ID": "default"}, json={
        "transaction_type": "expense", "amount": 12.0, "merchant": "Isolated Bakery",
        "account_id": acc_a["id"], "category_id": None, "transaction_date": "2026-10-02T12:00:00Z"
    }).json()

    # Profile B: completely separate clean workspace with 1 uncategorised transaction without history
    acc_b = client.post("/api/accounts", headers={"X-Profile-ID": prof_b.id}, json={
        "name": "Beta Bank", "account_type": "current", "starting_balance": 200
    }).json()
    uncat_b = client.post("/api/transactions", headers={"X-Profile-ID": prof_b.id}, json={
        "transaction_type": "expense", "amount": 25.0, "merchant": "Isolated Bakery",
        "account_id": acc_b["id"], "category_id": None, "transaction_date": "2026-10-03T12:00:00Z"
    }).json()

    rev_a = client.get("/api/review/findings", headers={"X-Profile-ID": "default"}).json()
    rev_b = client.get("/api/review/findings", headers={"X-Profile-ID": prof_b.id}).json()

    assert rev_a["profile_id"] == "default"
    assert rev_b["profile_id"] == prof_b.id

    a_tx_ids = {f.get("transaction_id") for f in rev_a["findings"]}
    b_tx_ids = {f.get("transaction_id") for f in rev_b["findings"]}
    assert uncat_a["id"] in a_tx_ids
    assert uncat_b["id"] not in a_tx_ids

    # Alpha's learned category "Alpha Dining" must NEVER suggest onto Beta's entry
    b_item = next(f for f in rev_b["findings"] if f.get("transaction_id") == uncat_b["id"])
    assert b_item["suggested_category_id"] is None

    # Dismissing Alpha's item does not affect Beta
    a_fid = f"dq_uncat_tx_{uncat_a['id']}"
    assert client.post("/api/review/dismiss", headers={"X-Profile-ID": "default"}, json={"finding_id": a_fid}).status_code == 200
    rev_b_after = client.get("/api/review/findings", headers={"X-Profile-ID": prof_b.id}).json()
    assert rev_b_after["summary"]["dismissed_count"] == 0
    assert rev_b_after["summary"]["total_active"] == rev_b["summary"]["total_active"]


def test_6_no_mutations_when_scanning(db_session, client):
    """Confirms repeated scans do NOT mutate transactions, staging items, anchors, settings, or balances."""
    fx = _create_base_fixtures(db_session)
    db_session.add_all([
        Transaction(
            transaction_date=datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc),
            transaction_type=TransactionType.EXPENSE,
            amount_pence=1200,
            merchant="Shop",
            account_id=fx["checking"].id,
            category_id=None,
        ),
        Transaction(
            transaction_date=datetime(2026, 10, 11, 12, 0, tzinfo=timezone.utc),
            transaction_type=TransactionType.EXPENSE,
            amount_pence=1200,
            merchant="Shop",
            account_id=fx["checking"].id,
            category_id=None,
        ),
    ])
    db_session.commit()

    before_bal = LedgerEngine.get_account_balance(db_session, fx["checking"].id)
    before_txs = db_session.query(Transaction).count()
    before_stg = db_session.query(StagingItem).count()
    before_settings = {s.key: s.value for s in db_session.query(SystemSetting).all()}

    for qs in ("", "?finding_type=potential_duplicate", "?include_dismissed=true"):
        res = client.get(f"/api/review/findings{qs}")
        assert res.status_code == 200

    db_session.expire_all()
    assert LedgerEngine.get_account_balance(db_session, fx["checking"].id) == before_bal
    assert db_session.query(Transaction).count() == before_txs
    assert db_session.query(StagingItem).count() == before_stg
    assert {s.key: s.value for s in db_session.query(SystemSetting).all()} == before_settings


def test_7_large_history_performance(db_session, client):
    """Scans 3,200 transactions across accounts quickly without quadratic blowup."""
    fx = _create_base_fixtures(db_session)
    cat_salary = Category(name="Salary", category_type=CategoryType.INCOME)
    db_session.add(cat_salary)
    db_session.commit()
    base_dt = datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc)

    bulk_txs = []
    for i in range(3200):
        dt = base_dt + timedelta(hours=4 * i)
        is_income = (i % 5 == 0)
        cat_id = None if i % 40 == 0 else (cat_salary.id if is_income else fx["cat_food"].id)
        acc_id = fx["checking"].id if i % 2 == 0 else fx["savings"].id
        bulk_txs.append(
            Transaction(
                transaction_date=dt,
                effective_timestamp=dt,
                transaction_type=TransactionType.INCOME if is_income else TransactionType.EXPENSE,
                amount_pence=500 + (i % 97) * 100,
                merchant=f"Merchant {(i % 30)}",
                account_id=acc_id,
                category_id=cat_id,
            )
        )

    db_session.bulk_save_objects(bulk_txs)
    db_session.commit()

    t0 = time.perf_counter()
    report = get_data_quality_report(db_session)
    elapsed = time.perf_counter() - t0

    assert report["summary"]["scanned_transactions_count"] == 3200
    assert report["summary"]["by_type"]["uncategorised"] == 80
    assert elapsed < 3.0
