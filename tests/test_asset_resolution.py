from dataclasses import replace
from decimal import Decimal
import json
from types import MappingProxyType

import pytest

from backend.asset_resolution import (
    JolikaAssetResolution,
    UnresolvedJolikaAsset,
    build_unresolved_asset_review_records,
    collect_unresolved_jolika_assets,
    export_unresolved_jolika_assets,
    load_jolika_asset_resolution_registry,
    resolve_jolika_position,
    resolve_jolika_positions,
)
from backend.models import EconomicAssetClass, PortfolioOwner, PortfolioPosition


def position(**changes) -> PortfolioPosition:
    base = PortfolioPosition(
        institution="UBS",
        owner=PortfolioOwner.JOLIKA,
        account="account-1",
        asset_class="Unmapped source class",
        asset_subclass=None,
        asset_name="Unknown Asset",
        identifier="UNKNOWN",
        identifier_type="ticker",
        quantity=Decimal("3"),
        unit_price=Decimal("40"),
        market_value=Decimal("120"),
        currency="USD",
        portfolio_weight=Decimal("1.2"),
        reference_date=None,
        source_file="positions.csv",
    )
    return replace(base, **changes)


def write_registry(tmp_path, resolutions=None, schema_version=1):
    path = tmp_path / "registry.json"
    payload = {
        "schema_version": schema_version,
        "resolutions": [] if resolutions is None else resolutions,
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def registry_entry(**changes):
    base = {
        "stable_key": "JOLIKA|UBS|TICKER:ARGOS-GOLD",
        "economic_asset_class": "Ouro & Commodities",
        "identifier": "ARGOS-GOLD",
        "identifier_type": "ticker",
        "asset_name": "Argos Gold",
        "status": "confirmed",
        "resolution_source": "human_review",
        "note": "reviewed",
    }
    base.update(changes)
    return base


def test_default_registry_loads_and_is_read_only():
    registry = load_jolika_asset_resolution_registry()
    assert list(registry) == sorted(registry)
    with pytest.raises(TypeError):
        registry["x"] = registry[next(iter(registry))]


def test_empty_registry_is_valid(tmp_path):
    registry = load_jolika_asset_resolution_registry(write_registry(tmp_path))
    assert dict(registry) == {}


def test_unknown_schema_version_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="schema_version"):
        load_jolika_asset_resolution_registry(write_registry(tmp_path, schema_version=2))


def test_invalid_json_is_rejected(tmp_path):
    path = tmp_path / "registry.json"
    path.write_text("{", encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid JOLIKA"):
        load_jolika_asset_resolution_registry(path)


def test_invalid_economic_class_is_rejected(tmp_path):
    path = write_registry(
        tmp_path,
        [registry_entry(economic_asset_class="Not a class")],
    )
    with pytest.raises(ValueError, match="economic_asset_class"):
        load_jolika_asset_resolution_registry(path)


def test_empty_stable_key_is_rejected(tmp_path):
    path = write_registry(tmp_path, [registry_entry(stable_key="")])
    with pytest.raises(ValueError, match="stable_key"):
        load_jolika_asset_resolution_registry(path)


def test_non_jolika_stable_key_is_rejected(tmp_path):
    path = write_registry(
        tmp_path,
        [registry_entry(stable_key="NEI|UBS|TICKER:ARGOS-GOLD")],
    )
    with pytest.raises(ValueError, match="JOLIKA"):
        load_jolika_asset_resolution_registry(path)


def test_duplicate_stable_key_is_rejected(tmp_path):
    entry = registry_entry()
    path = write_registry(tmp_path, [entry, dict(entry)])
    with pytest.raises(ValueError, match="Duplicate"):
        load_jolika_asset_resolution_registry(path)


def test_invalid_status_is_rejected(tmp_path):
    path = write_registry(tmp_path, [registry_entry(status="pending")])
    with pytest.raises(ValueError, match="confirmed"):
        load_jolika_asset_resolution_registry(path)


def test_identity_conflict_is_rejected(tmp_path):
    path = write_registry(tmp_path, [registry_entry(identifier="OTHER")])
    with pytest.raises(ValueError, match="conflicts"):
        load_jolika_asset_resolution_registry(path)


def test_registry_order_does_not_change_result(tmp_path):
    one = registry_entry()
    two = {
        "stable_key": "JOLIKA|UBS|NAME:ARGOS CONFIRMED EQUITY FUND",
        "economic_asset_class": "Fundos / Estratégias",
        "identifier": None,
        "identifier_type": None,
        "asset_name": "Argos Confirmed Equity Fund",
        "status": "confirmed",
        "resolution_source": "human_review",
        "note": None,
    }
    first = load_jolika_asset_resolution_registry(write_registry(tmp_path, [one, two]))
    second_path = tmp_path / "second.json"
    second_path.write_text(
        json.dumps({"resolutions": [two, one], "schema_version": 1}),
        encoding="utf-8",
    )
    second = load_jolika_asset_resolution_registry(second_path)
    assert first == second


def test_already_classified_position_is_preserved_intact():
    original = position(economic_asset_class=EconomicAssetClass.EQUITIES)
    assert resolve_jolika_position(original) is original


def test_known_identifier_resolution_preserves_source_fields():
    original = position(
        identifier="US0000000099",
        identifier_type="isin",
        asset_name="Unclassified Note",
    )
    resolved = resolve_jolika_position(original)
    assert resolved.economic_asset_class is EconomicAssetClass.FIXED_INCOME
    for field in (
        "market_value",
        "asset_class",
        "identifier",
        "institution",
        "quantity",
        "account",
        "source_file",
    ):
        assert getattr(resolved, field) == getattr(original, field)


def test_identifier_precedes_conflicting_known_name():
    resolved = resolve_jolika_position(
        position(
            identifier="ARGOS-GOLD",
            identifier_type="ticker",
            asset_name="ARGOS CONFIRMED EQUITY FUND",
        )
    )
    assert resolved.economic_asset_class is EconomicAssetClass.GOLD_AND_COMMODITIES


def test_name_is_fallback_when_identifier_has_no_resolution():
    resolved = resolve_jolika_position(
        position(
            identifier="NOT-IN-REGISTRY",
            identifier_type="ticker",
            asset_name="Argos Confirmed Equity Fund",
        )
    )
    assert resolved.economic_asset_class is EconomicAssetClass.FUNDS_STRATEGIES


def test_unknown_position_remains_unclassified():
    original = position()
    assert resolve_jolika_position(original).economic_asset_class is None


def test_empty_injected_registry_does_not_fall_back_to_default():
    original = position(identifier="ARGOS-GOLD")
    resolved = resolve_jolika_position(original, registry=MappingProxyType({}))
    assert resolved.economic_asset_class is None


def test_resolution_functions_are_idempotent():
    original = position(identifier="ARGOS-GOLD")
    once = resolve_jolika_position(original)
    assert resolve_jolika_position(once) == once
    assert resolve_jolika_positions(resolve_jolika_positions((original,))) == (once,)


def test_jolika_batch_preserves_count_and_total_market_value():
    original = (position(identifier="ARGOS-GOLD"), position(identifier="OTHER"))
    resolved = resolve_jolika_positions(original)
    assert len(resolved) == len(original)
    assert sum(item.market_value for item in resolved) == sum(
        item.market_value for item in original
    )


@pytest.mark.parametrize(
    "batch",
    [
        (position(owner=PortfolioOwner.NEI),),
        (position(), position(owner=PortfolioOwner.NEI)),
    ],
)
def test_non_jolika_and_mixed_batches_are_rejected(batch):
    with pytest.raises(ValueError, match="mixed or non-JOLIKA"):
        resolve_jolika_positions(batch)
    with pytest.raises(ValueError, match="mixed or non-JOLIKA"):
        collect_unresolved_jolika_assets(batch)


def test_single_nei_position_is_rejected():
    with pytest.raises(ValueError, match="non-JOLIKA"):
        resolve_jolika_position(position(owner=PortfolioOwner.NEI))


def test_unresolved_registry_deduplicates_and_orders_by_stable_key():
    unresolved = collect_unresolved_jolika_assets(
        (
            position(identifier="ZZZ"),
            position(identifier="AAA"),
            position(identifier="ZZZ"),
        )
    )
    assert [asset.stable_key for asset in unresolved] == [
        "JOLIKA|UBS|TICKER:AAA",
        "JOLIKA|UBS|TICKER:ZZZ",
    ]


def test_stable_key_excludes_market_value_and_account():
    first = collect_unresolved_jolika_assets((position(),))[0]
    changed = collect_unresolved_jolika_assets(
        (position(market_value=Decimal("999"), account="another-account"),)
    )[0]
    assert first.stable_key == changed.stable_key == "JOLIKA|UBS|TICKER:UNKNOWN"


def test_review_records_are_deduplicated_and_deterministic():
    assets = collect_unresolved_jolika_assets(
        (position(identifier="ZZZ"), position(identifier="AAA"), position(identifier="ZZZ"))
    )
    records = build_unresolved_asset_review_records(reversed(assets))
    assert [record.stable_key for record in records] == [
        "JOLIKA|UBS|TICKER:AAA",
        "JOLIKA|UBS|TICKER:ZZZ",
    ]


def test_review_rejects_non_jolika_record():
    bad = UnresolvedJolikaAsset(
        institution="UBS",
        identifier="X",
        identifier_type="ticker",
        asset_name="X",
        asset_class=None,
        currency="USD",
        source_file="x.csv",
        stable_key="NEI|UBS|TICKER:X",
    )
    with pytest.raises(ValueError, match="non-JOLIKA"):
        build_unresolved_asset_review_records((bad,))


def test_export_is_deterministic_and_excludes_financial_and_account_fields(tmp_path):
    original = position(market_value=Decimal("999"), account="secret-account")
    unresolved = collect_unresolved_jolika_assets((original,))
    first = export_unresolved_jolika_assets(unresolved)
    second_path = tmp_path / "review.json"
    second = export_unresolved_jolika_assets(unresolved, output_path=second_path)
    assert first == second == second_path.read_text(encoding="utf-8")
    assert first.endswith("\n")
    assert "market_value" not in first
    assert "account" not in first
    assert "999" not in first
    assert "secret-account" not in first


def test_export_does_not_modify_unresolved_records():
    unresolved = collect_unresolved_jolika_assets((position(),))
    before = tuple(unresolved)
    export_unresolved_jolika_assets(unresolved)
    assert unresolved == before
