"""B6/B7 human decisions and append-only provenance. Publication is always separate."""

import hashlib
from copy import deepcopy
from uuid import uuid4

from sqlalchemy import delete, select

from northstar.domain import DomainError
from northstar.retrieval.extraction import MAX_TEXT, normalize
from northstar.retrieval.models import Document, ExtractionRecord, RetrievalIndex, Section


def save_record(session, document, payload, actor="worker", reason=""):
    document.extraction_revision += 1
    document.extraction_status = payload["status"]
    session.add(
        ExtractionRecord(
            id=str(uuid4()),
            document_id=document.id,
            revision=document.extraction_revision,
            status=payload["status"],
            actor=actor,
            reason=reason,
            payload=deepcopy(payload),
        )
    )


def verify(sessions, identifier, decision, reason, revision, corrections=None):
    from northstar.retrieval.service import describe, record_event
    from northstar.storage import settings_for

    if decision not in {"ACCEPT", "CORRECT", "REJECT", "REPROCESS"} or not reason.strip():
        raise DomainError(
            "invalid_verification", "A verification decision and reason are required.", 422
        )
    with sessions.begin() as session:
        doc = session.get(Document, identifier, with_for_update=True)
        if doc is None or doc.publication_status == "DELETED":
            raise DomainError("not_found", "Document does not exist.", 404)
        if (
            doc.sensitivity in {"CONFIDENTIAL", "HIGHLY_RESTRICTED"}
            and not settings_for(sessions).storage.restricted_environment_approved
        ):
            raise DomainError(
                "restricted_environment", "Restricted environment is not approved.", 403
            )
        if doc.extraction_revision != revision or doc.status in {
            "QUEUED",
            "PROCESSING",
            "DUPLICATE",
        }:
            raise DomainError(
                "stale_verification", "Refresh the document before reviewing it.", 409
            )
        previous = session.scalar(
            select(ExtractionRecord)
            .where(ExtractionRecord.document_id == identifier)
            .order_by(ExtractionRecord.revision.desc())
            .limit(1)
        )
        sections = session.scalars(
            select(Section).where(Section.document_id == identifier).order_by(Section.ordinal)
        ).all()
        was_published = doc.publication_status == "APPROVED"
        payload = {
            "parent_revision": revision,
            "decision": decision,
            "previous_sections": [{"source": s.source, "text": s.text} for s in sections],
            "parser_record_revision": previous.revision if previous else None,
        }
        if decision == "CORRECT":
            if not corrections or sum(len(c["text"]) for c in corrections) > MAX_TEXT:
                raise DomainError("invalid_corrections", "Supply bounded corrected sections.", 422)
            corrected = [(c["source"], normalize(c["text"])) for c in corrections]
            if any(not text.strip() or not source.strip() for source, text in corrected):
                raise DomainError(
                    "invalid_corrections", "Each correction needs text and a source reference.", 422
                )
            digest = hashlib.sha256("\n\n".join(t for _, t in corrected).encode()).hexdigest()
            if session.scalar(
                select(Document.id).where(
                    Document.id != identifier, Document.content_hash == digest
                )
            ):
                raise DomainError(
                    "duplicate_correction", "Corrected content duplicates another version.", 409
                )
            session.execute(delete(Section).where(Section.document_id == identifier))
            for ordinal, (source, text) in enumerate(corrected, 1):
                session.add(
                    Section(
                        id=hashlib.sha256(
                            f"{identifier}:{revision + 1}:{ordinal}".encode()
                        ).hexdigest(),
                        document_id=identifier,
                        ordinal=ordinal,
                        source=source,
                        text=text,
                    )
                )
            doc.content_hash, doc.status, doc.error = digest, "READY", None
            payload["corrections"] = corrections
        if decision in {"ACCEPT", "CORRECT"}:
            if decision == "ACCEPT" and (doc.status != "READY" or not sections):
                raise DomainError(
                    "no_extraction", "No content to accept. Correct or reprocess it.", 409
                )
            payload["status"] = "VERIFIED"
        elif decision == "REPROCESS":
            payload["status"] = "PENDING"
            doc.status, doc.error, doc.attempts = "QUEUED", None, 0
        else:
            payload["status"] = "REJECTED"
        # Fence an in-flight classifier and require fresh human publication approval.
        doc.review_status, doc.review_attempts = "PENDING", 0
        doc.review_lease_token = doc.review_lease_expires_at = None
        doc.publication_status = "PENDING_REVIEW"
        save_record(session, doc, payload, "administrator", reason.strip())
        record_event(
            session, identifier, "verification_" + decision.lower(), "administrator", reason.strip()
        )
        if was_published:
            # Withdrawn content: purge cached representations, as for a deletion.
            session.execute(delete(RetrievalIndex))
        session.flush()
        return describe(session, doc, include_sections=True)
