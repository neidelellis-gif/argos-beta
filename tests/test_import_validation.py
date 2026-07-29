from dataclasses import replace
from decimal import Decimal
import operator
from collections.abc import MutableMapping
from typing import cast

import pytest

from backend.connectors import bradesco_connector, santander_connector, ubs_connector
from backend.import_validation import ImportValidationEngine, ImportValidationStatus
from backend.models import PortfolioOwner, PortfolioPosition


def _set_read_only_mapping(mapping: object, key: object, value: object) -> None:
    """Exercise MappingProxyType without declaring a mutable contract."""
    operator.setitem(cast(MutableMapping[object, object], mapping), key, value)


def _position(institution="UBS", owner=PortfolioOwner.JOLIKA, **changes):
    position = PortfolioPosition(
        institution=institution,
        owner=owner,
        account="account-1",
        asset_class="Equity",
        asset_subclass="Stock",
        asset_name="Example Asset",
        identifier="EXAMPLE",
        identifier_type="Ticker",
        quantity=Decimal("2"),
        unit_price=Decimal("50"),
        market_value=Decimal("100"),
        currency="USD",
        portfolio_weight=Decimal("1"),
        reference_date=None,
        source_file="portfolio.csv",
    )
    return replace(position, **changes)


@pytest.mark.parametrize(
    ("connector", "owner"),
    (
        (ubs_connector, PortfolioOwner.JOLIKA),
        (santander_connector, PortfolioOwner.JOLIKA),
        (bradesco_connector, PortfolioOwner.NEI),
    ),
)
def test_validates_official_connector_institutions(connector, owner):
    report = ImportValidationEngine().validate((_position(connector.institution, owner),))

    assert report.status is ImportValidationStatus.APPROVED
    assert report.errors == ()
    assert report.statistics.total_positions == 1
    assert report.statistics.gross_value == Decimal("100")
    assert report.statistics.positions_by_class == {"Equity": 1}
    assert report.statistics.positions_by_category == {"Stock": 1}


def test_rejects_empty_portfolio():
    report = ImportValidationEngine().validate(())

    assert report.status is ImportValidationStatus.REJECTED
    assert report.statistics.total_positions == 0
    assert report.statistics.error_count == 1


def test_reports_duplicate_assets_without_rejecting_import():
    report = ImportValidationEngine().validate((_position(), _position()))

    assert report.status is ImportValidationStatus.APPROVED_WITH_WARNINGS
    assert report.statistics.alert_count == 1
    assert "duplicate" in report.warnings[0]


def test_rejects_missing_required_identification_fields():
    report = ImportValidationEngine().validate(
        (_position(institution="Unknown", asset_name=" ", currency=None),)
    )

    assert report.status is ImportValidationStatus.REJECTED
    assert report.statistics.error_count == 3


def test_reports_missing_class_and_category_as_quality_alerts():
    report = ImportValidationEngine().validate(
        (_position(asset_class=None, asset_subclass=None),)
    )

    assert report.status is ImportValidationStatus.APPROVED_WITH_WARNINGS
    assert report.statistics.alert_count == 2
    assert report.statistics.positions_by_class == {}
    assert report.statistics.positions_by_category == {}


@pytest.mark.parametrize("market_value", (None, Decimal("-1"), Decimal("NaN")))
def test_rejects_invalid_market_values(market_value):
    report = ImportValidationEngine().validate((_position(market_value=market_value),))

    assert report.status is ImportValidationStatus.REJECTED
    assert report.statistics.gross_value == Decimal("0")
    assert report.statistics.error_count == 1


def test_rejects_an_empty_position_without_mutating_it():
    position = _position(
        asset_name=None,
        identifier=None,
        asset_class=None,
        asset_subclass=None,
        quantity=None,
        market_value=None,
    )

    report = ImportValidationEngine().validate((position,))

    assert report.status is ImportValidationStatus.REJECTED
    assert "Position 1 is empty" in report.errors
    assert position.asset_name is None


def test_report_statistics_are_deeply_immutable():
    report = ImportValidationEngine().validate((_position(),))

    with pytest.raises(TypeError):
        _set_read_only_mapping(report.statistics.positions_by_class, "Mutated", 1)
    with pytest.raises(TypeError):
        _set_read_only_mapping(report.statistics.positions_by_category, "Mutated", 1)
