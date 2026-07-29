from dataclasses import FrozenInstanceError, replace
from datetime import date
from decimal import Decimal

import pytest

from backend.daily_portfolio_snapshot import (
    DailyPortfolioSnapshotBuilder,
    DailyPortfolioStatus,
)
from backend.import_validation import ImportValidationEngine, ImportValidationStatus
from backend.models import PortfolioOwner, PortfolioPosition


def position(institution="UBS", identifier="AAA", owner=None, **changes):
    owner = owner or (
        PortfolioOwner.NEI if institution == "Bradesco" else PortfolioOwner.JOLIKA
    )
    item = PortfolioPosition(
        institution=institution,
        owner=owner,
        account=f"{institution}-1",
        asset_class="Equity",
        asset_subclass="Stock",
        asset_name=f"Asset {identifier}",
        identifier=identifier,
        identifier_type="Ticker",
        quantity=Decimal("1"),
        unit_price=Decimal("100"),
        market_value=Decimal("100"),
        currency="USD",
        portfolio_weight=None,
        reference_date=None,
        source_file=f"{institution}.csv",
    )
    return replace(item, **changes)


@pytest.mark.parametrize(
    ("positions", "institutions"),
    (
        ([position("Bradesco")], ("Bradesco",)),
        ([position("UBS")], ("UBS",)),
        ([position("Santander")], ("Santander",)),
        ([position("UBS"), position("Santander", "BBB")], ("Santander", "UBS")),
        (
            [position("UBS"), position("Santander", "BBB"), position("Bradesco", "CCC")],
            ("Bradesco", "Santander", "UBS"),
        ),
    ),
)
def test_builds_supported_institution_combinations(positions, institutions):
    snapshot = DailyPortfolioSnapshotBuilder().build(positions)

    assert snapshot.institutions == institutions
    assert len(snapshot.institution_snapshots) == len(positions)
    assert snapshot.status is DailyPortfolioStatus.READY


def test_empty_snapshot_has_no_inferred_reference_date():
    snapshot = DailyPortfolioSnapshotBuilder().build([])

    assert snapshot.reference_date is None
    assert snapshot.status is DailyPortfolioStatus.EMPTY
    assert snapshot.institution_snapshots == ()
    assert snapshot.summary.original_position_count == 0


def test_keeps_nei_and_jolika_in_independent_views_and_consolidation():
    items = [position("UBS", "AAA"), position("Bradesco", "AAA")]

    snapshot = DailyPortfolioSnapshotBuilder().build(items)

    assert snapshot.owners == (PortfolioOwner.JOLIKA, PortfolioOwner.NEI)
    assert [(view.owner, view.institution) for view in snapshot.institution_snapshots] == [
        (PortfolioOwner.JOLIKA, "UBS"),
        (PortfolioOwner.NEI, "Bradesco"),
    ]
    assert snapshot.consolidated.unique_assets == 2
    assert snapshot.consolidated.positions_by_owner == {"JOLIKA": 1, "NEI": 1}


def test_never_adds_brl_and_usd_and_splits_institution_currency_views():
    items = [
        position("UBS", "USD", market_value=Decimal("1250000.00")),
        position("UBS", "BRL", currency="BRL", market_value=Decimal("734375.98")),
    ]

    snapshot = DailyPortfolioSnapshotBuilder().build(items)

    assert snapshot.currencies == ("BRL", "USD")
    assert snapshot.consolidated.gross_value_by_currency == {
        "BRL": Decimal("734375.98"),
        "USD": Decimal("1250000.00"),
    }
    assert [(view.currency, view.gross_value) for view in snapshot.institution_snapshots] == [
        ("BRL", Decimal("734375.98")),
        ("USD", Decimal("1250000.00")),
    ]


def test_validation_statuses_drive_daily_status_and_counts():
    builder = DailyPortfolioSnapshotBuilder()
    warning = position("UBS", asset_class=None)
    rejected = position("Santander", "BBB", currency=None)
    reports = {
        (warning.owner, warning.institution, warning.currency): ImportValidationEngine().validate([warning]),
        (rejected.owner, rejected.institution, rejected.currency): ImportValidationEngine().validate([rejected]),
    }

    snapshot = builder.build([warning, rejected], validation_reports=reports)

    assert [view.validation_status for view in snapshot.institution_snapshots] == [
        ImportValidationStatus.REJECTED,
        ImportValidationStatus.APPROVED_WITH_WARNINGS,
    ]
    assert snapshot.status is DailyPortfolioStatus.BLOCKED
    assert snapshot.summary.validation_error_count == 1
    assert snapshot.summary.validation_warning_count == 1


def test_validation_and_consolidation_warnings_produce_ready_with_warnings():
    validation_warning = DailyPortfolioSnapshotBuilder().build(
        [position(asset_subclass=None)]
    )
    duplicate_warning = DailyPortfolioSnapshotBuilder().build(
        [position(identifier="AAA"), position(identifier="AAA")]
    )

    assert validation_warning.status is DailyPortfolioStatus.READY_WITH_WARNINGS
    assert duplicate_warning.status is DailyPortfolioStatus.READY_WITH_WARNINGS
    assert duplicate_warning.consolidated.duplicate_count == 1
    assert duplicate_warning.summary.duplicate_count == 1


def test_snapshot_is_immutable_and_preserves_original_positions():
    original = position()
    copy = replace(original)
    snapshot = DailyPortfolioSnapshotBuilder().build([original])

    with pytest.raises(FrozenInstanceError):
        snapshot.status = DailyPortfolioStatus.BLOCKED
    with pytest.raises(TypeError):
        snapshot.consolidated.gross_value_by_currency["USD"] = Decimal("0")
    assert original == copy


def test_is_deterministic_except_for_generation_time_and_has_stable_ordering():
    items = [
        position("UBS", "Z", asset_class="z class", asset_subclass="z category"),
        position("Santander", "A", asset_class="A class", asset_subclass="A category"),
        position("Bradesco", "B", currency="BRL"),
    ]
    builder = DailyPortfolioSnapshotBuilder()

    forward = builder.build(items)
    reverse = builder.build(reversed(items))

    assert replace(forward, generated_at=reverse.generated_at) == reverse
    assert tuple(forward.consolidated.positions_by_class) == ("A class", "Equity", "z class")
    assert forward.institutions == ("Bradesco", "Santander", "UBS")


def test_preserves_an_explicit_reference_date_and_calculates_statistics():
    reference = date(2026, 7, 29)
    items = [
        position("UBS", "AAA", market_value=Decimal("25")),
        position("Santander", "AAA", market_value=Decimal("75")),
        position("Santander", "BBB", market_value=Decimal("50")),
    ]

    snapshot = DailyPortfolioSnapshotBuilder().build(items, reference_date=reference)

    assert snapshot.reference_date == reference
    assert snapshot.summary.institution_count == 2
    assert snapshot.summary.owner_count == 1
    assert snapshot.summary.original_position_count == 3
    assert snapshot.summary.consolidated_asset_count == 2
    assert snapshot.consolidated.position_count == 3
    assert snapshot.consolidated.gross_value_by_currency == {"USD": Decimal("150")}
    assert snapshot.consolidated.positions_by_institution == {"Santander": 2, "UBS": 1}
    assert snapshot.consolidated.positions_by_class == {"Equity": 3}
    assert snapshot.consolidated.positions_by_category == {"Stock": 3}
