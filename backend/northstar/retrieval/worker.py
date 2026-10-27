"""Database-backed extraction worker with expiring claims and isolated conversion."""

import argparse
import hashlib
import json
import logging
import subprocess
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from sqlalchemy import or_, select, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from northstar.config import load_settings
from northstar.db import make_engine, session_factory
from northstar.logging import configure_logging
from northstar.retrieval.extraction import IngestionError, extract
from northstar.retrieval.models import Document, Section
from northstar.retrieval.service import utc

MAX_ATTEMPTS = 3
EXTRACTION_TIMEOUT = 120
LEASE_SECONDS = 180
logger = logging.getLogger("northstar")


def claim(sessions, now=None):
    now = now or datetime.now(UTC)
    with sessions.begin() as session:
        available = or_(
            Document.status == "QUEUED",
            (Document.status == "PROCESSING") & (Document.lease_expires_at <= now),
        )
        document = session.scalar(
            select(Document)
            .where(available)
            .order_by(Document.created_at, Document.id)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        if document is None:
            return None
        token = str(uuid4())
        exhausted = document.attempts >= MAX_ATTEMPTS
        # The condition also protects claims on SQLite, which has no row locks.
        changed = session.execute(
            update(Document)
            .execution_options(synchronize_session=False)
            .where(Document.id == document.id, available)
            .values(
                status="FAILED" if exhausted else "PROCESSING",
                error="extraction_attempts_exhausted" if exhausted else None,
                lease_token=None if exhausted else token,
                lease_expires_at=None if exhausted else now + timedelta(seconds=LEASE_SECONDS),
                attempts=document.attempts if exhausted else document.attempts + 1,
            )
        )
        if not changed.rowcount:
            return None
        return {
            "id": document.id,
            "token": None if exhausted else token,
            "filename": document.filename,
            "data": document.original,
        }


def finish(sessions, job, result=None, error=None):
    """A stale worker cannot publish. Sections and READY commit together."""
    with sessions.begin() as session:
        document = session.get(Document, job["id"], with_for_update=True)
        if (
            document is None
            or document.status != "PROCESSING"
            or document.lease_token != job["token"]
            or utc(document.lease_expires_at) <= datetime.now(UTC)
        ):
            return False
        document.lease_token = document.lease_expires_at = None
        if error:
            document.status, document.error = "FAILED", error
            return True
        media, content, sections, warnings = result
        digest = hashlib.sha256(content.encode()).hexdigest()
        duplicate = session.scalar(select(Document).where(Document.content_hash == digest))
        if duplicate:
            document.status, document.duplicate_of = "DUPLICATE", duplicate.id
            document.error = None
            return True
        document.media_type, document.content_hash = media, digest
        document.status, document.error, document.warnings = "READY", None, warnings
        for ordinal, (source, text) in enumerate(sections, 1):
            session.add(
                Section(
                    id=hashlib.sha256(f"{document.id}:{ordinal}".encode()).hexdigest(),
                    document_id=document.id,
                    ordinal=ordinal,
                    source=source,
                    text=text,
                )
            )
    return True


def convert_isolated(job, timeout=EXTRACTION_TIMEOUT):
    with TemporaryDirectory(prefix="northstar-extract-") as directory:
        incoming, outgoing = Path(directory) / "input", Path(directory) / "result.json"
        incoming.write_bytes(job["data"])
        try:
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "northstar.retrieval.worker",
                    "--extract",
                    str(incoming),
                    str(outgoing),
                    f"--filename={job['filename']}",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return {"error": "extraction_timeout"}
        if completed.returncode != 0 or not outgoing.exists():
            return {"error": "extraction_process_failed"}
        try:
            return json.loads(outgoing.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {"error": "extraction_process_failed"}


def run_once(sessions):
    job = claim(sessions)
    if job is None:
        return False
    if job["token"] is None:
        return True
    output = convert_isolated(job)
    try:
        finish(sessions, job, output.get("result"), output.get("error"))
    except IntegrityError:
        # A concurrent conversion may have committed the same normalized text.
        # Retry only the transaction; the unique content hash still arbitrates.
        finish(sessions, job, output.get("result"), output.get("error"))
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true", help="Process at most one available job")
    parser.add_argument("--extract", nargs=2, metavar=("INPUT", "OUTPUT"), help=argparse.SUPPRESS)
    parser.add_argument("--filename", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.extract:
        incoming, outgoing = map(Path, args.extract)
        try:
            output = {"result": extract(args.filename, incoming.read_bytes())}
        except IngestionError as exc:
            output = {"error": str(exc)}
        except Exception:
            output = {"error": "extraction_failed"}
        outgoing.write_text(json.dumps(output), encoding="utf-8")
        return
    settings = load_settings()
    configure_logging(settings.log_level)
    engine = make_engine(settings)
    sessions = session_factory(engine)
    try:
        while True:
            try:
                worked = run_once(sessions)
            except SQLAlchemyError:
                # Leave the claim to expire; never publish partial sections.
                logger.error("extraction_storage_unavailable")
                if args.once:
                    raise SystemExit(1) from None
                worked = False
            if args.once:
                break
            if not worked:
                time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
