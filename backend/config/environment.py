"""Load environment variables from the project-root ``.env`` file."""

from __future__ import annotations

import os
import re
from pathlib import Path


_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_VARIABLE_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _parse_line(line: str) -> tuple[str, str] | None:
    candidate = line.strip()
    if not candidate or candidate.startswith("#"):
        return None

    if candidate.startswith("export "):
        candidate = candidate[7:].lstrip()

    if "=" not in candidate:
        return None

    name, value = candidate.split("=", 1)
    name = name.strip()
    if not _VARIABLE_NAME.fullmatch(name):
        return None

    value = value.strip()
    if value.startswith(("\"", "'")):
        quote = value[0]
        closing_quote = value.find(quote, 1)
        if closing_quote == -1:
            return None
        remainder = value[closing_quote + 1 :].strip()
        if remainder and not remainder.startswith("#"):
            return None
        value = value[1:closing_quote]
    else:
        value = re.split(r"\s+#", value, maxsplit=1)[0].rstrip()

    return name, value


def load_environment(env_file: Path | None = None) -> None:
    """Load variables from *env_file*, preserving values already in the process."""

    path = env_file if env_file is not None else _PROJECT_ROOT / ".env"
    if not path.is_file():
        return

    for line in path.read_text(encoding="utf-8").splitlines():
        parsed = _parse_line(line)
        if parsed is not None:
            name, value = parsed
            os.environ.setdefault(name, value)
