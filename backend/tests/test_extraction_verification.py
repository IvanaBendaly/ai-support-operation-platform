"""BR-01 Architecture B: quality, fallback, DPP subset, field confidence and human verification."""

import json

import httpx2
import pytest
from knowledge_fixtures import approve_fixture
from sqlalchemy import select
from test_knowledge import pdf

from northstar.config import ExtractionSettings
from northstar.domain import DomainError
from northstar.retrieval import verification
from northstar.retrieval.extraction import IngestionError
from northstar.retrieval.extraction_review import verify
from northstar.retrieval.fields import evaluate_fields, external_allowed, extract_fields
from northstar.retrieval.models import Document, ExtractionRecord, RetrievalIndex, Section
from northstar.retrieval.search import RetrievalService
from northstar.retrieval.service import KnowledgeService, retrieval_sections
from northstar.retrieval.worker import convert_isolated, run_once
from northstar.storage import store_for

POLICY = (
    b"# Refunds\nPaid invoices may be refunded within thirty days of payment when the "
    b"account owner submits a written request."
)
SCHEMA = {"type": "object", "properties": {"policy_id": {"type": "string"}}}
LEVELS = ["UNCLASSIFIED", "PUBLIC", "INTERNAL", "CONFIDENTIAL", "HIGHLY_RESTRICTED", "unknown"]


def upload(sessions, data=POLICY, filename="refunds.md", sensitivity="PUBLIC", **kwargs):
    return KnowledgeService(sessions).ingest(
        "refunds", filename, data, title="Refunds", sensitivity=sensitivity, defer=True, **kwargs
    )["document"]


def state(sessions, identifier):
    with sessions() as session:
        doc = session.get(Document, identifier)
        records = session.scalars(
            select(ExtractionRecord)
            .where(ExtractionRecord.document_id == identifier)
            .order_by(ExtractionRecord.revision)
        ).all()
        return doc, records


def statuses(checks):
    return {c["rule"]: c["status"] for c in checks}


# B1/B2: deterministic checks for native text; Docling diagnostics only when present.


def test_native_text_passes_deterministic_checks_and_is_verified():
    result = verification.pipeline("refunds.md", POLICY)
    assert result["status"] == "VERIFIED" and len(result["attempts"]) == 1
    attempt = result["attempts"][0]
    assert attempt["metadata"]["parser"] == "python" and attempt["quality"]["outcome"] == (
        "ACCEPTABLE"
    )
    assert not any(c["rule"].endswith("_score") for c in attempt["quality"]["checks"])
    assert result["field_assessment"]["status"] == "SKIPPED"


@pytest.mark.parametrize(
    ("data", "rule"),
    [(b"Too short to trust.", "minimum_content"), (POLICY + "�".encode(), "text_integrity")],
)
def test_suspicious_text_is_uncertain_not_accepted(data, rule):
    result = verification.pipeline("refunds.txt", data)
    assert result["status"] == "HUMAN_REQUIRED"
    assert result["attempts"][0]["quality"]["outcome"] == "UNCERTAIN"
    assert statuses(result["attempts"][0]["quality"]["checks"])[rule] == "FAIL"


def docling_metadata(score, pages=(1, 2)):
    return {
        "parser": "docling",
        "page_count": 2,
        "confidence": dict.fromkeys(
            ("parse_score", "layout_score", "ocr_score", "table_score"), score
        ),
        "page_confidence": {},
        "warnings": [],
        "elements": [{"text": "Text", "pages": [p]} for p in pages],
    }


def test_missing_or_low_confidence_never_counts_as_pass():
    text = "x" * 100
    # No evaluated floor: a high score is still NOT_EVALUATED, never PASS.
    unset = verification.quality(text, docling_metadata(0.99), ExtractionSettings())
    assert statuses(unset["checks"])["parse_score"] == "NOT_EVALUATED"
    assert unset["outcome"] == "UNCERTAIN"
    floor = ExtractionSettings(confidence_floor=0.8)
    for score in (None, float("nan")):
        missing = verification.quality(text, docling_metadata(score), floor)
        assert statuses(missing["checks"])["parse_score"] == "NOT_EVALUATED"
        assert missing["outcome"] == "UNCERTAIN"
    low = verification.quality(text, docling_metadata(0.5), floor)
    assert statuses(low["checks"])["parse_score"] == "FAIL"
    good = verification.quality(text, docling_metadata(0.9), floor)
    assert good["outcome"] == "ACCEPTABLE"
    gap = verification.quality(text, docling_metadata(0.9, pages=(1,)), floor)
    assert statuses(gap["checks"])["page_coverage"] == "FAIL"


# B3: LiteParse runs only for non-acceptable PDFs and the first attempt is preserved.


def test_unreadable_pdf_tries_liteparse_and_never_accepts_empty_output():
    result = verification.pipeline("scan.pdf", pdf(False))
    assert [a["metadata"]["parser"] for a in result["attempts"]] == ["docling", "liteparse"]
    assert all(a["quality"]["outcome"] == "FAILED" for a in result["attempts"])
    assert result["result"] is None and result["error"] == "empty_or_unreadable_text"
    assert result["status"] == "HUMAN_REQUIRED"


def test_fallback_is_selective_and_preserves_first_attempt(monkeypatch):
    called = []
    monkeypatch.setattr(verification, "liteparse", lambda data: called.append(data))
    assert verification.pipeline("refunds.md", POLICY)["status"] == "VERIFIED"
    assert verification.pipeline("refunds.txt", b"short")["status"] == "HUMAN_REQUIRED"
    disabled = verification.pipeline(
        "scan.pdf", pdf(False), ExtractionSettings(liteparse_enabled=False)
    )
    assert len(disabled["attempts"]) == 1 and not called


def test_acceptable_fallback_is_selected_with_history(monkeypatch):
    text = "Refunds require a written request. " * 4

    def broken(filename, data, metadata):
        raise IngestionError("corrupt_pdf")

    def recovered(data):
        element = {"kind": "text", "text": text, "source": "page:1", "pages": [1], "order": 1}
        metadata = {"parser": "liteparse", "page_count": 1, "elements": [element]}
        return ("application/pdf", text, [("page:1;offset:0", text)], []), metadata

    monkeypatch.setattr(verification, "extract", broken)
    monkeypatch.setattr(verification, "liteparse", recovered)
    result = verification.pipeline("policy.pdf", b"%PDF")
    assert result["selected"] == 1 and result["result"][1] == text
    assert result["attempts"][0]["error"] == "corrupt_pdf"
    # Visual DPP rules cannot be automated, so a recovered PDF still needs a human.
    assert result["status"] == "HUMAN_REQUIRED"


def test_real_liteparse_reads_text_pdf():
    result, metadata = verification.liteparse(pdf())
    assert "Refund policy" in result[1] and metadata["parser"] == "liteparse"
    assert metadata["parser_version"] and metadata["page_count"] == 1


# B4: rule-level PASS / FAIL / NOT_EVALUATED, never a single accuracy score.


def test_dpp_subset_reports_rule_outcomes():
    elements = [
        {"kind": "section_header", "text": "Refunds", "source": "a", "order": 1},
        {"kind": "list_item", "text": "", "source": "b", "order": 2},
        {"kind": "table", "text": "", "source": "c", "order": 4, "table": {"rows": [[1, 2], [3]]}},
    ]
    result = verification.dpp({"parser": "docling", "elements": elements})
    outcomes = {(c["rule"], c["source"]): c["status"] for c in result["checks"]}
    assert outcomes[("heading_content", "a")] == "PASS"
    assert outcomes[("list_content", "b")] == "FAIL"
    assert outcomes[("table_shape", "c")] == "FAIL"
    assert outcomes[("order_sequence", "")] == "FAIL"
    assert outcomes[("visual_reading_order", "")] == "NOT_EVALUATED"
    assert result["requires_human"] and {c["status"] for c in result["checks"]} == {
        "PASS",
        "FAIL",
        "NOT_EVALUATED",
    }


# B5: optional, policy-gated, field-scoped confidence.


@pytest.mark.parametrize("level", LEVELS)
def test_external_field_extraction_respects_classification(level):
    everything = ExtractionSettings(
        external_public_allowed=True,
        external_internal_allowed=True,
        external_confidential_exception=True,
    )
    expected = level in {"PUBLIC", "INTERNAL", "CONFIDENTIAL"}
    assert external_allowed(everything, level) is expected
    assert not external_allowed(ExtractionSettings(), level)


def field_settings(**kwargs):
    options = dict(
        field_schema=SCHEMA,
        field_confidence_floor=0.9,
        llamaextract_api_key="test-key",
        llamaextract_project_id="project-1",
        external_public_allowed=True,
        external_internal_allowed=True,
        external_confidential_exception=True,
    )
    options.update(kwargs)
    return ExtractionSettings(**options)


def mock_llamaextract(monkeypatch, handler):
    calls = []
    real = httpx2.Client

    def recording(request):
        calls.append(request)
        return handler(request)

    monkeypatch.setattr(
        httpx2, "Client", lambda **kw: real(transport=httpx2.MockTransport(recording), **kw)
    )
    return calls


def completed(confidence=0.97, citation=({"page": 1, "matching_text": "P-1"},)):
    return {
        "id": "ext-abc",
        "status": "COMPLETED",
        "extract_result": {"policy_id": "P-1"},
        "extract_metadata": {
            "field_metadata": {
                "document_metadata": {
                    "policy_id": {"confidence": confidence, "citation": list(citation)}
                }
            }
        },
    }


def test_restricted_and_unconfigured_field_extraction_never_calls_out(monkeypatch):
    calls = mock_llamaextract(monkeypatch, lambda r: httpx2.Response(500))
    assert extract_fields(ExtractionSettings(), "PUBLIC", "a.pdf", b"x")["reason"] == (
        "schema_not_configured"
    )
    for level in ("HIGHLY_RESTRICTED", "UNCLASSIFIED", "unknown"):
        result = extract_fields(field_settings(), level, "a.pdf", b"x")
        assert result == {
            "status": "SKIPPED",
            "reason": "external_processing_prohibited",
            "requires_human": True,
        }
    unconfigured = field_settings(llamaextract_api_key=None)
    assert extract_fields(unconfigured, "PUBLIC", "a.pdf", b"x")["status"] == "HUMAN_REQUIRED"
    assert not calls


def test_llamaextract_wire_contract_and_grounded_confidence(monkeypatch):
    def handler(request):
        if request.url.path == "/api/v1/beta/files":
            return httpx2.Response(200, json={"id": "file-1"})
        if request.method == "POST":
            return httpx2.Response(200, json={"id": "ext-abc", "status": "PENDING"})
        return httpx2.Response(200, json=completed())

    calls = mock_llamaextract(monkeypatch, handler)
    result = extract_fields(field_settings(), "PUBLIC", "a.pdf", b"%PDF")
    assert result["status"] == "ACCEPTABLE" and result["fields"][0]["confidence"] == 0.97
    assert all(c.headers["Authorization"] == "Bearer test-key" for c in calls)
    job = json.loads(calls[1].content)
    assert job["configuration"]["cite_sources"] and job["configuration"]["confidence_scores"]
    assert calls[1].url.params["project_id"] == "project-1"


def test_llamaextract_failure_discards_remote_error_body(monkeypatch):
    mock_llamaextract(monkeypatch, lambda r: httpx2.Response(500, text="secret policy text"))
    result = extract_fields(field_settings(), "PUBLIC", "a.pdf", b"%PDF")
    assert result == {"status": "HUMAN_REQUIRED", "reason": "llamaextract_failed_or_timed_out"}


@pytest.mark.parametrize(
    ("payload", "schema", "floor"),
    [
        (completed(confidence=None), SCHEMA, 0.9),
        (completed(confidence=0.5), SCHEMA, 0.9),
        (completed(citation=()), SCHEMA, 0.9),
        (completed(citation=({"page": 0, "matching_text": "P-1"},)), SCHEMA, 0.9),
        (completed(), SCHEMA, None),
        (completed(), {"properties": {"policy_id": {"type": "object"}}}, 0.9),
    ],
)
def test_unsupported_or_ungrounded_fields_need_review(payload, schema, floor):
    result = evaluate_fields(payload, schema, floor)
    assert result["status"] == "HUMAN_REQUIRED"
    assert result["fields"][0]["status"] == "HUMAN_REQUIRED"


def test_isolated_worker_records_field_policy_for_restricted_documents():
    output = convert_isolated(
        {
            "data": POLICY,
            "filename": "refunds.md",
            "sensitivity": "HIGHLY_RESTRICTED",
            "extraction_settings": field_settings().model_dump(mode="json")
            | {"llamaextract_api_key": "test-key"},
        }
    )
    assert output["verification"]["field_assessment"]["reason"] == (
        "external_processing_prohibited"
    )
    assert output["verification"]["status"] == "HUMAN_REQUIRED" and output["result"]


# B6/B7: human decisions, provenance and separation from publication.


def test_worker_persists_parser_provenance_and_verified_is_not_published(business):
    sessions, _ = business
    document = upload(sessions)
    assert run_once(sessions)
    doc, records = state(sessions, document["id"])
    assert doc.extraction_status == "VERIFIED" and doc.publication_status == "PENDING_REVIEW"
    payload = records[-1].payload
    assert payload["attempts"][0]["metadata"]["parser_version"] == "utf8-v1"
    assert payload["dpp"]["rubric"] == "northstar-dpp-subset-v1"
    with sessions() as session:
        assert not retrieval_sections(session)


def test_correction_is_audited_and_keeps_previous_revisions(business):
    sessions, _ = business
    document = upload(sessions, data=b"Refunds within 30 dys.", filename="refunds.txt")
    run_once(sessions)
    doc, records = state(sessions, document["id"])
    assert doc.extraction_status == "HUMAN_REQUIRED"
    with pytest.raises(DomainError, match="reason"):
        verify(sessions, doc.id, "ACCEPT", " ", doc.extraction_revision)
    with pytest.raises(DomainError, match="Refresh"):
        verify(sessions, doc.id, "ACCEPT", "Checked", doc.extraction_revision - 1)
    corrected = [{"source": "line:1;heading:", "text": "Refunds within 30 days."}]
    verify(sessions, doc.id, "CORRECT", "Fixed typo", doc.extraction_revision, corrected)
    doc, records = state(sessions, document["id"])
    assert [r.status for r in records] == ["HUMAN_REQUIRED", "VERIFIED"]
    assert records[0].payload["attempts"], "parser history must survive a correction"
    latest = records[-1]
    assert latest.actor == "administrator" and latest.reason == "Fixed typo"
    assert latest.payload["previous_sections"][0]["text"] == "Refunds within 30 dys."
    with sessions() as session:
        texts = session.scalars(select(Section.text).where(Section.document_id == doc.id)).all()
    assert texts == ["Refunds within 30 days."]
    assert doc.publication_status == "PENDING_REVIEW"


def test_reject_blocks_publication_and_reprocess_keeps_original(business):
    sessions, _ = business
    document = upload(sessions, data=b"Unclear scan text.", filename="refunds.txt")
    run_once(sessions)
    doc, _ = state(sessions, document["id"])
    verify(sessions, doc.id, "REJECT", "Unreadable", doc.extraction_revision)
    with pytest.raises(DomainError, match="Verify extraction"):
        KnowledgeService(sessions).decide(doc.id, "APPROVED", "Attempted bypass")
    doc, _ = state(sessions, document["id"])
    verify(sessions, doc.id, "REPROCESS", "Try again", doc.extraction_revision)
    doc, _ = state(sessions, document["id"])
    assert doc.status == "QUEUED" and doc.extraction_status == "PENDING"
    assert run_once(sessions)
    doc, records = state(sessions, document["id"])
    assert [r.status for r in records] == [
        "HUMAN_REQUIRED",
        "REJECTED",
        "PENDING",
        "HUMAN_REQUIRED",
    ]
    assert store_for(sessions).get(doc.storage_key, doc.original_hash) == b"Unclear scan text."


def test_reverifying_published_content_withdraws_it(business):
    sessions, _ = business
    document = upload(sessions)
    run_once(sessions)
    approve_fixture(sessions, document["id"])
    RetrievalService(sessions).synchronize()
    with sessions() as session:
        assert retrieval_sections(session) and session.get(RetrievalIndex, "active")
    doc, _ = state(sessions, document["id"])
    verify(sessions, doc.id, "REJECT", "Found an error after publication", doc.extraction_revision)
    with sessions() as session:
        assert not retrieval_sections(session)
        assert session.get(RetrievalIndex, "active") is None
        assert session.get(Document, doc.id).publication_status == "PENDING_REVIEW"


def test_restricted_verification_requires_approved_environment(business):
    sessions, _ = business
    settings = sessions.kw["info"]["settings"]
    approved = settings.model_copy(
        update={
            "storage": settings.storage.model_copy(update={"restricted_environment_approved": True})
        }
    )
    sessions.kw["info"]["settings"] = approved
    document = upload(sessions, sensitivity="HIGHLY_RESTRICTED")
    run_once(sessions)
    sessions.kw["info"]["settings"] = settings
    doc, _ = state(sessions, document["id"])
    with pytest.raises(DomainError, match="Restricted environment"):
        verify(sessions, doc.id, "ACCEPT", "Checked", doc.extraction_revision)
