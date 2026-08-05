import base64
import http.client
import json
import threading
from datetime import date
from decimal import Decimal
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

import pytest
import zipfile
from xml.sax.saxutils import escape

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
        chunks.extend(
            [
                f"--{boundary}\r\n".encode(),
                (
                    'Content-Disposition: form-data; name="files"; '
                    f'filename="{name}"\r\n'
                    "Content-Type: application/octet-stream\r\n\r\n"
                ).encode(),
                content,
                b"\r\n",
            ]
        )
    chunks.append(f"--{boundary}--\r\n".encode())
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


def santander_real_structure_workbook(tmp_path):
    path = tmp_path / "your-positions-4005106-17 2.xlsx"
    rows = [
        ["RESUMO DE ATIVOS"],
        [
            "RENDA FIXA",
            8,
            "SALDO NA MOEDA DE REFERÊNCIA",
            1106902.92,
            "USD",
            "PESO DA CONTA (%)",
            "35.91%",
        ],
        [
            "RENDA VARIÁVEL",
            4,
            "SALDO NA MOEDA DE REFERÊNCIA",
            600000.00,
            "USD",
            "PESO DA CONTA (%)",
            "19.47%",
        ],
        [
            "FUNDOS ALTERNATIVOS",
            2,
            "SALDO NA MOEDA DE REFERÊNCIA",
            775423.26,
            "USD",
            "PESO DA CONTA (%)",
            "25.16%",
        ],
        [
            "LIQUIDEZ",
            2,
            "SALDO NA MOEDA DE REFERÊNCIA",
            600000.00,
            "USD",
            "PESO DA CONTA (%)",
            "19.47%",
        ],
        [None],
        [
            "RENDA FIXA INVESTMENT GRADE TÍTULOS",
            "ISIN",
            "FREQUÊNCIA",
            "NOME DA CARTEIRA",
            "VALOR DO MERCADO",
            "MOEDA",
            "SALDO MOEDA REFERÊNCIA",
        ],
        ["Issuer A", "US0000000001", "5.25%", "JOLIKA", 500000.00, "USD", 520000.00],
        ["Issuer B", "US0000000002", "6.00%", "JOLIKA", 575000.00, "USD", 586902.92],
        ["TOTAL RENDA FIXA", None, None, None, 1075000.00, "USD", 1106902.92],
        [None],
        [
            "RENDA VARIÁVEL AÇÕES",
            "ISIN",
            "NOME DA CARTEIRA",
            "VALOR DO MERCADO",
            "MOEDA",
            "SALDO MOEDA REFERÊNCIA",
        ],
        ["Stock A", "US0000000003", "JOLIKA", 250000.00, "USD", 300000.00],
        ["Stock B", "US0000000004", "JOLIKA", 275000.00, "USD", 300000.00],
        [None],
        [
            "FUNDOS ALTERNATIVOS",
            "ISIN",
            "NOME DA CARTEIRA",
            "VALOR ESTIMADO",
            "MOEDA",
            "SALDO MOEDA REFERÊNCIA",
        ],
        ["Alternative A", "US0000000005", "JOLIKA", 375000.00, "USD", 400000.00],
        ["Alternative B", "US0000000006", "JOLIKA", 350000.00, "USD", 375423.26],
        [None],
        [
            "LIQUIDEZ",
            "NUMERO DE CONTA",
            "NOME DA CARTEIRA",
            "VALOR DO MERCADO",
            "MOEDA",
            "SALDO MOEDA REFERÊNCIA",
        ],
        ["Cash USD", "4005106", "JOLIKA", 300000.00, "USD", 300000.00],
        ["Sweep USD", "4005106", "JOLIKA", 300000.00, "USD", 300000.00],
    ]
    with zipfile.ZipFile(path, "w") as archive:
        row_xml = []
        for row_index, row in enumerate(rows, start=1):
            cells = []
            for column_index, value in enumerate(row, start=1):
                if value is None:
                    continue
                column = chr(ord("A") + column_index - 1)
                if isinstance(value, str):
                    cells.append(
                        f'<c r="{column}{row_index}" t="inlineStr"><is><t>{escape(value)}</t></is></c>'
                    )
                else:
                    cells.append(f'<c r="{column}{row_index}"><v>{value}</v></c>')
            row_xml.append(f'<row r="{row_index}">{"".join(cells)}</row>')
        archive.writestr(
            "xl/worksheets/sheet1.xml",
            '<?xml version="1.0"?><worksheet '
            'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            f'<sheetData>{"".join(row_xml)}</sheetData></worksheet>',
        )
        archive.writestr(
            "xl/workbook.xml",
            '<?xml version="1.0"?><workbook '
            'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            '<sheets><sheet name="Posições" sheetId="1" r:id="rId1"/></sheets></workbook>',
        )
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            '<?xml version="1.0"?><Relationships '
            'xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
            'Target="worksheets/sheet1.xml"/></Relationships>',
        )
    return path


def post_json(server, path, payload):
    body = json.dumps(payload).encode()
    connection = http.client.HTTPConnection("127.0.0.1", server.server_port)
    connection.request(
        "POST",
        path,
        body=body,
        headers={"Content-Type": "application/json", "Content-Length": len(body)},
    )
    response = connection.getresponse()
    data = json.loads(response.read())
    connection.close()
    return response.status, data


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
    assert payload["files"] == [
        {
            "name": UBS_FIXTURE.name,
            "institution": "UBS",
            "position_count": 28,
        }
    ]
    assert payload["diagnostics"][0]["institution"] == "UBS"
    assert len(payload["positions"]) == 28
    assert set(payload["positions"][0]) == {
        "institution",
        "owner",
        "account",
        "asset_class",
        "asset_subclass",
        "asset_name",
        "identifier",
        "identifier_type",
        "quantity",
        "unit_price",
        "market_value",
        "currency",
        "portfolio_weight",
        "reference_date",
        "source_file",
    }
    assert payload["positions"][0]["owner"] == "JOLIKA"
    assert not payload["positions"][0]["source_file"].startswith("/")
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
    assert payload["diagnostics"] == [
        {
            "institution": "UBS",
            "position_count": 56,
            "warnings": payload["diagnostics"][0]["warnings"],
        }
    ]
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


def test_dashboard_uses_only_confirmed_session_import(server):
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
    assert dashboard["positions"] == imported["positions"]
    assert {item["institution"] for item in dashboard["positions"]} == {"UBS"}
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
        connection.request(
            "POST",
            "/api/portfolios/import",
            body=body,
            headers={
                "Content-Type": content_type,
                "Content-Length": len(body),
                "Cookie": cookie,
            },
        )
        second_response = connection.getresponse()
        second = json.loads(second_response.read())
        connection.close()

        body, content_type = multipart([("santander.xlsx", b"3")])
        connection = http.client.HTTPConnection("127.0.0.1", server.server_port)
        connection.request(
            "POST",
            "/api/portfolios/import",
            body=body,
            headers={
                "Content-Type": content_type,
                "Content-Length": len(body),
                "Cookie": cookie,
            },
        )
        third_response = connection.getresponse()
        third = json.loads(third_response.read())
        connection.close()

    assert first["dashboard"]["session"]["analyzed_institutions"] == ["Santander"]
    assert second["dashboard"]["session"]["analyzed_institutions"] == [
        "Santander",
        "UBS",
    ]
    assert third["dashboard"]["session"]["analyzed_institutions"] == [
        "Santander",
        "UBS",
    ]
    positions = SESSION_PORTFOLIOS[cookie.split("=", 1)[1]]["positions"]
    assert [(item.institution, item.identifier) for item in positions] == [
        ("UBS", "UBS-1"),
        ("Santander", "SAN-NOVO"),
    ]
    assert third["dashboard"]["consolidated"]["totals_by_currency"] == {
        "USD": "500",
    }
    assert [
        (item["institution"], item["identifier"]) for item in third["positions"]
    ] == [
        ("UBS", "UBS-1"),
        ("Santander", "SAN-NOVO"),
    ]


def test_invalid_import_clears_existing_session_and_returns_empty_dashboard(server):
    _, _, set_cookie = post_files(
        server, [(UBS_FIXTURE.name, UBS_FIXTURE.read_bytes())]
    )
    assert set_cookie is not None
    session_id = set_cookie.split(";", 1)[0].split("=", 1)[1]
    body, content_type = multipart([("invalid.pdf", b"invalid")])
    connection = http.client.HTTPConnection("127.0.0.1", server.server_port)
    connection.request(
        "POST",
        "/api/portfolios/import",
        body=body,
        headers={
            "Content-Type": content_type,
            "Content-Length": len(body),
            "Cookie": set_cookie.split(";", 1)[0],
        },
    )
    response = connection.getresponse()
    payload = json.loads(response.read())
    connection.close()

    assert response.status == 400
    assert payload["positions"] == []
    assert payload["dashboard"]["institutions"] == []
    assert payload["dashboard"]["consolidated"]["position_count"] == 0
    assert session_id not in SESSION_PORTFOLIOS


def test_clear_all_portfolios_empties_session_and_dashboard(server):
    _, _, set_cookie = post_files(
        server, [(UBS_FIXTURE.name, UBS_FIXTURE.read_bytes())]
    )
    assert set_cookie is not None
    cookie = set_cookie.split(";", 1)[0]

    status, payload = request_with_cookie(server, "DELETE", "/api/portfolios", cookie)

    assert status == 200
    assert payload["ok"] is True
    assert payload["dashboard"]["institutions"] == []
    assert payload["dashboard"]["consolidated"]["position_count"] == 0
    assert payload["positions"] == []
    assert cookie.split("=", 1)[1] not in SESSION_PORTFOLIOS


def test_dashboard_without_session_is_empty(server):
    status, payload = request_with_cookie(server, "GET", "/api/dashboard", "")
    assert status == 200
    assert payload["positions"] == []
    assert payload["institutions"] == []
    assert payload["consolidated"]["position_count"] == 0


def test_santander_real_structure_inspect_and_import_match(server, tmp_path):
    fixture = santander_real_structure_workbook(tmp_path)
    encoded = base64.b64encode(fixture.read_bytes()).decode()

    inspect_status, inspected = post_json(
        server,
        "/api/santander/inspect",
        {
            "file": {"name": fixture.name, "content": encoded},
        },
    )
    import_status, imported, _ = post_files(
        server, [(fixture.name, fixture.read_bytes())]
    )

    assert inspect_status == 200
    assert inspected["ok"] is True
    assert inspected["position_count"] > 1
    assert import_status == 200
    assert imported["ok"] is True
    assert imported["files"] == [
        {
            "name": fixture.name,
            "institution": "Santander",
            "position_count": inspected["position_count"],
        }
    ]
    assert len(imported["positions"]) == inspected["position_count"]
    assert {position["institution"] for position in imported["positions"]} == {
        "Santander"
    }
    assert {position["currency"] for position in imported["positions"]} == {"USD"}
    total = sum(Decimal(position["market_value"]) for position in imported["positions"])
    assert total == pytest.approx(Decimal("3082326.18"), abs=Decimal("0.01"))
    assert {position["asset_class"] for position in imported["positions"]} >= {
        "Renda Fixa",
        "Ação",
        "Alternativos",
        "Caixa",
    }
    assert all(
        "csv" not in warning.lower()
        for diagnostic in imported["diagnostics"]
        for warning in diagnostic["warnings"]
    )
    fixed_income = next(
        position
        for position in imported["positions"]
        if position["asset_class"] == "Renda Fixa"
    )
    assert fixed_income["identifier"] == "US0000000001"
    assert fixed_income["asset_name"].startswith("Issuer A")
    assert fixed_income["market_value"] == "520000.0"
