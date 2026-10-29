from datetime import UTC, datetime, timedelta
from io import BytesIO

import pytest
from knowledge_fixtures import PublishedKnowledgeService as KnowledgeService
from knowledge_fixtures import approve_fixture
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
from sqlalchemy import event, select
from starlette.testclient import TestClient

from northstar.api import create_app
from northstar.config import Settings
from northstar.domain import DomainError
from northstar.retrieval.models import Document, Section
from northstar.retrieval.service import describe, retrieval_sections
from northstar.retrieval.worker import run_once

NOW = datetime(2026, 10, 20, tzinfo=UTC)
TOKEN = "test-administrator-token-not-real-1234"


def pdf(text=True):
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    if text:
        font = DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Helvetica"),
            }
        )
        page[NameObject("/Resources")] = DictionaryObject(
            {NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})}
        )
        stream = DecodedStreamObject()
        stream.set_data(b"BT /F1 12 Tf 50 700 Td (Refund policy: within 30 days.) Tj ET")
        page[NameObject("/Contents")] = writer._add_object(stream)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


@pytest.mark.parametrize(
    ("filename", "data", "source"),
    [
        ("policy.md", b"# Refunds\nRefund within 30 days.", "heading:Refunds"),
        ("policy.txt", b"Refunds are available within 30 days.", "line:1"),
        ("policy.pdf", pdf(), "page:1"),
    ],
)
def test_formats(business, filename, data, source):
    sessions, _ = business
    service = KnowledgeService(sessions)
    result = service.ingest("refunds", filename, data, NOW)["document"]
    assert result["status"] == "READY"
    assert source in result["sections"][0]["source"]
    with sessions() as session:
        assert len(retrieval_sections(session, NOW)) == 1
        from northstar.storage import store_for

        document = session.get(Document, result["id"])
        assert store_for(sessions).get(document.storage_key, document.original_hash) == data


@pytest.mark.parametrize(
    ("filename", "data", "error"),
    [
        ("bad.exe", b"hello", "unsupported_file_type"),
        ("bad.pdf", b"no pdf", "corrupt_pdf"),
        ("scan.pdf", pdf(False), "empty_or_unreadable_text"),
        ("empty.txt", b"", "empty_document"),
        ("bad.txt", b"\xff", "text_must_be_utf8"),
        ("bad.txt", b"a\x00b", "unreadable_text"),
    ],
)
def test_failures_are_inspectable(business, filename, data, error):
    sessions, _ = business
    result = KnowledgeService(sessions).ingest("broken", filename, data)["document"]
    assert result["status"] == "FAILED" and result["error"] == error
    assert result["sections"] == []
    with sessions() as session:
        assert not retrieval_sections(session)


def test_versions_scheduling_expiry_and_no_resurrection(business):
    sessions, _ = business
    service = KnowledgeService(sessions)
    old = service.ingest("policy", "one.txt", b"Old policy rules", NOW)["document"]
    failed = service.ingest("policy", "bad.pdf", b"bad", NOW, replace=True)["document"]
    new = service.ingest(
        "policy",
        "two.txt",
        b"New policy rules",
        NOW + timedelta(days=1),
        NOW + timedelta(days=2),
        replace=True,
    )["document"]
    assert [old["version"], failed["version"], new["version"]] == [1, 2, 3]
    with sessions() as session:
        assert retrieval_sections(session, NOW)[0].document_id == old["id"]
        assert retrieval_sections(session, NOW + timedelta(days=1))[0].document_id == new["id"]
        assert not retrieval_sections(session, NOW + timedelta(days=2))
        assert (
            describe(session, session.get(Document, old["id"]), NOW + timedelta(days=1))[
                "lifecycle"
            ]
            == "SUPERSEDED"
        )
    service.deactivate("policy")
    with sessions() as session:
        assert not retrieval_sections(session, NOW)


def test_duplicate_and_metadata_validation(business):
    sessions, _ = business
    service = KnowledgeService(sessions)
    first = service.ingest("one", "a.txt", b"Same content\r\n")
    duplicate = service.ingest("two", "b.txt", b"Same content\n")
    assert duplicate["duplicate"] and duplicate["document"]["id"] == first["document"]["id"]
    with pytest.raises(DomainError):
        service.ingest("one", "a.txt", b"different")
    with pytest.raises(DomainError):
        service.ingest("missing", "a.txt", b"different", replace=True)
    with pytest.raises(DomainError):
        service.ingest("three", "a.txt", b"different", NOW, NOW)


def test_partial_persistence_rolls_back(business):
    sessions, _ = business
    service = KnowledgeService(sessions)
    first = service.ingest("policy", "a.txt", b"original", NOW)["document"]

    def fail(*args):
        raise RuntimeError("simulated section write failure")

    event.listen(Section, "before_insert", fail)
    try:
        with pytest.raises(RuntimeError):
            service.ingest("policy", "b.txt", b"replacement", NOW, replace=True)
    finally:
        event.remove(Section, "before_insert", fail)
    with sessions() as session:
        assert len(session.scalars(select(Document)).all()) == 1
        assert retrieval_sections(session, NOW)[0].document_id == first["id"]


def test_api_upload_inspection_batch_and_deactivate(business):
    sessions, _ = business
    settings = Settings(
        _env_file=None,
        environment="test",
        database_url="sqlite+pysqlite:///:memory:",
        admin_token=TOKEN,
    )
    app = create_app(settings, sessions.kw["bind"])
    with TestClient(app) as client:
        assert client.post("/api/admin/documents").status_code == 401
        client.headers["Authorization"] = "Bearer " + TOKEN
        response = client.post(
            "/api/admin/documents",
            data={"policy_id": "policy", "title": "Policy", "sensitivity": "PUBLIC"},
            files={"file": ("a.md", b"# Rules\nOriginal policy")},
        )
        assert response.status_code == 200, response.text
        doc = response.json()["document"]
        assert doc["status"] == "QUEUED"
        assert run_once(sessions)
        approve_fixture(sessions, doc["id"])
        assert client.get("/api/admin/documents/" + doc["id"]).json()["sections"]
        assert len(client.get("/api/admin/documents").json()) == 1
        response = client.post(
            "/api/admin/documents/policies/policy/versions",
            data={"title": "Policy", "sensitivity": "PUBLIC"},
            files={"file": ("b.txt", b"Updated policy")},
        )
        assert response.json()["document"]["version"] == 2
        response = client.post(
            "/api/admin/documents/batch",
            files=[
                ("files", ("a.txt", b"Batch policy")),
                ("files", ("bad.pdf", b"bad")),
                ("policy_ids", (None, "batch")),
                ("policy_ids", (None, "bad")),
                ("titles", (None, "Batch")),
                ("titles", (None, "Bad")),
                ("sensitivities", (None, "PUBLIC")),
                ("sensitivities", (None, "PUBLIC")),
            ],
        )
        assert response.status_code == 200, response.text
        assert [r["document"]["status"] for r in response.json()] == ["QUEUED", "QUEUED"]
        while run_once(sessions):
            pass
        assert [
            client.get("/api/admin/documents/" + r["document"]["id"]).json()["status"]
            for r in response.json()
        ] == ["READY", "FAILED"]
        assert client.post("/api/admin/documents/policies/policy/deactivate").status_code == 200
        assert client.get("/api/admin/documents/" + doc["id"]).json()["lifecycle"] == "INACTIVE"
        assert client.get("/api/admin/documents/missing").status_code == 404


def test_bounds_warnings_and_disabled_admin(business):
    from northstar.retrieval.extraction import MAX_BYTES, IngestionError, extract

    sessions, _ = business
    with pytest.raises(IngestionError, match="file_too_large"):
        extract("big.txt", b"a" * (MAX_BYTES + 1))
    result = KnowledgeService(sessions).ingest("short", "short.txt", b"Short policy")
    assert "review_extraction_quality" in result["document"]["warnings"]
    settings = Settings(
        _env_file=None, environment="test", database_url="sqlite+pysqlite:///:memory:"
    )
    with TestClient(create_app(settings, sessions.kw["bind"])) as client:
        assert client.get("/api/admin/documents").status_code == 503
    settings = Settings(
        _env_file=None,
        environment="test",
        database_url="sqlite+pysqlite:///:memory:",
        admin_token=TOKEN,
    )
    with TestClient(
        create_app(settings, sessions.kw["bind"]), headers={"Authorization": "Bearer " + TOKEN}
    ) as client:
        response = client.post(
            "/api/admin/documents",
            data={"policy_id": "big", "title": "Big", "sensitivity": "PUBLIC"},
            files={"file": ("big.txt", b"a" * (MAX_BYTES + 1))},
        )
        assert response.status_code == 413
        response = client.post(
            "/api/admin/documents",
            data={"policy_id": "invalid", "valid_from": "not-a-date"},
            files={"file": ("a.txt", b"Valid text")},
        )
        assert response.status_code == 422


def test_document_deactivation_does_not_restore_previous_version(business):
    sessions, _ = business
    service = KnowledgeService(sessions)
    service.ingest("p", "a.txt", b"First policy", NOW)
    new = service.ingest("p", "b.txt", b"Second policy", NOW, replace=True)["document"]
    settings = Settings(
        _env_file=None,
        environment="test",
        database_url="sqlite+pysqlite:///:memory:",
        admin_token=TOKEN,
    )
    with TestClient(
        create_app(settings, sessions.kw["bind"]), headers={"Authorization": "Bearer " + TOKEN}
    ) as client:
        assert client.post("/api/admin/documents/" + new["id"] + "/deactivate").status_code == 200
    with sessions() as session:
        assert not retrieval_sections(session, NOW)


def test_business_reset_preserves_knowledge(business):
    from datetime import date

    from northstar.seed import reset_business

    sessions, _ = business
    doc = KnowledgeService(sessions).ingest("p", "a.txt", b"Preserved policy", NOW)["document"]
    reset_business(sessions, as_of=date(2026, 10, 20), environment="test")
    with sessions() as session:
        assert retrieval_sections(session, NOW)[0].document_id == doc["id"]


@pytest.mark.postgres
def test_postgres_document_lifecycle(postgres_business):
    test_versions_scheduling_expiry_and_no_resurrection(postgres_business)


@pytest.mark.postgres
def test_postgres_concurrent_duplicates(postgres_business):
    from concurrent.futures import ThreadPoolExecutor

    sessions, _ = postgres_business
    service = KnowledgeService(sessions)

    def ingest(identifier):
        try:
            return service.ingest(identifier, "a.txt", b"Same concurrent policy", NOW)
        except DomainError as exc:
            assert exc.code == "concurrent_ingestion"

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(ingest, ["one", "two"]))
    with sessions() as session:
        assert len(session.scalars(select(Document)).all()) == 1
        assert len(retrieval_sections(session, NOW)) == 1


def test_section_fidelity_and_stable_references(business):
    sessions, _ = business
    source = "\n\n# Eligibility\nDo NOT refund unpaid invoices. Amount <= $100.\n" + (
        "Policy clause. " * 400
    )
    service = KnowledgeService(sessions)
    result = service.ingest("long", "rules.md", source.encode(), NOW)["document"]
    assert len(result["sections"]) > 1
    assert "line:3;heading:Eligibility" in result["sections"][0]["source"]
    combined = "".join(s["text"] for s in result["sections"])
    assert "Do NOT refund unpaid invoices. Amount <= $100." in combined
    assert combined.endswith("Policy clause.")
    duplicate = service.ingest("long", "rules.md", source.encode(), NOW)
    assert duplicate["document"]["sections"] == result["sections"]
    with sessions() as session:
        assert [s.ordinal for s in retrieval_sections(session, NOW)] == list(
            range(1, len(result["sections"]) + 1)
        )
