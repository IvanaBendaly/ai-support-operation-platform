"""Run the API and worker locally WITHOUT Docker, in test mode.

Uses a SQLite file and a local folder instead of PostgreSQL and MinIO. For trying the
workflow only: not a substitute for the Compose stack or PostgreSQL verification.
All state lives in the git-ignored `.test-run-local/` folder; delete it to start over.
The generated administrator token is written to `.test-run-local/admin-token.txt`.

Optional settings (AI review, LlamaExtract, ...) are read from your environment, so
`NORTHSTAR_REVIEW__*` and `NORTHSTAR_EXTRACTION__*` variables set in the shell apply.
"""

import os
import secrets
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / ".test-run-local"


def main():
    DATA.mkdir(exist_ok=True)
    token_file = DATA / "admin-token.txt"
    if not token_file.exists():
        token_file.write_text(secrets.token_urlsafe(32), encoding="utf-8")
    os.environ.update(
        NORTHSTAR_ENVIRONMENT="test",
        NORTHSTAR_DATABASE_URL=f"sqlite+pysqlite:///{(DATA / 'northstar.db').as_posix()}",
        NORTHSTAR_STORAGE__BACKEND="filesystem",
        NORTHSTAR_STORAGE__DIRECTORY=str(DATA / "objects"),
        NORTHSTAR_ADMIN_TOKEN=token_file.read_text(encoding="utf-8").strip(),
    )
    os.environ.setdefault("NORTHSTAR_REVIEW__PROVIDER", "disabled")
    backend = ROOT / "backend"
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=backend, check=True)
    worker = subprocess.Popen([sys.executable, "-m", "northstar.retrieval.worker"], cwd=backend)
    print(f"API http://127.0.0.1:8000 · admin token in {token_file}", flush=True)
    try:
        subprocess.run(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "--factory",
                "northstar.main:create_app",
                "--host",
                "127.0.0.1",
                "--port",
                "8000",
            ],
            cwd=backend,
            check=False,
        )
    finally:
        worker.terminate()


if __name__ == "__main__":
    main()
