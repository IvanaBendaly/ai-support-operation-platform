"""business domain and operation audit"""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "customers",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_customers")),
        sa.UniqueConstraint("email", name=op.f("uq_customers_email")),
    )
    op.create_table(
        "plans",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("price_minor", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.CheckConstraint("currency = 'USD'", name=op.f("ck_plans_currency")),
        sa.CheckConstraint("price_minor >= 0", name=op.f("ck_plans_price_nonnegative")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_plans")),
    )
    op.create_table(
        "accounts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("customer_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.CheckConstraint("status IN ('ACTIVE','SUSPENDED')", name=op.f("ck_accounts_status")),
        sa.ForeignKeyConstraint(
            ["customer_id"], ["customers.id"], name=op.f("fk_accounts_customer_id_customers")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_accounts")),
    )
    op.create_index(op.f("ix_accounts_customer_id"), "accounts", ["customer_id"], unique=False)
    op.create_table(
        "invoices",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("account_id", sa.String(length=36), nullable=False),
        sa.Column("amount_minor", sa.Integer(), nullable=False),
        sa.Column("refunded_minor", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("issued_on", sa.Date(), nullable=False),
        sa.CheckConstraint("currency = 'USD'", name=op.f("ck_invoices_currency")),
        sa.CheckConstraint("status IN ('PAID','UNPAID','VOID')", name=op.f("ck_invoices_status")),
        sa.CheckConstraint("amount_minor > 0", name=op.f("ck_invoices_amount_positive")),
        sa.CheckConstraint(
            "refunded_minor >= 0 AND refunded_minor <= amount_minor",
            name=op.f("ck_invoices_refund_limit"),
        ),
        sa.ForeignKeyConstraint(
            ["account_id"], ["accounts.id"], name=op.f("fk_invoices_account_id_accounts")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_invoices")),
    )
    op.create_index(op.f("ix_invoices_account_id"), "invoices", ["account_id"], unique=False)
    op.create_table(
        "operations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("account_id", sa.String(length=36), nullable=False),
        sa.Column("actor_id", sa.String(length=36), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("arguments", sa.JSON(), nullable=False),
        sa.Column("before", sa.JSON(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["account_id"], ["accounts.id"], name=op.f("fk_operations_account_id_accounts")
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"], ["customers.id"], name=op.f("fk_operations_actor_id_customers")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_operations")),
        sa.UniqueConstraint("account_id", "idempotency_key", name=op.f("uq_operations_account_id")),
    )
    op.create_index(op.f("ix_operations_account_id"), "operations", ["account_id"], unique=False)
    op.create_table(
        "subscriptions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("account_id", sa.String(length=36), nullable=False),
        sa.Column("plan_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("started_on", sa.Date(), nullable=False),
        sa.Column("ends_on", sa.Date(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "status IN ('ACTIVE','PAST_DUE','CANCELED')", name=op.f("ck_subscriptions_status")
        ),
        sa.CheckConstraint(
            "ends_on IS NULL OR ends_on >= started_on", name=op.f("ck_subscriptions_dates")
        ),
        sa.CheckConstraint("version > 0", name=op.f("ck_subscriptions_version_positive")),
        sa.ForeignKeyConstraint(
            ["account_id"], ["accounts.id"], name=op.f("fk_subscriptions_account_id_accounts")
        ),
        sa.ForeignKeyConstraint(
            ["plan_id"], ["plans.id"], name=op.f("fk_subscriptions_plan_id_plans")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_subscriptions")),
        sa.UniqueConstraint("account_id", name=op.f("uq_subscriptions_account_id")),
    )
    op.create_table(
        "refunds",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("invoice_id", sa.String(length=36), nullable=False),
        sa.Column("amount_minor", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("amount_minor > 0", name=op.f("ck_refunds_amount_positive")),
        sa.ForeignKeyConstraint(
            ["invoice_id"], ["invoices.id"], name=op.f("fk_refunds_invoice_id_invoices")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_refunds")),
        sa.UniqueConstraint("invoice_id", name=op.f("uq_refunds_invoice_id")),
    )


def downgrade():
    op.drop_table("refunds")
    op.drop_table("subscriptions")
    op.drop_index(op.f("ix_operations_account_id"), table_name="operations")
    op.drop_table("operations")
    op.drop_index(op.f("ix_invoices_account_id"), table_name="invoices")
    op.drop_table("invoices")
    op.drop_index(op.f("ix_accounts_customer_id"), table_name="accounts")
    op.drop_table("accounts")
    op.drop_table("plans")
    op.drop_table("customers")
