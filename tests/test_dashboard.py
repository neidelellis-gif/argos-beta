import json
import threading
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.request import urlopen

import pytest

import backend.dashboard as dashboard_module
import backend.daily.experience as experience_module
from backend.daily.experience import build_daily_experience
from backend.daily.context_service import DAILY_LOOKBACK_HOURS
from backend.dashboard import build_dashboard
from backend.models import EconomicAssetClass, PortfolioOwner, PortfolioPosition
from backend.server import ArgosRequestHandler


def position(
    institution,
    symbol,
    value,
    currency="USD",
    economic_class=EconomicAssetClass.EQUITIES,
    owner=PortfolioOwner.JOLIKA,
):
    return PortfolioPosition(
        institution=institution,
        owner=owner,
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
        economic_asset_class=economic_class,
    )


def test_dashboard_uses_daily_orchestrator_with_exact_inputs(monkeypatch):
    positions = [position("UBS", "AAA", "100")]
    expected_positions = tuple(positions)
    current_date = date(2026, 7, 28)
    now = datetime(2026, 7, 28, 15, 0, tzinfo=timezone.utc)
    expected_daily = build_daily_experience(expected_positions, current_date, now)
    calls = []

    class RecordingOrchestrator:
        def build(self, received_positions, current_date=None, now=None):
            calls.append((received_positions, current_date, now))
            return expected_daily

    monkeypatch.setattr(dashboard_module, "DailyOrchestrator", RecordingOrchestrator)

    result = build_dashboard(positions, current_date=current_date, now=now)

    assert calls == [(expected_positions, current_date, now)]
    assert result["daily"] is expected_daily


def test_dashboard_does_not_call_build_daily_experience(monkeypatch):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("build_daily_experience must not be called")

    monkeypatch.setattr(
        experience_module,
        "build_daily_experience",
        fail_if_called,
    )

    result = build_dashboard([], current_date=date(2026, 7, 28))

    assert result["daily"]["generated_for"] == "2026-07-28"


def test_orchestrated_daily_payload_matches_legacy_contract():
    positions = [position("UBS", "NVDA", "100")]
    current_date = date(2026, 7, 28)
    now = datetime(2026, 7, 28, 15, 0, tzinfo=timezone.utc)

    expected = build_daily_experience(positions, current_date, now)
    actual = build_dashboard(
        positions,
        current_date=current_date,
        now=now,
    )["daily"]

    assert actual == expected
    assert actual["sources"] == expected["sources"]
    assert actual["global_overview"] == expected["global_overview"]
    assert actual["market_agenda"] == expected["market_agenda"]
    assert actual["important_facts"] == expected["important_facts"]


def test_empty_dashboard_response():
    result = build_dashboard([], current_date=date(2026, 7, 28))

    assert result["header"] == {
        "current_date": "2026-07-28",
        "version": "2.3",
    }
    assert result["daily"]["generated_for"] == "2026-07-28"
    assert result["daily"]["lookback_hours"] == DAILY_LOOKBACK_HOURS
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
        "economic_allocation_by_currency": {},
        "warnings": [],
        "intelligence": {
            "original_position_count": 0,
            "consolidated_asset_count": 0,
            "institutions": [],
            "currencies": [],
            "totals_by_currency": {},
            "economic_allocation_by_currency": {},
            "concentration_by_currency": [],
            "coverage": {
                "original_position_count": 0,
                "consolidated_asset_count": 0,
                "assets_with_economic_class": 0,
                "assets_without_economic_class": 0,
                "assets_with_identifier": 0,
                "assets_without_identifier": 0,
            },
            "duplicate_exposures": [],
            "consolidation_alerts": [],
            "priority": {
                "level": "Baixa",
                "reasons": [],
            },
            "materiality": {
                "level": "Baixa",
                "max_position_weight": "0",
                "driver": None,
            },
            "diversification": {
                "level": "Alta",
                "asset_hhi": "0",
                "class_hhi": "0",
                "driver": None,
            },
            "portfolio_reading": (
                "Ainda não há carteira carregada para fazer uma leitura."
            ),
            "source_files": [],
        },
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

    assert result["institutions"][0]["intelligence"]["consolidated_asset_count"] == 1
    assert result["institutions"][0]["intelligence"]["priority"]["level"] == "Alta"

    assert result["institutions"][1]["intelligence"]["consolidated_asset_count"] == 2
    assert result["institutions"][1]["intelligence"]["concentration_by_currency"][0]["currency"] == "EUR"
    assert result["institutions"][1]["intelligence"]["concentration_by_currency"][1]["currency"] == "USD"

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
        now - timedelta(hours=DAILY_LOOKBACK_HOURS) <= event_time <= now
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
            "positions",
        }
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_dashboard_endpoint_accepts_empty_cache_ttl_setting(monkeypatch):
    monkeypatch.setenv("ARGOS_DAILY_CACHE_TTL_SECONDS", "")
    server = ThreadingHTTPServer(("127.0.0.1", 0), ArgosRequestHandler)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    try:
        with urlopen(
            f"http://127.0.0.1:{server.server_port}/api/dashboard"
        ) as response:
            payload = json.load(response)

        assert response.status == 200
        assert "error" not in payload
        assert payload["header"]["version"] == "2.3"
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_frontend_consumes_and_exposes_dashboard_sections():
    app = Path("frontend/app.js").read_text(encoding="utf-8")
    page = Path("frontend/index.html").read_text(encoding="utf-8")

    assert 'fetch("/api/dashboard"' in app
    assert "storeCanonicalPortfolioPositions(result.positions)" in app
    assert "renderDashboard(dashboard)" in app
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


def test_dashboard_exposes_institution_and_consolidated_economic_allocations():
    result = build_dashboard(
        [
            position("UBS", "CASH", "100000.00", economic_class=EconomicAssetClass.CASH),
            position("UBS", "BOND", "2500000.00", economic_class=EconomicAssetClass.FIXED_INCOME),
            position("Santander", "CASH", "50000.00", economic_class=EconomicAssetClass.CASH),
            position("Santander", "EUR-BOND", "20.00", "EUR", EconomicAssetClass.FIXED_INCOME),
        ]
    )

    assert [item["name"] for item in result["institutions"]] == ["Santander", "UBS"]
    assert result["institutions"][0]["economic_allocation_by_currency"] == {
        "EUR": {"Renda Fixa": "20.00"},
        "USD": {"Caixa": "50000.00"},
    }
    assert result["institutions"][1]["economic_allocation_by_currency"] == {
        "USD": {"Caixa": "100000.00", "Renda Fixa": "2500000.00"}
    }
    assert result["consolidated"]["economic_allocation_by_currency"] == {
        "EUR": {"Renda Fixa": "20.00"},
        "USD": {"Caixa": "150000.00", "Renda Fixa": "2500000.00"},
    }


@pytest.mark.parametrize(
    "positions",
    (
        [position("Bradesco", "AAA", "10", owner=PortfolioOwner.NEI)],
        [
            position("UBS", "AAA", "100"),
            position("Bradesco", "BBB", "10", owner=PortfolioOwner.NEI),
        ],
    ),
)
def test_dashboard_rejects_nei_before_any_processing(monkeypatch, positions):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("processing must not start for a non-JOLIKA portfolio")

    monkeypatch.setattr(dashboard_module, "consolidate_portfolio_positions", fail_if_called)
    monkeypatch.setattr(dashboard_module, "DailyOrchestrator", fail_if_called)

    with pytest.raises(ValueError, match="accepts only JOLIKA"):
        build_dashboard(positions)


def test_dashboard_exposes_jolika_intelligence_inside_consolidated():
    result = build_dashboard(
        [
            position("UBS", "AAA", "100"),
            position("Santander", "AAA", "50"),
            position(
                "UBS",
                "BBB",
                "50",
                economic_class=EconomicAssetClass.FIXED_INCOME,
            ),
        ],
        current_date=date(2026, 8, 19),
    )

    intelligence = result["consolidated"]["intelligence"]

    assert intelligence["consolidated_asset_count"] == 2
    assert intelligence["institutions"] == ["Santander", "UBS"]
    assert intelligence["currencies"] == ["USD"]
    assert intelligence["totals_by_currency"] == {"USD": "200"}

    assert intelligence["coverage"] == {
        "original_position_count": 3,
        "consolidated_asset_count": 2,
        "assets_with_economic_class": 2,
        "assets_without_economic_class": 0,
        "assets_with_identifier": 2,
        "assets_without_identifier": 0,
    }

    assert len(intelligence["duplicate_exposures"]) == 1
    assert intelligence["duplicate_exposures"][0] == {
        "asset_key": "aaa",
        "institutions": ["Santander", "UBS"],
        "within_same_institution": False,
        "across_institutions": True,
        "source_position_count": 2,
    }

    assert (
        "Duplicate positions found across institutions"
        in intelligence["consolidation_alerts"]
    )

    assert intelligence["priority"] == {
        "level": "Alta",
        "reasons": [
            "concentration",
            "cross_institution_duplicate",
        ],
    }

    assert intelligence["materiality"] == {
        "level": "Alta",
        "max_position_weight": "0.75",
        "driver": "concentration",
    }

    assert intelligence["diversification"] == {
        "level": "Baixa",
        "asset_hhi": "0.6250",
        "class_hhi": "0.6250",
        "driver": "asset_and_class_concentration",
    }

    assert intelligence["portfolio_reading"] == (
        "A carteira está concentrada em poucos ativos e isso merece mais atenção agora. "
        "A distribuição entre classes também está mais limitada."
    )
