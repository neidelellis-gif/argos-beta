from decimal import Decimal

from backend.connectors import tipranks_connector
from backend.models import PortfolioOwner, PortfolioPosition


def test_converts_all_available_tipranks_fields_to_mpu():
    position = tipranks_connector._to_portfolio_position(
        {
            "institution": "TipRanks",
            "ticker": "ICE",
            "name": "Intercontinental Exchange",
            "shares": Decimal("10"),
            "price": Decimal("175.00"),
            "holding_value": Decimal("1750.00"),
        },
        "portfolio.csv",
    )

    assert position == PortfolioPosition(
        institution="TipRanks",
        owner=PortfolioOwner.JOLIKA,
        account=None,
        asset_class=None,
        asset_subclass=None,
        asset_name="Intercontinental Exchange",
        identifier="ICE",
        identifier_type="Ticker",
        quantity=Decimal("10"),
        unit_price=Decimal("175.00"),
        market_value=Decimal("1750.00"),
        currency=None,
        portfolio_weight=None,
        reference_date=None,
        source_file="portfolio.csv",
    )


def test_uses_none_for_unavailable_tipranks_fields():
    position = tipranks_connector._to_portfolio_position(
        {"institution": "TipRanks", "ticker": None, "name": None},
        "portfolio.csv",
    )

    assert position.account is None
    assert position.asset_class is None
    assert position.asset_name is None
    assert position.identifier is None
    assert position.identifier_type is None
    assert position.quantity is None
    assert position.unit_price is None
    assert position.market_value is None
    assert position.currency is None


def test_load_positions_returns_decimal_mpu_positions(tmp_path):
    path = tmp_path / "tipranks.csv"
    path.write_text(
        "Ticker,Name,No. of Shares,Price,Holding Value,Smart Score\n"
        'ICE,Intercontinental Exchange,10,$175.00,"$1,750.00",9\n',
        encoding="utf-8",
    )

    positions = tipranks_connector.load_positions(path)

    assert len(positions) == 1
    assert isinstance(positions[0], PortfolioPosition)
    assert positions[0].quantity == Decimal("10")
    assert positions[0].unit_price == Decimal("175.00")
    assert positions[0].market_value == Decimal("1750.00")
