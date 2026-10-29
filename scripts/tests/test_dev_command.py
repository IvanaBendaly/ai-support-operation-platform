import os
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "dev.py"


def test_setup_fails_actionably_without_docker(tmp_path):
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "setup"],
        check=False,
        cwd=tmp_path,
        env=dict(os.environ, PATH=""),
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 1
    assert "Required executable not found: docker" in result.stderr


def test_required_postgres_check_cannot_silently_skip(tmp_path):
    environment = dict(os.environ)
    environment.pop("NORTHSTAR_TEST_DATABASE_URL", None)
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "check", "--require-postgres"],
        check=False,
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 1
    assert "Set NORTHSTAR_TEST_DATABASE_URL" in result.stderr


def test_setup_refuses_a_python_other_than_312():
    import importlib.util

    import pytest

    spec = importlib.util.spec_from_file_location("dev", SCRIPT)
    dev = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(dev)
    dev.require_python((3, 12), "ok")
    for version in [(3, 11), (3, 13)]:
        with pytest.raises(RuntimeError, match="Python 3.12 is required"):
            dev.require_python(version, "The existing .venv")
