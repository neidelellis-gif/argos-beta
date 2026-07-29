from collections import Counter
from decimal import Decimal
from pathlib import Path

import pytest

from backend.connectors import bradesco_connector
from backend.connectors.errors import UnsupportedExtensionError
from backend.models import PortfolioOwner


FIXTURE = Path("tests/fixtures/bradesco_private_fixture_oficial_marco_8_2b.txt")


def _by_name(positions, prefix):
    return next(item for item in positions if item.asset_name.startswith(prefix))


def test_recognizes_only_the_official_bradesco_text_layout(tmp_path):
    assert bradesco_connector.recognize(FIXTURE)
    unrelated = tmp_path / "portfolio.txt"
    unrelated.write_text("Posição Detalhada dos Investimentos", encoding="utf-8")
    assert not bradesco_connector.recognize(unrelated)


def test_rejects_non_text_reports():
    with pytest.raises(UnsupportedExtensionError, match="TXT"):
        bradesco_connector.load_positions(Path("relatorio.pdf"))


def test_maps_official_rows_to_nei_without_inventing_missing_fields():
    positions = bradesco_connector.load_positions(FIXTURE)
    cdb = _by_name(positions, "CDB - BANCO BRADESCO")

    assert cdb.owner is PortfolioOwner.NEI
    assert cdb.institution == "Bradesco"
    assert cdb.asset_class == "CDB"
    assert cdb.asset_subclass == "PÓS-FIXADO"
    assert cdb.quantity == Decimal("0.00")
    assert cdb.unit_price == Decimal("89526.22")
    assert cdb.market_value == Decimal("91457.04")
    assert cdb.portfolio_weight == Decimal("12.45")
    assert cdb.account is None
    assert cdb.identifier is None
    assert cdb.reference_date is None
    assert cdb.currency == "BRL"


def test_preserves_wrapped_names_and_parenthesized_values():
    positions = bradesco_connector.load_positions(FIXTURE)
    debenture = _by_name(positions, "DEBÊNTURES - CONCESSIONARIA")
    explorer = _by_name(positions, "BRADESCO EXPLORER PRIVATE")
    fii = _by_name(positions, "FUNDO CSHG")
    previdencia = _by_name(positions, "BRADESCO PRIVATE PERFORMANCE")
    western = _by_name(positions, "WESTERN ASSET")

    assert debenture.asset_name == "DEBÊNTURES - CONCESSIONARIA RODOVIAS DO TIETE S."
    assert debenture.asset_subclass == "PRÉ-FIXADO"
    assert explorer.asset_class == "Private Equity"
    assert explorer.asset_subclass == "PRIVATE EQUITY"
    assert fii.market_value == Decimal("24160.00")
    assert previdencia.quantity == Decimal("33773.35")
    assert previdencia.market_value == Decimal("61814.95")
    assert western.asset_name == "WESTERN ASSET US INDEX 500 FIC MM"
    assert western.asset_subclass == "RENDA VARIÁVEL"


def test_does_not_parse_totals_headers_or_previdencia_as_positions():
    positions = bradesco_connector.load_positions(FIXTURE)
    assert positions
    assert all(not item.asset_name.startswith("Total") for item in positions)
    assert all("Código da Carteira" not in item.asset_name for item in positions)


def test_reconciles_official_position_counts_and_gross_value():
    positions = bradesco_connector.load_positions(FIXTURE)

    assert Counter(item.asset_class for item in positions) == {
        "CDB": 5,
        "Debêntures": 1,
        "ETF": 3,
        "Fundos": 5,
        "Ações": 1,
        "Multimercados": 5,
        "FIIs": 3,
        "Private Equity": 27,
    }
    assert len(positions) == 50
    assert sum(item.market_value for item in positions) == Decimal("734375.98")
