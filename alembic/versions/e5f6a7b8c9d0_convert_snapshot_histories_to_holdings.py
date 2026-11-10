"""convert_snapshot_histories_to_holdings

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-10-22 02:25:00.000000

One-time, idempotent migration for holdings-only investment model:
- For investment accounts with AssetSnapshot history but NO holdings, creates a single
  synthetic holding ('Portfolio Valuation', asset_class='portfolio', quantity=1.0)
  with matching historical dated valuations.
- For investment accounts that already have detailed holdings (such as AJ Bell LISA),
  preserves them as the sole source of truth and creates NO synthetic holdings.
- Sets valuation_mode = 'holdings' on investment accounts.
"""
from typing import Sequence, Union
from datetime import datetime, timezone
from decimal import Decimal
from alembic import op
import sqlalchemy as sa

revision: str = 'e5f6a7b8c9d0'
down_revision: Union[str, Sequence[str], None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    tables = set(insp.get_table_names())

    if not {"accounts", "holdings", "holding_valuations", "asset_snapshots"}.issubset(tables):
        return

    # 1. Fetch all investment accounts
    accounts = conn.execute(sa.text("""
        SELECT id, name, currency FROM accounts 
        WHERE LOWER(account_type) = 'investment'
    """)).fetchall()

    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    for acc_row in accounts:
        acc_id = acc_row[0]
        acc_curr = acc_row[2] or "GBP"

        # Check if account already has holdings
        h_count = conn.execute(
            sa.text("SELECT count(*) FROM holdings WHERE account_id = :acc_id"),
            {"acc_id": acc_id}
        ).scalar() or 0

        if h_count > 0:
            # Already has holdings: do not create synthetic holding
            continue

        # Check if account has asset snapshots
        snaps = conn.execute(
            sa.text("""
                SELECT id, effective_date, valuation_pence, notes 
                FROM asset_snapshots 
                WHERE account_id = :acc_id 
                ORDER BY effective_date ASC, id ASC
            """),
            {"acc_id": acc_id}
        ).fetchall()

        if not snaps:
            continue

        # Check if synthetic holding already exists (idempotency)
        existing_synth = conn.execute(
            sa.text("SELECT id FROM holdings WHERE account_id = :acc_id AND name = 'Portfolio Valuation'"),
            {"acc_id": acc_id}
        ).fetchone()

        if existing_synth:
            synth_id = existing_synth[0]
        else:
            conn.execute(
                sa.text("""
                    INSERT INTO holdings (account_id, name, ticker, asset_class, currency, is_active, notes, created_at)
                    VALUES (:acc_id, 'Portfolio Valuation', NULL, 'portfolio', :curr, 1, 'Synthetic holding migrated from historical account snapshots', :created_at)
                """),
                {
                    "acc_id": acc_id,
                    "curr": acc_curr,
                    "created_at": snaps[0][1] if snaps[0][1] else now_str
                }
            )
            synth_id = conn.execute(
                sa.text("SELECT id FROM holdings WHERE account_id = :acc_id AND name = 'Portfolio Valuation'"),
                {"acc_id": acc_id}
            ).scalar()

        # Insert valuations for snapshots that haven't been migrated yet
        for snap in snaps:
            snap_eff = snap[1]
            snap_val = snap[2]
            snap_notes = snap[3] or "Migrated from historical asset snapshot"

            exists = conn.execute(
                sa.text("""
                    SELECT id FROM holding_valuations 
                    WHERE holding_id = :h_id AND effective_date = :eff_dt
                """),
                {"h_id": synth_id, "eff_dt": snap_eff}
            ).fetchone()

            if not exists:
                conn.execute(
                    sa.text("""
                        INSERT INTO holding_valuations (holding_id, effective_date, quantity, unit_price_pence, valuation_pence, notes, created_at)
                        VALUES (:h_id, :eff_dt, 1.0, :up, :vp, :notes, :created_at)
                    """),
                    {
                        "h_id": synth_id,
                        "eff_dt": snap_eff,
                        "up": snap_val,
                        "vp": snap_val,
                        "notes": snap_notes,
                        "created_at": now_str
                    }
                )

    # 2. Update valuation_mode to 'holdings' on all investment accounts
    conn.execute(sa.text("""
        UPDATE accounts SET valuation_mode = 'holdings' 
        WHERE LOWER(account_type) = 'investment'
    """))

def downgrade() -> None:
    # Safe no-op: does not drop user data on downgrade
    pass

