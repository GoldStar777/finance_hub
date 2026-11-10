"""add_deleted_at_to_transactions

Revision ID: a1b2c3d4e5f6
Revises: f6a7b8c9d0e1
Create Date: 2026-11-09 23:10:00.000000

NOTE:
Adds 'deleted_at' and 'deletion_batch_id' columns to 'transactions' table to support
reversible soft-deletion, batch undo, and Recently Deleted recovery.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'f6a7b8c9d0e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    tables = set(insp.get_table_names())

    if 'transactions' in tables:
        tx_cols = {c['name']: c for c in insp.get_columns('transactions')}

        with op.batch_alter_table('transactions', schema=None) as batch_op:
            if 'deleted_at' not in tx_cols:
                batch_op.add_column(
                    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True)
                )
            if 'deletion_batch_id' not in tx_cols:
                batch_op.add_column(
                    sa.Column('deletion_batch_id', sa.String(length=50), nullable=True)
                )

def downgrade() -> None:
    """
    WARNING: Drops soft-deletion and batch columns.
    """
    conn = op.get_bind()
    insp = sa.inspect(conn)
    tables = set(insp.get_table_names())

    if 'transactions' in tables:
        tx_cols = {c['name']: c for c in insp.get_columns('transactions')}
        with op.batch_alter_table('transactions', schema=None) as batch_op:
            if 'deletion_batch_id' in tx_cols:
                batch_op.drop_column('deletion_batch_id')
            if 'deleted_at' in tx_cols:
                batch_op.drop_column('deleted_at')
