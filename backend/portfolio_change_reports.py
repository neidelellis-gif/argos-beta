"""Deterministic historical change reports for official JOLIKA snapshots."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, fields
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
    PositionChangeType,
    PositionDelta,
    compare_portfolio_snapshots,
)
from backend.portfolio_snapshots import (
    PortfolioSnapshot,
    compare_portfolio_snapshot_objects,
)


PORTFOLIO_CHANGE_REPORT_SCHEMA_VERSION = 1
DEFAULT_PORTFOLIO_CHANGE_REPORT_DIRECTORY = (
    Path(__file__).with_name("data") / "portfolio_change_reports"
)

_REPORT_FIELDS = {
    "schema_version", "report_id", "owner", "previous_snapshot_id",
    "current_snapshot_id", "previous_captured_at", "current_captured_at",
    "generated_at", "previous_position_count", "current_position_count",
    "summary", "change_set",
}
_SUMMARY_FIELDS = {
    "added", "removed", "unchanged", "quantity_increased",
    "quantity_decreased", "account_changed", "market_value_changed",
    "unit_price_changed", "economic_class_changed",
    "legacy_asset_class_changed", "multiple_changes", "position_flow_unknown",
}
_DELTA_FIELDS = {
    "stable_key", "institution", "identifier", "identifier_type", "asset_name",
    "previous_position", "current_position", "change_types", "quantity_delta",
    "market_value_delta", "unit_price_delta", "previous_account",
    "current_account", "previous_economic_asset_class",
    "current_economic_asset_class", "previous_asset_class", "current_asset_class",
    "previous_instance_key", "current_instance_key", "position_flow_unknown",
}
_POSITION_FIELDS = {field.name for field in fields(PortfolioPosition)}
_FILENAME_RE = re.compile(
    r"^jolika_change_\d{8}T\d{6}Z_\d{8}T\d{6}Z_[0-9a-f]{16}\.json$"
)


@dataclass(frozen=True)
class PortfolioChangeSummary:
    added: int
    removed: int
    unchanged: int
    quantity_increased: int
    quantity_decreased: int
    account_changed: int
    market_value_changed: int
    unit_price_changed: int
    economic_class_changed: int
    legacy_asset_class_changed: int
    multiple_changes: int
    position_flow_unknown: int


@dataclass(frozen=True)
class PortfolioChangeReport:
    schema_version: int
    report_id: str
    owner: PortfolioOwner
    previous_snapshot_id: str
    current_snapshot_id: str
    previous_captured_at: datetime
    current_captured_at: datetime
    generated_at: datetime
    previous_position_count: int
    current_position_count: int
    summary: PortfolioChangeSummary
    change_set: PortfolioChangeSet


def _aware_utc(value: datetime, field: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _utc_iso(value: datetime) -> str:
    return _aware_utc(value, "timestamp").isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def _exact(record: object, expected: set[str], artifact: str) -> dict:
    if not isinstance(record, dict):
        raise ValueError(f"{artifact} must be an object")
    missing, extra = expected - set(record), set(record) - expected
    if missing:
        raise ValueError(f"Missing {artifact} fields: {', '.join(sorted(missing))}")
    if extra:
        raise ValueError(f"Unexpected {artifact} fields: {', '.join(sorted(extra))}")
    return record


def _decimal_text(value: Decimal | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ValueError("Change report Decimal values must be finite Decimals")
    return str(value)


def _position_payload(position: PortfolioPosition | None) -> dict | None:
    if position is None:
        return None
    payload: dict[str, object] = {}
    for field in fields(position):
        value = getattr(position, field.name)
        if isinstance(value, Decimal):
            value = _decimal_text(value)
        elif isinstance(value, Enum):
            value = value.value
        elif isinstance(value, date):
            value = value.isoformat()
        payload[field.name] = value
    return payload


def _delta_payload(delta: PositionDelta) -> dict:
    return {
        "stable_key": delta.stable_key,
        "institution": delta.institution,
        "identifier": delta.identifier,
        "identifier_type": delta.identifier_type,
        "asset_name": delta.asset_name,
        "previous_position": _position_payload(delta.previous_position),
        "current_position": _position_payload(delta.current_position),
        "change_types": [kind.value for kind in delta.change_types],
        "quantity_delta": _decimal_text(delta.quantity_delta),
        "market_value_delta": _decimal_text(delta.market_value_delta),
        "unit_price_delta": _decimal_text(delta.unit_price_delta),
        "previous_account": delta.previous_account,
        "current_account": delta.current_account,
        "previous_economic_asset_class": (
            None if delta.previous_economic_asset_class is None
            else delta.previous_economic_asset_class.value
        ),
        "current_economic_asset_class": (
            None if delta.current_economic_asset_class is None
            else delta.current_economic_asset_class.value
        ),
        "previous_asset_class": delta.previous_asset_class,
        "current_asset_class": delta.current_asset_class,
        "previous_instance_key": delta.previous_instance_key,
        "current_instance_key": delta.current_instance_key,
        "position_flow_unknown": delta.position_flow_unknown,
    }


def _summary(change_set: PortfolioChangeSet) -> PortfolioChangeSummary:
    def count(kind: PositionChangeType) -> int:
        return sum(kind in delta.change_types for delta in change_set.deltas)
    return PortfolioChangeSummary(
        added=count(PositionChangeType.ADDED),
        removed=count(PositionChangeType.REMOVED),
        unchanged=count(PositionChangeType.UNCHANGED),
        quantity_increased=count(PositionChangeType.QUANTITY_INCREASED),
        quantity_decreased=count(PositionChangeType.QUANTITY_DECREASED),
        account_changed=count(PositionChangeType.ACCOUNT_CHANGED),
        market_value_changed=count(PositionChangeType.MARKET_VALUE_CHANGED),
        unit_price_changed=count(PositionChangeType.UNIT_PRICE_CHANGED),
        economic_class_changed=count(PositionChangeType.ECONOMIC_CLASS_CHANGED),
        legacy_asset_class_changed=count(PositionChangeType.LEGACY_ASSET_CLASS_CHANGED),
        multiple_changes=count(PositionChangeType.MULTIPLE_CHANGES),
        position_flow_unknown=sum(delta.position_flow_unknown for delta in change_set.deltas),
    )


def _summary_payload(summary: PortfolioChangeSummary) -> dict[str, int]:
    return {field.name: getattr(summary, field.name) for field in fields(summary)}


def _canonical_payload(report: PortfolioChangeReport) -> dict:
    return {
        "schema_version": report.schema_version,
        "owner": report.owner.value,
        "previous_snapshot_id": report.previous_snapshot_id,
        "current_snapshot_id": report.current_snapshot_id,
        "previous_captured_at": _utc_iso(report.previous_captured_at),
        "current_captured_at": _utc_iso(report.current_captured_at),
        "generated_at": _utc_iso(report.generated_at),
        "previous_position_count": report.previous_position_count,
        "current_position_count": report.current_position_count,
        "summary": _summary_payload(report.summary),
        "change_set": {"deltas": [_delta_payload(delta) for delta in report.change_set.deltas]},
    }


def _hash(payload: dict) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _report_id(previous: datetime, current: datetime, payload: dict) -> str:
    return f"JOLIKA|CHANGE|{_utc_iso(previous)}|{_utc_iso(current)}|{_hash(payload)[:16]}"


def build_portfolio_change_report(
    previous_snapshot: PortfolioSnapshot,
    current_snapshot: PortfolioSnapshot,
    *,
    generated_at: datetime,
) -> PortfolioChangeReport:
    generated = _aware_utc(generated_at, "generated_at").replace(microsecond=0)
    if previous_snapshot.owner is not PortfolioOwner.JOLIKA or current_snapshot.owner is not PortfolioOwner.JOLIKA:
        raise ValueError("Portfolio change reports accept only JOLIKA snapshots")
    if previous_snapshot.captured_at >= current_snapshot.captured_at:
        raise ValueError("previous.captured_at must be before current.captured_at")
    if generated < current_snapshot.captured_at:
        raise ValueError("generated_at must not be before current.captured_at")
    compared = compare_portfolio_snapshot_objects(previous_snapshot, current_snapshot)
    change_set = PortfolioChangeSet(compared.deltas)
    report = PortfolioChangeReport(
        schema_version=PORTFOLIO_CHANGE_REPORT_SCHEMA_VERSION,
        report_id="",
        owner=PortfolioOwner.JOLIKA,
        previous_snapshot_id=previous_snapshot.snapshot_id,
        current_snapshot_id=current_snapshot.snapshot_id,
        previous_captured_at=_aware_utc(previous_snapshot.captured_at, "previous_captured_at"),
        current_captured_at=_aware_utc(current_snapshot.captured_at, "current_captured_at"),
        generated_at=generated,
        previous_position_count=len(previous_snapshot.positions),
        current_position_count=len(current_snapshot.positions),
        summary=_summary(change_set),
        change_set=change_set,
    )
    return PortfolioChangeReport(**{**report.__dict__, "report_id": _report_id(
        report.previous_captured_at, report.current_captured_at, _canonical_payload(report)
    )})


def _validated_report(report: PortfolioChangeReport) -> PortfolioChangeReport:
    if not isinstance(report, PortfolioChangeReport):
        raise ValueError("Invalid portfolio change report object")
    if report.schema_version != PORTFOLIO_CHANGE_REPORT_SCHEMA_VERSION:
        raise ValueError("Unsupported portfolio change report schema_version")
    if report.owner is not PortfolioOwner.JOLIKA:
        raise ValueError("Portfolio change report owner must be JOLIKA")
    previous = _aware_utc(report.previous_captured_at, "previous_captured_at")
    current = _aware_utc(report.current_captured_at, "current_captured_at")
    generated = _aware_utc(report.generated_at, "generated_at")
    if any(value.microsecond for value in (previous, current, generated)):
        raise ValueError("Portfolio change report timestamps must use whole seconds")
    if previous >= current or generated < current:
        raise ValueError("Invalid portfolio change report timestamp order")
    if not isinstance(report.previous_position_count, int) or isinstance(report.previous_position_count, bool) or report.previous_position_count < 0:
        raise ValueError("Invalid previous_position_count")
    if not isinstance(report.current_position_count, int) or isinstance(report.current_position_count, bool) or report.current_position_count < 0:
        raise ValueError("Invalid current_position_count")
    if report.summary != _summary(report.change_set):
        raise ValueError("Portfolio change report summary does not match change_set")
    previous_positions = tuple(
        delta.previous_position
        for delta in report.change_set.deltas
        if delta.previous_position is not None
    )
    current_positions = tuple(
        delta.current_position
        for delta in report.change_set.deltas
        if delta.current_position is not None
    )
    recalculated = compare_portfolio_snapshots(previous_positions, current_positions)
    if report.change_set.deltas != recalculated.deltas:
        raise ValueError("Portfolio change report change_set is not canonical")
    previous_count = sum(delta.previous_position is not None for delta in report.change_set.deltas)
    current_count = sum(delta.current_position is not None for delta in report.change_set.deltas)
    if (report.previous_position_count, report.current_position_count) != (previous_count, current_count):
        raise ValueError("Portfolio change report position counts do not match change_set")
    expected = _report_id(previous, current, _canonical_payload(report))
    if report.report_id != expected:
        raise ValueError("Portfolio change report_id does not match canonical content")
    return report


def serialize_portfolio_change_report(report: PortfolioChangeReport) -> str:
    report = _validated_report(report)
    payload = _canonical_payload(report)
    payload["report_id"] = report.report_id
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"


def _parse_timestamp(value: object, field: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError(f"{field} must be UTC ISO 8601 with Z")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ValueError(f"Invalid {field}") from exc
    return _aware_utc(parsed, field)


def _parse_decimal(value: object, field: str) -> Decimal | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"Invalid Decimal field: {field}")
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError(f"Invalid Decimal field: {field}") from exc
    if not parsed.is_finite():
        raise ValueError(f"Invalid Decimal field: {field}")
    return parsed


def _optional_string(value: object, field: str) -> str | None:
    if value is not None and not isinstance(value, str):
        raise ValueError(f"Invalid string field: {field}")
    return value


def _parse_position(value: object, field: str) -> PortfolioPosition | None:
    if value is None:
        return None
    record = _exact(value, _POSITION_FIELDS, field)
    try:
        owner = PortfolioOwner(record["owner"])
        economic = None if record["economic_asset_class"] is None else EconomicAssetClass(record["economic_asset_class"])
        reference = None if record["reference_date"] is None else date.fromisoformat(record["reference_date"])
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid {field} enum or date") from exc
    if owner is not PortfolioOwner.JOLIKA:
        raise ValueError(f"{field} owner must be JOLIKA")
    if not isinstance(record["institution"], str) or not record["institution"].strip():
        raise ValueError(f"Invalid {field} institution")
    if not isinstance(record["source_file"], str):
        raise ValueError(f"Invalid {field} source_file")
    return PortfolioPosition(
        institution=record["institution"], owner=owner,
        account=_optional_string(record["account"], "account"),
        asset_class=_optional_string(record["asset_class"], "asset_class"),
        asset_subclass=_optional_string(record["asset_subclass"], "asset_subclass"),
        asset_name=_optional_string(record["asset_name"], "asset_name"),
        identifier=_optional_string(record["identifier"], "identifier"),
        identifier_type=_optional_string(record["identifier_type"], "identifier_type"),
        quantity=_parse_decimal(record["quantity"], "quantity"),
        unit_price=_parse_decimal(record["unit_price"], "unit_price"),
        market_value=_parse_decimal(record["market_value"], "market_value"),
        currency=_optional_string(record["currency"], "currency"),
        portfolio_weight=_parse_decimal(record["portfolio_weight"], "portfolio_weight"),
        reference_date=reference, source_file=record["source_file"],
        economic_asset_class=economic,
    )


def _parse_delta(value: object) -> PositionDelta:
    record = _exact(value, _DELTA_FIELDS, "position delta")
    string_fields = ("stable_key", "institution")
    if any(not isinstance(record[name], str) or not record[name] for name in string_fields):
        raise ValueError("Invalid position delta identity")
    if not isinstance(record["change_types"], list) or not record["change_types"]:
        raise ValueError("Invalid position delta change_types")
    try:
        change_types = tuple(PositionChangeType(item) for item in record["change_types"])
        previous_economic = None if record["previous_economic_asset_class"] is None else EconomicAssetClass(record["previous_economic_asset_class"])
        current_economic = None if record["current_economic_asset_class"] is None else EconomicAssetClass(record["current_economic_asset_class"])
    except (TypeError, ValueError) as exc:
        raise ValueError("Invalid position delta enum") from exc
    if len(set(change_types)) != len(change_types):
        raise ValueError("Duplicate position delta change_type")
    flow_unknown = record["position_flow_unknown"]
    if not isinstance(flow_unknown, bool):
        raise ValueError("Invalid position_flow_unknown")
    optional = ("identifier", "identifier_type", "asset_name", "previous_account",
                "current_account", "previous_asset_class", "current_asset_class",
                "previous_instance_key", "current_instance_key")
    values = {name: _optional_string(record[name], name) for name in optional}
    return PositionDelta(
        stable_key=record["stable_key"], institution=record["institution"],
        identifier=values["identifier"], identifier_type=values["identifier_type"],
        asset_name=values["asset_name"],
        previous_position=_parse_position(record["previous_position"], "previous_position"),
        current_position=_parse_position(record["current_position"], "current_position"),
        change_types=change_types,
        quantity_delta=_parse_decimal(record["quantity_delta"], "quantity_delta"),
        market_value_delta=_parse_decimal(record["market_value_delta"], "market_value_delta"),
        unit_price_delta=_parse_decimal(record["unit_price_delta"], "unit_price_delta"),
        previous_account=values["previous_account"], current_account=values["current_account"],
        previous_economic_asset_class=previous_economic,
        current_economic_asset_class=current_economic,
        previous_asset_class=values["previous_asset_class"], current_asset_class=values["current_asset_class"],
        previous_instance_key=values["previous_instance_key"], current_instance_key=values["current_instance_key"],
        position_flow_unknown=flow_unknown,
    )


def load_portfolio_change_report(path: Path | str) -> PortfolioChangeReport:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid portfolio change report JSON: {exc}") from exc
    record = _exact(payload, _REPORT_FIELDS, "portfolio change report")
    if record["schema_version"] != PORTFOLIO_CHANGE_REPORT_SCHEMA_VERSION:
        raise ValueError("Unsupported portfolio change report schema_version")
    try:
        owner = PortfolioOwner(record["owner"])
    except (TypeError, ValueError) as exc:
        raise ValueError("Invalid portfolio change report owner") from exc
    summary_record = _exact(record["summary"], _SUMMARY_FIELDS, "change summary")
    if any(not isinstance(value, int) or isinstance(value, bool) or value < 0 for value in summary_record.values()):
        raise ValueError("Change summary counts must be non-negative integers")
    change_record = _exact(record["change_set"], {"deltas"}, "change_set")
    if not isinstance(change_record["deltas"], list):
        raise ValueError("change_set deltas must be a list")
    for name in ("report_id", "previous_snapshot_id", "current_snapshot_id"):
        if not isinstance(record[name], str) or not record[name]:
            raise ValueError(f"Invalid {name}")
    report = PortfolioChangeReport(
        schema_version=record["schema_version"], report_id=record["report_id"], owner=owner,
        previous_snapshot_id=record["previous_snapshot_id"], current_snapshot_id=record["current_snapshot_id"],
        previous_captured_at=_parse_timestamp(record["previous_captured_at"], "previous_captured_at"),
        current_captured_at=_parse_timestamp(record["current_captured_at"], "current_captured_at"),
        generated_at=_parse_timestamp(record["generated_at"], "generated_at"),
        previous_position_count=record["previous_position_count"], current_position_count=record["current_position_count"],
        summary=PortfolioChangeSummary(**summary_record),
        change_set=PortfolioChangeSet(tuple(_parse_delta(item) for item in change_record["deltas"])),
    )
    return _validated_report(report)


def validate_portfolio_change_report_lineage(
    report: PortfolioChangeReport,
    previous_snapshot: PortfolioSnapshot,
    current_snapshot: PortfolioSnapshot,
) -> None:
    _validated_report(report)
    rebuilt = build_portfolio_change_report(previous_snapshot, current_snapshot,
                                            generated_at=report.generated_at)
    compared = (
        report.previous_snapshot_id == rebuilt.previous_snapshot_id,
        report.current_snapshot_id == rebuilt.current_snapshot_id,
        report.previous_captured_at == rebuilt.previous_captured_at,
        report.current_captured_at == rebuilt.current_captured_at,
        report.previous_position_count == rebuilt.previous_position_count,
        report.current_position_count == rebuilt.current_position_count,
        report.change_set == rebuilt.change_set,
    )
    if not all(compared):
        raise ValueError("Portfolio change report lineage does not match snapshots")


def validate_portfolio_change_report_sequence(
    reports: Iterable[PortfolioChangeReport],
) -> None:
    ordered = sorted(tuple(reports), key=lambda item: (item.previous_captured_at, item.report_id))
    for report in ordered:
        _validated_report(report)
    if len({report.report_id for report in ordered}) != len(ordered):
        raise ValueError("Duplicate portfolio change report")
    previous_ids = [report.previous_snapshot_id for report in ordered]
    current_ids = [report.current_snapshot_id for report in ordered]
    if len(set(previous_ids)) != len(previous_ids) or len(set(current_ids)) != len(current_ids):
        raise ValueError("Branched portfolio change report history")
    for left, right in zip(ordered, ordered[1:]):
        if left.current_snapshot_id != right.previous_snapshot_id:
            raise ValueError("Gap in portfolio change report history")
        if left.current_captured_at != right.previous_captured_at or left.current_captured_at >= right.current_captured_at:
            raise ValueError("Portfolio change report timestamps are not strictly increasing")


def portfolio_change_report_filename(report: PortfolioChangeReport) -> str:
    report = _validated_report(report)
    previous = report.previous_captured_at.strftime("%Y%m%dT%H%M%SZ")
    current = report.current_captured_at.strftime("%Y%m%dT%H%M%SZ")
    return f"jolika_change_{previous}_{current}_{report.report_id.rsplit('|', 1)[-1]}.json"


def write_portfolio_change_report(
    report: PortfolioChangeReport,
    *,
    output_path: Path | str,
    overwrite: bool = False,
) -> None:
    destination = Path(output_path)
    text = serialize_portfolio_change_report(report)
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
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def list_portfolio_change_reports(directory: Path | str) -> tuple[PortfolioChangeReport, ...]:
    root = Path(directory)
    if not root.exists():
        return ()
    if not root.is_dir():
        raise ValueError("Portfolio change report path must be a directory")
    reports = [load_portfolio_change_report(path) for path in root.iterdir()
               if path.is_file() and _FILENAME_RE.fullmatch(path.name)]
    reports.sort(key=lambda report: (report.current_captured_at, report.report_id))
    return tuple(reports)
