"""add missing campaign status index

Revision ID: 20260903_0005
Revises: 20260903_0004
"""
from typing import Sequence, Union

from alembic import op

revision: str = "20260903_0005"
down_revision: Union[str, None] = "20260903_0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index("ix_campaigns_status", "campaigns", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_campaigns_status", table_name="campaigns")