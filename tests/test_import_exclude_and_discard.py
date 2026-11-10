"""
Regression tests for candidate exclusion and whole-import discard:
1. Exclude single candidate via DELETE /api/staging/{id}:
   - Discards that candidate from the import, persists status as REJECTED.
   - Queue count reflects exclusion immediately.
   - Preserves shared source file while any sibling candidate remains pending.
   - Cleans up shared source file only when no pending sibling needs it.
   - Cannot discard an already approved item (returns 400).
2. Discard whole import via POST /api/staging/import-commit (action: discard_all):
   - Discards all candidates belonging to the import.
   - Persists discards so they cannot be approved from the Review Queue.
   - Cleans up shared staging files when no pending items remain.
   - If partial items were already approved/committed, preserves committed ledger
     transactions and archived receipts, discarding only unresolved candidates,
     with clear explanation in the response.
3. Profile isolation:
   - Staging records and discards remain strictly isolated across profiles.
"""

import json
import pytest
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from app.main import app
from app.database import get_db
from app.models import (
    Base, Account, AccountType, Transaction, StagingItem, StagingStatus
)
from app.core.staging import discard_staging_item, approve_staging_item
from app.config import DATA_DIR
from tests.test_profiles import isolated_profiles_env


@pytest.fixture
def import_client(tmp_path):
    db_file = tmp_path / "test_import_actions.db"
    engine = create_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)

    def override_get_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)

    # Create test account
    acc_resp = client.post("/api/accounts", json={
        "name": "Main Checking",
        "account_type": "current",
        "starting_balance": 1500.0,
        "currency": "GBP"
    })
    assert acc_resp.status_code == 201
    account_id = acc_resp.json()["id"]

    try:
        yield client, SessionLocal, account_id, tmp_path
    finally:
        app.dependency_overrides.clear()


def test_exclude_single_candidate_and_shared_file_lifecycle(import_client):
    client, SessionLocal, account_id, tmp_path = import_client

    # Upload multi-row CSV statement
    csv_content = b"Date,Merchant,Amount\n2026-10-18,Coffee Roaster,4.50\n2026-10-19,Bookstore,18.99\n"
    upload_resp = client.post(
        "/api/staging/import-file",
        files={"file": ("expenses.csv", csv_content, "text/csv")},
        data={"account_id": str(account_id)}
    )
    assert upload_resp.status_code == 201
    import_data = upload_resp.json()
    items = import_data["items"]
    assert len(items) == 2

    item1_id = items[0]["id"]
    item2_id = items[1]["id"]

    # Initial pending count is 2
    count_resp = client.get("/api/staging/count")
    assert count_resp.status_code == 200
    assert count_resp.json()["pending_count"] == 2

    # Check shared staging file
    db = SessionLocal()
    stg1 = db.query(StagingItem).filter(StagingItem.id == item1_id).first()
    assert stg1.temp_file_path is not None
    p = Path(stg1.temp_file_path)
    file_path = p if p.is_absolute() else DATA_DIR / stg1.temp_file_path
    assert file_path.exists(), "Source staging file must exist initially"
    db.close()

    # 1. Exclude Item 1 via DELETE /api/staging/{id}
    del_resp = client.delete(f"/api/staging/{item1_id}")
    assert del_resp.status_code == 204

    # DB status must be REJECTED
    db = SessionLocal()
    stg1 = db.query(StagingItem).filter(StagingItem.id == item1_id).first()
    assert stg1.status == StagingStatus.REJECTED

    # Sibling Item 2 is still PENDING -> shared staging file MUST BE PRESERVED
    stg2 = db.query(StagingItem).filter(StagingItem.id == item2_id).first()
    assert stg2.status == StagingStatus.PENDING
    assert file_path.exists(), "Shared source file must NOT be deleted while sibling item is pending"
    db.close()

    # Queue count immediately dropped to 1
    count_resp2 = client.get("/api/staging/count")
    assert count_resp2.json()["pending_count"] == 1

    # Attempting to approve rejected Item 1 must fail
    app_resp = client.post(f"/api/staging/{item1_id}/approve")
    assert app_resp.status_code == 400

    # 2. Exclude Item 2 (the last pending sibling referencing the file)
    del_resp2 = client.delete(f"/api/staging/{item2_id}")
    assert del_resp2.status_code == 204

    # Staging queue count dropped to 0
    count_resp3 = client.get("/api/staging/count")
    assert count_resp3.json()["pending_count"] == 0

    # Now that NO pending siblings need it, the temporary staging file is cleaned up safely
    assert not file_path.exists(), "Temporary staging file must be unlinked when all siblings are resolved"


def test_exclude_already_approved_item_fails(import_client):
    client, SessionLocal, account_id, tmp_path = import_client

    # Upload single item
    csv_content = b"Date,Merchant,Amount\n2026-10-20,Hardware Store,25.00\n"
    upload_resp = client.post(
        "/api/staging/import-file",
        files={"file": ("single.csv", csv_content, "text/csv")},
        data={"account_id": str(account_id)}
    )
    assert upload_resp.status_code == 201
    item_id = upload_resp.json()["items"][0]["id"]

    # Approve item into ledger
    app_resp = client.post(f"/api/staging/{item_id}/approve")
    assert app_resp.status_code == 200

    # Attempt to discard the approved item
    del_resp = client.delete(f"/api/staging/{item_id}")
    assert del_resp.status_code == 400
    assert "already been approved" in del_resp.json()["detail"]

    # Verify item is still approved in DB and transaction exists in ledger
    db = SessionLocal()
    stg = db.query(StagingItem).filter(StagingItem.id == item_id).first()
    assert stg.status == StagingStatus.APPROVED
    tx_count = db.query(Transaction).count()
    assert tx_count == 1
    db.close()


def test_discard_whole_import_endpoint(import_client):
    client, SessionLocal, account_id, tmp_path = import_client

    csv_content = b"Date,Merchant,Amount\n2026-10-18,Store A,10.00\n2026-10-19,Store B,20.00\n2026-10-20,Store C,30.00\n"
    upload_resp = client.post(
        "/api/staging/import-file",
        files={"file": ("bulk.csv", csv_content, "text/csv")},
        data={"account_id": str(account_id)}
    )
    assert upload_resp.status_code == 201
    import_data = upload_resp.json()
    batch_id = import_data["batch_id"]
    items = import_data["items"]
    item_ids = [it["id"] for it in items]

    # Queue count is 3
    assert client.get("/api/staging/count").json()["pending_count"] == 3

    # Discard whole import
    discard_resp = client.post("/api/staging/import-commit", json={
        "batch_id": batch_id,
        "action": "discard_all",
        "items": [{"id": i} for i in item_ids]
    })
    assert discard_resp.status_code == 200
    res = discard_resp.json()
    assert res["action"] == "discard_all"
    assert res["discarded_count"] == 3
    assert res["already_committed_count"] == 0
    assert "Discarded all 3 candidate(s)" in res["message"]

    # Queue count is now 0
    assert client.get("/api/staging/count").json()["pending_count"] == 0

    # None can be approved from review queue
    for i in item_ids:
        r = client.post(f"/api/staging/{i}/approve")
        assert r.status_code == 400


def test_discard_whole_import_with_partial_prior_commitment(import_client):
    client, SessionLocal, account_id, tmp_path = import_client

    csv_content = b"Date,Merchant,Amount\n2026-10-18,Commited Store,12.50\n2026-10-19,Unresolved A,22.00\n2026-10-20,Unresolved B,32.00\n"
    upload_resp = client.post(
        "/api/staging/import-file",
        files={"file": ("mixed.csv", csv_content, "text/csv")},
        data={"account_id": str(account_id)}
    )
    assert upload_resp.status_code == 201
    import_data = upload_resp.json()
    batch_id = import_data["batch_id"]
    items = import_data["items"]
    committed_id = items[0]["id"]
    unresolved_ids = [items[1]["id"], items[2]["id"]]

    # Commit item 0 to the ledger
    app_resp = client.post(f"/api/staging/{committed_id}/approve")
    assert app_resp.status_code == 200
    tx_id = app_resp.json()["transaction_id"]

    # Now discard the whole import
    discard_resp = client.post("/api/staging/import-commit", json={
        "batch_id": batch_id,
        "action": "discard_all",
        "items": [{"id": it["id"]} for it in items]
    })
    assert discard_resp.status_code == 200
    res = discard_resp.json()
    assert res["discarded_count"] == 2
    assert res["already_committed_count"] == 1
    assert "previously committed" in res["message"]

    # Verify committed transaction still exists in ledger
    db = SessionLocal()
    tx = db.query(Transaction).filter(Transaction.id == tx_id).first()
    assert tx is not None
    assert tx.merchant == "Commited Store"

    # Committed staging item status is still APPROVED
    stg0 = db.query(StagingItem).filter(StagingItem.id == committed_id).first()
    assert stg0.status == StagingStatus.APPROVED

    # Unresolved staging items are REJECTED
    for uid in unresolved_ids:
        stg = db.query(StagingItem).filter(StagingItem.id == uid).first()
        assert stg.status == StagingStatus.REJECTED
    db.close()


def test_idempotent_repeated_discards(import_client):
    client, SessionLocal, account_id, tmp_path = import_client

    csv_content = b"Date,Merchant,Amount\n2026-10-21,Idempotent Cafe,3.20\n"
    upload_resp = client.post(
        "/api/staging/import-file",
        files={"file": ("single.csv", csv_content, "text/csv")},
        data={"account_id": str(account_id)}
    )
    assert upload_resp.status_code == 201
    item_id = upload_resp.json()["items"][0]["id"]

    # Discard 1st time
    r1 = client.delete(f"/api/staging/{item_id}")
    assert r1.status_code == 204

    # Discard 2nd time (should be idempotent 204)
    r2 = client.delete(f"/api/staging/{item_id}")
    assert r2.status_code == 204


def test_delete_nonexistent_item_404(import_client):
    client, _, _, _ = import_client
    resp = client.delete("/api/staging/999999")
    assert resp.status_code == 404


def test_profile_isolation_for_discards(isolated_profiles_env):
    from app.core import profiles as profiles_module
    prof_b = profiles_module.create_profile("Workspace Beta")

    client = TestClient(app)

    # 1. Create account in Default and upload 2 items (IDs 1, 2)
    acc_def = client.post(
        "/api/accounts",
        headers={"X-Profile-ID": "default"},
        json={"name": "Default Account", "account_type": "current", "starting_balance": 1000.0, "currency": "GBP"}
    ).json()

    up_def = client.post(
        "/api/staging/import-file",
        headers={"X-Profile-ID": "default"},
        files={"file": ("default.csv", b"Date,Merchant,Amount\n2026-10-22,Default Cafe 1,5.00\n2026-10-22,Default Cafe 2,10.00\n", "text/csv")},
        data={"account_id": str(acc_def["id"])}
    ).json()
    item_def_id2 = up_def["items"][1]["id"]  # ID 2 in Default

    # 2. Create account in Workspace Beta and upload 1 item (ID 1 in Beta)
    acc_b = client.post(
        "/api/accounts",
        headers={"X-Profile-ID": prof_b.id},
        json={"name": "Beta Account", "account_type": "current", "starting_balance": 2000.0, "currency": "GBP"}
    ).json()

    up_b = client.post(
        "/api/staging/import-file",
        headers={"X-Profile-ID": prof_b.id},
        files={"file": ("beta.csv", b"Date,Merchant,Amount\n2026-10-22,Beta Store,15.00\n", "text/csv")},
        data={"account_id": str(acc_b["id"])}
    ).json()
    item_b_id = up_b["items"][0]["id"]  # ID 1 in Beta

    # Beta's pending count is 1; Default's pending count is 2
    assert client.get("/api/staging/count", headers={"X-Profile-ID": "default"}).json()["pending_count"] == 2
    assert client.get("/api/staging/count", headers={"X-Profile-ID": prof_b.id}).json()["pending_count"] == 1

    # Attempting to delete Default's Item 2 using Workspace Beta profile header must return 404 (isolated database)
    cross_del = client.delete(f"/api/staging/{item_def_id2}", headers={"X-Profile-ID": prof_b.id})
    assert cross_del.status_code == 404

    # Default items are still both pending in Default profile
    assert client.get("/api/staging/count", headers={"X-Profile-ID": "default"}).json()["pending_count"] == 2

    # Discard Beta's item in Beta
    del_b = client.delete(f"/api/staging/{item_b_id}", headers={"X-Profile-ID": prof_b.id})
    assert del_b.status_code == 204

    # Beta's pending count is now 0; Default's pending count is still 2
    assert client.get("/api/staging/count", headers={"X-Profile-ID": prof_b.id}).json()["pending_count"] == 0
    assert client.get("/api/staging/count", headers={"X-Profile-ID": "default"}).json()["pending_count"] == 2

