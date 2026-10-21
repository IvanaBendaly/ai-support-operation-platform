"""Transactional case lifecycle. Processing hooks are trusted C07/C10 boundaries."""

import hashlib
import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import case as sql_case
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from northstar.cases.models import Attempt, Case, CaseEvent, Message, Submission
from northstar.cases.schemas import CreateCase, FollowUp, Outcome
from northstar.domain import DomainError, owned_account
from northstar.models import Customer, Invoice

OUTCOME_STATUS = {
    "answered": "resolved",
    "action_completed": "resolved",
    "refused": "resolved",
    "clarification_requested": "awaiting_customer",
    "escalated": "escalated",
}
ERROR_CODES = {"processing_failed", "provider_unavailable", "retrieval_failed", "invalid_result"}


def aware(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def view(case: Case) -> dict:
    return {
        name: getattr(case, name)
        for name in (
            "id",
            "customer_id",
            "account_id",
            "subject",
            "category",
            "context",
            "status",
            "disposition",
            "version",
            "message_count",
            "attempt_count",
            "last_error",
            "created_at",
            "updated_at",
            "resolved_at",
        )
    }


class CaseService:
    def __init__(self, sessions, clock=None):
        self.sessions = sessions
        self.clock = clock or (lambda: datetime.now(UTC))

    def _case(self, session, case_id: str, customer_id: str | None = None) -> Case:
        query = select(Case).where(Case.id == case_id)
        if customer_id is not None:
            query = query.where(Case.customer_id == customer_id)
        case = session.scalar(query.with_for_update())
        if case is None:
            raise DomainError("case_not_found", "Case not found.", 404)
        return case

    def _customer(self, session, customer_id):
        if session.get(Customer, customer_id, with_for_update=True) is None:
            raise DomainError("customer_not_found", "Customer not found.", 404)

    def _event(self, session, case, kind, actor, details=None, *, initial=False):
        if not initial:
            case.version += 1
        session.add(
            CaseEvent(
                id=str(uuid4()),
                case_id=case.id,
                version=case.version,
                kind=kind,
                actor=actor,
                status=case.status,
                disposition=case.disposition,
                details=details or {},
                created_at=self.clock(),
            )
        )

    def _message(self, session, case, content, role):
        case.message_count += 1
        message = Message(
            id=str(uuid4()),
            case_id=case.id,
            sequence=case.message_count,
            content=content,
            role=role,
            created_at=self.clock(),
        )
        session.add(message)
        return message

    def _replay(self, session, customer_id, key, arguments):
        if not isinstance(key, str) or not 1 <= len(key) <= 128 or not key.strip():
            raise DomainError(
                "invalid_idempotency_key", "Supply an Idempotency-Key of 1–128 characters.", 422
            )
        fingerprint = hashlib.sha256(
            json.dumps(arguments, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        receipt = session.scalar(
            select(Submission).where(Submission.customer_id == customer_id, Submission.key == key)
        )
        if receipt:
            if receipt.fingerprint != fingerprint:
                raise DomainError(
                    "idempotency_conflict", "This idempotency key was used for different input."
                )
            return fingerprint, {
                "case_id": receipt.case_id,
                "message_id": receipt.message_id,
                "replayed": True,
            }
        return fingerprint, None

    def _receipt(self, session, customer_id, key, fingerprint, case, message):
        session.flush()
        session.add(
            Submission(
                id=str(uuid4()),
                customer_id=customer_id,
                key=key,
                fingerprint=fingerprint,
                case_id=case.id,
                message_id=message.id,
            )
        )
        session.flush()
        return {"case_id": case.id, "message_id": message.id, "replayed": False}

    def create(self, customer_id: str, key: str, data: CreateCase) -> dict:
        try:
            with self.sessions.begin() as session:
                self._customer(session, customer_id)
                owned_account(session, customer_id, data.account_id)
                if data.context.invoice_id:
                    invoice = session.get(Invoice, data.context.invoice_id)
                    if invoice is None or invoice.account_id != data.account_id:
                        raise DomainError(
                            "invoice_not_found", "Invoice not found for this account.", 404
                        )
                fingerprint, replay = self._replay(
                    session, customer_id, key, {"create": data.model_dump()}
                )
                if replay:
                    return replay
                case = Case(
                    id=str(uuid4()),
                    customer_id=customer_id,
                    account_id=data.account_id,
                    subject=data.subject,
                    category=data.category,
                    context=data.context.model_dump(),
                    status="open",
                    version=1,
                    message_count=1,
                    attempt_count=0,
                )
                session.add(case)
                session.flush()
                message = Message(
                    id=str(uuid4()),
                    case_id=case.id,
                    sequence=1,
                    role="customer",
                    content=data.message,
                    created_at=self.clock(),
                )
                session.add(message)
                self._event(session, case, "created", "customer", initial=True)
                return self._receipt(session, customer_id, key, fingerprint, case, message)
        except IntegrityError:
            raise DomainError(
                "concurrent_submission", "Submission conflicted; retry with the same key."
            ) from None

    @staticmethod
    def _version(case, expected):
        if case.version != expected:
            raise DomainError("version_conflict", "Case changed; reload it before retrying.")

    def follow_up(self, customer_id: str, case_id: str, key: str, data: FollowUp) -> dict:
        try:
            with self.sessions.begin() as session:
                self._customer(session, customer_id)
                case = self._case(session, case_id, customer_id)
                fingerprint, replay = self._replay(
                    session, customer_id, key, {"follow_up": data.model_dump(), "case_id": case_id}
                )
                if replay:
                    return replay
                self._version(case, data.expected_version)
                if case.status not in {"open", "awaiting_customer", "escalated"}:
                    raise DomainError(
                        "invalid_case_state", "Case cannot accept a follow-up in its current state."
                    )
                message = self._message(session, case, data.message, "customer")
                if case.status == "awaiting_customer":
                    case.status = "open"
                self._event(
                    session, case, "customer_message", "customer", {"message_id": message.id}
                )
                return self._receipt(session, customer_id, key, fingerprint, case, message)
        except IntegrityError:
            raise DomainError(
                "concurrent_submission", "Submission conflicted; retry with the same key."
            ) from None

    def start_processing(self, case_id: str, *, lease_seconds: int = 60) -> dict:
        if type(lease_seconds) is not int or not 1 <= lease_seconds <= 900:
            raise DomainError("invalid_lease", "Processing leases must be 1–900 seconds.", 422)
        with self.sessions.begin() as session:
            case = self._case(session, case_id)
            if case.status != "open":
                raise DomainError("invalid_case_state", "Only open cases can begin processing.")
            now = self.clock()
            case.attempt_count += 1
            attempt = Attempt(
                id=str(uuid4()),
                case_id=case.id,
                number=case.attempt_count,
                status="processing",
                started_at=now,
                expires_at=now + timedelta(seconds=lease_seconds),
            )
            session.add(attempt)
            case.status, case.current_attempt_id, case.last_error = "processing", attempt.id, None
            self._event(session, case, "processing_started", "worker", {"attempt_id": attempt.id})
            return {"case_id": case.id, "attempt_id": attempt.id, "expires_at": attempt.expires_at}

    def _active_attempt(self, session, case, attempt_id):
        attempt = session.get(Attempt, attempt_id)
        if attempt is None or attempt.case_id != case.id:
            raise DomainError("attempt_not_found", "Processing attempt not found.", 404)
        if (
            case.status != "processing"
            or case.current_attempt_id != attempt.id
            or attempt.status != "processing"
            or aware(attempt.expires_at) <= self.clock()
        ):
            raise DomainError("stale_attempt", "Processing attempt is no longer active.")
        return attempt

    def _outcome(self, session, case, outcome: Outcome, actor: str, attempt_id=None):
        case.status = OUTCOME_STATUS[outcome.disposition]
        case.disposition, case.last_error = outcome.disposition, None
        case.resolved_at = self.clock() if case.status == "resolved" else None
        case.current_attempt_id = None
        message = self._message(
            session, case, outcome.reply, "human" if actor == "human" else "assistant"
        )
        self._event(
            session,
            case,
            "outcome_recorded",
            actor,
            {**outcome.model_dump(), "attempt_id": attempt_id, "message_id": message.id},
        )

    def complete(self, case_id: str, attempt_id: str, outcome: Outcome) -> dict:
        with self.sessions.begin() as session:
            case = self._case(session, case_id)
            prior = session.get(Attempt, attempt_id)
            if prior and prior.case_id == case.id and prior.status == "succeeded":
                if prior.result != outcome.model_dump():
                    raise DomainError(
                        "outcome_conflict", "Attempt already completed with a different result."
                    )
                return {"case_id": case.id, "attempt_id": attempt_id, "replayed": True}
            attempt = self._active_attempt(session, case, attempt_id)
            self._outcome(session, case, outcome, "worker", attempt_id)
            attempt.status, attempt.finished_at, attempt.result = (
                "succeeded",
                self.clock(),
                outcome.model_dump(),
            )
            return {"case_id": case.id, "attempt_id": attempt_id, "replayed": False}

    def fail(self, case_id: str, attempt_id: str, error_code: str = "processing_failed") -> None:
        if error_code not in ERROR_CODES:
            raise DomainError(
                "invalid_error_code", "Use a supported safe processing failure code.", 422
            )
        with self.sessions.begin() as session:
            case = self._case(session, case_id)
            attempt = self._active_attempt(session, case, attempt_id)
            attempt.status, attempt.finished_at, attempt.error_code = (
                "failed",
                self.clock(),
                error_code,
            )
            case.status, case.current_attempt_id, case.last_error = "failed", None, error_code
            self._event(
                session,
                case,
                "processing_failed",
                "worker",
                {"attempt_id": attempt.id, "error_code": error_code},
            )

    def _recover(self, session, case):
        if case.status != "processing":
            return False
        attempt = session.get(Attempt, case.current_attempt_id)
        if attempt is None:
            raise DomainError("case_inconsistent", "Processing metadata is unavailable.", 503)
        if aware(attempt.expires_at) > self.clock():
            return False
        attempt.status, attempt.finished_at, attempt.error_code = (
            "timed_out",
            self.clock(),
            "processing_interrupted",
        )
        case.status, case.current_attempt_id, case.last_error = (
            "failed",
            None,
            "processing_interrupted",
        )
        self._event(session, case, "processing_interrupted", "system", {"attempt_id": attempt.id})
        return True

    def recover_expired(self, limit: int = 100) -> int:
        if type(limit) is not int or not 1 <= limit <= 100:
            raise DomainError("invalid_limit", "Recovery limit must be 1–100.", 422)
        with self.sessions.begin() as session:
            cases = session.scalars(
                select(Case)
                .join(Attempt, Attempt.id == Case.current_attempt_id)
                .where(Case.status == "processing", Attempt.expires_at <= self.clock())
                .order_by(Case.id)
                .limit(limit)
                .with_for_update(of=Case, skip_locked=True)
            ).all()
            return sum(self._recover(session, case) for case in cases)

    def retry(self, customer_id: str, case_id: str, expected_version: int) -> dict:
        with self.sessions.begin() as session:
            case = self._case(session, case_id, customer_id)
            self._version(case, expected_version)
            if case.status != "failed":
                raise DomainError("invalid_case_state", "Only failed cases can be retried.")
            case.status, case.last_error = "open", None
            self._event(session, case, "retry_requested", "customer")
            session.flush()
            return view(case)

    def human_review(self, case_id: str, expected_version: int, outcome: Outcome) -> dict:
        if outcome.disposition == "escalated":
            raise DomainError(
                "invalid_review", "Human review must resolve or request clarification.", 422
            )
        with self.sessions.begin() as session:
            case = self._case(session, case_id)
            self._version(case, expected_version)
            if case.status != "escalated":
                raise DomainError("invalid_case_state", "Only escalated cases accept human review.")
            self._outcome(session, case, outcome, "human")
            session.flush()
            return view(case)

    def get(self, customer_id: str | None, case_id: str) -> dict:
        with self.sessions.begin() as session:
            case = self._case(session, case_id, customer_id)
            self._recover(session, case)
            session.flush()
            return view(case)

    def list_cases(
        self, customer_id: str, *, status=None, category=None, account_id=None, limit=25, offset=0
    ) -> list[dict]:
        self._page(limit, offset)
        if status is not None and status not in {
            "open",
            "processing",
            "awaiting_customer",
            "escalated",
            "resolved",
            "failed",
        }:
            raise DomainError("invalid_status", "Unknown case status.", 422)
        if category is not None and category not in {
            "general",
            "billing",
            "account",
            "technical",
            "privacy",
        }:
            raise DomainError("invalid_category", "Unknown case category.", 422)
        with self.sessions.begin() as session:
            # Filter on the effective state, then recover only the selected page.
            effective_status = sql_case(
                ((Case.status == "processing") & (Attempt.expires_at <= self.clock()), "failed"),
                else_=Case.status,
            )
            query = (
                select(Case)
                .outerjoin(Attempt, Attempt.id == Case.current_attempt_id)
                .where(Case.customer_id == customer_id)
            )
            for field, value in [
                (effective_status, status),
                (Case.category, category),
                (Case.account_id, account_id),
            ]:
                if value is not None:
                    query = query.where(field == value)
            rows = session.scalars(
                query.order_by(Case.created_at.desc(), Case.id)
                .offset(offset)
                .limit(limit)
                .with_for_update(of=Case)
            ).all()
            for row in rows:
                self._recover(session, row)
            session.flush()
            return [view(row) for row in rows]

    @staticmethod
    def _page(limit, offset):
        if type(limit) is not int or not 1 <= limit <= 100 or type(offset) is not int or offset < 0:
            raise DomainError(
                "invalid_pagination", "Use limit 1–100 and a nonnegative offset.", 422
            )

    def history(
        self, customer_id: str | None, case_id: str, kind: str, limit=25, offset=0
    ) -> list[dict]:
        self._page(limit, offset)
        if kind not in {"messages", "events", "attempts"}:
            raise DomainError("invalid_history", "Unknown history type.", 422)
        model, order, fields = {
            "messages": (
                Message,
                Message.sequence,
                ("id", "sequence", "role", "content", "created_at"),
            ),
            "events": (
                CaseEvent,
                CaseEvent.version,
                (
                    "id",
                    "version",
                    "kind",
                    "actor",
                    "status",
                    "disposition",
                    "details",
                    "created_at",
                ),
            ),
            "attempts": (
                Attempt,
                Attempt.number,
                (
                    "id",
                    "number",
                    "status",
                    "started_at",
                    "expires_at",
                    "finished_at",
                    "error_code",
                    "result",
                ),
            ),
        }[kind]
        with self.sessions.begin() as session:
            case = self._case(session, case_id, customer_id)
            self._recover(session, case)
            session.flush()
            return [
                {field: getattr(row, field) for field in fields}
                for row in session.scalars(
                    select(model)
                    .where(model.case_id == case_id)
                    .order_by(order)
                    .offset(offset)
                    .limit(limit)
                )
            ]
