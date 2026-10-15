from datetime import date, datetime

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from northstar.db import Base


class Customer(Base):
    __tablename__ = "customers"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    name: Mapped[str] = mapped_column(String(100))


class Account(Base):
    __tablename__ = "accounts"
    __table_args__ = (CheckConstraint("status IN ('ACTIVE','SUSPENDED')", name="status"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(20))


class Plan(Base):
    __tablename__ = "plans"
    __table_args__ = (
        CheckConstraint("price_minor >= 0", name="price_nonnegative"),
        CheckConstraint("currency = 'USD'", name="currency"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    price_minor: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3))
    enabled: Mapped[bool]


class Subscription(Base):
    __tablename__ = "subscriptions"
    __table_args__ = (
        CheckConstraint("status IN ('ACTIVE','PAST_DUE','CANCELED')", name="status"),
        CheckConstraint("ends_on IS NULL OR ends_on >= started_on", name="dates"),
        CheckConstraint("version > 0", name="version_positive"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"), unique=True)
    plan_id: Mapped[str] = mapped_column(ForeignKey("plans.id"))
    status: Mapped[str] = mapped_column(String(20))
    started_on: Mapped[date]
    ends_on: Mapped[date | None]
    version: Mapped[int] = mapped_column(Integer, default=1)


class Invoice(Base):
    __tablename__ = "invoices"
    __table_args__ = (
        CheckConstraint("status IN ('PAID','UNPAID','VOID')", name="status"),
        CheckConstraint("amount_minor > 0", name="amount_positive"),
        CheckConstraint(
            "refunded_minor >= 0 AND refunded_minor <= amount_minor", name="refund_limit"
        ),
        CheckConstraint("currency = 'USD'", name="currency"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"), index=True)
    amount_minor: Mapped[int] = mapped_column(Integer)
    refunded_minor: Mapped[int] = mapped_column(Integer, default=0)
    currency: Mapped[str] = mapped_column(String(3))
    status: Mapped[str] = mapped_column(String(20))
    issued_on: Mapped[date]


class Refund(Base):
    __tablename__ = "refunds"
    __table_args__ = (CheckConstraint("amount_minor > 0", name="amount_positive"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    invoice_id: Mapped[str] = mapped_column(ForeignKey("invoices.id"), unique=True)
    amount_minor: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Operation(Base):
    __tablename__ = "operations"
    __table_args__ = (UniqueConstraint("account_id", "idempotency_key"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"), index=True)
    actor_id: Mapped[str] = mapped_column(ForeignKey("customers.id"))
    idempotency_key: Mapped[str] = mapped_column(String(128))
    kind: Mapped[str] = mapped_column(String(40))
    arguments: Mapped[dict] = mapped_column(JSON)
    before: Mapped[dict] = mapped_column(JSON)
    result: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
