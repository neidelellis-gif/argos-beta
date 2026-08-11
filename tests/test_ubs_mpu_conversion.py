from decimal import Decimal

from backend.connectors import ubs_connector
from backend.models import PortfolioOwner, PortfolioPosition


def test_converts_ubs_position_to_mpu():
    position = ubs_connector._to_portfolio_position(
        {
            "institution": "UBS",
            "account": "R2 16003",
            "symbol": "GLD",
            "name": "GLD",
            "description": "SPDR Gold Shares",
            "asset_class": "Ação",
            "currency": "USD",
            "value": 1234.56,
            "weight": 12.5,
        },
        "carteira.csv",
    )

    assert position == PortfolioPosition(
        institution="UBS",
        owner=PortfolioOwner.JOLIKA,
        account="R2 16003",
        asset_class="Ação",
        asset_subclass=None,
        asset_name="GLD",
        identifier="GLD",
        identifier_type="ticker",
        quantity=None,
        unit_price=None,
        market_value=Decimal("1234.56"),
        currency="USD",
        portfolio_weight=Decimal("12.5"),
        reference_date=None,
        source_file="carteira.csv",
    )


def test_uses_none_for_information_missing_from_ubs_export():
    position = ubs_connector._to_portfolio_position(
        {
            "institution": "UBS",
            "account": "",
            "symbol": "N/A",
            "name": "UBS CASH RESERVE",
            "asset_class": "Outros",
            "currency": "USD",
            "value": 100,
            "weight": None,
        },
        "carteira.xlsx",
    )

    assert position.account is None
    assert position.asset_subclass is None
    assert position.identifier is None
    assert position.identifier_type is None
    assert position.quantity is None
    assert position.unit_price is None
    assert position.portfolio_weight is None
    assert position.reference_date is None


def test_load_positions_returns_mpu_positions(monkeypatch, tmp_path):
    path = tmp_path / "ubs.csv"
    path.touch()
    monkeypatch.setattr(
        ubs_connector,
        "_read_rows",
        lambda _path: [
            ["ACCOUNT NUMBER", "DESCRIPTION", "SYMBOL", "MARKET VALUE"],
            ["R2 16003", "SPDR Gold Shares", "GLD", "1,250.25"],
        ],
    )

    positions = ubs_connector.load_positions(path)

    assert len(positions) == 1
    assert isinstance(positions[0], PortfolioPosition)
    assert positions[0].asset_name == "GLD"
    assert positions[0].identifier == "GLD"
    assert positions[0].market_value == Decimal("1250.25")
    assert positions[0].source_file == "ubs.csv"
    assert positions[0].owner is PortfolioOwner.JOLIKA

def test_uses_cusip_when_symbol_is_missing():
    position = ubs_connector._to_portfolio_position(
        {
            "institution": "UBS",
            "account": "R2 16003",
            "symbol": "N/A",
            "cusip": "24703TAG1",
            "name": "DELL INTL",
            "description": "DELL INTL",
            "asset_class": "Renda Fixa",
            "currency": "USD",
            "value": 81056.80,
            "weight": None,
        },
        "carteira.csv",
    )

    assert position.identifier == "24703TAG1"
    assert position.identifier_type == "cusip"


def test_classifies_cash_reserve_as_cash():
    assert ubs_connector.classify_asset(
        "N/A",
        "UBS CASH RESERVE",
    ) == "Caixa"
