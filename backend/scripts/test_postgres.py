"""Run integration tests against the explicitly named disposable Compose database."""

import os
import subprocess
import sys

from sqlalchemy.engine import make_url

from northstar.config import Settings

settings = Settings()
url = make_url(settings.database_url.get_secret_value())
if url.get_backend_name() != "postgresql" or url.database == "northstar_test":
    raise SystemExit("Run from the normal PostgreSQL backend container.")
environment = os.environ.copy()
environment["NORTHSTAR_TEST_DATABASE_URL"] = url.set(database="northstar_test").render_as_string(
    hide_password=False
)
raise SystemExit(subprocess.call([sys.executable, "-m", "pytest", "-q"], env=environment))
