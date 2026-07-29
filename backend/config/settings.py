"""Helpers for reading backend settings from the environment."""

import os
from typing import TypeVar, overload


class MissingSettingError(RuntimeError):
    """Raised when a required environment variable is not defined."""


_Default = TypeVar("_Default")


@overload
def get_setting(name: str) -> str | None: ...


@overload
def get_setting(name: str, default: _Default) -> str | _Default: ...


def get_setting(name: str, default: _Default | None = None) -> str | _Default | None:
    """Return an environment variable or ``default`` when it is absent."""

    return os.environ.get(name, default)


def require_setting(name: str) -> str:
    """Return a required environment variable.

    Raises:
        MissingSettingError: If ``name`` is not present in the environment.
    """

    try:
        return os.environ[name]
    except KeyError:
        raise MissingSettingError(
            f"Required environment variable '{name}' is not set."
        ) from None
