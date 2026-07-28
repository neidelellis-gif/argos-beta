from datetime import date, datetime, timezone
from decimal import Decimal

from backend.daily.experience import (
    PANORAMA_TOPICS,
    PRIORITY_LEVELS,
    build_daily_experience,
)
from backend.models import PortfolioPosition


def position(institution):
    return PortfolioPosition(
        institution=institution,
        account=None,
        asset_class=None,
        asset_subclass=None,
        asset_name="Example",
        identifier="EXAMPLE",
        identifier_type="ticker",
        quantity=None,
        unit_price=None,
        market_value=Decimal("100"),
        currency="USD",
        portfolio_weight=None,
        reference_date=None,
        source_file=f"{institution}.csv",
    )


def test_daily_contract_has_only_approved_priority_levels():
    daily = build_daily_experience((), current_date=date(2026, 7, 28))

    assert daily["lookback_hours"] == 24
    assert len(daily["important_facts"]) <= 5
    assert daily["contracts"]["priority_levels"] == list(PRIORITY_LEVELS)
    assert {
        item["priority"] for item in daily["important_facts"]
    }.issubset(PRIORITY_LEVELS)
    assert {
        item["level"] for item in daily["priorities"]
    }.issubset(PRIORITY_LEVELS)


def test_daily_contract_exposes_all_future_intelligence_topics():
    daily = build_daily_experience(())

    assert tuple(
        item["topic"] for item in daily["global_overview"]
    ) == PANORAMA_TOPICS
    assert daily["contracts"]["agenda_event_types"] == [
        "Resultados",
        "Bancos centrais",
        "Inflação",
        "Emprego",
        "Dividendos",
        "Vencimentos",
    ]


def test_daily_context_updates_from_official_portfolio_data():
    imported_at = datetime(2026, 7, 28, 13, 0, tzinfo=timezone.utc)
    daily = build_daily_experience(
        (position("UBS"), position("Santander")),
        last_import_at=imported_at,
    )

    assert daily["important_facts"][0]["title"] == (
        "Contexto das carteiras atualizado"
    )
    assert "2 posições" in daily["important_facts"][0]["summary"]
    assert daily["analyses"][0]["related_to"] == "Santander, UBS"
    assert daily["analyses"][0]["updated_at"] == imported_at.isoformat()
