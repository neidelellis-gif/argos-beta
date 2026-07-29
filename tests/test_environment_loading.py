import os
import subprocess
import sys
from pathlib import Path

from backend.config.environment import load_environment


def test_load_environment_accepts_supported_assignments(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text(
        """
# comment
PLAIN=value
DOUBLE="two words"
SINGLE='three words'
export EXPORTED=available
WITH_COMMENT=result # ignored comment
EMPTY=
""",
        encoding="utf-8",
    )
    names = ("PLAIN", "DOUBLE", "SINGLE", "EXPORTED", "WITH_COMMENT", "EMPTY")
    for name in names:
        monkeypatch.delenv(name, raising=False)

    load_environment(env_file)

    assert {name: os.environ[name] for name in names} == {
        "PLAIN": "value",
        "DOUBLE": "two words",
        "SINGLE": "three words",
        "EXPORTED": "available",
        "WITH_COMMENT": "result",
        "EMPTY": "",
    }


def test_load_environment_ignores_invalid_lines(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text(
        """
NO_ASSIGNMENT
1INVALID=value
export MISSING_ASSIGNMENT
UNCLOSED="value
TRAILING="value" unexpected
VALID=loaded
""",
        encoding="utf-8",
    )
    monkeypatch.delenv("VALID", raising=False)

    load_environment(env_file)

    assert os.environ["VALID"] == "loaded"
    assert "1INVALID" not in os.environ


def test_load_environment_preserves_existing_values(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("EXISTING=from-file\n", encoding="utf-8")
    monkeypatch.setenv("EXISTING", "from-process")

    load_environment(env_file)

    assert os.environ["EXISTING"] == "from-process"


def test_importing_backend_loads_project_root_env(tmp_path):
    source_root = Path(__file__).resolve().parents[1]
    package_root = tmp_path / "backend"
    config_root = package_root / "config"
    config_root.mkdir(parents=True)
    (package_root / "__init__.py").write_text(
        (source_root / "backend" / "__init__.py").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (config_root / "__init__.py").write_text("", encoding="utf-8")
    (config_root / "environment.py").write_text(
        (source_root / "backend" / "config" / "environment.py").read_text(
            encoding="utf-8"
        ),
        encoding="utf-8",
    )
    (tmp_path / ".env").write_text("AUTOMATIC_ENV_LOAD=loaded\n", encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import backend, os; assert os.environ['AUTOMATIC_ENV_LOAD'] == 'loaded'",
        ],
        cwd=tmp_path,
        env={**os.environ, "PYTHONPATH": str(tmp_path)},
        capture_output=True,
        text=True,
        check=True,
    )

    assert result.stdout == ""
    assert result.stderr == ""
