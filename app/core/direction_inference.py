"""
Provider-agnostic statement transaction direction inference.
Infers direction ('expense' vs 'income') strictly from structural evidence:
1. Explicit separate Debit and Credit columns (e.g. Debit / Credit, Paid out / Paid in, Money out / Money in).
2. Transaction Type or Direction column (e.g. Type, CR/DR, Indicator).
3. Running-balance changes when sequential balance data is present and reliable.
4. Card-spending statement document context when supported by file structure (e.g. Card Member column, credit card account).
5. Signed amount conventions (negative vs positive).
6. Unsigned amounts without structural direction clues: NEVER default to income. Flag as uncertain for explicit human review.
"""

import re
from decimal import Decimal
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass


@dataclass
class RowDirectionResult:
    transaction_type: str  # 'expense' | 'income'
    is_uncertain: bool
    evidence_type: str
    explanation: str


@dataclass
class StatementDirectionAnalysis:
    evidence_type: str
    evidence_description: str
    expense_count: int
    income_count: int
    uncertain_count: int
    row_results: List[RowDirectionResult]


DEBIT_COLUMN_KEYWORDS = [
    "debit", "paid out", "spent", "money out", "outflow",
    "withdrawal", "charge", "debits", "dr"
]

CREDIT_COLUMN_KEYWORDS = [
    "credit", "paid in", "income", "money in", "inflow",
    "deposit", "credits", "cr"
]

TYPE_COLUMN_KEYWORDS = [
    "transaction type", "trans type", "trans_type", "type",
    "direction", "cr/dr", "cr_dr", "cr / dr", "indicator", "d/c"
]

BALANCE_COLUMN_KEYWORDS = [
    "balance", "running balance", "available balance", "account balance"
]

CARD_STRUCTURE_KEYWORDS = [
    "card member", "card number", "card details", "card no",
    "card ending", "cardholder", "appears on your statement as"
]


def detect_statement_columns(headers: List[str]) -> Dict[str, Optional[int]]:
    """Identifies structural columns from statement headers without assuming vendor-specific layouts."""
    cols: Dict[str, Optional[int]] = {
        "date": None,
        "merchant": None,
        "amount": None,
        "debit": None,
        "credit": None,
        "type": None,
        "balance": None,
        "card_structure": None,
    }

    for idx, raw_h in enumerate(headers):
        h = str(raw_h or "").strip().lower()
        if not h:
            continue

        # Date
        if cols["date"] is None and any(k in h for k in ["date", "booking date", "value date"]):
            cols["date"] = idx

        # Merchant / Description
        elif cols["merchant"] is None and any(k in h for k in ["description", "merchant", "payee", "narrative", "details", "memo", "name"]):
            cols["merchant"] = idx

        # Debit column
        elif cols["debit"] is None and any(k == h or f" {k}" in h or f"{k} " in h or f"({k})" in h for k in DEBIT_COLUMN_KEYWORDS) and "card" not in h:
            cols["debit"] = idx

        # Credit column
        elif cols["credit"] is None and any(k == h or f" {k}" in h or f"{k} " in h or f"({k})" in h for k in CREDIT_COLUMN_KEYWORDS) and "card" not in h:
            cols["credit"] = idx

        # Transaction type / direction column
        elif cols["type"] is None and any(k == h or f" {k}" in h or f"{k} " in h for k in TYPE_COLUMN_KEYWORDS):
            cols["type"] = idx

        # Balance column
        elif cols["balance"] is None and any(k in h for k in BALANCE_COLUMN_KEYWORDS):
            cols["balance"] = idx

        # Amount column (excluding balance)
        elif cols["amount"] is None and any(k in h for k in ["amount", "total", "value", "net", "gross"]) and "balance" not in h:
            cols["amount"] = idx

        # Card structure indicator in header
        if cols["card_structure"] is None and any(k in h for k in CARD_STRUCTURE_KEYWORDS):
            cols["card_structure"] = idx

    return cols


def parse_clean_decimal(val: Any) -> Optional[Decimal]:
    """Helper to parse a numeric value into Decimal safely."""
    if val is None:
        return None
    if isinstance(val, (int, float, Decimal)):
        return Decimal(str(val))
    s = str(val).strip().replace(",", "").replace("£", "").replace("$", "").replace("€", "")
    if not s:
        return None
    # Handle parenthesis negative e.g. (12.50)
    if s.startswith("(") and s.endswith(")"):
        s = f"-{s[1:-1]}"
    # Handle trailing minus e.g. 12.50-
    if s.endswith("-"):
        s = f"-{s[:-1]}"
    try:
        return Decimal(s)
    except Exception:
        return None


def infer_statement_direction(
    headers: List[str],
    data_rows: List[List[Any]],
    amount_col_idx: Optional[int] = None,
    debit_col_idx: Optional[int] = None,
    credit_col_idx: Optional[int] = None,
    type_col_idx: Optional[int] = None,
    balance_col_idx: Optional[int] = None,
    is_card_context: bool = False,
    filename: Optional[str] = None
) -> StatementDirectionAnalysis:
    """
    Analyzes statement rows and headers to determine transaction direction from evidence.
    Never defaults uncertain positive amounts to income.
    """
    detected_cols = detect_statement_columns(headers)
    amount_idx = amount_col_idx if amount_col_idx is not None else detected_cols["amount"]
    debit_idx = debit_col_idx if debit_col_idx is not None else detected_cols["debit"]
    credit_idx = credit_col_idx if credit_col_idx is not None else detected_cols["credit"]
    type_idx = type_col_idx if type_col_idx is not None else detected_cols["type"]
    balance_idx = balance_col_idx if balance_col_idx is not None else detected_cols["balance"]

    # Structural card context
    has_card_header = detected_cols["card_structure"] is not None
    fname = (filename or "").lower()
    has_card_filename = any(k in fname for k in ["amex", "credit_card", "creditcard", "mastercard", "visa"])
    is_card_structure = is_card_context or has_card_header or has_card_filename

    # Step 1: Check for explicit separate Debit and Credit columns
    has_debit_col = debit_idx is not None
    has_credit_col = credit_idx is not None

    if has_debit_col and has_credit_col:
        row_results: List[RowDirectionResult] = []
        exp_count = 0
        inc_count = 0
        unc_count = 0

        for row in data_rows:
            raw_deb = row[debit_idx] if debit_idx < len(row) else None
            raw_cred = row[credit_idx] if credit_idx < len(row) else None
            dec_deb = parse_clean_decimal(raw_deb)
            dec_cred = parse_clean_decimal(raw_cred)

            if dec_deb is not None and dec_deb != 0:
                row_results.append(RowDirectionResult(
                    transaction_type="expense",
                    is_uncertain=False,
                    evidence_type="debit_credit_columns",
                    explanation="Debit column entry"
                ))
                exp_count += 1
            elif dec_cred is not None and dec_cred != 0:
                row_results.append(RowDirectionResult(
                    transaction_type="income",
                    is_uncertain=False,
                    evidence_type="debit_credit_columns",
                    explanation="Credit column entry"
                ))
                inc_count += 1
            else:
                row_results.append(RowDirectionResult(
                    transaction_type="expense",
                    is_uncertain=True,
                    evidence_type="debit_credit_columns",
                    explanation="Both debit and credit columns were empty or zero"
                ))
                unc_count += 1

        return StatementDirectionAnalysis(
            evidence_type="debit_credit_columns",
            evidence_description=f"Derived with high confidence from separate Debit and Credit columns ({exp_count} expenses, {inc_count} income).",
            expense_count=exp_count,
            income_count=inc_count,
            uncertain_count=unc_count,
            row_results=row_results
        )

    # Step 2: Check for explicit Type / Direction column
    if type_idx is not None:
        row_results = []
        exp_count = 0
        inc_count = 0
        unc_count = 0

        for row in data_rows:
            type_val = str(row[type_idx] if type_idx < len(row) else "").strip().lower()
            if any(k in type_val for k in ["credit", "cr", "paid in", "money in", "deposit", "refund", "reversal"]) or type_val in ("c", "+"):
                row_results.append(RowDirectionResult(
                    transaction_type="income",
                    is_uncertain=False,
                    evidence_type="type_column",
                    explanation=f"Direction column '{headers[type_idx]}': {type_val}"
                ))
                inc_count += 1
            elif any(k in type_val for k in ["debit", "dr", "paid out", "money out", "purchase", "payment", "charge", "fee"]) or type_val in ("d", "-"):
                row_results.append(RowDirectionResult(
                    transaction_type="expense",
                    is_uncertain=False,
                    evidence_type="type_column",
                    explanation=f"Direction column '{headers[type_idx]}': {type_val}"
                ))
                exp_count += 1
            else:
                # Type column value not recognized
                row_results.append(RowDirectionResult(
                    transaction_type="expense",
                    is_uncertain=True,
                    evidence_type="type_column",
                    explanation=f"Unrecognized direction value: '{type_val}'"
                ))
                unc_count += 1

        type_h_name = headers[type_idx] if type_idx < len(headers) else "Type"
        return StatementDirectionAnalysis(
            evidence_type="type_column",
            evidence_description=f"Derived with high confidence from transaction type column '{type_h_name}' ({exp_count} expenses, {inc_count} income).",
            expense_count=exp_count,
            income_count=inc_count,
            uncertain_count=unc_count,
            row_results=row_results
        )

    # Step 3: Running Balance Verification (if balance column exists)
    if balance_idx is not None and amount_idx is not None:
        parsed_amounts: List[Optional[Decimal]] = []
        parsed_balances: List[Optional[Decimal]] = []
        for row in data_rows:
            amt_val = row[amount_idx] if amount_idx < len(row) else None
            bal_val = row[balance_idx] if balance_idx < len(row) else None
            parsed_amounts.append(parse_clean_decimal(amt_val))
            parsed_balances.append(parse_clean_decimal(bal_val))

        # Check consecutive deltas
        valid_deltas = 0
        balance_directed_rows: List[Optional[Tuple[str, bool]]] = [None] * len(data_rows)

        for i in range(1, len(data_rows)):
            b_prev = parsed_balances[i - 1]
            b_curr = parsed_balances[i]
            a_curr = parsed_amounts[i]
            if b_prev is not None and b_curr is not None and a_curr is not None and a_curr != 0:
                delta = b_curr - b_prev
                abs_a = abs(a_curr)
                if abs(abs(delta) - abs_a) <= Decimal("0.05"):
                    valid_deltas += 1
                    # In a standard bank account: balance goes down -> expense, goes up -> income
                    # In a card statement (balance = outstanding balance/debt): debt goes up -> expense, debt goes down -> income
                    if is_card_structure:
                        tx_t = "expense" if delta > 0 else "income"
                    else:
                        tx_t = "expense" if delta < 0 else "income"
                    balance_directed_rows[i] = (tx_t, False)

        # If >= 60% of transitions correlate mathematically with running balance, use it!
        total_transitions = max(len(data_rows) - 1, 1)
        if valid_deltas >= 3 and (valid_deltas / total_transitions) >= 0.6:
            row_results = []
            exp_count = 0
            inc_count = 0
            unc_count = 0
            for i in range(len(data_rows)):
                res = balance_directed_rows[i]
                if res is not None:
                    t_type, is_unc = res
                    row_results.append(RowDirectionResult(
                        transaction_type=t_type,
                        is_uncertain=is_unc,
                        evidence_type="running_balance",
                        explanation="Derived mathematically from running balance delta"
                    ))
                    if t_type == "expense":
                        exp_count += 1
                    else:
                        inc_count += 1
                else:
                    # Look at amount sign for first row or gap
                    a = parsed_amounts[i]
                    if a is not None:
                        if is_card_structure:
                            t_type = "income" if a < 0 else "expense"
                        else:
                            t_type = "expense" if a < 0 else "income"
                        row_results.append(RowDirectionResult(
                            transaction_type=t_type,
                            is_uncertain=False,
                            evidence_type="running_balance",
                            explanation="Inferred from balance trend"
                        ))
                        if t_type == "expense":
                            exp_count += 1
                        else:
                            inc_count += 1
                    else:
                        row_results.append(RowDirectionResult(
                            transaction_type="expense",
                            is_uncertain=True,
                            evidence_type="running_balance",
                            explanation="Could not calculate balance transition"
                        ))
                        unc_count += 1

            return StatementDirectionAnalysis(
                evidence_type="running_balance",
                evidence_description=f"Derived mathematically from running-balance changes across transactions ({exp_count} expenses, {inc_count} income).",
                expense_count=exp_count,
                income_count=inc_count,
                uncertain_count=unc_count,
                row_results=row_results
            )

    # Step 4: Amount Column Inspection (Signed amounts vs Unsigned ambiguous)
    if amount_idx is not None:
        parsed_amounts: List[Optional[Decimal]] = []
        raw_amounts: List[str] = []
        has_negative = False
        has_positive = False

        for row in data_rows:
            raw_a = str(row[amount_idx] if amount_idx < len(row) else "").strip()
            raw_amounts.append(raw_a)
            dec_a = parse_clean_decimal(raw_a)
            parsed_amounts.append(dec_a)
            if dec_a is not None:
                if dec_a < 0:
                    has_negative = True
                elif dec_a > 0:
                    has_positive = True

        # CASE 4A: Signed amounts are present (both positive and negative values exist)
        if has_negative:
            row_results = []
            exp_count = 0
            inc_count = 0
            unc_count = 0

            # If card structure context is supported (e.g. Card Member column, Amex/credit card context)
            if is_card_structure:
                # Credit card sign convention: positive amounts are card charges (expense); negative amounts are credits/payments (income)
                for idx, dec_a in enumerate(parsed_amounts):
                    if dec_a is None:
                        row_results.append(RowDirectionResult(
                            transaction_type="expense",
                            is_uncertain=True,
                            evidence_type="card_statement_context",
                            explanation="Missing amount"
                        ))
                        unc_count += 1
                    elif dec_a < 0:
                        # Negative on credit card statement is payment received or refund
                        row_results.append(RowDirectionResult(
                            transaction_type="income",
                            is_uncertain=False,
                            evidence_type="card_statement_context",
                            explanation="Credit/payment (negative amount on card statement)"
                        ))
                        inc_count += 1
                    else:
                        # Positive on credit card statement is a charge / purchase
                        row_results.append(RowDirectionResult(
                            transaction_type="expense",
                            is_uncertain=False,
                            evidence_type="card_statement_context",
                            explanation="Card purchase/charge (positive amount on card statement)"
                        ))
                        exp_count += 1

                return StatementDirectionAnalysis(
                    evidence_type="card_statement_context",
                    evidence_description=f"Derived from card statement structure and sign conventions: positive charges = expense ({exp_count}), negative credits = payment/refund ({inc_count}).",
                    expense_count=exp_count,
                    income_count=inc_count,
                    uncertain_count=unc_count,
                    row_results=row_results
                )
            else:
                # Standard bank statement signed amounts: negative = expense (money out), positive = income (money in)
                for idx, dec_a in enumerate(parsed_amounts):
                    if dec_a is None:
                        row_results.append(RowDirectionResult(
                            transaction_type="expense",
                            is_uncertain=True,
                            evidence_type="signed_amounts",
                            explanation="Missing amount"
                        ))
                        unc_count += 1
                    elif dec_a < 0:
                        row_results.append(RowDirectionResult(
                            transaction_type="expense",
                            is_uncertain=False,
                            evidence_type="signed_amounts",
                            explanation="Negative amount (money out = expense)"
                        ))
                        exp_count += 1
                    else:
                        row_results.append(RowDirectionResult(
                            transaction_type="income",
                            is_uncertain=False,
                            evidence_type="signed_amounts",
                            explanation="Positive amount (money in = income)"
                        ))
                        inc_count += 1

                return StatementDirectionAnalysis(
                    evidence_type="signed_amounts",
                    evidence_description=f"Derived from signed amounts: negative amounts = expense ({exp_count}), positive amounts = income ({inc_count}).",
                    expense_count=exp_count,
                    income_count=inc_count,
                    uncertain_count=unc_count,
                    row_results=row_results
                )

        # CASE 4B: All amounts are positive / unsigned, with NO signs and NO separate debit/credit or direction column
        # If card structure context is explicitly supported (e.g. Card Member column in file):
        if is_card_structure:
            row_results = []
            exp_count = 0
            inc_count = 0
            unc_count = 0
            for idx, dec_a in enumerate(parsed_amounts):
                if dec_a is None:
                    row_results.append(RowDirectionResult(
                        transaction_type="expense",
                        is_uncertain=True,
                        evidence_type="card_statement_context",
                        explanation="Missing amount"
                    ))
                    unc_count += 1
                else:
                    # On card-spending statements, purchases are positive debits
                    row_results.append(RowDirectionResult(
                        transaction_type="expense",
                        is_uncertain=False,
                        evidence_type="card_statement_context",
                        explanation="Card spending statement purchase"
                    ))
                    exp_count += 1

            return StatementDirectionAnalysis(
                evidence_type="card_statement_context",
                evidence_description=f"Derived from card statement structure: all {exp_count} unsigned records identified as card spending expenses.",
                expense_count=exp_count,
                income_count=0,
                uncertain_count=unc_count,
                row_results=row_results
            )

        # CASE 4C: True Ambiguous Unsigned CSV: NO negative amounts, NO debit/credit, NO type, NO balance, NO card context
        # In this case: NEVER default to income! Flag rows as uncertain for review.
        row_results = []
        for idx, dec_a in enumerate(parsed_amounts):
            row_results.append(RowDirectionResult(
                transaction_type="expense",
                is_uncertain=True,
                evidence_type="unsigned_ambiguous",
                explanation="Direction uncertain: unsigned amount without debit/credit or direction column"
            ))

        return StatementDirectionAnalysis(
            evidence_type="unsigned_ambiguous",
            evidence_description=f"Amounts in this file are unsigned without debit/credit or direction columns. All {len(data_rows)} rows flagged for review.",
            expense_count=0,
            income_count=0,
            uncertain_count=len(data_rows),
            row_results=row_results
        )

    # Fallback: No amount column found
    row_results = [
        RowDirectionResult(
            transaction_type="expense",
            is_uncertain=True,
            evidence_type="missing_columns",
            explanation="Could not locate amount or direction columns"
        )
        for _ in data_rows
    ]
    return StatementDirectionAnalysis(
        evidence_type="missing_columns",
        evidence_description="Could not locate standard amount or direction columns in statement.",
        expense_count=0,
        income_count=0,
        uncertain_count=len(data_rows),
        row_results=row_results
    )

