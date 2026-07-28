from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from backend.daily.context_service import DailyContextService, MarketEvent
from backend.daily.experience import (
    PANORAMA_TOPICS,
    PRIORITY_LEVELS,
    build_daily_experience,
)
from backend.models import PortfolioPosition


AS_OF = datetime(2026, 7, 28, 15, 0, tzinfo=timezone.utc)


def position(identifier, name=None, institution="UBS"):
    return PortfolioPosition(
        institution=institution,
        account=None,
        asset_class=None,
        asset_subclass=None,
        asset_name=name or identifier,
        identifier=identifier,
        identifier_type="ticker",
        quantity=None,
        unit_price=None,
        market_value=Decimal("100"),
        currency="USD",
        portfolio_weight=None,
        reference_date=None,
        source_file=f"{institution}.csv",
    )


def event(identifier, hours_ago, priority="Baixa", assets=(), macro=False):
    return MarketEvent(
        identifier=identifier,
        title=f"Fato {identifier}",
        category="Mercados",
        source="Mock de teste",
        occurred_at=AS_OF - timedelta(hours=hours_ago),
        priority=priority,
        summary=f"Resumo {identifier}",
        related_assets=assets,
        macro_impact=macro,
    )


def test_aggregator_applies_24_hour_window_limit_and_ordering():
    events = [
        event("old", 25, "Alta"),
        event("low", 1, "Baixa"),
        event("high-old", 8, "Alta"),
        event("high-new", 2, "Alta"),
        event("moderate", 1, "Moderada"),
        event("extra-1", 3),
        event("extra-2", 4),
    ]

    result = DailyContextService(events).generate((), now=AS_OF)

    assert len(result["facts"]) == 5
    assert [fact["id"] for fact in result["facts"][:3]] == [
        "high-new", "high-old", "moderate",
    ]
    assert "old" not in {fact["id"] for fact in result["facts"]}


def test_portfolio_match_increases_priority_and_exposes_context():
    result = DailyContextService([
        event("nvidia", 3, "Moderada", ("NVDA", "NVIDIA")),
    ]).generate([position("NVDA", "NVIDIA Corp")], now=AS_OF)

    fact = result["facts"][0]
    assert fact["priority"] == "Alta"
    assert fact["base_priority"] == "Moderada"
    assert fact["matched_portfolio_assets"] == ["NVDA"]
    assert fact["context_type"] == "portfolio"
    assert fact["context"] == "Relacionado à carteira: NVDA"


def test_macro_and_general_context_are_clear_without_portfolio():
    result = DailyContextService([
        event("fed", 1, "Alta", macro=True),
        event("market", 2),
    ]).generate((), now=AS_OF)

    assert result["has_portfolio_context"] is False
    assert result["facts"][0]["context"] == "Contexto macro geral de mercado"
    assert result["facts"][1]["context"] == "Contexto geral de mercado"


def test_daily_contract_uses_real_structured_facts_without_portfolio():
    daily = build_daily_experience(
        (), current_date=date(2026, 7, 28), now=AS_OF,
    )

    assert daily["lookback_hours"] == 24
    assert daily["context_scope"] == "general"
    assert len(daily["important_facts"]) == 5
    assert daily["important_facts"][0]["source"] == "Mock Federal Reserve"
    assert daily["contracts"]["priority_levels"] == list(PRIORITY_LEVELS)
    assert tuple(item["topic"] for item in daily["global_overview"]) == (
        PANORAMA_TOPICS
    )
    assert all(item["status"] == "Atualizado" for item in daily["global_overview"])


def test_daily_contract_contextualizes_nvidia_and_ethereum_positions():
    daily = build_daily_experience(
        [position("NVDA"), position("ETH", institution="Monte Bravo")],
        current_date=date(2026, 7, 28),
        now=AS_OF,
    )

    facts = {fact["id"]: fact for fact in daily["important_facts"]}
    assert daily["context_scope"] == "portfolio"
    assert facts["nvidia-chips"]["priority"] == "Alta"
    assert facts["nvidia-chips"]["matched_portfolio_assets"] == ["NVDA"]
    assert facts["ethereum-network"]["priority"] == "Alta"
    assert facts["ethereum-network"]["matched_portfolio_assets"] == ["ETH"]
    assert {analysis["related_to"] for analysis in daily["analyses"]} >= {
        "NVDA", "ETH",
    }
