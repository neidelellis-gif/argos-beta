from dataclasses import replace
from decimal import Decimal

import pytest

from backend.models import EconomicAssetClass, PortfolioOwner, PortfolioPosition
from backend.portfolio_changes import (
    PositionChangeType,
    compare_institution_snapshots,
    compare_portfolio_snapshots,
    position_instance_identity,
    position_snapshot_identity,
    serialize_portfolio_change_set,
)


def pos(
    name="A",
    institution="UBS",
    identifier="AAA",
    quantity="10",
    price="100",
    value="1000",
    account="1",
    owner=PortfolioOwner.JOLIKA,
    identifier_type="ticker",
):
    return PortfolioPosition(
        institution=institution,
        owner=owner,
        account=account,
        asset_class="Equity",
        asset_subclass=None,
        asset_name=name,
        identifier=identifier,
        identifier_type=identifier_type,
        quantity=None if quantity is None else Decimal(quantity),
        unit_price=None if price is None else Decimal(price),
        market_value=None if value is None else Decimal(value),
        currency="USD",
        portfolio_weight=Decimal("1"),
        reference_date=None,
        source_file="x",
        economic_asset_class=EconomicAssetClass.EQUITIES,
    )


def kinds(delta):
    return set(delta.change_types)


def test_identity_normalizes_and_ignores_market_fields():
    a = pos(identifier=" ábc ")
    b = replace(
        a,
        identifier="ABC",
        market_value=Decimal("999"),
        unit_price=Decimal("7"),
        portfolio_weight=Decimal("9"),
    )
    assert position_snapshot_identity(a).stable_key == position_snapshot_identity(b).stable_key


def test_asset_identity_excludes_account_and_instance_identity_includes_it():
    a = pos(account=" A ")
    b = replace(a, account="B")
    assert position_snapshot_identity(a).stable_key == position_snapshot_identity(b).stable_key
    assert position_instance_identity(a).instance_key != position_instance_identity(b).instance_key
    assert position_instance_identity(a).instance_key.endswith("|ACCOUNT:A")


def test_identity_falls_back_to_name_and_institution_participates():
    a = pos(name="Fóo  Fund", identifier=None)
    assert position_snapshot_identity(a).stable_key == "JOLIKA|UBS|NAME:FOO FUND"
    assert position_snapshot_identity(a).stable_key != position_snapshot_identity(
        replace(a, institution="Santander")
    ).stable_key


def test_nei_is_rejected():
    with pytest.raises(ValueError):
        compare_portfolio_snapshots([pos(owner=PortfolioOwner.NEI)], [])


def test_added_removed_and_unchanged():
    a = pos("A", identifier="A")
    b = pos("B", identifier="B")
    c = pos("C", identifier="C")
    result = compare_institution_snapshots([a, b], [a, c])
    by_key = {d.stable_key: d for d in result.deltas}
    assert PositionChangeType.UNCHANGED in kinds(by_key[position_snapshot_identity(a).stable_key])
    assert PositionChangeType.REMOVED in kinds(by_key[position_snapshot_identity(b).stable_key])
    assert PositionChangeType.ADDED in kinds(by_key[position_snapshot_identity(c).stable_key])


def test_quantity_increase_and_decrease():
    a = pos()
    assert PositionChangeType.QUANTITY_INCREASED in kinds(
        compare_institution_snapshots([a], [replace(a, quantity=Decimal("11"))]).deltas[0]
    )
    assert PositionChangeType.QUANTITY_DECREASED in kinds(
        compare_institution_snapshots([a], [replace(a, quantity=Decimal("9"))]).deltas[0]
    )


def test_account_transfer_is_not_add_remove():
    a = pos(account="A")
    delta = compare_institution_snapshots([a], [replace(a, account="B")]).deltas[0]
    assert kinds(delta) == {PositionChangeType.ACCOUNT_CHANGED}
    assert delta.previous_instance_key.endswith("|ACCOUNT:A")
    assert delta.current_instance_key.endswith("|ACCOUNT:B")


def test_account_and_quantity_changes_are_preserved():
    a = pos(account="A")
    delta = compare_institution_snapshots(
        [a], [replace(a, account="B", quantity=Decimal("12"))]
    ).deltas[0]
    assert {
        PositionChangeType.ACCOUNT_CHANGED,
        PositionChangeType.QUANTITY_INCREASED,
        PositionChangeType.MULTIPLE_CHANGES,
    } <= kinds(delta)


def test_price_change_does_not_imply_purchase():
    a = pos(quantity="10", price="100", value="1000")
    delta = compare_institution_snapshots(
        [a], [replace(a, unit_price=Decimal("120"), market_value=Decimal("1200"))]
    ).deltas[0]
    assert delta.unit_price_delta == Decimal("20")
    assert delta.market_value_delta == Decimal("200")
    assert PositionChangeType.QUANTITY_INCREASED not in kinds(delta)
    assert PositionChangeType.QUANTITY_DECREASED not in kinds(delta)


def test_quantity_none_never_infers_flow():
    a = pos(quantity=None, value="1000")
    delta = compare_institution_snapshots(
        [a], [replace(a, market_value=Decimal("1500"))]
    ).deltas[0]
    assert delta.position_flow_unknown is True
    assert delta.market_value_delta == Decimal("500")
    assert PositionChangeType.QUANTITY_INCREASED not in kinds(delta)


def test_economic_and_legacy_classes_report_changes():
    a = pos()
    current = replace(
        a,
        economic_asset_class=EconomicAssetClass.FIXED_INCOME,
        asset_class="Bond",
    )
    delta = compare_institution_snapshots([a], [current]).deltas[0]
    assert PositionChangeType.ECONOMIC_CLASS_CHANGED in kinds(delta)
    assert PositionChangeType.LEGACY_ASSET_CLASS_CHANGED in kinds(delta)


def test_duplicate_same_asset_and_same_account_rejected():
    a = pos()
    with pytest.raises(ValueError):
        compare_institution_snapshots([a, a], [])


def test_same_asset_in_different_accounts_is_valid():
    a = pos(account="A")
    b = replace(a, account="B")
    result = compare_institution_snapshots([a, b], [a, b])
    assert len(result.deltas) == 2
    assert result.unchanged_count == 2


def test_account_none_has_deterministic_instance_identity():
    a = pos(account=None)
    assert position_instance_identity(a).instance_key.endswith("|ACCOUNT:<NONE>")
    with pytest.raises(ValueError):
        compare_institution_snapshots([a, a], [])
    b = replace(a, account="A")
    assert compare_institution_snapshots([a, b], [a, b]).unchanged_count == 2


def test_multi_account_added_and_removed_instances():
    a = pos(account="A")
    b = replace(a, account="B")
    c = replace(a, account="C")
    added = compare_institution_snapshots([a, b], [a, b, c])
    assert added.unchanged_count == 2
    assert added.added_count == 1
    removed = compare_institution_snapshots([a, b, c], [a, b])
    assert removed.unchanged_count == 2
    assert removed.removed_count == 1


def test_multi_account_ambiguous_does_not_pair_transfers():
    a = pos(account="A")
    b = replace(a, account="B")
    c = replace(a, account="C")
    d = replace(a, account="D")
    result = compare_institution_snapshots([a, b], [c, d])
    assert result.removed_count == 2
    assert result.added_count == 2
    assert result.account_changed_count == 0


def test_real_santander_dda_multi_account_case_is_preserved():
    base = pos(
        name="DDA CUSTODIAL CASH ACCOUNTS",
        institution="Santander",
        identifier="DDA CUSTODIAL CASH ACCOUNTS",
        identifier_type=None,
        quantity=None,
        price=None,
        value="0",
        account="115099244",
    )
    positions = (
        base,
        replace(base, account="115111355"),
        replace(base, account="115111444"),
        replace(base, account="115088644", market_value=Decimal("350")),
    )
    result = compare_portfolio_snapshots(positions, tuple(reversed(positions)))
    assert len(result.deltas) == 4
    assert result.unchanged_count == 4
    assert len({delta.previous_instance_key for delta in result.deltas}) == 4


def test_multi_institution_is_compared_separately():
    ubs = pos(identifier="A", institution="UBS")
    sant = pos(identifier="B", institution="Santander")
    added = pos(identifier="C", institution="Santander")
    result = compare_portfolio_snapshots(
        [ubs, sant], [replace(ubs, quantity=Decimal("11")), sant, added]
    )
    assert result.for_institution("UBS").quantity_increased_count == 1
    assert result.for_institution("Santander").added_count == 1
    assert result.for_institution("Santander").unchanged_count == 1


def test_cross_institution_same_identifier_is_remove_plus_add():
    a = pos(identifier="X", institution="UBS")
    b = replace(a, institution="Santander")
    result = compare_portfolio_snapshots([a], [b])
    assert result.removed_count == 1
    assert result.added_count == 1


def test_order_independent_and_serialization_deterministic():
    a = pos(identifier="A")
    b = pos(identifier="B")
    one = compare_portfolio_snapshots(
        [a, b], [replace(a, quantity=Decimal("11")), b]
    )
    two = compare_portfolio_snapshots(
        [b, a], [b, replace(a, quantity=Decimal("11"))]
    )
    assert one.deltas == two.deltas
    assert serialize_portfolio_change_set(one) == serialize_portfolio_change_set(two)
    assert serialize_portfolio_change_set(one).endswith("\n")
    assert "previous_instance_key" in serialize_portfolio_change_set(one)


def test_institution_comparison_rejects_mixed_institutions():
    with pytest.raises(ValueError):
        compare_institution_snapshots(
            [pos(institution="UBS")], [pos(institution="Santander")]
        )


def test_empty_snapshots_are_valid():
    result = compare_portfolio_snapshots([], [])
    assert result.deltas == ()
    assert result.total_previous_positions == result.total_current_positions == 0


def test_identity_rejects_missing_identifier_and_name():
    with pytest.raises(ValueError):
        position_snapshot_identity(pos(name=None, identifier=None))


def test_instance_key_normalizes_account():
    a = pos(account=" acc  1 ")
    b = replace(a, account="ACC 1")
    assert position_instance_identity(a) == position_instance_identity(b)


def test_single_unmatched_each_side_can_be_account_transfer_after_exact_matches():
    a = pos(account="A")
    b = replace(a, account="B")
    c = replace(a, account="C")
    result = compare_institution_snapshots([a, b], [a, c])
    assert result.unchanged_count == 1
    assert result.account_changed_count == 1
    assert result.added_count == 0
    assert result.removed_count == 0


def test_multi_account_quantity_none_preserves_unknown_flow():
    a = pos(account="A", quantity=None, value="100")
    b = replace(a, account="B", market_value=Decimal("120"))
    result = compare_institution_snapshots([a], [b])
    delta = result.deltas[0]
    assert PositionChangeType.ACCOUNT_CHANGED in kinds(delta)
    assert delta.position_flow_unknown is True
    assert PositionChangeType.QUANTITY_INCREASED not in kinds(delta)
