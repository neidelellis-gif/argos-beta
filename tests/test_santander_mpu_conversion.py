from decimal import Decimal
from pathlib import Path

from backend.connectors import santander_connector
from backend.models import PortfolioOwner, PortfolioPosition


def test_converts_santander_position_to_mpu():
    position = santander_connector._to_portfolio_position(
        {
            "institution": "Santander",
            "account": "12345",
            "symbol": "US0000000001",
            "name": "Título exemplo",
            "description": "Título exemplo",
            "asset_class": "Renda Fixa",
            "currency": "USD",
            "value": 1234.56,
            "weight": 12.5,
        },
        "carteira.xlsx",
    )

    assert position == PortfolioPosition(
        institution="Santander",
        owner=PortfolioOwner.JOLIKA,
        account="12345",
        asset_class="Renda Fixa",
        asset_subclass=None,
        asset_name="Título exemplo",
        identifier="US0000000001",
        identifier_type=None,
        quantity=None,
        unit_price=None,
        market_value=Decimal("1234.56"),
        currency="USD",
        portfolio_weight=Decimal("12.5"),
        reference_date=None,
        source_file="carteira.xlsx",
    )


def test_uses_none_for_information_missing_from_santander_export():
    position = santander_connector._to_portfolio_position(
        {
            "institution": "Santander",
            "account": "",
            "symbol": "",
            "name": "Caixa",
            "asset_class": "Caixa",
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
    path = tmp_path / "santander.xlsx"
    path.touch()
    monkeypatch.setattr(
        santander_connector,
        "_read_rows",
        lambda _path: [
            [
                "RENDA VARIÁVEL AÇÕES",
                "ISIN",
                "SALDO MOEDA REFERÊNCIA",
                "MOEDA",
            ],
            ["Fundo exemplo", "US0000000001", 250.25, "USD"],
        ],
    )

    positions = santander_connector.load_positions(path)

    assert len(positions) == 1
    assert isinstance(positions[0], PortfolioPosition)
    assert positions[0].asset_name == "Fundo exemplo"
    assert positions[0].identifier == "US0000000001"
    assert positions[0].market_value == Decimal("250.25")
    assert positions[0].source_file == "santander.xlsx"
    assert positions[0].owner is PortfolioOwner.JOLIKA


def test_uses_reference_currency_when_value_comes_from_reference_balance(monkeypatch, tmp_path):
    path = tmp_path / "your-positions-4005106-17 2.xlsx"
    path.touch()
    monkeypatch.setattr(
        santander_connector,
        "_read_rows",
        lambda _path: [
            ["RESUMO DE ATIVOS"],
            ["NOME DO ATIVO", "SALDO", "MOEDA", "PESO DA CONTA (%)"],
            ["TOTAL", 3082326.18, "USD", 100],
            [
                "RENDA VARIÁVEL EUROPA AÇÕES",
                "ISIN",
                "NOME DA CARTEIRA",
                "VALOR DO MERCADO",
                "MOEDA",
                "SALDO MOEDA REFERÊNCIA",
                "MOEDA",
                "PESO DA CONTA (%)",
            ],
            [
                "SCHNEIDER ELECTRIC SE",
                "FR0000121972",
                "02 - Advisory",
                85000,
                "EUR",
                92179.34,
                "USD",
                "2.99",
            ],
            [
                "LIQUIDEZ",
                "NOME DA CARTEIRA",
                "NUMERO DE CONTA",
                "VALOR DO MERCADO",
                "MOEDA",
                "SALDO MOEDA REFERÊNCIA",
                "MOEDA",
                "PESO DA CONTA (%)",
            ],
            [
                "DDA CUSTODIAL CASH ACCOUNTS",
                "02 - Advisory",
                "115111444",
                80000,
                "EUR",
                90000,
                "USD",
                "2.92",
            ],
        ],
    )

    positions = santander_connector.load_positions(path)

    assert len(positions) == 2
    assert positions[0].asset_name.startswith("SCHNEIDER ELECTRIC SE")
    assert positions[0].market_value == Decimal("92179.34")
    assert positions[0].currency == "USD"
    assert positions[1].asset_class == "Caixa"
    assert positions[1].account == "115111444"
    assert positions[1].market_value == Decimal("90000")
    assert positions[1].currency == "USD"


def test_real_santander_file_total_uses_only_usd_reference_currency_when_available():
    path = Path("your-positions-4005106-17 2.xlsx")
    if not path.exists():
        import pytest

        pytest.skip("Arquivo real your-positions-4005106-17 2.xlsx não está disponível no workspace.")

    positions = santander_connector.load_positions(path)
    total = sum(position.market_value for position in positions)

    assert {position.currency for position in positions} == {"USD"}
    assert abs(total - Decimal("3082326.18")) <= Decimal("0.05")
