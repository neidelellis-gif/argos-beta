import http.client
import json
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from backend.server import ArgosRequestHandler, SESSION_MARKET_AGENDA, SESSION_PORTFOLIOS
from tests.test_portfolio_import import multipart


@pytest.fixture
def server():
    SESSION_MARKET_AGENDA.clear()
    SESSION_PORTFOLIOS.clear()
    instance = ThreadingHTTPServer(("127.0.0.1", 0), ArgosRequestHandler)
    thread = threading.Thread(target=instance.serve_forever)
    thread.start()
    yield instance
    instance.shutdown()
    instance.server_close()
    thread.join()
    SESSION_MARKET_AGENDA.clear()
    SESSION_PORTFOLIOS.clear()


def request(server, method, path, body=b"", content_type=None, cookie=None):
    headers = {"Content-Length": len(body)}
    if content_type:
        headers["Content-Type"] = content_type
    if cookie:
        headers["Cookie"] = cookie
    connection = http.client.HTTPConnection("127.0.0.1", server.server_port)
    connection.request(method, path, body=body, headers=headers)
    response = connection.getresponse()
    result = response.status, json.loads(response.read()), response.getheader("Set-Cookie")
    connection.close()
    return result


def test_import_get_invalid_preserves_and_delete(server):
    valid = Path("frontend/test/fixtures/market_agenda_valid.json").read_bytes()
    body, content_type = multipart([("agenda.json", valid)])
    status, payload, set_cookie = request(server, "POST", "/api/market-agenda/import", body, content_type)
    assert status == 200 and payload["ok"] is True and payload["count"] == 1
    assert set_cookie is not None
    cookie = set_cookie.split(";", 1)[0]
    status, current, _ = request(server, "GET", "/api/market-agenda", cookie=cookie)
    assert status == 200 and current["events"] == payload["events"]
    daily_body = json.dumps({
        "positions": [{
            "institution": "UBS", "owner": "JOLIKA", "account": None,
            "asset_class": "FIXED_INCOME", "asset_subclass": None,
            "asset_name": "Treasury", "identifier": "UST", "identifier_type": "TICKER",
            "quantity": "1", "unit_price": None, "market_value": None,
            "currency": "USD", "portfolio_weight": None, "reference_date": None,
            "source_file": "test.csv",
        }],
        "fact_candidates": [], "reference_date": "2026-07-30",
    }).encode()
    status, daily, _ = request(
        server, "POST", "/api/daily-experience", daily_body, "application/json", cookie
    )
    assert status == 200 and daily["status"] == "SUCCESS" and daily["error"] is None
    assert daily["contract_version"] == "1.4" and len(daily["market_agenda"]) == 1
    assert len(daily["impact_assessments"]) == 1
    assert set(daily["impact_assessments"][0]) == {
        "id", "source_type", "impact_level", "impact_direction", "confidence",
        "title", "summary", "affected_assets", "impact_factors",
    }
    assert daily["impact_assessments"][0]["source_type"] == "MARKET_EVENT"
    assert not ({"source_id", "affected_positions", "related_facts", "related_events"}
                & daily["impact_assessments"][0].keys())
    assert set(daily["market_agenda"][0]) == {
        "id", "event_type", "importance", "title", "summary", "event_date",
        "event_time", "timezone", "all_day", "affected_assets", "source_name",
    }
    session_id = cookie.split("=", 1)[1]
    before = SESSION_MARKET_AGENDA[session_id]
    invalid = Path("frontend/test/fixtures/market_agenda_invalid.json").read_bytes()
    body, content_type = multipart([("invalid.json", invalid)])
    status, failed, _ = request(server, "POST", "/api/market-agenda/import", body, content_type, cookie)
    assert status == 400 and failed["ok"] is False
    assert SESSION_MARKET_AGENDA[session_id] is before
    status, cleared, _ = request(server, "DELETE", "/api/market-agenda", cookie=cookie)
    assert status == 200 and cleared == {"ok": True, "events": [], "count": 0}
    assert session_id not in SESSION_MARKET_AGENDA
