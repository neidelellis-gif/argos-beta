from pathlib import Path

import pytest

from backend.connectors import registry, santander_connector, tipranks_connector, ubs_connector
from backend.connectors.contract import PortfolioConnector
from backend.connectors.errors import (
    ConnectorError,
    ConnectorFileNotFoundError,
    DuplicateConnectorIdError,
    EmptyPortfolioError,
    UnsupportedExtensionError,
)
from backend.connectors.registry import ConnectorRegistry
from backend.models import PortfolioOwner


CONNECTORS = (ubs_connector, santander_connector, tipranks_connector)


@pytest.mark.parametrize("connector", CONNECTORS)
def test_connectors_implement_official_contract(connector):
    assert isinstance(connector, PortfolioConnector)
    assert connector.connector_id
    assert connector.institution
    assert isinstance(connector.owner, PortfolioOwner)
    assert isinstance(connector.supported_extensions, frozenset)


def test_registry_lists_all_connectors_but_keeps_tipranks_out_of_active_upload():
    assert [connector.connector_id for connector in registry.all()] == [
        "ubs", "santander", "tipranks"
    ]
    assert [connector.connector_id for connector in registry.active()] == [
        "ubs", "santander"
    ]
    assert tipranks_connector in registry.for_extension(".csv")
    assert tipranks_connector not in registry.for_extension(".csv", active_only=True)


def test_registry_rejects_duplicate_connector_id():
    local_registry = ConnectorRegistry()
    local_registry.register(ubs_connector)
    with pytest.raises(DuplicateConnectorIdError):
        local_registry.register(ubs_connector)


@pytest.mark.parametrize("connector", CONNECTORS)
def test_connector_owner_metadata_is_used(connector, monkeypatch):
    monkeypatch.setattr(connector, "owner", PortfolioOwner.NEI)
    raw = {"institution": connector.institution}
    if connector is ubs_connector:
        raw.update(name="Asset", symbol="A", asset_class="Ação", currency="USD", value=1)
    elif connector is santander_connector:
        raw.update(name="Asset", symbol="A", asset_class="Ação", currency="USD", value=1)
    else:
        raw.update(name="Asset", ticker="A")
    assert connector._to_portfolio_position(raw, "source.csv").owner is PortfolioOwner.NEI


@pytest.mark.parametrize("connector", CONNECTORS)
def test_unsupported_extension_raises_typed_error(connector, tmp_path):
    path = tmp_path / "portfolio.txt"
    path.touch()
    with pytest.raises(UnsupportedExtensionError):
        connector.load_positions(path)


def test_recognition_is_separate_from_loading(monkeypatch, tmp_path):
    path = tmp_path / "ubs.csv"
    path.touch()
    monkeypatch.setattr(
        ubs_connector,
        "_read_rows",
        lambda _path: [["ACCOUNT NUMBER", "DESCRIPTION", "SYMBOL", "VALUE"]],
    )
    monkeypatch.setattr(
        ubs_connector,
        "load_positions",
        lambda _path: pytest.fail("recognize must not call load_positions"),
    )
    assert ubs_connector.recognize(path) is True


def test_tipranks_recognizes_headers_without_parsing_positions(tmp_path):
    path = tmp_path / "portfolio.csv"
    path.write_text("Ticker,No. of Shares\n", encoding="utf-8")
    assert tipranks_connector.recognize(path) is True


def test_recognized_empty_tipranks_file_raises_typed_error(tmp_path):
    path = tmp_path / "portfolio.csv"
    path.write_text("Ticker,No. of Shares\n", encoding="utf-8")
    with pytest.raises(EmptyPortfolioError):
        tipranks_connector.load_positions(path)


def test_missing_file_raises_typed_connector_error(tmp_path):
    missing = tmp_path / "missing.csv"
    with pytest.raises(ConnectorFileNotFoundError) as error:
        ubs_connector.load_positions(missing)
    assert isinstance(error.value, ConnectorError)


@pytest.mark.parametrize("connector", CONNECTORS)
def test_load_positions_returns_tuple(connector, monkeypatch, tmp_path):
    suffix = next(iter(connector.supported_extensions))
    path = tmp_path / f"portfolio{suffix}"
    path.touch()
    if connector is ubs_connector:
        monkeypatch.setattr(connector, "_read_rows", lambda _: [
            ["ACCOUNT NUMBER", "DESCRIPTION", "SYMBOL", "VALUE"],
            ["1", "Asset", "A", 1],
        ])
    elif connector is santander_connector:
        monkeypatch.setattr(connector, "_read_rows", lambda _: [
            ["NOME DO ATIVO", "ISIN", "SALDO MOEDA REFERÊNCIA", "PESO DA CONTA (%)"],
            ["Asset", "A", 1, 100],
        ])
    else:
        monkeypatch.setattr(connector, "_read_positions", lambda _: [{
            "institution": "TipRanks", "ticker": "A", "name": "Asset"
        }])
    positions = connector.load_positions(path)
    assert isinstance(positions, tuple)
    assert positions[0].institution == connector.institution
    assert positions[0].owner == connector.owner
    assert positions[0].source_file == path.name
