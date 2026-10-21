"""Durable support cases and opaque customer credentials."""

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def id_column():
    return sa.Column("id", sa.String(36), primary_key=True)


def case_column():
    return sa.Column("case_id", sa.String(36), sa.ForeignKey("support_cases.id"), nullable=False)


def upgrade():
    with op.batch_alter_table("accounts") as batch:
        batch.create_unique_constraint("uq_accounts_id", ["id", "customer_id"])
    op.create_table(
        "customer_credentials",
        id_column(),
        sa.Column("customer_id", sa.String(36), sa.ForeignKey("customers.id"), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_customer_credentials_customer_id", "customer_credentials", ["customer_id"])
    op.create_table(
        "support_cases",
        id_column(),
        sa.Column("customer_id", sa.String(36), sa.ForeignKey("customers.id"), nullable=False),
        sa.Column("account_id", sa.String(36), nullable=False),
        sa.Column("subject", sa.String(200), nullable=False),
        sa.Column("category", sa.String(20), nullable=False),
        sa.Column("context", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("disposition", sa.String(32)),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("message_count", sa.Integer(), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("current_attempt_id", sa.String(36)),
        sa.Column("last_error", sa.String(64)),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["account_id", "customer_id"], ["accounts.id", "accounts.customer_id"]
        ),
        sa.CheckConstraint(
            "status IN ('open','processing','awaiting_customer','escalated','resolved','failed')",
            name="status",
        ),
        sa.CheckConstraint(
            "disposition IS NULL OR disposition IN ('answered','action_completed',"
            "'clarification_requested','refused','escalated')",
            name="disposition",
        ),
        sa.CheckConstraint(
            "category IN ('general','billing','account','technical','privacy')", name="category"
        ),
        sa.CheckConstraint(
            "version > 0 AND message_count > 0 AND attempt_count >= 0", name="counters"
        ),
        sa.CheckConstraint(
            "(status = 'processing' AND current_attempt_id IS NOT NULL) OR "
            "(status != 'processing' AND current_attempt_id IS NULL)",
            name="processing_attempt",
        ),
        sa.CheckConstraint(
            "(status = 'resolved' AND resolved_at IS NOT NULL) OR "
            "(status != 'resolved' AND resolved_at IS NULL)",
            name="resolution_time",
        ),
    )
    for column in ["customer_id", "account_id"]:
        op.create_index("ix_support_cases_" + column, "support_cases", [column])
    op.create_table(
        "case_messages",
        id_column(),
        case_column(),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("case_id", "sequence"),
        sa.CheckConstraint("role IN ('customer','assistant','human')", name="role"),
    )
    op.create_table(
        "case_attempts",
        id_column(),
        case_column(),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("error_code", sa.String(64)),
        sa.Column("result", sa.JSON()),
        sa.UniqueConstraint("case_id", "number"),
        sa.CheckConstraint(
            "status IN ('processing','succeeded','failed','timed_out')", name="status"
        ),
    )
    op.create_table(
        "case_events",
        id_column(),
        case_column(),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("actor", sa.String(20), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("disposition", sa.String(32)),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("case_id", "version"),
    )
    for table in ["case_messages", "case_attempts", "case_events"]:
        op.create_index("ix_" + table + "_case_id", table, ["case_id"])
    op.create_table(
        "case_submissions",
        id_column(),
        sa.Column("customer_id", sa.String(36), sa.ForeignKey("customers.id"), nullable=False),
        sa.Column("key", sa.String(128), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        case_column(),
        sa.Column("message_id", sa.String(36), sa.ForeignKey("case_messages.id"), nullable=False),
        sa.UniqueConstraint("customer_id", "key"),
    )


def downgrade():
    for table in [
        "case_submissions",
        "case_events",
        "case_attempts",
        "case_messages",
        "support_cases",
        "customer_credentials",
    ]:
        op.drop_table(table)
    with op.batch_alter_table("accounts") as batch:
        batch.drop_constraint("uq_accounts_id", type_="unique")
