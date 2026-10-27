"""Atomic ingestion and the authoritative eligibility boundary for future indexes."""

import hashlib
import re
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import exists, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, aliased, sessionmaker

from northstar.domain import DomainError
from northstar.retrieval.extraction import MAX_BYTES, IngestionError, extract, validate_file
from northstar.retrieval.models import Document, Policy, Section


def utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def eligible_documents(at: datetime | None = None):
    """Recheck this predicate at evidence use, even when an external index caches chunks.

    A newer effective version permanently supersedes older versions, including when
    it expires or is disabled. Failed and not-yet-effective versions do not replace it.
    """
    at = at or datetime.now(UTC)
    newer = aliased(Document)
    return (
        select(Document)
        .join(Policy)
        .where(
            Policy.enabled.is_(True),
            Document.enabled.is_(True),
            Document.status == "READY",
            Document.valid_from <= at,
            (Document.valid_until.is_(None) | (Document.valid_until > at)),
            ~exists(
                select(newer.id).where(
                    newer.policy_id == Document.policy_id,
                    newer.status == "READY",
                    newer.valid_from <= at,
                    newer.version > Document.version,
                )
            ),
        )
    )


def retrieval_sections(session: Session, at: datetime | None = None) -> list[Section]:
    ids = eligible_documents(at).with_only_columns(Document.id)
    return session.scalars(
        select(Section)
        .where(Section.document_id.in_(ids))
        .order_by(Section.document_id, Section.ordinal)
    ).all()


def describe(
    session: Session, document: Document, at: datetime | None = None, include_sections: bool = False
) -> dict:
    at = at or datetime.now(UTC)
    active = session.scalar(eligible_documents(at).where(Document.id == document.id)) is not None
    policy = session.get(Policy, document.policy_id)
    if document.status != "READY":
        lifecycle = document.status
    elif not document.enabled or not policy.enabled:
        lifecycle = "INACTIVE"
    elif utc(document.valid_from) > at:
        lifecycle = "SCHEDULED"
    elif active:
        lifecycle = "ACTIVE"
    elif document.valid_until and utc(document.valid_until) <= at:
        lifecycle = "EXPIRED"
    else:
        lifecycle = "SUPERSEDED"
    result = {
        key: getattr(document, key)
        for key in (
            "id",
            "policy_id",
            "version",
            "filename",
            "media_type",
            "original_hash",
            "content_hash",
            "status",
            "error",
            "attempts",
            "duplicate_of",
            "warnings",
            "valid_from",
            "valid_until",
            "created_at",
            "updated_at",
        )
    }
    result.update(lifecycle=lifecycle, policy_revision=policy.revision)
    if include_sections:
        result["sections"] = [
            {"id": s.id, "ordinal": s.ordinal, "source": s.source, "text": s.text}
            for s in session.scalars(
                select(Section).where(Section.document_id == document.id).order_by(Section.ordinal)
            )
        ]
    return result


class KnowledgeService:
    def __init__(self, sessions: sessionmaker[Session]):
        self.sessions = sessions

    def ingest(
        self,
        policy_id: str,
        filename: str,
        data: bytes,
        valid_from: datetime | None = None,
        valid_until: datetime | None = None,
        replace: bool = False,
        *,
        defer: bool = False,
    ) -> dict:
        if len(data) > MAX_BYTES:
            raise DomainError("file_too_large", "File exceeds 5 MiB.", 413)
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,99}", policy_id):
            raise DomainError("invalid_policy_id", "Use a lowercase policy identifier.", 422)
        valid_from = valid_from or datetime.now(UTC)
        if valid_from.tzinfo is None or (valid_until and valid_until.tzinfo is None):
            raise DomainError("invalid_period", "Validity timestamps must include a timezone.", 422)
        if valid_until and valid_until <= valid_from:
            raise DomainError("invalid_period", "Expiry must follow the effective timestamp.", 422)
        filename = filename.replace("\\", "/").rsplit("/", 1)[-1][:255]
        original_hash = hashlib.sha256(data).hexdigest()
        # Hash equality never establishes a new policy/version relationship.
        with self.sessions() as session:
            if replace and session.get(Policy, policy_id) is None:
                raise DomainError("not_found", "Policy does not exist.", 404)
            duplicate = session.scalar(
                select(Document)
                .where(Document.original_hash == original_hash)
                .order_by(Document.created_at, Document.id)
                .limit(1)
            )
            if duplicate:
                return {
                    "duplicate": True,
                    "document": describe(session, duplicate, include_sections=True),
                }
        document_id = str(uuid4())
        media, content_hash, sections, warnings, failure = (
            "application/octet-stream",
            None,
            [],
            [],
            None,
        )
        try:
            media = validate_file(filename, data)
            if not defer:
                media, content, sections, warnings = extract(filename, data)
                content_hash = hashlib.sha256(content.encode()).hexdigest()
        except IngestionError as exc:
            failure = str(exc)
        try:
            with self.sessions.begin() as session:
                if session.bind.dialect.name == "postgresql":
                    from sqlalchemy import text

                    session.execute(
                        text("SELECT pg_advisory_xact_lock(:key)"),
                        {"key": int(original_hash[:15], 16)},
                    )
                duplicate = session.scalar(
                    select(Document)
                    .where(Document.original_hash == original_hash)
                    .order_by(Document.created_at, Document.id)
                    .limit(1)
                )
                if duplicate:
                    return {
                        "duplicate": True,
                        "document": describe(session, duplicate, include_sections=True),
                    }
                policy = session.scalar(
                    select(Policy).where(Policy.id == policy_id).with_for_update()
                )
                if replace and policy is None:
                    raise DomainError("not_found", "Policy does not exist.", 404)
                if content_hash:
                    duplicate = session.scalar(
                        select(Document).where(Document.content_hash == content_hash)
                    )
                    if duplicate:
                        return {
                            "duplicate": True,
                            "document": describe(session, duplicate, include_sections=True),
                        }
                if policy and not replace:
                    raise DomainError(
                        "policy_exists", "Use the replacement endpoint for this policy."
                    )
                if policy is None:
                    policy = Policy(id=policy_id, enabled=True, revision=0)
                    session.add(policy)
                    session.flush()
                policy.revision += 1
                document = Document(
                    id=document_id,
                    policy_id=policy_id,
                    version=policy.revision,
                    filename=filename,
                    media_type=media,
                    original_hash=original_hash,
                    content_hash=content_hash,
                    original=data,
                    status="FAILED" if failure else "QUEUED" if defer else "READY",
                    error=failure,
                    warnings=warnings,
                    valid_from=valid_from,
                    valid_until=valid_until,
                    enabled=True,
                )
                session.add(document)
                session.flush()
                for ordinal, (source, text) in enumerate(sections, 1):
                    session.add(
                        Section(
                            id=hashlib.sha256(f"{document_id}:{ordinal}".encode()).hexdigest(),
                            document_id=document_id,
                            ordinal=ordinal,
                            source=source,
                            text=text,
                        )
                    )
                session.flush()
                return {
                    "duplicate": False,
                    "document": describe(session, document, include_sections=True),
                }
        except IntegrityError:
            raise DomainError(
                "concurrent_ingestion", "Conflicting upload; inspect the policy and retry."
            ) from None

    def deactivate(self, policy_id: str) -> dict:
        with self.sessions.begin() as session:
            policy = session.scalar(select(Policy).where(Policy.id == policy_id).with_for_update())
            if policy is None:
                raise DomainError("not_found", "Policy does not exist.", 404)
            policy.enabled = False
            return {"policy_id": policy_id, "enabled": False}
