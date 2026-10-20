from datetime import date
from unittest.mock import patch

import pytest
from sqlalchemy import event, select, text
from sqlalchemy.exc import IntegrityError

from northstar.domain import (
    DomainError,
    get_account_history,
    get_billing_history,
    get_refunds,
)
from northstar.models import Account, BillingEvent, BusinessFixture, Invoice, Refund
from northstar.seed import BUSINESS_RECORDS, reset_business

AS_OF = date(2026, 10, 12)


def snapshot(sessions):
    with sessions() as session:
        return {
            model.__tablename__: [
                dict(row)
                for row in session.execute(select(model.__table__).order_by(model.id)).mappings()
            ]
            for model in (*BUSINESS_RECORDS, BusinessFixture)
        }


def test_reset_restores_every_record_and_metadata_repeatedly(business):
    sessions, service = business
    baseline = snapshot(sessions)
    service.refund("alice", "alice-active", "inv-eligible", "refund", reason="Duplicate purchase")
    service.record_payment("alice", "alice-active", "inv-unpaid", "paid")
    service.transition_account("alice", "alice-growth", "SUSPENDED", "suspend", "Review requested")
    assert snapshot(sessions) != baseline
    for _ in range(2):
        reset_business(sessions, AS_OF, environment="test")
        assert snapshot(sessions) == baseline
    # Idempotency records must reset along with business rows, never contaminate another scenario.
    result = service.refund(
        "alice", "alice-active", "inv-eligible", "refund", reason="Duplicate purchase"
    )
    assert result["amount_minor"] == 4900


def test_reset_is_atomic_and_preserves_unrelated_state(business):
    sessions, service = business
    service.change_plan("alice", "alice-active", "growth", "plan")
    baseline = snapshot(sessions)
    with sessions.begin() as session:
        session.execute(text("CREATE TABLE unrelated_state (value TEXT)"))
        session.execute(text("INSERT INTO unrelated_state VALUES ('keep me')"))
    with patch("northstar.seed._populate", side_effect=RuntimeError("injected seed failure")):
        with pytest.raises(RuntimeError, match="injected"):
            reset_business(sessions, AS_OF, environment="test")
    assert snapshot(sessions) == baseline
    reset_business(sessions, AS_OF, environment="development")
    with sessions() as session:
        assert session.execute(text("SELECT value FROM unrelated_state")).scalar() == "keep me"


def test_reset_rejects_production_and_unmarked_database(business):
    sessions, _ = business
    before = snapshot(sessions)
    with pytest.raises(ValueError, match="restricted"):
        reset_business(sessions, AS_OF, environment="production")
    assert snapshot(sessions) == before
    with sessions.begin() as session:
        session.delete(session.get(BusinessFixture, "northstar-demo"))
    before = snapshot(sessions)
    with pytest.raises(ValueError, match="marker"):
        reset_business(sessions, AS_OF, environment="test")
    assert snapshot(sessions) == before


def test_fresh_initializations_are_equivalent(business):
    from northstar.config import Settings
    from northstar.db import Base, make_engine, session_factory
    from northstar.seed import seed

    sessions, _ = business
    engine = make_engine(
        Settings(_env_file=None, environment="test", database_url="sqlite+pysqlite:///:memory:")
    )
    Base.metadata.create_all(engine)
    other = session_factory(engine)
    try:
        with other.begin() as session:
            seed(session, AS_OF)
        assert snapshot(other) == snapshot(sessions)
    finally:
        engine.dispose()


def test_reset_cannot_cascade_into_support_references(business):
    sessions, _ = business
    before = snapshot(sessions)
    with sessions.begin() as session:
        session.execute(
            text("CREATE TABLE support_reference (customer_id TEXT REFERENCES customers(id))")
        )
        session.execute(text("INSERT INTO support_reference VALUES ('alice')"))
    with pytest.raises(IntegrityError):
        reset_business(sessions, AS_OF, environment="test")
    assert snapshot(sessions) == before
    with sessions() as session:
        assert (
            session.execute(text("SELECT customer_id FROM support_reference")).scalar() == "alice"
        )


def test_billing_events_payment_refund_and_idempotency(business):
    sessions, service = business
    result = service.record_payment("alice", "alice-active", "inv-unpaid", "pay")
    assert service.record_payment("alice", "alice-active", "inv-unpaid", "pay") == result
    refunded = service.refund("alice", "alice-active", "inv-unpaid", "refund", "Plan unsuitable")
    with sessions() as session:
        events = session.scalars(
            select(BillingEvent).where(BillingEvent.operation_id.is_not(None))
        ).all()
        assert {row.kind for row in events} == {"PAYMENT_RECEIVED", "REFUND_ISSUED"}
        assert len(events) == 2
        assert all(row.amount_minor == 4900 for row in events)
        refund = session.get(Refund, refunded["refund_id"])
        assert (refund.reason, refund.state) == ("Plan unsuitable", "COMPLETED")
        assert refund.updated_at >= refund.created_at
        assert session.get(Invoice, "inv-unpaid").refunded_minor == 4900
        assert (
            session.get(Invoice, "inv-unpaid").updated_at
            > session.get(Invoice, "inv-unpaid").created_at
        )
        assert any(
            row["reason"] == "Plan unsuitable"
            for row in get_refunds(session, "alice", "alice-active")
        )
    with pytest.raises(DomainError, match="another request"):
        service.refund("alice", "alice-active", "inv-unpaid", "refund", "Changed reason")


def test_void_and_rejected_payment_transitions(business):
    sessions, service = business
    result = service.void_invoice("alice", "alice-active", "inv-unpaid", "void")
    assert result["status"] == "VOID"
    with pytest.raises(DomainError, match="unpaid invoice"):
        service.record_payment("alice", "alice-active", "inv-unpaid", "pay")
    for invoice, code in [
        ("inv-bob", "invoice_not_found"),
        ("missing", "invoice_not_found"),
        ("inv-scheduled", "invoice_ineligible"),
        ("inv-eligible", "invalid_transition"),
    ]:
        with pytest.raises(DomainError) as error:
            service.record_payment("alice", "alice-active", invoice, invoice)
        assert error.value.code == code


def test_account_lifecycle_history_and_ownership(business):
    sessions, service = business
    service.transition_account(
        "alice", "alice-active", "SUSPENDED", "suspend", "Verification required"
    )
    with pytest.raises(DomainError, match="not active"):
        service.refund("alice", "alice-active", "inv-eligible", "denied")
    with pytest.raises(DomainError, match="Account not found"):
        service.transition_account("bob", "alice-active", "ACTIVE", "wrong-owner", "Override")
    service.transition_account("alice", "alice-active", "ACTIVE", "resume", "Verification complete")
    with pytest.raises(DomainError, match="not permitted"):
        service.transition_account("alice", "alice-active", "DELETED", "invalid", "Invalid")
    with sessions() as session:
        history = get_account_history(session, "alice", "alice-active")
        assert len(history) == 2
        assert history[0]["before"]["status"] == "ACTIVE"
        assert history[1]["result"]["status"] == "ACTIVE"
        assert session.get(Account, "alice-active").status == "ACTIVE"
        for reader in (get_account_history, get_billing_history, get_refunds):
            with pytest.raises(DomainError, match="Account not found"):
                reader(session, "bob", "alice-active")
            with pytest.raises(DomainError, match="pagination"):
                reader(session, "alice", "alice-active", limit=101)


def test_billing_event_failure_rolls_back_invoice_and_audit(business):
    sessions, service = business
    before = snapshot(sessions)

    def fail(mapper, connection, target):
        raise RuntimeError("event storage failed")

    event.listen(BillingEvent, "before_insert", fail)
    try:
        with pytest.raises(RuntimeError, match="event storage"):
            service.record_payment("alice", "alice-active", "inv-unpaid", "fail")
    finally:
        event.remove(BillingEvent, "before_insert", fail)
    assert snapshot(sessions) == before


@pytest.mark.parametrize("reason", ["", "  ", "x" * 501, None])
def test_invalid_refund_reasons_preserve_state(business, reason):
    sessions, service = business
    before = snapshot(sessions)
    with pytest.raises(DomainError, match="reason"):
        service.refund("alice", "alice-active", "inv-eligible", "reason", reason)
    assert snapshot(sessions) == before


def test_database_rejects_missing_invoice_duplicate_refund_and_invalid_metadata(business):
    sessions, _ = business
    for invoice_id in ["absent", "inv-refunded"]:
        with pytest.raises(IntegrityError), sessions.begin() as session:
            session.add(Refund(id="bad", invoice_id=invoice_id, amount_minor=1900, reason="test"))
    for attribute, value in [("state", "PENDING"), ("reason", " ")]:
        with pytest.raises(IntegrityError), sessions.begin() as session:
            setattr(session.get(Refund, "refund-existing"), attribute, value)


def test_additional_evaluation_scenarios(business):
    sessions, service = business
    assert service.refund("alice", "alice-growth", "inv-limit", "limit")["amount_minor"] == 10000
    with pytest.raises(DomainError, match="enabled plan"):
        service.change_plan("alice", "alice-active", "retired", "retired")
    with pytest.raises(DomainError, match="not active"):
        service.refund("alice", "alice-suspended", "inv-suspended", "suspended")
    with sessions() as session:
        eligible = session.scalars(
            select(Invoice).where(
                Invoice.account_id == "alice-active",
                Invoice.status == "PAID",
                Invoice.refunded_minor == 0,
                Invoice.issued_on >= date(2026, 9, 12),
                Invoice.issued_on <= AS_OF,
                Invoice.amount_minor <= 10000,
            )
        ).all()
        assert len(eligible) > 1  # A request without an invoice identifier is genuinely ambiguous.
        assert not get_billing_history(session, "alice", "alice-no-subscription")
