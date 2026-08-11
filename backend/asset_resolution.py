"""Deterministic, versioned resolution of unknown JOLIKA assets."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, replace
from types import MappingProxyType
import unicodedata

from backend.models import EconomicAssetClass, PortfolioOwner, PortfolioPosition


def _normalize(value: str | None) -> str:
    text = unicodedata.normalize("NFKD", value or "")
    return " ".join(
        "".join(character for character in text if not unicodedata.combining(character))
        .upper()
        .split()
    )


def _identifier_type(value: str | None) -> str:
    normalized = _normalize(value)
    if normalized in {"ISIN", "CUSIP", "TICKER"}:
        return normalized
    return normalized or "IDENTIFIER"


# Deliberately small, reviewed registry. Add entries only after human confirmation.
_KNOWN_IDENTIFIER_RESOLUTIONS = MappingProxyType(
    {
        ("ISIN", "US0000000099"): EconomicAssetClass.FIXED_INCOME,
        ("TICKER", "ARGOS-GOLD"): EconomicAssetClass.GOLD_AND_COMMODITIES,
    }
)

_KNOWN_NAME_RESOLUTIONS = MappingProxyType(
    {
        "ARGOS CONFIRMED EQUITY FUND": EconomicAssetClass.FUNDS_STRATEGIES,
    }
)


@dataclass(frozen=True)
class UnresolvedJolikaAsset:
    """Immutable audit record for a JOLIKA asset awaiting confirmation."""

    institution: str
    identifier: str | None
    identifier_type: str | None
    asset_name: str | None
    asset_class: str | None
    currency: str | None
    source_file: str
    stable_key: str


def _stable_key(position: PortfolioPosition) -> str:
    institution = _normalize(position.institution)
    identifier = _normalize(position.identifier)
    if identifier:
        identity = f"{_identifier_type(position.identifier_type)}:{identifier}"
    else:
        identity = f"NAME:{_normalize(position.asset_name)}"
    return f"JOLIKA|{institution}|{identity}"


def _validate_jolika(position: PortfolioPosition) -> None:
    if position.owner is not PortfolioOwner.JOLIKA:
        raise ValueError("JOLIKA asset resolution rejects non-JOLIKA positions")


def resolve_jolika_position(position: PortfolioPosition) -> PortfolioPosition:
    """Return a resolved copy, preserving classified and unresolved positions."""
    _validate_jolika(position)
    if position.economic_asset_class is not None:
        return position

    identifier = _normalize(position.identifier)
    resolution = None
    if identifier:
        resolution = _KNOWN_IDENTIFIER_RESOLUTIONS.get(
            (_identifier_type(position.identifier_type), identifier)
        )
    if resolution is None:
        resolution = _KNOWN_NAME_RESOLUTIONS.get(_normalize(position.asset_name))
    if resolution is None:
        return position
    return replace(position, economic_asset_class=resolution)


def resolve_jolika_positions(
    positions: Iterable[PortfolioPosition],
) -> tuple[PortfolioPosition, ...]:
    """Resolve an exclusively JOLIKA batch without changing its shape or values."""
    batch = tuple(positions)
    if any(position.owner is not PortfolioOwner.JOLIKA for position in batch):
        raise ValueError("JOLIKA asset resolution rejects mixed or non-JOLIKA batches")
    return tuple(resolve_jolika_position(position) for position in batch)


def collect_unresolved_jolika_assets(
    positions: Iterable[PortfolioPosition],
) -> tuple[UnresolvedJolikaAsset, ...]:
    """Collect one deterministic audit record per unresolved stable asset key."""
    batch = tuple(positions)
    if any(position.owner is not PortfolioOwner.JOLIKA for position in batch):
        raise ValueError("JOLIKA asset resolution rejects mixed or non-JOLIKA batches")

    unresolved: dict[str, UnresolvedJolikaAsset] = {}
    candidates = sorted(
        (position for position in batch if position.economic_asset_class is None),
        key=lambda position: (
            _stable_key(position),
            position.source_file,
            _normalize(position.asset_name),
        ),
    )
    for position in candidates:
        stable_key = _stable_key(position)
        unresolved.setdefault(
            stable_key,
            UnresolvedJolikaAsset(
                institution=position.institution,
                identifier=position.identifier,
                identifier_type=position.identifier_type,
                asset_name=position.asset_name,
                asset_class=position.asset_class,
                currency=position.currency,
                source_file=position.source_file,
                stable_key=stable_key,
            ),
        )
    return tuple(unresolved[key] for key in sorted(unresolved))
