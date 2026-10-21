from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from northstar.db import Base
from northstar.models import RecordTimestamps, utc_now


class CustomerCredential(Base):
    __tablename__ = "customer_credentials"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class Case(RecordTimestamps, Base):
    __tablename__ = "support_cases"
    __table_args__ = (
        ForeignKeyConstraint(
            ["account_id", "customer_id"], ["accounts.id", "accounts.customer_id"]
        ),
        CheckConstraint(
            "status IN ('open','processing','awaiting_customer','escalated','resolved','failed')",
            name="status",
        ),
        CheckConstraint(
            "disposition IS NULL OR disposition IN ('answered','action_completed',"
            "'clarification_requested','refused','escalated')",
            name="disposition",
        ),
        CheckConstraint(
            "category IN ('general','billing','account','technical','privacy')", name="category"
        ),
        CheckConstraint(
            "version > 0 AND message_count > 0 AND attempt_count >= 0", name="counters"
        ),
        CheckConstraint(
            "(status = 'processing' AND current_attempt_id IS NOT NULL) OR "
            "(status != 'processing' AND current_attempt_id IS NULL)",
            name="processing_attempt",
        ),
        CheckConstraint(
            "(status = 'resolved' AND resolved_at IS NOT NULL) OR "
            "(status != 'resolved' AND resolved_at IS NULL)",
            name="resolution_time",
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id"), index=True)
    account_id: Mapped[str] = mapped_column(String(36), index=True)
    subject: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(20))
    context: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(24))
    disposition: Mapped[str | None] = mapped_column(String(32))
    version: Mapped[int] = mapped_column(Integer)
    message_count: Mapped[int] = mapped_column(Integer)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    current_attempt_id: Mapped[str | None] = mapped_column(String(36))
    last_error: Mapped[str | None] = mapped_column(String(64))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Message(Base):
    __tablename__ = "case_messages"
    __table_args__ = (
        UniqueConstraint("case_id", "sequence"),
        CheckConstraint("role IN ('customer','assistant','human')", name="role"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("support_cases.id"), index=True)
    sequence: Mapped[int] = mapped_column(Integer)
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class Attempt(Base):
    __tablename__ = "case_attempts"
    __table_args__ = (
        UniqueConstraint("case_id", "number"),
        CheckConstraint("status IN ('processing','succeeded','failed','timed_out')", name="status"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("support_cases.id"), index=True)
    number: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(64))
    result: Mapped[dict | None] = mapped_column(JSON)


class CaseEvent(Base):
    __tablename__ = "case_events"
    __table_args__ = (UniqueConstraint("case_id", "version"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("support_cases.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(32))
    actor: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(24))
    disposition: Mapped[str | None] = mapped_column(String(32))
    details: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class Submission(Base):
    __tablename__ = "case_submissions"
    __table_args__ = (UniqueConstraint("customer_id", "key"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id"))
    key: Mapped[str] = mapped_column(String(128))
    fingerprint: Mapped[str] = mapped_column(String(64))
    case_id: Mapped[str] = mapped_column(ForeignKey("support_cases.id"))
    message_id: Mapped[str] = mapped_column(ForeignKey("case_messages.id"))
