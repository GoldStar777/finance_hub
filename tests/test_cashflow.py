import pytest
from datetime import datetime, timezone
from decimal import Decimal

from app.models import (
    Account,
    AccountType,
    Category,
    Transaction,
    TransactionType,
    ExpenseNature,
)
from app.core.cashflow import (
    get_cashflow_summary,
    parse_month_range,
    get_available_currencies,
    get_available_months,
)

def test_transfers_contribute_zero_to_income_and_expenses(db_session, client):
    """Rule 1: Internal transfers between user accounts must contribute exactly zero to cash-flow income and expenses."""
    acc1 = Account(name="Current Account", account_type=AccountType.CURRENT, currency="GBP", starting_balance_pence=100000)
    acc2 = Account(name="Savings Account", account_type=AccountType.SAVINGS, currency="GBP", starting_balance_pence=50000)
    db_session.add_all([acc1, acc2])
    db_session.commit()

    test_date = datetime(2026, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
    tx_transfer = Transaction(
        transaction_date=test_date,
        transaction_type=TransactionType.TRANSFER,
        amount_pence=30000,
        merchant="Internal Transfer",
        account_id=acc1.id,
        destination_account_id=acc2.id,
        expense_nature=ExpenseNature.UNCLASSIFIED,
    )
    db_session.add(tx_transfer)
    db_session.commit()

    summary = get_cashflow_summary(db_session, month_str="2026-06", currency_param="GBP")

    assert summary["income_pence"] == 0
    assert summary["fixed_expenses_pence"] == 0
    assert summary["variable_expenses_pence"] == 0
    assert summary["unclassified_expenses_pence"] == 0
    assert summary["total_expenses_pence"] == 0
    assert summary["net_surplus_pence"] == 0
    assert summary["transfers_volume_pence"] == 30000
    assert summary["transfers_count"] == 1
    assert summary["categories"] == []

def test_expense_nature_and_per_transaction_override(db_session):
    """Rule 2: Expense nature must use each transaction's fixed/variable value, including overrides."""
    acc = Account(name="Current Account", account_type=AccountType.CURRENT, currency="GBP")
    cat_fixed = Category(name="Rent & Bills", default_expense_nature=ExpenseNature.FIXED)
    cat_variable = Category(name="Groceries", default_expense_nature=ExpenseNature.VARIABLE)
    db_session.add_all([acc, cat_fixed, cat_variable])
    db_session.commit()

    month_dt = datetime(2026, 7, 10, 10, 0, 0, tzinfo=timezone.utc)

    # 1. Fixed expense using category default
    tx1 = Transaction(
        transaction_date=month_dt,
        transaction_type=TransactionType.EXPENSE,
        amount_pence=120000,  # £1,200
        merchant="Landlord",
        account_id=acc.id,
        category_id=cat_fixed.id,
        expense_nature=ExpenseNature.FIXED,
    )

    # 2. Variable expense using category default
    tx2 = Transaction(
        transaction_date=month_dt,
        transaction_type=TransactionType.EXPENSE,
        amount_pence=25000,  # £250
        merchant="Sainsburys",
        account_id=acc.id,
        category_id=cat_variable.id,
        expense_nature=ExpenseNature.VARIABLE,
    )

    # 3. Expense with category default FIXED, but overridden to VARIABLE for this transaction
    tx3 = Transaction(
        transaction_date=month_dt,
        transaction_type=TransactionType.EXPENSE,
        amount_pence=5000,  # £50 one-off maintenance bill
        merchant="Plumber Callout",
        account_id=acc.id,
        category_id=cat_fixed.id,
        expense_nature=ExpenseNature.VARIABLE,  # Overridden!
    )

    # 4. Unclassified expense without category
    tx4 = Transaction(
        transaction_date=month_dt,
        transaction_type=TransactionType.EXPENSE,
        amount_pence=1500,  # £15
        merchant="Corner Shop",
        account_id=acc.id,
        category_id=None,
        expense_nature=ExpenseNature.UNCLASSIFIED,
    )

    # 5. Income
    tx_income = Transaction(
        transaction_date=month_dt,
        transaction_type=TransactionType.INCOME,
        amount_pence=300000,  # £3,000
        merchant="Tech Corp Salary",
        account_id=acc.id,
        expense_nature=ExpenseNature.UNCLASSIFIED,
    )

    db_session.add_all([tx1, tx2, tx3, tx4, tx_income])
    db_session.commit()

    summary = get_cashflow_summary(db_session, month_str="2026-07", currency_param="GBP")

    assert summary["income_pence"] == 300000
    assert summary["fixed_expenses_pence"] == 120000
    assert summary["variable_expenses_pence"] == 30000  # £250 + £50 override
    assert summary["unclassified_expenses_pence"] == 1500
    assert summary["total_expenses_pence"] == 151500
    assert summary["operating_surplus_pence"] == 300000 - 151500  # 148500 (£1,485)
    assert summary["net_surplus_pence"] == 148500
    assert summary["fixed_percentage"] == round(120000 / 151500 * 100, 1)
    assert summary["variable_percentage"] == round(30000 / 151500 * 100, 1)

def test_refunds_and_adjustments_handling(db_session):
    """Rule 3: Defined and consistent handling of refunds and reconciliation adjustments."""
    acc = Account(name="Current Account", account_type=AccountType.CURRENT, currency="GBP")
    db_session.add(acc)
    db_session.commit()

    dt = datetime(2026, 8, 5, 14, 0, 0, tzinfo=timezone.utc)

    # Income (e.g. Salary + Store Refund recorded as income)
    tx_salary = Transaction(
        transaction_date=dt,
        transaction_type=TransactionType.INCOME,
        amount_pence=200000,
        merchant="Salary",
        account_id=acc.id
    )
    tx_refund = Transaction(
        transaction_date=dt,
        transaction_type=TransactionType.INCOME,
        amount_pence=5000,  # £50 refund
        merchant="Amazon Refund",
        account_id=acc.id
    )

    # Expenses
    tx_exp = Transaction(
        transaction_date=dt,
        transaction_type=TransactionType.EXPENSE,
        amount_pence=100000,
        merchant="Rent",
        account_id=acc.id,
        expense_nature=ExpenseNature.FIXED
    )

    # Positive Adjustment (Credit / Discrepancy correction in user's favor)
    tx_adj_pos = Transaction(
        transaction_date=dt,
        transaction_type=TransactionType.ADJUSTMENT,
        amount_pence=1500,  # +£15
        merchant="Reconciliation Correction",
        notes="[Positive adjustment] Missing interest credited",
        account_id=acc.id
    )

    # Negative Adjustment (Debit / Discrepancy correction against user)
    tx_adj_neg = Transaction(
        transaction_date=dt,
        transaction_type=TransactionType.ADJUSTMENT,
        amount_pence=500,  # -£5
        merchant="Reconciliation Correction",
        notes="Bank fee discrepancy deduction",
        account_id=acc.id
    )

    db_session.add_all([tx_salary, tx_refund, tx_exp, tx_adj_pos, tx_adj_neg])
    db_session.commit()

    summary = get_cashflow_summary(db_session, month_str="2026-08", currency_param="GBP")

    assert summary["income_pence"] == 205000  # £2,000 + £50 refund
    assert summary["total_expenses_pence"] == 100000
    assert summary["operating_surplus_pence"] == 105000

    assert summary["adjustments_inflow_pence"] == 1500
    assert summary["adjustments_outflow_pence"] == 500
    assert summary["adjustments_net_pence"] == 1000

    # Net Surplus = Operating Surplus + Net Adjustments
    assert summary["net_surplus_pence"] == 105000 + 1000  # 106000 (£1,060)

def test_multi_currency_isolation(db_session):
    """Rule 4: Multi-currency isolation - never combine amounts from different currencies."""
    acc_gbp = Account(name="UK Bank", account_type=AccountType.CURRENT, currency="GBP")
    acc_eur = Account(name="Euro Bank", account_type=AccountType.CURRENT, currency="EUR")
    db_session.add_all([acc_gbp, acc_eur])
    db_session.commit()

    dt = datetime(2026, 9, 10, 10, 0, 0, tzinfo=timezone.utc)

    # GBP transactions
    db_session.add_all([
        Transaction(
            transaction_date=dt,
            transaction_type=TransactionType.INCOME,
            amount_pence=200000,  # £2,000
            merchant="UK Salary",
            account_id=acc_gbp.id
        ),
        Transaction(
            transaction_date=dt,
            transaction_type=TransactionType.EXPENSE,
            amount_pence=50000,  # £500
            merchant="UK Groceries",
            account_id=acc_gbp.id,
            expense_nature=ExpenseNature.VARIABLE
        )
    ])

    # EUR transactions
    db_session.add_all([
        Transaction(
            transaction_date=dt,
            transaction_type=TransactionType.INCOME,
            amount_pence=350000,  # €3,500
            merchant="Euro Freelance",
            account_id=acc_eur.id
        ),
        Transaction(
            transaction_date=dt,
            transaction_type=TransactionType.EXPENSE,
            amount_pence=120000,  # €1,200
            merchant="Euro Rent",
            account_id=acc_eur.id,
            expense_nature=ExpenseNature.FIXED
        )
    ])
    db_session.commit()

    # Query GBP
    summary_gbp = get_cashflow_summary(db_session, month_str="2026-09", currency_param="GBP")
    assert summary_gbp["currency"] == "GBP"
    assert summary_gbp["currency_symbol"] == "£"
    assert summary_gbp["income_pence"] == 200000
    assert summary_gbp["total_expenses_pence"] == 50000
    assert summary_gbp["net_surplus_pence"] == 150000

    # Query EUR
    summary_eur = get_cashflow_summary(db_session, month_str="2026-09", currency_param="EUR")
    assert summary_eur["currency"] == "EUR"
    assert summary_eur["currency_symbol"] == "€"
    assert summary_eur["income_pence"] == 350000
    assert summary_eur["total_expenses_pence"] == 120000
    assert summary_eur["net_surplus_pence"] == 230000

    # Available currencies lists both
    assert "GBP" in summary_gbp["available_currencies"]
    assert "EUR" in summary_gbp["available_currencies"]

def test_zero_income_and_safe_division(db_session):
    """Rule 5: Handle months with zero income safely without ZeroDivisionError."""
    acc = Account(name="Current Account", account_type=AccountType.CURRENT, currency="GBP")
    db_session.add(acc)
    db_session.commit()

    dt = datetime(2026, 1, 15, 10, 0, 0, tzinfo=timezone.utc)

    # Expenses only, zero income
    tx_exp = Transaction(
        transaction_date=dt,
        transaction_type=TransactionType.EXPENSE,
        amount_pence=45000,  # £450
        merchant="Bills",
        account_id=acc.id,
        expense_nature=ExpenseNature.FIXED
    )
    db_session.add(tx_exp)
    db_session.commit()

    summary = get_cashflow_summary(db_session, month_str="2026-01", currency_param="GBP")

    assert summary["income_pence"] == 0
    assert summary["total_expenses_pence"] == 45000
    assert summary["net_surplus_pence"] == -45000
    assert summary["savings_rate"] == 0.0
    assert summary["is_savings_rate_applicable"] is False
    assert summary["formatted_savings_rate"] == "N/A"

def test_sparse_or_empty_month_state(db_session):
    """Rule 6: Informative empty state when month has no transactions."""
    acc = Account(name="Current Account", account_type=AccountType.CURRENT, currency="GBP")
    db_session.add(acc)
    db_session.commit()

    summary = get_cashflow_summary(db_session, month_str="2024-03", currency_param="GBP")

    assert summary["has_data"] is False
    assert summary["total_transactions_count"] == 0
    assert summary["income_pence"] == 0
    assert summary["total_expenses_pence"] == 0
    assert summary["net_surplus_pence"] == 0
    assert summary["categories"] == []
    assert summary["is_savings_rate_applicable"] is False

def test_category_breakdown_aggregation(db_session):
    """Verifies category spending aggregation, sorting, and percentage computation."""
    acc = Account(name="Current Account", account_type=AccountType.CURRENT, currency="GBP")
    cat1 = Category(name="Housing", color="#FF0000", default_expense_nature=ExpenseNature.FIXED)
    cat2 = Category(name="Dining", color="#00FF00", default_expense_nature=ExpenseNature.VARIABLE)
    db_session.add_all([acc, cat1, cat2])
    db_session.commit()

    dt = datetime(2026, 10, 5, 12, 0, 0, tzinfo=timezone.utc)

    db_session.add_all([
        Transaction(
            transaction_date=dt,
            transaction_type=TransactionType.EXPENSE,
            amount_pence=80000,  # £800
            merchant="Rent",
            account_id=acc.id,
            category_id=cat1.id,
            expense_nature=ExpenseNature.FIXED
        ),
        Transaction(
            transaction_date=dt,
            transaction_type=TransactionType.EXPENSE,
            amount_pence=20000,  # £200
            merchant="Restaurant",
            account_id=acc.id,
            category_id=cat2.id,
            expense_nature=ExpenseNature.VARIABLE
        ),
        Transaction(
            transaction_date=dt,
            transaction_type=TransactionType.EXPENSE,
            amount_pence=10000,  # £100
            merchant="Uncategorized Store",
            account_id=acc.id,
            category_id=None,
            expense_nature=ExpenseNature.UNCLASSIFIED
        ),
    ])
    db_session.commit()

    summary = get_cashflow_summary(db_session, month_str="2026-10", currency_param="GBP")

    assert summary["total_expenses_pence"] == 110000
    categories = summary["categories"]
    assert len(categories) == 3

    # Sorted by spend descending
    assert categories[0]["category_name"] == "Housing"
    assert categories[0]["total_pence"] == 80000
    assert categories[0]["percentage"] == round(80000 / 110000 * 100, 1)

    assert categories[1]["category_name"] == "Dining"
    assert categories[1]["total_pence"] == 20000
    assert categories[1]["percentage"] == round(20000 / 110000 * 100, 1)

    assert categories[2]["category_name"] == "Uncategorized"
    assert categories[2]["total_pence"] == 10000
    assert categories[2]["percentage"] == round(10000 / 110000 * 100, 1)

def test_api_cashflow_endpoint(client, db_session):
    """Integration test for GET /api/analytics/cashflow endpoint."""
    acc = Account(name="Current Account", account_type=AccountType.CURRENT, currency="GBP")
    db_session.add(acc)
    db_session.commit()

    dt = datetime(2026, 10, 12, 10, 0, 0, tzinfo=timezone.utc)
    db_session.add(
        Transaction(
            transaction_date=dt,
            transaction_type=TransactionType.INCOME,
            amount_pence=150000,
            merchant="Consulting",
            account_id=acc.id
        )
    )
    db_session.commit()

    res = client.get("/api/analytics/cashflow?month=2026-10&currency=GBP")
    assert res.status_code == 200
    data = res.json()

    assert data["selected_month"] == "2026-10"
    assert data["currency"] == "GBP"
    assert data["currency_symbol"] == "£"
    assert data["income_pence"] == 150000
    assert data["income_pounds"] == 1500.0
    assert data["savings_rate"] == 100.0
    assert len(data["historical_trend"]) == 6

    # Test filtering by invalid account ID returns 404
    res_err = client.get("/api/analytics/cashflow?account_id=999999")
    assert res_err.status_code == 404

