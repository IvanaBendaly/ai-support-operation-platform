"""Atomic ingestion and the authoritative eligibility boundary for future indexes."""

import hashlib
import re
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import exists, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, aliased, sessionmaker

from northstar.ai.review import SENSITIVITIES
from northstar.domain import DomainError
from northstar.retrieval.extraction import MAX_BYTES, IngestionError, validate_file
from northstar.retrieval.models import (
    Document,
    DocumentEvent,
    Policy,
    ReviewAssessment,
    Section,
    StoredObject,
)
from northstar.storage import settings_for, store_for


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
            Document.extraction_status == "VERIFIED",
            Document.publication_status == "APPROVED",
            Document.approved_at.is_not(None),
            # No ACL-aware search exists yet: only explicitly public material may be indexed.
            Document.sensitivity == "PUBLIC",
            Document.valid_from <= at,
            (Document.valid_until.is_(None) | (Document.valid_until > at)),
            ~exists(
                select(newer.id).where(
                    newer.policy_id == Document.policy_id,
                    newer.status == "READY",
                    newer.approved_at.is_not(None),
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
    if document.publication_status == "DELETED":
        lifecycle = "DELETED"
    elif document.status != "READY":
        lifecycle = document.status
    elif document.publication_status != "APPROVED":
        lifecycle = document.publication_status
    elif not document.enabled or not policy.enabled:
        lifecycle = "INACTIVE"
    elif utc(document.valid_from) > at:
        lifecycle = "SCHEDULED"
    elif active:
        lifecycle = "ACTIVE"
    elif document.valid_until and utc(document.valid_until) <= at:
        lifecycle = "EXPIRED"
    elif (
        document.sensitivity != "PUBLIC"
        and session.scalar(
            select(Document.id)
            .where(
                Document.policy_id == document.policy_id,
                Document.version > document.version,
                Document.approved_at.is_not(None),
                Document.valid_from <= at,
            )
            .limit(1)
        )
        is None
    ):
        lifecycle = "RESTRICTED"
    else:
        lifecycle = "SUPERSEDED"
    result = {
        key: getattr(document, key)
        for key in (
            "id",
            "policy_id",
            "version",
            "filename",
            "title",
            "sensitivity",
            "publication_status",
            "review_status",
            "extraction_status",
            "extraction_revision",
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
        from northstar.retrieval.models import ExtractionRecord

        result["extractions"] = [
            {
                key: getattr(row, key)
                for key in ("revision", "status", "actor", "reason", "payload", "created_at")
            }
            for row in session.scalars(
                select(ExtractionRecord)
                .where(ExtractionRecord.document_id == document.id)
                .order_by(ExtractionRecord.revision)
            )
        ]
        result["sections"] = [
            {"id": s.id, "ordinal": s.ordinal, "source": s.source, "text": s.text}
            for s in session.scalars(
                select(Section).where(Section.document_id == document.id).order_by(Section.ordinal)
            )
        ]
        result["assessments"] = [
            {
                key: getattr(a, key)
                for key in (
                    "id",
                    "provider",
                    "model_id",
                    "assessment_status",
                    "needs_review",
                    "risk_level",
                    "review_reasons",
                    "explanation",
                    "supporting_references",
                    "metrics",
                    "prompt_version",
                    "created_at",
                )
            }
            for a in session.scalars(
                select(ReviewAssessment)
                .where(ReviewAssessment.document_id == document.id)
                .order_by(ReviewAssessment.created_at)
            )
        ]
        result["events"] = [
            {key: getattr(e, key) for key in ("action", "actor", "reason", "created_at")}
            for e in session.scalars(
                select(DocumentEvent)
                .where(DocumentEvent.document_id == document.id)
                .order_by(DocumentEvent.created_at)
            )
        ]
    return result


def record_event(session, document_id, action, actor="worker", reason=""):
    session.add(
        DocumentEvent(
            id=str(uuid4()), document_id=document_id, action=action, actor=actor, reason=reason
        )
    )


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
        sensitivity: str,
        title: str,
    ) -> dict:
        if sensitivity not in SENSITIVITIES or sensitivity == "UNCLASSIFIED":
            raise DomainError(
                "classification_required", "Select a valid document sensitivity.", 422
            )
        if not title.strip() or len(title) > 160:
            raise DomainError("invalid_title", "Supply a title of 1–160 characters.", 422)
        settings = settings_for(self.sessions)
        if (
            sensitivity in {"CONFIDENTIAL", "HIGHLY_RESTRICTED"}
            and not settings.storage.restricted_environment_approved
        ):
            raise DomainError(
                "restricted_storage_not_approved",
                "Private storage, previews and backups must be approved for restricted content.",
                403,
            )
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
                if duplicate.sensitivity != sensitivity:
                    raise DomainError(
                        "classification_conflict",
                        "Existing content has a different classification.",
                        409,
                    )
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
                from northstar.retrieval.verification import pipeline

                verification = pipeline(filename, data, settings.extraction)
                if verification["result"]:
                    media, content, sections, warnings = verification["result"]
                    content_hash = hashlib.sha256(content.encode()).hexdigest()
                else:
                    failure = verification["error"] or "extraction_failed"
        except IngestionError as exc:
            failure = str(exc)
        storage_key = "originals/" + document_id
        # Reserve before PUT so crashes/rollback leave a discoverable cleanup record.
        with self.sessions.begin() as session:
            session.add(StoredObject(key=storage_key))
        store_for(self.sessions).put(storage_key, data)
        try:
            with self.sessions.begin() as session:
                reservation = session.get(StoredObject, storage_key, with_for_update=True)
                if reservation is None:
                    raise DomainError("upload_expired", "Upload reservation expired; retry.", 409)
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
                    if duplicate.sensitivity != sensitivity:
                        raise DomainError(
                            "classification_conflict",
                            "Existing content has a different classification.",
                            409,
                        )
                    return {
                        "duplicate": True,
                        "document": describe(session, duplicate, include_sections=True),
                    }
                policy = session.scalar(
                    select(Policy).where(Policy.id == policy_id).with_for_update()
                )
                if replace and policy is None:
                    raise DomainError("not_found", "Policy does not exist.", 404)
                if policy:
                    prior_levels = session.scalars(
                        select(Document.sensitivity).where(Document.policy_id == policy_id)
                    ).all()
                    if any(
                        SENSITIVITIES.get(level, 4) > SENSITIVITIES[sensitivity]
                        for level in prior_levels
                    ):
                        raise DomainError(
                            "classification_downgrade",
                            "A replacement cannot lower the policy sensitivity.",
                            409,
                        )
                if content_hash:
                    duplicate = session.scalar(
                        select(Document).where(Document.content_hash == content_hash)
                    )
                    if duplicate:
                        if duplicate.sensitivity != sensitivity:
                            raise DomainError(
                                "classification_conflict",
                                "Existing content has a different classification.",
                                409,
                            )
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
                    storage_key=storage_key,
                    title=title.strip(),
                    sensitivity=sensitivity,
                    publication_status="PENDING_REVIEW",
                    review_status="PENDING",
                    status="FAILED" if failure else "QUEUED" if defer else "READY",
                    error=failure,
                    warnings=warnings,
                    valid_from=valid_from,
                    valid_until=valid_until,
                    enabled=True,
                )
                session.add(document)
                session.flush()
                if not defer:
                    from northstar.retrieval.extraction_review import save_record

                    save_record(
                        session,
                        document,
                        verification
                        if "verification" in locals()
                        else {"status": "HUMAN_REQUIRED", "error": failure, "attempts": []},
                    )
                record_event(session, document_id, "uploaded", "administrator")
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
            for identifier in session.scalars(
                select(Document.id).where(Document.policy_id == policy_id)
            ):
                record_event(session, identifier, "policy_deactivated", "administrator")
            return {"policy_id": policy_id, "enabled": False}

    def decide(self, document_id: str, decision: str, reason: str):
        if decision not in {"APPROVED", "REJECTED", "CHANGES_REQUESTED", "DELETED"}:
            raise DomainError("invalid_decision", "Invalid publication decision.", 422)
        if not reason.strip() or len(reason) > 500:
            raise DomainError(
                "reason_required", "Record a decision reason of 1–500 characters.", 422
            )
        with self.sessions.begin() as session:
            document = session.get(Document, document_id)
            if document is None:
                raise DomainError("not_found", "Document does not exist.", 404)
            session.scalar(select(Policy).where(Policy.id == document.policy_id).with_for_update())
            document = session.get(
                Document, document_id, populate_existing=True, with_for_update=True
            )
            if document.publication_status == "DELETED":
                raise DomainError("document_deleted", "Deleted documents cannot change state.", 409)
            if decision != "DELETED" and document.publication_status != "PENDING_REVIEW":
                raise DomainError(
                    "invalid_transition", "Only pending versions can be reviewed.", 409
                )
            if decision == "APPROVED":
                if document.extraction_status != "VERIFIED":
                    raise DomainError(
                        "extraction_unverified", "Verify extraction before publication.", 409
                    )
                if document.status != "READY" or document.sensitivity == "UNCLASSIFIED":
                    raise DomainError(
                        "not_ready", "Extraction and sensitivity classification are required.", 409
                    )
                if document.review_status in {"PENDING", "PROCESSING"}:
                    raise DomainError(
                        "review_pending", "Wait for the assessment attempt to finish.", 409
                    )
                if document.publication_status != "PENDING_REVIEW":
                    raise DomainError(
                        "invalid_transition", "Only pending versions can be approved.", 409
                    )
                document.approved_at = datetime.now(UTC)
            document.publication_status = decision
            if decision == "DELETED":
                document.enabled = False
            # The same predicate atomically switches the active revision at commit.
            record_event(session, document_id, decision.lower(), "administrator", reason.strip())
            # Purge cached representations; next search rebuilds only eligible public sources.
            from sqlalchemy import delete

            from northstar.retrieval.models import RetrievalIndex

            if decision == "DELETED" or document.sensitivity != "PUBLIC":
                session.execute(delete(RetrievalIndex))
            session.flush()
            return describe(session, document, include_sections=True)
