import pytest
from app.models import AccountType, TransactionType, ExpenseNature

def test_create_and_list_expense_with_category_inheritance(client, db_session):
    # 1. Create an account
    acc_res = client.post("/api/accounts", json={
        "name": "Barclays Checking",
        "account_type": "current",
        "starting_balance": 100.00
    })
    assert acc_res.status_code == 201
    account_id = acc_res.json()["id"]

    # 2. Create a category with default_expense_nature = 'fixed'
    cat_res = client.post("/api/categories", json={
        "name": "Rent & Housing",
        "color": "#6366F1",
        "default_expense_nature": "fixed"
    })
    assert cat_res.status_code == 201
    category_id = cat_res.json()["id"]

    # 3. Create expense without specifying expense_nature -> should inherit 'fixed'
    tx1_res = client.post("/api/transactions", json={
        "transaction_type": "expense",
        "amount": 45.50,
        "merchant": "Landlord Ltd",
        "account_id": account_id,
        "category_id": category_id,
        "notes": "Monthly rent installment"
    })
    assert tx1_res.status_code == 201
    data1 = tx1_res.json()
    assert data1["amount_pence"] == 4550
    assert data1["amount_pounds"] == 45.5
    assert data1["formatted_amount"] == "£45.50"
    assert data1["expense_nature"] == "fixed"
    assert data1["account_name"] == "Barclays Checking"
    assert data1["category_name"] == "Rent & Housing"

    # 4. Create another expense with explicit override -> should use 'variable'
    tx2_res = client.post("/api/transactions", json={
        "transaction_type": "expense",
        "amount": 12.00,
        "merchant": "Repairs",
        "account_id": account_id,
        "category_id": category_id,
        "expense_nature": "variable"
    })
    assert tx2_res.status_code == 201
    data2 = tx2_res.json()
    assert data2["expense_nature"] == "variable"

    # Check updated balance: 100.00 - 45.50 - 12.00 = 42.50
    acc_check = client.get(f"/api/accounts/{account_id}").json()
    assert acc_check["current_balance_pence"] == 4250
    assert acc_check["formatted_balance"] == "£42.50"

def test_transfer_atomic_lifecycle(client, db_session):
    # 1. Create source and dest accounts
    src_res = client.post("/api/accounts", json={
        "name": "NatWest Current",
        "account_type": "current",
        "starting_balance": 500.00
    })
    assert src_res.status_code == 201
    src_id = src_res.json()["id"]

    dest_res = client.post("/api/accounts", json={
        "name": "Marcus Savings",
        "account_type": "savings",
        "starting_balance": 1000.00
    })
    assert dest_res.status_code == 201
    dest_id = dest_res.json()["id"]

    # 2. Reject transfer if source == dest
    fail_res = client.post("/api/transactions", json={
        "transaction_type": "transfer",
        "amount": 50.00,
        "account_id": src_id,
        "destination_account_id": src_id
    })
    assert fail_res.status_code == 400
    assert "distinct" in fail_res.json()["detail"].lower()

    # 3. Create valid transfer of £200.00
    tx_res = client.post("/api/transactions", json={
        "transaction_type": "transfer",
        "amount": 200.00,
        "account_id": src_id,
        "destination_account_id": dest_id,
        "notes": "Emergency fund deposit"
    })
    assert tx_res.status_code == 201
    tx_data = tx_res.json()
    tx_id = tx_data["id"]
    assert tx_data["amount_pence"] == 20000
    assert tx_data["destination_account_id"] == dest_id
    assert tx_data["destination_account_name"] == "Marcus Savings"

    # 4. Verify balances: src = 300.00, dest = 1200.00
    src_bal = client.get(f"/api/accounts/{src_id}").json()
    dest_bal = client.get(f"/api/accounts/{dest_id}").json()
    assert src_bal["current_balance_pence"] == 30000
    assert dest_bal["current_balance_pence"] == 120000

    # 5. Update transfer amount to £100.00
    upd_res = client.put(f"/api/transactions/{tx_id}", json={
        "amount": 100.00
    })
    assert upd_res.status_code == 200
    assert upd_res.json()["amount_pence"] == 10000

    # Check updated balances: src = 400.00, dest = 1100.00
    src_bal = client.get(f"/api/accounts/{src_id}").json()
    dest_bal = client.get(f"/api/accounts/{dest_id}").json()
    assert src_bal["current_balance_pence"] == 40000
    assert dest_bal["current_balance_pence"] == 110000

    # 6. Delete transfer -> restores both balances atomically
    del_res = client.delete(f"/api/transactions/{tx_id}")
    assert del_res.status_code == 204

    src_bal = client.get(f"/api/accounts/{src_id}").json()
    dest_bal = client.get(f"/api/accounts/{dest_id}").json()
    assert src_bal["current_balance_pence"] == 50000
    assert dest_bal["current_balance_pence"] == 100000

def test_transaction_search_and_filtering(client, db_session):
    acc1 = client.post("/api/accounts", json={"name": "Checking", "account_type": "current", "starting_balance": 100}).json()
    acc2 = client.post("/api/accounts", json={"name": "Savings", "account_type": "savings", "starting_balance": 100}).json()
    cat_food = client.post("/api/categories", json={"name": "Food & Dining", "default_expense_nature": "variable"}).json()
    cat_bills = client.post("/api/categories", json={"name": "Bills", "default_expense_nature": "fixed"}).json()

    # Create transactions
    client.post("/api/transactions", json={
        "transaction_type": "expense",
        "amount": 15.00,
        "merchant": "Pret A Manger",
        "account_id": acc1["id"],
        "category_id": cat_food["id"],
        "notes": "Lunch with team"
    })
    client.post("/api/transactions", json={
        "transaction_type": "expense",
        "amount": 80.00,
        "merchant": "Octopus Energy",
        "account_id": acc1["id"],
        "category_id": cat_bills["id"],
        "notes": "Electricity bill"
    })
    client.post("/api/transactions", json={
        "transaction_type": "income",
        "amount": 2500.00,
        "merchant": "Employer Payroll",
        "account_id": acc1["id"],
        "notes": "Monthly salary"
    })
    client.post("/api/transactions", json={
        "transaction_type": "transfer",
        "amount": 500.00,
        "account_id": acc1["id"],
        "destination_account_id": acc2["id"],
        "notes": "Savings allocation"
    })

    # Test total list count
    all_res = client.get("/api/transactions").json()
    assert all_res["total"] == 4
    assert len(all_res["items"]) == 4

    # Test search by query `q`
    search_res = client.get("/api/transactions?q=pret").json()
    assert search_res["total"] == 1
    assert search_res["items"][0]["merchant"] == "Pret A Manger"

    search_notes = client.get("/api/transactions?q=salary").json()
    assert search_notes["total"] == 1
    assert search_notes["items"][0]["merchant"] == "Employer Payroll"

    # Test filter by category
    cat_res = client.get(f"/api/transactions?category_id={cat_bills['id']}").json()
    assert cat_res["total"] == 1
    assert cat_res["items"][0]["merchant"] == "Octopus Energy"

    # Test filter by account (acc2 should find the transfer where it's the destination!)
    acc2_txs = client.get(f"/api/transactions?account_id={acc2['id']}").json()
    assert acc2_txs["total"] == 1
    assert acc2_txs["items"][0]["transaction_type"] == "transfer"
    assert acc2_txs["items"][0]["destination_account_id"] == acc2["id"]

    # Test filter by type
    income_txs = client.get("/api/transactions?transaction_type=income").json()
    assert income_txs["total"] == 1
    assert income_txs["items"][0]["merchant"] == "Employer Payroll"

    # Test filter by expense nature
    fixed_txs = client.get("/api/transactions?expense_nature=fixed").json()
    assert fixed_txs["total"] == 1
    assert fixed_txs["items"][0]["merchant"] == "Octopus Energy"

    # Test pagination
    paged = client.get("/api/transactions?limit=2&offset=0").json()
    assert paged["total"] == 4
    assert len(paged["items"]) == 2
    assert paged["limit"] == 2
    assert paged["offset"] == 0

def test_transaction_validation_and_edge_cases(client, db_session):
    acc = client.post("/api/accounts", json={"name": "Checking", "account_type": "current"}).json()
    cat = client.post("/api/categories", json={"name": "Groceries", "default_expense_nature": "variable"}).json()

    # Zero or negative amount rejected
    res_zero = client.post("/api/transactions", json={
        "transaction_type": "expense",
        "amount": 0,
        "merchant": "Free store",
        "account_id": acc["id"]
    })
    assert res_zero.status_code == 422 or res_zero.status_code == 400

    res_neg = client.post("/api/transactions", json={
        "transaction_type": "expense",
        "amount": -10.00,
        "merchant": "Negative store",
        "account_id": acc["id"]
    })
    assert res_neg.status_code == 422 or res_neg.status_code == 400

    # Non-existent account
    res_no_acc = client.post("/api/transactions", json={
        "transaction_type": "expense",
        "amount": 10.00,
        "merchant": "Test",
        "account_id": 99999
    })
    assert res_no_acc.status_code == 404

    # Create valid tx
    create_res = client.post("/api/transactions", json={
        "transaction_type": "expense",
        "amount": 25.00,
        "merchant": "Waitrose",
        "account_id": acc["id"],
        "category_id": cat["id"]
    })
    assert create_res.status_code == 201
    tx_id = create_res.json()["id"]

    # Unlink category (set category_id = None)
    upd_res = client.put(f"/api/transactions/{tx_id}", json={
        "category_id": None
    })
    assert upd_res.status_code == 200
    assert upd_res.json()["category_id"] is None
    assert upd_res.json()["category_name"] is None

    # Delete transaction
    del_res = client.delete(f"/api/transactions/{tx_id}")
    assert del_res.status_code == 204

    # 404 on deleting already deleted transaction
    del_again = client.delete(f"/api/transactions/{tx_id}")
    assert del_again.status_code == 404

