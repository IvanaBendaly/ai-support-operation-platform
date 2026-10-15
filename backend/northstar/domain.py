from datetime import UTC, date, datetime
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from northstar.models import Account, Invoice, Operation, Plan, Refund, Subscription


class DomainError(Exception):
    def __init__(self, code: str, message: str, status: int = 409):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


def owned_account(session, customer_id: str, account_id: str, lock=False):
    query = select(Account).where(Account.id == account_id, Account.customer_id == customer_id)
    if lock:
        query = query.with_for_update()
    account = session.scalar(query)
    if account is None:
        raise DomainError("account_not_found", "Account not found.", 404)
    return account


def get_account(session, customer_id: str, account_id: str):
    account = owned_account(session, customer_id, account_id)
    return {"id": account.id, "name": account.name, "status": account.status}


def get_subscription(session, customer_id: str, account_id: str):
    owned_account(session, customer_id, account_id)
    subscription = session.scalar(select(Subscription).where(Subscription.account_id == account_id))
    if subscription is None:
        raise DomainError("subscription_not_found", "Subscription not found.", 404)
    return {
        "id": subscription.id,
        "plan_id": subscription.plan_id,
        "status": subscription.status,
        "version": subscription.version,
        "started_on": subscription.started_on.isoformat(),
    }


def get_invoices(session, customer_id: str, account_id: str, limit=25, offset=0):
    owned_account(session, customer_id, account_id)
    if not 1 <= limit <= 100 or offset < 0:
        raise DomainError("invalid_pagination", "Invalid pagination.", 422)
    invoices = session.scalars(
        select(Invoice)
        .where(Invoice.account_id == account_id)
        .order_by(Invoice.issued_on.desc(), Invoice.id)
        .limit(limit)
        .offset(offset)
    )
    return [
        {
            "id": i.id,
            "amount_minor": i.amount_minor,
            "currency": i.currency,
            "refunded_minor": i.refunded_minor,
            "status": i.status,
            "issued_on": i.issued_on.isoformat(),
        }
        for i in invoices
    ]


class BusinessService:
    """Each public mutation owns exactly one transaction, including its audit record."""

    def __init__(self, sessions, today=date.today):
        self.sessions, self.today = sessions, today

    def _execute(self, customer_id, account_id, key, kind, arguments, mutate):
        if not isinstance(key, str) or not 1 <= len(key) <= 128 or not key.strip():
            raise DomainError("invalid_idempotency_key", "An idempotency key is required.", 422)
        try:
            with self.sessions.begin() as session:
                account = owned_account(session, customer_id, account_id, lock=True)
                previous = session.scalar(
                    select(Operation).where(
                        Operation.account_id == account_id, Operation.idempotency_key == key
                    )
                )
                if previous:
                    if previous.kind != kind or previous.arguments != arguments:
                        raise DomainError(
                            "idempotency_conflict", "Key already used for another request."
                        )
                    return previous.result
                if account.status != "ACTIVE":
                    raise DomainError("account_ineligible", "The account is not active.")
                before, result = mutate(session)
                operation_id = str(uuid4())
                result["operation_id"] = operation_id
                session.add(
                    Operation(
                        id=operation_id,
                        account_id=account_id,
                        actor_id=customer_id,
                        idempotency_key=key,
                        kind=kind,
                        arguments=arguments,
                        before=before,
                        result=result,
                        created_at=datetime.now(UTC),
                    )
                )
                session.flush()
            return result
        except IntegrityError:
            raise DomainError(
                "concurrent_conflict", "The operation conflicts with current state."
            ) from None

    def change_plan(self, customer_id: str, account_id: str, plan_id: str, key: str):
        def mutate(session):
            plan = session.get(Plan, plan_id)
            subscription = session.scalar(
                select(Subscription).where(Subscription.account_id == account_id).with_for_update()
            )
            if plan is None or not plan.enabled:
                raise DomainError("invalid_plan", "Select an enabled plan.", 422)
            if subscription is None or subscription.status != "ACTIVE":
                raise DomainError("subscription_ineligible", "An active subscription is required.")
            if subscription.plan_id == plan_id:
                raise DomainError("unchanged_plan", "The subscription already uses that plan.")
            before = {"plan_id": subscription.plan_id, "version": subscription.version}
            changed = session.execute(
                update(Subscription)
                .where(
                    Subscription.id == subscription.id,
                    Subscription.version == subscription.version,
                    Subscription.status == "ACTIVE",
                )
                .values(plan_id=plan_id, version=subscription.version + 1)
            )
            if changed.rowcount != 1:
                raise DomainError(
                    "concurrent_conflict", "Subscription changed; reload before retrying."
                )
            return before, {
                "kind": "change_plan",
                "account_id": account_id,
                "subscription_id": subscription.id,
                "plan_id": plan_id,
                "version": before["version"] + 1,
            }

        return self._execute(
            customer_id, account_id, key, "change_plan", {"plan_id": plan_id}, mutate
        )

    def transition_subscription(self, customer_id: str, account_id: str, target: str, key: str):
        """Internal lifecycle service; not an AI-registered tool."""
        allowed = {
            "ACTIVE": {"PAST_DUE", "CANCELED"},
            "PAST_DUE": {"ACTIVE", "CANCELED"},
            "CANCELED": set(),
        }

        def mutate(session):
            subscription = session.scalar(
                select(Subscription).where(Subscription.account_id == account_id).with_for_update()
            )
            if subscription is None:
                raise DomainError("subscription_not_found", "Subscription not found.", 404)
            if target not in allowed[subscription.status]:
                raise DomainError("invalid_transition", "Subscription transition is not permitted.")
            before = {"status": subscription.status, "version": subscription.version}
            subscription.status = target
            subscription.version += 1
            if target == "CANCELED":
                subscription.ends_on = self.today()
            return before, {
                "kind": "subscription_transition",
                "account_id": account_id,
                "status": target,
                "version": subscription.version,
            }

        return self._execute(
            customer_id, account_id, key, "subscription_transition", {"status": target}, mutate
        )

    def refund(self, customer_id: str, account_id: str, invoice_id: str, key: str):
        def mutate(session):
            invoice = session.scalar(
                select(Invoice)
                .where(Invoice.id == invoice_id, Invoice.account_id == account_id)
                .with_for_update()
            )
            if invoice is None:
                raise DomainError("invoice_not_found", "Invoice not found.", 404)
            age = (self.today() - invoice.issued_on).days
            if invoice.refunded_minor or session.scalar(
                select(Refund).where(Refund.invoice_id == invoice_id)
            ):
                raise DomainError("already_refunded", "The invoice has already been refunded.")
            if invoice.status != "PAID" or not 0 <= age <= 30 or invoice.amount_minor > 10000:
                raise DomainError("refund_ineligible", "The invoice is not eligible for a refund.")
            changed = session.execute(
                update(Invoice)
                .where(
                    Invoice.id == invoice_id, Invoice.refunded_minor == 0, Invoice.status == "PAID"
                )
                .values(refunded_minor=invoice.amount_minor)
            )
            if changed.rowcount != 1:
                raise DomainError("concurrent_conflict", "Invoice changed; reload before retrying.")
            refund_id = str(uuid4())
            session.add(
                Refund(
                    id=refund_id,
                    invoice_id=invoice_id,
                    amount_minor=invoice.amount_minor,
                    created_at=datetime.now(UTC),
                )
            )
            return {"refunded_minor": 0}, {
                "kind": "refund",
                "refund_id": refund_id,
                "invoice_id": invoice_id,
                "account_id": account_id,
                "amount_minor": invoice.amount_minor,
                "currency": invoice.currency,
            }

        return self._execute(
            customer_id, account_id, key, "refund", {"invoice_id": invoice_id}, mutate
        )
