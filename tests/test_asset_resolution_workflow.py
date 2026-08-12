from dataclasses import replace
from decimal import Decimal
import json
from pathlib import Path

import pytest

from backend.asset_resolution import (
    JolikaAssetResolution,
    collect_unresolved_jolika_assets,
    export_unresolved_jolika_assets,
    load_jolika_asset_resolution_registry,
    resolve_jolika_position,
)
from backend.asset_resolution_workflow import (
    JolikaAssetResolutionDecision,
    build_updated_jolika_asset_resolution_registry,
    load_jolika_asset_resolution_decisions,
    load_unresolved_jolika_assets,
    serialize_jolika_asset_resolution_registry,
    validate_jolika_resolution_decisions,
    write_jolika_asset_resolution_registry,
)
from backend.models import EconomicAssetClass, PortfolioOwner, PortfolioPosition


def position(**changes):
    base = PortfolioPosition(
        institution="UBS",
        owner=PortfolioOwner.JOLIKA,
        account="A1",
        asset_class="ETF",
        asset_subclass=None,
        asset_name="Future Asset",
        identifier="FUTURE-1",
        identifier_type="ticker",
        quantity=Decimal("2"),
        unit_price=Decimal("50"),
        market_value=Decimal("100"),
        currency="USD",
        portfolio_weight=None,
        reference_date=None,
        source_file="future.csv",
        economic_asset_class=None,
    )
    return replace(base, **changes)


def unresolved():
    return collect_unresolved_jolika_assets((position(),))[0]


def decision(**changes):
    base = JolikaAssetResolutionDecision(
        stable_key=unresolved().stable_key,
        economic_asset_class=EconomicAssetClass.FIXED_INCOME,
        status="confirmed",
        resolution_source="human_review",
        note="Reviewed",
    )
    return replace(base, **changes)


def write_decisions(path: Path, records, schema_version=1):
    path.write_text(
        json.dumps({"schema_version": schema_version, "decisions": records}),
        encoding="utf-8",
    )


def test_decision_loader_is_deterministic_and_strict(tmp_path):
    path = tmp_path / "decisions.json"
    records = [
        {
            "stable_key": "JOLIKA|UBS|TICKER:ZZZ",
            "economic_asset_class": "Renda Fixa",
            "status": "confirmed",
            "resolution_source": "human_review",
            "note": None,
        },
        {
            "stable_key": "JOLIKA|UBS|TICKER:AAA",
            "economic_asset_class": "Ações",
            "status": "confirmed",
            "resolution_source": "human_review",
            "note": "ok",
        },
    ]
    write_decisions(path, records)
    loaded = load_jolika_asset_resolution_decisions(path)
    assert tuple(item.stable_key for item in loaded) == (
        "JOLIKA|UBS|TICKER:AAA",
        "JOLIKA|UBS|TICKER:ZZZ",
    )


@pytest.mark.parametrize(
    "mutation",
    [
        lambda r: r.update(stable_key="NEI|UBS|TICKER:X"),
        lambda r: r.update(economic_asset_class="Invalida"),
        lambda r: r.update(status="pending"),
        lambda r: r.update(resolution_source="automatic"),
        lambda r: r.update(market_value="100"),
    ],
)
def test_decision_loader_rejects_invalid_semantics(tmp_path, mutation):
    path = tmp_path / "decisions.json"
    record = {
        "stable_key": "JOLIKA|UBS|TICKER:X",
        "economic_asset_class": "Renda Fixa",
        "status": "confirmed",
        "resolution_source": "human_review",
        "note": None,
    }
    mutation(record)
    write_decisions(path, [record])
    with pytest.raises(ValueError):
        load_jolika_asset_resolution_decisions(path)


def test_decision_loader_rejects_duplicate_and_schema(tmp_path):
    path = tmp_path / "decisions.json"
    record = {
        "stable_key": "JOLIKA|UBS|TICKER:X",
        "economic_asset_class": "Renda Fixa",
        "status": "confirmed",
        "resolution_source": "human_review",
        "note": None,
    }
    write_decisions(path, [record, record])
    with pytest.raises(ValueError):
        load_jolika_asset_resolution_decisions(path)
    write_decisions(path, [], schema_version=99)
    with pytest.raises(ValueError):
        load_jolika_asset_resolution_decisions(path)


def test_unresolved_round_trip_loader(tmp_path):
    source = unresolved()
    path = tmp_path / "unresolved.json"
    export_unresolved_jolika_assets((source,), output_path=path)
    loaded = load_unresolved_jolika_assets(path)
    assert loaded == (source,)


def test_build_promotes_using_observed_identity_and_preserves_inputs():
    asset = unresolved()
    current = {}
    proposed = build_updated_jolika_asset_resolution_registry(
        (asset,),
        (decision(),),
        current,
    )
    resolution = proposed[asset.stable_key]
    assert resolution.identifier == asset.identifier
    assert resolution.identifier_type == asset.identifier_type
    assert resolution.asset_name == asset.asset_name
    assert resolution.economic_asset_class is EconomicAssetClass.FIXED_INCOME
    assert not hasattr(resolution, "market_value")
    assert current == {}


def test_stale_and_conflicting_decisions_fail():
    asset = unresolved()
    with pytest.raises(ValueError):
        validate_jolika_resolution_decisions((), (decision(),), {})

    existing = {
        asset.stable_key: JolikaAssetResolution(
            stable_key=asset.stable_key,
            economic_asset_class=EconomicAssetClass.EQUITIES,
            identifier=asset.identifier,
            identifier_type=asset.identifier_type,
            asset_name=asset.asset_name,
            status="confirmed",
            resolution_source="human_review",
            note="Different",
        )
    }
    with pytest.raises(ValueError):
        validate_jolika_resolution_decisions((asset,), (decision(),), existing)


def test_identical_existing_resolution_is_idempotent():
    asset = unresolved()
    d = decision()
    existing_resolution = JolikaAssetResolution(
        stable_key=asset.stable_key,
        economic_asset_class=d.economic_asset_class,
        identifier=asset.identifier,
        identifier_type=asset.identifier_type,
        asset_name=asset.asset_name,
        status=d.status,
        resolution_source=d.resolution_source,
        note=d.note,
    )
    existing = {asset.stable_key: existing_resolution}
    proposed = build_updated_jolika_asset_resolution_registry((asset,), (d,), existing)
    assert proposed[asset.stable_key] == existing_resolution


def test_serialization_is_deterministic_and_loader_compatible(tmp_path):
    asset = unresolved()
    proposed = build_updated_jolika_asset_resolution_registry((asset,), (decision(),), {})
    first = serialize_jolika_asset_resolution_registry(proposed)
    second = serialize_jolika_asset_resolution_registry(proposed)
    assert first == second
    assert first.endswith("\n")
    path = tmp_path / "registry.json"
    path.write_text(first, encoding="utf-8")
    loaded = load_jolika_asset_resolution_registry(path)
    assert dict(loaded) == dict(proposed)


def test_write_requires_explicit_overwrite(tmp_path):
    asset = unresolved()
    proposed = build_updated_jolika_asset_resolution_registry((asset,), (decision(),), {})
    path = tmp_path / "registry.json"
    write_jolika_asset_resolution_registry(proposed, output_path=path)
    original = path.read_text()
    with pytest.raises(FileExistsError):
        write_jolika_asset_resolution_registry(proposed, output_path=path)
    write_jolika_asset_resolution_registry(proposed, output_path=path, overwrite=True)
    assert path.read_text() == original


def test_end_to_end_review_build_and_resolution(tmp_path):
    original = position()
    unresolved_assets = collect_unresolved_jolika_assets((original,))
    review_path = tmp_path / "unresolved.json"
    export_unresolved_jolika_assets(unresolved_assets, output_path=review_path)
    loaded_unresolved = load_unresolved_jolika_assets(review_path)

    proposed = build_updated_jolika_asset_resolution_registry(
        loaded_unresolved,
        (decision(),),
        {},
    )
    registry_path = tmp_path / "proposed_registry.json"
    write_jolika_asset_resolution_registry(proposed, output_path=registry_path)
    registry = load_jolika_asset_resolution_registry(registry_path)
    resolved = resolve_jolika_position(original, registry=registry)

    assert resolved.economic_asset_class is EconomicAssetClass.FIXED_INCOME
    assert collect_unresolved_jolika_assets((resolved,)) == ()
    assert resolved.market_value == original.market_value
    assert resolved.quantity == original.quantity
    assert resolved.identifier == original.identifier
    assert resolved.institution == original.institution
    assert resolved.asset_class == original.asset_class
    assert resolved.source_file == original.source_file
