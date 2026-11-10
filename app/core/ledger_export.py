"""
Ledger Export Generator (CSV & XLSX)

Provides deterministic, profile-scoped CSV and XLSX exports for all matching
transactions in the Ledger.
- Reflects the active profile's configured currency symbol and IANA timezone.
- Formats monetary values as pure numeric numbers in Excel with proper cell formatting.
- Includes comprehensive metadata headers: date range, active filters, record counts, and timezone.
- Preserves all core transaction fields: date, effective timestamp, entry timestamp,
  type, merchant, notes, account, destination account, category, nature, amount, currency,
  foreign origin provenance, entry method, and receipt/source links.
"""

import csv
import io
import re
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, List, Union, Tuple, Any
from zoneinfo import ZoneInfo
from sqlalchemy.orm import Session, joinedload

from app.models import Transaction, TransactionType, ExpenseNature, Account, Category
from app.core.currency import (
    pence_to_pounds, format_pence, get_currency_spec,
    get_effective_base_currency
)
from app.core.timezone import (
    get_app_timezone, get_now_utc, ensure_utc, get_today_local, get_end_of_day_utc
)
from app.core.transactions import build_transactions_query, apply_transactions_sorting


def generate_ledger_export(
    db: Session,
    export_format: str = "xlsx",
    account_id: Optional[int] = None,
    account_ids: Optional[str] = None,
    unassigned_only: Optional[bool] = None,
    category_id: Optional[Union[int, str]] = None,
    category_ids: Optional[str] = None,
    uncategorized_only: Optional[bool] = None,
    transaction_type: Optional[TransactionType] = None,
    transaction_types: Optional[str] = None,
    expense_nature: Optional[ExpenseNature] = None,
    q: Optional[str] = None,
    start_date: Optional[Union[str, datetime]] = None,
    end_date: Optional[Union[str, datetime]] = None,
    status: Optional[str] = None,
    date_preset: Optional[str] = None,
    date_offset: Optional[int] = 0,
    sort_by: Optional[str] = "date",
    sort_order: Optional[str] = "desc",
) -> Tuple[bytes, str, str]:
    """
    Generates a full CSV or XLSX export for all ledger transactions matching current filters.
    Returns (file_bytes, filename, media_type).
    """
    clean_format = (export_format or "xlsx").strip().lower()
    if clean_format not in ("csv", "xlsx"):
        clean_format = "xlsx"

    app_tz_str = get_app_timezone(db)
    app_tz = ZoneInfo(app_tz_str)
    base_curr = get_effective_base_currency(db)
    base_spec = get_currency_spec(base_curr)

    # Build filtered query across all pages
    query = build_transactions_query(
        db=db,
        account_id=account_id,
        account_ids=account_ids,
        unassigned_only=unassigned_only,
        category_id=category_id,
        category_ids=category_ids,
        uncategorized_only=uncategorized_only,
        transaction_type=transaction_type,
        transaction_types=transaction_types,
        expense_nature=expense_nature,
        q=q,
        start_date=start_date,
        end_date=end_date,
        status=status,
        date_preset=date_preset,
        date_offset=date_offset,
    )

    sorted_query = apply_transactions_sorting(query, sort_by=sort_by, sort_order=sort_order)

    transactions = (
        sorted_query.options(
            joinedload(Transaction.account),
            joinedload(Transaction.destination_account),
            joinedload(Transaction.category)
        )
        .all()
    )

    total_count = len(transactions)

    # Build human-readable filter descriptions for metadata block
    # 1. Accounts
    acc_filter_str = "All Accounts"
    if unassigned_only:
        acc_filter_str = "Unassigned Only"
    elif account_ids:
        raw_ids = [int(x.strip()) for x in account_ids.split(",") if x.strip().isdigit()]
        names = []
        if raw_ids:
            accs = db.query(Account).filter(Account.id.in_(raw_ids)).all()
            names.extend([a.name for a in accs])
        if "unassigned" in [x.strip().lower() for x in account_ids.split(",")]:
            names.append("Unassigned")
        if names:
            acc_filter_str = ", ".join(names)
    elif account_id is not None:
        acc = db.query(Account).filter(Account.id == account_id).first()
        acc_filter_str = acc.name if acc else f"Account #{account_id}"

    # 2. Categories
    cat_filter_str = "All Categories"
    if uncategorized_only:
        cat_filter_str = "Uncategorised Only"
    elif category_ids:
        raw_parts = [x.strip().lower() for x in category_ids.split(",") if x.strip()]
        names = []
        num_ids = [int(x) for x in raw_parts if x.isdigit() and int(x) > 0]
        if num_ids:
            cats = db.query(Category).filter(Category.id.in_(num_ids)).all()
            names.extend([c.name for c in cats])
        if "0" in raw_parts or "uncategorized" in raw_parts or "uncategorised" in raw_parts:
            names.append("Uncategorised")
        if names:
            cat_filter_str = ", ".join(names)
    elif category_id is not None:
        cat_s = str(category_id).strip().lower()
        if cat_s in ("0", "uncategorized", "uncategorised"):
            cat_filter_str = "Uncategorised"
        elif cat_s.isdigit():
            c = db.query(Category).filter(Category.id == int(cat_s)).first()
            cat_filter_str = c.name if c else f"Category #{cat_s}"

    # 3. Transaction Types
    type_filter_str = "All Types"
    if transaction_types:
        type_filter_str = ", ".join([t.capitalize() for t in transaction_types.split(",") if t.strip()])
    elif transaction_type is not None:
        type_filter_str = transaction_type.value.capitalize()

    # 4. Nature
    nature_filter_str = expense_nature.value.capitalize() if expense_nature else "All"

    # 5. Status
    status_filter_str = status.capitalize() if status else "All"

    # 6. Search
    search_filter_str = f"'{q.strip()}'" if q and q.strip() else "None"

    # 7. Date Range
    def _format_date_label(d_val: Optional[Union[str, datetime]]) -> str:
        if not d_val:
            return ""
        if isinstance(d_val, str):
            return d_val[:10]
        local_dt = d_val.astimezone(app_tz) if d_val.tzinfo else d_val
        return local_dt.strftime("%Y-%m-%d")

    s_label = _format_date_label(start_date)
    e_label = _format_date_label(end_date)
    if s_label and e_label:
        date_range_str = f"{s_label} to {e_label}"
    elif s_label:
        date_range_str = f"From {s_label}"
    elif e_label:
        date_range_str = f"Until {e_label}"
    else:
        date_range_str = "All Dates"

    now_local = datetime.now(app_tz)
    export_timestamp_str = now_local.strftime("%Y-%m-%d %H:%M:%S")

    sort_labels = {
        ("date", "desc"): "Date (Newest first)",
        ("date", "asc"): "Date (Oldest first)",
        ("amount", "asc"): "Amount (Lowest first)",
        ("amount", "desc"): "Amount (Highest first)",
        ("category", "asc"): "Category (A to Z)",
        ("category", "desc"): "Category (Z to A)",
        ("account", "asc"): "Account (A to Z)",
        ("account", "desc"): "Account (Z to A)",
    }
    sort_key = ((sort_by or "date").lower(), (sort_order or "desc").lower())
    sort_label = sort_labels.get(sort_key, f"{sort_key[0].capitalize()} ({sort_key[1]})")

    metadata_rows = [
        ["Finance Hub — Ledger Export"],
        ["Export Date", f"{export_timestamp_str} ({app_tz_str})"],
        ["Base Currency", f"{base_curr} ({base_spec.symbol})"],
        ["Matching Transactions", f"{total_count} records"],
        ["Sort Order", sort_label],
        ["Date Range", date_range_str],
        ["Status Filter", status_filter_str],
        ["Account Filter", acc_filter_str],
        ["Category Filter", cat_filter_str],
        ["Type Filter", type_filter_str],
        ["Nature Filter", nature_filter_str],
        ["Search Query", search_filter_str],
        [],
    ]

    headers = [
        "Transaction ID",
        "Date",
        "Effective Timestamp",
        "Entry Timestamp",
        "Type",
        "Merchant / Payee",
        "Account",
        "Destination Account",
        "Category",
        "Nature",
        "Amount",
        "Currency",
        "Original Amount",
        "Original Currency",
        "Exchange Rate",
        "Notes",
        "Entry Method",
        "Receipt / Source File",
        "Activity Status",
    ]

    col_types = [
        "integer",
        "date",
        "timestamp",
        "timestamp",
        "text",
        "text",
        "text",
        "text",
        "text",
        "text",
        "currency",
        "text",
        "foreign_amount",
        "text",
        "rate",
        "text",
        "text",
        "text",
        "text",
    ]

    data_rows: List[List[Any]] = []
    total_amount_pounds = 0.0
    today_local = get_today_local(app_tz)
    end_of_today_utc = get_end_of_day_utc(today_local, tz_str=app_tz)

    for tx in transactions:
        eff_utc = ensure_utc(tx.effective_timestamp or tx.transaction_date)
        act_status = "Planned" if eff_utc > end_of_today_utc else "Completed"

        tx_dt = tx.transaction_date.astimezone(app_tz) if tx.transaction_date.tzinfo else tx.transaction_date
        tx_date_str = tx_dt.strftime("%Y-%m-%d")

        eff_dt_str = ""
        if tx.effective_timestamp:
            eff_dt = tx.effective_timestamp.astimezone(app_tz) if tx.effective_timestamp.tzinfo else tx.effective_timestamp
            eff_dt_str = eff_dt.strftime("%Y-%m-%d %H:%M:%S")

        created_str = ""
        if tx.created_at:
            created_dt = tx.created_at.astimezone(app_tz) if tx.created_at.tzinfo else tx.created_at
            created_str = created_dt.strftime("%Y-%m-%d %H:%M:%S")

        tx_type_str = tx.transaction_type.value.capitalize()
        merchant_str = tx.merchant.strip() if tx.merchant and tx.merchant.strip() else "Merchant not recorded"
        acc_name = tx.account.name if tx.account else "Unassigned"
        dest_acc_name = tx.destination_account.name if tx.destination_account else ""
        cat_name = tx.category.name if tx.category else "Uncategorised"
        nature_str = (
            (tx.expense_nature.value if tx.expense_nature else "unclassified").capitalize()
            if tx.transaction_type == TransactionType.EXPENSE
            else "N/A"
        )

        acc_curr = tx.account.currency if tx.account else base_curr
        amt_float = round(pence_to_pounds(tx.amount_pence), 2)
        total_amount_pounds += amt_float

        orig_amt_float = float(tx.original_amount) if tx.original_amount is not None else None
        orig_curr_str = tx.original_currency or ""
        rate_float = float(tx.exchange_rate) if tx.exchange_rate is not None else None

        notes_str = tx.notes or ""
        entry_method_str = tx.entry_method or "manual"
        receipt_str = tx.receipt_path or ""

        data_rows.append([
            tx.id,
            tx_date_str,
            eff_dt_str,
            created_str,
            tx_type_str,
            merchant_str,
            acc_name,
            dest_acc_name,
            cat_name,
            nature_str,
            amt_float,
            acc_curr,
            orig_amt_float,
            orig_curr_str,
            rate_float,
            notes_str,
            entry_method_str,
            receipt_str,
            act_status,
        ])

    timestamp_clean = now_local.strftime("%Y%m%d_%H%M%S")
    filename_base = f"finance_hub_ledger_{timestamp_clean}"

    if clean_format == "csv":
        sio = io.StringIO()
        writer = csv.writer(sio)
        for mrow in metadata_rows:
            writer.writerow(mrow)
        writer.writerow(headers)

        for drow in data_rows:
            csv_row = []
            for i, val in enumerate(drow):
                ctype = col_types[i]
                if val is None:
                    csv_row.append("")
                elif ctype == "currency":
                    csv_row.append(f"{val:.2f}")
                elif ctype == "foreign_amount":
                    csv_row.append(f"{val:.2f}")
                elif ctype == "rate":
                    csv_row.append(f"{val:.8f}")
                else:
                    csv_row.append(str(val))
            writer.writerow(csv_row)

        csv_bytes = sio.getvalue().encode("utf-8-sig")
        return csv_bytes, f"{filename_base}.csv", "text/csv; charset=utf-8"

    # Build XLSX workbook using openpyxl
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    ws = wb.active
    ws.title = "Ledger Transactions"

    title_font = Font(name="Calibri", size=13, bold=True, color="0F172A")
    meta_label_font = Font(name="Calibri", size=10, bold=True, color="475569")
    meta_val_font = Font(name="Calibri", size=10, bold=False, color="1E293B")
    header_font = Font(name="Calibri", size=10, bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid")
    data_font = Font(name="Calibri", size=10, bold=False, color="0F172A")
    zebra_fill = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")
    data_border = Border(bottom=Side(border_style="thin", color="E2E8F0"))

    # Write metadata
    cur_row = 1
    for mrow in metadata_rows:
        if not mrow:
            cur_row += 1
            continue
        if len(mrow) == 1:
            cell = ws.cell(row=cur_row, column=1, value=mrow[0])
            cell.font = title_font
        else:
            c_lbl = ws.cell(row=cur_row, column=1, value=mrow[0])
            c_lbl.font = meta_label_font
            c_val = ws.cell(row=cur_row, column=2, value=mrow[1])
            c_val.font = meta_val_font
        cur_row += 1

    header_row_idx = cur_row
    for col_idx, h_text in enumerate(headers, start=1):
        cell = ws.cell(row=header_row_idx, column=col_idx, value=h_text)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center" if col_types[col_idx - 1] in ("date", "timestamp", "integer") else ("right" if col_types[col_idx - 1] in ("currency", "foreign_amount", "rate") else "left"), vertical="center")

    # Dynamic currency cell format for amounts in XLSX
    # e.g., "[$£-809] #,##0.00" or simple "#,##0.00" with explicit currency column
    amount_num_format = f"{base_spec.symbol}#,##0.00;[Red]-{base_spec.symbol}#,##0.00;\"-\""

    data_start_row = header_row_idx + 1
    for r_offset, drow in enumerate(data_rows):
        row_idx = data_start_row + r_offset
        is_zebra = (r_offset % 2 == 1)
        for col_idx, val in enumerate(drow, start=1):
            cell = ws.cell(row=row_idx, column=col_idx)
            ctype = col_types[col_idx - 1]
            cell.font = data_font
            cell.border = data_border
            if is_zebra:
                cell.fill = zebra_fill

            if val is None:
                cell.value = ""
            elif ctype == "integer":
                cell.value = int(val)
                cell.alignment = Alignment(horizontal="center")
            elif ctype == "currency":
                cell.value = float(val)
                cell.number_format = amount_num_format
                cell.alignment = Alignment(horizontal="right")
            elif ctype == "foreign_amount":
                cell.value = float(val)
                cell.number_format = "#,##0.00"
                cell.alignment = Alignment(horizontal="right")
            elif ctype == "rate":
                cell.value = float(val)
                cell.number_format = "0.00000000"
                cell.alignment = Alignment(horizontal="right")
            elif ctype in ("date", "timestamp"):
                cell.value = str(val)
                cell.alignment = Alignment(horizontal="center")
            else:
                cell.value = str(val)
                cell.alignment = Alignment(horizontal="left")

    # Freeze header row
    ws.freeze_panes = f"A{data_start_row}"

    # Auto-fit column widths
    for col_idx in range(1, len(headers) + 1):
        col_letter = get_column_letter(col_idx)
        max_len = len(headers[col_idx - 1])
        for r in range(data_start_row, min(data_start_row + 100, data_start_row + len(data_rows))):
            val_str = str(ws.cell(row=r, column=col_idx).value or "")
            if len(val_str) > max_len:
                max_len = len(val_str)
        ws.column_dimensions[col_letter].width = max(max_len + 3, 11)

    bio = io.BytesIO()
    wb.save(bio)
    xlsx_bytes = bio.getvalue()

    return xlsx_bytes, f"{filename_base}.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
