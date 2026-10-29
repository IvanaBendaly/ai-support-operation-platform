"""Repeatable development setup and checks. Run from any working directory."""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]


def run(command: list[str], cwd: Path = ROOT) -> None:
    subprocess.run(command, cwd=cwd, check=True)


def executable(name: str) -> str:
    found = shutil.which(name)
    if not found:
        raise RuntimeError(
            f"Required executable not found: {name}. See docs/guides/SETUP.md prerequisites."
        )
    return found


def require_python(version: tuple[int, int], label: str) -> None:
    """The lockfile pins Python 3.12 binaries; another version breaks native packages."""
    if tuple(version[:2]) != (3, 12):
        raise RuntimeError(
            f"{label} is Python {version[0]}.{version[1]}; Python 3.12 is required. "
            "On Windows run: py -3.12 scripts/dev.py setup"
        )


def venv_version(python: Path) -> tuple[int, int]:
    output = subprocess.run(
        [str(python), "-c", "import sys; print(*sys.version_info[:2])"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    major, minor = output.split()
    return int(major), int(minor)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("task", choices=["setup", "check"])
    parser.add_argument(
        "--require-postgres",
        action="store_true",
        help="Fail rather than skip database checks without a configured test DB",
    )
    args = parser.parse_args()
    try:
        python = ROOT / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        if args.task == "setup":
            docker = executable("docker")
            run([docker, "version", "--format", "{{.Server.Version}}"], cwd=ROOT)
            pnpm = executable("pnpm")
            run([executable("node"), "--version"])
            if not python.is_file():
                require_python(sys.version_info, "The interpreter running this script")
                run([sys.executable, "-m", "venv", str(ROOT / ".venv")])
            # Never install into an existing environment of another version.
            require_python(venv_version(python), "The existing .venv")
            run([str(python), "-m", "pip", "install", "-r", "backend/requirements.lock"])
            run(
                [
                    str(python),
                    "-m",
                    "pip",
                    "install",
                    "--no-deps",
                    "--no-build-isolation",
                    "-e",
                    "backend",
                ]
            )
            run([pnpm, "install", "--frozen-lockfile"], ROOT / "frontend")
            if not (ROOT / ".env").exists():
                shutil.copyfile(ROOT / ".env.example", ROOT / ".env")
            run([docker, "compose", "config", "--quiet"])
            run([docker, "compose", "up", "--build", "--wait"])
            print("Northstar is running at http://localhost:8080")
        else:
            if args.require_postgres and not os.getenv("NORTHSTAR_TEST_DATABASE_URL"):
                raise RuntimeError(
                    "Set NORTHSTAR_TEST_DATABASE_URL to an empty disposable database."
                )
            if not python.is_file():
                raise RuntimeError(
                    "Install local development dependencies as documented in README.md."
                )
            pnpm = executable("pnpm")
            run([str(python), "-m", "ruff", "check", "backend", "scripts"])
            run([str(python), "-m", "ruff", "format", "--check", "backend", "scripts"])
            # Isolate test files and cache from previous runs under other OS identities.
            with TemporaryDirectory(prefix="northstar-check-") as directory:
                run(
                    [
                        str(python),
                        "-m",
                        "pytest",
                        "-q",
                        "tests",
                        "../scripts/tests",
                        "--basetemp",
                        str(Path(directory) / "tests"),
                        "-o",
                        f"cache_dir={Path(directory) / 'cache'}",
                    ],
                    ROOT / "backend",
                )
            run([pnpm, "test"], ROOT / "frontend")
            run([pnpm, "build"], ROOT / "frontend")
        return 0
    except (RuntimeError, subprocess.CalledProcessError) as error:
        print(f"Development command failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
