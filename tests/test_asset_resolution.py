from dataclasses import replace
from decimal import Decimal

import pytest

from backend.asset_resolution import (
    collect_unresolved_jolika_assets,
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


def test_already_classified_position_is_preserved_intact():
    original = position(economic_asset_class=EconomicAssetClass.EQUITIES)
    assert resolve_jolika_position(original) is original


def test_unknown_position_remains_unclassified_and_is_collected():
    original = position()
    resolved = resolve_jolika_position(original)
    unresolved = collect_unresolved_jolika_assets((resolved,))

    assert resolved is original
    assert resolved.economic_asset_class is None
    assert len(unresolved) == 1
    assert unresolved[0].identifier == "UNKNOWN"


def test_known_identifier_resolution_preserves_all_source_fields():
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


def test_stable_key_is_deterministic_and_excludes_market_value_and_account():
    first = collect_unresolved_jolika_assets((position(),))[0]
    changed = collect_unresolved_jolika_assets(
        (position(market_value=Decimal("999"), account="another-account"),)
    )[0]

    assert first.stable_key == changed.stable_key == "JOLIKA|UBS|TICKER:UNKNOWN"


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


def test_registry_deduplicates_and_orders_by_stable_key():
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
