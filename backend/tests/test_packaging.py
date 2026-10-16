"""Exercise the installed distribution, rather than relying on the source checkout."""

import os
import shutil
import subprocess
import sys
from pathlib import Path


def test_installed_package_can_migrate_and_report_readiness(tmp_path):
    source = tmp_path / "source"
    shutil.copytree(
        Path(__file__).resolve().parents[1],
        source,
        ignore=shutil.ignore_patterns(
            "*.egg-info", "build", "__pycache__", ".pytest_cache", ".ruff_cache", "*.db", ".env*"
        ),
    )
    wheels = tmp_path / "wheels"
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "wheel",
            "--no-index",
            "--no-deps",
            "--no-build-isolation",
            "--wheel-dir",
            str(wheels),
            str(source),
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )
    installed = tmp_path / "installed"
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--no-index",
            "--no-deps",
            "--target",
            str(installed),
            str(next(wheels.glob("*.whl"))),
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    code = """
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import northstar
assert Path(northstar.__file__).is_relative_to(Path(sys.argv[1]))
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from northstar.api import create_app
config = Config()
config.set_main_option("script_location", "northstar:migrations")
command.upgrade(config, "head")
with TestClient(create_app()) as client:
    assert client.get("/api/ready").status_code == 200
command.check(config)
command.downgrade(config, "base")
"""
    environment = {
        key: value for key, value in os.environ.items() if not key.startswith("NORTHSTAR_")
    }
    environment.update(
        NORTHSTAR_ENVIRONMENT="test",
        NORTHSTAR_DATABASE_URL=f"sqlite+pysqlite:///{tmp_path / 'packaged.db'}",
    )
    subprocess.run(
        [sys.executable, "-I", "-c", code, str(installed)],
        cwd=tmp_path,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
