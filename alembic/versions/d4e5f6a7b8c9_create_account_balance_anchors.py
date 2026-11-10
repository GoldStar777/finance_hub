"""create_account_balance_anchors

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-10-21 23:55:00.000000

NOTE ON DOWNGRADE:
Downgrading this migration removes checkpoint balance anchors and drops 'effective_timestamp'.
Pre-migration starting balances are restored from opening anchors, but subsequent non-opening
checkpoints, intraday ordering timestamps, and staging anchor resolution flags will be permanently
deleted. Canonical ledger balances remain preserved, but multi-anchor history cannot be recovered
without restoring from a verified database backup. Always preserve a verified backup before
applying or reverting database migrations.
"""
from typing import Sequence, Union
from datetime import datetime, timedelta, timezone
from alembic import op
import sqlalchemy as sa

revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, Sequence[str], None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    tables = set(insp.get_table_names())

    # 1. Create account_balance_anchors table if missing
    if 'account_balance_anchors' not in tables:
        op.create_table(
            'account_balance_anchors',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
            sa.Column('account_id', sa.Integer(), sa.ForeignKey('accounts.id', ondelete='CASCADE'), nullable=False),
            sa.Column('balance_pence', sa.Integer(), nullable=False),
            sa.Column('anchor_date', sa.DateTime(timezone=True), nullable=False),
            sa.Column('is_opening', sa.Boolean(), nullable=False, server_default=sa.text('0')),
            sa.Column('notes', sa.String(length=255), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        )
        op.create_index('ix_account_balance_anchors_id', 'account_balance_anchors', ['id'])
        op.create_index('ix_account_balance_anchors_account_id', 'account_balance_anchors', ['account_id'])
        op.create_index('ix_account_balance_anchors_anchor_date', 'account_balance_anchors', ['anchor_date'])

    # 2. Add effective_timestamp and created_at to transactions table if missing, and permit unassigned/unknown details
    if 'transactions' in tables:
        tx_cols = {c['name']: c for c in insp.get_columns('transactions')}
        with op.batch_alter_table('transactions', schema=None) as batch_op:
            if 'effective_timestamp' not in tx_cols:
                batch_op.add_column(
                    sa.Column('effective_timestamp', sa.DateTime(timezone=True), nullable=True)
                )
            if 'created_at' not in tx_cols:
                # Legacy transactions have unknown entry timestamps; preserve as NULL rather than masquerading migration time as historical truth
                batch_op.add_column(
                    sa.Column('created_at', sa.DateTime(timezone=True), nullable=True)
                )
            # Support optional/unassigned account and unrecorded merchant
            batch_op.alter_column('account_id', existing_type=sa.Integer(), nullable=True)
            batch_op.alter_column('merchant', existing_type=sa.String(length=255), nullable=True)
        if 'effective_timestamp' not in tx_cols:
            op.create_index('ix_transactions_effective_timestamp', 'transactions', ['effective_timestamp'])
        # Guarantee all existing rows backfill effective_timestamp from transaction_date
        op.execute("UPDATE transactions SET effective_timestamp = transaction_date WHERE effective_timestamp IS NULL")

    # 3. Add effective_timestamp and anchor_mode to staging_items table if missing
    if 'staging_items' in tables:
        stg_cols = {c['name']: c for c in insp.get_columns('staging_items')}
        with op.batch_alter_table('staging_items', schema=None) as batch_op:
            if 'effective_timestamp' not in stg_cols:
                batch_op.add_column(
                    sa.Column('effective_timestamp', sa.DateTime(timezone=True), nullable=True)
                )
            if 'anchor_mode' not in stg_cols:
                batch_op.add_column(
                    sa.Column('anchor_mode', sa.String(length=20), nullable=False, server_default=sa.text("'auto'"))
                )

    # 4. Migrate existing starting balances into opening balance anchors
    if 'accounts' in tables:
        acc_cols = {c['name']: c for c in insp.get_columns('accounts')}
        if 'starting_balance_pence' in acc_cols:
            # Query all accounts
            accounts = conn.execute(sa.text("SELECT id, starting_balance_pence, created_at FROM accounts")).fetchall()
            for acc in accounts:
                acc_id = acc[0]
                start_pence = acc[1] or 0
                acc_created = acc[2]

                # Check if an opening anchor already exists
                has_anchor = conn.execute(
                    sa.text("SELECT id FROM account_balance_anchors WHERE account_id = :acc_id"),
                    {"acc_id": acc_id}
                ).fetchone()

                if not has_anchor:
                    # Balance Preservation Formula:
                    # Find min transaction_date for this account
                    min_tx = None
                    if 'transactions' in tables:
                        min_tx_row = conn.execute(
                            sa.text("SELECT MIN(transaction_date) FROM transactions WHERE account_id = :acc_id OR destination_account_id = :acc_id"),
                            {"acc_id": acc_id}
                        ).fetchone()
                        min_tx = min_tx_row[0] if min_tx_row else None

                    # Calculate anchor_date strictly < min_tx to guarantee identical calculated balance
                    if min_tx:
                        if isinstance(min_tx, str):
                            try:
                                min_dt = datetime.fromisoformat(min_tx.replace("Z", "+00:00"))
                            except Exception:
                                min_dt = datetime.now(timezone.utc)
                        else:
                            min_dt = min_tx

                        anchor_dt = min_dt - timedelta(seconds=1)
                        if acc_created:
                            if isinstance(acc_created, str):
                                try:
                                    cr_dt = datetime.fromisoformat(acc_created.replace("Z", "+00:00"))
                                except Exception:
                                    cr_dt = min_dt
                            else:
                                cr_dt = acc_created
                            anchor_dt = min(anchor_dt, cr_dt)
                    else:
                        if acc_created:
                            if isinstance(acc_created, str):
                                try:
                                    anchor_dt = datetime.fromisoformat(acc_created.replace("Z", "+00:00"))
                                except Exception:
                                    anchor_dt = datetime.now(timezone.utc)
                            else:
                                anchor_dt = acc_created
                        else:
                            anchor_dt = datetime.now(timezone.utc)

                    conn.execute(
                        sa.text("""
                            INSERT INTO account_balance_anchors (account_id, balance_pence, anchor_date, is_opening, notes, created_at)
                            VALUES (:acc_id, :bal, :dt, 1, 'Migrated starting balance anchor', CURRENT_TIMESTAMP)
                        """),
                        {"acc_id": acc_id, "bal": start_pence, "dt": anchor_dt.isoformat() if hasattr(anchor_dt, "isoformat") else str(anchor_dt)}
                    )

            # Alter starting_balance_pence to nullable=True for backward compatibility
            with op.batch_alter_table('accounts', schema=None) as batch_op:
                batch_op.alter_column('starting_balance_pence', nullable=True, server_default=sa.text('0'))

def downgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    tables = set(insp.get_table_names())

    if 'accounts' in tables:
        acc_cols = {c['name']: c for c in insp.get_columns('accounts')}
        if 'starting_balance_pence' not in acc_cols:
            with op.batch_alter_table('accounts', schema=None) as batch_op:
                batch_op.add_column(
                    sa.Column('starting_balance_pence', sa.Integer(), nullable=False, server_default=sa.text('0'))
                )
            # Restore starting_balance_pence from opening anchor
            if 'account_balance_anchors' in tables:
                op.execute("""
                    UPDATE accounts SET starting_balance_pence = COALESCE(
                        (SELECT balance_pence FROM account_balance_anchors WHERE account_balance_anchors.account_id = accounts.id AND is_opening = 1 ORDER BY anchor_date ASC LIMIT 1),
                        0
                    )
                """)

    if 'staging_items' in tables:
        stg_cols = {c['name']: c for c in insp.get_columns('staging_items')}
        with op.batch_alter_table('staging_items', schema=None) as batch_op:
            if 'anchor_mode' in stg_cols:
                batch_op.drop_column('anchor_mode')
            if 'effective_timestamp' in stg_cols:
                batch_op.drop_column('effective_timestamp')

    if 'transactions' in tables:
        tx_cols = {c['name']: c for c in insp.get_columns('transactions')}
        with op.batch_alter_table('transactions', schema=None) as batch_op:
            if 'effective_timestamp' in tx_cols:
                batch_op.drop_column('effective_timestamp')
            if 'created_at' in tx_cols:
                batch_op.drop_column('created_at')

    if 'account_balance_anchors' in tables:
        op.drop_table('account_balance_anchors')
