"""Business metadata, billing events, and fixture provenance."""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None
TABLES = ("customers", "accounts", "plans", "subscriptions", "invoices", "refunds")


def upgrade():
    # Unknown historic creation times are backfilled at migration time.
    for table in TABLES:
        with op.batch_alter_table(table) as batch:
            if table != "refunds":
                batch.add_column(
                    sa.Column(
                        "created_at",
                        sa.DateTime(timezone=True),
                        nullable=False,
                        server_default=sa.func.now(),
                    )
                )
            batch.add_column(
                sa.Column(
                    "updated_at",
                    sa.DateTime(timezone=True),
                    nullable=False,
                    server_default=sa.func.now(),
                )
            )
    with op.batch_alter_table("refunds") as batch:
        batch.alter_column(
            "created_at", existing_type=sa.DateTime(timezone=True), server_default=sa.func.now()
        )
        batch.add_column(
            sa.Column("reason", sa.String(500), nullable=False, server_default="legacy_refund")
        )
        batch.add_column(
            sa.Column("state", sa.String(20), nullable=False, server_default="COMPLETED")
        )
        batch.create_check_constraint("state", "state = 'COMPLETED'")
        batch.create_check_constraint("reason", "length(trim(reason)) BETWEEN 1 AND 500")
    with op.batch_alter_table("invoices") as batch:
        batch.create_check_constraint(
            "refund_state",
            "refunded_minor = 0 OR (status = 'PAID' AND refunded_minor = amount_minor)",
        )
    with op.batch_alter_table("subscriptions") as batch:
        batch.create_check_constraint(
            "end_state",
            "(status = 'CANCELED' AND ends_on IS NOT NULL) OR "
            "(status != 'CANCELED' AND ends_on IS NULL)",
        )
    op.create_table(
        "billing_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("invoice_id", sa.String(36), sa.ForeignKey("invoices.id"), nullable=False),
        sa.Column("operation_id", sa.String(36), sa.ForeignKey("operations.id"), unique=True),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("amount_minor", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "kind IN ('INVOICE_ISSUED','PAYMENT_RECEIVED','INVOICE_VOIDED','REFUND_ISSUED')",
            name="kind",
        ),
        sa.CheckConstraint("amount_minor > 0", name="amount_positive"),
        sa.CheckConstraint("currency = 'USD'", name="currency"),
    )
    op.create_index("ix_billing_events_invoice_id", "billing_events", ["invoice_id"])
    op.create_table(
        "business_fixture",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("version", sa.String(30), nullable=False),
        sa.Column("as_of", sa.Date(), nullable=False),
    )


def downgrade():
    op.drop_table("business_fixture")
    op.drop_table("billing_events")
    with op.batch_alter_table("invoices") as batch:
        batch.drop_constraint("refund_state", type_="check")
    with op.batch_alter_table("subscriptions") as batch:
        batch.drop_constraint("end_state", type_="check")
    with op.batch_alter_table("refunds") as batch:
        batch.drop_constraint("state", type_="check")
        batch.drop_constraint("reason", type_="check")
        batch.drop_column("reason")
        batch.drop_column("state")
        batch.alter_column(
            "created_at", existing_type=sa.DateTime(timezone=True), server_default=None
        )
    for table in reversed(TABLES):
        with op.batch_alter_table(table) as batch:
            batch.drop_column("updated_at")
            if table != "refunds":
                batch.drop_column("created_at")
