from concurrent.futures import ThreadPoolExecutor
from datetime import date
from threading import Barrier

import pytest
from sqlalchemy import func, select

from northstar.domain import DomainError
from northstar.models import Invoice, Operation, Refund, Subscription
from northstar.seed import BUSINESS_RECORDS, reset_business

pytestmark = pytest.mark.postgres


def test_concurrent_refunds_commit_only_one(postgres_business):
    sessions, service = postgres_business
    barrier = Barrier(2)

    def refund(key):
        barrier.wait(timeout=5)
        try:
            return service.refund("alice", "alice-active", "inv-eligible", key)
        except DomainError as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(refund, ["one", "two"]))
    assert sum(isinstance(result, dict) for result in results) == 1
    assert "already_refunded" in results
    with sessions() as session:
        assert session.get(Invoice, "inv-eligible").refunded_minor == 4900
        assert (
            session.scalar(
                select(func.count()).select_from(Refund).where(Refund.invoice_id == "inv-eligible")
            )
            == 1
        )
        assert session.scalar(select(func.count()).select_from(Operation)) == 1


def test_concurrent_same_key_returns_same_result(postgres_business):
    sessions, service = postgres_business
    barrier = Barrier(2)

    def change(_):
        barrier.wait(timeout=5)
        return service.change_plan("alice", "alice-active", "growth", "shared-key")

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(change, range(2)))
    assert results[0] == results[1]
    with sessions() as session:
        assert session.get(Subscription, "sub-alice-active").version == 2
        assert session.scalar(select(func.count()).select_from(Operation)) == 1


def test_postgres_reset_restores_baseline(postgres_business):
    sessions, service = postgres_business

    def snapshot():
        with sessions() as session:
            return {
                model.__tablename__: session.execute(select(model.__table__).order_by(model.id))
                .mappings()
                .all()
                for model in BUSINESS_RECORDS
            }

    before = snapshot()
    service.record_payment("alice", "alice-active", "inv-unpaid", "pay")
    service.refund("alice", "alice-active", "inv-eligible", "refund")
    reset_business(sessions, date(2026, 10, 12), environment="test")
    assert snapshot() == before
