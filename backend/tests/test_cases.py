from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError
from sqlalchemy import event, select
from sqlalchemy.exc import IntegrityError
from starlette.testclient import TestClient

from northstar.api import create_app
from northstar.cases.credentials import issue
from northstar.cases.models import Attempt, Case, CaseEvent, CustomerCredential, Message, Submission
from northstar.cases.schemas import CreateCase, FollowUp, Outcome
from northstar.cases.service import CaseService
from northstar.config import Settings
from northstar.domain import DomainError

NOW = datetime(2026, 10, 20, tzinfo=UTC)
DATA = CreateCase(
    account_id="alice-active",
    subject="Invoice question",
    message="Please explain this invoice.",
    category="billing",
)


@pytest.fixture
def cases(business):
    sessions, _ = business
    clock = [NOW]
    return sessions, CaseService(sessions, clock=lambda: clock[0]), clock


def create(service, key="create-one"):
    return service.create("alice", key, DATA)["case_id"]


def test_create_history_context_and_idempotency(cases):
    sessions, service, _ = cases
    first = service.create("alice", "request-1", DATA)
    repeated = service.create("alice", "request-1", DATA)
    assert repeated == {**first, "replayed": True}
    case = service.get("alice", first["case_id"])
    assert case["status"] == "open" and case["category"] == "billing"
    assert service.history("alice", case["id"], "messages")[0]["content"] == DATA.message
    with sessions() as session:
        assert len(session.scalars(select(Case)).all()) == 1
        assert len(session.scalars(select(Submission)).all()) == 1
    with pytest.raises(DomainError) as exc:
        service.create(
            "alice", "request-1", DATA.model_copy(update={"message": "Different request"})
        )
    assert exc.value.code == "idempotency_conflict"


@pytest.mark.parametrize(
    "account,customer", [("bob-active", "alice"), ("missing", "alice"), ("alice-active", "missing")]
)
def test_bad_association_has_no_records(cases, account, customer):
    sessions, service, _ = cases
    with pytest.raises(DomainError):
        service.create(customer, "key", DATA.model_copy(update={"account_id": account}))
    with sessions() as session:
        for model in [Case, Message, CaseEvent, Submission]:
            assert session.scalar(select(model)) is None


def test_invalid_invoice_context(cases):
    _, service, _ = cases
    with pytest.raises(DomainError):
        service.create(
            "alice",
            "key",
            CreateCase(**{**DATA.model_dump(), "context": {"invoice_id": "inv-bob"}}),
        )


def test_followup_version_fencing_and_terminal_case(cases):
    _, service, _ = cases
    case_id = create(service)
    data = FollowUp(message="More detail", expected_version=1)
    first = service.follow_up("alice", case_id, "follow-1", data)
    assert service.follow_up("alice", case_id, "follow-1", data)["replayed"]
    with pytest.raises(DomainError) as exc:
        service.follow_up("alice", case_id, "follow-2", data)
    assert exc.value.code == "version_conflict"
    attempt = service.start_processing(case_id)
    with pytest.raises(DomainError):
        service.follow_up(
            "alice", case_id, "follow-3", FollowUp(message="During processing", expected_version=3)
        )
    result = Outcome(
        disposition="answered",
        reply="Here is the invoice explanation.",
        decision_id="decision-example",
    )
    service.complete(case_id, attempt["attempt_id"], result)
    assert service.complete(case_id, attempt["attempt_id"], result)["replayed"]
    closed = service.get("alice", case_id)
    assert closed["status"] == "resolved" and closed["resolved_at"] is not None
    with pytest.raises(DomainError):
        service.follow_up(
            "alice",
            case_id,
            "closed-message",
            FollowUp(message="New question", expected_version=closed["version"]),
        )
    assert len(service.history("alice", case_id, "messages")) == 3
    assert first["message_id"] in [m["id"] for m in service.history("alice", case_id, "messages")]
    assert (
        service.history("alice", case_id, "events")[-1]["details"]["decision_id"]
        == "decision-example"
    )


def test_clarification_and_human_review(cases):
    _, service, _ = cases
    case_id = create(service)
    attempt = service.start_processing(case_id)
    service.complete(
        case_id,
        attempt["attempt_id"],
        Outcome(disposition="clarification_requested", reply="Which invoice?"),
    )
    awaiting = service.get("alice", case_id)
    assert awaiting["status"] == "awaiting_customer"
    service.follow_up(
        "alice",
        case_id,
        "clarification",
        FollowUp(message="The latest invoice.", expected_version=awaiting["version"]),
    )
    assert service.get("alice", case_id)["status"] == "open"
    second = service.start_processing(case_id)
    service.complete(
        case_id,
        second["attempt_id"],
        Outcome(
            disposition="escalated", reply="A specialist will review.", escalation_id="review-123"
        ),
    )
    escalated = service.get("alice", case_id)
    service.follow_up(
        "alice",
        case_id,
        "review-info",
        FollowUp(message="Additional detail for review.", expected_version=escalated["version"]),
    )
    latest = service.get("alice", case_id)
    assert latest["status"] == "escalated"
    human = service.human_review(
        case_id,
        latest["version"],
        Outcome(disposition="clarification_requested", reply="Please confirm the date."),
    )
    assert human["status"] == "awaiting_customer"
    with pytest.raises(DomainError):
        service.human_review(
            case_id, human["version"], Outcome(disposition="answered", reply="Done")
        )
    assert [m["role"] for m in service.history("alice", case_id, "messages")][-1] == "human"


def test_timeout_restart_recovery_and_stale_worker(cases):
    sessions, service, clock = cases
    case_id = create(service)
    first = service.start_processing(case_id, lease_seconds=30)
    with pytest.raises(DomainError):
        service.start_processing(case_id)
    clock[0] += timedelta(seconds=30)
    restarted = CaseService(sessions, clock=lambda: clock[0])
    failed = restarted.get("alice", case_id)
    assert failed["status"] == "failed" and failed["last_error"] == "processing_interrupted"
    assert restarted.recover_expired() == 0
    reopened = restarted.retry("alice", case_id, failed["version"])
    assert reopened["status"] == "open"
    second = restarted.start_processing(case_id)
    with pytest.raises(DomainError) as exc:
        restarted.complete(
            case_id, first["attempt_id"], Outcome(disposition="answered", reply="Old worker reply")
        )
    assert exc.value.code == "stale_attempt"
    restarted.complete(
        case_id,
        second["attempt_id"],
        Outcome(disposition="refused", reply="This request is not supported."),
    )
    history = restarted.history("alice", case_id, "attempts")
    assert [h["status"] for h in history] == ["timed_out", "succeeded"]
    assert history[0]["finished_at"] is not None


def test_visible_processing_failure_and_recovery_sweep(cases):
    _, service, clock = cases
    case_id = create(service)
    attempt = service.start_processing(case_id)
    service.fail(case_id, attempt["attempt_id"], "provider_unavailable")
    failed = service.get("alice", case_id)
    assert failed["last_error"] == "provider_unavailable"
    service.retry("alice", case_id, failed["version"])
    service.start_processing(case_id, lease_seconds=1)
    clock[0] += timedelta(seconds=2)
    assert service.recover_expired() == 1
    assert service.get("alice", case_id)["status"] == "failed"


def test_outcome_and_message_roll_back_together(cases):
    sessions, service, _ = cases
    case_id = create(service)
    attempt = service.start_processing(case_id)

    def fail(*args):
        raise RuntimeError("injected audit persistence failure")

    event.listen(CaseEvent, "before_insert", fail)
    try:
        with pytest.raises(RuntimeError):
            service.complete(
                case_id,
                attempt["attempt_id"],
                Outcome(disposition="answered", reply="Should roll back"),
            )
    finally:
        event.remove(CaseEvent, "before_insert", fail)
    with sessions() as session:
        assert session.get(Case, case_id).status == "processing"
        assert session.get(Attempt, attempt["attempt_id"]).status == "processing"
        assert len(session.scalars(select(Message).where(Message.case_id == case_id)).all()) == 1


def test_database_prevents_cross_customer_case(cases):
    sessions, service, _ = cases
    case_id = create(service)
    with pytest.raises(IntegrityError), sessions.begin() as session:
        session.get(Case, case_id).customer_id = "bob"


def test_outcome_requires_action_reference():
    with pytest.raises(ValidationError):
        Outcome(disposition="action_completed", reply="Done")


def test_customer_api_end_to_end_and_authorization(business):
    sessions, _ = business
    alice = issue(sessions, "alice")
    bob = issue(sessions, "bob")
    settings = Settings(
        _env_file=None,
        environment="test",
        database_url="sqlite+pysqlite:///:memory:",
        admin_token="private-test-administrator-token-123",
    )
    with TestClient(create_app(settings, sessions.kw["bind"])) as client:
        assert client.get("/api/cases").status_code == 401
        client.headers["Authorization"] = "Bearer " + alice["token"]
        client.headers["Idempotency-Key"] = "api-create"
        response = client.post("/api/cases", json=DATA.model_dump())
        assert response.status_code == 201, response.text
        case_id = response.json()["case_id"]
        assert client.post("/api/cases", json=DATA.model_dump()).json()["replayed"]
        case = client.get("/api/cases/" + case_id).json()
        assert case["status"] == "open"
        assert len(client.get("/api/cases?category=billing&status=open").json()) == 1
        client.headers["Idempotency-Key"] = "api-follow"
        response = client.post(
            f"/api/cases/{case_id}/messages",
            json={"message": "More information", "expected_version": case["version"]},
        )
        assert response.status_code == 201
        assert len(client.get(f"/api/cases/{case_id}/messages").json()) == 2
        assert client.get(f"/api/cases/{case_id}/events").status_code == 200
        assert client.get("/api/cases?limit=0").status_code == 422
        client.headers["Authorization"] = "Bearer " + bob["token"]
        for path in ["", "/messages", "/events", "/attempts"]:
            assert client.get(f"/api/cases/{case_id}" + path).status_code == 404
        assert (
            client.post(f"/api/cases/{case_id}/retry", json={"expected_version": 2}).status_code
            == 404
        )
        assert (
            client.post(
                f"/api/cases/{case_id}/messages",
                json={"message": "No access", "expected_version": 2},
            ).status_code
            == 404
        )
        assert client.get("/api/cases").json() == []
        assert client.post("/api/cases", json=DATA.model_dump()).status_code == 404
        assert client.post(f"/api/admin/cases/{case_id}/review", json={}).status_code == 401
        with sessions.begin() as session:
            session.get(CustomerCredential, bob["credential_id"]).revoked = True
        assert client.get("/api/cases").status_code == 401
        with sessions() as session:
            stored = session.get(CustomerCredential, alice["credential_id"])
            assert stored.token_hash != alice["token"] and len(stored.token_hash) == 64


def test_api_validation_no_partial_cases_and_expired_token(business):
    sessions, _ = business
    credential = issue(sessions, "alice")
    settings = Settings(
        _env_file=None, environment="test", database_url="sqlite+pysqlite:///:memory:"
    )
    with TestClient(
        create_app(settings, sessions.kw["bind"]),
        headers={"Authorization": "Bearer " + credential["token"], "Idempotency-Key": "test"},
    ) as client:
        for body in [
            {},
            {**DATA.model_dump(), "message": " "},
            {**DATA.model_dump(), "message": "x" * 8001},
            {**DATA.model_dump(), "customer_id": "bob"},
        ]:
            assert client.post("/api/cases", json=body).status_code == 422
        assert client.post("/api/cases", content=b"x" * 65537).status_code == 413
        with sessions.begin() as session:
            assert session.scalar(select(Case)) is None
            session.get(CustomerCredential, credential["credential_id"]).expires_at = datetime.now(
                UTC
            ) - timedelta(seconds=1)
        assert client.get("/api/cases").status_code == 401


@pytest.mark.postgres
def test_postgres_duplicate_creation_and_claim(postgres_business):
    from concurrent.futures import ThreadPoolExecutor

    sessions, _ = postgres_business
    service = CaseService(sessions)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: service.create("alice", "same-key", DATA), range(2)))
    assert results[0]["case_id"] == results[1]["case_id"]
    case_id = results[0]["case_id"]

    def claim(_):
        try:
            return service.start_processing(case_id)
        except DomainError as exc:
            assert exc.code == "invalid_case_state"
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        attempts = list(pool.map(claim, range(2)))
    assert sum(a is not None for a in attempts) == 1


def test_history_and_filter_recover_expired_attempts(cases):
    _, service, clock = cases
    first = create(service)
    second = create(service, "second")
    service.start_processing(first, lease_seconds=1)
    service.start_processing(second, lease_seconds=1)
    clock[0] += timedelta(seconds=1)
    rows = service.list_cases("alice", status="failed", category="billing", limit=1)
    assert len(rows) == 1 and rows[0]["status"] == "failed"
    assert service.list_cases("alice", status="processing") == []
    assert service.history("alice", second, "attempts")[0]["status"] == "timed_out"


def test_api_human_review_and_processing_failure_retry(business):
    sessions, _ = business
    credential = issue(sessions, "alice")
    admin_token = "test-admin-human-review-token-123456"
    settings = Settings(
        _env_file=None,
        environment="test",
        database_url="sqlite+pysqlite:///:memory:",
        admin_token=admin_token,
    )
    service = CaseService(sessions)
    case_id = create(service)
    attempt = service.start_processing(case_id)
    service.fail(case_id, attempt["attempt_id"], "retrieval_failed")
    with TestClient(
        create_app(settings, sessions.kw["bind"]),
        headers={"Authorization": "Bearer " + credential["token"]},
    ) as client:
        state = client.get("/api/cases/" + case_id).json()
        assert state["status"] == "failed"
        assert (
            client.post(
                f"/api/cases/{case_id}/retry", json={"expected_version": state["version"]}
            ).status_code
            == 200
        )
        second = service.start_processing(case_id)
        service.complete(
            case_id,
            second["attempt_id"],
            Outcome(disposition="escalated", reply="Human review required."),
        )
        version = client.get("/api/cases/" + case_id).json()["version"]
        assert client.get(f"/api/admin/cases/{case_id}").status_code == 401
        client.headers["Authorization"] = "Bearer " + admin_token
        assert client.get(f"/api/admin/cases/{case_id}").json()["version"] == version
        assert client.get(f"/api/admin/cases/{case_id}/messages").status_code == 200
        response = client.post(
            f"/api/admin/cases/{case_id}/review",
            json={
                "expected_version": version,
                "disposition": "answered",
                "reply": "Reviewed and explained.",
            },
        )
        assert response.status_code == 200 and response.json()["status"] == "resolved"
        assert client.post("/api/admin/cases/recover").json() == {"recovered": 0}


def test_failed_creation_rolls_back_message_and_idempotency(cases):
    sessions, service, _ = cases

    def fail(*args):
        raise RuntimeError("receipt unavailable")

    event.listen(Submission, "before_insert", fail)
    try:
        with pytest.raises(RuntimeError):
            create(service)
    finally:
        event.remove(Submission, "before_insert", fail)
    with sessions() as session:
        for model in [Case, Message, CaseEvent, Submission]:
            assert session.scalar(select(model)) is None
    assert create(service)


def test_case_history_prevents_business_reset(cases):
    from datetime import date

    from northstar.seed import reset_business

    _, service, _ = cases
    sessions = service.sessions
    case_id = create(service)
    with pytest.raises(IntegrityError):
        reset_business(sessions, as_of=date(2026, 10, 20), environment="test")
    assert service.get("alice", case_id)["status"] == "open"


@pytest.mark.postgres
def test_postgres_concurrent_followups(postgres_business):
    from concurrent.futures import ThreadPoolExecutor

    sessions, _ = postgres_business
    service = CaseService(sessions)
    case_id = create(service)

    def follow(index):
        try:
            return service.follow_up(
                "alice",
                case_id,
                f"follow-{index}",
                FollowUp(message=f"Message {index}", expected_version=1),
            )
        except DomainError as exc:
            assert exc.code == "version_conflict"
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        replies = list(pool.map(follow, range(2)))
    assert sum(r is not None for r in replies) == 1
    assert len(service.history("alice", case_id, "messages")) == 2
