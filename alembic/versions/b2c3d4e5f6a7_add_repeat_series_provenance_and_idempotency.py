"""add_repeat_series_provenance_and_idempotency

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-11-10 15:20:00.000000

NOTE:
Adds nullable provenance column 'repeat_series_id' on 'transactions' and creates
'repeat_series_batches' table for atomic retry/idempotency tracking of multi-occurrence creation.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    tables = set(insp.get_table_names())

    if 'transactions' in tables:
        tx_cols = {c['name']: c for c in insp.get_columns('transactions')}
        tx_indexes = {idx['name'] for idx in insp.get_indexes('transactions')}
        with op.batch_alter_table('transactions', schema=None) as batch_op:
            if 'repeat_series_id' not in tx_cols:
                batch_op.add_column(
                    sa.Column('repeat_series_id', sa.String(length=50), nullable=True)
                )
            if 'ix_transactions_repeat_series_id' not in tx_indexes:
                batch_op.create_index('ix_transactions_repeat_series_id', ['repeat_series_id'], unique=False)

    if 'repeat_series_batches' not in tables:
        op.create_table(
            'repeat_series_batches',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('series_id', sa.String(length=50), nullable=False),
            sa.Column('idempotency_key', sa.String(length=128), nullable=False),
            sa.Column('request_hash', sa.String(length=64), nullable=False),
            sa.Column('occurrence_count', sa.Integer(), nullable=False),
            sa.Column('transaction_ids_json', sa.Text(), nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('series_id'),
            sa.UniqueConstraint('idempotency_key'),
        )
        op.create_index('ix_repeat_series_batches_id', 'repeat_series_batches', ['id'], unique=False)
        op.create_index('ix_repeat_series_batches_series_id', 'repeat_series_batches', ['series_id'], unique=True)
        op.create_index('ix_repeat_series_batches_idempotency_key', 'repeat_series_batches', ['idempotency_key'], unique=True)


def downgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    tables = set(insp.get_table_names())

    if 'repeat_series_batches' in tables:
        op.drop_table('repeat_series_batches')

    if 'transactions' in tables:
        tx_cols = {c['name']: c for c in insp.get_columns('transactions')}
        tx_indexes = {idx['name'] for idx in insp.get_indexes('transactions')}
        if 'repeat_series_id' in tx_cols or 'ix_transactions_repeat_series_id' in tx_indexes:
            with op.batch_alter_table('transactions', schema=None) as batch_op:
                if 'ix_transactions_repeat_series_id' in tx_indexes:
                    batch_op.drop_index('ix_transactions_repeat_series_id')
                if 'repeat_series_id' in tx_cols:
                    batch_op.drop_column('repeat_series_id')
