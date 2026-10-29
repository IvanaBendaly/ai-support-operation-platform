"""Existing retrieval fixtures explicitly classify and human-approve synthetic public policies."""

from northstar.ai.worker import run_review_once
from northstar.retrieval.service import KnowledgeService


def verify_fixture(sessions, identifier):
    """Human B6 acceptance for synthetic fixtures that automated checks left uncertain."""
    from northstar.retrieval.extraction_review import verify
    from northstar.retrieval.models import Document

    with sessions() as session:
        doc = session.get(Document, identifier)
        revision, status = doc.extraction_revision, doc.extraction_status
    if status != "VERIFIED":
        verify(sessions, identifier, "ACCEPT", "Synthetic extraction checked", revision)


def approve_fixture(sessions, identifier):
    verify_fixture(sessions, identifier)
    while run_review_once(sessions):
        pass
    return KnowledgeService(sessions).decide(
        identifier, "APPROVED", "Synthetic fixture reviewed for test"
    )


class PublishedKnowledgeService(KnowledgeService):
    def ingest(self, *args, **kwargs):
        kwargs.setdefault("title", "Synthetic test policy")
        kwargs.setdefault("sensitivity", "PUBLIC")
        result = super().ingest(*args, **kwargs)
        if not result["duplicate"] and result["document"]["status"] == "READY":
            result["document"] = approve_fixture(self.sessions, result["document"]["id"])
        return result
