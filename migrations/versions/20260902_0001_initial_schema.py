"""Create the initial patient offer schema."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260902_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "patients",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("patient_uid", sa.String(32), nullable=False),
        sa.Column("full_name", sa.String(150), nullable=False),
        sa.Column("mobile", sa.String(30), nullable=False),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("age", sa.Integer(), nullable=True),
        sa.Column("gender", sa.String(30), nullable=True),
        sa.Column("city", sa.String(100), nullable=True),
        sa.Column("doctor_name", sa.String(150), nullable=True),
        sa.Column("campaign_name", sa.String(150), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_patients_patient_uid", "patients", ["patient_uid"], unique=True)
    op.create_index("ix_patients_mobile", "patients", ["mobile"])

    op.create_table(
        "offers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(150), nullable=False, unique=True),
        sa.Column("description", sa.Text(), nullable=False),
    )

    op.create_table(
        "patient_offers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("coupon_uid", sa.String(32), nullable=False),
        sa.Column("patient_id", sa.Integer(), sa.ForeignKey("patients.id"), nullable=False),
        sa.Column("offer_id", sa.Integer(), sa.ForeignKey("offers.id"), nullable=False),
        sa.Column("secure_token", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("redeemed_at", sa.DateTime(), nullable=True),
        sa.Column("redeemed_by", sa.String(100), nullable=True),
    )
    op.create_index("ix_patient_offers_coupon_uid", "patient_offers", ["coupon_uid"], unique=True)
    op.create_index("ix_patient_offers_patient_id", "patient_offers", ["patient_id"])
    op.create_index("ix_patient_offers_offer_id", "patient_offers", ["offer_id"])
    op.create_index("ix_patient_offers_secure_token", "patient_offers", ["secure_token"], unique=True)
    op.create_index("ix_patient_offers_expires_at", "patient_offers", ["expires_at"])
    op.create_index("ix_patient_offers_status", "patient_offers", ["status"])
    op.create_index("ix_patient_offers_status_expiry", "patient_offers", ["status", "expires_at"])

    op.create_table(
        "delivery_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("coupon_id", sa.Integer(), sa.ForeignKey("patient_offers.id"), nullable=False),
        sa.Column("channel", sa.String(20), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("sent_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_delivery_logs_coupon_id", "delivery_logs", ["coupon_id"])

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
        sa.Column("user", sa.String(100), nullable=False),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("coupon_id", sa.Integer(), sa.ForeignKey("patient_offers.id"), nullable=True),
        sa.Column("patient_id", sa.Integer(), sa.ForeignKey("patients.id"), nullable=True),
        sa.Column("details", sa.Text(), nullable=True),
    )
    op.create_index("ix_audit_logs_timestamp", "audit_logs", ["timestamp"])


def downgrade() -> None:
    op.drop_index("ix_audit_logs_timestamp", table_name="audit_logs")
    op.drop_table("audit_logs")
    op.drop_index("ix_delivery_logs_coupon_id", table_name="delivery_logs")
    op.drop_table("delivery_logs")
    op.drop_index("ix_patient_offers_status_expiry", table_name="patient_offers")
    op.drop_index("ix_patient_offers_status", table_name="patient_offers")
    op.drop_index("ix_patient_offers_expires_at", table_name="patient_offers")
    op.drop_index("ix_patient_offers_secure_token", table_name="patient_offers")
    op.drop_index("ix_patient_offers_offer_id", table_name="patient_offers")
    op.drop_index("ix_patient_offers_patient_id", table_name="patient_offers")
    op.drop_index("ix_patient_offers_coupon_uid", table_name="patient_offers")
    op.drop_table("patient_offers")
    op.drop_table("offers")
    op.drop_index("ix_patients_mobile", table_name="patients")
    op.drop_index("ix_patients_patient_uid", table_name="patients")
    op.drop_table("patients")
