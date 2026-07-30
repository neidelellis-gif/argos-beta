"""Safe serializers for decision profiles and public decision contexts."""

from dataclasses import asdict
from datetime import date
from enum import Enum
from typing import Any

from backend.decision_context import DecisionProfile

PUBLIC_CONTEXT_FIELDS = (
    "id", "context_type", "relevance_level", "title", "summary",
    "related_assets", "context_factors", "limitations",
)


def _plain(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, tuple):
        return [_plain(item) for item in value]
    if isinstance(value, dict):
        return {key: _plain(item) for key, item in value.items()}
    return value


def serialize_decision_profile(profile: DecisionProfile) -> dict[str, object]:
    return _plain(asdict(profile))


def serialize_public_context(context: dict[str, object]) -> dict[str, object]:
    return {field: _plain(context[field]) for field in PUBLIC_CONTEXT_FIELDS}
