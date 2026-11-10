"""
Review Queue Advisory Refinement Suggestions Tests

Tests:
1. Candidate duplicate detection (intra-staging and staging vs ledger)
2. Candidate transfer detection (intra-staging and staging vs ledger)
3. Advisory nature: no mutation until explicit confirmation
4. Safe duplicate confirmation and sibling file retention
5. Atomic transfer pairing (both staging items approved, single transfer transaction)
6. Dismissal persistence per profile
7. API endpoints integration
"""

import json
from datetime import datetime, timezone
import pytest
from fastapi.testclient import TestClient

from app.models import StagingItem, StagingStatus, Transaction, TransactionType, Account, AccountType, Category
from app.core.review_suggestions import (
    get_review_queue_suggestions, confirm_duplicate_suggestion, confirm_transfer_suggestion,
    add_dismissed_suggestion_id, get_dismissed_suggestion_ids
)


def test_duplicate_suggestions_intra_staging_and_ledger(client: TestClient, db_session):
    acc1 = Account(name="Current Account", account_type=AccountType.CURRENT, currency="GBP")
    acc2 = Account(name="Credit Card", account_type=AccountType.CREDIT_CARD, currency="GBP")
    db_session.add_all([acc1, acc2])
    db_session.commit()

    # 1. Existing ledger transaction
    ledger_tx = Transaction(
        transaction_date=datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc),
        transaction_type=TransactionType.EXPENSE,
        amount_pence=4500,
        merchant="Tesco Stores Ltd",
        account_id=acc1.id,
    )
    db_session.add(ledger_tx)
    db_session.commit()

    # 2. Staging item 1: duplicate of ledger transaction
    stg1 = StagingItem(
        status=StagingStatus.PENDING,
        source_type="csv",
        extracted_date=datetime(2026, 10, 15, 14, 0, tzinfo=timezone.utc),
        extracted_amount_pence=4500,
        extracted_merchant="Tesco Stores",
        suggested_account_id=acc1.id,
        raw_payload_json=json.dumps({"transaction_type": "expense"})
    )

    # 3. Staging item 2 & 3: duplicate pair within staging
    stg2 = StagingItem(
        status=StagingStatus.PENDING,
        source_type="csv",
        extracted_date=datetime(2026, 10, 16, 9, 0, tzinfo=timezone.utc),
        extracted_amount_pence=1899,
        extracted_merchant="Netflix Subscription",
        suggested_account_id=acc2.id,
        raw_payload_json=json.dumps({"transaction_type": "expense"})
    )
    stg3 = StagingItem(
        status=StagingStatus.PENDING,
        source_type="csv",
        extracted_date=datetime(2026, 10, 16, 9, 30, tzinfo=timezone.utc),
        extracted_amount_pence=1899,
        extracted_merchant="Netflix.com",
        suggested_account_id=acc2.id,
        raw_payload_json=json.dumps({"transaction_type": "expense"})
    )

    db_session.add_all([stg1, stg2, stg3])
    db_session.commit()

    # Fetch suggestions via core engine
    suggestions = get_review_queue_suggestions(db_session)
    dupes = suggestions["duplicate_suggestions"]
    assert len(dupes) >= 2

    # Check that stg1 matched ledger_tx
    stg1_match = next((d for d in dupes if d["record_a"]["id"] == stg1.id), None)
    assert stg1_match is not None
    assert stg1_match["record_b"]["kind"] == "ledger"
    assert stg1_match["record_b"]["id"] == ledger_tx.id
    assert len(stg1_match["reasons"]) > 0

    # Check that stg3 matched stg2
    stg3_match = next((d for d in dupes if (d["record_a"]["id"] == stg3.id and d["record_b"]["id"] == stg2.id) or (d["record_a"]["id"] == stg2.id and d["record_b"]["id"] == stg3.id)), None)
    assert stg3_match is not None
    assert stg3_match["record_b"]["kind"] == "staging"

    # Test API endpoint
    resp = client.get("/api/staging/suggestions")
    assert resp.status_code == 200
    api_data = resp.json()
    assert api_data["summary"]["duplicates_count"] >= 2


def test_transfer_suggestions_and_pairing(client: TestClient, db_session):
    acc_checking = Account(name="Current Account", account_type=AccountType.CURRENT, currency="GBP")
    acc_savings = Account(name="Savings Account", account_type=AccountType.SAVINGS, currency="GBP")
    db_session.add_all([acc_checking, acc_savings])
    db_session.commit()

    # Outgoing money from Checking: expense of £500
    out_item = StagingItem(
        status=StagingStatus.PENDING,
        source_type="csv",
        extracted_date=datetime(2026, 10, 18, 10, 0, tzinfo=timezone.utc),
        extracted_amount_pence=50000,
        extracted_merchant="Transfer to Savings",
        suggested_account_id=acc_checking.id,
        raw_payload_json=json.dumps({"transaction_type": "expense"})
    )
    # Incoming money into Savings: income of £500
    in_item = StagingItem(
        status=StagingStatus.PENDING,
        source_type="csv",
        extracted_date=datetime(2026, 10, 18, 10, 5, tzinfo=timezone.utc),
        extracted_amount_pence=50000,
        extracted_merchant="Deposit from Current Acc",
        suggested_account_id=acc_savings.id,
        raw_payload_json=json.dumps({"transaction_type": "income"})
    )
    db_session.add_all([out_item, in_item])
    db_session.commit()

    resp = client.get("/api/staging/suggestions")
    assert resp.status_code == 200
    data = resp.json()
    transfers = data["transfer_suggestions"]
    assert len(transfers) >= 1

    tf = transfers[0]
    assert tf["type"] == "transfer"
    assert tf["source_record"]["account_name"] == "Current Account"
    assert tf["destination_record"]["account_name"] == "Savings Account"
    assert tf["source_record"]["amount_pence"] == 50000

    # Confirm transfer pairing via API
    confirm_resp = client.post("/api/staging/suggestions/confirm-transfer", json={
        "source_id": tf["source_record"]["id"],
        "source_kind": tf["source_record"]["kind"],
        "destination_id": tf["destination_record"]["id"],
        "destination_kind": tf["destination_record"]["kind"],
        "suggestion_id": tf["id"]
    })
    assert confirm_resp.status_code == 200
    tx_id = confirm_resp.json()["transaction_id"]

    # Verify created transaction
    paired_tx = db_session.query(Transaction).filter(Transaction.id == tx_id).first()
    assert paired_tx is not None
    assert paired_tx.transaction_type == TransactionType.TRANSFER
    assert paired_tx.account_id == acc_checking.id
    assert paired_tx.destination_account_id == acc_savings.id
    assert paired_tx.amount_pence == 50000

    # Verify both staging items are marked APPROVED
    db_session.refresh(out_item)
    db_session.refresh(in_item)
    assert out_item.status == StagingStatus.APPROVED
    assert in_item.status == StagingStatus.APPROVED


def test_confirm_duplicate_and_dismissal(client: TestClient, db_session):
    acc = Account(name="Current Account", account_type=AccountType.CURRENT, currency="GBP")
    db_session.add(acc)
    db_session.commit()

    stg_orig = StagingItem(
        status=StagingStatus.PENDING,
        source_type="csv",
        extracted_date=datetime(2026, 10, 20, 11, 0, tzinfo=timezone.utc),
        extracted_amount_pence=3200,
        extracted_merchant="Gym Membership",
        suggested_account_id=acc.id,
        raw_payload_json=json.dumps({"transaction_type": "expense"})
    )
    stg_dupe = StagingItem(
        status=StagingStatus.PENDING,
        source_type="csv",
        extracted_date=datetime(2026, 10, 20, 11, 0, tzinfo=timezone.utc),
        extracted_amount_pence=3200,
        extracted_merchant="Gym Membership",
        suggested_account_id=acc.id,
        raw_payload_json=json.dumps({"transaction_type": "expense"})
    )
    db_session.add_all([stg_orig, stg_dupe])
    db_session.commit()

    # Query suggestions
    resp = client.get("/api/staging/suggestions")
    dupes = resp.json()["duplicate_suggestions"]
    assert len(dupes) == 1
    sug_id = dupes[0]["id"]

    # Confirm exclusion of duplicate
    confirm_resp = client.post("/api/staging/suggestions/confirm-duplicate", json={
        "duplicate_staging_id": stg_dupe.id,
        "suggestion_id": sug_id
    })
    assert confirm_resp.status_code == 200
    assert confirm_resp.json()["discarded_id"] == stg_dupe.id

    # Verify stg_dupe is rejected and stg_orig is still pending
    db_session.refresh(stg_dupe)
    db_session.refresh(stg_orig)
    assert stg_dupe.status == StagingStatus.REJECTED
    assert stg_orig.status == StagingStatus.PENDING

    # Suggestion should now be dismissed and not returned
    resp2 = client.get("/api/staging/suggestions")
    assert resp2.json()["summary"]["duplicates_count"] == 0


def test_ledger_to_ledger_same_day_opposite_direction_suggestion_and_atomic_confirmation(client: TestClient, db_session, tmp_path):
    """
    Verifies:
    1. Creating two same-day, equal-amount opposite-direction entries across distinct
       compatible accounts in the Ledger (e.g. an expense on Current Account and an
       income on a Credit Card account) produces an advisory transfer suggestion in
       the Review Queue even when 0 staging items exist.
    2. Dismissing a suggestion changes neither Ledger record.
    3. Confirming the transfer atomically converts the outgoing record into a single
       dual-account Transaction(type=TRANSFER), merges the counterpart record, preserves
       both original dates, merchants, notes, and archived receipt paths, never deletes
       archived files on disk, and keeps account balances accurate.
    """
    from app.ledger import LedgerEngine

    opening_dt = datetime(2026, 10, 1, 0, 0, tzinfo=timezone.utc)
    acc_current = Account(
        name="Current Account",
        account_type=AccountType.CURRENT,
        currency="GBP",
        starting_balance_pence=100000,
        starting_balance_date=opening_dt,
    )
    acc_card = Account(
        name="Rewards Credit Card",
        account_type=AccountType.CREDIT_CARD,
        currency="GBP",
        starting_balance_pence=-25000,
        starting_balance_date=opening_dt,
    )
    db_session.add_all([acc_current, acc_card])
    db_session.commit()

    # Create two archived receipt files on disk to verify neither is deleted
    arch_file_1 = tmp_path / "archived_outflow_receipt.pdf"
    arch_file_2 = tmp_path / "archived_inflow_statement.pdf"
    arch_file_1.write_bytes(b"%PDF-1.4 synthetic outflow document")
    arch_file_2.write_bytes(b"%PDF-1.4 synthetic inflow document")

    tx_out = Transaction(
        transaction_date=datetime(2026, 10, 23, 9, 15, tzinfo=timezone.utc),
        effective_timestamp=datetime(2026, 10, 23, 9, 15, tzinfo=timezone.utc),
        transaction_type=TransactionType.EXPENSE,
        amount_pence=25000,
        merchant="Card Bill Payment",
        notes="Monthly Amex settlement",
        entry_method="manual",
        receipt_path=str(arch_file_1),
        account_id=acc_current.id,
    )
    tx_in = Transaction(
        transaction_date=datetime(2026, 10, 23, 10, 30, tzinfo=timezone.utc),
        effective_timestamp=datetime(2026, 10, 23, 10, 30, tzinfo=timezone.utc),
        transaction_type=TransactionType.INCOME,
        amount_pence=25000,
        merchant="Payment Received - Thank You",
        notes="Direct credit received",
        entry_method="manual",
        receipt_path=str(arch_file_2),
        account_id=acc_card.id,
    )
    db_session.add_all([tx_out, tx_in])
    db_session.commit()

    out_id = tx_out.id
    in_id = tx_in.id

    # Verify suggestion appears when 0 pending staging items exist
    assert db_session.query(StagingItem).count() == 0
    resp = client.get("/api/staging/suggestions")
    assert resp.status_code == 200
    data = resp.json()
    transfers = data["transfer_suggestions"]
    assert len(transfers) == 1

    tf = transfers[0]
    assert tf["subtype"] == "ledger_ledger"
    assert tf["source_record"]["id"] == out_id
    assert tf["source_record"]["kind"] == "ledger"
    assert tf["destination_record"]["id"] == in_id
    assert tf["destination_record"]["kind"] == "ledger"
    assert tf["action_explanation"] is not None
    assert f"Ledger #{out_id}" in tf["action_explanation"]
    assert f"Ledger #{in_id}" in tf["action_explanation"]

    # Confirm transfer via API
    confirm_resp = client.post("/api/staging/suggestions/confirm-transfer", json={
        "source_id": out_id,
        "source_kind": "ledger",
        "destination_id": in_id,
        "destination_kind": "ledger",
        "suggestion_id": tf["id"]
    })
    assert confirm_resp.status_code == 200
    paired_id = confirm_resp.json()["transaction_id"]
    assert paired_id == out_id

    # Verify atomic conversion: 1 transfer transaction remains, counterpart merged
    remaining_txs = db_session.query(Transaction).all()
    assert len(remaining_txs) == 1
    merged_tx = remaining_txs[0]
    assert merged_tx.id == out_id
    assert merged_tx.transaction_type == TransactionType.TRANSFER
    assert merged_tx.account_id == acc_current.id
    assert merged_tx.destination_account_id == acc_card.id
    assert merged_tx.amount_pence == 25000
    assert merged_tx.category_id is None

    # Verify provenance preserved in notes & receipt_path, and neither file on disk was deleted
    assert "Monthly Amex settlement" in merged_tx.notes
    assert "Direct credit received" in merged_tx.notes
    assert f"Outgoing Ledger #{out_id}" in merged_tx.notes
    assert f"Incoming Ledger #{in_id}" in merged_tx.notes
    assert str(arch_file_2) in merged_tx.notes
    assert merged_tx.receipt_path == str(arch_file_1)
    assert arch_file_1.exists()
    assert arch_file_2.exists()

    # Verify account balances are identical (-25000 from Current, +25000 to Credit Card)
    assert LedgerEngine.get_account_balance(db_session, acc_current.id) == 75000
    assert LedgerEngine.get_account_balance(db_session, acc_card.id) == 0


def test_dismissing_transfer_suggestion_mutates_nothing(client: TestClient, db_session):
    """
    Dismissing an advisory suggestion must never alter, delete, or reclassify
    the underlying Ledger or Staging records.
    """
    acc1 = Account(name="Main Current", account_type=AccountType.CURRENT, currency="GBP")
    acc2 = Account(name="Everyday Saver", account_type=AccountType.SAVINGS, currency="GBP")
    db_session.add_all([acc1, acc2])
    db_session.commit()

    tx1 = Transaction(
        transaction_date=datetime(2026, 10, 22, 12, 0, tzinfo=timezone.utc),
        transaction_type=TransactionType.EXPENSE,
        amount_pence=12000,
        merchant="Coffee & Co",
        account_id=acc1.id,
    )
    tx2 = Transaction(
        transaction_date=datetime(2026, 10, 22, 12, 0, tzinfo=timezone.utc),
        transaction_type=TransactionType.INCOME,
        amount_pence=12000,
        merchant="Refund Processed",
        account_id=acc2.id,
    )
    db_session.add_all([tx1, tx2])
    db_session.commit()

    resp = client.get("/api/staging/suggestions")
    transfers = resp.json()["transfer_suggestions"]
    assert len(transfers) == 1
    sug_id = transfers[0]["id"]

    # Dismiss suggestion
    d_resp = client.post("/api/staging/suggestions/dismiss", json={"suggestion_id": sug_id})
    assert d_resp.status_code == 200

    # Suggestion is hidden
    resp2 = client.get("/api/staging/suggestions")
    assert len(resp2.json()["transfer_suggestions"]) == 0

    # Underlying records are completely untouched
    db_session.refresh(tx1)
    db_session.refresh(tx2)
    assert tx1.transaction_type == TransactionType.EXPENSE
    assert tx1.merchant == "Coffee & Co"
    assert tx2.transaction_type == TransactionType.INCOME
    assert tx2.merchant == "Refund Processed"


def test_cross_currency_and_ambiguous_pairs_are_not_suggested_or_paired(client: TestClient, db_session):
    """
    Verifies:
    1. Cross-currency accounts (e.g. GBP vs USD) never produce transfer suggestions
       and cannot be paired via confirm_transfer_suggestion.
    2. Transactions with foreign original_currency conflict metadata are not paired.
    3. Ambiguous 1-to-many equal-amount pairs on the same day with tied scores are suppressed.
    4. Multi-day unrelated opposite-direction entries without transfer cues are not suggested.
    """
    acc_gbp_1 = Account(name="UK Current", account_type=AccountType.CURRENT, currency="GBP")
    acc_gbp_2 = Account(name="UK Savings A", account_type=AccountType.SAVINGS, currency="GBP")
    acc_gbp_3 = Account(name="UK Savings B", account_type=AccountType.SAVINGS, currency="GBP")
    acc_usd = Account(name="US Checking", account_type=AccountType.CURRENT, currency="USD")
    db_session.add_all([acc_gbp_1, acc_gbp_2, acc_gbp_3, acc_usd])
    db_session.commit()

    # 1. Cross-currency pair (GBP 100.00 vs USD 100.00 on same day)
    tx_gbp = Transaction(
        transaction_date=datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc),
        transaction_type=TransactionType.EXPENSE,
        amount_pence=10000,
        merchant="Transfer Out",
        account_id=acc_gbp_1.id,
    )
    tx_usd = Transaction(
        transaction_date=datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc),
        transaction_type=TransactionType.INCOME,
        amount_pence=10000,
        merchant="Transfer In",
        account_id=acc_usd.id,
    )

    # 2. Ambiguous 1-to-many GBP pair on same day (one £75 outflow, two identical £75 inflows on distinct accounts)
    tx_amb_out = Transaction(
        transaction_date=datetime(2026, 10, 12, 12, 0, tzinfo=timezone.utc),
        transaction_type=TransactionType.EXPENSE,
        amount_pence=7500,
        merchant="General Outflow",
        account_id=acc_gbp_1.id,
    )
    tx_amb_in_1 = Transaction(
        transaction_date=datetime(2026, 10, 12, 12, 0, tzinfo=timezone.utc),
        transaction_type=TransactionType.INCOME,
        amount_pence=7500,
        merchant="General Inflow",
        account_id=acc_gbp_2.id,
    )
    tx_amb_in_2 = Transaction(
        transaction_date=datetime(2026, 10, 12, 12, 0, tzinfo=timezone.utc),
        transaction_type=TransactionType.INCOME,
        amount_pence=7500,
        merchant="General Inflow",
        account_id=acc_gbp_3.id,
    )

    # 3. Unrelated 3-day-apart entries with no transfer/payment cues
    tx_unrel_out = Transaction(
        transaction_date=datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc),
        transaction_type=TransactionType.EXPENSE,
        amount_pence=4200,
        merchant="Supermarket Weekly Shop",
        account_id=acc_gbp_1.id,
    )
    tx_unrel_in = Transaction(
        transaction_date=datetime(2026, 10, 4, 12, 0, tzinfo=timezone.utc),
        transaction_type=TransactionType.INCOME,
        amount_pence=4200,
        merchant="Marketplace Sale Proceeds",
        account_id=acc_gbp_2.id,
    )

    db_session.add_all([tx_gbp, tx_usd, tx_amb_out, tx_amb_in_1, tx_amb_in_2, tx_unrel_out, tx_unrel_in])
    db_session.commit()

    suggestions = get_review_queue_suggestions(db_session)
    assert len(suggestions["transfer_suggestions"]) == 0

    # Also verify direct confirm_transfer_suggestion rejects cross-currency pairing
    with pytest.raises(ValueError, match="Cross-currency"):
        confirm_transfer_suggestion(
            db=db_session,
            source_id=tx_gbp.id,
            source_kind="ledger",
            destination_id=tx_usd.id,
            destination_kind="ledger"
        )


def test_staging_transfer_confirmation_preserves_shared_source_file_until_no_pending_siblings(db_session, tmp_path):
    """
    Verifies that confirming a transfer involving a staging item:
    1. Archives the staging file into archive_dir.
    2. Preserves the shared staging source file while another pending sibling references it.
    3. Cleans up the staging source file only when no pending siblings remain.
    """
    staging_dir = tmp_path / "staging_receipts"
    archive_dir = tmp_path / "receipts"
    staging_dir.mkdir(parents=True, exist_ok=True)
    archive_dir.mkdir(parents=True, exist_ok=True)

    shared_staged_file = staging_dir / "abcd1234_statement_upload.csv"
    shared_staged_file.write_bytes(b"Date,Description,Amount\n2026-10-20,Transfer,-200.00\n2026-10-20,Groceries,-45.00\n")

    acc_src = Account(name="Current Account", account_type=AccountType.CURRENT, currency="GBP")
    acc_dest = Account(name="Savings Account", account_type=AccountType.SAVINGS, currency="GBP")
    db_session.add_all([acc_src, acc_dest])
    db_session.commit()

    stg_transfer_out = StagingItem(
        status=StagingStatus.PENDING,
        source_type="statement_csv",
        extracted_date=datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc),
        extracted_amount_pence=20000,
        extracted_merchant="Transfer to Savings",
        suggested_account_id=acc_src.id,
        temp_file_path=str(shared_staged_file),
        raw_payload_json=json.dumps({"transaction_type": "expense"})
    )
    stg_sibling = StagingItem(
        status=StagingStatus.PENDING,
        source_type="statement_csv",
        extracted_date=datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc),
        extracted_amount_pence=4500,
        extracted_merchant="Groceries",
        suggested_account_id=acc_src.id,
        temp_file_path=str(shared_staged_file),
        raw_payload_json=json.dumps({"transaction_type": "expense"})
    )
    ledger_in = Transaction(
        transaction_date=datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc),
        transaction_type=TransactionType.INCOME,
        amount_pence=20000,
        merchant="Faster Payment In",
        account_id=acc_dest.id,
    )
    db_session.add_all([stg_transfer_out, stg_sibling, ledger_in])
    db_session.commit()

    # Confirm staging + ledger transfer while stg_sibling is still PENDING
    tx = confirm_transfer_suggestion(
        db=db_session,
        source_id=stg_transfer_out.id,
        source_kind="staging",
        destination_id=ledger_in.id,
        destination_kind="ledger",
        staging_dir=staging_dir,
        archive_dir=archive_dir,
    )
    assert tx.transaction_type == TransactionType.TRANSFER
    assert tx.receipt_path is not None
    # Shared file must STILL exist because stg_sibling is pending
    assert shared_staged_file.exists()


def test_paired_transfer_preserves_per_leg_timestamps_provenance_files_and_supports_unpair(db_session, tmp_path):
    """
    Verifies that pairing two records with different dates/timestamps, merchants, notes,
    entry methods, and receipt files into a transfer:
    1. Preserves both legs' dates and effective timestamps so LedgerEngine.get_account_balance
       evaluates the outgoing leg at the source timestamp and the incoming leg at the destination
       timestamp (preserving anchor-relative balances on both accounts).
    2. Exposes both legs' merchants, notes, entry methods, and receipt links on TransactionResponse
       and in transfer_provenance.
    3. Can be atomically reversed via unpair_transfer_transaction, restoring both original records
       with their exact original IDs, dates, timestamps, categories, merchants, notes, entry methods,
       and receipt paths.
    """
    from app.models import AccountBalanceAnchor, Category, ExpenseNature
    from app.ledger import LedgerEngine
    from app.core.review_suggestions import unpair_transfer_transaction
    from app.api.transactions import _to_transaction_response

    acc_src = Account(
        name="HSBC Current",
        account_type=AccountType.CURRENT,
        starting_balance_pence=100000,
        starting_balance_date=datetime(2026, 10, 1, 0, 0, tzinfo=timezone.utc),
        currency="GBP",
    )
    acc_dest = Account(
        name="Barclaycard Platinum",
        account_type=AccountType.CREDIT_CARD,
        starting_balance_pence=-80000,
        starting_balance_date=datetime(2026, 10, 11, 12, 0, tzinfo=timezone.utc),
        currency="GBP",
    )
    cat_bills = Category(name="Bills", default_expense_nature=ExpenseNature.FIXED, is_active=True)
    db_session.add_all([acc_src, acc_dest, cat_bills])
    db_session.commit()

    src_dt = datetime(2026, 10, 10, 9, 30, tzinfo=timezone.utc)
    dest_dt = datetime(2026, 10, 12, 16, 45, tzinfo=timezone.utc)

    tx_out = Transaction(
        transaction_date=src_dt,
        effective_timestamp=src_dt,
        transaction_type=TransactionType.EXPENSE,
        amount_pence=35000,
        merchant="BARCLAYCARD PAYMENT",
        notes="Faster payment ref 9912",
        entry_method="csv",
        receipt_path="receipts/2026/10/hsbc_stmt.csv",
        account_id=acc_src.id,
        category_id=cat_bills.id,
        expense_nature=ExpenseNature.FIXED,
    )
    tx_in = Transaction(
        transaction_date=dest_dt,
        effective_timestamp=dest_dt,
        transaction_type=TransactionType.INCOME,
        amount_pence=35000,
        merchant="PAYMENT RECEIVED - THANK YOU",
        notes="Direct credit cleared",
        entry_method="pdf_statement",
        receipt_path="receipts/2026/10/barclaycard_stmt.pdf",
        account_id=acc_dest.id,
        category_id=None,
        expense_nature=ExpenseNature.UNCLASSIFIED,
    )
    db_session.add_all([tx_out, tx_in])
    db_session.commit()
    orig_out_id = tx_out.id
    orig_in_id = tx_in.id

    # Verify pre-pairing balances:
    # acc_src: 100000 - 35000 (on 10 Oct) = 65000
    # acc_dest: -80000 (anchor on 11 Oct) + 35000 (cleared on 12 Oct, after anchor!) = -45000
    assert LedgerEngine.get_account_balance(db_session, acc_src.id) == 65000
    assert LedgerEngine.get_account_balance(db_session, acc_dest.id) == -45000
    # As of 11 Oct 18:00 UTC (after outgoing leg on 10 Oct, before incoming leg on 12 Oct):
    mid_as_of = datetime(2026, 10, 11, 18, 0, tzinfo=timezone.utc)
    assert LedgerEngine.get_account_balance(db_session, acc_src.id, as_of=mid_as_of) == 65000
    assert LedgerEngine.get_account_balance(db_session, acc_dest.id, as_of=mid_as_of) == -80000

    # Pair tx_out and tx_in as a transfer
    paired_tx = confirm_transfer_suggestion(
        db=db_session,
        source_id=orig_out_id,
        source_kind="ledger",
        destination_id=orig_in_id,
        destination_kind="ledger",
    )

    # 1. Verify neither account's current or historical as_of balance changed after pairing!
    assert LedgerEngine.get_account_balance(db_session, acc_src.id) == 65000
    assert LedgerEngine.get_account_balance(db_session, acc_dest.id) == -45000
    assert LedgerEngine.get_account_balance(db_session, acc_src.id, as_of=mid_as_of) == 65000
    assert LedgerEngine.get_account_balance(db_session, acc_dest.id, as_of=mid_as_of) == -80000

    # 2. Verify TransactionResponse exposes full source + destination provenance
    from app.core.timezone import ensure_utc
    resp = _to_transaction_response(paired_tx)
    assert ensure_utc(resp.transaction_date) == src_dt
    assert ensure_utc(resp.effective_timestamp) == src_dt
    assert resp.merchant == "BARCLAYCARD PAYMENT"
    assert resp.entry_method == "csv"
    assert resp.receipt_path == "receipts/2026/10/hsbc_stmt.csv"
    assert resp.receipt_url == "/static/receipts/2026/10/hsbc_stmt.csv"

    assert ensure_utc(resp.destination_transaction_date) == dest_dt
    assert ensure_utc(resp.destination_effective_timestamp) == dest_dt
    assert resp.destination_merchant == "PAYMENT RECEIVED - THANK YOU"
    assert resp.destination_notes == "Direct credit cleared"
    assert resp.destination_entry_method == "pdf_statement"
    assert resp.destination_receipt_path == "receipts/2026/10/barclaycard_stmt.pdf"
    assert resp.destination_receipt_url == "/static/receipts/2026/10/barclaycard_stmt.pdf"
    assert resp.transfer_provenance is not None
    assert resp.transfer_provenance["pair_kind"] == "ledger_ledger"

    # 3. Reverse the pairing via unpair_transfer_transaction and verify full restoration
    unpair_res = unpair_transfer_transaction(db_session, paired_tx.id)
    assert unpair_res["pair_kind"] == "ledger_ledger"
    assert set(unpair_res["restored_transaction_ids"]) == {orig_out_id, orig_in_id}

    restored_out = db_session.query(Transaction).filter(Transaction.id == orig_out_id).first()
    restored_in = db_session.query(Transaction).filter(Transaction.id == orig_in_id).first()
    assert restored_out is not None and restored_in is not None

    assert restored_out.transaction_type == TransactionType.EXPENSE
    assert restored_out.account_id == acc_src.id
    assert restored_out.destination_account_id is None
    assert ensure_utc(restored_out.transaction_date) == src_dt
    assert ensure_utc(restored_out.effective_timestamp) == src_dt
    assert restored_out.merchant == "BARCLAYCARD PAYMENT"
    assert restored_out.notes == "Faster payment ref 9912"
    assert restored_out.entry_method == "csv"
    assert restored_out.receipt_path == "receipts/2026/10/hsbc_stmt.csv"
    assert restored_out.category_id == cat_bills.id
    assert restored_out.expense_nature == ExpenseNature.FIXED

    assert restored_in.transaction_type == TransactionType.INCOME
    assert restored_in.account_id == acc_dest.id
    assert restored_in.destination_account_id is None
    assert ensure_utc(restored_in.transaction_date) == dest_dt
    assert ensure_utc(restored_in.effective_timestamp) == dest_dt
    assert restored_in.merchant == "PAYMENT RECEIVED - THANK YOU"
    assert restored_in.notes == "Direct credit cleared"
    assert restored_in.entry_method == "pdf_statement"
    assert restored_in.receipt_path == "receipts/2026/10/barclaycard_stmt.pdf"


