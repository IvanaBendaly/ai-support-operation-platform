"""Versioned synthetic fixtures for isolated development and evaluation databases."""

import argparse
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.exc import SQLAlchemyError

from northstar.config import load_settings
from northstar.db import make_engine, session_factory
from northstar.models import (
    Account,
    BillingEvent,
    BusinessFixture,
    Customer,
    Invoice,
    Operation,
    Plan,
    Refund,
    Subscription,
)

FIXTURE_VERSION = "northstar-business-v2"
FIXTURE_ID = "northstar-demo"
BUSINESS_RECORDS = (BillingEvent, Operation, Refund, Invoice, Subscription, Account, Customer, Plan)


def seed(session, as_of: date):
    """Populate within a caller-owned transaction; never commit partial fixtures."""
    if session.get(BusinessFixture, FIXTURE_ID) or any(
        session.scalar(select(model.id).limit(1)) for model in BUSINESS_RECORDS
    ):
        raise ValueError("Seed requires an empty business database; existing data was not changed.")
    _populate(session, as_of)
    session.add(BusinessFixture(id=FIXTURE_ID, version=FIXTURE_VERSION, as_of=as_of))
    session.flush()


def reset_business(sessions, as_of: date, *, environment: str):
    """Atomically restore the baseline. Use a dedicated database per evaluator.

    Only explicitly listed business tables are replaced. Foreign keys from other
    features prevent reset rather than cascading into support-case state.
    """
    if environment not in {"development", "test"}:
        raise ValueError("Business reset is restricted to development and test environments.")
    with sessions.begin() as session:
        fixture = session.scalar(
            select(BusinessFixture).where(BusinessFixture.id == FIXTURE_ID).with_for_update()
        )
        if fixture is None:
            raise ValueError(
                "Reset requires a Northstar fixture marker; seed an empty database first."
            )
        for model in BUSINESS_RECORDS:
            session.execute(delete(model))
        _populate(session, as_of)
        fixture.version, fixture.as_of = FIXTURE_VERSION, as_of
        session.flush()


def _populate(session, as_of: date):
    instant = datetime.combine(as_of, datetime.min.time(), tzinfo=UTC)
    timestamps = {"created_at": instant, "updated_at": instant}
    for customer in ("alice", "bob"):
        session.add(
            Customer(
                id=customer,
                name=f"{customer.title()} Demo",
                email=f"{customer}@example.test",
                **timestamps,
            )
        )
    session.flush()
    for name, customer, status in [
        ("alice-active", "alice", "ACTIVE"),
        ("bob-active", "bob", "ACTIVE"),
        ("alice-canceled", "alice", "ACTIVE"),
        ("alice-suspended", "alice", "SUSPENDED"),
        ("alice-past-due", "alice", "ACTIVE"),
        ("alice-no-subscription", "alice", "ACTIVE"),
        ("alice-growth", "alice", "ACTIVE"),
    ]:
        session.add(Account(id=name, customer_id=customer, name=name, status=status, **timestamps))
    for name, price, enabled in [
        ("starter", 1900, True),
        ("growth", 4900, True),
        ("scale", 9900, True),
        ("retired", 2900, False),
    ]:
        session.add(
            Plan(
                id=name,
                name=name.title(),
                price_minor=price,
                currency="USD",
                enabled=enabled,
                **timestamps,
            )
        )
    session.flush()
    for name, status, plan in [
        ("alice-active", "ACTIVE", "starter"),
        ("bob-active", "ACTIVE", "starter"),
        ("alice-canceled", "CANCELED", "starter"),
        ("alice-suspended", "ACTIVE", "starter"),
        ("alice-past-due", "PAST_DUE", "starter"),
        ("alice-growth", "ACTIVE", "growth"),
    ]:
        session.add(
            Subscription(
                id=f"sub-{name}",
                account_id=name,
                plan_id=plan,
                status=status,
                started_on=as_of - timedelta(days=90),
                version=1,
                ends_on=as_of if status == "CANCELED" else None,
                **timestamps,
            )
        )
    for name, account, amount, status, age, refunded in [
        ("eligible", "alice-active", 4900, "PAID", 5, 0),
        ("unpaid", "alice-active", 4900, "UNPAID", 5, 0),
        ("old", "alice-active", 4900, "PAID", 31, 0),
        ("over-limit", "alice-active", 15000, "PAID", 5, 0),
        ("refunded", "alice-active", 1900, "PAID", 5, 1900),
        ("future", "alice-active", 1900, "PAID", -1, 0),
        ("boundary", "alice-active", 1900, "PAID", 30, 0),
        ("void", "alice-active", 1900, "VOID", 2, 0),
        ("second-eligible", "alice-active", 9900, "PAID", 2, 0),
        ("scheduled", "alice-active", 1900, "UNPAID", -1, 0),
        ("suspended", "alice-suspended", 1900, "PAID", 2, 0),
        ("limit", "alice-growth", 10000, "PAID", 2, 0),
        ("bob", "bob-active", 1900, "PAID", 0, 0),
    ]:
        session.add(
            Invoice(
                id=f"inv-{name}",
                account_id=account,
                amount_minor=amount,
                refunded_minor=refunded,
                currency="USD",
                status=status,
                issued_on=as_of - timedelta(days=age),
                **timestamps,
            )
        )
    session.flush()
    session.add(
        Refund(
            id="refund-existing",
            invoice_id="inv-refunded",
            amount_minor=1900,
            reason="Previously approved demo refund",
            state="COMPLETED",
            **timestamps,
        )
    )
    for invoice in session.scalars(select(Invoice).order_by(Invoice.id)):
        kinds = ["INVOICE_ISSUED"]
        if invoice.status == "PAID":
            kinds.append("PAYMENT_RECEIVED")
        if invoice.status == "VOID":
            kinds.append("INVOICE_VOIDED")
        if invoice.refunded_minor:
            kinds.append("REFUND_ISSUED")
        for index, kind in enumerate(kinds):
            session.add(
                BillingEvent(
                    id=f"{invoice.id}-event-{index}",
                    invoice_id=invoice.id,
                    kind=kind,
                    amount_minor=invoice.amount_minor,
                    currency=invoice.currency,
                    created_at=instant,
                )
            )
    session.flush()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--as-of", type=date.fromisoformat, required=True)
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Replace ALL business records in an already seeded disposable database",
    )
    args = parser.parse_args()
    settings = load_settings()
    if settings.environment == "production":
        parser.error("Demo seed/reset is disabled in production")
    engine = make_engine(settings)
    sessions = session_factory(engine)
    try:
        if args.reset:
            reset_business(sessions, args.as_of, environment=settings.environment)
        else:
            with sessions.begin() as session:
                seed(session, args.as_of)
    except ValueError as error:
        parser.error(str(error))
    except SQLAlchemyError:
        parser.error("Database operation failed; the business transaction was rolled back.")
    finally:
        engine.dispose()
    print(f"Synthetic business baseline ready: {FIXTURE_VERSION}, as_of={args.as_of}.")


if __name__ == "__main__":
    main()
