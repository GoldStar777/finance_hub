"""add_holdings_and_valuation_mode

Revision ID: 8d1f2a3c4b5e
Revises: 57ad957569a1
Create Date: 2026-10-21 17:30:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '8d1f2a3c4b5e'
down_revision: Union[str, Sequence[str], None] = '57ad957569a1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    tables = set(insp.get_table_names())

    # 1. Verification & creation for accounts.valuation_mode
    if 'accounts' not in tables:
        raise RuntimeError("Expected baseline table 'accounts' does not exist.")

    account_cols = {c['name']: c for c in insp.get_columns('accounts')}
    if 'valuation_mode' not in account_cols:
        with op.batch_alter_table('accounts', schema=None) as batch_op:
            batch_op.add_column(
                sa.Column('valuation_mode', sa.String(length=20), server_default='snapshot', nullable=False)
            )
    else:
        # Verify existing column structure
        c = account_cols['valuation_mode']
        type_str = str(c['type']).upper()
        if 'VARCHAR' not in type_str and 'STRING' not in type_str and 'TEXT' not in type_str:
            raise RuntimeError(f"Existing column accounts.valuation_mode has unexpected type: {c['type']}")

    # 2. Verification & creation for holdings table
    if 'holdings' not in tables:
        op.create_table(
            'holdings',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('account_id', sa.Integer(), nullable=False),
            sa.Column('name', sa.String(length=150), nullable=False),
            sa.Column('ticker', sa.String(length=30), nullable=True),
            sa.Column('asset_class', sa.String(length=50), server_default='equity', nullable=False),
            sa.Column('currency', sa.String(length=3), server_default='GBP', nullable=False),
            sa.Column('is_active', sa.Boolean(), server_default='1', nullable=False),
            sa.Column('notes', sa.Text(), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
            sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_holdings_id'), 'holdings', ['id'], unique=False)
        op.create_index(op.f('ix_holdings_account_id'), 'holdings', ['account_id'], unique=False)
    else:
        # Verify existing table structure
        hold_cols = {c['name']: c for c in insp.get_columns('holdings')}
        expected_hold_cols = {'id', 'account_id', 'name', 'ticker', 'asset_class', 'currency', 'is_active', 'notes', 'created_at'}
        missing = expected_hold_cols - set(hold_cols.keys())
        if missing:
            raise RuntimeError(f"Existing table 'holdings' is missing required columns: {missing}")
        
        # Ensure indexes exist
        hold_indexes = {ix['name'] for ix in insp.get_indexes('holdings')}
        if op.f('ix_holdings_id') not in hold_indexes and 'ix_holdings_id' not in hold_indexes:
            try:
                op.create_index(op.f('ix_holdings_id'), 'holdings', ['id'], unique=False)
            except Exception:
                pass
        if op.f('ix_holdings_account_id') not in hold_indexes and 'ix_holdings_account_id' not in hold_indexes:
            try:
                op.create_index(op.f('ix_holdings_account_id'), 'holdings', ['account_id'], unique=False)
            except Exception:
                pass

    # 3. Verification & creation for holding_valuations table
    if 'holding_valuations' not in tables:
        op.create_table(
            'holding_valuations',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('holding_id', sa.Integer(), nullable=False),
            sa.Column('effective_date', sa.DateTime(timezone=True), nullable=False),
            sa.Column('quantity', sa.Numeric(precision=18, scale=8), nullable=False),
            sa.Column('unit_price_pence', sa.Numeric(precision=14, scale=4), nullable=True),
            sa.Column('valuation_pence', sa.Integer(), nullable=False),
            sa.Column('notes', sa.String(length=255), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
            sa.CheckConstraint('quantity >= 0', name='check_positive_quantity'),
            sa.CheckConstraint('valuation_pence >= 0', name='check_positive_holding_valuation'),
            sa.ForeignKeyConstraint(['holding_id'], ['holdings.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_holding_valuations_id'), 'holding_valuations', ['id'], unique=False)
        op.create_index(op.f('ix_holding_valuations_holding_id'), 'holding_valuations', ['holding_id'], unique=False)
        op.create_index(op.f('ix_holding_valuations_effective_date'), 'holding_valuations', ['effective_date'], unique=False)
    else:
        # Verify existing table structure
        val_cols = {c['name']: c for c in insp.get_columns('holding_valuations')}
        expected_val_cols = {'id', 'holding_id', 'effective_date', 'quantity', 'unit_price_pence', 'valuation_pence', 'notes', 'created_at'}
        missing = expected_val_cols - set(val_cols.keys())
        if missing:
            raise RuntimeError(f"Existing table 'holding_valuations' is missing required columns: {missing}")

        val_indexes = {ix['name'] for ix in insp.get_indexes('holding_valuations')}
        if op.f('ix_holding_valuations_id') not in val_indexes and 'ix_holding_valuations_id' not in val_indexes:
            try:
                op.create_index(op.f('ix_holding_valuations_id'), 'holding_valuations', ['id'], unique=False)
            except Exception:
                pass
        if op.f('ix_holding_valuations_holding_id') not in val_indexes and 'ix_holding_valuations_holding_id' not in val_indexes:
            try:
                op.create_index(op.f('ix_holding_valuations_holding_id'), 'holding_valuations', ['holding_id'], unique=False)
            except Exception:
                pass
        if op.f('ix_holding_valuations_effective_date') not in val_indexes and 'ix_holding_valuations_effective_date' not in val_indexes:
            try:
                op.create_index(op.f('ix_holding_valuations_effective_date'), 'holding_valuations', ['effective_date'], unique=False)
            except Exception:
                pass

    # 4. Final verification: Ensure entire expected schema is verified before completing
    final_insp = sa.inspect(conn)
    final_tables = set(final_insp.get_table_names())
    final_acc_cols = {c['name'] for c in final_insp.get_columns('accounts')}
    if 'holdings' not in final_tables:
        raise RuntimeError("Final verification failed: 'holdings' table not present.")
    if 'holding_valuations' not in final_tables:
        raise RuntimeError("Final verification failed: 'holding_valuations' table not present.")
    if 'valuation_mode' not in final_acc_cols:
        raise RuntimeError("Final verification failed: 'accounts.valuation_mode' column not present.")

def downgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    tables = set(insp.get_table_names())

    if 'holding_valuations' in tables:
        val_indexes = {ix['name'] for ix in insp.get_indexes('holding_valuations')}
        if op.f('ix_holding_valuations_effective_date') in val_indexes:
            op.drop_index(op.f('ix_holding_valuations_effective_date'), table_name='holding_valuations')
        if op.f('ix_holding_valuations_holding_id') in val_indexes:
            op.drop_index(op.f('ix_holding_valuations_holding_id'), table_name='holding_valuations')
        if op.f('ix_holding_valuations_id') in val_indexes:
            op.drop_index(op.f('ix_holding_valuations_id'), table_name='holding_valuations')
        op.drop_table('holding_valuations')

    if 'holdings' in tables:
        hold_indexes = {ix['name'] for ix in insp.get_indexes('holdings')}
        if op.f('ix_holdings_account_id') in hold_indexes:
            op.drop_index(op.f('ix_holdings_account_id'), table_name='holdings')
        if op.f('ix_holdings_id') in hold_indexes:
            op.drop_index(op.f('ix_holdings_id'), table_name='holdings')
        op.drop_table('holdings')

    insp_after = sa.inspect(conn)
    if 'accounts' in set(insp_after.get_table_names()):
        account_cols = {c['name'] for c in insp_after.get_columns('accounts')}
        if 'valuation_mode' in account_cols:
            with op.batch_alter_table('accounts', schema=None) as batch_op:
                batch_op.drop_column('valuation_mode')
