"""Deterministic resolution of portfolio identities to market symbols."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import json
from pathlib import Path
from types import MappingProxyType
import unicodedata

from backend.models import PortfolioPosition


REGISTRY_SCHEMA_VERSION = 1
DEFAULT_REGISTRY_PATH = (
    Path(__file__).with_name("data")
    / "jolika_market_symbols.json"
)


def _normalize(value: str | None) -> str:
    text = unicodedata.normalize("NFKD", value or "")
    return " ".join(
        "".join(
            character
            for character in text
            if not unicodedata.combining(character)
        )
        .upper()
        .split()
    )


def _identifier_type(value: str | None) -> str:
    return _normalize(value) or "IDENTIFIER"


def market_symbol_stable_key(
    position: PortfolioPosition,
) -> str | None:
    institution = _normalize(position.institution)
    identifier = _normalize(position.identifier)

    if not institution or not identifier:
        return None

    return (
        f"JOLIKA|{institution}|"
        f"{_identifier_type(position.identifier_type)}:"
        f"{identifier}"
    )


@dataclass(frozen=True)
class MarketSymbolResolution:
    stable_key: str
    market_symbol: str
    status: str
    resolution_source: str
    note: str | None = None


def _require_string(record: dict, field: str) -> str:
    value = record.get(field)

    if not isinstance(value, str) or not value.strip():
        raise ValueError(
            f"Invalid market symbol resolution field: {field}"
        )

    return value


def _optional_string(
    record: dict,
    field: str,
) -> str | None:
    value = record.get(field)

    if value is not None and not isinstance(value, str):
        raise ValueError(
            f"Invalid market symbol resolution field: {field}"
        )

    return value


def load_market_symbol_registry(
    path: Path | str | None = None,
) -> Mapping[str, MarketSymbolResolution]:
    registry_path = (
        Path(path)
        if path is not None
        else DEFAULT_REGISTRY_PATH
    )

    try:
        payload = json.loads(
            registry_path.read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(
            f"Invalid market symbol registry: {exc}"
        ) from exc

    if not isinstance(payload, dict):
        raise ValueError(
            "Market symbol registry root must be an object"
        )

    if (
        payload.get("schema_version")
        != REGISTRY_SCHEMA_VERSION
    ):
        raise ValueError(
            "Unsupported market symbol registry schema_version"
        )

    raw_resolutions = payload.get("resolutions")

    if not isinstance(raw_resolutions, list):
        raise ValueError(
            "Market symbol registry resolutions must be a list"
        )

    resolutions: dict[str, MarketSymbolResolution] = {}

    for raw in raw_resolutions:
        if not isinstance(raw, dict):
            raise ValueError(
                "Market symbol registry entries must be objects"
            )

        stable_key = _require_string(
            raw,
            "stable_key",
        )
        market_symbol = _require_string(
            raw,
            "market_symbol",
        )
        status = _require_string(
            raw,
            "status",
        )
        resolution_source = _require_string(
            raw,
            "resolution_source",
        )
        note = _optional_string(
            raw,
            "note",
        )

        if not stable_key.startswith("JOLIKA|"):
            raise ValueError(
                "Market symbol stable_key must belong to JOLIKA"
            )

        if status != "confirmed":
            raise ValueError(
                "Market symbol resolution status must be confirmed"
            )

        if stable_key in resolutions:
            raise ValueError(
                "Duplicate market symbol stable_key: "
                f"{stable_key}"
            )

        resolutions[stable_key] = MarketSymbolResolution(
            stable_key=stable_key,
            market_symbol=_normalize(market_symbol),
            status=status,
            resolution_source=resolution_source,
            note=note,
        )

    return MappingProxyType(
        {
            key: resolutions[key]
            for key in sorted(resolutions)
        }
    )


def resolve_market_symbol(
    position: PortfolioPosition,
    *,
    registry: (
        Mapping[str, MarketSymbolResolution] | None
    ) = None,
) -> str | None:
    identifier = _normalize(position.identifier)
    identifier_type = _identifier_type(
        position.identifier_type
    )

    if identifier and identifier_type in {
        "TICKER",
        "SYMBOL",
    }:
        return identifier

    stable_key = market_symbol_stable_key(position)

    if stable_key is None:
        return None

    active_registry = (
        load_market_symbol_registry()
        if registry is None
        else registry
    )

    resolution = active_registry.get(stable_key)

    if resolution is None:
        return None

    return resolution.market_symbol
