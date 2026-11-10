"""add_foreign_currency_origin_to_transactions

Revision ID: c3d4e5f6a7b8
Revises: 8d1f2a3c4b5e
Create Date: 2026-10-21 21:20:00.000000

NOTE ON DOWNGRADE:
Downgrading this migration drops 'original_amount', 'original_currency', and 'exchange_rate'
from the 'transactions' table. Any foreign transaction provenance metadata entered while
this migration was active will be permanently deleted. Canonical ledger amounts
(amount_pence) and account balances remain intact, but foreign origin currency and rate
history cannot be recovered without restoring from a verified database backup.
Always ensure a verified backup exists before applying migrations or downgrades.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, Sequence[str], None] = '8d1f2a3c4b5e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    tables = set(insp.get_table_names())

    if 'transactions' in tables:
        tx_cols = {c['name']: c for c in insp.get_columns('transactions')}

        with op.batch_alter_table('transactions', schema=None) as batch_op:
            if 'original_amount' not in tx_cols:
                batch_op.add_column(
                    sa.Column('original_amount', sa.Numeric(precision=18, scale=4), nullable=True)
                )
            if 'original_currency' not in tx_cols:
                batch_op.add_column(
                    sa.Column('original_currency', sa.String(length=3), nullable=True)
                )
            if 'exchange_rate' not in tx_cols:
                batch_op.add_column(
                    sa.Column('exchange_rate', sa.Numeric(precision=18, scale=8), nullable=True)
                )

    # Ensure system_settings has base_currency initialized if missing
    if 'system_settings' in tables:
        res = conn.execute(
            sa.text("SELECT value FROM system_settings WHERE key = 'base_currency'")
        ).fetchone()
        if not res:
            conn.execute(
                sa.text("INSERT INTO system_settings (key, value) VALUES ('base_currency', 'GBP')")
            )

def downgrade() -> None:
    """
    WARNING: Drops foreign transaction provenance columns.
    Any recorded original amounts, currencies, and exchange rates will be deleted.
    """
    conn = op.get_bind()
    insp = sa.inspect(conn)
    tables = set(insp.get_table_names())

    if 'transactions' in tables:
        tx_cols = {c['name']: c for c in insp.get_columns('transactions')}
        with op.batch_alter_table('transactions', schema=None) as batch_op:
            if 'exchange_rate' in tx_cols:
                batch_op.drop_column('exchange_rate')
            if 'original_currency' in tx_cols:
                batch_op.drop_column('original_currency')
            if 'original_amount' in tx_cols:
                batch_op.drop_column('original_amount')
