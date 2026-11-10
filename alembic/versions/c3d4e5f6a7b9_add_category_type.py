"""add_category_type

Revision ID: c3d4e5f6a7b9
Revises: b2c3d4e5f6a7
Create Date: 2026-11-10 16:00:00.000000

NOTE:
Adds 'category_type' column ('EXPENSE' | 'INCOME') to 'categories' table,
deterministically defaulting all existing categories to 'EXPENSE'.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'c3d4e5f6a7b9'
down_revision: Union[str, Sequence[str], None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    tables = set(insp.get_table_names())

    if 'categories' in tables:
        cat_cols = {c['name']: c for c in insp.get_columns('categories')}
        if 'category_type' not in cat_cols:
            with op.batch_alter_table('categories', schema=None) as batch_op:
                batch_op.add_column(
                    sa.Column('category_type', sa.String(length=10), nullable=False, server_default='EXPENSE')
                )
        conn.execute(
            sa.text(
                "UPDATE categories SET category_type = 'EXPENSE' "
                "WHERE category_type IS NULL OR TRIM(category_type) = ''"
            )
        )


def downgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    tables = set(insp.get_table_names())

    if 'categories' in tables:
        cat_cols = {c['name']: c for c in insp.get_columns('categories')}
        if 'category_type' in cat_cols:
            with op.batch_alter_table('categories', schema=None) as batch_op:
                batch_op.drop_column('category_type')
