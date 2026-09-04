"""add beneficiary category to patient offers

Revision ID: 20260904_0007
Revises: 20260904_0006
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260904_0007"
down_revision: Union[str, None] = "20260904_0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ALL_CATEGORY_VALUES = ("CAPF", "CGHS", "CISF", "DU", "ECHS", "NHAI", "NOT_APPLICABLE", "UNSPECIFIED")


def upgrade() -> None:
    with op.batch_alter_table("patient_offers", recreate="always") as batch_op:
        batch_op.add_column(sa.Column("beneficiary_category", sa.String(20), nullable=True))

    op.execute("UPDATE patient_offers SET beneficiary_category = 'UNSPECIFIED' WHERE beneficiary_category IS NULL")

    with op.batch_alter_table("patient_offers", recreate="always") as batch_op:
        batch_op.alter_column("beneficiary_category", existing_type=sa.String(20), nullable=False)
        batch_op.create_index("ix_patient_offers_beneficiary_category", ["beneficiary_category"], unique=False)
        batch_op.create_check_constraint(
            "ck_patient_offers_beneficiary_category",
            "beneficiary_category IN (" + ", ".join(f"'{value}'" for value in ALL_CATEGORY_VALUES) + ")",
        )


def downgrade() -> None:
    with op.batch_alter_table("patient_offers", recreate="always") as batch_op:
        batch_op.drop_constraint("ck_patient_offers_beneficiary_category", type_="check")
        batch_op.drop_index("ix_patient_offers_beneficiary_category")
        batch_op.drop_column("beneficiary_category")
