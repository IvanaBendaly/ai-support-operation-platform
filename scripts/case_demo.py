"""Demonstrate C05 against a disposable database; no real credentials are printed."""

import json
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi.encoders import jsonable_encoder
from northstar.api import create_app
from northstar.cases.credentials import issue
from northstar.cases.schemas import Outcome
from northstar.cases.service import CaseService
from northstar.config import Settings
from northstar.db import Base, make_engine, session_factory
from northstar.seed import seed
from starlette.testclient import TestClient


def main():
    with TemporaryDirectory(prefix="northstar-case-demo-") as directory:
        settings = Settings(
            _env_file=None,
            environment="test",
            log_level="WARNING",
            database_url=f"sqlite+pysqlite:///{Path(directory) / 'demo.db'}",
        )
        engine = make_engine(settings)
        try:
            Base.metadata.create_all(engine)
            sessions = session_factory(engine)
            with sessions.begin() as session:
                seed(session, date(2026, 10, 20))
            credential = issue(sessions, "alice")
            worker = CaseService(sessions)
            output = {"environment": "disposable SQLite test database", "states": []}
            with TestClient(create_app(settings, engine)) as client:
                client.headers["Authorization"] = "Bearer " + credential["token"]
                client.headers["Idempotency-Key"] = "demo-create"
                payload = {
                    "account_id": "alice-active",
                    "subject": "Invoice explanation",
                    "message": "Can you explain my latest invoice?",
                    "category": "billing",
                }
                created = client.post("/api/cases", json=payload)
                assert created.status_code == 201
                case_id = created.json()["case_id"]
                output["submission"] = created.json()
                output["duplicate_submission"] = client.post("/api/cases", json=payload).json()
                output["states"].append(client.get("/api/cases/" + case_id).json())
                attempt = worker.start_processing(case_id)
                output["states"].append(client.get("/api/cases/" + case_id).json())
                worker.complete(
                    case_id,
                    attempt["attempt_id"],
                    Outcome(
                        disposition="clarification_requested",
                        reply="Which invoice date do you mean?",
                    ),
                )
                state = client.get("/api/cases/" + case_id).json()
                output["states"].append(state)
                client.headers["Idempotency-Key"] = "demo-followup"
                follow = client.post(
                    f"/api/cases/{case_id}/messages",
                    json={"message": "The October invoice.", "expected_version": state["version"]},
                )
                assert follow.status_code == 201
                output["states"].append(client.get("/api/cases/" + case_id).json())
                second = worker.start_processing(case_id)
                worker.complete(
                    case_id,
                    second["attempt_id"],
                    Outcome(
                        disposition="answered",
                        reply="The invoice reflects your selected subscription plan.",
                    ),
                )
                output["states"].append(client.get("/api/cases/" + case_id).json())
                for kind in ["messages", "events", "attempts"]:
                    output[kind] = client.get(f"/api/cases/{case_id}/{kind}").json()
                assert output["duplicate_submission"]["replayed"]
                assert output["states"][-1]["status"] == "resolved"
            print(json.dumps(jsonable_encoder(output), indent=2))
        finally:
            engine.dispose()


if __name__ == "__main__":
    main()
