"""Add consent, weekly duplicate prevention, cancellation, and hashed QR tokens."""

from datetime import timedelta
import hashlib
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260902_0002"
down_revision: Union[str, None] = "20260902_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("patients", sa.Column("registration_week", sa.Date(), nullable=True))
    op.add_column("patients", sa.Column("consent_given", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("patients", sa.Column("consent_version", sa.String(20), nullable=True))
    op.add_column("patients", sa.Column("consented_at", sa.DateTime(), nullable=True))
    op.add_column("patient_offers", sa.Column("secure_token_hash", sa.String(64), nullable=True))
    op.add_column("patient_offers", sa.Column("cancelled_at", sa.DateTime(), nullable=True))
    op.add_column("patient_offers", sa.Column("cancelled_by", sa.String(100), nullable=True))
    op.add_column("patient_offers", sa.Column("cancellation_reason", sa.String(255), nullable=True))

    bind = op.get_bind()
    patients = bind.execute(sa.text("SELECT id, created_at FROM patients")).mappings()
    for row in patients:
        created = row["created_at"]
        week = (created - timedelta(days=(created.weekday() + 1) % 7)).date()
        bind.execute(sa.text("UPDATE patients SET registration_week=:week, consent_version='legacy', consented_at=:created WHERE id=:id"), {"week": week, "created": created, "id": row["id"]})
    coupons = bind.execute(sa.text("SELECT id, secure_token FROM patient_offers")).mappings()
    for row in coupons:
        digest = hashlib.sha256(row["secure_token"].encode()).hexdigest()
        bind.execute(sa.text("UPDATE patient_offers SET secure_token_hash=:digest WHERE id=:id"), {"digest": digest, "id": row["id"]})

    with op.batch_alter_table("patients") as batch:
        batch.alter_column("registration_week", nullable=False)
        batch.alter_column("consent_version", nullable=False)
        batch.alter_column("consented_at", nullable=False)
        batch.create_index("ix_patients_registration_week", ["registration_week"])
        batch.create_unique_constraint("uq_patient_mobile_registration_week", ["mobile", "registration_week"])
    with op.batch_alter_table("patient_offers") as batch:
        batch.drop_index("ix_patient_offers_secure_token")
        batch.drop_column("secure_token")
        batch.alter_column("secure_token_hash", nullable=False)
        batch.create_index("ix_patient_offers_secure_token_hash", ["secure_token_hash"], unique=True)


def downgrade() -> None:
    with op.batch_alter_table("patient_offers") as batch:
        batch.drop_index("ix_patient_offers_secure_token_hash")
        batch.add_column(sa.Column("secure_token", sa.String(128), nullable=True))
    bind = op.get_bind()
    bind.execute(sa.text("UPDATE patient_offers SET secure_token = 'RETIRED-' || id"))
    with op.batch_alter_table("patient_offers") as batch:
        batch.alter_column("secure_token", nullable=False)
        batch.create_index("ix_patient_offers_secure_token", ["secure_token"], unique=True)
        batch.drop_column("cancellation_reason")
        batch.drop_column("cancelled_by")
        batch.drop_column("cancelled_at")
        batch.drop_column("secure_token_hash")
    with op.batch_alter_table("patients") as batch:
        batch.drop_constraint("uq_patient_mobile_registration_week", type_="unique")
        batch.drop_index("ix_patients_registration_week")
        batch.drop_column("consented_at")
        batch.drop_column("consent_version")
        batch.drop_column("consent_given")
        batch.drop_column("registration_week")
