"""Durable, independently leased review attempts after extraction. No publication authority."""

from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import or_, select

from northstar.ai.review import Assessment, assess
from northstar.retrieval.models import Document, ReviewAssessment, Section
from northstar.retrieval.service import record_event, utc
from northstar.storage import settings_for


def run_review_once(sessions, provider_factory=None):
    now = datetime.now(UTC)
    with sessions.begin() as session:
        document = session.scalar(
            select(Document)
            .where(
                Document.status == "READY",
                Document.extraction_status == "VERIFIED",
                Document.publication_status != "DELETED",
                or_(
                    Document.review_status == "PENDING",
                    (Document.review_status == "PROCESSING")
                    & (Document.review_lease_expires_at <= now),
                ),
            )
            .order_by(Document.created_at, Document.id)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        if document is None:
            return False
        identifier, token = document.id, str(uuid4())
        exhausted = document.review_attempts >= 3
        document.review_status = "PROCESSING"
        document.review_lease_token = token
        document.review_lease_expires_at = now + timedelta(seconds=180)
        document.review_attempts += 1
        record_event(session, identifier, "review_claimed")
        previous = session.scalar(
            select(Document)
            .where(
                Document.policy_id == document.policy_id,
                Document.version < document.version,
                Document.status == "READY",
                Document.extraction_status == "VERIFIED",
                Document.publication_status != "DELETED",
            )
            .order_by(Document.version.desc())
            .limit(1)
        )
        sensitivities = [document.sensitivity] + ([previous.sensitivity] if previous else [])
        title, warnings = document.title, document.warnings

        def sections(doc):
            return (
                [
                    {"id": s.id, "text": s.text, "source": s.source}
                    for s in session.scalars(
                        select(Section)
                        .where(Section.document_id == doc.id)
                        .order_by(Section.ordinal)
                    )
                ]
                if doc
                else []
            )

        current_sections, previous_sections = sections(document), sections(previous)
    if exhausted:
        result = Assessment(
            "none",
            None,
            "failed",
            True,
            "high",
            ["attempts_exhausted"],
            "Interrupted assessments exhausted retries. Human review is required.",
            [],
            {},
        )
    else:
        result = assess(
            settings_for(sessions).review,
            title,
            current_sections,
            previous_sections,
            sensitivities,
            warnings,
            provider_factory,
        )
    with sessions.begin() as session:
        document = session.get(Document, identifier, with_for_update=True)
        if (
            document is None
            or document.publication_status == "DELETED"
            or document.review_lease_token != token
            or document.review_status != "PROCESSING"
            or utc(document.review_lease_expires_at) <= datetime.now(UTC)
        ):
            return True
        session.add(ReviewAssessment(id=str(uuid4()), document_id=identifier, **asdict(result)))
        document.review_status = "DONE"
        document.review_lease_token = document.review_lease_expires_at = None
        record_event(session, identifier, "review_" + result.assessment_status)
    return True
