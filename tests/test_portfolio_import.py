import http.client
import json
import threading
from datetime import date
from decimal import Decimal
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

import pytest

from backend.server import (
    ArgosRequestHandler,
    SESSION_PORTFOLIOS,
)
from backend.models import PortfolioOwner, PortfolioPosition


UBS_FIXTURE = Path("frontend/test/fixtures/UBS_Holdings_27_07_2026.csv")


def multipart(files):
    boundary = "argos-test-boundary"
    chunks = []
    for name, content in files:
        chunks.extend([
            f"--{boundary}\r\n".encode(),
            (
                'Content-Disposition: form-data; name="files"; '
                f'filename="{name}"\r\n'
                "Content-Type: application/octet-stream\r\n\r\n"
            ).encode(),
            content,
            b"\r\n",
        ])
    chunks.append(f"--{boundary}--\r\n".encode())
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


@pytest.fixture
def server():
    SESSION_PORTFOLIOS.clear()
    instance = ThreadingHTTPServer(("127.0.0.1", 0), ArgosRequestHandler)
    thread = threading.Thread(target=instance.serve_forever)
    thread.start()
    yield instance
    instance.shutdown()
    instance.server_close()
    thread.join()
    SESSION_PORTFOLIOS.clear()


def post_files(server, files):
    body, content_type = multipart(files)
    connection = http.client.HTTPConnection("127.0.0.1", server.server_port)
    connection.request(
        "POST",
        "/api/portfolios/import",
        body=body,
        headers={"Content-Type": content_type, "Content-Length": len(body)},
    )
    response = connection.getresponse()
    payload = json.loads(response.read())
    cookie = response.getheader("Set-Cookie")
    connection.close()
    return response.status, payload, cookie


def session_position(institution, identifier, value):
    return PortfolioPosition(
        institution=institution,
        owner=PortfolioOwner.JOLIKA,
        account=None,
        asset_class=None,
        asset_subclass=None,
        asset_name=identifier,
        identifier=identifier,
        identifier_type="ticker",
        quantity=Decimal("1"),
        unit_price=Decimal(value),
        market_value=Decimal(value),
        currency="USD",
        portfolio_weight=Decimal("100"),
        reference_date=date(2026, 7, 28),
        source_file=f"{institution}.csv",
    )


def request_with_cookie(server, method, path, cookie):
    connection = http.client.HTTPConnection("127.0.0.1", server.server_port)
    connection.request(method, path, headers={"Cookie": cookie})
    response = connection.getresponse()
    payload = json.loads(response.read())
    connection.close()
    return response.status, payload


def test_upload_one_file(server):
    status, payload, cookie = post_files(
        server, [(UBS_FIXTURE.name, UBS_FIXTURE.read_bytes())]
    )

    assert status == 200
    assert payload["ok"] is True
    assert payload["files"] == [{
        "name": UBS_FIXTURE.name,
        "institution": "UBS",
        "position_count": 28,
    }]
    assert payload["diagnostics"][0]["institution"] == "UBS"
    assert cookie is not None
    assert cookie.startswith("argos_session=")


def test_upload_multiple_files(server):
    content = UBS_FIXTURE.read_bytes()
    status, payload, _ = post_files(
        server,
        [("ubs-primary.csv", content), ("ubs-secondary.csv", content)],
    )

    assert status == 200
    assert len(payload["files"]) == 2
    assert payload["diagnostics"] == [{
        "institution": "UBS",
        "position_count": 56,
        "warnings": payload["diagnostics"][0]["warnings"],
    }]
    assert payload["dashboard"]["consolidated"]["position_count"] == 56


def test_invalid_file(server):
    status, payload, cookie = post_files(server, [("notes.pdf", b"hello")])

    assert status == 400
    assert "Arquivo inválido" in payload["error"]
    assert cookie is None


def test_unrecognized_text_file(server):
    status, payload, cookie = post_files(server, [("notes.txt", b"hello")])

    assert status == 400
    assert "Instituição não reconhecida" in payload["error"]
    assert cookie is None


def test_unrecognized_institution(server):
    status, payload, cookie = post_files(
        server, [("portfolio.csv", b"Asset,Value\nExample,100\n")]
    )

    assert status == 400
    assert "Instituição não reconhecida" in payload["error"]
    assert cookie is None


def test_dashboard_uses_current_session_after_import(server):
    _, imported, set_cookie = post_files(
        server, [(UBS_FIXTURE.name, UBS_FIXTURE.read_bytes())]
    )
    assert set_cookie is not None
    cookie = set_cookie.split(";", 1)[0]
    connection = http.client.HTTPConnection("127.0.0.1", server.server_port)
    connection.request("GET", "/api/dashboard", headers={"Cookie": cookie})
    response = connection.getresponse()
    dashboard = json.loads(response.read())
    connection.close()

    assert response.status == 200
    assert dashboard["session"] == imported["dashboard"]["session"]
    assert dashboard["institutions"] == imported["dashboard"]["institutions"]
    assert dashboard["consolidated"] == imported["dashboard"]["consolidated"]
    assert [fact["id"] for fact in dashboard["daily"]["important_facts"]] == [
        fact["id"]
        for fact in imported["dashboard"]["daily"]["important_facts"]
    ]
    assert (
        dashboard["daily"]["generated_at"]
        >= imported["dashboard"]["daily"]["generated_at"]
    )
    assert dashboard["institutions"][0]["name"] == "UBS"
    assert dashboard["consolidated"]["position_count"] == 28


def test_sequential_import_replaces_only_the_reimported_institution(server):
    imports = [
        (session_position("Santander", "SAN-ANTIGO", "100"),),
        (session_position("UBS", "UBS-1", "200"),),
        (session_position("Santander", "SAN-NOVO", "300"),),
    ]

    def fake_import(_paths):
        positions = imports.pop(0)
        return {"positions": positions, "files": [], "diagnostics": []}

    with patch("backend.server.import_portfolios", side_effect=fake_import):
        _, first, set_cookie = post_files(server, [("santander.xlsx", b"1")])
        assert set_cookie is not None
        cookie = set_cookie.split(";", 1)[0]

        body, content_type = multipart([("ubs.csv", b"2")])
        connection = http.client.HTTPConnection("127.0.0.1", server.server_port)
        connection.request("POST", "/api/portfolios/import", body=body, headers={
            "Content-Type": content_type,
            "Content-Length": len(body),
            "Cookie": cookie,
        })
        second_response = connection.getresponse()
        second = json.loads(second_response.read())
        connection.close()

        body, content_type = multipart([("santander.xlsx", b"3")])
        connection = http.client.HTTPConnection("127.0.0.1", server.server_port)
        connection.request("POST", "/api/portfolios/import", body=body, headers={
            "Content-Type": content_type,
            "Content-Length": len(body),
            "Cookie": cookie,
        })
        third_response = connection.getresponse()
        third = json.loads(third_response.read())
        connection.close()

    assert first["dashboard"]["session"]["analyzed_institutions"] == ["Santander"]
    assert second["dashboard"]["session"]["analyzed_institutions"] == [
        "Santander", "UBS",
    ]
    assert third["dashboard"]["session"]["analyzed_institutions"] == [
        "Santander", "UBS",
    ]
    positions = SESSION_PORTFOLIOS[cookie.split("=", 1)[1]]["positions"]
    assert [(item.institution, item.identifier) for item in positions] == [
        ("UBS", "UBS-1"),
        ("Santander", "SAN-NOVO"),
    ]
    assert third["dashboard"]["consolidated"]["totals_by_currency"] == {
        "USD": "500",
    }


def test_clear_all_portfolios_empties_session_and_dashboard(server):
    _, _, set_cookie = post_files(
        server, [(UBS_FIXTURE.name, UBS_FIXTURE.read_bytes())]
    )
    assert set_cookie is not None
    cookie = set_cookie.split(";", 1)[0]

    status, payload = request_with_cookie(
        server, "DELETE", "/api/portfolios", cookie
    )

    assert status == 200
    assert payload["ok"] is True
    assert payload["dashboard"]["institutions"] == []
    assert payload["dashboard"]["consolidated"]["position_count"] == 0
    assert cookie.split("=", 1)[1] not in SESSION_PORTFOLIOS
