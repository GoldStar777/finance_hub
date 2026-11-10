"""add_category_description

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-10-22 21:50:00.000000

"""
import json
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'f6a7b8c9d0e1'
down_revision: Union[str, Sequence[str], None] = 'e5f6a7b8c9d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    tables = set(insp.get_table_names())

    if 'categories' not in tables:
        return

    cat_cols = {c['name']: c for c in insp.get_columns('categories')}
    if 'description' not in cat_cols:
        with op.batch_alter_table('categories', schema=None) as batch_op:
            batch_op.add_column(
                sa.Column('description', sa.String(length=500), nullable=True)
            )

        # Migrate any descriptions existing in system_settings into categories.description
        if 'system_settings' in tables:
            try:
                row = conn.execute(
                    sa.text("SELECT value FROM system_settings WHERE key = 'category_descriptions'")
                ).fetchone()
                if row and row[0]:
                    descs = json.loads(row[0])
                    for cat_id_str, desc in descs.items():
                        if desc and str(desc).strip():
                            conn.execute(
                                sa.text("UPDATE categories SET description = :desc WHERE id = :id"),
                                {"desc": str(desc).strip(), "id": int(cat_id_str)}
                            )
            except Exception:
                pass

def downgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    tables = set(insp.get_table_names())
    if 'categories' in tables:
        cat_cols = {c['name']: c for c in insp.get_columns('categories')}
        if 'description' in cat_cols:
            with op.batch_alter_table('categories', schema=None) as batch_op:
                batch_op.drop_column('description')

