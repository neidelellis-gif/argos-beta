"""Deterministic, versioned resolution of unknown JOLIKA assets."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass, replace
import json
from pathlib import Path
from types import MappingProxyType
import unicodedata

from backend.models import EconomicAssetClass, PortfolioOwner, PortfolioPosition


REGISTRY_SCHEMA_VERSION = 1
DEFAULT_REGISTRY_PATH = Path(__file__).with_name("data") / "jolika_asset_resolutions.json"


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


def _name_stable_key(institution: str, asset_name: str | None) -> str:
    return f"JOLIKA|{_normalize(institution)}|NAME:{_normalize(asset_name)}"


@dataclass(frozen=True)
class JolikaAssetResolution:
    """One human-confirmed, version-controlled JOLIKA asset resolution."""

    stable_key: str
    economic_asset_class: EconomicAssetClass
    identifier: str | None
    identifier_type: str | None
    asset_name: str | None
    status: str
    resolution_source: str
    note: str | None = None


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


@dataclass(frozen=True)
class UnresolvedJolikaAssetReviewRecord:
    """Minimal, immutable facts required for human review."""

    stable_key: str
    institution: str
    identifier: str | None
    identifier_type: str | None
    asset_name: str | None
    asset_class: str | None
    currency: str | None
    source_file: str


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


def _require_string(record: dict, field: str) -> str:
    if field not in record or not isinstance(record[field], str):
        raise ValueError(f"Invalid JOLIKA asset resolution field: {field}")
    value = record[field]
    if not value.strip():
        raise ValueError(f"Invalid JOLIKA asset resolution field: {field}")
    return value


def _optional_string(record: dict, field: str) -> str | None:
    value = record.get(field)
    if value is not None and not isinstance(value, str):
        raise ValueError(f"Invalid JOLIKA asset resolution field: {field}")
    return value


def _validate_resolution_identity(resolution: JolikaAssetResolution) -> None:
    stable_key = resolution.stable_key
    if not stable_key.startswith("JOLIKA|"):
        raise ValueError("JOLIKA asset resolution stable_key must belong to JOLIKA")
    parts = stable_key.split("|", 2)
    if len(parts) != 3 or not parts[1] or not parts[2]:
        raise ValueError("Invalid JOLIKA asset resolution stable_key")

    identity = parts[2]
    if identity.startswith("NAME:"):
        expected_name = identity.removeprefix("NAME:")
        if resolution.identifier is not None or resolution.identifier_type is not None:
            raise ValueError("Name resolution cannot declare identifier fields")
        if not expected_name or expected_name != _normalize(resolution.asset_name):
            raise ValueError("JOLIKA asset resolution identity conflicts with stable_key")
        return

    if ":" not in identity:
        raise ValueError("Invalid JOLIKA asset resolution stable_key")
    key_type, key_identifier = identity.split(":", 1)
    if not key_identifier:
        raise ValueError("Invalid JOLIKA asset resolution stable_key")
    if resolution.identifier is None or resolution.identifier_type is None:
        raise ValueError("Identifier resolution requires identifier fields")
    if key_type != _identifier_type(resolution.identifier_type):
        raise ValueError("JOLIKA asset resolution identifier_type conflicts with stable_key")
    if key_identifier != _normalize(resolution.identifier):
        raise ValueError("JOLIKA asset resolution identifier conflicts with stable_key")


def load_jolika_asset_resolution_registry(
    path: Path | str | None = None,
) -> Mapping[str, JolikaAssetResolution]:
    """Load and validate the reviewed registry, failing closed on any defect."""
    registry_path = Path(path) if path is not None else DEFAULT_REGISTRY_PATH
    try:
        payload = json.loads(registry_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Invalid JOLIKA asset resolution registry: {exc}") from exc

    if not isinstance(payload, dict):
        raise ValueError("JOLIKA asset resolution registry root must be an object")
    if payload.get("schema_version") != REGISTRY_SCHEMA_VERSION:
        raise ValueError("Unsupported JOLIKA asset resolution registry schema_version")
    raw_resolutions = payload.get("resolutions")
    if not isinstance(raw_resolutions, list):
        raise ValueError("JOLIKA asset resolution registry resolutions must be a list")

    resolutions: dict[str, JolikaAssetResolution] = {}
    for raw in raw_resolutions:
        if not isinstance(raw, dict):
            raise ValueError("JOLIKA asset resolution registry entries must be objects")
        stable_key = _require_string(raw, "stable_key")
        class_value = _require_string(raw, "economic_asset_class")
        status = _require_string(raw, "status")
        source = _require_string(raw, "resolution_source")
        identifier = _optional_string(raw, "identifier")
        identifier_type = _optional_string(raw, "identifier_type")
        asset_name = _optional_string(raw, "asset_name")
        note = _optional_string(raw, "note")

        try:
            economic_class = EconomicAssetClass(class_value)
        except ValueError as exc:
            raise ValueError(
                f"Invalid JOLIKA economic_asset_class: {class_value}"
            ) from exc
        if status != "confirmed":
            raise ValueError("JOLIKA asset resolution status must be confirmed")
        if stable_key in resolutions:
            raise ValueError(f"Duplicate JOLIKA asset resolution stable_key: {stable_key}")

        resolution = JolikaAssetResolution(
            stable_key=stable_key,
            economic_asset_class=economic_class,
            identifier=identifier,
            identifier_type=identifier_type,
            asset_name=asset_name,
            status=status,
            resolution_source=source,
            note=note,
        )
        _validate_resolution_identity(resolution)
        resolutions[stable_key] = resolution

    return MappingProxyType({key: resolutions[key] for key in sorted(resolutions)})


def _resolve_with_registry(
    position: PortfolioPosition,
    registry: Mapping[str, JolikaAssetResolution],
) -> PortfolioPosition:
    _validate_jolika(position)
    if position.economic_asset_class is not None:
        return position

    resolution = registry.get(_stable_key(position))
    if resolution is None and position.asset_name:
        resolution = registry.get(_name_stable_key(position.institution, position.asset_name))
    if resolution is None:
        return position
    return replace(position, economic_asset_class=resolution.economic_asset_class)


def resolve_jolika_position(
    position: PortfolioPosition,
    *,
    registry: Mapping[str, JolikaAssetResolution] | None = None,
) -> PortfolioPosition:
    """Return a resolved copy, preserving classified and unresolved positions."""
    active_registry = (
        load_jolika_asset_resolution_registry() if registry is None else registry
    )
    return _resolve_with_registry(position, active_registry)


def resolve_jolika_positions(
    positions: Iterable[PortfolioPosition],
    *,
    registry: Mapping[str, JolikaAssetResolution] | None = None,
) -> tuple[PortfolioPosition, ...]:
    """Resolve an exclusively JOLIKA batch without changing its shape or values."""
    batch = tuple(positions)
    if any(position.owner is not PortfolioOwner.JOLIKA for position in batch):
        raise ValueError("JOLIKA asset resolution rejects mixed or non-JOLIKA batches")
    active_registry = (
        load_jolika_asset_resolution_registry() if registry is None else registry
    )
    return tuple(_resolve_with_registry(position, active_registry) for position in batch)


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


def build_unresolved_asset_review_records(
    unresolved_assets: Iterable[UnresolvedJolikaAsset],
) -> tuple[UnresolvedJolikaAssetReviewRecord, ...]:
    """Build deterministic, minimal records for human review."""
    records: dict[str, UnresolvedJolikaAssetReviewRecord] = {}
    for asset in unresolved_assets:
        if not asset.stable_key.startswith("JOLIKA|"):
            raise ValueError("JOLIKA unresolved review rejects non-JOLIKA records")
        records.setdefault(
            asset.stable_key,
            UnresolvedJolikaAssetReviewRecord(
                stable_key=asset.stable_key,
                institution=asset.institution,
                identifier=asset.identifier,
                identifier_type=asset.identifier_type,
                asset_name=asset.asset_name,
                asset_class=asset.asset_class,
                currency=asset.currency,
                source_file=asset.source_file,
            ),
        )
    return tuple(records[key] for key in sorted(records))


def export_unresolved_jolika_assets(
    unresolved_assets: Iterable[UnresolvedJolikaAsset],
    *,
    output_path: Path | str | None = None,
) -> str:
    """Serialize unresolved review facts deterministically, with no auto-approval."""
    records = build_unresolved_asset_review_records(unresolved_assets)
    payload = {
        "schema_version": REGISTRY_SCHEMA_VERSION,
        "unresolved_assets": [asdict(record) for record in records],
    }
    text = json.dumps(
        payload,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ) + "\n"
    if output_path is not None:
        Path(output_path).write_text(text, encoding="utf-8")
    return text
