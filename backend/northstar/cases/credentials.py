"""Opaque customer tokens: issue out of band, persist only a digest, expire/revoke."""

import argparse
import hashlib
import json
import secrets
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from northstar.cases.models import CustomerCredential
from northstar.config import load_settings
from northstar.db import make_engine, session_factory
from northstar.domain import DomainError
from northstar.models import Customer


def issue(sessions, customer_id: str, hours: int = 24) -> dict:
    if not 1 <= hours <= 720:
        raise DomainError("invalid_expiry", "Credential lifetime must be 1–720 hours.", 422)
    token = secrets.token_urlsafe(32)
    with sessions.begin() as session:
        if session.get(Customer, customer_id) is None:
            raise DomainError("customer_not_found", "Customer not found.", 404)
        credential = CustomerCredential(
            id=str(uuid4()),
            customer_id=customer_id,
            token_hash=hashlib.sha256(token.encode()).hexdigest(),
            expires_at=datetime.now(UTC) + timedelta(hours=hours),
            revoked=False,
        )
        session.add(credential)
        return {
            "credential_id": credential.id,
            "token": token,
            "expires_at": credential.expires_at.isoformat(),
        }


def authenticated_customer(request: Request) -> str:
    header = request.headers.get("authorization", "")
    if not header.startswith("Bearer ") or len(header) > 200:
        raise DomainError("unauthenticated", "Customer credentials required.", 401)
    digest = hashlib.sha256(header[7:].encode()).hexdigest()
    with request.app.state.sessions() as session:
        credential = session.scalar(
            select(CustomerCredential).where(
                CustomerCredential.token_hash == digest,
                CustomerCredential.revoked.is_(False),
                CustomerCredential.expires_at > datetime.now(UTC),
            )
        )
        if credential is None:
            raise DomainError("unauthenticated", "Customer credentials required.", 401)
        return credential.customer_id


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("issue")
    create.add_argument("customer_id")
    create.add_argument("--hours", type=int, default=24)
    revoke = commands.add_parser("revoke")
    revoke.add_argument("credential_id")
    args = parser.parse_args()
    engine = make_engine(load_settings())
    sessions = session_factory(engine)
    try:
        if args.command == "issue":
            print(json.dumps(issue(sessions, args.customer_id, args.hours)))
        else:
            with sessions.begin() as session:
                credential = session.get(CustomerCredential, args.credential_id)
                if credential is None:
                    raise DomainError("not_found", "Credential not found.", 404)
                credential.revoked = True
            print("Credential revoked.")
    except SQLAlchemyError:
        parser.error(
            "Credential storage is unavailable; check migrations and database connectivity."
        )
    except DomainError as exc:
        parser.error(str(exc))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
