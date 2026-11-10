import pytest
from fastapi.testclient import TestClient

def test_edit_posted_expense_transaction(client: TestClient):
    """Verifies editing a posted expense transaction and automatic balance recalculation."""
    # 1. Create account
    acc_res = client.post("/api/accounts", json={
        "name": "Current Account",
        "account_type": "current",
        "currency": "GBP",
        "starting_balance": 500.00,
        "color": "#3B82F6"
    })
    assert acc_res.status_code == 201
    acc_id = acc_res.json()["id"]

    # 2. Create category
    cat_res = client.post("/api/categories", json={
        "name": "Utilities",
        "color": "#F59E0B",
        "default_expense_nature": "fixed"
    })
    assert cat_res.status_code == 201
    cat_id = cat_res.json()["id"]

    # 3. Post expense of £50.00
    tx_res = client.post("/api/transactions", json={
        "account_id": acc_id,
        "transaction_type": "expense",
        "amount": 50.00,
        "merchant": "Electric Co",
        "category_id": cat_id,
        "expense_nature": "fixed"
    })
    assert tx_res.status_code == 201
    tx_id = tx_res.json()["id"]

    # Check account balance: 500 - 50 = 450
    bal_res = client.get(f"/api/accounts/{acc_id}")
    assert bal_res.json()["current_balance_pence"] == 45000

    # 4. Edit transaction: increase amount to £80.00, change merchant, notes
    update_res = client.put(f"/api/transactions/{tx_id}", json={
        "amount": 80.00,
        "merchant": "Electric & Gas Co",
        "notes": "Adjusted billing statement"
    })
    assert update_res.status_code == 200
    updated_data = update_res.json()
    assert updated_data["amount_pounds"] == 80.00
    assert updated_data["merchant"] == "Electric & Gas Co"
    assert updated_data["notes"] == "Adjusted billing statement"

    # Check recalculated balance: 500 - 80 = 420
    bal_res2 = client.get(f"/api/accounts/{acc_id}")
    assert bal_res2.json()["current_balance_pence"] == 42000


def test_edit_posted_transfer_transaction(client: TestClient):
    """Verifies editing a posted transfer updates both source and destination balances atomically."""
    # 1. Create two accounts
    acc1_res = client.post("/api/accounts", json={
        "name": "Checking",
        "account_type": "current",
        "currency": "GBP",
        "starting_balance": 1000.00
    })
    acc1_id = acc1_res.json()["id"]

    acc2_res = client.post("/api/accounts", json={
        "name": "Savings",
        "account_type": "savings",
        "currency": "GBP",
        "starting_balance": 500.00
    })
    acc2_id = acc2_res.json()["id"]

    # 2. Transfer £200 from Checking to Savings
    tx_res = client.post("/api/transactions", json={
        "account_id": acc1_id,
        "destination_account_id": acc2_id,
        "transaction_type": "transfer",
        "amount": 200.00,
        "merchant": "Transfer to Savings"
    })
    assert tx_res.status_code == 201
    tx_id = tx_res.json()["id"]

    # Checking: 1000 - 200 = 800; Savings: 500 + 200 = 700
    assert client.get(f"/api/accounts/{acc1_id}").json()["current_balance_pence"] == 80000
    assert client.get(f"/api/accounts/{acc2_id}").json()["current_balance_pence"] == 70000

    # 3. Edit transfer: change amount to £350
    update_res = client.put(f"/api/transactions/{tx_id}", json={
        "amount": 350.00
    })
    assert update_res.status_code == 200
    assert update_res.json()["amount_pounds"] == 350.00

    # Checking: 1000 - 350 = 650; Savings: 500 + 350 = 850
    assert client.get(f"/api/accounts/{acc1_id}").json()["current_balance_pence"] == 65000
    assert client.get(f"/api/accounts/{acc2_id}").json()["current_balance_pence"] == 85000


def test_convert_transaction_types_and_validations(client: TestClient):
    """Verifies converting between normal and transfer transactions, and validation rules."""
    acc1 = client.post("/api/accounts", json={
        "name": "Acc A", "account_type": "current", "currency": "GBP", "starting_balance": 100.00
    }).json()["id"]

    acc2 = client.post("/api/accounts", json={
        "name": "Acc B", "account_type": "current", "currency": "GBP", "starting_balance": 100.00
    }).json()["id"]

    # 1. Create expense
    tx = client.post("/api/transactions", json={
        "account_id": acc1,
        "transaction_type": "expense",
        "amount": 25.00,
        "merchant": "Coffee Shop"
    }).json()

    # 2. Cannot convert to transfer without destination account
    fail_res = client.put(f"/api/transactions/{tx['id']}", json={
        "transaction_type": "transfer"
    })
    assert fail_res.status_code == 400

    # 3. Cannot transfer to same account
    fail_self = client.put(f"/api/transactions/{tx['id']}", json={
        "transaction_type": "transfer",
        "destination_account_id": acc1
    })
    assert fail_self.status_code == 400

    # 4. Successfully convert to transfer
    conv_res = client.put(f"/api/transactions/{tx['id']}", json={
        "transaction_type": "transfer",
        "destination_account_id": acc2
    })
    assert conv_res.status_code == 200
    assert conv_res.json()["transaction_type"] == "transfer"
    assert conv_res.json()["destination_account_id"] == acc2

    # 5. Successfully convert back to expense
    conv_back = client.put(f"/api/transactions/{tx['id']}", json={
        "transaction_type": "expense",
        "merchant": "Office Supplies"
    })
    assert conv_back.status_code == 200
    assert conv_back.json()["transaction_type"] == "expense"
    assert conv_back.json()["destination_account_id"] is None


def test_account_edit_and_archive(client: TestClient):
    """Verifies editing account metadata, archiving, and reactivating without loss of transaction history."""
    # 1. Create account
    acc = client.post("/api/accounts", json={
        "name": "Old Credit Card",
        "account_type": "credit_card",
        "currency": "GBP",
        "starting_balance": 0.00,
        "color": "#EC4899"
    }).json()
    acc_id = acc["id"]

    # 2. Post a transaction
    client.post("/api/transactions", json={
        "account_id": acc_id,
        "transaction_type": "expense",
        "amount": 45.00,
        "merchant": "Train Ticket"
    })

    # 3. Update account metadata
    edit_res = client.put(f"/api/accounts/{acc_id}", json={
        "name": "Primary Credit Card",
        "color": "#10B981"
    })
    assert edit_res.status_code == 200
    assert edit_res.json()["name"] == "Primary Credit Card"
    assert edit_res.json()["color"] == "#10B981"

    # 4. Archive account
    arch_res = client.delete(f"/api/accounts/{acc_id}")
    assert arch_res.status_code == 204

    # Default list should omit it
    active_accs = client.get("/api/accounts").json()
    assert all(a["id"] != acc_id for a in active_accs)

    # List with include_inactive=true should include it
    all_accs = client.get("/api/accounts?include_inactive=true").json()
    archived_acc = next(a for a in all_accs if a["id"] == acc_id)
    assert archived_acc["is_active"] is False

    # Historical transactions must still exist and be readable
    txs = client.get(f"/api/transactions?account_id={acc_id}").json()["items"]
    assert len(txs) == 1
    assert txs[0]["merchant"] == "Train Ticket"
    assert txs[0]["amount_pounds"] == 45.00

    # 5. Reactivate account
    react_res = client.put(f"/api/accounts/{acc_id}", json={
        "is_active": True
    })
    assert react_res.status_code == 200
    assert react_res.json()["is_active"] is True

    # Account is back in active list
    active_now = client.get("/api/accounts").json()
    assert any(a["id"] == acc_id for a in active_now)


def test_category_management_and_audit_protection(client: TestClient):
    """Verifies category CRUD, transaction usage counting, and soft-delete protection."""
    # 1. Create category
    cat_res = client.post("/api/categories", json={
        "name": "Dining",
        "color": "#EF4444",
        "default_expense_nature": "variable"
    })
    assert cat_res.status_code == 201
    cat_id = cat_res.json()["id"]
    assert cat_res.json()["transaction_count"] == 0

    # 2. Create account & post transaction using category
    acc = client.post("/api/accounts", json={
        "name": "Current",
        "account_type": "current",
        "currency": "GBP",
        "starting_balance": 200.00
    }).json()

    tx = client.post("/api/transactions", json={
        "account_id": acc["id"],
        "transaction_type": "expense",
        "amount": 32.50,
        "merchant": "Italian Restaurant",
        "category_id": cat_id
    }).json()

    # 3. Verify category lists transaction count
    cat_detail = client.get(f"/api/categories/{cat_id}").json()
    assert cat_detail["transaction_count"] == 1

    # 4. Edit category name and nature
    edit_res = client.put(f"/api/categories/{cat_id}", json={
        "name": "Dining & Takeout",
        "default_expense_nature": "variable"
    })
    assert edit_res.status_code == 200
    assert edit_res.json()["name"] == "Dining & Takeout"

    # Transaction reflects updated category
    tx_check = client.get(f"/api/transactions/{tx['id']}").json()
    assert tx_check["category_id"] == cat_id
    assert tx_check["category_name"] == "Dining & Takeout"

    # 5. Archive category
    del_res = client.delete(f"/api/categories/{cat_id}")
    assert del_res.status_code == 204

    # Default list excludes it
    active_cats = client.get("/api/categories").json()
    assert all(c["id"] != cat_id for c in active_cats)

    # Include inactive includes it
    all_cats = client.get("/api/categories?include_inactive=true").json()
    archived_cat = next(c for c in all_cats if c["id"] == cat_id)
    assert archived_cat["is_active"] is False

    # Historical transaction STILL retains category_id and category_name!
    tx_after_archive = client.get(f"/api/transactions/{tx['id']}").json()
    assert tx_after_archive["category_id"] == cat_id
    assert tx_after_archive["category_name"] == "Dining & Takeout"

    # 6. Re-creating category with same name reactivates it cleanly
    recreate_res = client.post("/api/categories", json={
        "name": "Dining & Takeout",
        "color": "#10B981"
    })
    assert recreate_res.status_code == 201
    assert recreate_res.json()["id"] == cat_id
    assert recreate_res.json()["is_active"] is True
    assert recreate_res.json()["color"] == "#10B981"


def test_account_permanent_deletion_impact_and_cascade(client: TestClient):
    """Verifies two-step account permanent deletion impact analysis and cascade erasure."""
    # 1. Create Account A and Account B
    acc_a = client.post("/api/accounts", json={
        "name": "Checking Account A",
        "account_type": "current",
        "currency": "GBP",
        "starting_balance": 1000.00
    }).json()["id"]

    acc_b = client.post("/api/accounts", json={
        "name": "Savings Account B",
        "account_type": "savings",
        "currency": "GBP",
        "starting_balance": 500.00
    }).json()["id"]

    # 2. Add standard transactions on A
    client.post("/api/transactions", json={
        "account_id": acc_a,
        "transaction_type": "expense",
        "amount": 20.00,
        "merchant": "Coffee"
    })
    client.post("/api/transactions", json={
        "account_id": acc_a,
        "transaction_type": "income",
        "amount": 100.00,
        "merchant": "Refund"
    })

    # 3. Add transfers involving A (one outbound, one inbound)
    client.post("/api/transactions", json={
        "account_id": acc_a,
        "destination_account_id": acc_b,
        "transaction_type": "transfer",
        "amount": 50.00,
        "merchant": "To Savings"
    })
    client.post("/api/transactions", json={
        "account_id": acc_b,
        "destination_account_id": acc_a,
        "transaction_type": "transfer",
        "amount": 30.00,
        "merchant": "From Savings"
    })

    # 4. Add a reconciliation snapshot on A
    snap_res = client.post(f"/api/accounts/{acc_a}/reconciliation/snapshots", json={
        "actual_balance": 1060.00,
        "notes": "Verified against statement"
    })
    assert snap_res.status_code == 201

    # 5. Check deletion impact endpoint
    impact_res = client.get(f"/api/accounts/{acc_a}/deletion-impact")
    assert impact_res.status_code == 200
    impact = impact_res.json()
    assert impact["account_name"] == "Checking Account A"
    assert impact["transaction_count"] == 2
    assert impact["transfer_count"] == 2
    assert impact["snapshot_count"] == 1

    # 6. Execute permanent deletion
    del_res = client.delete(f"/api/accounts/{acc_a}?permanent=true")
    assert del_res.status_code == 204

    # Account A is completely gone
    get_a = client.get(f"/api/accounts/{acc_a}")
    assert get_a.status_code == 404

    # Transactions referencing Account A are gone
    all_txs = client.get("/api/transactions").json()["items"]
    assert len(all_txs) == 0

    # Account B remains safe and intact
    get_b = client.get(f"/api/accounts/{acc_b}")
    assert get_b.status_code == 200
    assert get_b.json()["name"] == "Savings Account B"
    assert get_b.json()["current_balance_pence"] == 50000


def test_category_permanent_deletion_with_reassignment_protection(client: TestClient):
    """Verifies category permanent deletion mandates reassignment when transactions exist."""
    # 1. Create two categories
    cat1 = client.post("/api/categories", json={
        "name": "Vacation Travel",
        "color": "#3B82F6",
        "default_expense_nature": "variable"
    }).json()["id"]

    cat2 = client.post("/api/categories", json={
        "name": "General Transport",
        "color": "#10B981",
        "default_expense_nature": "fixed"
    }).json()["id"]

    acc = client.post("/api/accounts", json={
        "name": "Primary Current",
        "account_type": "current",
        "currency": "GBP",
        "starting_balance": 500.00
    }).json()["id"]

    # 2. Add 2 transactions referencing Vacation Travel
    tx1 = client.post("/api/transactions", json={
        "account_id": acc,
        "transaction_type": "expense",
        "amount": 150.00,
        "merchant": "Flight Booking",
        "category_id": cat1
    }).json()["id"]

    tx2 = client.post("/api/transactions", json={
        "account_id": acc,
        "transaction_type": "expense",
        "amount": 75.00,
        "merchant": "Hotel Stay",
        "category_id": cat1
    }).json()["id"]

    # 3. Check impact endpoint
    impact_res = client.get(f"/api/categories/{cat1}/deletion-impact")
    assert impact_res.status_code == 200
    assert impact_res.json()["transaction_count"] == 2

    # 4. Attempt permanent deletion WITHOUT reassignment -> Rejected with 400
    fail_del = client.delete(f"/api/categories/{cat1}?permanent=true")
    assert fail_del.status_code == 400
    assert "Reassign them to another active category" in fail_del.json()["detail"]

    # Category and transactions remain untouched
    assert client.get(f"/api/categories/{cat1}").status_code == 200
    assert client.get(f"/api/transactions/{tx1}").json()["category_id"] == cat1

    # 5. Permanent deletion WITH reassignment to cat2
    success_del = client.delete(f"/api/categories/{cat1}?permanent=true&reassign_to_id={cat2}")
    assert success_del.status_code == 204

    # Category 1 is permanently deleted
    assert client.get(f"/api/categories/{cat1}").status_code == 404

    # Transactions now safely point to Category 2 (General Transport)
    tx1_updated = client.get(f"/api/transactions/{tx1}").json()
    assert tx1_updated["category_id"] == cat2
    assert tx1_updated["category_name"] == "General Transport"

    tx2_updated = client.get(f"/api/transactions/{tx2}").json()
    assert tx2_updated["category_id"] == cat2
    assert tx2_updated["category_name"] == "General Transport"

    # 6. Category with 0 transactions can be permanently deleted directly
    cat_empty = client.post("/api/categories", json={
        "name": "Temporary Hobby",
        "color": "#F59E0B"
    }).json()["id"]
    empty_del = client.delete(f"/api/categories/{cat_empty}?permanent=true")
    assert empty_del.status_code == 204
    assert client.get(f"/api/categories/{cat_empty}").status_code == 404


