from datetime import date

import pytest
from sqlalchemy import event, func, select
from sqlalchemy.exc import IntegrityError

from northstar.domain import DomainError, get_account, get_invoices, get_subscription
from northstar.models import Account, Customer, Invoice, Operation, Refund, Subscription
from northstar.seed import seed


def test_persisted_reads_and_ownership(business):
    sessions, _ = business
    with sessions() as session:
        assert get_account(session, "alice", "alice-active")["status"] == "ACTIVE"
        assert get_subscription(session, "alice", "alice-active")["plan_id"] == "starter"
        assert len(get_invoices(session, "alice", "alice-active", limit=2)) == 2
        for read in [get_account, get_subscription, get_invoices]:
            with pytest.raises(DomainError, match="Account not found"):
                read(session, "alice", "bob-active")
        with pytest.raises(DomainError, match="Subscription not found"):
            get_subscription(session, "alice", "alice-no-subscription")


def test_change_plan_commits_with_audit_and_replays(business):
    sessions, service = business
    result = service.change_plan("alice", "alice-active", "growth", "plan-1")
    assert service.change_plan("alice", "alice-active", "growth", "plan-1") == result
    with sessions() as session:
        subscription = session.get(Subscription, "sub-alice-active")
        assert (subscription.plan_id, subscription.version) == ("growth", 2)
        operation = session.get(Operation, result["operation_id"])
        assert operation.before == {"plan_id": "starter", "version": 1}
        assert operation.result == result
        assert session.scalar(select(func.count()).select_from(Operation)) == 1
    with pytest.raises(DomainError) as error:
        service.change_plan("alice", "alice-active", "scale", "plan-1")
    assert error.value.code == "idempotency_conflict"


@pytest.mark.parametrize(
    "account,plan,code",
    [
        ("bob-active", "growth", "account_not_found"),
        ("alice-canceled", "growth", "subscription_ineligible"),
        ("alice-past-due", "growth", "subscription_ineligible"),
        ("alice-suspended", "growth", "account_ineligible"),
        ("alice-active", "nonexistent", "invalid_plan"),
        ("alice-active", "starter", "unchanged_plan"),
        ("alice-no-subscription", "growth", "subscription_ineligible"),
    ],
)
def test_plan_rejections_never_mutate(business, account, plan, code):
    sessions, service = business
    with pytest.raises(DomainError) as error:
        service.change_plan("alice", account, plan, "reject")
    assert error.value.code == code
    with sessions() as session:
        assert session.scalar(select(func.count()).select_from(Operation)) == 0
        assert all(s.plan_id == "starter" for s in session.scalars(select(Subscription)))


def test_refund_commits_once_and_duplicate_is_rejected(business):
    sessions, service = business
    result = service.refund("alice", "alice-active", "inv-eligible", "refund-1")
    assert result["amount_minor"] == 4900
    assert service.refund("alice", "alice-active", "inv-eligible", "refund-1") == result
    with pytest.raises(DomainError) as error:
        service.refund("alice", "alice-active", "inv-eligible", "another-key")
    assert error.value.code == "already_refunded"
    with sessions() as session:
        assert session.get(Invoice, "inv-eligible").refunded_minor == 4900
        refunds = session.scalars(select(Refund).where(Refund.invoice_id == "inv-eligible")).all()
        assert len(refunds) == 1
        assert refunds[0].amount_minor == 4900
        assert session.scalar(select(func.count()).select_from(Operation)) == 1


@pytest.mark.parametrize(
    "invoice,code",
    [
        ("inv-unpaid", "refund_ineligible"),
        ("inv-old", "refund_ineligible"),
        ("inv-over-limit", "refund_ineligible"),
        ("inv-future", "refund_ineligible"),
        ("inv-void", "refund_ineligible"),
        ("inv-refunded", "already_refunded"),
        ("inv-bob", "invoice_not_found"),
        ("missing", "invoice_not_found"),
    ],
)
def test_refund_ineligibility(business, invoice, code):
    sessions, service = business
    with pytest.raises(DomainError) as error:
        service.refund("alice", "alice-active", invoice, "reject")
    assert error.value.code == code
    with sessions() as session:
        assert session.scalar(select(func.count()).select_from(Refund)) == 1
        assert session.scalar(select(func.count()).select_from(Operation)) == 0


def test_refund_window_includes_day_30(business):
    _, service = business
    assert (
        service.refund("alice", "alice-active", "inv-boundary", "boundary")["amount_minor"] == 1900
    )


def test_audit_failure_rolls_back_mutation_and_refund(business):
    sessions, service = business

    def break_audit(mapper, connection, target):
        raise RuntimeError("injected audit failure")

    event.listen(Operation, "before_insert", break_audit)
    try:
        with pytest.raises(RuntimeError, match="injected"):
            service.refund("alice", "alice-active", "inv-eligible", "rollback")
    finally:
        event.remove(Operation, "before_insert", break_audit)
    with sessions() as session:
        assert session.get(Invoice, "inv-eligible").refunded_minor == 0
        assert session.scalar(select(func.count()).select_from(Refund)) == 1
        assert session.scalar(select(func.count()).select_from(Operation)) == 0


def test_database_constraints_and_seed_guard(business):
    sessions, _ = business
    with pytest.raises(IntegrityError), sessions.begin() as session:
        session.add(Account(id="orphan", customer_id="absent", name="Orphan", status="ACTIVE"))
    with pytest.raises(IntegrityError), sessions.begin() as session:
        session.get(Invoice, "inv-eligible").refunded_minor = 999999
    with pytest.raises(IntegrityError), sessions.begin() as session:
        session.get(Subscription, "sub-alice-active").status = "INVALID"
    with pytest.raises(ValueError, match="empty business database"), sessions.begin() as session:
        seed(session, date(2026, 10, 12))
    with sessions() as session:
        assert session.scalar(select(func.count()).select_from(Customer)) == 2
        assert session.get(Invoice, "inv-eligible").issued_on == date(2026, 10, 7)


def test_subscription_state_machine(business):
    sessions, service = business
    service.transition_subscription("alice", "alice-active", "PAST_DUE", "past-due")
    with pytest.raises(DomainError, match="active subscription"):
        service.change_plan("alice", "alice-active", "growth", "ineligible")
    service.transition_subscription("alice", "alice-active", "ACTIVE", "restored")
    service.transition_subscription("alice", "alice-active", "CANCELED", "canceled")
    with pytest.raises(DomainError, match="transition is not permitted"):
        service.transition_subscription("alice", "alice-active", "ACTIVE", "invalid")
    with sessions() as session:
        subscription = session.get(Subscription, "sub-alice-active")
        assert subscription.status == "CANCELED"
        assert subscription.ends_on == date(2026, 10, 12)
        assert subscription.version == 4
