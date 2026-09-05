"""add delivery intent grouping, idempotency, and durable outbox state to delivery_logs

Revision ID: 20260905_0008
Revises: 20260904_0007
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260905_0008"
down_revision: Union[str, None] = "20260904_0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

KNOWN_LEGACY_STATUSES = {"PENDING", "SENT", "DELIVERED", "FAILED"}
NEW_STATUS_VALUES = ("PREPARED", "SENDING", "SENT", "DELIVERED", "FAILED")


def upgrade() -> None:
    connection = op.get_bind()

    # Safety check: fail loudly on any status this migration does not know how to handle,
    # rather than let the CHECK constraint added below fail with an unclear database error.
    existing_statuses = {
        row[0] for row in connection.exec_driver_sql("SELECT DISTINCT status FROM delivery_logs")
    }
    unknown = existing_statuses - KNOWN_LEGACY_STATUSES
    if unknown:
        raise RuntimeError(
            "Cannot apply delivery_logs status CHECK constraint: unrecognized existing status "
            f"value(s) {sorted(unknown)!r} found in delivery_logs.status. Add explicit handling "
            "for these values to this migration before re-running it."
        )

    # 1. Nullable columns first.
    with op.batch_alter_table("delivery_logs") as batch_op:
        batch_op.add_column(sa.Column("delivery_intent_key", sa.String(40), nullable=True))
        batch_op.add_column(sa.Column("idempotency_key", sa.String(40), nullable=True))
        batch_op.add_column(sa.Column("attempt_number", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("retryable", sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column("dispatched_at", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("delivered_at", sa.DateTime(), nullable=True))

    # 2. Data-fix pass: the old PENDING status meant "recorded locally, nothing attempted against
    #    n8n yet" — exactly what PREPARED means in the new state machine. Lossless rename.
    op.execute("UPDATE delivery_logs SET status = 'PREPARED' WHERE status = 'PENDING'")

    # 3. Backfill legacy rows: deterministic per-row intent key, idempotency key stays NULL
    #    (n8n never received a key for these attempts and could never echo one back), attempt 1,
    #    retryable by default.
    op.execute("UPDATE delivery_logs SET delivery_intent_key = 'legacy_' || id WHERE delivery_intent_key IS NULL")
    op.execute("UPDATE delivery_logs SET attempt_number = 1 WHERE attempt_number IS NULL")
    op.execute("UPDATE delivery_logs SET retryable = TRUE WHERE retryable IS NULL")

    # 4. NOT NULL + indexes/constraints only after backfill.
    with op.batch_alter_table("delivery_logs") as batch_op:
        batch_op.alter_column("delivery_intent_key", existing_type=sa.String(40), nullable=False)
        batch_op.alter_column("attempt_number", existing_type=sa.Integer(), nullable=False, server_default="1")
        batch_op.alter_column("retryable", existing_type=sa.Boolean(), nullable=False, server_default=sa.true())
        batch_op.create_index("ix_delivery_logs_delivery_intent_key", ["delivery_intent_key"])
        batch_op.create_index("ux_delivery_logs_idempotency_key", ["idempotency_key"], unique=True)
        batch_op.create_unique_constraint("uq_delivery_logs_intent_attempt", ["delivery_intent_key", "attempt_number"])
        batch_op.create_check_constraint(
            "ck_delivery_logs_status",
            "status IN (" + ", ".join(f"'{value}'" for value in NEW_STATUS_VALUES) + ")",
        )


def downgrade() -> None:
    with op.batch_alter_table("delivery_logs") as batch_op:
        batch_op.drop_constraint("ck_delivery_logs_status", type_="check")
        batch_op.drop_constraint("uq_delivery_logs_intent_attempt", type_="unique")
        batch_op.drop_index("ux_delivery_logs_idempotency_key")
        batch_op.drop_index("ix_delivery_logs_delivery_intent_key")
        batch_op.drop_column("delivered_at")
        batch_op.drop_column("dispatched_at")
        batch_op.drop_column("retryable")
        batch_op.drop_column("attempt_number")
        batch_op.drop_column("idempotency_key")
        batch_op.drop_column("delivery_intent_key")
    # The PENDING -> PREPARED status rewrite is a one-way semantic correction and is
    # intentionally not reversed here.
