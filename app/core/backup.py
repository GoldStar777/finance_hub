import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
import zipfile
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, Any, List, Optional, Union

from dateutil.relativedelta import relativedelta
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from sqlalchemy import text
from sqlalchemy.orm import Session, joinedload

from app.config import BACKUP_DIR, STAGING_RECEIPTS_DIR, ARCHIVE_RECEIPTS_DIR, DB_PATH
from app.models import (
    Account, Transaction, TransactionType, ExpenseNature, Category, 
    AssetSnapshot, SystemSetting, Holding, HoldingValuation, AccountBalanceAnchor
)
from app.ledger import LedgerEngine
from app.core.currency import (
    pence_to_pounds, format_pence, get_effective_base_currency, get_currency_spec
)

def _compute_sha256(filepath: Path) -> str:
    """Computes SHA-256 hash of a file."""
    sha256 = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            sha256.update(chunk)
    return sha256.hexdigest()

def _format_size(size_bytes: int) -> str:
    """Formats bytes into human-readable string (KB, MB, GB)."""
    for unit in ["B", "KB", "MB", "GB"]:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} TB"

def get_system_setting(db: Session, key: str, default: str = "") -> str:
    """Reads a setting from the system_settings table with fallback default."""
    setting = db.query(SystemSetting).filter(SystemSetting.key == key).first()
    if setting:
        return setting.value
    return default

def set_system_setting(db: Session, key: str, value: str):
    """Sets a system setting in SQLite."""
    setting = db.query(SystemSetting).filter(SystemSetting.key == key).first()
    if setting:
        setting.value = value
    else:
        setting = SystemSetting(key=key, value=value)
        db.add(setting)
    db.commit()

def generate_reference_workbook(db: Session, target_path: Path):
    """
    Generates a high-fidelity, human-readable reference Excel workbook:
    - Sheet 1: Summary (As-of-date net position and totals)
    - Sheet 2: Accounts (One row per account, preserving currency codes)
    - Sheet 3: Transactions (Full ledger history, one row per transaction)
    - Sheet 4: Categories (Taxonomy and budget natures)
    - Sheet 5: Cash Flow (Monthly cash flow aggregates)
    - Sheet 6: Investments (Valuation snapshots and records)
    """
    wb = openpyxl.Workbook()
    wb.remove(wb.active)  # Remove default blank sheet

    # Common styling
    header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid")  # Slate 800
    title_font = Font(name="Calibri", size=14, bold=True, color="0F172A")
    meta_font = Font(name="Calibri", size=10, italic=True, color="64748B")
    border_thin = Side(border_style="thin", color="E2E8F0")
    cell_border = Border(left=border_thin, right=border_thin, top=border_thin, bottom=border_thin)

    def apply_header_style(sheet, col_count):
        for col in range(1, col_count + 1):
            cell = sheet.cell(row=1, column=col)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal="left", vertical="center")

    def auto_fit_columns(sheet):
        for col in sheet.columns:
            max_len = 0
            col_letter = get_column_letter(col[0].column)
            for cell in col:
                val = str(cell.value or "")
                if len(val) > max_len and len(val) < 80:
                    max_len = len(val)
            sheet.column_dimensions[col_letter].width = max(max_len + 4, 12)

    now_utc = datetime.now(timezone.utc)
    now_str = now_utc.strftime("%Y-%m-%d %H:%M:%S UTC")

    # --- 1. SUMMARY SHEET ---
    ws_sum = wb.create_sheet(title="Summary")
    ws_sum.views.sheetView[0].showGridLines = True
    base_curr = get_effective_base_currency(db)
    base_spec = get_currency_spec(base_curr)
    summary_data = LedgerEngine.get_dashboard_summary(db)

    ws_sum.cell(row=1, column=1, value="Finance Hub — Executive Backup Summary").font = title_font
    ws_sum.cell(row=2, column=1, value=f"As-of Date: {now_str}").font = meta_font
    ws_sum.cell(row=3, column=1, value="Note: This workbook is a human-readable reference report. The database and receipts remain the restorable source.").font = meta_font

    ws_sum.cell(row=5, column=1, value="Core Executive Metric").font = Font(bold=True)
    ws_sum.cell(row=5, column=2, value=f"Amount ({base_spec.symbol})").font = Font(bold=True)
    ws_sum.cell(row=5, column=3, value="Formatted Value").font = Font(bold=True)

    metrics = [
        ("Net Worth", summary_data["net_worth_pounds"], summary_data["formatted_net_worth"]),
        ("Total Liquid Reserves", summary_data["total_liquid_pounds"], summary_data["formatted_total_liquid"]),
        ("Total Debt / Liabilities", summary_data["total_debt_pounds"], summary_data["formatted_total_debt"]),
        ("Total Invested Assets", summary_data["total_invested_pounds"], summary_data["formatted_total_invested"]),
    ]

    for idx, (lbl, val, fmt) in enumerate(metrics, start=6):
        ws_sum.cell(row=idx, column=1, value=lbl).border = cell_border
        c2 = ws_sum.cell(row=idx, column=2, value=val)
        c2.number_format = "#,##0.00"
        c2.border = cell_border
        ws_sum.cell(row=idx, column=3, value=fmt).border = cell_border

    # Metadata counts
    total_accs = db.query(Account).count()
    total_txs = db.query(Transaction).count()
    total_cats = db.query(Category).count()
    total_snaps = db.query(AssetSnapshot).count()
    total_holdings = db.query(Holding).count()
    total_valuations = db.query(HoldingValuation).count()

    ws_sum.cell(row=12, column=1, value="Database Record Counts").font = Font(bold=True)
    counts_data = [
        ("Financial Accounts", total_accs),
        ("Ledger Transactions", total_txs),
        ("Expense Categories", total_cats),
        ("Investment Snapshots", total_snaps),
        ("Investment Holdings", total_holdings),
        ("Holding Valuations", total_valuations),
    ]
    for idx, (lbl, cnt) in enumerate(counts_data, start=13):
        ws_sum.cell(row=idx, column=1, value=lbl).border = cell_border
        ws_sum.cell(row=idx, column=2, value=cnt).border = cell_border

    auto_fit_columns(ws_sum)

    # --- 2. ACCOUNTS SHEET ---
    ws_acc = wb.create_sheet(title="Accounts")
    ws_acc.views.sheetView[0].showGridLines = True
    acc_headers = ["ID", "Account Name", "Account Type", "Currency", "Starting Balance", "Current Balance", "Status", "Created At"]
    ws_acc.append(acc_headers)
    apply_header_style(ws_acc, len(acc_headers))

    accounts = db.query(Account).order_by(Account.id.asc()).all()
    for acc in accounts:
        bal_pence = LedgerEngine.get_account_balance(db, acc.id)
        bal_pounds = pence_to_pounds(bal_pence)
        start_pounds = pence_to_pounds(acc.starting_balance_pence)
        created_str = acc.created_at.strftime("%Y-%m-%d %H:%M:%S") if acc.created_at else ""
        row = [
            acc.id,
            acc.name,
            acc.account_type.value,
            acc.currency,
            start_pounds,
            bal_pounds,
            "Active" if acc.is_active else "Archived",
            created_str
        ]
        ws_acc.append(row)
        curr_row = ws_acc.max_row
        ws_acc.cell(row=curr_row, column=5).number_format = "#,##0.00"
        ws_acc.cell(row=curr_row, column=6).number_format = "#,##0.00"
        for col_idx in range(1, len(acc_headers) + 1):
            ws_acc.cell(row=curr_row, column=col_idx).border = cell_border

    auto_fit_columns(ws_acc)

    # --- 3. TRANSACTIONS SHEET ---
    ws_tx = wb.create_sheet(title="Transactions")
    ws_tx.views.sheetView[0].showGridLines = True
    tx_headers = [
        "ID", "Date", "Type", "Merchant / Description", "Amount", "Currency",
        "Original Amount", "Original Currency", "Exchange Rate",
        "Account", "Destination Account", "Category", "Budget Nature", "Notes",
        "Effective Timestamp", "Entry Timestamp"
    ]
    ws_tx.append(tx_headers)
    apply_header_style(ws_tx, len(tx_headers))

    txs = (
        db.query(Transaction)
        .options(
            joinedload(Transaction.account),
            joinedload(Transaction.destination_account),
            joinedload(Transaction.category)
        )
        .order_by(Transaction.transaction_date.desc(), Transaction.id.desc())
        .all()
    )

    for tx in txs:
        date_str = tx.transaction_date.strftime("%Y-%m-%d") if tx.transaction_date else ""
        amt_pounds = pence_to_pounds(tx.amount_pence)
        # Expense is negative in display amount column for intuitive accounting read
        if tx.transaction_type == TransactionType.EXPENSE:
            display_amt = -amt_pounds
        else:
            display_amt = amt_pounds

        currency_code = tx.account.currency if tx.account else base_curr
        orig_amt = float(tx.original_amount) if tx.original_amount is not None else ""
        orig_curr = tx.original_currency or ""
        rate_val = float(tx.exchange_rate) if tx.exchange_rate is not None else ""

        acc_name = tx.account.name if tx.account else "Unassigned"
        dest_name = tx.destination_account.name if tx.destination_account else ""
        cat_name = tx.category.name if tx.category else "Uncategorised"
        nature = tx.expense_nature.value if tx.expense_nature else "unclassified"

        eff_str = tx.effective_timestamp.strftime("%Y-%m-%d %H:%M:%S") if tx.effective_timestamp else ""
        entry_str = tx.created_at.strftime("%Y-%m-%d %H:%M:%S") if tx.created_at else "Unknown"

        row = [
            tx.id,
            date_str,
            tx.transaction_type.value,
            tx.merchant or "Merchant not recorded",
            display_amt,
            currency_code,
            orig_amt,
            orig_curr,
            rate_val,
            acc_name,
            dest_name,
            cat_name,
            nature,
            tx.notes or "",
            eff_str,
            entry_str
        ]
        ws_tx.append(row)
        curr_row = ws_tx.max_row
        ws_tx.cell(row=curr_row, column=5).number_format = "#,##0.00"
        if orig_amt != "":
            ws_tx.cell(row=curr_row, column=7).number_format = "#,##0.00"
        if rate_val != "":
            ws_tx.cell(row=curr_row, column=9).number_format = "0.00000000"
        for col_idx in range(1, len(tx_headers) + 1):
            ws_tx.cell(row=curr_row, column=col_idx).border = cell_border

    auto_fit_columns(ws_tx)

    # --- 4. CATEGORIES SHEET ---
    ws_cat = wb.create_sheet(title="Categories")
    ws_cat.views.sheetView[0].showGridLines = True
    cat_headers = ["ID", "Category Name", "Purpose", "Default Budget Nature", "Accent Color", "Active Status"]
    ws_cat.append(cat_headers)
    apply_header_style(ws_cat, len(cat_headers))

    categories = db.query(Category).order_by(Category.name.asc()).all()
    for cat in categories:
        cat_purpose = (getattr(cat, "category_type", None).value if getattr(cat, "category_type", None) else "expense")
        nature_val = "N/A" if cat_purpose == "income" else cat.default_expense_nature.value
        row = [
            cat.id,
            cat.name,
            cat_purpose.capitalize(),
            nature_val,
            cat.color,
            "Active" if cat.is_active else "Archived"
        ]
        ws_cat.append(row)
        curr_row = ws_cat.max_row
        for col_idx in range(1, len(cat_headers) + 1):
            ws_cat.cell(row=curr_row, column=col_idx).border = cell_border

    auto_fit_columns(ws_cat)

    # --- 5. CASH FLOW SHEET ---
    ws_cf = wb.create_sheet(title="Cash Flow")
    ws_cf.views.sheetView[0].showGridLines = True
    cf_headers = ["Month (YYYY-MM)", "Inflows", "Fixed Outflows", "Variable Outflows", "Net Savings", "Currency"]
    ws_cf.append(cf_headers)
    apply_header_style(ws_cf, len(cf_headers))

    # Aggregate by calendar month
    monthly_data: Dict[str, Dict[str, int]] = {}
    for tx in txs:
        if not tx.transaction_date or tx.transaction_type == TransactionType.TRANSFER:
            continue
        m_key = tx.transaction_date.strftime("%Y-%m")
        if m_key not in monthly_data:
            monthly_data[m_key] = {"inflow": 0, "fixed": 0, "variable": 0}

        if tx.transaction_type == TransactionType.INCOME:
            monthly_data[m_key]["inflow"] += tx.amount_pence
        elif tx.transaction_type == TransactionType.EXPENSE:
            if tx.expense_nature == ExpenseNature.FIXED:
                monthly_data[m_key]["fixed"] += tx.amount_pence
            else:
                monthly_data[m_key]["variable"] += tx.amount_pence

    sorted_months = sorted(monthly_data.keys(), reverse=True)
    for m in sorted_months:
        d = monthly_data[m]
        in_p = pence_to_pounds(d["inflow"])
        fx_p = pence_to_pounds(d["fixed"])
        vr_p = pence_to_pounds(d["variable"])
        net_p = in_p - fx_p - vr_p
        row = [m, in_p, fx_p, vr_p, net_p, base_curr]
        ws_cf.append(row)
        curr_row = ws_cf.max_row
        for c in range(2, 6):
            ws_cf.cell(row=curr_row, column=c).number_format = "#,##0.00"
        for col_idx in range(1, len(cf_headers) + 1):
            ws_cf.cell(row=curr_row, column=col_idx).border = cell_border

    auto_fit_columns(ws_cf)

    # --- 6. INVESTMENTS SHEET ---
    ws_inv = wb.create_sheet(title="Investments")
    ws_inv.views.sheetView[0].showGridLines = True
    inv_headers = ["ID", "Account Name", "Effective Date", "Valuation", "Currency", "Recorded At", "Notes"]
    ws_inv.append(inv_headers)
    apply_header_style(ws_inv, len(inv_headers))

    snaps = (
        db.query(AssetSnapshot)
        .options(joinedload(AssetSnapshot.account))
        .order_by(AssetSnapshot.effective_date.desc(), AssetSnapshot.id.desc())
        .all()
    )
    for sn in snaps:
        acc_name = sn.account.name if sn.account else "Unknown"
        currency = sn.account.currency if sn.account else base_curr
        eff_str = sn.effective_date.strftime("%Y-%m-%d") if sn.effective_date else ""
        rec_str = sn.created_at.strftime("%Y-%m-%d %H:%M:%S") if sn.created_at else ""
        val_pounds = pence_to_pounds(sn.valuation_pence)
        row = [sn.id, acc_name, eff_str, val_pounds, currency, rec_str, sn.notes or ""]
        ws_inv.append(row)
        curr_row = ws_inv.max_row
        ws_inv.cell(row=curr_row, column=4).number_format = "#,##0.00"
        for col_idx in range(1, len(inv_headers) + 1):
            ws_inv.cell(row=curr_row, column=col_idx).border = cell_border

    auto_fit_columns(ws_inv)

    # --- 7. HOLDINGS SHEET ---
    ws_hold = wb.create_sheet(title="Holdings")
    ws_hold.views.sheetView[0].showGridLines = True
    hold_headers = ["ID", "Account Name", "Holding Name", "Ticker", "Asset Class", "Currency", "Quantity", "Unit Price", "Valuation", "Valuation Date", "Active"]
    ws_hold.append(hold_headers)
    apply_header_style(ws_hold, len(hold_headers))

    from app.core.investments import get_holding_latest_valuation
    holdings = db.query(Holding).options(joinedload(Holding.account)).order_by(Holding.account_id.asc(), Holding.name.asc()).all()
    for h in holdings:
        acc_name = h.account.name if h.account else "Unknown"
        currency = h.currency or (h.account.currency if h.account else base_curr)
        latest = get_holding_latest_valuation(db, h.id)
        if latest:
            qty = float(latest.quantity)
            up_pounds = float((Decimal(str(latest.unit_price_pence)) / Decimal(100)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)) if latest.unit_price_pence is not None else None
            val_pounds = pence_to_pounds(latest.valuation_pence)
            val_date = latest.effective_date.strftime("%Y-%m-%d") if latest.effective_date else ""
        else:
            qty = 0.0
            up_pounds = None
            val_pounds = 0.0
            val_date = ""

        row = [h.id, acc_name, h.name, h.ticker or "", h.asset_class, currency, qty, up_pounds or "", val_pounds, val_date, "Yes" if h.is_active else "No"]
        ws_hold.append(row)
        curr_row = ws_hold.max_row
        ws_hold.cell(row=curr_row, column=7).number_format = "#,##0.0000"
        if up_pounds is not None:
            ws_hold.cell(row=curr_row, column=8).number_format = "#,##0.0000"
        ws_hold.cell(row=curr_row, column=9).number_format = "#,##0.00"
        for col_idx in range(1, len(hold_headers) + 1):
            ws_hold.cell(row=curr_row, column=col_idx).border = cell_border

    auto_fit_columns(ws_hold)

    # --- 8. BALANCE ANCHORS SHEET ---
    ws_anc = wb.create_sheet(title="Balance Anchors")
    ws_anc.views.sheetView[0].showGridLines = True
    anc_headers = ["ID", "Account Name", "Anchor Date (UTC)", "Balance", "Currency", "Opening Anchor", "Notes", "Created At"]
    ws_anc.append(anc_headers)
    apply_header_style(ws_anc, len(anc_headers))

    anchors = (
        db.query(AccountBalanceAnchor)
        .options(joinedload(AccountBalanceAnchor.account))
        .order_by(AccountBalanceAnchor.account_id.asc(), AccountBalanceAnchor.anchor_date.asc())
        .all()
    )
    for a in anchors:
        acc_name = a.account.name if a.account else "Unknown"
        curr = a.account.currency if a.account else base_curr
        dt_str = a.anchor_date.strftime("%Y-%m-%d %H:%M:%S") if a.anchor_date else ""
        cr_str = a.created_at.strftime("%Y-%m-%d %H:%M:%S") if a.created_at else ""
        bal_pounds = pence_to_pounds(a.balance_pence)
        row = [
            a.id,
            acc_name,
            dt_str,
            bal_pounds,
            curr,
            "Yes" if a.is_opening else "No",
            a.notes or "",
            cr_str
        ]
        ws_anc.append(row)
        curr_row = ws_anc.max_row
        ws_anc.cell(row=curr_row, column=4).number_format = "#,##0.00"
        for col_idx in range(1, len(anc_headers) + 1):
            ws_anc.cell(row=curr_row, column=col_idx).border = cell_border

    auto_fit_columns(ws_anc)

    wb.save(target_path)

def generate_backup_bundle(
    db: Session,
    backup_dir: Path = BACKUP_DIR,
    staging_receipts_dir: Path = STAGING_RECEIPTS_DIR,
    archive_receipts_dir: Path = ARCHIVE_RECEIPTS_DIR
) -> Dict[str, Any]:
    """
    Executes the multi-stage validated backup pipeline:
    1. Prepares a sandboxed temporary staging directory.
    2. Runs SQLite VACUUM INTO into database.db.
    3. Verifies PRAGMA integrity_check on the snapshot.
    4. Copies receipts from both staging and permanent archive directories.
    5. Generates human-readable reference Excel workbook (openpyxl).
    6. Writes manifest.json with SHA-256 hashes and metadata.
    7. Assembles portable ZIP archive and verifies CRC32 checksums.
    8. Atomically moves verified ZIP into backup_dir.
    9. Updates system settings and returns verified metadata.
    """
    backup_dir.mkdir(parents=True, exist_ok=True)
    temp_dir = Path(tempfile.mkdtemp(prefix="fh_backup_"))

    try:
        now = datetime.now(timezone.utc)
        timestamp_str = now.strftime("%Y-%m-%d_%H%M%S")
        target_filename = f"finance_hub_backup_{timestamp_str}.zip"
        final_zip_path = backup_dir / target_filename

        # --- Stage 1: SQLite Snapshot via VACUUM INTO ---
        temp_db_path = temp_dir / "database.db"
        # VACUUM INTO requires a clean path string
        db.execute(text(f"VACUUM INTO '{str(temp_db_path)}'"))

        # --- Stage 2: Verify Snapshot Integrity Immediately ---
        if not temp_db_path.exists() or temp_db_path.stat().st_size == 0:
            raise RuntimeError("Database snapshot was not created or is empty.")

        with sqlite3.connect(temp_db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA integrity_check;")
            res = cursor.fetchall()
            if not res or res[0][0] != "ok":
                raise RuntimeError(f"Database snapshot failed integrity check: {res}")
            cursor.execute("PRAGMA quick_check;")
            qres = cursor.fetchall()
            if not qres or qres[0][0] != "ok":
                raise RuntimeError(f"Database snapshot failed quick check: {qres}")

        # --- Stage 3: Mirror Receipts (Staging & Archive) ---
        receipts_staging_dest = temp_dir / "receipts" / "staging"
        receipts_archive_dest = temp_dir / "receipts" / "archive"
        receipts_staging_dest.mkdir(parents=True, exist_ok=True)
        receipts_archive_dest.mkdir(parents=True, exist_ok=True)

        receipt_file_count = 0
        if staging_receipts_dir.exists():
            for p in staging_receipts_dir.rglob("*"):
                if p.is_file() and not p.name.startswith("."):
                    rel = p.relative_to(staging_receipts_dir)
                    target = receipts_staging_dest / rel
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(p, target)
                    receipt_file_count += 1

        if archive_receipts_dir.exists():
            for p in archive_receipts_dir.rglob("*"):
                if p.is_file() and not p.name.startswith("."):
                    rel = p.relative_to(archive_receipts_dir)
                    target = receipts_archive_dest / rel
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(p, target)
                    receipt_file_count += 1

        # --- Stage 4: Generate Reference Excel Report ---
        excel_path = temp_dir / "finance_hub_summary.xlsx"
        generate_reference_workbook(db, excel_path)

        # --- Stage 5: Cryptographic Manifest ---
        sha256_map = {
            "database.db": _compute_sha256(temp_db_path),
            "finance_hub_summary.xlsx": _compute_sha256(excel_path),
        }
        for p in (temp_dir / "receipts").rglob("*"):
            if p.is_file():
                rel = str(p.relative_to(temp_dir))
                sha256_map[rel] = _compute_sha256(p)

        from app.database import get_alembic_head_revision
        schema_rev = None
        try:
            schema_rev = db.execute(text("SELECT version_num FROM alembic_version LIMIT 1")).scalar()
        except Exception:
            schema_rev = None
        if not schema_rev:
            schema_rev = get_alembic_head_revision()

        manifest = {
            "backup_timestamp": now.isoformat(),
            "app_version": "2.0.0",
            "schema_revision": schema_rev,
            "counts": {
                "accounts": db.query(Account).count(),
                "transactions": db.query(Transaction).count(),
                "categories": db.query(Category).count(),
                "asset_snapshots": db.query(AssetSnapshot).count(),
                "holdings": db.query(Holding).count(),
                "holding_valuations": db.query(HoldingValuation).count(),
                "receipt_files": receipt_file_count,
            },
            "sha256": sha256_map
        }
        manifest_path = temp_dir / "manifest.json"
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)

        # --- Stage 6: Assemble ZIP Bundle & Verify Checksums ---
        temp_zip = temp_dir / "bundle.zip"
        with zipfile.ZipFile(temp_zip, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.write(temp_db_path, arcname="database.db")
            zf.write(excel_path, arcname="finance_hub_summary.xlsx")
            zf.write(manifest_path, arcname="manifest.json")
            for p in (temp_dir / "receipts").rglob("*"):
                if p.is_file():
                    arcname = p.relative_to(temp_dir)
                    zf.write(p, arcname=str(arcname))

        # Test ZIP integrity (CRC32 check)
        with zipfile.ZipFile(temp_zip, "r") as zf:
            bad_member = zf.testzip()
            if bad_member is not None:
                raise RuntimeError(f"Corrupt file detected in created ZIP: {bad_member}")

        # --- Stage 7: Atomically Move to Final Backup Directory ---
        shutil.move(str(temp_zip), str(final_zip_path))

        # --- Stage 8: Update Settings in SQLite ---
        set_system_setting(db, "last_successful_backup_at", now.isoformat())

        size_bytes = final_zip_path.stat().st_size
        return {
            "success": True,
            "filename": target_filename,
            "filepath": str(final_zip_path),
            "size_bytes": size_bytes,
            "size_formatted": _format_size(size_bytes),
            "created_at": now,
            "manifest": manifest
        }

    finally:
        # Guarantee cleanup of staging sandbox
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)

def list_existing_backups(backup_dir: Path = BACKUP_DIR) -> List[Dict[str, Any]]:
    """
    Lists all valid dated backups in the archive directory.
    Inspects ZIP headers without extracting the full archive.
    """
    if not backup_dir.exists():
        return []

    backups = []
    for p in backup_dir.glob("*.zip"):
        if not p.is_file():
            continue
        try:
            stat = p.stat()
            size_bytes = stat.st_size
            created_at = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
            manifest = None

            # Attempt to read manifest.json from ZIP
            try:
                with zipfile.ZipFile(p, "r") as zf:
                    if "manifest.json" in zf.namelist():
                        manifest_data = zf.read("manifest.json")
                        manifest = json.loads(manifest_data.decode("utf-8"))
            except Exception:
                pass

            backups.append({
                "filename": p.name,
                "filepath": str(p),
                "created_at": created_at,
                "size_bytes": size_bytes,
                "size_formatted": _format_size(size_bytes),
                "manifest": manifest
            })
        except Exception:
            continue

    backups.sort(key=lambda b: b["created_at"], reverse=True)
    return backups

def compute_next_backup_due_date(last_backup: datetime, frequency_setting: Union[str, int]) -> datetime:
    """
    Computes the exact next backup due timestamp.
    Uses true calendar-month math with natural month-end clamping for monthly and quarterly schedules:
    - Monthly (default, 'monthly' or 30): exactly +1 calendar month (e.g. Jan 31 -> Feb 28/29, Mar 31 -> Apr 30)
    - Quarterly ('quarterly' or 90): exactly +3 calendar months
    - Bi-weekly ('biweekly' or 14): exactly +14 days
    - Generic integer: +N days
    """
    freq_str = str(frequency_setting).lower().strip()
    if freq_str in ("monthly", "30", "1m"):
        return last_backup + relativedelta(months=1)
    elif freq_str in ("quarterly", "90", "3m"):
        return last_backup + relativedelta(months=3)
    elif freq_str in ("biweekly", "14", "2w"):
        return last_backup + timedelta(days=14)
    else:
        try:
            days = int(freq_str)
            return last_backup + timedelta(days=days)
        except ValueError:
            return last_backup + relativedelta(months=1)

def evaluate_backup_schedule(
    db: Session,
    backup_dir: Path = BACKUP_DIR,
    staging_receipts_dir: Path = STAGING_RECEIPTS_DIR,
    archive_receipts_dir: Path = ARCHIVE_RECEIPTS_DIR
) -> Dict[str, Any]:
    """
    Evaluates backup automation state and due schedule with low-noise 24-hour throttling.
    - If automation is OFF and backup is overdue: returns is_overdue=True and overdue_message.
    - If automation is ON and backup is due: triggers generate_backup_bundle and returns updated state.
    """
    enabled_str = get_system_setting(db, "backup_automation_enabled", "false")
    automation_enabled = enabled_str.strip().lower() in ("true", "1", "yes")

    freq_setting = get_system_setting(db, "backup_frequency_days", "30")
    try:
        freq_days = int(freq_setting)
    except ValueError:
        freq_days = 30

    last_check_str = get_system_setting(db, "last_backup_check_at", "")
    last_backup_str = get_system_setting(db, "last_successful_backup_at", "")

    now = datetime.now(timezone.utc)

    # Determine latest backup timestamp from files if setting is empty
    latest_backup_dt: Optional[datetime] = None
    if last_backup_str:
        try:
            latest_backup_dt = datetime.fromisoformat(last_backup_str)
        except Exception:
            pass

    if not latest_backup_dt:
        backups = list_existing_backups(backup_dir)
        if backups:
            latest_backup_dt = backups[0]["created_at"]
            set_system_setting(db, "last_successful_backup_at", latest_backup_dt.isoformat())

    # Check whether a backup is due using true calendar-month math
    is_overdue = False
    next_due_dt: Optional[datetime] = None
    if latest_backup_dt:
        next_due_dt = compute_next_backup_due_date(latest_backup_dt, freq_setting)
        is_overdue = now >= next_due_dt
    else:
        is_overdue = True

    overdue_message = None
    if is_overdue:
        if latest_backup_dt:
            days_since = (now - latest_backup_dt).days
            overdue_message = f"Backup recommended: Last backup was created {days_since} days ago."
        else:
            overdue_message = "Backup recommended: No backups recorded yet."

    # Low-noise throttling: only check automated trigger at most once every 24 hours
    last_check_dt: Optional[datetime] = None
    if last_check_str:
        try:
            last_check_dt = datetime.fromisoformat(last_check_str)
        except Exception:
            pass

    should_check_trigger = True
    if last_check_dt and (now - last_check_dt) < timedelta(hours=24):
        should_check_trigger = False

    if automation_enabled and is_overdue and should_check_trigger:
        # Automatic backup is enabled and due -> execute validated backup
        try:
            generate_backup_bundle(
                db,
                backup_dir=backup_dir,
                staging_receipts_dir=staging_receipts_dir,
                archive_receipts_dir=archive_receipts_dir
            )
            set_system_setting(db, "last_backup_check_at", now.isoformat())
            is_overdue = False
            overdue_message = None
            latest_backup_dt = now
        except Exception as e:
            overdue_message = f"Automatic backup failed: {str(e)}"
    elif should_check_trigger:
        set_system_setting(db, "last_backup_check_at", now.isoformat())

    return {
        "backup_automation_enabled": automation_enabled,
        "backup_frequency_days": freq_days,
        "last_backup_check_at": last_check_dt,
        "last_successful_backup_at": latest_backup_dt,
        "next_backup_due_at": next_due_dt,
        "is_backup_overdue": is_overdue,
        "overdue_message": overdue_message,
        "import_confidence_category": get_system_setting(db, "import_confidence_category", "balanced"),
        "import_confidence_account": get_system_setting(db, "import_confidence_account", "balanced")
    }

