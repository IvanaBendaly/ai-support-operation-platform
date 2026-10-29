import json
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock

import pytest
from knowledge_fixtures import verify_fixture
from pydantic import ValidationError
from sqlalchemy import event, inspect, select
from starlette.testclient import TestClient

from northstar.ai.review import (
    Classification,
    OllamaProvider,
    OpenAIProvider,
    assess,
    choose_provider,
)
from northstar.ai.worker import run_review_once
from northstar.config import ReviewSettings, Settings
from northstar.domain import DomainError
from northstar.main import create_app
from northstar.retrieval.models import Document, DocumentEvent, ReviewAssessment, StoredObject
from northstar.retrieval.service import KnowledgeService, retrieval_sections
from northstar.retrieval.worker import run_once
from northstar.storage import StorageError, store_for
from northstar.storage_admin import cleanup

TOKEN = "test-document-administrator-token-123456"
VALID = dict(
    needs_review=False,
    review_reasons=[],
    risk_level="low",
    explanation="No issues detected in the supplied passages.",
    supporting_references=[],
)


def fake_factory(raw=None, fails=False):
    provider = Mock(name="provider")
    provider.name = "ollama"
    provider.model = "qwen3:4b"
    if fails:
        provider.classify.side_effect = TimeoutError("do not persist private text or credential")
    else:
        provider.classify.return_value = (
            json.dumps(VALID if raw is None else raw),
            {"input_tokens": 100, "output_tokens": 20},
        )
    factory = Mock(return_value=Mock(return_value=provider))
    return factory, provider


def upload(
    sessions,
    data=b"An explicit policy requires manager approval before any employee leave begins.",
    **kwargs,
):
    options = dict(sensitivity="PUBLIC", title="Leave policy", defer=True)
    options.update(kwargs)
    return KnowledgeService(sessions).ingest("leave", "leave.txt", data, **options)["document"]


@pytest.mark.parametrize(
    "level,external,local,restricted,expected",
    [
        ("PUBLIC", True, True, False, "openai"),
        ("PUBLIC", False, True, False, "ollama"),
        ("INTERNAL", False, False, False, None),
        ("INTERNAL", True, True, False, "openai"),
        ("CONFIDENTIAL", False, True, False, "ollama"),
        ("CONFIDENTIAL", True, False, False, "openai"),
        ("HIGHLY_RESTRICTED", True, True, False, None),
        ("HIGHLY_RESTRICTED", True, True, True, "ollama"),
        ("UNCLASSIFIED", True, True, True, None),
        ("unknown", True, True, True, None),
    ],
)
def test_routing_matrix(level, external, local, restricted, expected):
    settings = ReviewSettings(
        provider="auto",
        openai_api_key="test-key",
        local_environment_approved=local,
        restricted_local_approved=restricted,
        external_public_allowed=external,
        external_internal_allowed=external,
        external_confidential_exception=external,
    )
    assert choose_provider(settings, [level]) == expected


def test_previous_version_sensitivity_and_absent_key_are_respected():
    settings = ReviewSettings(
        provider="auto",
        openai_api_key="test-key",
        external_public_allowed=True,
        local_environment_approved=True,
    )
    assert choose_provider(settings, ["PUBLIC", "CONFIDENTIAL"]) == "ollama"
    assert choose_provider(settings, ["PUBLIC", "HIGHLY_RESTRICTED"]) is None
    assert (
        choose_provider(settings.model_copy(update={"openai_api_key": None}), ["PUBLIC"])
        == "ollama"
    )


def test_prohibited_content_never_constructs_provider():
    factory = Mock(side_effect=AssertionError("must not construct or call provider"))
    result = assess(
        ReviewSettings(provider="auto", openai_api_key="test-key", external_public_allowed=True),
        "Title",
        [{"id": "a", "text": "secret"}],
        [],
        ["HIGHLY_RESTRICTED"],
        [],
        factory,
    )
    assert result.assessment_status == "unavailable" and result.needs_review
    factory.assert_not_called()


def test_timeout_fails_closed_without_external_fallback():
    factory, provider = fake_factory(fails=True)
    settings = ReviewSettings(
        provider="auto", local_environment_approved=True, openai_api_key="test-key"
    )
    result = assess(
        settings, "Title", [{"id": "a", "text": "Private policy"}], [], ["INTERNAL"], [], factory
    )
    assert (
        result.assessment_status == "failed" and result.risk_level == "high" and result.needs_review
    )
    factory.assert_called_once_with("ollama")
    provider.classify.assert_called_once()
    assert "credential" not in result.explanation


@pytest.mark.parametrize(
    "raw",
    [
        {**VALID, "needs_review": "false"},
        {**VALID, "approve": True},
        {**VALID, "supporting_references": [{"section_id": "invented", "quote": "secret"}]},
        {**VALID, "supporting_references": [{"section_id": "a", "quote": "invented passage"}]},
        {**VALID, "risk_level": "high"},
    ],
)
def test_invalid_schema_and_fabricated_citations_fail_closed(raw):
    factory, _ = fake_factory(raw)
    result = assess(
        ReviewSettings(provider="ollama", local_environment_approved=True),
        "Title",
        [{"id": "a", "text": "Real policy."}],
        [],
        ["PUBLIC"],
        [],
        factory,
    )
    assert result.assessment_status == "failed" and result.needs_review


def test_deterministic_warnings_override_low_risk_and_bound_input():
    factory, provider = fake_factory()
    result = assess(
        ReviewSettings(provider="ollama", local_environment_approved=True, max_input_chars=2000),
        "Title",
        [{"id": "a", "text": "x" * 3000}],
        [],
        ["PUBLIC"],
        ["review_extraction_quality"],
        factory,
    )
    assert result.assessment_status == "completed" and result.needs_review
    assert set(result.review_reasons) == {"extraction_quality", "incomplete_comparison"}
    content = json.loads(provider.classify.call_args.args[0][1]["content"])
    assert sum(len(s["text"]) for s in content["sections"]) == 2000


def test_provider_wire_contracts_and_refusal(monkeypatch):
    transport = Mock(
        return_value={
            "status": "completed",
            "output": [{"content": [{"type": "output_text", "text": json.dumps(VALID)}]}],
            "usage": {"input_tokens": 12, "output_tokens": 4},
        }
    )
    monkeypatch.setattr("northstar.ai.review.post_json", transport)
    settings = ReviewSettings(openai_api_key="test-key")
    raw, usage = OpenAIProvider(settings).classify([])
    assert (
        Classification.model_validate_json(raw).needs_review is False
        and usage["input_tokens"] == 12
    )
    payload = transport.call_args.args[1]
    assert payload["store"] is False and payload["text"]["format"]["strict"] is True
    transport.return_value = {"status": "completed", "output": [{"content": [{"type": "refusal"}]}]}
    with pytest.raises(ValueError, match="refusal"):
        OpenAIProvider(settings).classify([])
    transport.return_value = {"done": True, "message": {"content": json.dumps(VALID)}}
    OllamaProvider(settings).classify([])
    payload = transport.call_args.args[1]
    assert payload["think"] is False and payload["stream"] is False
    assert payload["format"]["additionalProperties"] is False


@pytest.mark.parametrize(
    "url",
    ["https://ollama.com", "http://8.8.8.8", "http://user:pass@localhost", "http://localhost/path"],
)
def test_local_provider_rejects_public_or_credentialed_endpoints(url):
    with pytest.raises(ValidationError):
        ReviewSettings(ollama_url=url)


def test_storage_extraction_review_and_human_approval_are_separate(business):
    sessions, _ = business
    document = upload(sessions)
    with sessions() as session:
        row = session.get(Document, document["id"])
        assert not hasattr(row, "original")
        assert row.storage_key.startswith("originals/")
        assert (
            store_for(sessions).get(row.storage_key, row.original_hash).startswith(b"An explicit")
        )
    assert run_once(sessions)
    with sessions() as session:
        assert not retrieval_sections(session)
        # Below the configured minimum length: automated checks cannot accept it.
        assert session.get(Document, document["id"]).extraction_status == "HUMAN_REQUIRED"
    with pytest.raises(DomainError, match="Verify extraction"):
        KnowledgeService(sessions).decide(document["id"], "APPROVED", "Human review")
    # The content classifier never receives unverified extraction output.
    assert not run_review_once(sessions)
    verify_fixture(sessions, document["id"])
    with pytest.raises(DomainError, match="assessment"):
        KnowledgeService(sessions).decide(document["id"], "APPROVED", "Human review")
    assert run_review_once(sessions)
    with sessions() as session:
        assessment = session.scalar(select(ReviewAssessment))
        assert assessment.assessment_status == "unavailable" and assessment.needs_review
        assert not retrieval_sections(session)
    KnowledgeService(sessions).decide(
        document["id"], "APPROVED", "Manually checked source despite unavailable AI"
    )
    with sessions() as session:
        assert retrieval_sections(session)[0].document_id == document["id"]
        assert session.scalar(
            select(DocumentEvent).where(DocumentEvent.action == "approved")
        ).reason


def test_rejected_replacement_keeps_active_and_restricted_never_indexed(business):
    sessions, _ = business
    first = upload(sessions)
    run_once(sessions)
    verify_fixture(sessions, first["id"])
    run_review_once(sessions)
    service = KnowledgeService(sessions)
    service.decide(first["id"], "APPROVED", "Checked")
    second = upload(sessions, b"A changed policy requiring human consideration.", replace=True)
    run_once(sessions)
    run_review_once(sessions)
    service.decide(second["id"], "REJECTED", "Conflicting revision")
    with sessions() as session:
        assert retrieval_sections(session)[0].document_id == first["id"]
    private = upload(
        sessions, b"Private internal rules for staff only.", replace=True, sensitivity="INTERNAL"
    )
    run_once(sessions)
    verify_fixture(sessions, private["id"])
    run_review_once(sessions)
    service.decide(private["id"], "APPROVED", "Internal only")
    with sessions() as session:
        assert not retrieval_sections(session)
    with pytest.raises(DomainError, match="lower"):
        upload(sessions, b"Attempted downgrade", replace=True, sensitivity="PUBLIC")


def test_missing_classification_and_auth_block_upload(business):
    sessions, _ = business
    settings = Settings(
        _env_file=None,
        environment="test",
        database_url="sqlite+pysqlite:///:memory:",
        admin_token=TOKEN,
    )
    with TestClient(create_app(settings, sessions.kw["bind"])) as client:
        assert client.post("/api/admin/documents").status_code == 401
        client.headers["Authorization"] = "Bearer " + TOKEN
        response = client.post(
            "/api/admin/documents",
            data={"policy_id": "leave", "title": "Leave"},
            files={"file": ("a.txt", b"Policy")},
        )
        assert response.status_code == 422
        response = client.post(
            "/api/admin/documents",
            data={"policy_id": "leave", "title": "Leave", "sensitivity": "HIGHLY_RESTRICTED"},
            files={"file": ("a.txt", b"Policy")},
        )
        assert response.status_code == 403
    with sessions() as session:
        assert session.scalar(select(Document)) is None


def test_failed_database_write_has_safe_durable_orphan_cleanup(business):
    sessions, _ = business

    def broken(*args):
        raise RuntimeError("injected database failure")

    event.listen(Document, "before_insert", broken)
    try:
        with pytest.raises(RuntimeError):
            upload(sessions)
    finally:
        event.remove(Document, "before_insert", broken)
    with sessions.begin() as session:
        reservation = session.scalar(select(StoredObject))
        reservation.created_at = datetime.now(UTC) - timedelta(days=2)
    assert cleanup(sessions) == 1
    assert cleanup(sessions, apply=True) == 1
    assert cleanup(sessions) == 0
    active = upload(sessions)
    with sessions.begin() as session:
        session.scalar(select(StoredObject)).created_at = datetime.now(UTC) - timedelta(days=2)
    assert cleanup(sessions, apply=True) == 0
    assert active["id"]


def test_storage_missing_object_never_becomes_ready(business):
    sessions, _ = business
    document = upload(sessions)
    with sessions() as session:
        row = session.get(Document, document["id"])
        store_for(sessions).delete(row.storage_key)
        with pytest.raises(StorageError):
            store_for(sessions).get(row.storage_key, row.original_hash)
    assert run_once(sessions)
    with sessions() as session:
        assert session.get(Document, document["id"]).status == "PROCESSING"
        assert not retrieval_sections(session)


def test_database_has_no_original_column(business):
    sessions, _ = business
    assert "original" not in {
        c["name"] for c in inspect(sessions.kw["bind"]).get_columns("knowledge_documents")
    }


def test_stale_review_worker_cannot_commit_and_expired_claim_recovers(business):
    sessions, _ = business
    document = upload(sessions)
    run_once(sessions)
    verify_fixture(sessions, document["id"])
    original_settings = sessions.kw["info"]["settings"]
    sessions.kw["info"]["settings"] = original_settings.model_copy(
        update={"review": ReviewSettings(provider="ollama", local_environment_approved=True)}
    )
    factory, provider = fake_factory()

    def stale(messages):
        with sessions.begin() as session:
            row = session.get(Document, document["id"])
            row.review_lease_token = "another-worker"
            row.review_lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
        return json.dumps(VALID), {}

    provider.classify.side_effect = stale
    assert run_review_once(sessions, factory)
    with sessions() as session:
        assert session.scalar(select(ReviewAssessment)) is None
        assert session.get(Document, document["id"]).review_status == "PROCESSING"
    provider.classify.side_effect = None
    assert run_review_once(sessions, factory)
    assert not run_review_once(sessions, factory)
    with sessions() as session:
        assert len(session.scalars(select(ReviewAssessment)).all()) == 1
        assert session.get(Document, document["id"]).publication_status == "PENDING_REVIEW"


def test_review_result_and_status_roll_back_together(business):
    sessions, _ = business
    document = upload(sessions)
    run_once(sessions)
    verify_fixture(sessions, document["id"])

    def broken(*args):
        raise RuntimeError("injected review persistence failure")

    event.listen(ReviewAssessment, "before_insert", broken)
    try:
        with pytest.raises(RuntimeError):
            run_review_once(sessions)
    finally:
        event.remove(ReviewAssessment, "before_insert", broken)
    with sessions.begin() as session:
        assert session.scalar(select(ReviewAssessment)) is None
        row = session.get(Document, document["id"])
        assert row.review_status == "PROCESSING"
        row.review_attempts = 3
        row.review_lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
    factory = Mock(side_effect=AssertionError("exhausted claims must not call models"))
    assert run_review_once(sessions, factory)
    with sessions() as session:
        result = session.scalar(select(ReviewAssessment))
        assert result.assessment_status == "failed" and result.needs_review
        assert result.review_reasons == ["attempts_exhausted"]


@pytest.mark.postgres
def test_postgres_review_claims_are_exclusive(postgres_business):
    from concurrent.futures import ThreadPoolExecutor

    sessions, _ = postgres_business
    upload(sessions)
    run_once(sessions)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: run_review_once(sessions), range(2)))
    assert sum(results) == 1
    with sessions() as session:
        assert len(session.scalars(select(ReviewAssessment)).all()) == 1
