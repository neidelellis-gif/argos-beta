import json
import threading
from datetime import date, datetime, timedelta, timezone
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
        "version": "2.2",
    }
    assert result["daily"]["generated_for"] == "2026-07-28"
    assert result["daily"]["lookback_hours"] == 24
    assert result["daily"]["context_scope"] == "general"
    assert result["daily"]["important_facts"] == []
    assert result["daily"]["sources"]["facts"]["status"] == "unavailable"
    assert result["daily"]["contracts"]["priority_levels"] == [
        "Alta", "Moderada", "Baixa",
    ]
    assert len(result["daily"]["global_overview"]) == 5
    assert result["daily"]["market_agenda"] == []
    assert result["session"] == {
        "last_import_at": None,
        "institution_count": 0,
        "position_count": 0,
        "analyzed_institutions": [],
        "status": "waiting_import",
    }
    assert result["daily_situation"] == [{
        "status": "waiting",
        "message": "Nenhuma carteira carregada",
    }]
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
    imported_at = datetime(2026, 7, 28, 14, 35, tzinfo=timezone.utc)
    result = build_dashboard(
        [
            position("UBS", "AAA", "100"),
            position("UBS", "BBB", "20", "EUR"),
            position("Santander", "AAA", "50"),
        ],
        current_date=date(2026, 7, 28),
        last_import_at=imported_at,
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
    assert result["session"] == {
        "last_import_at": "2026-07-28T14:35:00+00:00",
        "institution_count": 2,
        "position_count": 3,
        "analyzed_institutions": ["Santander", "UBS"],
        "status": "active",
    }
    assert result["daily_situation"][0]["message"] == (
        "2 instituições analisadas"
    )
    assert result["modules"][0] == {
        "id": "portfolios",
        "title": "Carteiras",
        "status": "completed",
        "message": "2 instituições analisadas",
    }
    assert result["daily"]["context_scope"] == "portfolio"
    assert result["daily"]["context_scope"] == "portfolio"


def test_dashboard_reports_one_analyzed_institution():
    result = build_dashboard(
        [position("UBS", "AAA", "100")],
        last_import_at=datetime(2026, 7, 28, 15, 0, tzinfo=timezone.utc),
    )

    assert result["session"]["institution_count"] == 1
    assert result["session"]["position_count"] == 1
    assert result["session"]["analyzed_institutions"] == ["UBS"]
    assert result["modules"][0]["message"] == "1 instituição analisada"


def test_old_import_does_not_shift_daily_market_window():
    imported_at = datetime(2026, 7, 20, 10, 0, tzinfo=timezone.utc)
    now = datetime(2026, 7, 28, 15, 0, tzinfo=timezone.utc)

    result = build_dashboard(
        [position("UBS", "NVDA", "100")],
        current_date=now.date(),
        last_import_at=imported_at,
        now=now,
    )

    assert result["session"]["last_import_at"] == imported_at.isoformat()
    assert result["daily"]["generated_at"] == now.isoformat()
    occurred_at = [
        datetime.fromisoformat(fact["occurred_at"])
        for fact in result["daily"]["important_facts"]
    ]
    assert all(
        now - timedelta(hours=24) <= event_time <= now
        for event_time in occurred_at
    )
    assert all(event_time > imported_at for event_time in occurred_at)


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
            "daily",
            "labels",
            "session",
            "daily_situation",
            "modules",
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
        "dailyPriorities",
        "dailyAnalyses",
        "dailyPanorama",
        "marketAgenda",
        "institutions",
        "consolidated",
        "toggleValues",
        "lastUpdate",
        "executiveCards",
        "moduleCards",
    ):
        assert f'id="{element_id}"' in page
    assert "loadCockpit();" not in app


def test_duplicate_operational_panorama_is_removed():
    app = Path("frontend/app.js").read_text(encoding="utf-8")
    page = Path("frontend/index.html").read_text(encoding="utf-8")
    assert 'id="globalOverview"' not in page
    assert "Aguardando integração da Inteligência de Mercado" not in app
    assert 'id="marketAgendaPanel"' in page
