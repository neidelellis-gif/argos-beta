"""Deterministic, explicit persistence for official JOLIKA portfolio snapshots."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from enum import Enum
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile

from backend.models import EconomicAssetClass, PortfolioOwner, PortfolioPosition
from backend.portfolio_changes import (
    PortfolioChangeSet,
    compare_portfolio_snapshots,
    position_snapshot_identity,
)

PORTFOLIO_SNAPSHOT_SCHEMA_VERSION = 1
DEFAULT_SNAPSHOT_DIRECTORY = Path(__file__).with_name("data") / "portfolio_snapshots"
_SNAPSHOT_FILENAME_RE = re.compile(r"^jolika_\d{8}T\d{6}Z_[0-9a-f]{16}\.json$")
_SNAPSHOT_FIELDS = {
    "schema_version",
    "snapshot_id",
    "owner",
    "captured_at",
    "institutions",
    "source_files",
    "reference_dates",
    "positions",
}
_POSITION_FIELDS = set(PortfolioPosition.__dataclass_fields__)


@dataclass(frozen=True)
class PortfolioSnapshot:
    """One immutable, official JOLIKA portfolio snapshot."""

    schema_version: int
    snapshot_id: str
    owner: PortfolioOwner
    captured_at: datetime
    positions: tuple[PortfolioPosition, ...]
    source_files: tuple[str, ...]
    institutions: tuple[str, ...]
    reference_dates: tuple[str, ...]


def _require_aware(value: datetime, field: str = "captured_at") -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _utc_iso(value: datetime) -> str:
    return _require_aware(value).isoformat(timespec="seconds").replace("+00:00", "Z")


def _safe_source_file(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("source_file must be a non-empty basename")
    if value in {".", ".."} or Path(value).name != value or "/" in value or "\\" in value:
        raise ValueError("source_file must be a basename without directories")
    return value


def _decimal_text(value: Decimal | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ValueError("Snapshot Decimal values must be finite Decimal instances")
    return str(value)


def _position_payload(position: PortfolioPosition) -> dict:
    return {
        "institution": position.institution,
        "owner": position.owner.value,
        "account": position.account,
        "asset_class": position.asset_class,
        "asset_subclass": position.asset_subclass,
        "asset_name": position.asset_name,
        "identifier": position.identifier,
        "identifier_type": position.identifier_type,
        "quantity": _decimal_text(position.quantity),
        "unit_price": _decimal_text(position.unit_price),
        "market_value": _decimal_text(position.market_value),
        "currency": position.currency,
        "portfolio_weight": _decimal_text(position.portfolio_weight),
        "reference_date": None if position.reference_date is None else position.reference_date.isoformat(),
        "source_file": _safe_source_file(position.source_file),
        "economic_asset_class": (
            None if position.economic_asset_class is None else position.economic_asset_class.value
        ),
    }


def _canonical_snapshot_payload(
    *,
    owner: PortfolioOwner,
    captured_at: datetime,
    positions: tuple[PortfolioPosition, ...],
    source_files: tuple[str, ...],
    institutions: tuple[str, ...],
    reference_dates: tuple[str, ...],
) -> dict:
    return {
        "schema_version": PORTFOLIO_SNAPSHOT_SCHEMA_VERSION,
        "owner": owner.value,
        "captured_at": _utc_iso(captured_at),
        "institutions": list(institutions),
        "source_files": list(source_files),
        "reference_dates": list(reference_dates),
        "positions": [_position_payload(position) for position in positions],
    }


def _content_hash(payload: dict) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _snapshot_id(captured_at: datetime, payload: dict) -> str:
    stamp = _require_aware(captured_at).strftime("%Y%m%dT%H%M%SZ")
    return f"JOLIKA|{stamp}|{_content_hash(payload)[:16]}"


def _ordered_positions(
    positions: Iterable[PortfolioPosition],
) -> tuple[PortfolioPosition, ...]:
    indexed: dict[str, PortfolioPosition] = {}
    for position in positions:
        if position.owner is not PortfolioOwner.JOLIKA:
            raise ValueError("JOLIKA snapshot rejects NEI or mixed positions")
        identity = position_snapshot_identity(position)
        if identity.stable_key in indexed:
            raise ValueError(f"Duplicate JOLIKA snapshot stable_key: {identity.stable_key}")
        _safe_source_file(position.source_file)
        _position_payload(position)
        indexed[identity.stable_key] = position
    if not indexed:
        raise ValueError("JOLIKA snapshot cannot be empty")
    return tuple(indexed[key] for key in sorted(indexed))


def build_portfolio_snapshot(
    positions: Iterable[PortfolioPosition],
    *,
    captured_at: datetime,
) -> PortfolioSnapshot:
    """Purely build a deterministic JOLIKA snapshot without writing anything."""
    captured_at_utc = _require_aware(captured_at)
    ordered = _ordered_positions(tuple(positions))
    institutions = tuple(
        sorted({position_snapshot_identity(position).institution for position in ordered})
    )
    source_files = tuple(sorted({_safe_source_file(position.source_file) for position in ordered}))
    reference_dates = tuple(
        sorted(
            {
                position.reference_date.isoformat()
                for position in ordered
                if position.reference_date is not None
            }
        )
    )
    payload = _canonical_snapshot_payload(
        owner=PortfolioOwner.JOLIKA,
        captured_at=captured_at_utc,
        positions=ordered,
        source_files=source_files,
        institutions=institutions,
        reference_dates=reference_dates,
    )
    return PortfolioSnapshot(
        schema_version=PORTFOLIO_SNAPSHOT_SCHEMA_VERSION,
        snapshot_id=_snapshot_id(captured_at_utc, payload),
        owner=PortfolioOwner.JOLIKA,
        captured_at=captured_at_utc,
        positions=ordered,
        source_files=source_files,
        institutions=institutions,
        reference_dates=reference_dates,
    )


def _validated_snapshot(snapshot: PortfolioSnapshot) -> PortfolioSnapshot:
    if not isinstance(snapshot, PortfolioSnapshot):
        raise ValueError("Invalid portfolio snapshot object")
    if snapshot.schema_version != PORTFOLIO_SNAPSHOT_SCHEMA_VERSION:
        raise ValueError("Unsupported portfolio snapshot schema_version")
    if snapshot.owner is not PortfolioOwner.JOLIKA:
        raise ValueError("Portfolio snapshot owner must be JOLIKA")
    rebuilt = build_portfolio_snapshot(snapshot.positions, captured_at=snapshot.captured_at)
    if snapshot.source_files != rebuilt.source_files:
        raise ValueError("Portfolio snapshot source_files conflict with positions")
    if snapshot.institutions != rebuilt.institutions:
        raise ValueError("Portfolio snapshot institutions conflict with positions")
    if snapshot.reference_dates != rebuilt.reference_dates:
        raise ValueError("Portfolio snapshot reference_dates conflict with positions")
    if snapshot.snapshot_id != rebuilt.snapshot_id:
        raise ValueError("Portfolio snapshot_id does not match canonical content")
    return snapshot


def serialize_portfolio_snapshot(snapshot: PortfolioSnapshot) -> str:
    """Serialize a validated snapshot to deterministic loader-compatible JSON."""
    snapshot = _validated_snapshot(snapshot)
    payload = _canonical_snapshot_payload(
        owner=snapshot.owner,
        captured_at=snapshot.captured_at,
        positions=snapshot.positions,
        source_files=snapshot.source_files,
        institutions=snapshot.institutions,
        reference_dates=snapshot.reference_dates,
    )
    payload["snapshot_id"] = snapshot.snapshot_id
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ) + "\n"


def _require_exact_fields(record: dict, expected: set[str], artifact: str) -> None:
    if not isinstance(record, dict):
        raise ValueError(f"{artifact} must be an object")
    missing = expected - set(record)
    unexpected = set(record) - expected
    if missing:
        raise ValueError(f"Missing {artifact} fields: {', '.join(sorted(missing))}")
    if unexpected:
        raise ValueError(f"Unexpected {artifact} fields: {', '.join(sorted(unexpected))}")


def _parse_optional_string(value, field: str) -> str | None:
    if value is not None and not isinstance(value, str):
        raise ValueError(f"Invalid snapshot position field: {field}")
    return value


def _parse_decimal(value, field: str) -> Decimal | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"Invalid snapshot Decimal field: {field}")
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError(f"Invalid snapshot Decimal field: {field}") from exc
    if not parsed.is_finite():
        raise ValueError(f"Invalid snapshot Decimal field: {field}")
    return parsed


def _parse_position(record: dict) -> PortfolioPosition:
    _require_exact_fields(record, _POSITION_FIELDS, "snapshot position")
    try:
        owner = PortfolioOwner(record["owner"])
    except (TypeError, ValueError) as exc:
        raise ValueError("Invalid snapshot position owner") from exc
    if owner is not PortfolioOwner.JOLIKA:
        raise ValueError("Snapshot position owner must be JOLIKA")
    raw_economic = record["economic_asset_class"]
    try:
        economic_class = None if raw_economic is None else EconomicAssetClass(raw_economic)
    except (TypeError, ValueError) as exc:
        raise ValueError("Invalid snapshot economic_asset_class") from exc
    raw_date = record["reference_date"]
    try:
        reference_date = None if raw_date is None else date.fromisoformat(raw_date)
    except (TypeError, ValueError) as exc:
        raise ValueError("Invalid snapshot reference_date") from exc
    institution = record["institution"]
    source_file = record["source_file"]
    if not isinstance(institution, str) or not institution.strip():
        raise ValueError("Invalid snapshot institution")
    if not isinstance(source_file, str):
        raise ValueError("Invalid snapshot source_file")
    return PortfolioPosition(
        institution=institution,
        owner=owner,
        account=_parse_optional_string(record["account"], "account"),
        asset_class=_parse_optional_string(record["asset_class"], "asset_class"),
        asset_subclass=_parse_optional_string(record["asset_subclass"], "asset_subclass"),
        asset_name=_parse_optional_string(record["asset_name"], "asset_name"),
        identifier=_parse_optional_string(record["identifier"], "identifier"),
        identifier_type=_parse_optional_string(record["identifier_type"], "identifier_type"),
        quantity=_parse_decimal(record["quantity"], "quantity"),
        unit_price=_parse_decimal(record["unit_price"], "unit_price"),
        market_value=_parse_decimal(record["market_value"], "market_value"),
        currency=_parse_optional_string(record["currency"], "currency"),
        portfolio_weight=_parse_decimal(record["portfolio_weight"], "portfolio_weight"),
        reference_date=reference_date,
        source_file=_safe_source_file(source_file),
        economic_asset_class=economic_class,
    )


def _parse_captured_at(value) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError("snapshot captured_at must be UTC ISO 8601 with Z")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ValueError("Invalid snapshot captured_at") from exc
    return _require_aware(parsed)


def load_portfolio_snapshot(path: Path | str) -> PortfolioSnapshot:
    """Load and fully validate one snapshot, failing closed on tampering."""
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except OSError:
        raise
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid portfolio snapshot JSON: {exc}") from exc
    _require_exact_fields(payload, _SNAPSHOT_FIELDS, "portfolio snapshot")
    if payload["schema_version"] != PORTFOLIO_SNAPSHOT_SCHEMA_VERSION:
        raise ValueError("Unsupported portfolio snapshot schema_version")
    try:
        owner = PortfolioOwner(payload["owner"])
    except (TypeError, ValueError) as exc:
        raise ValueError("Invalid portfolio snapshot owner") from exc
    if owner is not PortfolioOwner.JOLIKA:
        raise ValueError("Portfolio snapshot owner must be JOLIKA")
    if not isinstance(payload["positions"], list):
        raise ValueError("Portfolio snapshot positions must be a list")
    positions = tuple(_parse_position(record) for record in payload["positions"])
    rebuilt = build_portfolio_snapshot(positions, captured_at=_parse_captured_at(payload["captured_at"]))
    for field in ("institutions", "source_files", "reference_dates"):
        if not isinstance(payload[field], list) or not all(isinstance(item, str) for item in payload[field]):
            raise ValueError(f"Invalid portfolio snapshot {field}")
    if tuple(payload["institutions"]) != rebuilt.institutions:
        raise ValueError("Portfolio snapshot institutions conflict with positions")
    if tuple(payload["source_files"]) != rebuilt.source_files:
        raise ValueError("Portfolio snapshot source_files conflict with positions")
    if tuple(payload["reference_dates"]) != rebuilt.reference_dates:
        raise ValueError("Portfolio snapshot reference_dates conflict with positions")
    if payload["snapshot_id"] != rebuilt.snapshot_id:
        raise ValueError("Portfolio snapshot_id does not match canonical content")
    return rebuilt


def portfolio_snapshot_filename(snapshot: PortfolioSnapshot) -> str:
    snapshot = _validated_snapshot(snapshot)
    stamp = snapshot.captured_at.strftime("%Y%m%dT%H%M%SZ")
    hash_prefix = snapshot.snapshot_id.rsplit("|", 1)[-1]
    return f"jolika_{stamp}_{hash_prefix}.json"


def write_portfolio_snapshot(
    snapshot: PortfolioSnapshot,
    *,
    output_path: Path | str,
    overwrite: bool = False,
) -> None:
    """Explicitly and atomically persist one validated snapshot."""
    destination = Path(output_path)
    text = serialize_portfolio_snapshot(snapshot)
    if destination.exists() and not overwrite:
        raise FileExistsError(f"Output already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{destination.name}.", dir=destination.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
        try:
            directory_fd = os.open(destination.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except OSError:
            pass
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def list_portfolio_snapshots(directory: Path | str) -> tuple[PortfolioSnapshot, ...]:
    """Load every candidate snapshot in deterministic chronological order."""
    root = Path(directory)
    if not root.exists():
        return ()
    if not root.is_dir():
        raise ValueError("Portfolio snapshot path must be a directory")
    snapshots = [
        load_portfolio_snapshot(path)
        for path in sorted(root.iterdir(), key=lambda item: item.name)
        if path.is_file() and _SNAPSHOT_FILENAME_RE.fullmatch(path.name)
    ]
    snapshots.sort(key=lambda snapshot: (snapshot.captured_at, snapshot.snapshot_id))
    return tuple(snapshots)


def select_previous_portfolio_snapshot(
    snapshots: Iterable[PortfolioSnapshot],
    *,
    before: datetime,
) -> PortfolioSnapshot | None:
    """Return the latest unambiguous JOLIKA snapshot strictly before ``before``."""
    cutoff = _require_aware(before, "before")
    materialized = tuple(snapshots)
    seen_times: dict[datetime, str] = {}
    for snapshot in materialized:
        _validated_snapshot(snapshot)
        previous_id = seen_times.get(snapshot.captured_at)
        if previous_id is not None and previous_id != snapshot.snapshot_id:
            raise ValueError("Ambiguous portfolio snapshots share captured_at")
        seen_times[snapshot.captured_at] = snapshot.snapshot_id
    eligible = [snapshot for snapshot in materialized if snapshot.captured_at < cutoff]
    if not eligible:
        return None
    eligible.sort(key=lambda snapshot: (snapshot.captured_at, snapshot.snapshot_id))
    return eligible[-1]


def compare_snapshot_to_positions(
    previous_snapshot: PortfolioSnapshot | None,
    current_positions: Iterable[PortfolioPosition],
) -> PortfolioChangeSet | None:
    """Compare an official baseline to current positions, or return no-baseline."""
    if previous_snapshot is None:
        return None
    _validated_snapshot(previous_snapshot)
    current = tuple(current_positions)
    return compare_portfolio_snapshots(previous_snapshot.positions, current)


def compare_portfolio_snapshot_objects(
    previous_snapshot: PortfolioSnapshot,
    current_snapshot: PortfolioSnapshot,
) -> PortfolioChangeSet:
    """Delegate snapshot-to-snapshot comparison to the FASE 2.4 delta engine."""
    _validated_snapshot(previous_snapshot)
    _validated_snapshot(current_snapshot)
    return compare_portfolio_snapshots(previous_snapshot.positions, current_snapshot.positions)
