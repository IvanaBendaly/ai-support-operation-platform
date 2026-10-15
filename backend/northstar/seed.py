"""Deterministic business fixtures. CLI never deletes existing business data."""

import argparse
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select

from northstar.config import Settings
from northstar.db import make_engine, session_factory
from northstar.models import Account, Customer, Invoice, Plan, Refund, Subscription


def seed(session, as_of: date):
    if session.scalar(select(Customer.id).limit(1)):
        raise ValueError("Seed requires an empty business database; existing data was not changed.")
    for customer in ("alice", "bob"):
        session.add(
            Customer(id=customer, name=f"{customer.title()} Demo", email=f"{customer}@example.test")
        )
    session.flush()
    for name, customer, status in [
        ("alice-active", "alice", "ACTIVE"),
        ("bob-active", "bob", "ACTIVE"),
        ("alice-canceled", "alice", "ACTIVE"),
        ("alice-suspended", "alice", "SUSPENDED"),
        ("alice-past-due", "alice", "ACTIVE"),
        ("alice-no-subscription", "alice", "ACTIVE"),
    ]:
        session.add(Account(id=name, customer_id=customer, name=name, status=status))
    for name, price in [("starter", 1900), ("growth", 4900), ("scale", 9900)]:
        session.add(
            Plan(id=name, name=name.title(), price_minor=price, currency="USD", enabled=True)
        )
    session.flush()
    for name, status in [
        ("alice-active", "ACTIVE"),
        ("bob-active", "ACTIVE"),
        ("alice-canceled", "CANCELED"),
        ("alice-suspended", "ACTIVE"),
        ("alice-past-due", "PAST_DUE"),
    ]:
        session.add(
            Subscription(
                id=f"sub-{name}",
                account_id=name,
                plan_id="starter",
                status=status,
                started_on=as_of - timedelta(days=90),
                version=1,
                ends_on=as_of if status == "CANCELED" else None,
            )
        )
    for name, amount, status, age, refunded in [
        ("eligible", 4900, "PAID", 5, 0),
        ("unpaid", 4900, "UNPAID", 5, 0),
        ("old", 4900, "PAID", 31, 0),
        ("over-limit", 15000, "PAID", 5, 0),
        ("refunded", 1900, "PAID", 5, 1900),
        ("future", 1900, "PAID", -1, 0),
        ("boundary", 1900, "PAID", 30, 0),
        ("void", 1900, "VOID", 2, 0),
    ]:
        session.add(
            Invoice(
                id=f"inv-{name}",
                account_id="alice-active",
                amount_minor=amount,
                refunded_minor=refunded,
                currency="USD",
                status=status,
                issued_on=as_of - timedelta(days=age),
            )
        )
    session.add(
        Invoice(
            id="inv-bob",
            account_id="bob-active",
            amount_minor=1900,
            refunded_minor=0,
            currency="USD",
            status="PAID",
            issued_on=as_of,
        )
    )
    session.flush()
    session.add(
        Refund(
            id="refund-existing",
            invoice_id="inv-refunded",
            amount_minor=1900,
            created_at=datetime.combine(as_of, datetime.min.time(), tzinfo=UTC),
        )
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--as-of",
        type=date.fromisoformat,
        required=True,
        help="Explicit YYYY-MM-DD fixture date; use today's date for an interactive demo",
    )
    args = parser.parse_args()
    settings = Settings()
    if settings.environment == "production":
        parser.error("Demo seeding is disabled in production")
    engine = make_engine(settings)
    try:
        with session_factory(engine).begin() as session:
            seed(session, args.as_of)
    finally:
        engine.dispose()
    print("Synthetic Northstar business fixtures inserted.")


if __name__ == "__main__":
    main()
