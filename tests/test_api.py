def test_health_check(client):
    res = client.get("/api/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "healthy"
    assert data["offline"] is True

def test_account_creation_and_balance(client):
    # 1. Create a Current Account
    payload = {
        "name": "Barclays Checking",
        "account_type": "current",
        "currency": "GBP",
        "color": "#10B981",
        "starting_balance": 1500.50
    }
    res = client.post("/api/accounts", json=payload)
    assert res.status_code == 201
    account = res.json()
    assert account["name"] == "Barclays Checking"
    assert account["account_type"] == "current"
    assert account["starting_balance_pence"] == 150050
    assert account["current_balance_pence"] == 150050
    assert account["formatted_balance"] == "£1,500.50"

    # 2. List accounts
    res = client.get("/api/accounts")
    assert res.status_code == 200
    accounts = res.json()
    assert len(accounts) == 1
    assert accounts[0]["id"] == account["id"]

def test_dashboard_summary_calculation(client):
    # Create checking account with £2000
    client.post("/api/accounts", json={
        "name": "Nationwide",
        "account_type": "current",
        "starting_balance": 2000.00
    })
    # Create credit card with -£500
    client.post("/api/accounts", json={
        "name": "Amex",
        "account_type": "credit_card",
        "starting_balance": -500.00
    })

    res = client.get("/api/dashboard/summary")
    assert res.status_code == 200
    data = res.json()
    assert data["total_liquid_pence"] == 200000
    assert data["total_debt_pence"] == 50000
    # Net worth = 200,000 - 50,000 = 150,000 (£1,500.00)
    assert data["net_worth_pence"] == 150000
    assert data["formatted_net_worth"] == "£1,500.00"

def test_category_with_expense_nature(client):
    # Create fixed category (Mortgage)
    res = client.post("/api/categories", json={
        "name": "Mortgage",
        "color": "#EF4444",
        "default_expense_nature": "fixed"
    })
    assert res.status_code == 201
    cat = res.json()
    assert cat["name"] == "Mortgage"
    assert cat["default_expense_nature"] == "fixed"

    # List categories
    res = client.get("/api/categories")
    assert res.status_code == 200
    cats = res.json()
    assert any(c["name"] == "Mortgage" and c["default_expense_nature"] == "fixed" for c in cats)

def test_spa_index_served(client):
    res = client.get("/")
    assert res.status_code == 200
    assert "Finance Hub" in res.text


def test_account_breakdown_depository_with_ground_truth_anchor(client, db_session):
    from datetime import datetime, timezone
    from app.models import Account, AccountType, AccountBalanceAnchor, Transaction, TransactionType

    acc = Account(
        name="Santander Current",
        account_type=AccountType.CURRENT,
        starting_balance_pence=100000,
        starting_balance_date=datetime(2026, 10, 1, 0, 0, tzinfo=timezone.utc)
    )
    db_session.add(acc)
    db_session.commit()

    # Ground-truth anchor on 15 Oct 2026: £1,200.00
    anchor = AccountBalanceAnchor(
        account_id=acc.id,
        balance_pence=120000,
        anchor_date=datetime(2026, 10, 15, 0, 0, tzinfo=timezone.utc),
        is_opening=False,
        notes="Bank statement confirmed"
    )
    db_session.add(anchor)

    # Post-anchor transactions
    # 1. Income +£50.00
    tx1 = Transaction(
        transaction_date=datetime(2026, 10, 18, 12, 0, tzinfo=timezone.utc),
        transaction_type=TransactionType.INCOME,
        amount_pence=5000,
        merchant="Client payment",
        account_id=acc.id
    )
    # 2. Expense -£20.00
    tx2 = Transaction(
        transaction_date=datetime(2026, 10, 20, 15, 30, tzinfo=timezone.utc),
        transaction_type=TransactionType.EXPENSE,
        amount_pence=2000,
        merchant="Grocery store",
        account_id=acc.id
    )
    db_session.add_all([tx1, tx2])
    db_session.commit()

    res = client.get(f"/api/accounts/{acc.id}/breakdown")
    assert res.status_code == 200, res.text
    data = res.json()

    assert data["account_id"] == acc.id
    assert data["account_name"] == "Santander Current"
    assert data["account_group"] == "Depository Accounts"
    assert data["current_balance_pence"] == 123000 # 120000 + 5000 - 2000
    assert data["formatted_current_balance"] == "£1,230.00"

    # Anchor checks
    assert data["anchor"]["has_anchor"] is True
    assert data["anchor"]["balance_pence"] == 120000
    assert data["anchor"]["formatted_balance"] == "£1,200.00"
    assert "15/10/2026" in data["anchor"]["anchor_date_local"]

    # Movement equation checks: anchor + movement == current_balance
    assert data["movement"]["net_movement_pence"] == 3000
    assert data["movement"]["inflows_pence"] == 5000
    assert data["movement"]["outflows_pence"] == 2000
    assert data["anchor"]["balance_pence"] + data["movement"]["net_movement_pence"] == data["current_balance_pence"]

    # Recent activity
    assert len(data["recent_transactions"]) == 2
    assert len(data["anchors"]) == 2


def test_account_breakdown_opening_only_anchor(client, db_session):
    """
    Verifies that an opening anchor counts as ground truth:
    1. Account with only its opening balance anchor has has_anchor=True and is_opening=True.
    2. Reports the opening anchor balance and local timestamp.
    3. Formula satisfies: opening_anchor + post_anchor_movement == current_balance.
    """
    from datetime import datetime, timezone
    from app.models import Account, AccountType, AccountBalanceAnchor, Transaction, TransactionType

    acc = Account(
        name="Opening Only Account",
        account_type=AccountType.CURRENT,
        starting_balance_pence=50000,
        starting_balance_date=datetime(2026, 10, 1, 0, 0, tzinfo=timezone.utc)
    )
    db_session.add(acc)
    db_session.commit()

    # Verify only opening anchor exists
    anchors = db_session.query(AccountBalanceAnchor).filter(AccountBalanceAnchor.account_id == acc.id).all()
    assert len(anchors) == 1
    assert anchors[0].is_opening is True

    # Post-opening-anchor transaction (+£200)
    tx = Transaction(
        transaction_date=datetime(2026, 10, 10, 14, 0, tzinfo=timezone.utc),
        transaction_type=TransactionType.INCOME,
        amount_pence=20000,
        merchant="Freelance Client",
        account_id=acc.id
    )
    db_session.add(tx)
    db_session.commit()

    res = client.get(f"/api/accounts/{acc.id}/breakdown")
    assert res.status_code == 200, res.text
    d = res.json()

    assert d["account_name"] == "Opening Only Account"
    assert d["account_group"] == "Depository Accounts"
    assert d["current_balance_pence"] == 70000
    assert d["formatted_current_balance"] == "£700.00"

    # Opening anchor must count as ground truth
    assert d["anchor"]["has_anchor"] is True
    assert d["anchor"]["is_opening"] is True
    assert d["anchor"]["balance_pence"] == 50000
    assert d["anchor"]["formatted_balance"] == "£500.00"
    assert "Opening balance anchor" in d["anchor"]["label"]
    assert "01/10/2026" in d["anchor"]["anchor_date_local"]

    # Movement equation
    assert d["movement"]["net_movement_pence"] == 20000
    assert d["movement"]["inflows_pence"] == 20000
    assert d["anchor"]["balance_pence"] + d["movement"]["net_movement_pence"] == d["current_balance_pence"]


def test_account_breakdown_unanchored_and_credit_card_liability(client, db_session):
    from app.models import Account, AccountType

    # 1. Truly unanchored Account (opening anchor removed)
    acc_unanchored = Account(name="Halifax Savings", account_type=AccountType.SAVINGS)
    acc_unanchored.balance_anchors = []
    # 2. Credit Card Liability
    acc_credit = Account(name="Amex Gold", account_type=AccountType.CREDIT_CARD, starting_balance_pence=-15000)
    # 3. Investment Account
    acc_invest = Account(name="Vanguard ISA", account_type=AccountType.INVESTMENT, starting_balance_pence=0)
    db_session.add_all([acc_unanchored, acc_credit, acc_invest])
    db_session.commit()

    # Unanchored breakdown check
    res_unanchored = client.get(f"/api/accounts/{acc_unanchored.id}/breakdown")
    assert res_unanchored.status_code == 200
    d_un = res_unanchored.json()
    assert d_un["anchor"]["has_anchor"] is False
    assert d_un["anchor"]["balance_pence"] is None
    assert "No ground-truth anchor" in d_un["anchor"]["label"]
    assert d_un["starting_balance_pence"] + d_un["movement"]["net_movement_pence"] == d_un["current_balance_pence"]

    # Credit card breakdown check
    res_credit = client.get(f"/api/accounts/{acc_credit.id}/breakdown")
    assert res_credit.status_code == 200
    d_cr = res_credit.json()
    assert d_cr["account_group"] == "Credit Liabilities"
    assert d_cr["current_balance_pence"] == -15000
    assert d_cr["liability"] is not None
    assert d_cr["liability"]["is_liability"] is True
    assert d_cr["liability"]["amount_owed_pence"] == 15000
    assert d_cr["liability"]["formatted_amount_owed"] == "£150.00"
    assert "liabilities" in d_cr["liability"]["explanation"]

    # Investment breakdown check
    res_invest = client.get(f"/api/accounts/{acc_invest.id}/breakdown")
    assert res_invest.status_code == 200
    d_inv = res_invest.json()
    assert d_inv["account_group"] == "Investment Portfolios"
    assert d_inv["investment"] is not None
    assert d_inv["investment"]["is_investment"] is True
    assert "active security holdings" in d_inv["investment"]["explanation"]

