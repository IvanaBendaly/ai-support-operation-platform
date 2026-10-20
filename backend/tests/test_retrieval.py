import copy
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError
from sqlalchemy import event, select
from sqlalchemy.exc import OperationalError
from starlette.testclient import TestClient

from northstar.api import create_app
from northstar.config import RetrievalSettings, Settings
from northstar.domain import DomainError
from northstar.retrieval import representation
from northstar.retrieval.models import Document, RetrievalIndex, Section
from northstar.retrieval.search import RetrievalFailure, RetrievalService
from northstar.retrieval.service import KnowledgeService

NOW = datetime(2026, 10, 20, tzinfo=UTC)
CORPUS = json.loads((Path(__file__).parent / "fixtures/retrieval_corpus.json").read_text())


def populate(sessions):
    service = KnowledgeService(sessions)
    for policy in CORPUS:
        service.ingest(policy["id"], policy["id"] + ".md", policy["text"].encode(), NOW)
    return RetrievalService(sessions)


@pytest.fixture
def retrieval(business):
    sessions, _ = business
    return sessions, populate(sessions)


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("Can I get a refund for my paid invoice?", "refunds"),
        ("How can I cancel my subscription?", "cancellation"),
        ("How do I reset my password?", "login"),
        ("Where can I check a service outage?", "outage"),
        ("Can I upgrade my plan to Growth?", "upgrade"),
        ("Where are invoice receipts?", "invoices"),
        ("How do I export customer data?", "export"),
        ("How can I delete personal data?", "deletion"),
        ("I want my money back", "refunds"),
        ("I want to stop paying", "cancellation"),
        ("I am locked out", "login"),
    ],
)
def test_policy_selection_and_attribution(retrieval, query, expected):
    sessions, service = retrieval
    result = service.search(query, at=NOW)
    assert result.evidence, result
    assert result.evidence[0].policy_id == expected, result
    assert result.result_count == len(result.evidence)
    assert result.duration_ms >= 0 and result.index_status == "READY"
    with sessions() as session:
        for evidence in result.evidence:
            section = session.get(Section, evidence.section_id)
            document = session.get(Document, evidence.document_id)
            assert section.document_id == document.id
            assert section.text == evidence.text and section.source == evidence.source
            assert document.version == evidence.version
            assert evidence.section_id in result.context


def test_index_persistence_and_deterministic_reload(retrieval, monkeypatch):
    sessions, service = retrieval
    first = service.search("refund paid invoice", at=NOW)

    def no_rebuild(*args):
        raise AssertionError("Unchanged corpus must use persisted representations")

    monkeypatch.setattr(representation, "train", no_rebuild)
    second = RetrievalService(sessions).search("refund paid invoice", at=NOW)
    assert first.evidence == second.evidence
    assert first.index_generation == second.index_generation
    with sessions() as session:
        index = session.get(RetrievalIndex, "active")
        assert len(index.payload["embeddings"]) == len(CORPUS)
        assert index.model_id.startswith("northstar-lsa-hybrid-v1")


def test_empty_and_unrelated_are_explicit(business):
    sessions, _ = business
    service = RetrievalService(sessions)
    empty = service.search("refund", at=NOW)
    assert empty.status == "no_matches" and empty.reason == "no_active_documents"
    assert empty.evidence == [] and empty.context == ""
    populate(sessions)
    unrelated = service.search("astronomy telescope galaxies", at=NOW)
    assert unrelated.status == "no_matches" and unrelated.reason == "no_relevant_sections"


def test_replacement_failed_upload_deactivation_and_schedule(retrieval):
    sessions, service = retrieval
    ingestion = KnowledgeService(sessions)
    before = service.search("refund", at=NOW)
    old_id = before.evidence[0].document_id
    ingestion.ingest("refunds", "broken.pdf", b"corrupt", NOW, replace=True)
    unchanged = service.search("refund", at=NOW)
    assert unchanged.index_generation == before.index_generation
    new = ingestion.ingest(
        "refunds",
        "new.txt",
        b"Refund requests require approval from the finance team.",
        NOW + timedelta(days=1),
        NOW + timedelta(days=2),
        replace=True,
    )["document"]
    assert service.search("refund", at=NOW).index_generation == before.index_generation
    after = service.search("refund", at=NOW + timedelta(days=1))
    assert all(e.document_id != old_id for e in after.evidence)
    assert new["id"] in [e.document_id for e in after.evidence]
    with sessions() as session:
        stored_ids = session.get(RetrievalIndex, "active").payload["section_ids"]
        old_sections = session.scalars(
            select(Section.id).where(Section.document_id == old_id)
        ).all()
        assert not set(stored_ids) & set(old_sections)
    expired = service.search("refund", at=NOW + timedelta(days=2))
    assert not any(e.policy_id == "refunds" for e in expired.evidence)
    ingestion.deactivate("cancellation")
    deactivated = service.search("cancel subscription", at=NOW + timedelta(days=2))
    assert not any(e.policy_id == "cancellation" for e in deactivated.evidence)


def test_context_limits_never_cut_policy_clauses(retrieval):
    sessions, _ = retrieval
    settings = RetrievalSettings(result_limit=1, context_chars=500, section_chars=2000)
    result = RetrievalService(sessions, settings).search("refund paid invoice", at=NOW)
    assert len(result.context) <= 500 and result.result_count <= 1
    assert result.context_chars == len(result.context)
    for evidence in result.evidence:
        assert evidence.text == next(p["text"] for p in CORPUS if p["id"] == evidence.policy_id)
    tiny = RetrievalService(
        sessions, RetrievalSettings(context_chars=256, section_chars=128)
    ).search("refund", at=NOW)
    assert tiny.status == "insufficient_evidence" and tiny.budget_limited
    assert not tiny.evidence


def test_corrupt_or_partial_index_is_not_empty_evidence(retrieval):
    sessions, service = retrieval
    service.synchronize(at=NOW)
    with sessions.begin() as session:
        index = session.get(RetrievalIndex, "active")
        bad = copy.deepcopy(index.payload)
        bad["embeddings"].pop()
        index.payload, index.payload_hash = bad, representation.digest(bad)
    with pytest.raises(RetrievalFailure, match="incomplete or corrupt") as exc:
        service.search("refund", at=NOW)
    assert exc.value.code == "index_corrupt"
    service.synchronize(at=NOW, force=True)
    assert service.search("refund", at=NOW).evidence


def test_representation_failure_preserves_previous_snapshot(retrieval, monkeypatch):
    sessions, service = retrieval
    before = service.search("refund", at=NOW)
    KnowledgeService(sessions).ingest("extra", "extra.txt", b"Extra refund review policy", NOW)

    def unavailable(*args):
        raise RuntimeError("private provider failure details")

    monkeypatch.setattr(representation, "train", unavailable)
    with pytest.raises(RetrievalFailure) as exc:
        service.search("refund", at=NOW)
    assert exc.value.code == "representation_unavailable"
    assert "private" not in str(exc.value)
    with sessions() as session:
        assert session.get(RetrievalIndex, "active").generation == before.index_generation


def test_write_failure_rolls_back_snapshot(retrieval):
    sessions, service = retrieval
    before = service.search("refund", at=NOW)
    KnowledgeService(sessions).deactivate("refunds")

    def fail(*args):
        raise OperationalError("hidden SQL", {}, Exception("private connection info"))

    event.listen(RetrievalIndex, "before_update", fail)
    try:
        with pytest.raises(RetrievalFailure) as exc:
            service.search("refund", at=NOW)
        assert exc.value.code == "index_unavailable"
    finally:
        event.remove(RetrievalIndex, "before_update", fail)
    with sessions() as session:
        assert session.get(RetrievalIndex, "active").generation == before.index_generation
    assert all(e.policy_id != "refunds" for e in service.search("refund", at=NOW).evidence)


def test_missing_source_sections_fail_closed(retrieval):
    sessions, service = retrieval
    with sessions.begin() as session:
        document = session.scalar(select(Document).where(Document.policy_id == "refunds"))
        for section in session.scalars(select(Section).where(Section.document_id == document.id)):
            session.delete(section)
    with pytest.raises(RetrievalFailure) as exc:
        service.search("refund", at=NOW)
    assert exc.value.code == "source_inconsistent"


def test_ambiguous_candidates_and_query_reformulation(business):
    sessions, _ = business
    ingestion = KnowledgeService(sessions)
    ingestion.ingest("a", "a.txt", b"Refund requests are reviewed by finance.", NOW)
    ingestion.ingest("b", "b.txt", b"Refund requests are reviewed by support.", NOW)
    result = RetrievalService(sessions).search("refund requests", at=NOW)
    assert result.status == "ambiguous"
    assert len(result.evidence) == 2
    result = RetrievalService(sessions).search("I want my money back", at=NOW)
    assert result.query_expansions == ["refund"]


def test_invalid_queries_settings_and_corpus_limit(retrieval):
    sessions, service = retrieval
    for query in ["", "  ", "x" * 2001]:
        with pytest.raises(DomainError):
            service.search(query, at=NOW)
    with pytest.raises(ValidationError):
        RetrievalSettings(result_limit=10, candidate_limit=5)
    with pytest.raises(ValidationError):
        RetrievalSettings(min_score=float("nan"))
    with pytest.raises(RetrievalFailure) as exc:
        RetrievalService(sessions, RetrievalSettings(max_sections=1)).search("refund", at=NOW)
    assert exc.value.code == "corpus_limit"


def test_admin_api_auth_and_safe_failure(retrieval, monkeypatch):
    sessions, _ = retrieval
    token = "not-a-real-administrator-token-12345"
    settings = Settings(
        _env_file=None,
        environment="test",
        database_url="sqlite+pysqlite:///:memory:",
        admin_token=token,
    )
    with TestClient(create_app(settings, sessions.kw["bind"])) as client:
        assert (
            client.post("/api/admin/retrieval/search", json={"query": "refund"}).status_code == 401
        )
        client.headers["Authorization"] = "Bearer " + token
        assert client.post("/api/admin/retrieval/index").status_code == 200
        response = client.post("/api/admin/retrieval/search", json={"query": "refund"})
        assert response.status_code == 200 and response.json()["evidence"]
        assert client.post("/api/admin/retrieval/search", json={"query": " "}).status_code == 422

        def fail(*args):
            raise RuntimeError("do not reveal this")

        monkeypatch.setattr(representation, "rank", fail)
        response = client.post("/api/admin/retrieval/search", json={"query": "refund"})
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "representation_unavailable"
        assert "do not reveal" not in response.text


@pytest.mark.postgres
def test_postgres_retrieval_lifecycle(postgres_business):
    sessions, _ = postgres_business
    service = populate(sessions)
    test_replacement_failed_upload_deactivation_and_schedule((sessions, service))


def test_forced_rebuild_and_model_change_are_reproducible(retrieval):
    sessions, service = retrieval
    first = service.search("cancel subscription", at=NOW)
    rebuilt = service.synchronize(at=NOW, force=True)
    assert rebuilt["generation"] != first.index_generation
    assert service.search("cancel subscription", at=NOW).evidence == first.evidence
    changed = RetrievalService(sessions, RetrievalSettings(dimensions=2))
    result = changed.search("cancel subscription", at=NOW)
    assert result.model_id != first.model_id
    assert result.index_generation != rebuilt["generation"]
    assert result.evidence[0].policy_id == "cancellation"


def test_query_computation_failure_is_explicit(retrieval, monkeypatch):
    _, service = retrieval
    service.synchronize(at=NOW)

    def failed(*args):
        raise TimeoutError("local compute unavailable")

    monkeypatch.setattr(representation, "rank", failed)
    with pytest.raises(RetrievalFailure) as exc:
        service.search("refund", at=NOW)
    assert exc.value.code == "representation_unavailable"


def test_nonfinite_vectors_fail_validation(retrieval, monkeypatch):
    _, service = retrieval
    original = representation.train

    def invalid(*args):
        result = original(*args)
        result["embeddings"][0][0] = float("nan")
        return result

    monkeypatch.setattr(representation, "train", invalid)
    with pytest.raises(RetrievalFailure) as exc:
        service.search("refund", at=NOW)
    assert exc.value.code == "representation_unavailable"


def test_context_reference_includes_pdf_page(business):
    from test_knowledge import pdf

    sessions, _ = business
    KnowledgeService(sessions).ingest("pdf-policy", "policy.pdf", pdf(), NOW)
    evidence = RetrievalService(sessions).search("refund", at=NOW).evidence[0]
    assert evidence.source.startswith("page:1") and evidence.filename == "policy.pdf"


def test_nested_configuration(monkeypatch):
    monkeypatch.setenv("NORTHSTAR_RETRIEVAL__CONTEXT_CHARS", "1200")
    settings = Settings(
        _env_file=None, environment="test", database_url="sqlite+pysqlite:///:memory:"
    )
    assert settings.retrieval.context_chars == 1200


def test_lifecycle_change_during_search_is_not_returned(tmp_path, monkeypatch):
    from northstar.db import Base, make_engine, session_factory

    engine = make_engine(
        Settings(
            _env_file=None,
            environment="test",
            database_url=f"sqlite+pysqlite:///{tmp_path / 'race.db'}",
        )
    )
    Base.metadata.create_all(engine)
    sessions = session_factory(engine)
    service = populate(sessions)
    service.synchronize(at=NOW)
    original = representation.rank

    def deactivate_while_ranking(*args):
        KnowledgeService(sessions).deactivate("refunds")
        return original(*args)

    monkeypatch.setattr(representation, "rank", deactivate_while_ranking)
    try:
        with pytest.raises(RetrievalFailure) as exc:
            service.search("refund", at=NOW)
        assert exc.value.code == "index_changed"
    finally:
        engine.dispose()


@pytest.mark.postgres
def test_postgres_concurrent_index_builds(postgres_business):
    from concurrent.futures import ThreadPoolExecutor

    sessions, _ = postgres_business
    service = populate(sessions)

    def search(_):
        try:
            return service.search("refund", at=NOW)
        except RetrievalFailure as exc:
            # First-ever singleton creation can race; the loser must not return empty evidence.
            assert exc.code == "index_unavailable"
            return service.search("refund", at=NOW)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(search, range(2)))
    assert results[0].evidence == results[1].evidence
    with sessions() as session:
        assert len(session.scalars(select(RetrievalIndex)).all()) == 1
