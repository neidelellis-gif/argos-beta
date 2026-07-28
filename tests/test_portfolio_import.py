import http.client
import json
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from backend.server import (
    ArgosRequestHandler,
    SESSION_PORTFOLIOS,
)


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
    status, payload, cookie = post_files(server, [("notes.txt", b"hello")])

    assert status == 400
    assert "Arquivo inválido" in payload["error"]
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
    cookie = set_cookie.split(";", 1)[0]
    connection = http.client.HTTPConnection("127.0.0.1", server.server_port)
    connection.request("GET", "/api/dashboard", headers={"Cookie": cookie})
    response = connection.getresponse()
    dashboard = json.loads(response.read())
    connection.close()

    assert response.status == 200
    assert dashboard == imported["dashboard"]
    assert dashboard["institutions"][0]["name"] == "UBS"
    assert dashboard["consolidated"]["position_count"] == 28
