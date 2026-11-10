"""initial_foundation_schema

Revision ID: 57ad957569a1
Revises: 
Create Date: 2026-10-21 03:12:38.450460

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '57ad957569a1'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    # 1. Accounts
    with op.batch_alter_table('accounts', schema=None) as batch_op:
        batch_op.add_column(sa.Column('starting_balance_pence', sa.Integer(), nullable=True))
    op.execute("UPDATE accounts SET starting_balance_pence = CAST(ROUND(COALESCE(starting_balance, 0) * 100) AS INTEGER)")
    with op.batch_alter_table('accounts', schema=None) as batch_op:
        batch_op.alter_column('starting_balance_pence', nullable=False)
        batch_op.drop_column('starting_balance')

    # 2. Categories
    with op.batch_alter_table('categories', schema=None) as batch_op:
        batch_op.add_column(sa.Column('default_expense_nature', sa.Enum('FIXED', 'VARIABLE', 'UNCLASSIFIED', name='expensenature'), nullable=True))
    op.execute("UPDATE categories SET default_expense_nature = 'UNCLASSIFIED'")
    with op.batch_alter_table('categories', schema=None) as batch_op:
        batch_op.alter_column('default_expense_nature', nullable=False)
        try:
            batch_op.drop_column('icon')
        except Exception:
            pass
        try:
            batch_op.drop_column('is_income')
        except Exception:
            pass

    # 3. Transactions
    with op.batch_alter_table('transactions', schema=None) as batch_op:
        batch_op.add_column(sa.Column('amount_pence', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('receipt_path', sa.String(length=500), nullable=True))
        batch_op.add_column(sa.Column('expense_nature', sa.Enum('FIXED', 'VARIABLE', 'UNCLASSIFIED', name='expensenature'), nullable=True))
    op.execute("UPDATE transactions SET amount_pence = CAST(ROUND(ABS(COALESCE(amount, 0)) * 100) AS INTEGER), expense_nature = 'UNCLASSIFIED'")
    with op.batch_alter_table('transactions', schema=None) as batch_op:
        batch_op.alter_column('amount_pence', nullable=False)
        batch_op.alter_column('expense_nature', nullable=False)
        try:
            batch_op.drop_column('source_file_path')
        except Exception:
            pass
        try:
            batch_op.drop_column('amount')
        except Exception:
            pass

    # 4. Account Snapshots
    with op.batch_alter_table('account_snapshots', schema=None) as batch_op:
        batch_op.add_column(sa.Column('actual_balance_pence', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('calculated_balance_pence', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('discrepancy_pence', sa.Integer(), nullable=True))
    op.execute("""
        UPDATE account_snapshots SET 
            actual_balance_pence = CAST(ROUND(COALESCE(actual_balance, 0) * 100) AS INTEGER),
            calculated_balance_pence = CAST(ROUND(COALESCE(calculated_balance, 0) * 100) AS INTEGER),
            discrepancy_pence = CAST(ROUND(COALESCE(discrepancy, 0) * 100) AS INTEGER)
    """)
    with op.batch_alter_table('account_snapshots', schema=None) as batch_op:
        batch_op.alter_column('actual_balance_pence', nullable=False)
        batch_op.alter_column('calculated_balance_pence', nullable=False)
        batch_op.alter_column('discrepancy_pence', nullable=False)
        try:
            batch_op.drop_column('actual_balance')
            batch_op.drop_column('calculated_balance')
            batch_op.drop_column('discrepancy')
        except Exception:
            pass

    # 5. Staging Items
    with op.batch_alter_table('staging_items', schema=None) as batch_op:
        batch_op.add_column(sa.Column('extracted_amount_pence', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('suggested_expense_nature', sa.Enum('FIXED', 'VARIABLE', 'UNCLASSIFIED', name='expensenature'), nullable=True))
    op.execute("UPDATE staging_items SET extracted_amount_pence = CAST(ROUND(COALESCE(extracted_amount, 0) * 100) AS INTEGER), suggested_expense_nature = 'UNCLASSIFIED'")
    with op.batch_alter_table('staging_items', schema=None) as batch_op:
        batch_op.alter_column('suggested_expense_nature', nullable=False)
        try:
            batch_op.drop_column('extracted_amount')
        except Exception:
            pass

    # 6. Create AssetSnapshots table if not exists
    op.execute("""
        CREATE TABLE IF NOT EXISTS asset_snapshots (
            id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
            account_id INTEGER NOT NULL,
            valuation_pence INTEGER NOT NULL,
            effective_date DATETIME NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            notes VARCHAR(255),
            FOREIGN KEY (account_id) REFERENCES accounts (id) ON DELETE CASCADE
        )
    """)

def downgrade() -> None:
    pass
