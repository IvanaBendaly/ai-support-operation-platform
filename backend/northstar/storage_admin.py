"""Maintenance commands. Stop API and workers before export or orphan cleanup."""

import argparse
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import inspect, select, text

from northstar.config import load_settings
from northstar.db import make_engine, session_factory
from northstar.retrieval.models import Document, StoredObject
from northstar.storage import ObjectStore, store_for


def export_legacy(engine, store):
    columns = {column["name"] for column in inspect(engine).get_columns("knowledge_documents")}
    if not {"original", "storage_key"} <= columns:
        raise RuntimeError("Export requires schema 0008; stop all writers first.")
    count = 0
    with engine.connect() as connection:
        identifiers = (
            connection.execute(text("SELECT id FROM knowledge_documents WHERE storage_key IS NULL"))
            .scalars()
            .all()
        )
    for identifier in identifiers:
        with engine.begin() as connection:
            row = connection.execute(
                text("SELECT original, original_hash FROM knowledge_documents WHERE id=:id"),
                {"id": identifier},
            ).one()
            key = "originals/" + str(uuid4())
            connection.execute(StoredObject.__table__.insert().values(key=key))
        # Reservation persists if upload/read-back/DB update fails; reruns are safe.
        store.put(key, bytes(row.original))
        store.get(key, row.original_hash)
        with engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE knowledge_documents SET storage_key=:key "
                    "WHERE id=:id AND storage_key IS NULL"
                ),
                {"key": key, "id": identifier},
            )
        count += 1
    return count


def cleanup(sessions, *, apply=False):
    cutoff = datetime.now(UTC) - timedelta(hours=24)
    count = 0
    with sessions.begin() as session:
        candidates = session.scalars(
            select(StoredObject)
            .where(
                StoredObject.created_at < cutoff,
                ~select(Document.id).where(Document.storage_key == StoredObject.key).exists(),
            )
            .with_for_update(skip_locked=True)
        ).all()
        for item in candidates:
            if apply:
                store_for(sessions).delete(item.key)
                session.delete(item)
            count += 1
    return count


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["export-legacy", "cleanup"])
    parser.add_argument(
        "--apply", action="store_true", help="Delete unreferenced reservations older than 24 hours"
    )
    args = parser.parse_args()
    settings = load_settings()
    engine = make_engine(settings)
    try:
        if args.command == "export-legacy":
            print(f"Verified exports: {export_legacy(engine, ObjectStore(settings.storage))}")
        else:
            count = cleanup(session_factory(engine), apply=args.apply)
            print(f"Orphan objects {'deleted' if args.apply else 'eligible'}: {count}")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
