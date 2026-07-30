from datetime import date, datetime, timezone
import http.client
import json
import threading
from http.server import ThreadingHTTPServer

import pytest

from backend.daily_facts_engine import DailyFactsEngine
from backend.market_agenda_engine import MarketAgendaEngine
from backend.market_connectors import (
    BcbMarketConnector,
    ConnectorCache,
    ConnectorManager,
    ConnectorUnavailableError,
    LocalMarketConnector,
)
from backend.official_portfolios import OfficialPortfolioLoader
from backend.server import ArgosRequestHandler, MARKET_CONNECTOR_MANAGER


NOW = datetime(2026, 7, 30, 15, tzinfo=timezone.utc)


def manager(connector=None) -> ConnectorManager:
    result = ConnectorManager(ConnectorCache(), clock=lambda: NOW)
    result.register("LOCAL", connector or LocalMarketConnector(), active=True)
    return result


def test_registers_selects_and_rejects_duplicate_connectors() -> None:
    connector = LocalMarketConnector()
    result = ConnectorManager()
    result.register("local", connector)
    assert result.active_connector == "LOCAL"
    with pytest.raises(ValueError, match="já registrado"):
        result.register("LOCAL", connector)
    with pytest.raises(KeyError, match="não registrado"):
        result.select("OTHER")


def test_unavailable_connector_does_not_replace_cache(tmp_path) -> None:
    result = manager(LocalMarketConnector(tmp_path / "missing"))
    with pytest.raises(ConnectorUnavailableError, match="indisponível"):
        result.reload()
    status = result.status()
    assert status["connector"] == "LOCAL" and status["available"] is False
    assert status["last_reload"] is None and status["facts"] == status["agenda"] == 0
    assert status["last_reload_success"] is None


def test_reload_populates_cache_with_canonical_models() -> None:
    result = manager()
    entry = result.reload()
    assert entry.last_reload == NOW
    assert entry.source == "data/market"
    assert entry.connector == "LOCAL" and entry.reload_succeeded is True
    assert result.load_facts() is entry.facts
    assert result.load_agenda() is entry.agenda
    assert result.status()["facts"] == len(entry.facts)
    assert result.status()["agenda"] == len(entry.agenda)


@pytest.fixture
def server():
    MARKET_CONNECTOR_MANAGER.reload()
    instance = ThreadingHTTPServer(("127.0.0.1", 0), ArgosRequestHandler)
    thread = threading.Thread(target=instance.serve_forever)
    thread.start()
    yield instance
    instance.shutdown()
    instance.server_close()
    thread.join()


def request(server, method: str, path: str) -> tuple[int, dict[str, object]]:
    connection = http.client.HTTPConnection("127.0.0.1", server.server_port)
    connection.request(method, path, body=b"", headers={"Content-Length": "0"})
    response = connection.getresponse()
    result = response.status, json.loads(response.read())
    connection.close()
    return result


def test_status_and_manual_reload_endpoints(server) -> None:
    status, before = request(server, "GET", "/api/market/status")
    assert status == 200
    assert {"active_connector", "fallback_available", "last_reload", "source"} <= set(before)
    assert before["active_connector"] in {"BCB", "LOCAL"}
    assert before["fallback_available"] is True

    status, after = request(server, "POST", "/api/market/reload")
    assert status == 200
    assert after["facts"] == before["facts"]
    assert after["agenda"] == before["agenda"]
    assert after["last_reload"] is not None


def test_connector_flow_preserves_existing_engines() -> None:
    result = manager()
    positions = OfficialPortfolioLoader().load_positions()
    facts = DailyFactsEngine().generate(positions, result.load_facts())
    agenda = MarketAgendaEngine().generate(result.load_agenda(), positions, date(2026, 7, 30))
    assert facts[0]["id"] == "bcb-focus-2026-07-30"
    assert agenda[0]["id"] == "agenda-bcb-copom-2026-08-05"


def bcb_transport(url: str, timeout: float):
    assert timeout == 2.0
    if "sgs.432" in url:
        return [{"data": "30/07/2026", "valor": "15.00"}]
    return {"conteudo": [{"dataReferencia": "2026-08-05"}]}


def remote_manager(transport=bcb_transport) -> ConnectorManager:
    result = ConnectorManager(ConnectorCache(), clock=lambda: NOW)
    result.register("BCB", BcbMarketConnector(transport), active=True)
    result.register("LOCAL", LocalMarketConnector())
    result.configure_fallback("BCB", "LOCAL")
    return result


def test_bcb_available_produces_only_canonical_models_and_remote_cache() -> None:
    result = remote_manager()
    entry = result.reload()
    assert entry.connector == "BCB" and entry.source == "BCB"
    assert entry.reload_succeeded is True and entry.error is None
    assert entry.facts[0].fact_id == "bcb-sgs-selic-meta-2026-07-30"
    assert entry.agenda[0].event_id == "bcb-copom-2026-08-05"
    assert result.status()["source"] == "REMOTE"


def test_bcb_unavailable_automatically_falls_back_and_records_failure() -> None:
    def unavailable(url: str, timeout: float):
        raise OSError("BCB offline")

    result = remote_manager(unavailable)
    entry = result.reload()
    assert result.active_connector == "LOCAL"
    assert entry.connector == "LOCAL" and entry.source == "data/market"
    assert entry.reload_succeeded is False and entry.error == "Conector de mercado indisponível: BCB."
    status = result.status()
    assert status["source"] == "LOCAL" and status["last_reload_success"] is False
    assert status["facts"] and status["agenda"]


def test_manual_reload_retries_preferred_bcb_after_fallback() -> None:
    calls = {"count": 0}

    def recovering(url: str, timeout: float):
        calls["count"] += 1
        if calls["count"] == 1:
            raise OSError("temporary")
        return bcb_transport(url, timeout)

    result = remote_manager(recovering)
    assert result.reload().connector == "LOCAL"
    assert result.reload().connector == "BCB"
    assert result.status()["last_reload_success"] is True
