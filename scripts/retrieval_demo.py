"""Run the C04 portfolio demonstration in a disposable SQLite test database."""

import json
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from northstar.ai.worker import run_review_once
from northstar.config import Settings, StorageSettings
from northstar.db import Base, make_engine, session_factory
from northstar.retrieval.search import RetrievalService
from northstar.retrieval.service import KnowledgeService


def main():
    corpus_path = (
        Path(__file__).resolve().parents[1] / "backend/tests/fixtures/retrieval_corpus.json"
    )
    at = datetime(2026, 10, 20, tzinfo=UTC)
    with TemporaryDirectory(prefix="northstar-retrieval-demo-") as directory:
        engine = make_engine(
            Settings(
                _env_file=None,
                environment="test",
                storage=StorageSettings(
                    backend="filesystem", directory=str(Path(directory) / "objects")
                ),
                database_url=f"sqlite+pysqlite:///{Path(directory) / 'demo.db'}",
            )
        )
        try:
            Base.metadata.create_all(engine)
            sessions = session_factory(engine)
            knowledge = KnowledgeService(sessions)
            for policy in json.loads(corpus_path.read_text()):
                document = knowledge.ingest(
                    policy["id"],
                    policy["id"] + ".md",
                    policy["text"].encode(),
                    at,
                    sensitivity="PUBLIC",
                    title=policy["id"],
                )["document"]
                run_review_once(sessions)
                knowledge.decide(document["id"], "APPROVED", "Reviewed synthetic demo fixture")
            retrieval = RetrievalService(sessions)
            questions = ["I want my money back", "I am locked out", "astronomy telescope galaxies"]
            output = {
                "environment": "disposable SQLite test database",
                "queries": [
                    retrieval.search(query, at=at).model_dump(mode="json") for query in questions
                ],
            }
            previous = retrieval.search("refund", at=at)
            replacement = knowledge.ingest(
                "refunds",
                "refunds-v2.txt",
                b"Refunds require finance review before approval. Submit the invoice for review.",
                at,
                replace=True,
                sensitivity="PUBLIC",
                title="Updated refunds",
            )["document"]
            run_review_once(sessions)
            knowledge.decide(replacement["id"], "APPROVED", "Reviewed synthetic replacement")
            updated = retrieval.search("refund", at=at)
            output["replacement"] = {
                "previous_document_id": previous.evidence[0].document_id,
                "new_document_id": replacement["id"],
                "result": updated.model_dump(mode="json"),
                "old_version_excluded": all(
                    e.document_id != previous.evidence[0].document_id for e in updated.evidence
                ),
            }
            knowledge.deactivate("refunds")
            output["deactivation"] = retrieval.search("refund", at=at).model_dump(mode="json")
            print(json.dumps(output, indent=2, ensure_ascii=True))
        finally:
            engine.dispose()


if __name__ == "__main__":
    main()
