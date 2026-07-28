import json
import threading
from datetime import date
from decimal import Decimal
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.request import urlopen

from backend.dashboard import build_dashboard
from backend.models import PortfolioPosition
from backend.server import ArgosRequestHandler


def position(institution, symbol, value, currency="USD"):
    return PortfolioPosition(
        institution=institution,
        account=None,
        asset_class=None,
        asset_subclass=None,
        asset_name=symbol,
        identifier=symbol,
        identifier_type="ticker",
        quantity=None,
        unit_price=None,
        market_value=Decimal(value),
        currency=currency,
        portfolio_weight=None,
        reference_date=None,
        source_file=f"{institution}.csv",
    )


def test_empty_dashboard_response():
    result = build_dashboard([], current_date=date(2026, 7, 28))

    assert result["header"] == {
        "current_date": "2026-07-28",
        "version": "1.0",
    }
    assert result["institutions"] == []
    assert result["consolidated"] == {
        "institution_count": 0,
        "position_count": 0,
        "unique_asset_count": 0,
        "repeated_asset_count": 0,
        "totals_by_currency": {},
        "warnings": [],
    }


def test_dashboard_diagnoses_multiple_institutions():
    result = build_dashboard(
        [
            position("UBS", "AAA", "100"),
            position("UBS", "BBB", "20", "EUR"),
            position("Santander", "AAA", "50"),
        ],
        current_date=date(2026, 7, 28),
    )

    assert [item["name"] for item in result["institutions"]] == [
        "Santander",
        "UBS",
    ]
    assert result["institutions"][1]["currencies"] == ["EUR", "USD"]
    assert result["consolidated"]["institution_count"] == 2
    assert result["consolidated"]["position_count"] == 3
    assert result["consolidated"]["unique_asset_count"] == 2
    assert result["consolidated"]["repeated_asset_count"] == 1
    assert result["consolidated"]["totals_by_currency"] == {
        "EUR": "20",
        "USD": "150",
    }


def test_dashboard_endpoint_returns_single_structure():
    server = ThreadingHTTPServer(("127.0.0.1", 0), ArgosRequestHandler)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    try:
        with urlopen(
            f"http://127.0.0.1:{server.server_port}/api/dashboard"
        ) as response:
            payload = json.load(response)

        assert response.status == 200
        assert set(payload) == {
            "header",
            "important_facts",
            "institutions",
            "consolidated",
        }
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_frontend_consumes_and_exposes_dashboard_sections():
    app = Path("frontend/app.js").read_text(encoding="utf-8")
    page = Path("frontend/index.html").read_text(encoding="utf-8")

    assert 'fetch("/api/dashboard"' in app
    assert "renderDashboard(await response.json())" in app
    for element_id in (
        "importantFacts",
        "institutions",
        "consolidated",
        "toggleValues",
    ):
        assert f'id="{element_id}"' in page
