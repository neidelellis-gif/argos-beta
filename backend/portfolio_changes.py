"""Pure, deterministic change detection for JOLIKA portfolio snapshots."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
import json
import unicodedata

from backend.models import EconomicAssetClass, PortfolioOwner, PortfolioPosition


class PositionChangeType(str, Enum):
    ADDED = "added"
    REMOVED = "removed"
    UNCHANGED = "unchanged"
    QUANTITY_INCREASED = "quantity_increased"
    QUANTITY_DECREASED = "quantity_decreased"
    ACCOUNT_CHANGED = "account_changed"
    MARKET_VALUE_CHANGED = "market_value_changed"
    UNIT_PRICE_CHANGED = "unit_price_changed"
    ECONOMIC_CLASS_CHANGED = "economic_class_changed"
    LEGACY_ASSET_CLASS_CHANGED = "legacy_asset_class_changed"
    MULTIPLE_CHANGES = "multiple_changes"


def _normalize(value: str | None) -> str:
    text = unicodedata.normalize("NFKD", value or "")
    return " ".join(
        "".join(c for c in text if not unicodedata.combining(c)).upper().split()
    )


@dataclass(frozen=True)
class PositionSnapshotIdentity:
    owner: PortfolioOwner
    institution: str
    identifier_type: str | None
    identifier: str | None
    asset_name: str | None
    stable_key: str


@dataclass(frozen=True)
class PositionDelta:
    stable_key: str
    institution: str
    identifier: str | None
    identifier_type: str | None
    asset_name: str | None
    previous_position: PortfolioPosition | None
    current_position: PortfolioPosition | None
    change_types: tuple[PositionChangeType, ...]
    quantity_delta: Decimal | None
    market_value_delta: Decimal | None
    unit_price_delta: Decimal | None
    previous_account: str | None
    current_account: str | None
    previous_economic_asset_class: EconomicAssetClass | None
    current_economic_asset_class: EconomicAssetClass | None
    previous_asset_class: str | None
    current_asset_class: str | None
    position_flow_unknown: bool = False


@dataclass(frozen=True)
class PortfolioChangeSet:
    deltas: tuple[PositionDelta, ...]
    institution_change_sets: tuple[tuple[str, "PortfolioChangeSet"], ...] = ()

    def _count(self, kind: PositionChangeType) -> int:
        return sum(kind in delta.change_types for delta in self.deltas)

    @property
    def added_count(self) -> int: return self._count(PositionChangeType.ADDED)
    @property
    def removed_count(self) -> int: return self._count(PositionChangeType.REMOVED)
    @property
    def unchanged_count(self) -> int: return self._count(PositionChangeType.UNCHANGED)
    @property
    def quantity_increased_count(self) -> int: return self._count(PositionChangeType.QUANTITY_INCREASED)
    @property
    def quantity_decreased_count(self) -> int: return self._count(PositionChangeType.QUANTITY_DECREASED)
    @property
    def account_changed_count(self) -> int: return self._count(PositionChangeType.ACCOUNT_CHANGED)
    @property
    def economic_class_changed_count(self) -> int: return self._count(PositionChangeType.ECONOMIC_CLASS_CHANGED)
    @property
    def total_previous_positions(self) -> int:
        return sum(delta.previous_position is not None for delta in self.deltas)
    @property
    def total_current_positions(self) -> int:
        return sum(delta.current_position is not None for delta in self.deltas)

    def for_institution(self, institution: str) -> "PortfolioChangeSet":
        wanted = _normalize(institution)
        for name, changes in self.institution_change_sets:
            if name == wanted:
                return changes
        raise KeyError(institution)


def position_snapshot_identity(position: PortfolioPosition) -> PositionSnapshotIdentity:
    if position.owner is not PortfolioOwner.JOLIKA:
        raise ValueError("JOLIKA portfolio comparison rejects non-JOLIKA positions")
    institution = _normalize(position.institution)
    identifier = _normalize(position.identifier)
    identifier_type = _normalize(position.identifier_type)
    asset_name = _normalize(position.asset_name)
    if identifier:
        identity = f"{identifier_type or 'IDENTIFIER'}:{identifier}"
    elif asset_name:
        identity = f"NAME:{asset_name}"
    else:
        raise ValueError("JOLIKA position requires identifier or asset_name")
    return PositionSnapshotIdentity(
        owner=position.owner,
        institution=institution,
        identifier_type=identifier_type or None,
        identifier=identifier or None,
        asset_name=asset_name or None,
        stable_key=f"{position.owner.value}|{institution}|{identity}",
    )


def decimal_delta(previous: Decimal | None, current: Decimal | None) -> Decimal | None:
    if previous is None or current is None:
        return None
    return current - previous


def _index(positions: Iterable[PortfolioPosition]) -> dict[str, PortfolioPosition]:
    result: dict[str, PortfolioPosition] = {}
    for position in positions:
        identity = position_snapshot_identity(position)
        if identity.stable_key in result:
            raise ValueError(f"Duplicate JOLIKA position stable_key: {identity.stable_key}")
        result[identity.stable_key] = position
    return result


def _delta(key: str, previous: PortfolioPosition | None, current: PortfolioPosition | None) -> PositionDelta:
    position = current or previous
    assert position is not None
    if previous is None:
        kinds = (PositionChangeType.ADDED,)
        flow_unknown = current.quantity is None
    elif current is None:
        kinds = (PositionChangeType.REMOVED,)
        flow_unknown = previous.quantity is None
    else:
        changes: list[PositionChangeType] = []
        if previous.quantity is not None and current.quantity is not None:
            if current.quantity > previous.quantity:
                changes.append(PositionChangeType.QUANTITY_INCREASED)
            elif current.quantity < previous.quantity:
                changes.append(PositionChangeType.QUANTITY_DECREASED)
            flow_unknown = False
        else:
            flow_unknown = True
        if previous.account != current.account:
            changes.append(PositionChangeType.ACCOUNT_CHANGED)
        if previous.market_value != current.market_value:
            changes.append(PositionChangeType.MARKET_VALUE_CHANGED)
        if previous.unit_price != current.unit_price:
            changes.append(PositionChangeType.UNIT_PRICE_CHANGED)
        if previous.economic_asset_class != current.economic_asset_class:
            changes.append(PositionChangeType.ECONOMIC_CLASS_CHANGED)
        if previous.asset_class != current.asset_class:
            changes.append(PositionChangeType.LEGACY_ASSET_CLASS_CHANGED)
        if not changes:
            kinds = (PositionChangeType.UNCHANGED,)
        elif len(changes) == 1:
            kinds = tuple(changes)
        else:
            kinds = tuple(changes) + (PositionChangeType.MULTIPLE_CHANGES,)
    return PositionDelta(
        stable_key=key,
        institution=_normalize(position.institution),
        identifier=position.identifier,
        identifier_type=position.identifier_type,
        asset_name=position.asset_name,
        previous_position=previous,
        current_position=current,
        change_types=kinds,
        quantity_delta=decimal_delta(previous.quantity if previous else None, current.quantity if current else None),
        market_value_delta=decimal_delta(previous.market_value if previous else None, current.market_value if current else None),
        unit_price_delta=decimal_delta(previous.unit_price if previous else None, current.unit_price if current else None),
        previous_account=previous.account if previous else None,
        current_account=current.account if current else None,
        previous_economic_asset_class=previous.economic_asset_class if previous else None,
        current_economic_asset_class=current.economic_asset_class if current else None,
        previous_asset_class=previous.asset_class if previous else None,
        current_asset_class=current.asset_class if current else None,
        position_flow_unknown=flow_unknown,
    )


def compare_institution_snapshots(
    previous: Iterable[PortfolioPosition], current: Iterable[PortfolioPosition]
) -> PortfolioChangeSet:
    previous_tuple, current_tuple = tuple(previous), tuple(current)
    institutions = {_normalize(p.institution) for p in previous_tuple + current_tuple}
    if len(institutions) > 1:
        raise ValueError("Institution comparison accepts exactly one institution")
    old, new = _index(previous_tuple), _index(current_tuple)
    keys = sorted(set(old) | set(new))
    return PortfolioChangeSet(tuple(_delta(key, old.get(key), new.get(key)) for key in keys))


def compare_portfolio_snapshots(
    previous: Iterable[PortfolioPosition], current: Iterable[PortfolioPosition]
) -> PortfolioChangeSet:
    previous_tuple, current_tuple = tuple(previous), tuple(current)
    for position in previous_tuple + current_tuple:
        if position.owner is not PortfolioOwner.JOLIKA:
            raise ValueError("JOLIKA portfolio comparison rejects NEI or mixed snapshots")
    institutions = sorted({_normalize(p.institution) for p in previous_tuple + current_tuple})
    institutional: list[tuple[str, PortfolioChangeSet]] = []
    all_deltas: list[PositionDelta] = []
    for institution in institutions:
        changes = compare_institution_snapshots(
            (p for p in previous_tuple if _normalize(p.institution) == institution),
            (p for p in current_tuple if _normalize(p.institution) == institution),
        )
        institutional.append((institution, changes))
        all_deltas.extend(changes.deltas)
    all_deltas.sort(key=lambda d: (d.institution, d.stable_key))
    return PortfolioChangeSet(tuple(all_deltas), tuple(institutional))


def _position_payload(position: PortfolioPosition | None):
    if position is None:
        return None
    def value(item):
        if isinstance(item, Decimal): return str(item)
        if isinstance(item, Enum): return item.value
        if hasattr(item, "isoformat"): return item.isoformat()
        return item
    return {name: value(getattr(position, name)) for name in position.__dataclass_fields__}


def serialize_portfolio_change_set(change_set: PortfolioChangeSet) -> str:
    payload = {"deltas": []}
    for delta in change_set.deltas:
        payload["deltas"].append({
            "stable_key": delta.stable_key,
            "institution": delta.institution,
            "identifier": delta.identifier,
            "identifier_type": delta.identifier_type,
            "asset_name": delta.asset_name,
            "change_types": [kind.value for kind in delta.change_types],
            "quantity_delta": None if delta.quantity_delta is None else str(delta.quantity_delta),
            "market_value_delta": None if delta.market_value_delta is None else str(delta.market_value_delta),
            "unit_price_delta": None if delta.unit_price_delta is None else str(delta.unit_price_delta),
            "previous_account": delta.previous_account,
            "current_account": delta.current_account,
            "previous_economic_asset_class": None if delta.previous_economic_asset_class is None else delta.previous_economic_asset_class.value,
            "current_economic_asset_class": None if delta.current_economic_asset_class is None else delta.current_economic_asset_class.value,
            "previous_asset_class": delta.previous_asset_class,
            "current_asset_class": delta.current_asset_class,
            "position_flow_unknown": delta.position_flow_unknown,
            "previous_position": _position_payload(delta.previous_position),
            "current_position": _position_payload(delta.current_position),
        })
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
