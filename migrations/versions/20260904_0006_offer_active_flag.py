"""add active flag to offers

Revision ID: 20260904_0006
Revises: 20260903_0005
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260904_0006"
down_revision: Union[str, None] = "20260903_0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("offers") as batch_op:
        batch_op.add_column(sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()))


def downgrade() -> None:
    with op.batch_alter_table("offers") as batch_op:
        batch_op.drop_column("active")
