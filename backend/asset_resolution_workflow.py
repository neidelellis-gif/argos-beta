"""Controlled human-review workflow for JOLIKA asset resolutions.

This module is deliberately separate from normal portfolio imports. It validates
review artifacts and builds proposed registry files, but never mutates the
versioned registry automatically.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import tempfile
from types import MappingProxyType

from backend.asset_resolution import JolikaAssetResolution, UnresolvedJolikaAsset
from backend.models import EconomicAssetClass

DECISIONS_SCHEMA_VERSION = 1
UNRESOLVED_SCHEMA_VERSION = 1
REGISTRY_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class JolikaAssetResolutionDecision:
    """Minimal explicit classification decision supplied by a human operator."""

    stable_key: str
    economic_asset_class: EconomicAssetClass
    status: str
    resolution_source: str
    note: str | None = None


def _load_json_object(path: Path | str, artifact: str) -> dict:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Invalid JOLIKA {artifact}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"JOLIKA {artifact} root must be an object")
    return payload


def _require_exact_fields(record: dict, expected: set[str], artifact: str) -> None:
    unexpected = set(record) - expected
    missing = expected - {"note"} - set(record)
    if unexpected:
        raise ValueError(
            f"Unexpected JOLIKA {artifact} fields: {', '.join(sorted(unexpected))}"
        )
    if missing:
        raise ValueError(f"Missing JOLIKA {artifact} fields: {', '.join(sorted(missing))}")


def _required_string(record: dict, field: str, artifact: str) -> str:
    value = record.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Invalid JOLIKA {artifact} field: {field}")
    return value


def _optional_string(record: dict, field: str, artifact: str) -> str | None:
    value = record.get(field)
    if value is not None and not isinstance(value, str):
        raise ValueError(f"Invalid JOLIKA {artifact} field: {field}")
    return value


def _split_stable_key(stable_key: str) -> tuple[str, str]:
    if not stable_key.startswith("JOLIKA|"):
        raise ValueError("JOLIKA stable_key must belong to JOLIKA")
    parts = stable_key.split("|", 2)
    if len(parts) != 3 or not parts[1] or not parts[2] or ":" not in parts[2]:
        raise ValueError("Invalid JOLIKA stable_key")
    return parts[1], parts[2]


def load_jolika_asset_resolution_decisions(
    path: Path | str,
) -> tuple[JolikaAssetResolutionDecision, ...]:
    payload = _load_json_object(path, "asset resolution decisions")
    _require_exact_fields(payload, {"schema_version", "decisions"}, "decisions root")
    if payload.get("schema_version") != DECISIONS_SCHEMA_VERSION:
        raise ValueError("Unsupported JOLIKA asset resolution decisions schema_version")
    raw_decisions = payload.get("decisions")
    if not isinstance(raw_decisions, list):
        raise ValueError("JOLIKA asset resolution decisions must be a list")

    expected = {
        "stable_key",
        "economic_asset_class",
        "status",
        "resolution_source",
        "note",
    }
    decisions: dict[str, JolikaAssetResolutionDecision] = {}
    for raw in raw_decisions:
        if not isinstance(raw, dict):
            raise ValueError("JOLIKA asset resolution decision entries must be objects")
        _require_exact_fields(raw, expected, "decision")
        stable_key = _required_string(raw, "stable_key", "decision")
        _split_stable_key(stable_key)
        try:
            economic_class = EconomicAssetClass(
                _required_string(raw, "economic_asset_class", "decision")
            )
        except ValueError as exc:
            raise ValueError("Invalid JOLIKA decision economic_asset_class") from exc
        status = _required_string(raw, "status", "decision")
        source = _required_string(raw, "resolution_source", "decision")
        if status != "confirmed":
            raise ValueError("JOLIKA decision status must be confirmed")
        if source != "human_review":
            raise ValueError("JOLIKA decision resolution_source must be human_review")
        if stable_key in decisions:
            raise ValueError(f"Duplicate JOLIKA decision stable_key: {stable_key}")
        decisions[stable_key] = JolikaAssetResolutionDecision(
            stable_key=stable_key,
            economic_asset_class=economic_class,
            status=status,
            resolution_source=source,
            note=_optional_string(raw, "note", "decision"),
        )
    return tuple(decisions[key] for key in sorted(decisions))


def _validate_unresolved_identity(asset: UnresolvedJolikaAsset) -> None:
    institution, identity = _split_stable_key(asset.stable_key)
    if institution != " ".join(asset.institution.upper().split()):
        raise ValueError("JOLIKA unresolved asset identity conflicts with stable_key")
    if identity.startswith("NAME:"):
        if asset.identifier is not None or asset.identifier_type is not None:
            raise ValueError("Name unresolved identity cannot declare identifier fields")
    else:
        if asset.identifier is None or asset.identifier_type is None:
            raise ValueError("Identifier unresolved identity requires identifier fields")


def load_unresolved_jolika_assets(path: Path | str) -> tuple[UnresolvedJolikaAsset, ...]:
    payload = _load_json_object(path, "unresolved asset review")
    _require_exact_fields(
        payload,
        {"schema_version", "unresolved_assets"},
        "unresolved review root",
    )
    if payload.get("schema_version") != UNRESOLVED_SCHEMA_VERSION:
        raise ValueError("Unsupported JOLIKA unresolved review schema_version")
    raw_assets = payload.get("unresolved_assets")
    if not isinstance(raw_assets, list):
        raise ValueError("JOLIKA unresolved_assets must be a list")

    expected = {
        "stable_key",
        "institution",
        "identifier",
        "identifier_type",
        "asset_name",
        "asset_class",
        "currency",
        "source_file",
    }
    assets: dict[str, UnresolvedJolikaAsset] = {}
    for raw in raw_assets:
        if not isinstance(raw, dict):
            raise ValueError("JOLIKA unresolved asset entries must be objects")
        _require_exact_fields(raw, expected, "unresolved asset")
        asset = UnresolvedJolikaAsset(
            institution=_required_string(raw, "institution", "unresolved asset"),
            identifier=_optional_string(raw, "identifier", "unresolved asset"),
            identifier_type=_optional_string(raw, "identifier_type", "unresolved asset"),
            asset_name=_optional_string(raw, "asset_name", "unresolved asset"),
            asset_class=_optional_string(raw, "asset_class", "unresolved asset"),
            currency=_optional_string(raw, "currency", "unresolved asset"),
            source_file=_required_string(raw, "source_file", "unresolved asset"),
            stable_key=_required_string(raw, "stable_key", "unresolved asset"),
        )
        _validate_unresolved_identity(asset)
        if asset.stable_key in assets:
            raise ValueError(f"Duplicate JOLIKA unresolved stable_key: {asset.stable_key}")
        assets[asset.stable_key] = asset
    return tuple(assets[key] for key in sorted(assets))


def _resolution_from_decision(
    asset: UnresolvedJolikaAsset,
    decision: JolikaAssetResolutionDecision,
) -> JolikaAssetResolution:
    return JolikaAssetResolution(
        stable_key=asset.stable_key,
        economic_asset_class=decision.economic_asset_class,
        identifier=asset.identifier,
        identifier_type=asset.identifier_type,
        asset_name=asset.asset_name,
        status=decision.status,
        resolution_source=decision.resolution_source,
        note=decision.note,
    )


def validate_jolika_resolution_decisions(
    unresolved_assets: Iterable[UnresolvedJolikaAsset],
    decisions: Iterable[JolikaAssetResolutionDecision],
    existing_registry: Mapping[str, JolikaAssetResolution],
) -> None:
    assets: dict[str, UnresolvedJolikaAsset] = {}
    for asset in unresolved_assets:
        _validate_unresolved_identity(asset)
        if asset.stable_key in assets:
            raise ValueError(f"Duplicate JOLIKA unresolved stable_key: {asset.stable_key}")
        assets[asset.stable_key] = asset

    for key, resolution in existing_registry.items():
        _split_stable_key(key)
        if key != resolution.stable_key:
            raise ValueError("JOLIKA registry key conflicts with resolution stable_key")

    seen: set[str] = set()
    for decision in decisions:
        _split_stable_key(decision.stable_key)
        if decision.status != "confirmed":
            raise ValueError("JOLIKA decision status must be confirmed")
        if decision.resolution_source != "human_review":
            raise ValueError("JOLIKA decision resolution_source must be human_review")
        if decision.stable_key in seen:
            raise ValueError(f"Duplicate JOLIKA decision stable_key: {decision.stable_key}")
        seen.add(decision.stable_key)
        asset = assets.get(decision.stable_key)
        if asset is None:
            raise ValueError(f"Stale or unknown JOLIKA decision: {decision.stable_key}")
        proposed = _resolution_from_decision(asset, decision)
        current = existing_registry.get(decision.stable_key)
        if current is not None and current != proposed:
            raise ValueError(f"Conflicting JOLIKA resolution: {decision.stable_key}")


def build_updated_jolika_asset_resolution_registry(
    unresolved_assets: Iterable[UnresolvedJolikaAsset],
    decisions: Iterable[JolikaAssetResolutionDecision],
    existing_registry: Mapping[str, JolikaAssetResolution],
) -> Mapping[str, JolikaAssetResolution]:
    assets_tuple = tuple(unresolved_assets)
    decisions_tuple = tuple(decisions)
    validate_jolika_resolution_decisions(
        assets_tuple,
        decisions_tuple,
        existing_registry,
    )
    assets = {asset.stable_key: asset for asset in assets_tuple}
    updated = dict(existing_registry)
    for decision in decisions_tuple:
        updated.setdefault(
            decision.stable_key,
            _resolution_from_decision(assets[decision.stable_key], decision),
        )
    return MappingProxyType({key: updated[key] for key in sorted(updated)})


def serialize_jolika_asset_resolution_registry(
    registry: Mapping[str, JolikaAssetResolution],
) -> str:
    validate_jolika_resolution_decisions((), (), registry)
    payload = {
        "schema_version": REGISTRY_SCHEMA_VERSION,
        "resolutions": [asdict(registry[key]) for key in sorted(registry)],
    }
    for record in payload["resolutions"]:
        record["economic_asset_class"] = record["economic_asset_class"].value
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def write_jolika_asset_resolution_registry(
    registry: Mapping[str, JolikaAssetResolution],
    *,
    output_path: Path | str,
    overwrite: bool = False,
) -> None:
    destination = Path(output_path)
    text = serialize_jolika_asset_resolution_registry(registry)
    if destination.exists() and not overwrite:
        raise FileExistsError(f"Output already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(
        prefix=f".{destination.name}.",
        dir=destination.parent,
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise
