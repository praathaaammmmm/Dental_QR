"""add admin CRM campaigns and delivery metadata

Revision ID: 20260903_0003
Revises: 20260902_0002
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260903_0003"
down_revision: Union[str, None] = "20260902_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "campaigns",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(150), nullable=False, unique=True),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="DRAFT"),
        sa.Column("created_by", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "campaign_offers",
        sa.Column("campaign_id", sa.Integer(), sa.ForeignKey("campaigns.id"), primary_key=True),
        sa.Column("offer_id", sa.Integer(), sa.ForeignKey("offers.id"), primary_key=True),
    )
    with op.batch_alter_table("patient_offers", recreate="always") as batch_op:
        batch_op.add_column(sa.Column("campaign_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_patient_offers_campaign_id",
            "campaigns",
            ["campaign_id"],
            ["id"],
        )
        batch_op.create_index("ix_patient_offers_campaign_id", ["campaign_id"], unique=False)
    with op.batch_alter_table("delivery_logs", recreate="always") as batch_op:
        batch_op.add_column(sa.Column("recipient", sa.String(255), nullable=True))
        batch_op.add_column(sa.Column("n8n_workflow_id", sa.String(150), nullable=True))
        batch_op.add_column(sa.Column("provider_message_id", sa.String(150), nullable=True))
        batch_op.add_column(sa.Column("failure_reason", sa.String(255), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("delivery_logs", recreate="always") as batch_op:
        batch_op.drop_column("failure_reason")
        batch_op.drop_column("provider_message_id")
        batch_op.drop_column("n8n_workflow_id")
        batch_op.drop_column("recipient")
    with op.batch_alter_table("patient_offers", recreate="always") as batch_op:
        batch_op.drop_index("ix_patient_offers_campaign_id")
        batch_op.drop_constraint("fk_patient_offers_campaign_id", type_="foreignkey")
        batch_op.drop_column("campaign_id")
    op.drop_table("campaign_offers")
    op.drop_table("campaigns")