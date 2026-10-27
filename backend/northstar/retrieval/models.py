"""Persistent policy versions, separate from business and support records."""

from datetime import datetime

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from northstar.db import Base
from northstar.models import RecordTimestamps


class Policy(Base, RecordTimestamps):
    __tablename__ = "knowledge_policies"
    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    enabled: Mapped[bool] = mapped_column(default=True)
    revision: Mapped[int] = mapped_column(default=0)


class Document(Base, RecordTimestamps):
    __tablename__ = "knowledge_documents"
    __table_args__ = (
        UniqueConstraint("policy_id", "version"),
        UniqueConstraint("content_hash"),
        CheckConstraint("version > 0", name="positive_version"),
        CheckConstraint(
            "status IN ('QUEUED','PROCESSING','READY','FAILED','DUPLICATE')",
            name="processing_status",
        ),
        CheckConstraint("valid_until IS NULL OR valid_until > valid_from", name="valid_period"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    policy_id: Mapped[str] = mapped_column(ForeignKey("knowledge_policies.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    filename: Mapped[str] = mapped_column(String(255))
    media_type: Mapped[str] = mapped_column(String(100))
    original_hash: Mapped[str] = mapped_column(String(64), index=True)
    content_hash: Mapped[str | None] = mapped_column(String(64))
    original: Mapped[bytes] = mapped_column(LargeBinary)
    status: Mapped[str] = mapped_column(String(20))
    lease_token: Mapped[str | None] = mapped_column(String(36))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    duplicate_of: Mapped[str | None] = mapped_column(String(36))
    error: Mapped[str | None] = mapped_column(String(100))
    warnings: Mapped[list] = mapped_column(JSON)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    enabled: Mapped[bool] = mapped_column(default=True)


class Section(Base):
    __tablename__ = "knowledge_sections"
    __table_args__ = (UniqueConstraint("document_id", "ordinal"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("knowledge_documents.id"), index=True)
    ordinal: Mapped[int] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(String(500))
    text: Mapped[str] = mapped_column(Text)


class RetrievalIndex(Base, RecordTimestamps):
    """One atomic, bounded corpus snapshot; vectors never commit independently."""

    __tablename__ = "knowledge_retrieval_index"
    __table_args__ = (
        CheckConstraint("id = 'active'", name="singleton"),
        CheckConstraint("status IN ('EMPTY', 'READY')", name="index_status"),
    )
    id: Mapped[str] = mapped_column(String(20), primary_key=True)
    status: Mapped[str] = mapped_column(String(20))
    model_id: Mapped[str] = mapped_column(String(100))
    generation: Mapped[str] = mapped_column(String(36))
    source_hash: Mapped[str] = mapped_column(String(64))
    payload_hash: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict] = mapped_column(JSON)
