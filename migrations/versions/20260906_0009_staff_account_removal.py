"""add removed_at to staff_users for safe removal (soft-delete)

Revision ID: 20260906_0009
Revises: 20260905_0008
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260906_0009"
down_revision: Union[str, None] = "20260905_0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("staff_users") as batch_op:
        batch_op.add_column(sa.Column("removed_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("staff_users") as batch_op:
        batch_op.drop_column("removed_at")
