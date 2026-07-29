import base64
import http.client
import json
import threading
from http.server import ThreadingHTTPServer
from unittest.mock import patch

import pytest

from backend.server import ArgosRequestHandler


@pytest.fixture
def server():
    instance = ThreadingHTTPServer(("127.0.0.1", 0), ArgosRequestHandler)
    thread = threading.Thread(target=instance.serve_forever)
    thread.start()
    yield instance
    instance.shutdown()
    thread.join()
    instance.server_close()


def request(server, method, path, payload=None):
    connection = http.client.HTTPConnection("127.0.0.1", server.server_port)
    body = json.dumps(payload).encode() if payload is not None else None
    headers = {"Content-Type": "application/json"} if body else {}
    connection.request(method, path, body=body, headers=headers)
    response = connection.getresponse()
    result = response.status, json.loads(response.read())
    connection.close()
    return result


def official_dashboard():
    return {
        "header": {"version": "unchanged"},
        "daily": {"important_facts": [{"id": "official-fact"}]},
        "consolidated": {"position_count": 2},
    }


def test_legacy_get_endpoints_project_the_unchanged_official_dashboard(server):
    dashboard = official_dashboard()

    with patch("backend.server.load_dashboard", return_value=dashboard) as load:
        dashboard_status, dashboard_payload = request(
            server, "GET", "/api/dashboard"
        )
        cockpit_status, cockpit_payload = request(server, "GET", "/api/cockpit")
        facts_status, facts_payload = request(server, "GET", "/api/facts")

    assert dashboard_status == cockpit_status == facts_status == 200
    assert dashboard_payload == dashboard
    assert cockpit_payload == {"ok": True, "cockpit": dashboard}
    assert facts_payload == {
        "ok": True,
        "facts": dashboard["daily"]["important_facts"],
    }
    assert load.call_count == 3


def test_legacy_analyze_delegates_to_official_import_dashboard_flow(server):
    dashboard = official_dashboard()
    imported_paths = []

    def official_import(paths):
        imported_paths.extend(paths)
        assert [path.read_bytes() for path in paths] == [b"ubs", b"santander"]
        return {"positions": (), "dashboard": dashboard}

    payload = {
        "portfolio": "JOLIKA",
        "files": {
            "ubs": {
                "name": "ubs.csv",
                "content": base64.b64encode(b"ubs").decode(),
            },
            "santander": {
                "name": "santander.xlsx",
                "content": base64.b64encode(b"santander").decode(),
            },
        },
    }

    with patch(
        "backend.server.import_portfolios",
        side_effect=official_import,
    ) as load:
        status, response = request(server, "POST", "/api/analyze", payload)

    assert status == 200
    assert response == {"ok": True, "result": dashboard}
    load.assert_called_once()
    assert imported_paths
    assert all(not path.exists() for path in imported_paths)
