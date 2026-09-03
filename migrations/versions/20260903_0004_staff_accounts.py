"""add internal staff accounts"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
revision: str = "20260903_0004"
down_revision: Union[str, None] = "20260903_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None
def upgrade() -> None:
    op.create_table("staff_users", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("username", sa.String(100), nullable=False, unique=True), sa.Column("password_hash", sa.String(255), nullable=False), sa.Column("role", sa.String(20), nullable=False, server_default="staff"), sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()), sa.Column("created_at", sa.DateTime(), nullable=False))
    op.create_index("ix_staff_users_username", "staff_users", ["username"], unique=True)
    op.create_index("ix_staff_users_role", "staff_users", ["role"])
def downgrade() -> None:
    op.drop_index("ix_staff_users_role", table_name="staff_users")
    op.drop_index("ix_staff_users_username", table_name="staff_users")
    op.drop_table("staff_users")
